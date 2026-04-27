"""Chain Marker — file-based skill continuation for non-Skill hosts (M2).

On hosts without a Skill tool (Codex CLI, OpenCode, generic), the pipeline
continues via a file marker at `.samvil/next-skill.json`. Each skill writes
its successor info on completion; the next invocation reads it and proceeds.

Format:
  {
    "next_skill": "samvil-qa",
    "chain_via": "file_marker",
    "host_name": "codex_cli",
    "command": "samvil samvil-qa",
    "marker_path": ".samvil/next-skill.json",
    "written_at": "2026-04-27T12:00:00Z"
  }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .host_adapters import get_chain_continuation as _get_chain_continuation

MARKER_FILENAME = "next-skill.json"
SAMVIL_DIR = ".samvil"


def write_chain_marker(
    project_root: str,
    host_name: str | None,
    current_skill: str,
) -> dict[str, Any]:
    """Write the next-skill marker after current_skill completes.

    Creates `.samvil/next-skill.json` with chain continuation data.
    Returns the marker dict that was written.
    """
    root = Path(project_root)
    samvil_dir = root / SAMVIL_DIR
    samvil_dir.mkdir(parents=True, exist_ok=True)

    continuation = _get_chain_continuation(host_name, current_skill)
    marker = {
        **continuation,
        "schema_version": "1.0",
        "reason": f"{current_skill} completed",
        "from_stage": current_skill,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    marker_path = samvil_dir / MARKER_FILENAME
    marker_path.write_text(json.dumps(marker, indent=2))

    return marker


def read_chain_marker(
    project_root: str,
) -> dict[str, Any] | None:
    """Read the current next-skill marker.

    Returns the marker dict or None if no marker exists.
    """
    marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
    if not marker_path.exists():
        return None

    try:
        data = json.loads(marker_path.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return None


def clear_chain_marker(
    project_root: str,
) -> bool:
    """Remove the chain marker (e.g., after pipeline completes).

    Returns True if marker was removed, False if it didn't exist.
    """
    marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
    if marker_path.exists():
        marker_path.unlink()
        return True
    return False


def advance_chain(
    project_root: str,
    host_name: str | None,
) -> dict[str, Any]:
    """Read current marker and advance to next skill.

    Reads the marker, writes a new one for the next skill in chain,
    and returns the new marker. Returns empty dict if at pipeline end.
    """
    current = read_chain_marker(project_root)
    if current is None or not current.get("next_skill"):
        return {"next_skill": "", "status": "pipeline_complete"}

    next_skill = current["next_skill"]
    new_marker = write_chain_marker(project_root, host_name, next_skill)
    return new_marker


def get_pipeline_status(
    project_root: str,
) -> dict[str, Any]:
    """Get current pipeline position from marker.

    Returns dict with: has_marker, current_position, next_skill,
    pipeline_progress.
    """
    from .host_adapters import _SKILL_CHAIN

    marker = read_chain_marker(project_root)

    if marker is None:
        return {
            "has_marker": False,
            "current_position": None,
            "next_skill": None,
            "pipeline_progress": "no marker",
            "total_skills": len(_SKILL_CHAIN),
        }

    current = marker.get("command", "").split()[-1] if marker.get("command") else None
    next_skill = marker.get("next_skill", "")

    # Find progress
    skill_names = [e["name"] for e in _SKILL_CHAIN]
    completed = 0
    if current and current in skill_names:
        completed = skill_names.index(current)

    return {
        "has_marker": True,
        "current_position": current,
        "next_skill": next_skill,
        "pipeline_progress": f"{completed + 1}/{len(_SKILL_CHAIN)}",
        "total_skills": len(_SKILL_CHAIN),
        "completed_count": completed + 1,
        "written_at": marker.get("written_at"),
    }
