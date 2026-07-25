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

from .claim_ledger import _locked
from .host_adapters import (
    _SKILL_CHAIN,
    _ADAPTERS,
    _GENERIC_ADAPTER,
    _host_command_for_skill,
    get_chain_continuation as _get_chain_continuation,
)
from .ssot_io import atomic_write_text

MARKER_FILENAME = "next-skill.json"
SAMVIL_DIR = ".samvil"


def write_chain_marker(
    project_root: str,
    host_name: str | None,
    current_skill: str,
    next_skill: str | None = None,
) -> dict[str, Any]:
    """Write the next-skill marker after current_skill completes.

    Creates `.samvil/next-skill.json` with chain continuation data.
    Returns the marker dict that was written.
    """
    root = Path(project_root)
    samvil_dir = root / SAMVIL_DIR
    samvil_dir.mkdir(parents=True, exist_ok=True)

    continuation = _get_chain_continuation(host_name, current_skill)
    if next_skill is not None:
        valid_skills = {entry["name"] for entry in _SKILL_CHAIN}
        if next_skill not in valid_skills:
            raise ValueError(f"unknown next_skill: {next_skill!r}")
        continuation["next_skill"] = next_skill
    target_skill = str(continuation.get("next_skill") or "")
    adapter = _ADAPTERS.get(
        (host_name or "").strip().lower().replace("-", "_"),
        _GENERIC_ADAPTER,
    )
    continuation["command"] = (
        _host_command_for_skill(adapter, target_skill)
        if target_skill
        else ""
    )
    marker = {
        **continuation,
        "schema_version": "1.0",
        "reason": f"{current_skill} completed",
        "from_stage": current_skill,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    marker_path = samvil_dir / MARKER_FILENAME
    atomic_write_text(marker_path, json.dumps(marker, indent=2))

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
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _read_project_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def resolve_stage_next_skill(
    project_root: str | Path,
    current_skill: str,
) -> str | None:
    """Resolve project-aware dynamic routing for stage-end recovery markers."""
    root = Path(project_root)
    if current_skill == "samvil-qa":
        results = _read_project_json(root / ".samvil" / "qa-results.json")
        synthesis = results.get("synthesis")
        if not isinstance(synthesis, dict) or not synthesis:
            return None
        if str(synthesis.get("verdict") or "").upper() not in {
            "PASS",
            "REVISE",
            "FAIL",
        }:
            return None
        pass2 = synthesis.get("pass2")
        if pass2 is not None and not isinstance(pass2, dict):
            return None
        if isinstance(pass2, dict):
            counts = pass2.get("counts")
            if counts is not None and not isinstance(counts, dict):
                return None
            if isinstance(counts, dict) and any(
                not isinstance(label, str) or not _is_nonnegative_int(value)
                for label, value in counts.items()
            ):
                return None
        state = _read_project_json(root / "project.state.json")
        build_retries = state.get("build_retries")
        if build_retries is not None and not _is_nonnegative_int(build_retries):
            return None
        qa_history = state.get("qa_history")
        if qa_history is not None and not isinstance(qa_history, list):
            return None
        convergence = results.get("convergence")
        if convergence is None:
            convergence = {}
        elif not isinstance(convergence, dict):
            return None
        from .qa_finalize import _decide_next_skill

        return str(
            _decide_next_skill(synthesis, state, convergence).get("suggested") or ""
        ) or None

    if current_skill != "samvil-pm-interview":
        return None

    config = _read_project_json(root / "project.config.json")
    state = _read_project_json(root / "project.state.json")
    flags = config.get("flags") or []
    if isinstance(flags, str):
        flags = flags.split()
    tier = str(
        state.get("samvil_tier")
        or state.get("selected_tier")
        or config.get("samvil_tier")
        or config.get("selected_tier")
        or "standard"
    )
    if isinstance(flags, list) and "--council" in flags and tier != "minimal":
        return "samvil-council"
    return "samvil-design"


def clear_chain_marker(
    project_root: str,
) -> bool:
    """Remove the chain marker (e.g., after pipeline completes).

    Returns True if marker was removed, False if it didn't exist.
    """
    marker_path = Path(project_root) / SAMVIL_DIR / MARKER_FILENAME
    with _locked(marker_path):
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
    resolved = resolve_stage_next_skill(project_root, next_skill)
    if next_skill == "samvil-qa" and resolved is None:
        return {
            **current,
            "status": "blocked_missing_qa_results",
        }
    new_marker = write_chain_marker(
        project_root,
        host_name,
        next_skill,
        next_skill=resolved,
    )
    return new_marker


def get_pipeline_status(
    project_root: str,
) -> dict[str, Any]:
    """Get current pipeline position from marker.

    Returns dict with: has_marker, current_position, next_skill,
    pipeline_progress.
    """
    marker = read_chain_marker(project_root)

    if marker is None:
        return {
            "has_marker": False,
            "current_position": None,
            "next_skill": None,
            "pipeline_progress": "no marker",
            "total_skills": len(_SKILL_CHAIN),
        }

    current = marker.get("from_stage")
    if not current and marker.get("command"):
        current = marker["command"].split()[-1]
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
