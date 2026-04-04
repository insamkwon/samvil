"""Tests for SAMVIL Interview Ambiguity Scoring."""

import pytest
from samvil_mcp.interview_engine import score_ambiguity


def test_fully_clear_interview():
    """Well-defined interview should converge (≤ 0.05)."""
    state = {
        "target_user": "Freelance designers who manage multiple client projects",
        "core_problem": "They lose track of deadlines across different projects",
        "core_experience": "See all deadlines on a single kanban board",
        "features": ["task-crud", "kanban-view", "deadline-alerts"],
        "exclusions": ["real-time collaboration", "file attachments", "invoicing"],
        "constraints": ["No backend — localStorage only", "Mobile responsive"],
        "acceptance_criteria": [
            "User can create a task with title and deadline",
            "User can drag tasks between kanban columns",
            "Tasks persist after page refresh",
            "Overdue tasks show a red indicator",
        ],
    }
    result = score_ambiguity(state)
    assert result["converged"] is True
    assert result["ambiguity"] <= 0.05


def test_empty_interview():
    """Empty interview should be maximally ambiguous."""
    state = {}
    result = score_ambiguity(state)
    assert result["converged"] is False
    assert result["ambiguity"] > 0.5


def test_vague_target_user():
    """Vague target user should increase goal ambiguity."""
    state = {
        "target_user": "everyone",
        "core_problem": "They need a tool",
        "core_experience": "Use the app",
        "features": ["feature-a"],
        "exclusions": ["nothing"],
        "constraints": [],
        "acceptance_criteria": ["It works"],
    }
    result = score_ambiguity(state)
    assert result["goal_clarity"] <= 0.8  # Not very clear


def test_untestable_criteria():
    """Vague acceptance criteria should lower testability score."""
    state = {
        "target_user": "Project managers at agencies with 10+ clients",
        "core_problem": "They can't see project status at a glance",
        "core_experience": "View project dashboard with health indicators",
        "features": ["dashboard", "project-status"],
        "exclusions": ["invoicing"],
        "constraints": ["Web only"],
        "acceptance_criteria": [
            "App looks nice and professional",
            "Dashboard is user-friendly and intuitive",
            "Everything works smooth",
        ],
    }
    result = score_ambiguity(state)
    assert result["criteria_testability"] < 0.7  # Vague criteria detected


def test_too_many_features():
    """8+ features should increase constraint ambiguity."""
    state = {
        "target_user": "Small business owners managing inventory",
        "core_problem": "Manual inventory tracking is error-prone",
        "core_experience": "Scan a barcode to add/remove inventory",
        "features": ["scan", "crud", "search", "export", "import", "analytics", "auth", "notifications"],
        "exclusions": ["POS integration"],
        "constraints": ["Mobile first"],
        "acceptance_criteria": [
            "User can scan barcode to add item",
            "Inventory count updates in real-time",
            "User can export to CSV",
        ],
    }
    result = score_ambiguity(state)
    # 8 features should penalize
    assert result["constraint_clarity"] < 0.9


def test_contradiction_detected():
    """Feature in both features and exclusions should penalize."""
    state = {
        "target_user": "Students tracking study habits",
        "core_problem": "No way to see study patterns over time",
        "core_experience": "Log study session with one tap",
        "features": ["logging", "analytics", "auth"],
        "exclusions": ["analytics"],  # Contradiction!
        "constraints": ["No backend"],
        "acceptance_criteria": [
            "User can log a study session",
            "User can view weekly summary chart",
        ],
    }
    result = score_ambiguity(state)
    assert result["constraint_clarity"] < 0.8  # Contradiction penalized
