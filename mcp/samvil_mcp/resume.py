"""Session resume helper — reads project state and determines resume entry point."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STAGE_NEXT_SKILL: dict[str, str] = {
    "interview": "samvil-interview",
    "seed": "samvil-seed",
    "council": "samvil-council",
    "design": "samvil-design",
    "scaffold": "samvil-scaffold",
    "build": "samvil-build",
    "qa": "samvil-qa",
    "deploy": "samvil-deploy",
    "evolve": "samvil-evolve",
    "retro": "samvil-retro",
}


def _read_json_safe(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _minutes_since(ts_iso: str | None) -> int | None:
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
    except (ValueError, TypeError):
        return None


def _handoff_excerpt(samvil_dir: Path, max_chars: int = 500) -> str:
    handoff = samvil_dir / "handoff.md"
    if not handoff.exists():
        return ""
    try:
        text = handoff.read_text(encoding="utf-8")
        return text[-max_chars:].strip() if len(text) > max_chars else text.strip()
    except OSError:
        return ""


def _stage_progress(state: dict[str, Any]) -> str:
    stage = state.get("current_stage", "")
    completed = state.get("completed_features") or []
    in_progress = state.get("in_progress") or ""

    if stage == "build":
        if in_progress and completed:
            return f"Phase B: {len(completed)} done, '{in_progress}' in progress"
        if in_progress:
            return f"Phase B: '{in_progress}' in progress"
        if completed:
            return f"Phase B: {len(completed)} features done"
        return "Phase B: starting"

    if stage == "qa":
        qa_history = state.get("qa_history") or []
        passes = len(qa_history)
        return f"QA: {passes}/3 pass(es) done" if passes else "QA: starting"

    if stage == "evolve":
        retro = state.get("retro_count") or 0
        return f"Evolve: cycle {retro}"

    return stage or "unknown"


def resume_session(project_root: str) -> dict[str, Any]:
    """Read project state and determine resume entry point.

    Returns a dict with:
      found: bool
      last_stage: str
      stage_progress: str
      next_skill: str
      minutes_since: int | None
      last_event_at: str | None
      handoff_excerpt: str
      completed_features: list[str]
      failed_acs: list[str]
      samvil_tier: str
      project_name: str
    """
    root = Path(project_root) if project_root else Path(".")
    samvil_dir = root / ".samvil"

    state = _read_json_safe(root / "project.state.json")
    if not state:
        state = _read_json_safe(samvil_dir / "state.json")

    if not state or not state.get("current_stage"):
        return {
            "found": False,
            "last_stage": "",
            "stage_progress": "",
            "next_skill": "samvil-interview",
            "minutes_since": None,
            "last_event_at": None,
            "handoff_excerpt": "",
            "completed_features": [],
            "failed_acs": [],
            "samvil_tier": "standard",
            "project_name": "",
        }

    current_stage = state.get("current_stage", "")
    last_ts = state.get("last_progress_at")

    seed = _read_json_safe(root / "project.seed.json")
    if not seed:
        seed = _read_json_safe(samvil_dir / "seed.json")

    tier = (
        state.get("samvil_tier")
        or state.get("selected_tier")
        or "standard"
    )
    project_name = seed.get("project_name") or seed.get("app_name") or ""

    return {
        "found": True,
        "last_stage": current_stage,
        "stage_progress": _stage_progress(state),
        "next_skill": _STAGE_NEXT_SKILL.get(current_stage, f"samvil-{current_stage}"),
        "minutes_since": _minutes_since(last_ts),
        "last_event_at": last_ts,
        "handoff_excerpt": _handoff_excerpt(samvil_dir),
        "completed_features": state.get("completed_features") or [],
        "failed_acs": state.get("failed_acs") or [],
        "samvil_tier": tier,
        "project_name": project_name,
    }
