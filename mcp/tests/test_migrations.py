"""Tests for v3.0.0 T1.4 seed migration v2 → v3."""

import json
from pathlib import Path

import pytest

from samvil_mcp.migrations import migrate_seed_v2_to_v3, migrate_with_backup


def test_migrate_flat_strings_to_tree_leaves():
    v2 = {
        "features": [
            {"name": "auth", "acceptance_criteria": ["sign up", "log in"]}
        ]
    }
    v3 = migrate_seed_v2_to_v3(v2)
    acs = v3["features"][0]["acceptance_criteria"]
    assert isinstance(acs[0], dict)
    assert acs[0]["description"] == "sign up"
    assert acs[0]["children"] == []
    assert acs[0]["status"] == "pending"
    assert acs[0]["evidence"] == []
    assert acs[0]["id"] == "AC-auth-1"
    assert acs[1]["id"] == "AC-auth-2"


def test_migrate_sets_schema_version():
    v2 = {"features": []}
    v3 = migrate_seed_v2_to_v3(v2)
    assert v3["schema_version"] == "3.0"


def test_migrate_preserves_existing_dict_description():
    v2 = {
        "features": [{
            "name": "f1",
            "acceptance_criteria": [
                {"id": "AC-X", "description": "something", "status": "pass"},
            ],
        }]
    }
    v3 = migrate_seed_v2_to_v3(v2)
    ac = v3["features"][0]["acceptance_criteria"][0]
    assert ac["id"] == "AC-X"
    assert ac["status"] == "pass"
    assert ac["children"] == []
    assert ac["evidence"] == []


def test_migrate_converts_criterion_schema():
    v2 = {
        "features": [{
            "name": "f1",
            "acceptance_criteria": [
                {"criterion": "User logs in", "vague_words": ["fast"]},
            ],
        }]
    }
    v3 = migrate_seed_v2_to_v3(v2)
    ac = v3["features"][0]["acceptance_criteria"][0]
    assert ac["description"] == "User logs in"
    assert ac["vague_words"] == ["fast"]
    assert ac["children"] == []


def test_migrate_empty_features_list():
    v2 = {"features": []}
    v3 = migrate_seed_v2_to_v3(v2)
    assert v3["features"] == []
    assert v3["schema_version"] == "3.0"


def test_migrate_with_backup_creates_backup(tmp_path: Path):
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps({
        "features": [{"name": "f", "acceptance_criteria": ["a"]}]
    }))
    migrated = migrate_with_backup(str(seed_path))
    backup = seed_path.with_suffix(".v2.backup.json")
    assert backup.exists()
    assert migrated["schema_version"] == "3.0"
    on_disk = json.loads(seed_path.read_text())
    assert on_disk["schema_version"] == "3.0"
    assert on_disk["features"][0]["acceptance_criteria"][0]["description"] == "a"


def test_migrate_with_backup_idempotent_on_v3(tmp_path: Path):
    seed_path = tmp_path / "project.seed.json"
    original = {"schema_version": "3.0", "features": []}
    seed_path.write_text(json.dumps(original))
    result = migrate_with_backup(str(seed_path))
    assert result["schema_version"] == "3.0"
    # v3 seed → no backup created, file unchanged
    backup = seed_path.with_suffix(".v2.backup.json")
    assert not backup.exists(), "v3 seed should not produce a backup"
    assert json.loads(seed_path.read_text()) == original


def test_migrate_with_backup_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError):
        migrate_with_backup(str(missing))


def test_migrate_with_backup_does_not_overwrite_existing_backup(tmp_path: Path):
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps({
        "features": [{"name": "f", "acceptance_criteria": ["a"]}]
    }))
    backup_path = seed_path.with_suffix(".v2.backup.json")
    backup_path.write_text('{"existing": "backup"}')
    migrate_with_backup(str(seed_path))
    # existing backup preserved
    assert json.loads(backup_path.read_text()) == {"existing": "backup"}
