"""Evolve loop engine for SAMVIL — seed improvement through evaluation feedback.

Pipeline:
  1. Wonder: "What was lacking?" (analyze QA results)
  2. Reflect: "How to improve?" (propose seed changes)
  3. New seed version with improvements
  4. Check convergence → stop or continue
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .seed_manager import check_convergence, compare_seeds

EVOLVE_CONTEXT_SCHEMA_VERSION = "1.0"


def generate_evolve_context(
    current_seed: dict,
    qa_result: dict,
    seed_history: list[dict] | None = None,
) -> dict:
    """Generate context for wonder/reflect agents.

    Args:
        current_seed: Current seed JSON
        qa_result: QA report with verdicts per AC
        seed_history: Previous seed versions for convergence context

    Returns:
        Context dict for agent prompts.
    """
    context = {
        "current_seed": current_seed,
        "qa_result": qa_result,
        "version": current_seed.get("version", 1),
    }

    if seed_history and len(seed_history) >= 2:
        convergence = check_convergence(seed_history)
        context["convergence"] = convergence
        context["previous_changes"] = compare_seeds(
            seed_history[-2], seed_history[-1]
        )["changes"]

    return context


def evolve_context_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-context.json"


def build_evolve_context_from_project(project_root: Path | str) -> dict[str, Any]:
    """Build a file-based evolve intake context from SAMVIL project artifacts."""
    root = Path(project_root)
    seed = _load_json(root / "project.seed.json")
    state = _load_json(root / "project.state.json") or _load_json(root / ".samvil" / "state.json")
    qa_results = _load_json(root / ".samvil" / "qa-results.json")
    qa_routing = _load_json(root / ".samvil" / "qa-routing.json")
    seed_history = _load_seed_history(root, seed)
    synthesis = qa_results.get("synthesis") or {}
    convergence = qa_results.get("convergence") or synthesis.get("convergence") or {}
    primary_route = qa_routing.get("primary_route") or {}
    context = generate_evolve_context(seed, qa_results or synthesis, seed_history)
    context.update({
        "schema_version": EVOLVE_CONTEXT_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "project_artifacts",
        "state": {
            "session_id": state.get("session_id"),
            "current_stage": state.get("current_stage") or state.get("stage"),
            "samvil_tier": state.get("samvil_tier") or state.get("selected_tier"),
            "qa_history_count": len(state.get("qa_history") or []),
        },
        "qa": {
            "verdict": synthesis.get("verdict"),
            "reason": synthesis.get("reason"),
            "next_action": synthesis.get("next_action"),
            "issue_ids": synthesis.get("issue_ids") or convergence.get("issue_ids") or [],
            "convergence": convergence,
            "pass2_counts": ((synthesis.get("pass2") or {}).get("counts") or {}),
            "pass3_verdict": ((synthesis.get("pass3") or {}).get("verdict")),
        },
        "routing": {
            "present": bool(qa_routing),
            "next_skill": primary_route.get("next_skill"),
            "route_type": primary_route.get("route_type"),
            "reason": primary_route.get("reason"),
            "next_action": qa_routing.get("next_action") or primary_route.get("next_action"),
            "alternatives": qa_routing.get("alternative_routes") or [],
        },
        "ground_truth": _ground_truth_summary(root),
        "seed_history": {
            "count": len(seed_history),
            "versions": [item.get("version") for item in seed_history],
        },
        "focus": _evolve_focus(synthesis, convergence, primary_route),
    })
    return context


def materialize_evolve_context(project_root: Path | str) -> dict[str, Any]:
    """Persist file-based evolve context into .samvil/evolve-context.json."""
    context = build_evolve_context_from_project(project_root)
    path = _atomic_write_json(evolve_context_path(project_root), context)
    return {
        "schema_version": EVOLVE_CONTEXT_SCHEMA_VERSION,
        "status": "ok",
        "project_root": str(Path(project_root)),
        "evolve_context_path": str(path),
        "next_skill": ((context.get("routing") or {}).get("next_skill")),
        "focus": context.get("focus") or {},
    }


def read_evolve_context(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(evolve_context_path(project_root))
    return data or None


def evolve_context_summary(project_root: Path | str) -> dict[str, Any]:
    context = read_evolve_context(project_root) or {}
    routing = context.get("routing") or {}
    focus = context.get("focus") or {}
    return {
        "present": bool(context),
        "next_skill": routing.get("next_skill"),
        "route_type": routing.get("route_type"),
        "focus_area": focus.get("area"),
        "issue_count": focus.get("issue_count", 0),
        "path": str(evolve_context_path(project_root)) if context else "",
    }


def validate_evolved_seed(original: dict, evolved: dict) -> dict:
    """Validate that an evolved seed is a valid improvement.

    Rules:
    - Must keep same name and mode
    - Must not add more than 2 new features per evolution
    - Must not remove core_experience
    - Version must increment by 1

    Returns:
        Validation result with issues list.
    """
    issues = []

    # Name and mode must be preserved
    if evolved.get("name") != original.get("name"):
        issues.append("name changed — must be preserved")
    if evolved.get("mode") != original.get("mode"):
        issues.append("mode changed — must be preserved")

    # v3.0.0+: schema_version must be preserved (downgrading to v2 silently
    # would route the next build through the wrong validation path).
    orig_sv = original.get("schema_version")
    new_sv = evolved.get("schema_version")
    if orig_sv and orig_sv != new_sv:
        issues.append(
            f"schema_version changed ({orig_sv!r} → {new_sv!r}) — must be preserved"
        )

    # Core experience must exist
    if not evolved.get("core_experience"):
        issues.append("core_experience removed — must be preserved")

    # Version must increment
    orig_version = original.get("version", 1)
    new_version = evolved.get("version", 1)
    if new_version != orig_version + 1:
        issues.append(f"version should be {orig_version + 1}, got {new_version}")

    # Feature count check (max 2 new features per evolution)
    orig_features = {f["name"] if isinstance(f, dict) else f for f in original.get("features", [])}
    new_features = {f["name"] if isinstance(f, dict) else f for f in evolved.get("features", [])}
    added = new_features - orig_features
    if len(added) > 2:
        issues.append(f"Too many new features ({len(added)}). Max 2 per evolution.")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "features_added": list(added),
        "features_removed": list(orig_features - new_features),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evolve_focus(synthesis: dict[str, Any], convergence: dict[str, Any], primary_route: dict[str, Any]) -> dict[str, Any]:
    issue_ids = synthesis.get("issue_ids") or convergence.get("issue_ids") or []
    families = _issue_families([str(item) for item in issue_ids])
    area = "functional_spec" if families.get("pass2") else "quality_repair"
    if families.get("pass1"):
        area = "mechanical_repair"
    if families.get("ownership"):
        area = "process_contract"
    return {
        "area": area,
        "issue_count": len(issue_ids),
        "issue_ids": issue_ids,
        "route_type": primary_route.get("route_type"),
        "instructions": _focus_instructions(area),
    }


def _focus_instructions(area: str) -> list[str]:
    if area == "functional_spec":
        return [
            "inspect blocked Pass 2 acceptance criteria",
            "split, clarify, or descope impossible criteria before rebuilding",
            "preserve core_experience and schema_version",
        ]
    if area == "mechanical_repair":
        return ["fix build/smoke blockers before seed evolution"]
    if area == "process_contract":
        return ["record retro finding and tighten independent QA ownership"]
    return ["apply targeted quality repair or clarify UX acceptance criteria"]


def _issue_families(issue_ids: list[str]) -> dict[str, int]:
    counts = {"pass1": 0, "pass2": 0, "pass3": 0, "ownership": 0, "other": 0}
    for issue_id in issue_ids:
        family = issue_id.split(":", 1)[0]
        counts[family if family in counts else "other"] += 1
    return counts


def _ground_truth_summary(root: Path) -> dict[str, Any]:
    samvil = root / ".samvil"
    paths = {
        "qa_report": samvil / "qa-report.md",
        "qa_results": samvil / "qa-results.json",
        "qa_routing": samvil / "qa-routing.json",
        "events": samvil / "events.jsonl",
        "build_log": samvil / "build.log",
        "fix_log": samvil / "fix-log.md",
    }
    return {
        name: {"present": path.exists(), "path": str(path)}
        for name, path in paths.items()
    }


def _load_seed_history(root: Path, current_seed: dict[str, Any]) -> list[dict[str, Any]]:
    history_dir = root / "seed_history"
    history: list[dict[str, Any]] = []
    if history_dir.exists():
        for path in sorted(history_dir.glob("v*.json")):
            data = _load_json(path)
            if data:
                history.append(data)
    if current_seed and all(seed.get("version") != current_seed.get("version") for seed in history):
        history.append(current_seed)
    return history


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
