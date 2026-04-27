"""Tests for seed_manager: schema validation and comparison."""

import pytest
from samvil_mcp.seed_manager import validate_seed, validate_state, compare_seeds, check_convergence


# ── validate_seed ──────────────────────────────────────────────


def test_valid_seed():
    seed = {
        "name": "my-app",
        "description": "A simple task management application",
        "solution_type": "web-app",
        "mode": "web",
        "tech_stack": {"framework": "nextjs", "ui": "tailwind"},
        "core_experience": {
            "description": "User creates and completes a task within 30 seconds",
            "primary_screen": "TaskList",
            "key_interactions": ["create-task", "complete-task"],
        },
        "features": [
            {"name": "task-crud", "priority": 1, "independent": True, "depends_on": None},
        ],
        "acceptance_criteria": ["User can create a task and see it in the list"],
        "constraints": ["Must work offline"],
        "out_of_scope": ["User authentication"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is True
    assert result["errors"] == []


def test_missing_required_fields():
    seed = {"name": "my-app"}
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("description" in e for e in result["errors"])


def test_invalid_name_format():
    seed = {
        "name": "My App!",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [{"name": "feat1", "priority": 1}],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("kebab-case" in e for e in result["errors"])


def test_invalid_framework():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "django"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [{"name": "feat1", "priority": 1}],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("framework" in e for e in result["errors"])


def test_empty_features():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("features" in e for e in result["errors"])


def test_depends_on_nonexistent_feature():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [
            {"name": "feat1", "priority": 1, "independent": False, "depends_on": "nonexistent"},
        ],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("non-existent" in e for e in result["errors"])


# ── validate_state ──────────────────────────────────────────────


def test_valid_state():
    state = {"seed_version": 1, "current_stage": "build"}
    result = validate_state(state)
    assert result["valid"] is True


def test_missing_stage():
    state = {"seed_version": 1}
    result = validate_state(state)
    assert result["valid"] is False


def test_invalid_stage():
    state = {"seed_version": 1, "current_stage": "unknown"}
    result = validate_state(state)
    assert result["valid"] is False


# ── compare_seeds (existing, sanity check) ──────────────────────


def test_identical_seeds():
    seed = {"name": "a", "version": 1}
    result = compare_seeds(seed, seed)
    assert result["similarity"] == 1.0
    assert result["converged"] is True


# ── merge_brownfield_seed (v2.6.0) ─────────────────────────────

from samvil_mcp.seed_manager import merge_brownfield_seed


def _existing_brownfield_seed():
    return {
        "name": "todo-app",
        "description": "A basic todo app",
        "solution_type": "web-app",
        "schema_version": "3.0",
        "version": 1,
        "tech_stack": {"framework": "nextjs", "ui": "tailwind"},
        "core_experience": {"description": "Manage tasks"},
        "target_user": "Users",
        "core_problem": "Need to track tasks",
        "features": [
            {"name": "task-create", "description": "Create tasks", "status": "existing",
             "acceptance_criteria": []},
            {"name": "task-list", "description": "List tasks", "status": "existing",
             "acceptance_criteria": []},
        ],
        "constraints": ["localStorage only"],
        "out_of_scope": [],
        "acceptance_criteria": [],
    }


def _interview_state():
    return {
        "target_user": "Freelance developers managing 5+ client projects simultaneously",
        "core_problem": "They lose track of deadlines and project context when switching clients",
        "core_experience": "Dashboard showing all projects with upcoming deadlines",
        "features": ["deadline-alerts", "project-grouping"],
        "exclusions": ["real-time collaboration", "file attachments", "invoicing"],
        "constraints": ["Mobile responsive", "No PII stored"],
        "acceptance_criteria": [
            "User sees all deadlines on one screen within 1 second",
            "Overdue tasks show red indicator",
        ],
    }


def test_merge_preserves_existing_features():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    names = [f["name"] for f in merged["features"]]
    assert "task-create" in names
    assert "task-list" in names


def test_merge_adds_new_features():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    names = [f["name"] for f in merged["features"]]
    assert "deadline-alerts" in names
    assert "project-grouping" in names


def test_merge_existing_features_keep_status():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    existing = [f for f in merged["features"] if f["name"] in ("task-create", "task-list")]
    for f in existing:
        assert f["status"] == "existing"


def test_merge_new_features_have_new_status():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    new_feats = [f for f in merged["features"] if f["name"] in ("deadline-alerts", "project-grouping")]
    for f in new_feats:
        assert f["status"] == "new"


def test_merge_no_duplicate_features():
    """If a feature from interview already exists, it should not be duplicated."""
    existing = _existing_brownfield_seed()
    iv = _interview_state()
    iv["features"] = ["task-create", "deadline-alerts"]  # task-create already exists
    merged = merge_brownfield_seed(existing, iv)
    names = [f["name"] for f in merged["features"]]
    assert names.count("task-create") == 1


def test_merge_updates_metadata_when_interview_more_specific():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "Freelance developers" in merged["target_user"]
    assert "deadlines" in merged["core_problem"]


def test_merge_keeps_existing_tech_stack():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert merged["tech_stack"]["framework"] == "nextjs"


def test_merge_unions_constraints():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "localStorage only" in merged["constraints"]
    assert "Mobile responsive" in merged["constraints"]


def test_merge_uses_interview_exclusions():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "real-time collaboration" in merged["out_of_scope"]


def test_merge_sets_analysis_source():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert merged["_analysis_source"] == "brownfield"


def test_merge_explicit_new_features_override_interview():
    explicit = [{"name": "gantt-chart", "description": "Gantt chart view"}]
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state(),
                                   new_features=explicit)
    names = [f["name"] for f in merged["features"]]
    assert "gantt-chart" in names
    # interview features should NOT be added when explicit list given
    assert "deadline-alerts" not in names
