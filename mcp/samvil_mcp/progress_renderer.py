"""Progress Renderer — ASCII Double Diamond visualization (v2.5.0, Ouroboros #15).

Renders SAMVIL pipeline progress as a Double Diamond diagram.
Updates `.samvil/progress.md` file for user to cat anytime.

Double Diamond mapping:
  Discover → Interview (explore)
  Define   → Seed (converge)
  Develop  → Build + QA (explore + test)
  Deliver  → Evolve → Deploy (converge + ship)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


Status = Literal["pending", "in_progress", "done", "skipped", "failed"]


STAGE_TO_DIAMOND = {
    "interview": "Discover",
    "seed": "Define",
    "council": "Define",
    "design": "Define",
    "scaffold": "Develop",
    "build": "Develop",
    "qa": "Develop",
    "deploy": "Deliver",
    "evolve": "Deliver",
    "retro": "Deliver",
    "complete": "Deliver",
}


STATUS_ICON = {
    "pending": "⏸",
    "in_progress": "⟳",
    "done": "✓",
    "skipped": "⏭",
    "failed": "✗",
}


def render_double_diamond(stage_statuses: dict[str, Status]) -> str:
    """Render ASCII Double Diamond diagram from stage statuses.

    Args:
        stage_statuses: {stage_name: status}

    Returns:
        ASCII art string.
    """
    # Aggregate per diamond phase
    diamonds = {"Discover": [], "Define": [], "Develop": [], "Deliver": []}
    for stage, status in stage_statuses.items():
        phase = STAGE_TO_DIAMOND.get(stage, "Deliver")
        diamonds[phase].append((stage, status))

    def phase_status(stages: list[tuple[str, Status]]) -> str:
        if not stages:
            return "pending"
        if any(s == "failed" for _, s in stages):
            return "failed"
        if all(s in ("done", "skipped") for _, s in stages):
            return "done"
        if any(s == "in_progress" for _, s in stages):
            return "in_progress"
        return "pending"

    phases = [(p, phase_status(stages), stages) for p, stages in diamonds.items()]

    # Render
    lines = [
        "  Discover        Define         Develop         Deliver",
        "    " + "  ".join(
            "◆" if ps in ("done", "skipped") else ("◇" if ps == "in_progress" else "○")
            + "────────────"
            for _, ps, _ in phases[:-1]
        ) + ("◆" if phases[-1][1] == "done" else ("◇" if phases[-1][1] == "in_progress" else "○")),
        "",
    ]

    # Status row
    status_labels = []
    for name, ps, _ in phases:
        if ps == "done":
            status_labels.append("✓ 완료      ")
        elif ps == "in_progress":
            status_labels.append("⟳ 진행중    ")
        elif ps == "failed":
            status_labels.append("✗ 실패      ")
        else:
            status_labels.append("⏸ 대기      ")
    lines.append("    " + "   ".join(status_labels))
    lines.append("")

    # Stage detail per phase
    for phase_name, phase_s, stages in phases:
        if stages:
            lines.append(f"  [{phase_name}]")
            for stage_name, st in stages:
                icon = STATUS_ICON.get(st, "?")
                lines.append(f"    {icon} {stage_name}")
            lines.append("")

    return "\n".join(lines)


def render_ac_tree_flat(features: list[dict]) -> str:
    """Render per-feature AC progress (flat, not tree).

    Args:
        features: list of {name, acs: [{id, verdict}]}

    Returns:
        ASCII list.
    """
    lines = []
    for feat in features:
        name = feat.get("name", "unknown")
        acs = feat.get("acs", [])
        total = len(acs)
        passed = sum(1 for a in acs if a.get("verdict") == "PASS")
        status_icon = "✓" if passed == total and total > 0 else ("⟳" if passed > 0 else "⏸")
        lines.append(f"  {status_icon} {name} [{passed}/{total}]")
        for ac in acs:
            v = ac.get("verdict", "PENDING")
            ai = "✓" if v == "PASS" else ("⟳" if v == "PARTIAL" else ("✗" if v == "FAIL" else "⏸"))
            lines.append(f"    {ai} {ac.get('id', '?')}")
    return "\n".join(lines)


def update_progress_file(project_path: str, state: dict, features: list[dict] | None = None) -> dict:
    """Write `.samvil/progress.md` with current visualization.

    Args:
        project_path: Project root
        state: Current state dict (from state.json)
        features: Optional per-feature AC progress

    Returns:
        Dict with path and bytes_written.
    """
    samvil_dir = Path(project_path) / ".samvil"
    samvil_dir.mkdir(parents=True, exist_ok=True)

    progress_path = samvil_dir / "progress.md"

    # Determine stage statuses
    current_stage = state.get("current_stage", "interview")
    completed = set(state.get("completed_stages", []))
    failed_set = {f.get("stage") for f in state.get("failed", []) if f.get("stage")}

    all_stages = ["interview", "seed", "council", "design", "scaffold", "build", "qa", "deploy", "evolve", "retro"]
    stage_statuses: dict[str, Status] = {}
    for s in all_stages:
        if s in failed_set:
            stage_statuses[s] = "failed"
        elif s in completed:
            stage_statuses[s] = "done"
        elif s == current_stage:
            stage_statuses[s] = "in_progress"
        else:
            stage_statuses[s] = "pending"

    timestamp = datetime.now(timezone.utc).isoformat()

    lines = [
        "# SAMVIL Progress",
        "",
        f"> Last updated: {timestamp}",
        f"> Current stage: **{current_stage}**",
        "",
        "## Double Diamond",
        "",
        "```",
        render_double_diamond(stage_statuses),
        "```",
        "",
    ]

    if features:
        lines.extend([
            "## Feature Progress",
            "",
            "```",
            render_ac_tree_flat(features),
            "```",
            "",
        ])

    content = "\n".join(lines)
    progress_path.write_text(content, encoding="utf-8")
    return {"path": str(progress_path), "bytes": len(content)}
