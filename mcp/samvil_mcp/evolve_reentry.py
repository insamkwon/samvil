"""Prepare scaffold reentry input after evolve rebuild handoff."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVOLVE_REENTRY_SCHEMA_VERSION = "1.0"


def rebuild_reentry_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "rebuild-reentry.json"


def scaffold_input_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "scaffold-input.json"


def build_rebuild_reentry(project_root: Path | str) -> dict[str, Any]:
    """Build deterministic input for re-entering scaffold after evolve."""
    root = Path(project_root)
    seed = _load_json(root / "project.seed.json")
    marker = _load_json(root / ".samvil" / "next-skill.json")
    rebuild = _load_json(root / ".samvil" / "evolve-rebuild.json")
    issues = _issues(seed, marker, rebuild)
    status = "ready" if not issues else "blocked"
    target_version = rebuild.get("to_version") or seed.get("version")
    scaffold_input = {
        "schema_version": "1.0",
        "project_root": str(root),
        "seed_path": str(root / "project.seed.json"),
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "seed_sha256": _stable_hash(seed) if seed else "",
        "next_skill": marker.get("next_skill"),
        "from_stage": marker.get("from_stage"),
        "reason": marker.get("reason") or rebuild.get("reason"),
    } if status == "ready" else {}
    return {
        "schema_version": EVOLVE_REENTRY_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "evolve_rebuild_handoff",
        "status": status,
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "target_version": target_version,
        "seed_sha256": _stable_hash(seed) if seed else "",
        "next_skill": marker.get("next_skill"),
        "from_stage": marker.get("from_stage"),
        "issues": issues,
        "scaffold_input": scaffold_input,
        "next_action": "run samvil-scaffold with scaffold input" if status == "ready" else "fix rebuild reentry blockers",
    }


def materialize_rebuild_reentry(project_root: Path | str) -> dict[str, Any]:
    reentry = build_rebuild_reentry(project_root)
    reentry_path = _atomic_write_json(rebuild_reentry_path(project_root), reentry)
    scaffold_path = ""
    if reentry.get("status") == "ready":
        scaffold_path = str(_atomic_write_json(scaffold_input_path(project_root), reentry["scaffold_input"]))
    return {
        "schema_version": EVOLVE_REENTRY_SCHEMA_VERSION,
        "status": reentry["status"],
        "project_root": str(Path(project_root)),
        "rebuild_reentry_path": str(reentry_path),
        "scaffold_input_path": scaffold_path,
        "next_skill": reentry.get("next_skill"),
        "next_action": reentry.get("next_action"),
    }


def read_rebuild_reentry(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(rebuild_reentry_path(project_root))
    return data or None


def rebuild_reentry_summary(project_root: Path | str) -> dict[str, Any]:
    reentry = read_rebuild_reentry(project_root) or {}
    return {
        "present": bool(reentry),
        "status": reentry.get("status"),
        "seed_name": reentry.get("seed_name"),
        "seed_version": reentry.get("seed_version"),
        "target_version": reentry.get("target_version"),
        "next_skill": reentry.get("next_skill"),
        "issue_count": len(reentry.get("issues") or []),
        "next_action": reentry.get("next_action"),
        "path": str(rebuild_reentry_path(project_root)) if reentry else "",
        "scaffold_input_path": str(scaffold_input_path(project_root)) if scaffold_input_path(project_root).exists() else "",
    }


def _issues(seed: dict[str, Any], marker: dict[str, Any], rebuild: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not seed:
        issues.append("project.seed.json missing")
    if not marker:
        issues.append(".samvil/next-skill.json missing")
    if not rebuild:
        issues.append(".samvil/evolve-rebuild.json missing")
    if marker and marker.get("next_skill") != "samvil-scaffold":
        issues.append("next-skill marker does not target samvil-scaffold")
    if marker and marker.get("from_stage") != "evolve":
        issues.append("next-skill marker does not start from evolve")
    if rebuild and rebuild.get("status") != "ready":
        issues.append("evolve rebuild handoff is not ready")
    if seed and rebuild and rebuild.get("to_version") and seed.get("version") != rebuild.get("to_version"):
        issues.append("project.seed.json version does not match rebuild target")
    return issues


def _stable_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
