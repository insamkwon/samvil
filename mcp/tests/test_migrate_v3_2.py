"""Unit tests for migration v3.1 → v3.2 (Sprint 6, ⑫)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.migrate_v3_2 import (
    BACKUP_FILENAME,
    V32_SCHEMA_VERSION,
    _migrate_seed_dict,
    apply_migration,
    plan_migration,
)


def _write_json(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))


def _v3_1_seed() -> dict:
    return {
        "schema_version": "3.1",
        "name": "demo",
        "agent_tier": "standard",  # glossary-allow: v3.1 legacy field
        "features": [
            {
                "name": "login",
                "acceptance_criteria": [
                    {
                        "id": "AC-1.1",
                        "intent": "user logs in",
                        "verification": "login returns 200",
                        "children": [],
                    }
                ],
            }
        ],
    }


def test_plan_flags_schema_and_renames(tmp_path: Path) -> None:
    seed = _v3_1_seed()
    _write_json(tmp_path / "project.seed.json", seed)
    plan = plan_migration(tmp_path)
    assert any("schema_version" in c for c in plan.seed_changes)
    assert any("samvil_tier" in c for c in plan.seed_changes)
    # backup path present
    assert any(BACKUP_FILENAME in b for b in plan.backups)


def test_plan_idempotent_when_already_v3_2(tmp_path: Path) -> None:
    seed = _v3_1_seed()
    new_seed, _ = _migrate_seed_dict(seed)
    _write_json(tmp_path / "project.seed.json", new_seed)
    plan = plan_migration(tmp_path)
    # Second pass has no AC/schema changes.
    assert plan.seed_changes == []


def test_apply_writes_backup_and_migrates(tmp_path: Path) -> None:
    seed = _v3_1_seed()
    _write_json(tmp_path / "project.seed.json", seed)
    plan = apply_migration(tmp_path, dry_run=False)
    assert not plan.dry_run

    # Backup exists with old content.
    backup = (tmp_path / BACKUP_FILENAME).read_text()
    assert "3.1" in backup

    # Seed is now v3.2.
    migrated = json.loads((tmp_path / "project.seed.json").read_text())
    assert migrated["schema_version"] == V32_SCHEMA_VERSION
    assert "samvil_tier" in migrated
    assert "agent_tier" not in migrated  # glossary-allow: verify removal

    # 12 inferred AC fields backfilled.
    leaf = migrated["features"][0]["acceptance_criteria"][0]
    for field in ("description", "risk_level", "model_tier_hint", "status", "evidence"):  # glossary-allow: schema field list
        assert field in leaf
    assert leaf["needs_review"] is True

    # .samvil/ artifacts created.
    assert (tmp_path / ".samvil" / "claims.jsonl").exists()
    assert (tmp_path / ".samvil" / "model_profiles.yaml").exists()

    # Rollback manifest exists.
    rb = tmp_path / ".samvil" / "rollback" / "v3_2_0" / "manifest.json"
    assert rb.exists()


def test_apply_is_idempotent(tmp_path: Path) -> None:
    seed = _v3_1_seed()
    _write_json(tmp_path / "project.seed.json", seed)
    apply_migration(tmp_path, dry_run=False)
    before = (tmp_path / "project.seed.json").read_text()
    apply_migration(tmp_path, dry_run=False)
    after = (tmp_path / "project.seed.json").read_text()
    # The `needs_review: true` flag is deterministic, so re-running
    # does not change the file content.
    assert before == after


def test_dry_run_makes_no_changes(tmp_path: Path) -> None:
    seed = _v3_1_seed()
    _write_json(tmp_path / "project.seed.json", seed)
    plan = apply_migration(tmp_path, dry_run=True)
    assert plan.dry_run

    # Seed unchanged, backup not written, .samvil not created.
    current = json.loads((tmp_path / "project.seed.json").read_text())
    assert current["schema_version"] == "3.1"
    assert not (tmp_path / BACKUP_FILENAME).exists()
    assert not (tmp_path / ".samvil").exists()


def test_council_files_imported_as_observations(tmp_path: Path) -> None:
    _write_json(tmp_path / "project.seed.json", _v3_1_seed())
    council = tmp_path / ".samvil" / "council"
    council.mkdir(parents=True)
    (council / "round1.md").write_text("# R1 notes")

    apply_migration(tmp_path, dry_run=False)

    imported = tmp_path / ".samvil" / "retro" / "imported-from-v3_1.yaml"
    assert imported.exists()
    # The file should reference round1 at minimum.
    assert "round1" in imported.read_text()
