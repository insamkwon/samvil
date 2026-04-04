"""Tests for SAMVIL seed management and evolve loop."""

import pytest
from samvil_mcp.seed_manager import compare_seeds, check_convergence
from samvil_mcp.evolve_loop import validate_evolved_seed, generate_evolve_context


SEED_V1 = {
    "name": "task-app",
    "description": "Simple task management",
    "mode": "web",
    "tech_stack": {"framework": "next-14", "ui": "tailwind"},
    "core_experience": {"description": "Create tasks", "primary_screen": "TaskBoard"},
    "features": [
        {"name": "task-crud", "priority": 1, "independent": True},
        {"name": "kanban", "priority": 1, "independent": False},
    ],
    "acceptance_criteria": ["User can create tasks", "User can drag tasks"],
    "constraints": ["No backend"],
    "out_of_scope": ["real-time"],
    "version": 1,
}


def _make_seed_v2():
    v2 = {**SEED_V1, "version": 2}
    v2["acceptance_criteria"] = SEED_V1["acceptance_criteria"] + ["Tasks persist on refresh"]
    return v2


# ── compare_seeds ──


def test_identical_seeds():
    result = compare_seeds(SEED_V1, SEED_V1)
    assert result["similarity"] == 1.0
    assert result["converged"] is True
    assert result["changes"] == []


def test_different_seeds():
    v2 = _make_seed_v2()
    result = compare_seeds(SEED_V1, v2)
    assert result["similarity"] < 1.0
    assert len(result["changes"]) > 0


def test_minor_change_high_similarity():
    v2 = {**SEED_V1, "version": 2, "description": "Simple task management app"}
    result = compare_seeds(SEED_V1, v2)
    assert result["similarity"] > 0.8  # Most fields identical


# ── check_convergence ──


def test_convergence_needs_2_versions():
    result = check_convergence([SEED_V1])
    assert result["converged"] is False
    assert "Need at least 2" in result["reason"]


def test_convergence_identical_pair():
    result = check_convergence([SEED_V1, SEED_V1])
    assert result["converged"] is True
    assert result["similarity"] == 1.0


def test_convergence_with_trend():
    v2 = _make_seed_v2()
    v3 = {**v2, "version": 3}  # Same as v2 = converging
    result = check_convergence([SEED_V1, v2, v3])
    assert result["trend"] in ("converging", "stable")
    assert result["generations"] == 3


# ── validate_evolved_seed ──


def test_valid_evolution():
    v2 = _make_seed_v2()
    result = validate_evolved_seed(SEED_V1, v2)
    assert result["valid"] is True
    assert result["issues"] == []


def test_name_change_rejected():
    v2 = {**_make_seed_v2(), "name": "different-name"}
    result = validate_evolved_seed(SEED_V1, v2)
    assert result["valid"] is False
    assert any("name changed" in i for i in result["issues"])


def test_too_many_features_rejected():
    v2 = _make_seed_v2()
    v2["features"] = SEED_V1["features"] + [
        {"name": "a", "priority": 2},
        {"name": "b", "priority": 2},
        {"name": "c", "priority": 2},
    ]
    result = validate_evolved_seed(SEED_V1, v2)
    assert result["valid"] is False
    assert any("Too many" in i for i in result["issues"])


def test_version_must_increment():
    v2 = {**_make_seed_v2(), "version": 5}
    result = validate_evolved_seed(SEED_V1, v2)
    assert result["valid"] is False
    assert any("version should be 2" in i for i in result["issues"])


# ── generate_evolve_context ──


def test_evolve_context_basic():
    qa = {"verdict": "REVISE", "issues": ["drag not working"]}
    context = generate_evolve_context(SEED_V1, qa)
    assert context["version"] == 1
    assert context["current_seed"] == SEED_V1
    assert context["qa_result"] == qa


def test_evolve_context_with_history():
    v2 = _make_seed_v2()
    qa = {"verdict": "PASS"}
    context = generate_evolve_context(v2, qa, [SEED_V1, v2])
    assert "convergence" in context
    assert context["convergence"]["generations"] == 2
