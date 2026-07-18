"""Seed migration from v3.2 to v3.3 AC verify contracts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

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
        "solution_type": "web-app",
        "features": [
            {
                "name": "counter",
                "acceptance_criteria": [
                    {"id": "F1.AC1", "description": "counter increments"}
                ],
            }
        ],
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


def test_migrate_seed_v3_3_mcp_tool(tmp_path: Path) -> None:
    from samvil_mcp.server import migrate_seed_v3_3

    (tmp_path / "project.seed.json").write_text(json.dumps(_seed()))

    result = json.loads(asyncio.run(migrate_seed_v3_3(str(tmp_path))))

    assert result["changed"] is True
    assert result["schema_version"] == "3.3"
