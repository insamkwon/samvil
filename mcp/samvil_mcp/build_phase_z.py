"""Post-stage finalize aggregator for samvil-build (T4.8 ultra-thin).

Runs ONCE at the end of the build stage, before the chain into
`samvil-qa`. Owns the v3.2 Contract Layer post_stage work that the
SKILL body would otherwise scatter across 4-6 inline MCP calls:

  1. **claim_post inputs (per leaf)** — for every leaf with status
     `pass`, prepare the `ac_verdict` claim payload (subject =
     leaf.id, evidence = leaf.evidence). Skill body still calls
     `claim_post` itself (one per leaf, file-mutating) but no longer
     hand-rolls the JSON shape.
  2. **stage_claim verify input** — surface the
     `state.json.stage_claims.build` claim ID so the skill body can
     hand it directly to `claim_verify(verified_by="agent:user")`.
  3. **gate_check input** — compute `implementation_rate` =
     `passed_leaves / total_leaves` across all features and the
     other metrics required for the `build_to_qa` gate, plus the
     resolved `samvil_tier` from state.json.
  4. **stagnation hint** — surface previous attempt count from the
     events log so the skill knows whether to call
     `stagnation_evaluate` (only on retry attempts).
  5. **handoff body** — pre-rendered handoff.md block for the build
     stage so the skill body can `cat >>` it without composing
     prose itself.

What stays in the skill body (CC-bound, P8):
  - The actual `claim_post` calls (state-mutating; one per leaf).
  - `claim_verify` for stage_claim (state-mutating).
  - `gate_check` MCP call (state-mutating; result determines chain).
  - `stagnation_evaluate` MCP call (state-mutating).
  - Writing to `.samvil/handoff.md` (CC tool — Bash `cat >>` or Edit).
  - Chain into `samvil-qa`.

All reads are best-effort. Missing files yield empty defaults and a
non-fatal entry in `errors[]`. Never raises. Honors INV-1 / INV-5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ac_tree import ACNode, leaves as _ac_leaves, tree_progress as _tree_progress

BUILD_PHASE_Z_SCHEMA_VERSION = "1.0"


# ── Helpers ───────────────────────────────────────────────────────────


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    """Best-effort JSON read. Returns None on missing/invalid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _count_retry_attempts(events_path: Path, *, stage: str = "build") -> int:
    """Count `build_fail` events at integration scope to detect retry attempts.

    Returns:
        0 on first attempt; ≥1 means previous build attempts have been
        recorded for this session.
    """
    if not events_path.exists():
        return 0
    count = 0
    try:
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("stage") != stage:
                continue
            etype = evt.get("event_type", "")
            if etype == "build_fail":
                data = evt.get("data") or {}
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        data = {}
                scope = str(data.get("scope") or "")
                if scope.startswith("integration") or scope == "integration":
                    count += 1
    except OSError:
        return 0
    return count


def _all_leaves_from_features(
    features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Walk every feature's AC tree and return (leaves, leaves_by_feature).

    Each returned leaf dict carries `id`, `description`, `status`,
    `evidence`, `feature` (added). Used for the claim payload prep
    and the implementation-rate calculation.
    """
    flat: list[dict[str, Any]] = []
    by_feature: dict[str, list[str]] = {}
    for feature in features or []:
        feat_name = str(feature.get("name", ""))
        ac_data = feature.get("acceptance_criteria")
        if not ac_data:
            continue
        # Tree node or list — handle both. v3 seeds use single-root node;
        # v2 migrations may pass a list of leaves.
        if isinstance(ac_data, dict):
            try:
                root = ACNode.from_dict(ac_data)
            except Exception:  # noqa: BLE001
                continue
            roots = [root]
        elif isinstance(ac_data, list):
            roots = []
            for item in ac_data:
                try:
                    if isinstance(item, dict):
                        roots.append(ACNode.from_dict(item))
                    elif isinstance(item, str):
                        roots.append(ACNode(id="", description=item, children=[]))
                except Exception:  # noqa: BLE001
                    continue
        else:
            continue
        leaf_ids: list[str] = []
        for root_node in roots:
            for leaf_node in _ac_leaves(root_node):
                leaf_dict = leaf_node.to_dict()
                leaf_dict["feature"] = feat_name
                flat.append(leaf_dict)
                leaf_ids.append(str(leaf_node.id))
        by_feature[feat_name] = leaf_ids
    return flat, by_feature


def build_ac_verdict_claims(
    leaves: list[dict[str, Any]],
    *,
    claimed_by: str = "agent:build-worker",
) -> list[dict[str, Any]]:
    """Build the `ac_verdict` claim payloads — one per `pass` leaf.

    The skill body iterates this list and posts each via
    `mcp__samvil_mcp__claim_post`. Returning the prepared payload
    (instead of posting here) keeps INV-1: the SSOT write happens in
    the skill body, not deep inside an aggregator.
    """
    payloads: list[dict[str, Any]] = []
    for leaf in leaves:
        if str(leaf.get("status", "")) != "pass":
            continue
        evidence = leaf.get("evidence") or []
        payloads.append({
            "claim_type": "ac_verdict",
            "subject": str(leaf.get("id", "")),
            "statement": "build-worker asserts leaf implemented",
            "authority_file": "qa-results.json",
            "claimed_by": claimed_by,
            "evidence": list(evidence),
            "feature": str(leaf.get("feature", "")),
        })
    return payloads


def render_handoff_block(
    *,
    completed_features: list[str],
    failed_features: list[str],
    retries: int,
    total_leaves: int,
    passed_leaves: int,
    failed_leaves: int,
    feature_count: int,
    rate_budget_stats: dict[str, Any] | None,
) -> str:
    """Pre-rendered build-stage handoff block.

    The skill body appends this verbatim via `cat >>` or Edit (per
    INV-3 / handoff pattern). No newline normalization here —
    callers decide on the trailing newline.
    """
    lines = ["", "## Build Stage", ""]
    lines.append(
        f"- Completed: {', '.join(completed_features) if completed_features else '없음'}"
    )
    lines.append(
        f"- Failed: {', '.join(failed_features) if failed_features else '없음'}"
    )
    lines.append(f"- Retries: {retries}")
    lines.append(
        f"- Tree progress: {total_leaves} total / {passed_leaves} passed "
        f"/ {failed_leaves} failed across {feature_count} feature(s)"
    )
    if rate_budget_stats:
        peak = rate_budget_stats.get("peak", 0)
        total_acquired = rate_budget_stats.get("total_acquired", 0)
        stale = rate_budget_stats.get("stale_recovery", 0)
        lines.append(
            f"- Rate budget: peak={peak}, total_acquired={total_acquired}, "
            f"stale_recovery={stale}"
        )
    return "\n".join(lines)


# ── Aggregator ────────────────────────────────────────────────────────


@dataclass
class BuildPhaseZReport:
    schema_version: str = BUILD_PHASE_Z_SCHEMA_VERSION
    project_path: str = ""
    session_id: str = ""
    samvil_tier: str = "standard"
    metrics: dict[str, Any] = field(default_factory=dict)
    ac_verdict_claims: list[dict[str, Any]] = field(default_factory=list)
    stage_claim_id: str = ""
    gate_input: dict[str, Any] = field(default_factory=dict)
    stagnation_hint: dict[str, Any] = field(default_factory=dict)
    handoff_block: str = ""
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_path": self.project_path,
            "session_id": self.session_id,
            "samvil_tier": self.samvil_tier,
            "metrics": self.metrics,
            "ac_verdict_claims": self.ac_verdict_claims,
            "stage_claim_id": self.stage_claim_id,
            "gate_input": self.gate_input,
            "stagnation_hint": self.stagnation_hint,
            "handoff_block": self.handoff_block,
            "notes": self.notes,
            "errors": self.errors,
        }


def finalize_build_phase_z(
    project_path: str | Path,
    *,
    rate_budget_stats: dict[str, Any] | None = None,
    failed_features: list[str] | None = None,
    retries: int = 0,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-build skill needs at Phase Z.

    Args:
        project_path: Project root containing seed/state/events.
        rate_budget_stats: Optional pre-fetched
            `mcp__samvil_mcp__rate_budget_stats(...)` result. Skill
            body passes it in to avoid a second MCP roundtrip; we
            only render it into the handoff block.
        failed_features: List of feature names that hit the circuit
            breaker. Defaults to empty.
        retries: Total retry attempts in this build stage (for the
            handoff block). Caller-supplied to avoid re-walking the
            event log twice.

    Returns:
        JSON-serializable dict — see BuildPhaseZReport fields.
    """
    report = BuildPhaseZReport()
    root = Path(str(project_path)).expanduser()
    report.project_path = str(root)

    # Load seed + state.
    seed = _read_json_safe(root / "project.seed.json") or {}
    state = _read_json_safe(root / "project.state.json") or {}
    if not seed:
        report.errors.append("project.seed.json missing or invalid")
    if not state:
        report.errors.append("project.state.json missing or invalid")

    report.session_id = str(state.get("session_id", ""))

    # Resolve samvil_tier (state > config > default).
    config = _read_json_safe(root / "project.config.json") or {}
    tier = (
        state.get("samvil_tier")
        or state.get("selected_tier")
        or config.get("samvil_tier")
        or config.get("selected_tier")
        or "standard"
    )
    report.samvil_tier = str(tier)

    # Stage-claim ID (recorded at Phase A).
    stage_claims = state.get("stage_claims") or {}
    report.stage_claim_id = str(stage_claims.get("build", ""))

    # Walk all features → leaves.
    features = seed.get("features") or []
    flat_leaves, by_feature = _all_leaves_from_features(features)
    total = len(flat_leaves)
    passed = sum(1 for l in flat_leaves if str(l.get("status", "")) == "pass")
    failed = sum(1 for l in flat_leaves if str(l.get("status", "")) == "fail")
    pending = total - passed - failed
    implementation_rate = round(passed / total, 4) if total > 0 else 0.0

    completed_features = [
        name for name, ids in by_feature.items()
        if ids and all(
            any(
                l for l in flat_leaves
                if str(l.get("id")) == lid and str(l.get("status")) == "pass"
            )
            for lid in ids
        )
    ]
    failed_features = list(failed_features or [])
    if not failed_features:
        # Derive failed features from leaf statuses.
        for name, ids in by_feature.items():
            if any(
                str(l.get("status")) == "fail"
                for l in flat_leaves
                if str(l.get("id")) in ids
            ):
                failed_features.append(name)

    report.metrics = {
        "features_total": len(features),
        "features_passed": len(completed_features),
        "features_failed": len(failed_features),
        "implementation_rate": implementation_rate,
        "total_leaves": total,
        "passed_leaves": passed,
        "failed_leaves": failed,
        "pending_leaves": pending,
    }

    # AC verdict claim payloads.
    report.ac_verdict_claims = build_ac_verdict_claims(flat_leaves)

    # Gate input (build_to_qa gate).
    report.gate_input = {
        "gate_name": "build_to_qa",
        "samvil_tier": report.samvil_tier,
        "metrics": {"implementation_rate": implementation_rate},
    }

    # Stagnation hint — only run stagnation_evaluate if there were
    # prior integration build_fail events (this is a retry attempt).
    events_path = root / ".samvil" / "events.jsonl"
    prior_failures = _count_retry_attempts(events_path, stage="build")
    report.stagnation_hint = {
        "should_evaluate": prior_failures >= 2,
        "prior_integration_failures": prior_failures,
    }

    # Handoff block.
    report.handoff_block = render_handoff_block(
        completed_features=completed_features,
        failed_features=failed_features,
        retries=retries,
        total_leaves=total,
        passed_leaves=passed,
        failed_leaves=failed,
        feature_count=len(features),
        rate_budget_stats=rate_budget_stats,
    )

    # Notes.
    if total == 0:
        report.notes.append("no AC leaves found — feature seed may be empty")
    if implementation_rate < 0.85 and total > 0:
        report.notes.append(
            f"implementation_rate {implementation_rate} below typical 0.85 — gate may block"
        )
    if not report.stage_claim_id:
        report.notes.append("stage_claim_id missing — claim_verify will be skipped")

    return report.to_dict()
