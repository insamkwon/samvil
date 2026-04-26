"""Consolidated evolve proposal + apply pipeline.

Consolidates ``evolve_proposal`` + ``evolve_apply`` (T2.2). They were
sequentially coupled — ``materialize_evolve_apply_plan`` reads the output of
``materialize_evolve_proposal`` via ``read_evolve_proposal``. Combining them
into a single module deduplicates the file-IO helpers (``_now_iso``,
``_load_json``, ``_atomic_write_json``, ``_atomic_write_text``) and removes
the cross-module import edge while preserving every public symbol.

Public surface (signature-compatible with the pre-T2.2 layout):

* ``materialize_evolve_proposal`` (MCP tool)
* ``materialize_evolve_apply_plan`` (MCP tool)
* ``apply_evolve_apply_plan`` (MCP tool)
* ``read_evolve_proposal`` / ``read_evolve_apply_plan``
* ``evolve_proposal_summary`` / ``evolve_apply_summary``
* ``render_evolve_proposal`` / ``render_evolve_apply_plan``
* ``build_evolve_proposal`` / ``build_evolve_apply_plan`` (internal helpers
  retained for ``materialize_*`` and external scripts)
* Path helpers: ``evolve_proposal_path``, ``evolve_proposal_report_path``,
  ``evolve_apply_plan_path``, ``evolved_seed_preview_path``,
  ``evolve_apply_report_path``
* Schema constants: ``EVOLVE_PROPOSAL_SCHEMA_VERSION``,
  ``EVOLVE_APPLY_SCHEMA_VERSION``
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evolve_loop import read_evolve_context, validate_evolved_seed
from .seed_manager import compare_seeds

EVOLVE_PROPOSAL_SCHEMA_VERSION = "1.0"
EVOLVE_APPLY_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def evolve_proposal_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-proposal.json"


def evolve_proposal_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-proposal.md"


def evolve_apply_plan_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-apply-plan.json"


def evolved_seed_preview_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolved-seed.preview.json"


def evolve_apply_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-apply-report.md"


# ---------------------------------------------------------------------------
# Evolve proposal — build / materialize / read / summarize / render
# ---------------------------------------------------------------------------


def build_evolve_proposal(
    project_root: Path | str,
    evolve_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic evolve proposal without modifying project.seed.json."""
    root = Path(project_root)
    context = evolve_context if evolve_context is not None else read_evolve_context(root) or {}
    seed = context.get("current_seed") or {}
    qa = context.get("qa") or {}
    focus = context.get("focus") or {}
    routing = context.get("routing") or {}
    issue_ids = [str(item) for item in focus.get("issue_ids") or qa.get("issue_ids") or []]
    changes = _proposed_changes(seed, focus, issue_ids)
    return {
        "schema_version": EVOLVE_PROPOSAL_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "evolve_context",
        "status": "ready" if context else "missing_evolve_context",
        "seed_name": seed.get("name"),
        "from_version": seed.get("version"),
        "to_version": (int(seed.get("version") or 1) + 1) if seed else None,
        "route": {
            "next_skill": routing.get("next_skill"),
            "route_type": routing.get("route_type"),
            "reason": routing.get("reason"),
        },
        "focus": {
            "area": focus.get("area"),
            "issue_count": len(issue_ids),
            "issue_ids": issue_ids,
        },
        "qa": {
            "verdict": qa.get("verdict"),
            "reason": qa.get("reason"),
            "convergence": qa.get("convergence") or {},
        },
        "proposed_changes": changes,
        "expected_impact": _expected_impact(focus, changes),
        "next_action": "review/apply evolve proposal" if changes else "materialize evolve context first",
    }


def materialize_evolve_proposal(project_root: Path | str) -> dict[str, Any]:
    proposal = build_evolve_proposal(project_root)
    json_path = _atomic_write_json(evolve_proposal_path(project_root), proposal)
    report_path = _atomic_write_text(evolve_proposal_report_path(project_root), render_evolve_proposal(proposal))
    return {
        "schema_version": EVOLVE_PROPOSAL_SCHEMA_VERSION,
        "status": proposal["status"],
        "project_root": str(Path(project_root)),
        "evolve_proposal_path": str(json_path),
        "evolve_proposal_report_path": str(report_path),
        "changes": len(proposal.get("proposed_changes") or []),
        "next_action": proposal.get("next_action"),
    }


def read_evolve_proposal(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(evolve_proposal_path(project_root))
    return data or None


def evolve_proposal_summary(project_root: Path | str) -> dict[str, Any]:
    proposal = read_evolve_proposal(project_root) or {}
    return {
        "present": bool(proposal),
        "status": proposal.get("status"),
        "seed_name": proposal.get("seed_name"),
        "from_version": proposal.get("from_version"),
        "to_version": proposal.get("to_version"),
        "focus_area": ((proposal.get("focus") or {}).get("area")),
        "changes": len(proposal.get("proposed_changes") or []),
        "next_action": proposal.get("next_action"),
        "path": str(evolve_proposal_path(project_root)) if proposal else "",
        "report_path": str(evolve_proposal_report_path(project_root)) if evolve_proposal_report_path(project_root).exists() else "",
    }


def render_evolve_proposal(proposal: dict[str, Any]) -> str:
    lines = [
        "# Evolve Proposal",
        "",
        f"- Status: {proposal.get('status') or '?'}",
        f"- Seed: {proposal.get('seed_name') or '?'} v{proposal.get('from_version') or '?'} -> v{proposal.get('to_version') or '?'}",
        f"- Focus: {((proposal.get('focus') or {}).get('area')) or '?'}",
        f"- Issues: {((proposal.get('focus') or {}).get('issue_count')) or 0}",
        f"- Next action: {proposal.get('next_action') or '?'}",
        "",
        "## Proposed Changes",
    ]
    changes = proposal.get("proposed_changes") or []
    if not changes:
        lines.append("- (none)")
    for change in changes:
        lines.append(f"- {change.get('type')}: {change.get('target')} - {change.get('instruction')}")
    lines.extend(["", "## Expected Impact"])
    for item in proposal.get("expected_impact") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _proposed_changes(seed: dict[str, Any], focus: dict[str, Any], issue_ids: list[str]) -> list[dict[str, Any]]:
    area = str(focus.get("area") or "")
    if area == "functional_spec":
        return [_functional_change(seed, issue_id) for issue_id in issue_ids if issue_id.startswith("pass2:")]
    if area == "mechanical_repair":
        return [_change("repair_build", "project", "fix mechanical build/smoke blockers before evolving the seed")]
    if area == "process_contract":
        return [_change("tighten_contract", "samvil-qa", "record ownership violation and strengthen independent QA write rules")]
    if area == "quality_repair":
        return [_change("clarify_quality_ac", "acceptance_criteria", "make UX/accessibility quality expectations testable")]
    return [_change("review_seed", seed.get("name") or "project.seed.json", "review blocked QA evidence before applying changes")]


def _functional_change(seed: dict[str, Any], issue_id: str) -> dict[str, Any]:
    ac_id = issue_id.split(":", 2)[1] if ":" in issue_id else "acceptance_criteria"
    return _change(
        "clarify_or_split_ac",
        ac_id,
        "split or clarify blocked functional acceptance criterion; remove stubs and make runtime evidence explicit",
        evidence=[issue_id],
    )


def _change(change_type: str, target: str, instruction: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": change_type,
        "target": target,
        "instruction": instruction,
        "evidence": evidence or [],
        "apply_mode": "proposal_only",
    }


def _expected_impact(focus: dict[str, Any], changes: list[dict[str, Any]]) -> list[str]:
    if not changes:
        return ["No proposal generated until evolve context is available."]
    area = str(focus.get("area") or "")
    if area == "functional_spec":
        return [
            "blocked functional QA should become buildable acceptance criteria",
            "next build can target concrete runtime evidence instead of repeating the same stub fix",
        ]
    if area == "quality_repair":
        return ["quality findings become explicit repair criteria before QA rerun"]
    return ["next run has a concrete recovery target instead of a generic blocked state"]


# ---------------------------------------------------------------------------
# Evolve apply — build / materialize / apply / read / summarize / render
# ---------------------------------------------------------------------------


def build_evolve_apply_plan(
    project_root: Path | str,
    proposal: dict[str, Any] | None = None,
    seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic seed patch plan without modifying project.seed.json."""
    root = Path(project_root)
    current_seed = copy.deepcopy(seed if seed is not None else _load_json(root / "project.seed.json"))
    current_proposal = proposal if proposal is not None else read_evolve_proposal(root) or {}
    operations: list[dict[str, Any]] = []
    evolved_seed = copy.deepcopy(current_seed)

    if current_seed and current_proposal.get("status") == "ready":
        for change in current_proposal.get("proposed_changes") or []:
            operations.append(_apply_change_preview(evolved_seed, change))
        if _has_mutation(operations):
            evolved_seed["version"] = current_proposal.get("to_version") or int(current_seed.get("version") or 1) + 1

    validation = validate_evolved_seed(current_seed, evolved_seed) if current_seed and evolved_seed else {
        "valid": False,
        "issues": ["project.seed.json missing"],
    }
    comparison = compare_seeds(current_seed, evolved_seed) if current_seed and evolved_seed else {}
    status = _plan_status(current_seed, current_proposal, operations, validation)

    return {
        "schema_version": EVOLVE_APPLY_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "evolve_proposal",
        "status": status,
        "seed_name": current_seed.get("name"),
        "from_version": current_seed.get("version"),
        "to_version": evolved_seed.get("version") if evolved_seed else None,
        "proposal_status": current_proposal.get("status"),
        "proposal_changes": len(current_proposal.get("proposed_changes") or []),
        "original_seed_sha256": _stable_hash(current_seed) if current_seed else "",
        "evolved_seed_sha256": _stable_hash(evolved_seed) if evolved_seed else "",
        "operations": operations,
        "validation": validation,
        "comparison": comparison,
        "evolved_seed": evolved_seed,
        "next_action": _next_action(status),
    }


def materialize_evolve_apply_plan(project_root: Path | str) -> dict[str, Any]:
    plan = build_evolve_apply_plan(project_root)
    plan_path = _atomic_write_json(evolve_apply_plan_path(project_root), plan)
    preview_path = _atomic_write_json(evolved_seed_preview_path(project_root), plan.get("evolved_seed") or {})
    report_path = _atomic_write_text(evolve_apply_report_path(project_root), render_evolve_apply_plan(plan))
    return {
        "schema_version": EVOLVE_APPLY_SCHEMA_VERSION,
        "status": plan["status"],
        "project_root": str(Path(project_root)),
        "evolve_apply_plan_path": str(plan_path),
        "evolved_seed_preview_path": str(preview_path),
        "evolve_apply_report_path": str(report_path),
        "operations": len(plan.get("operations") or []),
        "mutations": _mutation_count(plan.get("operations") or []),
        "next_action": plan.get("next_action"),
    }


def apply_evolve_apply_plan(project_root: Path | str) -> dict[str, Any]:
    """Apply a ready evolve plan after verifying the current seed hash."""
    root = Path(project_root)
    plan = read_evolve_apply_plan(root) or build_evolve_apply_plan(root)
    if plan.get("status") != "ready":
        return {
            "schema_version": EVOLVE_APPLY_SCHEMA_VERSION,
            "status": "blocked",
            "reason": f"apply plan is not ready: {plan.get('status')}",
            "next_action": plan.get("next_action") or "fix evolve apply plan",
        }

    seed_path = root / "project.seed.json"
    current_seed = _load_json(seed_path)
    current_hash = _stable_hash(current_seed) if current_seed else ""
    if current_hash != plan.get("original_seed_sha256"):
        return {
            "schema_version": EVOLVE_APPLY_SCHEMA_VERSION,
            "status": "blocked",
            "reason": "project.seed.json changed after apply plan was built",
            "next_action": "rebuild evolve apply plan",
        }

    backup_path = root / "seed_history" / f"v{plan.get('from_version')}.json"
    diff_path = root / "seed_history" / f"v{plan.get('from_version')}_v{plan.get('to_version')}_diff.md"
    evolved_seed = plan.get("evolved_seed") or {}
    _atomic_write_json(backup_path, current_seed)
    _atomic_write_json(seed_path, evolved_seed)
    _atomic_write_text(diff_path, _render_seed_diff(plan))
    plan["status"] = "applied"
    plan["applied_at"] = _now_iso()
    plan["backup_path"] = str(backup_path)
    plan["diff_path"] = str(diff_path)
    plan["next_action"] = "rerun build and QA with evolved seed"
    _atomic_write_json(evolve_apply_plan_path(root), plan)
    _atomic_write_json(evolved_seed_preview_path(root), evolved_seed)
    _atomic_write_text(evolve_apply_report_path(root), render_evolve_apply_plan(plan))
    return {
        "schema_version": EVOLVE_APPLY_SCHEMA_VERSION,
        "status": "applied",
        "project_root": str(root),
        "from_version": plan.get("from_version"),
        "to_version": plan.get("to_version"),
        "backup_path": str(backup_path),
        "diff_path": str(diff_path),
        "next_action": plan.get("next_action"),
    }


def read_evolve_apply_plan(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(evolve_apply_plan_path(project_root))
    return data or None


def evolve_apply_summary(project_root: Path | str) -> dict[str, Any]:
    plan = read_evolve_apply_plan(project_root) or {}
    operations = plan.get("operations") or []
    return {
        "present": bool(plan),
        "status": plan.get("status"),
        "seed_name": plan.get("seed_name"),
        "from_version": plan.get("from_version"),
        "to_version": plan.get("to_version"),
        "operations": len(operations),
        "mutations": _mutation_count(operations),
        "next_action": plan.get("next_action"),
        "path": str(evolve_apply_plan_path(project_root)) if plan else "",
        "preview_path": str(evolved_seed_preview_path(project_root)) if evolved_seed_preview_path(project_root).exists() else "",
        "report_path": str(evolve_apply_report_path(project_root)) if evolve_apply_report_path(project_root).exists() else "",
    }


def render_evolve_apply_plan(plan: dict[str, Any]) -> str:
    lines = [
        "# Evolve Apply Plan",
        "",
        f"- Status: {plan.get('status') or '?'}",
        f"- Seed: {plan.get('seed_name') or '?'} v{plan.get('from_version') or '?'} -> v{plan.get('to_version') or '?'}",
        f"- Operations: {len(plan.get('operations') or [])}",
        f"- Mutations: {_mutation_count(plan.get('operations') or [])}",
        f"- Next action: {plan.get('next_action') or '?'}",
        "",
        "## Operations",
    ]
    operations = plan.get("operations") or []
    if not operations:
        lines.append("- (none)")
    for operation in operations:
        lines.append(
            f"- {operation.get('status')}: {operation.get('type')} "
            f"{operation.get('target')} - {operation.get('summary')}"
        )
    lines.extend(["", "## Validation"])
    validation = plan.get("validation") or {}
    lines.append(f"- Valid: {validation.get('valid')}")
    for issue in validation.get("issues") or []:
        lines.append(f"- Issue: {issue}")
    return "\n".join(lines) + "\n"


def _apply_change_preview(seed: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    change_type = str(change.get("type") or "")
    target = str(change.get("target") or "")
    if change_type == "clarify_or_split_ac":
        node = _find_ac_node(seed, target)
        if not node:
            return _operation(change_type, target, "blocked", "target AC was not found")
        description = str(node.get("description") or target)
        children = node.setdefault("children", [])
        if children:
            node["description"] = _clarified_description(description)
            return _operation(change_type, target, "mutated", "clarified existing AC branch description")
        node["children"] = [
            _leaf(f"{target}.1", f"{description} uses real runtime behavior, not stubs or placeholders"),
            _leaf(f"{target}.2", f"Runtime evidence proves this criterion through visible user behavior"),
        ]
        node["status"] = "pending"
        node["evidence"] = []
        return _operation(change_type, target, "mutated", "split blocked AC into runtime and evidence leaves")
    if change_type == "clarify_quality_ac":
        feature = _first_feature(seed)
        if not feature:
            return _operation(change_type, target, "blocked", "seed has no feature to attach quality AC")
        criteria = feature.setdefault("acceptance_criteria", [])
        criteria.append(_leaf(_next_ac_id(criteria, "AC-Q"), "UX and accessibility expectations are testable in browser QA"))
        return _operation(change_type, target, "mutated", "added testable quality acceptance criterion")
    return _operation(change_type, target, "manual_only", "proposal requires manual implementation outside seed patch")


def _plan_status(
    seed: dict[str, Any],
    proposal: dict[str, Any],
    operations: list[dict[str, Any]],
    validation: dict[str, Any],
) -> str:
    if not seed:
        return "missing_seed"
    if not proposal:
        return "missing_evolve_proposal"
    if proposal.get("status") != "ready":
        return "proposal_not_ready"
    if any(item.get("status") == "blocked" for item in operations):
        return "blocked"
    if not _has_mutation(operations):
        return "manual_only"
    if not validation.get("valid"):
        return "blocked"
    return "ready"


def _next_action(status: str) -> str:
    if status == "ready":
        return "review evolved seed preview, then apply evolve plan"
    if status == "manual_only":
        return "handle manual evolve proposal before applying seed"
    if status == "missing_evolve_proposal":
        return "materialize evolve proposal first"
    if status == "missing_seed":
        return "create project.seed.json first"
    return "fix evolve apply blockers"


def _find_ac_node(seed: dict[str, Any], target: str) -> dict[str, Any] | None:
    for feature in seed.get("features") or []:
        for node in feature.get("acceptance_criteria") or []:
            found = _walk_ac_node(node, target)
            if found:
                return found
    return None


def _walk_ac_node(node: Any, target: str) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    if str(node.get("id") or "") == target:
        return node
    for child in node.get("children") or []:
        found = _walk_ac_node(child, target)
        if found:
            return found
    return None


def _first_feature(seed: dict[str, Any]) -> dict[str, Any] | None:
    features = seed.get("features") or []
    return features[0] if features and isinstance(features[0], dict) else None


def _leaf(node_id: str, description: str) -> dict[str, Any]:
    return {"id": node_id, "description": description, "children": [], "status": "pending", "evidence": []}


def _next_ac_id(criteria: list[Any], prefix: str) -> str:
    return f"{prefix}-{len(criteria) + 1}"


def _clarified_description(description: str) -> str:
    suffix = " with explicit runtime evidence"
    return description if description.endswith(suffix) else description + suffix


def _operation(change_type: str, target: str, status: str, summary: str) -> dict[str, Any]:
    return {"type": change_type, "target": target, "status": status, "summary": summary}


def _has_mutation(operations: list[dict[str, Any]]) -> bool:
    return any(item.get("status") == "mutated" for item in operations)


def _mutation_count(operations: list[dict[str, Any]]) -> int:
    return sum(1 for item in operations if item.get("status") == "mutated")


def _render_seed_diff(plan: dict[str, Any]) -> str:
    comparison = plan.get("comparison") or {}
    lines = [
        f"## v{plan.get('from_version')} -> v{plan.get('to_version')}",
        "",
        f"Similarity: {comparison.get('similarity')}",
        "",
        "### Operations",
    ]
    for operation in plan.get("operations") or []:
        lines.append(f"- {operation.get('status')}: {operation.get('type')} {operation.get('target')}")
    return "\n".join(lines) + "\n"


def _stable_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Shared file IO helpers (deduplicated from the two source modules)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    return _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path
