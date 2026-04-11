"""Tests for seed_manager: schema validation and comparison."""

import pytest
from samvil_mcp.seed_manager import validate_seed, validate_state, compare_seeds, check_convergence


# ── validate_seed ──────────────────────────────────────────────


def test_valid_seed():
    seed = {
        "name": "my-app",
        "description": "A simple task management application",
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
