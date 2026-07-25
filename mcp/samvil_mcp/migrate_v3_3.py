"""Backup-first seed migration from v3.2 to v3.3 verify contracts."""

from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from .ac_verification import prepare_seed_verify_contracts
from .claim_ledger import _locked
from .seed_manager import validate_seed
from .ssot_io import atomic_write_text, atomic_write_text_unlocked


V33_SCHEMA_VERSION = "3.3"
BACKUP_FILENAME = "project.v3-2.backup.json"
MIGRATION_JOURNAL_FILENAME = ".project.seed.json.migration-journal"
_backup_lock_state = threading.local()
_atomic_write_text_original = atomic_write_text


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
) -> bool:
    """Preserve the first valid backup or atomically replace an invalid one."""
    if _is_valid_v32_backup(backup_path):
        return False

    if getattr(_backup_lock_state, "held", False):
        write_backup = (
            atomic_write_text
            if atomic_write_text is not _atomic_write_text_original
            else atomic_write_text_unlocked
        )
    else:
        write_backup = atomic_write_text
    write_backup(backup_path, seed_text)
    try:
        written_text = backup_path.read_text(encoding="utf-8")
        written_seed = json.loads(written_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError(f"backup verification failed: {exc}") from exc
    if written_text != seed_text or written_seed != seed:
        raise OSError("backup verification failed: content mismatch")
    return True


def _verify_backup_contents(
    backup_path: Path,
    seed_text: str | None,
    seed: dict[str, Any] | None,
) -> None:
    try:
        written_text = backup_path.read_text(encoding="utf-8")
        written_seed = json.loads(written_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError(f"backup verification failed: {exc}") from exc
    if not (
        isinstance(written_seed, dict)
        and str(written_seed.get("schema_version")) == "3.2"
        and validate_seed(copy.deepcopy(written_seed))["valid"]
    ):
        raise OSError("backup verification failed: invalid v3.2 backup")
    if seed_text is not None and (written_text != seed_text or written_seed != seed):
        raise OSError("backup verification failed: content mismatch")


def _migration_journal_path(root: Path) -> Path:
    return root / MIGRATION_JOURNAL_FILENAME


def _recover_interrupted_migration(root: Path) -> None:
    journal_path = _migration_journal_path(root)
    if not journal_path.exists():
        return
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        original_text = str(journal["original_seed_text"])
        migrated_text = str(journal["migrated_seed_text"])
        backup_text = str(journal["backup_text"])
        seed_path = root / "project.seed.json"
        backup_path = root / BACKUP_FILENAME
        current_seed = seed_path.read_text(encoding="utf-8")
        current_backup = backup_path.read_text(encoding="utf-8")
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError("migration recovery journal is corrupt") from exc

    if current_seed == original_text:
        if current_backup != backup_text:
            atomic_write_text_unlocked(backup_path, backup_text)
        journal_path.unlink(missing_ok=True)
        return
    if current_seed != migrated_text:
        raise RuntimeError("migration recovery found an unexpected seed; manual review required")
    if current_backup == backup_text:
        journal_path.unlink(missing_ok=True)
        return

    atomic_write_text_unlocked(seed_path, original_text)
    atomic_write_text_unlocked(backup_path, backup_text)
    journal_path.unlink(missing_ok=True)


def _replace_seed_if_unchanged(
    seed_path: Path,
    expected_text: str,
    migrated_text: str,
) -> None:
    """Replace the seed only if an in-place writer did not mutate its inode."""
    snapshot_path = seed_path.with_name(
        f".{seed_path.name}.migration-snapshot-{uuid.uuid4().hex}"
    )
    result_path = seed_path.with_name(
        f".{seed_path.name}.migration-result-{uuid.uuid4().hex}"
    )
    try:
        os.link(seed_path, snapshot_path)
        if snapshot_path.read_text(encoding="utf-8") != expected_text:
            raise RuntimeError("seed changed during migration; retry from current state")
        atomic_write_text_unlocked(result_path, migrated_text)
        if (
            not os.path.samefile(seed_path, snapshot_path)
            or snapshot_path.read_text(encoding="utf-8") != expected_text
        ):
            raise RuntimeError("seed changed during migration; retry from current state")
        os.replace(result_path, seed_path)
        snapshot_text = snapshot_path.read_text(encoding="utf-8")
        if snapshot_text != expected_text:
            atomic_write_text_unlocked(seed_path, snapshot_text)
            raise RuntimeError("seed changed during migration; retry from current state")
    finally:
        try:
            snapshot_path.unlink(missing_ok=True)
        except OSError:
            pass
        for temporary in (result_path,):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


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
        _recover_interrupted_migration(root)
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
        with _locked(backup_path):
            _backup_lock_state.held = True
            try:
                backup_rewritten = _ensure_verified_backup(backup_path, seed_text, seed)
                _verify_backup_contents(
                    backup_path,
                    seed_text if backup_rewritten else None,
                    seed if backup_rewritten else None,
                )
                backup_snapshot_text = backup_path.read_text(encoding="utf-8")
                backup_snapshot_seed = json.loads(backup_snapshot_text)
                if seed_path.read_text(encoding="utf-8") != seed_text:
                    raise RuntimeError(
                        "seed changed during migration; retry from current state"
                    )
                migrated_text = json.dumps(migrated, indent=2, ensure_ascii=False) + "\n"
                atomic_write_text_unlocked(
                    _migration_journal_path(root),
                    json.dumps(
                        {
                            "original_seed_text": seed_text,
                            "migrated_seed_text": migrated_text,
                            "backup_text": backup_snapshot_text,
                        },
                        ensure_ascii=False,
                    ),
                )
                _replace_seed_if_unchanged(
                    seed_path,
                    seed_text,
                    migrated_text,
                )
                try:
                    _verify_backup_contents(
                        backup_path,
                        backup_snapshot_text,
                        backup_snapshot_seed,
                    )
                except OSError:
                    if seed_path.read_text(encoding="utf-8") == migrated_text:
                        atomic_write_text_unlocked(seed_path, seed_text)
                    raise
                _migration_journal_path(root).unlink(missing_ok=True)
            finally:
                _backup_lock_state.held = False
        return {
            "changed": True,
            "changes": changes,
            "schema_version": V33_SCHEMA_VERSION,
            "backup": BACKUP_FILENAME,
        }
