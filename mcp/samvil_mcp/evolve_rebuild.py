"""Materialize rebuild handoff after an evolved seed is applied."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evolve_apply import read_evolve_apply_plan

EVOLVE_REBUILD_SCHEMA_VERSION = "1.0"


def evolve_rebuild_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-rebuild.json"


def next_skill_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "next-skill.json"


def build_evolve_rebuild_handoff(project_root: Path | str) -> dict[str, Any]:
    """Build a portable continuation marker from applied evolve output."""
    root = Path(project_root)
    apply_plan = read_evolve_apply_plan(root) or {}
    status = "ready" if apply_plan.get("status") == "applied" else "blocked"
    from_version = apply_plan.get("from_version")
    to_version = apply_plan.get("to_version")
    reason = (
        f"evolved seed v{from_version}->v{to_version} applied; rebuild with evolved seed"
        if status == "ready"
        else "apply evolve plan before rebuild handoff"
    )
    marker = {
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "host": "portable",
        "next_skill": "samvil-scaffold",
        "reason": reason,
        "from_stage": "evolve",
        "created_by": "samvil-evolve",
        "target_stage": "scaffold",
    }
    return {
        "schema_version": EVOLVE_REBUILD_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "evolve_apply_plan",
        "status": status,
        "from_version": from_version,
        "to_version": to_version,
        "next_skill": marker["next_skill"] if status == "ready" else None,
        "reason": reason,
        "marker": marker if status == "ready" else {},
        "next_action": "continue with samvil-scaffold" if status == "ready" else "apply evolve plan first",
    }


def materialize_evolve_rebuild_handoff(project_root: Path | str) -> dict[str, Any]:
    handoff = build_evolve_rebuild_handoff(project_root)
    handoff_path = _atomic_write_json(evolve_rebuild_path(project_root), handoff)
    marker_path = ""
    if handoff.get("status") == "ready":
        marker_path = str(_atomic_write_json(next_skill_path(project_root), handoff["marker"]))
    return {
        "schema_version": EVOLVE_REBUILD_SCHEMA_VERSION,
        "status": handoff["status"],
        "project_root": str(Path(project_root)),
        "evolve_rebuild_path": str(handoff_path),
        "next_skill_path": marker_path,
        "next_skill": handoff.get("next_skill"),
        "next_action": handoff.get("next_action"),
    }


def read_evolve_rebuild_handoff(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(evolve_rebuild_path(project_root))
    return data or None


def evolve_rebuild_summary(project_root: Path | str) -> dict[str, Any]:
    handoff = read_evolve_rebuild_handoff(project_root) or {}
    return {
        "present": bool(handoff),
        "status": handoff.get("status"),
        "from_version": handoff.get("from_version"),
        "to_version": handoff.get("to_version"),
        "next_skill": handoff.get("next_skill"),
        "next_action": handoff.get("next_action"),
        "path": str(evolve_rebuild_path(project_root)) if handoff else "",
        "next_skill_path": str(next_skill_path(project_root)) if next_skill_path(project_root).exists() else "",
    }


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
