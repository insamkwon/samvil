"""Backup-first seed migration from v3.2 to v3.3 verify contracts."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from .ac_verification import prepare_seed_verify_contracts
from .ssot_io import atomic_write_text


V33_SCHEMA_VERSION = "3.3"
BACKUP_FILENAME = "project.v3-2.backup.json"


def _migrate_seed_dict(seed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    source_version = str(seed.get("schema_version") or "")
    if source_version == V33_SCHEMA_VERSION:
        return copy.deepcopy(seed), []
    if source_version != "3.2":
        raise ValueError(
            "v3.3 migration requires schema_version '3.2'; "
            f"got {source_version!r}"
        )
    original = copy.deepcopy(seed)
    preparation = prepare_seed_verify_contracts(original)
    prepared = preparation["seed"]
    changes: list[str] = []
    if str(seed.get("schema_version") or "") != V33_SCHEMA_VERSION:
        changes.append(
            f"schema_version: {seed.get('schema_version')!r} -> {V33_SCHEMA_VERSION!r}"
        )
    if preparation["filled_count"]:
        changes.append("populate browser AC verify.command contracts")
    return prepared, changes


def apply_migration(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    seed_path = root / "project.seed.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    migrated, changes = _migrate_seed_dict(seed)
    if not changes:
        return {"changed": False, "changes": [], "schema_version": V33_SCHEMA_VERSION}

    backup_path = root / BACKUP_FILENAME
    if not backup_path.exists():
        shutil.copy2(seed_path, backup_path)
    atomic_write_text(
        seed_path,
        json.dumps(migrated, indent=2, ensure_ascii=False) + "\n",
    )
    return {
        "changed": True,
        "changes": changes,
        "schema_version": V33_SCHEMA_VERSION,
        "backup": BACKUP_FILENAME,
    }
