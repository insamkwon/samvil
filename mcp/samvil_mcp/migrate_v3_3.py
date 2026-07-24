"""Backup-first seed migration from v3.2 to v3.3 verify contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .ac_verification import prepare_seed_verify_contracts
from .claim_ledger import _locked
from .seed_manager import validate_seed
from .ssot_io import atomic_write_text, atomic_write_text_unlocked


V33_SCHEMA_VERSION = "3.3"
BACKUP_FILENAME = "project.v3-2.backup.json"


def _is_valid_v32_backup(path: Path) -> bool:
    try:
        backup = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(backup, dict)
        and str(backup.get("schema_version")) == "3.2"
        and validate_seed(copy.deepcopy(backup))["valid"]
    )


def _ensure_verified_backup(
    backup_path: Path,
    seed_text: str,
    seed: dict[str, Any],
) -> None:
    """Preserve the first valid backup or atomically replace an invalid one."""
    if _is_valid_v32_backup(backup_path):
        return

    atomic_write_text(backup_path, seed_text)
    try:
        written_text = backup_path.read_text(encoding="utf-8")
        written_seed = json.loads(written_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError(f"backup verification failed: {exc}") from exc
    if written_text != seed_text or written_seed != seed:
        raise OSError("backup verification failed: content mismatch")


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
    with _locked(seed_path):
        seed_text = seed_path.read_text(encoding="utf-8")
        seed = json.loads(seed_text)
        if str(seed.get("schema_version") or "") == "3.2":
            validation = validate_seed(copy.deepcopy(seed))
            if not validation["valid"]:
                details = "; ".join(
                    str(error) for error in validation.get("errors", [])
                )
                raise ValueError(
                    f"source seed is invalid: {details or 'validation failed'}"
                )
        migrated, changes = _migrate_seed_dict(seed)
        if not changes:
            return {
                "changed": False,
                "changes": [],
                "schema_version": V33_SCHEMA_VERSION,
            }

        backup_path = root / BACKUP_FILENAME
        _ensure_verified_backup(backup_path, seed_text, seed)
        if seed_path.read_text(encoding="utf-8") != seed_text:
            raise RuntimeError("seed changed during migration; retry from current state")
        atomic_write_text_unlocked(
            seed_path,
            json.dumps(migrated, indent=2, ensure_ascii=False) + "\n",
        )
        return {
            "changed": True,
            "changes": changes,
            "schema_version": V33_SCHEMA_VERSION,
            "backup": BACKUP_FILENAME,
        }
