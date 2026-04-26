"""Materialize evolve proposals from file-based evolve context."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evolve_loop import read_evolve_context

EVOLVE_PROPOSAL_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evolve_proposal_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-proposal.json"


def evolve_proposal_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-proposal.md"


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
