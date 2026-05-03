"""Per-batch dispatch aggregator for samvil-build Phase B (T4.8 ultra-thin).

The build skill enters Phase B (or Phase B-Tree for v3 seeds) once per
feature, then iterates batches of leaves until all are built. This
module owns the batch-composition and worker-context preparation work
that previously lived inline in the 1432-LOC SKILL body:

  1. **MAX_PARALLEL** — resolve from `config.max_parallel` (user
     override) → CPU-core heuristic → memory-pressure clamp. Returns
     a single integer + the inputs that drove it (for retro).
  2. **batch leaves** — call into `ac_tree.next_buildable_leaves` to
     pick the next chunk respecting the in-progress completed_ids
     set, the current `tree_json`, and `max_parallel`. (Skill body
     calls `update_leaf_status` after each spawn — that stays inline
     because it's per-leaf and depends on Agent results.)
  3. **worker context bundle** — for each leaf in the batch, render
     the ≤2000-token Agent prompt context (`feature_summary`,
     `architecture_summary`, `peers_list`, `recipe_pointer`, plus
     the Worker Contract block with the parser shape). This makes
     the skill body's "spawn N agents in one message" loop
     mechanical: it just walks `worker_bundles` and shells out.
  4. **independence check** — when there are 2+ features in the
     same chunk (legacy Phase B path for game/automation/mobile),
     run the file-overlap heuristic and downgrade conflicting
     pairs to sequential.
  5. **circuit-breaker hint** — surface the previous batch's
     `consecutive_fail_batches` count (read from checkpoint) so the
     skill body knows when to stop. Skill is still the one that
     bumps the counter — easier to reason about there.

What stays in the skill body (CC-bound, P8):
  - The parallel-Agent dispatch (`Agent()` × N in ONE message).
  - Worker reply parsing (the literal `Leaf: <id>\\nfiles_created:
    [...]` block format).
  - `update_leaf_status` per Agent result (per-leaf, depends on the
    Agent's reply).
  - `rate_budget_acquire` / `rate_budget_release` per Agent (per-leaf).
  - `save_checkpoint` after every batch (state-mutating).
  - `tree_progress` / HUD render (per-batch progress display).

All reads are best-effort. Missing files yield empty defaults and a
non-fatal entry in `errors[]`. Never raises. Honors INV-1 / INV-5.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ac_tree import (
    ACNode,
    next_buildable_leaves as _next_buildable_leaves,
    tree_progress as _tree_progress,
)

# ac_search imported lazily inside functions (INV-5: missing index is non-fatal)
try:
    from .ac_search import (
        search_ac_tree as _fts_search,
        search_ac_tree_by_feature as _fts_by_feature,
    )
    _AC_SEARCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AC_SEARCH_AVAILABLE = False

BUILD_PHASE_B_SCHEMA_VERSION = "1.0"


# ── MAX_PARALLEL resolution ──────────────────────────────────────────


def _detect_cpu_cores() -> int:
    """Best-effort CPU core count. Returns 1 on failure (safest)."""
    try:
        return os.cpu_count() or 1
    except Exception:  # pragma: no cover - defensive
        return 1


def _detect_memory_pressure_pct() -> float | None:
    """Best-effort memory pressure read (Linux + macOS).

    Returns a float 0..100 or None when we can't determine. None
    means "skip the memory clamp" — the skill body still uses the
    CPU-derived MAX_PARALLEL.
    """
    # Try psutil if available (more accurate, cross-platform).
    try:
        import psutil  # type: ignore

        return float(psutil.virtual_memory().percent)
    except Exception:  # noqa: BLE001
        pass

    # Linux fallback: parse /proc/meminfo.
    try:
        meminfo = Path("/proc/meminfo").read_text()
        kv: dict[str, int] = {}
        for line in meminfo.splitlines():
            parts = line.split(":")
            if len(parts) != 2:
                continue
            value = parts[1].strip().split()
            if value:
                try:
                    kv[parts[0].strip()] = int(value[0])
                except ValueError:
                    continue
        total = kv.get("MemTotal", 0)
        avail = kv.get("MemAvailable", kv.get("MemFree", 0))
        if total > 0:
            return round((1.0 - avail / total) * 100.0, 1)
    except Exception:  # noqa: BLE001
        pass
    return None


def resolve_max_parallel(
    config: dict[str, Any] | None,
    *,
    cpu_cores: int | None = None,
    memory_pct: float | None = None,
) -> dict[str, Any]:
    """Pure function — given config + system metrics, return MAX_PARALLEL.

    Precedence:
      1. `config.max_parallel` (user override, integer ≥ 1).
      2. CPU-core heuristic: ≤4 → 1, ≥8 → 3, else 2.
      3. Memory clamp: if pct > 80, subtract 1 (min 1).

    Args:
        config: Project config (may carry `max_parallel`).
        cpu_cores: Override for tests. None → autodetect.
        memory_pct: Override for tests. None → autodetect.

    Returns:
        dict with `max_parallel` (int) + `cpu_cores` + `memory_pct`
        + `source` ("config" / "cpu" / "cpu+memory_clamp") for retro
        instrumentation.
    """
    config = config or {}
    if cpu_cores is None:
        cpu_cores = _detect_cpu_cores()
    if memory_pct is None:
        memory_pct = _detect_memory_pressure_pct()

    # 1. User override wins.
    user_override = config.get("max_parallel")
    if isinstance(user_override, int) and user_override >= 1:
        return {
            "max_parallel": user_override,
            "cpu_cores": cpu_cores,
            "memory_pct": memory_pct,
            "source": "config",
        }

    # 2. CPU-core heuristic.
    if cpu_cores <= 4:
        base = 1
    elif cpu_cores >= 8:
        base = 3
    else:
        base = 2

    # 3. Memory clamp.
    source = "cpu"
    if memory_pct is not None and memory_pct > 80.0 and base > 1:
        base -= 1
        source = "cpu+memory_clamp"

    return {
        "max_parallel": base,
        "cpu_cores": cpu_cores,
        "memory_pct": memory_pct,
        "source": source,
    }


# ── Worker context bundle ────────────────────────────────────────────


def _summarize_tech_stack(tech_stack: dict[str, Any]) -> str:
    """One-line tech_stack summary, ≤80 chars."""
    if not tech_stack:
        return "Unknown stack"
    parts: list[str] = []
    framework = tech_stack.get("framework")
    if framework:
        parts.append(str(framework))
    ui = tech_stack.get("ui_library") or tech_stack.get("ui")
    if ui:
        parts.append(str(ui))
    state = tech_stack.get("state")
    if state:
        parts.append(str(state))
    language = tech_stack.get("language")
    if language:
        parts.append(str(language))
    return " + ".join(parts)[:80] if parts else "Unknown stack"


def _summarize_architecture(blueprint: dict[str, Any]) -> str:
    """5-10 line architecture summary from blueprint.

    Pulls `directory_structure`, `component_hierarchy`, or
    `architecture` and renders a compact tree. Returns a placeholder
    when blueprint is missing.
    """
    if not blueprint:
        return "(blueprint not available — derive from existing scaffold)"

    arch = blueprint.get("architecture") or {}
    dirs = arch.get("directory_structure") or blueprint.get("directory_structure")
    if isinstance(dirs, str):
        return dirs[:500]
    if isinstance(dirs, list):
        return "\n".join(str(d) for d in dirs[:10])
    if isinstance(dirs, dict):
        lines: list[str] = []
        for k, v in list(dirs.items())[:10]:
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
    # Fallback: dump first 300 chars of blueprint as summary.
    return json.dumps(arch or blueprint, indent=2)[:500]


def _peers_list(features: list[dict[str, Any]], current: str) -> list[str]:
    """List of OTHER feature names (for the Worker contract context)."""
    return [str(f.get("name", "")) for f in features if str(f.get("name", "")) != current]


def render_worker_context(
    seed: dict[str, Any],
    blueprint: dict[str, Any],
    feature: dict[str, Any],
    leaf: dict[str, Any],
    *,
    sibling_leaf_ids: list[str] | None = None,
    fts_sibling_leaves: list[dict[str, Any]] | None = None,
    cross_feature_related: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render the ≤2000-token Worker Agent context for one leaf.

    Args:
        fts_sibling_leaves: FTS5-fetched leaves for this feature (optional).
            Used to include sibling descriptions so workers understand
            what adjacent leaves are building.
        cross_feature_related: BM25 cross-feature leaves related to this
            leaf's description (optional). Helps workers avoid conflicts.

    Returns:
        dict with `persona_pointer`, `context`, `your_leaf`,
        `contract`, `reply_format` — the skill body assembles them
        into the Agent prompt.
    """
    tech_stack = seed.get("tech_stack") or {}
    features = seed.get("features") or []
    feature_name = str(feature.get("name", "unknown"))
    seed_name = str(seed.get("name", "project"))
    leaf_id = str(leaf.get("id", ""))

    sibling_context = [
        {"id": l["leaf_id"], "description": l["description"]}
        for l in (fts_sibling_leaves or [])
        if l.get("leaf_id") != leaf_id
    ]
    cross_context = [
        {"feature": l["feature_name"], "description": l["description"]}
        for l in (cross_feature_related or [])
    ]

    return {
        "persona_pointer": "agents/frontend-dev.md (paste content)",
        "context": {
            "project_path": f"~/dev/{seed_name}/",
            "stack": _summarize_tech_stack(tech_stack),
            "architecture": _summarize_architecture(blueprint),
            "feature": f"{feature_name} — {feature.get('description', '')[:100]}",
            "peers": ", ".join(_peers_list(features, feature_name)),
        },
        "your_leaf": {
            "leaf_id": leaf_id,
            "leaf_description": str(leaf.get("description", "")),
            "parent_id": str(leaf.get("parent_id") or "(root)"),
            "sibling_leaf_ids": list(sibling_leaf_ids or []),
            "sibling_leaf_context": sibling_context,
            "cross_feature_related": cross_context,
        },
        "contract": {
            "scope": f"Only create/modify files under components/{feature_name}/ (or blueprint equivalent)",
            "shared_files": "Do NOT modify shared files (layout.tsx, store root) without justification",
            "verify_command": (
                f"cd ~/dev/{seed_name} && npx tsc --noEmit 2>&1 | head -20 "
                "&& npx eslint . --quiet 2>&1 | head -20"
            ),
            "no_full_build": "Do NOT run `npm run build` — integration build is the main session's job",
        },
        "reply_format": (
            "Leaf: <leaf-id>\n"
            "files_created: [<paths>]\n"
            "files_modified: [<paths>]\n"
            "typecheck_ok: <true|false>\n"
            "lint_ok: <true|false>\n"
            "notes: <≤ 2 sentences>"
        ),
    }


# ── Independence check (legacy Phase B feature batches) ─────────────


def check_feature_independence(
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    """Heuristic independence check for parallel feature dispatch.

    Returns:
        dict with `independent_pairs` (list of [a, b] safe to run
        in parallel) and `sequential_pairs` (list of [a, b, reason]
        downgraded to sequential).

    Heuristic flags conflict when two features:
      - share an explicit `touched_files` entry,
      - have a `depends_on` link (implies ordering),
      - share a `routes` entry,
      - share a Zustand `store_slice`.
    """
    independent: list[list[str]] = []
    sequential: list[list[str]] = []
    n = len(features)
    for i in range(n):
        a = features[i]
        a_name = str(a.get("name", f"feat-{i}"))
        a_files = set(a.get("touched_files") or [])
        a_routes = set(a.get("routes") or [])
        a_slice = a.get("store_slice")
        a_deps = set(a.get("depends_on") or [])
        for j in range(i + 1, n):
            b = features[j]
            b_name = str(b.get("name", f"feat-{j}"))
            b_files = set(b.get("touched_files") or [])
            b_routes = set(b.get("routes") or [])
            b_slice = b.get("store_slice")
            b_deps = set(b.get("depends_on") or [])
            reasons: list[str] = []
            if a_files & b_files:
                reasons.append(f"shared files: {sorted(a_files & b_files)}")
            if a_routes & b_routes:
                reasons.append(f"shared routes: {sorted(a_routes & b_routes)}")
            if a_slice and a_slice == b_slice:
                reasons.append(f"shared store_slice: {a_slice}")
            if a_name in b_deps or b_name in a_deps:
                reasons.append("dependency link")
            if reasons:
                sequential.append([a_name, b_name, "; ".join(reasons)])
            else:
                independent.append([a_name, b_name])
    return {"independent_pairs": independent, "sequential_pairs": sequential}


# ── Aggregator ───────────────────────────────────────────────────────


@dataclass
class BuildPhaseBReport:
    schema_version: str = BUILD_PHASE_B_SCHEMA_VERSION
    feature: str = ""
    feature_num: int = 0
    max_parallel: int = 1
    parallel_meta: dict[str, Any] = field(default_factory=dict)
    batch: dict[str, Any] = field(default_factory=dict)
    worker_bundles: list[dict[str, Any]] = field(default_factory=list)
    independence: dict[str, Any] | None = None
    circuit_breaker: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature": self.feature,
            "feature_num": self.feature_num,
            "max_parallel": self.max_parallel,
            "parallel_meta": self.parallel_meta,
            "batch": self.batch,
            "worker_bundles": self.worker_bundles,
            "independence": self.independence,
            "circuit_breaker": self.circuit_breaker,
            "notes": self.notes,
            "errors": self.errors,
        }


def dispatch_build_batch(
    *,
    seed: dict[str, Any],
    blueprint: dict[str, Any] | None,
    config: dict[str, Any] | None,
    feature: dict[str, Any],
    feature_num: int,
    tree_json: str,
    completed_ids: list[str] | None,
    consecutive_fail_batches: int = 0,
    cpu_cores: int | None = None,
    memory_pct: float | None = None,
    project_root: str = ".",
) -> dict[str, Any]:
    """Compose the next build batch for one feature.

    Args:
        seed: Loaded seed dict.
        blueprint: Loaded blueprint dict (None ok).
        config: Loaded config dict (None ok).
        feature: One feature dict from `seed.features`.
        feature_num: 1-based feature index for status display.
        tree_json: Current AC tree JSON (string). Skill keeps SSOT
            and passes the latest after each `update_leaf_status`.
        completed_ids: List of leaf IDs already marked done.
        consecutive_fail_batches: From checkpoint or last iteration.
        cpu_cores / memory_pct: Test overrides only.

    Returns:
        dict — see BuildPhaseBReport. Missing/invalid tree_json sets
        `errors[]` and returns an empty batch.
    """
    report = BuildPhaseBReport()
    report.feature = str(feature.get("name", ""))
    report.feature_num = int(feature_num)

    # 1. MAX_PARALLEL.
    parallel = resolve_max_parallel(
        config or {},
        cpu_cores=cpu_cores,
        memory_pct=memory_pct,
    )
    report.max_parallel = int(parallel["max_parallel"])
    report.parallel_meta = parallel

    # 2. Batch leaves — operate on the ACNode tree directly so we can
    #    return rich leaf info (parent_id, description) for the worker
    #    bundle. Skill body still owns the per-leaf update_leaf_status
    #    via the existing MCP tool.
    completed_ids = list(completed_ids or [])
    try:
        node = ACNode.from_dict(json.loads(tree_json))
        completed_set = set(completed_ids)
        batch_nodes = _next_buildable_leaves(
            node,
            completed_set,
            max_parallel=report.max_parallel,
        )
        batch = {
            "count": len(batch_nodes),
            "max_parallel": report.max_parallel,
            "leaves": [leaf.to_dict() for leaf in batch_nodes],
        }
    except Exception as e:  # noqa: BLE001 - tree_json may be malformed
        report.errors.append(f"next_buildable_leaves failed: {e}")
        report.batch = {"count": 0, "leaves": []}
        report.circuit_breaker = {
            "consecutive_fail_batches": consecutive_fail_batches,
            "halt": False,
        }
        return report.to_dict()

    report.batch = batch

    # 3. Worker bundles for each leaf.
    leaves = batch.get("leaves") or []
    sibling_ids = [str(leaf.get("id", "")) for leaf in leaves]

    # FTS enrichment — best-effort (INV-5): missing index is non-fatal.
    feature_id = str(feature.get("id") or feature.get("name") or "")
    fts_feature_leaves: list[dict[str, Any]] = []
    if _AC_SEARCH_AVAILABLE:
        try:
            fts_feature_leaves = _fts_by_feature(project_root, feature_id)
        except Exception:  # noqa: BLE001
            pass

    for leaf in leaves:
        peers = [lid for lid in sibling_ids if lid != str(leaf.get("id", ""))]

        # BM25 cross-feature context — top-2 related leaves from other features.
        cross_feature: list[dict[str, Any]] = []
        if _AC_SEARCH_AVAILABLE:
            try:
                leaf_desc = str(leaf.get("description", ""))
                if leaf_desc:
                    raw = _fts_search(project_root, leaf_desc, limit=5)
                    cross_feature = [
                        r for r in raw if r.get("feature_id") != feature_id
                    ][:2]
            except Exception:  # noqa: BLE001
                pass

        bundle = render_worker_context(
            seed,
            blueprint or {},
            feature,
            leaf,
            sibling_leaf_ids=peers,
            fts_sibling_leaves=fts_feature_leaves,
            cross_feature_related=cross_feature,
        )
        bundle["leaf_id"] = str(leaf.get("id", ""))
        report.worker_bundles.append(bundle)

    # 4. Independence (legacy Phase B path — only if multiple features
    #    are being considered; skill body opts in by passing >1 feature
    #    via seed.features). For tree dispatch within one feature we
    #    skip — tree itself enforces dependencies.
    features_in_seed = seed.get("features") or []
    if len(features_in_seed) > 1:
        report.independence = check_feature_independence(features_in_seed)

    # 5. Circuit-breaker hint.
    halt = consecutive_fail_batches >= 2
    report.circuit_breaker = {
        "consecutive_fail_batches": consecutive_fail_batches,
        "max_retries": 2,
        "halt": halt,
    }
    if halt:
        report.notes.append(
            f"circuit breaker tripped: {consecutive_fail_batches} consecutive failed batches"
        )

    if not leaves:
        report.notes.append("no buildable leaves — feature complete or blocked")

    return report.to_dict()
