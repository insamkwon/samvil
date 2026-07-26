"""Session resume helper — reads project state and determines resume entry point.

Also provides L2 AC-leaf checkpoint: tracks which specific leaf (feature + ac)
the build stage was processing when interrupted, enabling sub-feature recovery.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ssot_io import atomic_write_text
from .stage_catalog import iter_stage_specs

_LEAF_CHECKPOINT_FILENAME = "leaf-checkpoint.json"
_SAMVIL_DIR = ".samvil"

# Compatibility view: state-to-skill mapping is owned by stage_catalog.
_STAGE_NEXT_SKILL: dict[str, str] = {
    spec.state_stage: spec.skill_name
    for spec in iter_stage_specs()
    if spec.state_stage is not None
}


from .utils import read_json_or_empty as _read_json_safe  # noqa: E402


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


def _stage_progress(state: dict[str, Any], leaf: dict[str, Any] | None = None) -> str:
    stage = state.get("current_stage", "")
    completed = state.get("completed_features") or []
    in_progress = state.get("in_progress") or ""

    if stage == "build":
        if leaf:
            feat = leaf.get("feature_id", "")
            leaf_id = leaf.get("leaf_id", "")
            desc = leaf.get("leaf_description", "")
            prefix = f"Phase B: {len(completed)} done, " if completed else "Phase B: "
            detail = f"{feat} › {leaf_id}"
            if desc:
                detail += f" ({desc})"
            return f"{prefix}{detail} in progress"
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


def write_leaf_checkpoint(
    project_root: str,
    feature_id: str,
    leaf_id: str,
    leaf_description: str = "",
) -> dict[str, Any]:
    """Write an L2 AC-leaf checkpoint so resume can pinpoint the interrupted leaf."""
    root = Path(project_root) if project_root else Path(".")
    d = root / _SAMVIL_DIR
    d.mkdir(parents=True, exist_ok=True)
    checkpoint: dict[str, Any] = {
        "feature_id": feature_id,
        "leaf_id": leaf_id,
        "leaf_description": leaf_description,
        "written_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    atomic_write_text(
        d / _LEAF_CHECKPOINT_FILENAME,
        json.dumps(checkpoint, ensure_ascii=False, indent=2),
    )
    return checkpoint


def read_leaf_checkpoint(project_root: str) -> dict[str, Any] | None:
    """Read the L2 AC-leaf checkpoint. Returns None if not present or corrupt."""
    root = Path(project_root) if project_root else Path(".")
    path = root / _SAMVIL_DIR / _LEAF_CHECKPOINT_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_leaf_checkpoint(project_root: str) -> bool:
    """Remove the leaf checkpoint file. Returns True if it existed."""
    path = (Path(project_root) if project_root else Path(".")) / _SAMVIL_DIR / _LEAF_CHECKPOINT_FILENAME
    if path.exists():
        path.unlink()
        return True
    return False


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
      in_progress_leaf: dict | None  — L2 leaf checkpoint if build was interrupted
    """
    root = Path(project_root) if project_root else Path(".")
    samvil_dir = root / _SAMVIL_DIR

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
            "in_progress_leaf": None,
            "chain_marker": None,
        }

    current_stage = state.get("current_stage", "")
    last_ts = state.get("last_progress_at")
    leaf = read_leaf_checkpoint(project_root)

    # W2.2 — chain-break recovery: the stage-end hook writes
    # .samvil/next-skill.json when a stage completes; the stage-start hook
    # clears it when the chain actually continues. A surviving marker means
    # the chain invoke never happened — its next_skill is the recovery point.
    #
    # v4.30.4 guard: the hook fires when the Skill tool *returns* (i.e. at
    # stage start), so the marker exists while the stage is still running.
    # Trust it only when the state shows the marker's stage actually
    # completed — otherwise a mid-stage crash would skip the unfinished
    # stage (e.g. half-built project sent straight to QA).
    from .chain_markers import read_chain_marker

    chain_marker = read_chain_marker(str(root))
    marker_next = ""
    if chain_marker and chain_marker.get("next_skill"):
        marker_stage = str(chain_marker.get("from_stage", "")).replace("samvil-", "")
        completed = [
            str(s).replace("samvil-", "")
            for s in (state.get("completed_stages") or [])
        ]
        if marker_stage and (
            marker_stage in completed or marker_stage != current_stage
        ):
            marker_next = str(chain_marker["next_skill"])

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
        "stage_progress": _stage_progress(state, leaf),
        "next_skill": marker_next
        or _STAGE_NEXT_SKILL.get(current_stage, f"samvil-{current_stage}"),
        "chain_marker": chain_marker,
        "minutes_since": _minutes_since(last_ts),
        "last_event_at": last_ts,
        "handoff_excerpt": _handoff_excerpt(samvil_dir),
        "completed_features": state.get("completed_features") or [],
        "failed_acs": state.get("failed_acs") or [],
        "samvil_tier": tier,
        "project_name": project_name,
        "in_progress_leaf": leaf,
    }
