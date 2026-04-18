"""Tests for v3.0.0 T4 PM seed conversion."""

import pytest

from samvil_mcp.pm_seed import pm_seed_to_eng_seed, validate_pm_seed


def _valid_pm_seed() -> dict:
    return {
        "name": "habit",
        "vision": "accountability for remote workers",
        "users": [
            {"segment": "remote workers", "pain_points": ["no peers"]}
        ],
        "metrics": [{"name": "D7", "target": ">=40%"}],
        "epics": [
            {
                "id": "E1",
                "title": "Habit CRUD",
                "tasks": [
                    {
                        "id": "T1.1",
                        "description": "Add habit",
                        "acceptance_criteria": [
                            {"id": "AC-1.1.1", "description": "validate", "children": []},
                        ],
                    }
                ],
            }
        ],
    }


def test_validate_accepts_valid_pm_seed():
    assert validate_pm_seed(_valid_pm_seed()) == []


def test_validate_rejects_missing_name():
    seed = _valid_pm_seed()
    del seed["name"]
    errors = validate_pm_seed(seed)
    assert any("name" in e for e in errors)


def test_validate_rejects_empty_epics():
    seed = _valid_pm_seed()
    seed["epics"] = []
    errors = validate_pm_seed(seed)
    assert errors


def test_validate_rejects_duplicate_task_ids():
    seed = _valid_pm_seed()
    seed["epics"][0]["tasks"].append({
        "id": "T1.1",
        "description": "dup",
        "acceptance_criteria": [{"id": "X", "description": "x"}],
    })
    errors = validate_pm_seed(seed)
    assert any("duplicate task id" in e for e in errors)


def test_validate_rejects_task_without_acs():
    seed = _valid_pm_seed()
    seed["epics"][0]["tasks"][0]["acceptance_criteria"] = []
    errors = validate_pm_seed(seed)
    assert any("acceptance_criteria" in e for e in errors)


def test_convert_flattens_epics_into_features():
    eng = pm_seed_to_eng_seed(_valid_pm_seed())
    assert eng["schema_version"] == "3.0"
    assert len(eng["features"]) == 1
    feat = eng["features"][0]
    assert feat["name"] == "T1.1"
    assert "Habit CRUD" in feat["description"]
    assert feat["priority"] == 1
    assert feat["acceptance_criteria"][0]["id"] == "AC-1.1.1"


def test_convert_preserves_vision_users_metrics():
    eng = pm_seed_to_eng_seed(_valid_pm_seed())
    assert eng["vision"].startswith("accountability")
    assert eng["users"][0]["segment"] == "remote workers"
    assert eng["metrics"][0]["name"] == "D7"


def test_convert_rejects_invalid_seed():
    bad = _valid_pm_seed()
    bad["epics"][0]["tasks"][0]["acceptance_criteria"] = []
    with pytest.raises(ValueError):
        pm_seed_to_eng_seed(bad)


def test_convert_preserves_extra_root_fields():
    seed = _valid_pm_seed()
    seed["custom_field"] = "keep me"
    eng = pm_seed_to_eng_seed(seed)
    assert eng["custom_field"] == "keep me"


def test_convert_multiple_epics_tasks_ordered():
    seed = _valid_pm_seed()
    seed["epics"].append({
        "id": "E2",
        "title": "Auth",
        "tasks": [
            {"id": "T2.1", "description": "sign up",
             "acceptance_criteria": [{"id": "AC-2.1.1", "description": "x"}]},
            {"id": "T2.2", "description": "log in",
             "acceptance_criteria": [{"id": "AC-2.2.1", "description": "y"}]},
        ],
    })
    eng = pm_seed_to_eng_seed(seed)
    assert [f["name"] for f in eng["features"]] == ["T1.1", "T2.1", "T2.2"]
    assert all("/" in f["description"] for f in eng["features"])
