"""Seed migration from v3.2 to v3.3 AC verify contracts."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Event

import pytest

from samvil_mcp.migrate_v3_3 import (
    BACKUP_FILENAME,
    V33_SCHEMA_VERSION,
    _migrate_seed_dict,
    apply_migration,
)


def _seed() -> dict:
    return {
        "schema_version": "3.2",
        "name": "demo-app",
        "description": "A demo counter application",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "primary_screen": "CounterScreen",
            "key_interactions": ["increment counter"],
        },
        "features": [
            {
                "name": "counter",
                "priority": 1,
                "acceptance_criteria": [
                    {"id": "F1.AC1", "description": "counter increments"}
                ],
            }
        ],
        "constraints": ["local-first"],
        "out_of_scope": ["authentication"],
        "version": "1.0.0",
    }


def test_migrate_seed_adds_browser_verify_contract() -> None:
    migrated, changes = _migrate_seed_dict(_seed())

    assert migrated["schema_version"] == V33_SCHEMA_VERSION
    assert migrated["features"][0]["acceptance_criteria"][0]["verify"] == {
        "command": "npx playwright test tests/e2e/counter.spec.ts"
    }
    assert changes


@pytest.mark.parametrize("schema_version", ["2.0", "3.1", "3.4", "4.0", ""])
def test_migration_rejects_unsupported_source_versions(schema_version: str) -> None:
    seed = _seed()
    seed["schema_version"] = schema_version

    with pytest.raises(ValueError, match="requires schema_version '3.2'"):
        _migrate_seed_dict(seed)


def test_apply_migration_is_backup_first_and_idempotent(tmp_path: Path) -> None:
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(_seed()))

    first = apply_migration(tmp_path)
    after_first = seed_path.read_text()
    second = apply_migration(tmp_path)

    assert first["changed"] is True
    assert (tmp_path / BACKUP_FILENAME).exists()
    assert json.loads(seed_path.read_text())["schema_version"] == "3.3"
    assert second["changed"] is False
    assert seed_path.read_text() == after_first


def test_apply_migration_replaces_corrupt_partial_backup(tmp_path: Path) -> None:
    seed_path = tmp_path / "project.seed.json"
    original_text = json.dumps(_seed())
    seed_path.write_text(original_text)
    backup_path = tmp_path / BACKUP_FILENAME
    backup_path.write_text('{"schema_version": "3.2"')

    result = apply_migration(tmp_path)

    assert result["changed"] is True
    assert backup_path.read_text() == original_text
    assert json.loads(seed_path.read_text())["schema_version"] == "3.3"


def test_apply_migration_replaces_parseable_but_incomplete_backup(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "project.seed.json"
    original_text = json.dumps(_seed())
    seed_path.write_text(original_text)
    backup_path = tmp_path / BACKUP_FILENAME
    backup_path.write_text(json.dumps({"schema_version": "3.2"}))

    apply_migration(tmp_path)

    assert backup_path.read_text() == original_text


def test_apply_migration_replaces_backup_rejected_by_canonical_validator(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "project.seed.json"
    original_text = json.dumps(_seed())
    seed_path.write_text(original_text)
    invalid_backup = _seed()
    invalid_backup["tech_stack"] = {"framework": "unsupported"}
    backup_path = tmp_path / BACKUP_FILENAME
    backup_path.write_text(json.dumps(invalid_backup))

    apply_migration(tmp_path)

    assert backup_path.read_text() == original_text


def test_apply_migration_rejects_invalid_source_before_backup_or_seed_write(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "project.seed.json"
    invalid_seed = _seed()
    invalid_seed["tech_stack"] = {"framework": "unsupported"}
    original_text = json.dumps(invalid_seed)
    seed_path.write_text(original_text)

    with pytest.raises(ValueError, match="source seed is invalid"):
        apply_migration(tmp_path)

    assert seed_path.read_text() == original_text
    assert not (tmp_path / BACKUP_FILENAME).exists()


def test_apply_migration_preserves_valid_first_backup(tmp_path: Path) -> None:
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(_seed()))
    first_seed = _seed()
    first_seed["name"] = "original-first-seed"
    backup_path = tmp_path / BACKUP_FILENAME
    first_backup = json.dumps(first_seed)
    backup_path.write_text(first_backup)

    apply_migration(tmp_path)

    assert backup_path.read_text() == first_backup


def test_apply_migration_does_not_change_seed_when_backup_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from samvil_mcp import migrate_v3_3 as migration

    seed_path = tmp_path / "project.seed.json"
    original_text = json.dumps(_seed())
    seed_path.write_text(original_text)
    real_atomic_write = migration.atomic_write_text

    def fail_backup_write(path, text, **kwargs):
        if Path(path).name == BACKUP_FILENAME:
            raise OSError("backup disk full")
        return real_atomic_write(path, text, **kwargs)

    monkeypatch.setattr(migration, "atomic_write_text", fail_backup_write)

    with pytest.raises(OSError, match="backup disk full"):
        apply_migration(tmp_path)

    assert seed_path.read_text() == original_text
    assert not (tmp_path / BACKUP_FILENAME).exists()


def test_apply_migration_does_not_overwrite_seed_changed_during_backup(
    tmp_path: Path, monkeypatch
) -> None:
    from samvil_mcp import migrate_v3_3 as migration

    seed_path = tmp_path / "project.seed.json"
    original_text = json.dumps(_seed())
    seed_path.write_text(original_text)
    concurrent_seed = _seed()
    concurrent_seed["name"] = "written-by-concurrent-owner"
    concurrent_text = json.dumps(concurrent_seed)
    real_ensure_backup = migration._ensure_verified_backup

    def backup_then_concurrent_write(backup_path, seed_text, seed):
        real_ensure_backup(backup_path, seed_text, seed)
        seed_path.write_text(concurrent_text)

    monkeypatch.setattr(migration, "_ensure_verified_backup", backup_then_concurrent_write)

    with pytest.raises(RuntimeError, match="seed changed during migration"):
        apply_migration(tmp_path)

    assert seed_path.read_text() == concurrent_text
    assert (tmp_path / BACKUP_FILENAME).read_text() == original_text


def test_apply_migration_holds_seed_lock_until_atomic_replace(
    tmp_path: Path, monkeypatch
) -> None:
    from samvil_mcp import migrate_v3_3 as migration
    from samvil_mcp.ssot_io import atomic_write_text as concurrent_atomic_write

    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps(_seed()))
    concurrent_seed = _seed()
    concurrent_seed["name"] = "serialized-concurrent-owner"
    concurrent_text = json.dumps(concurrent_seed)
    backup_ready = Event()
    release_migration = Event()
    writer_started = Event()
    real_ensure_backup = migration._ensure_verified_backup

    def pause_after_backup(backup_path, seed_text, seed):
        real_ensure_backup(backup_path, seed_text, seed)
        backup_ready.set()
        assert release_migration.wait(timeout=2)

    def write_concurrently() -> None:
        writer_started.set()
        concurrent_atomic_write(seed_path, concurrent_text)

    monkeypatch.setattr(migration, "_ensure_verified_backup", pause_after_backup)

    with ThreadPoolExecutor(max_workers=2) as executor:
        migration_future = executor.submit(apply_migration, tmp_path)
        assert backup_ready.wait(timeout=2)
        writer_future = executor.submit(write_concurrently)
        assert writer_started.wait(timeout=2)
        with pytest.raises(FutureTimeoutError):
            writer_future.result(timeout=0.1)
        release_migration.set()
        assert migration_future.result(timeout=2)["changed"] is True
        writer_future.result(timeout=2)

    assert seed_path.read_text() == concurrent_text


def test_apply_migration_holds_backup_lock_through_seed_replace(
    tmp_path: Path, monkeypatch
) -> None:
    from samvil_mcp import migrate_v3_3 as migration
    from samvil_mcp.ssot_io import atomic_write_text as concurrent_atomic_write

    seed_path = tmp_path / "project.seed.json"
    backup_path = tmp_path / BACKUP_FILENAME
    seed_path.write_text(json.dumps(_seed()))
    backup_ready = Event()
    release_migration = Event()
    writer_started = Event()
    writer_finished = Event()
    real_ensure_backup = migration._ensure_verified_backup

    def pause_after_backup(path, seed_text, seed):
        real_ensure_backup(path, seed_text, seed)
        backup_ready.set()
        assert release_migration.wait(timeout=2)

    def write_concurrently() -> None:
        writer_started.set()
        concurrent_atomic_write(backup_path, "corrupt")
        writer_finished.set()

    monkeypatch.setattr(migration, "_ensure_verified_backup", pause_after_backup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        migration_future = executor.submit(apply_migration, tmp_path)
        assert backup_ready.wait(timeout=2)
        writer_future = executor.submit(write_concurrently)
        assert writer_started.wait(timeout=2)
        with pytest.raises(FutureTimeoutError):
            writer_future.result(timeout=0.1)
        release_migration.set()
        result = migration_future.result(timeout=2)
        writer_future.result(timeout=2)

    assert result["changed"] is True
    assert json.loads(seed_path.read_text())["schema_version"] == "3.3"


def test_migrate_seed_v3_3_mcp_tool(tmp_path: Path) -> None:
    from samvil_mcp.server import migrate_seed_v3_3

    (tmp_path / "project.seed.json").write_text(json.dumps(_seed()))

    result = json.loads(asyncio.run(migrate_seed_v3_3(str(tmp_path))))

    assert result["changed"] is True
    assert result["schema_version"] == "3.3"
