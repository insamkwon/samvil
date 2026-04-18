"""Tests for v2.4.0 additions to interview_engine.py.

Covers:
  - Milestone matching (INITIAL/PROGRESS/REFINED/READY)
  - Component floors
  - missing_items extraction
  - update_streak (Rhythm Guard)
  - Tracks management (Breadth-Keeper)
"""

import pytest

from samvil_mcp.interview_engine import (
    score_ambiguity,
    update_streak,
    initialize_tracks,
    update_track,
    mark_track_resolved,
    should_force_breadth,
    MAX_AI_STREAK,
    MAX_ROUNDS_ON_SAME_TRACK,
)


# ── Milestone tests ────────────────────────────────────────────


def test_milestone_ready_on_clear_interview():
    """Well-defined interview should reach READY milestone."""
    state = {
        "target_user": "Freelance designers managing multiple client projects",
        "core_problem": "They lose track of deadlines across projects",
        "core_experience": "See all deadlines on a kanban board",
        "features": ["task-crud", "kanban-view", "deadline-alerts"],
        "exclusions": ["real-time collab", "file attachments"],
        "constraints": ["localStorage only", "mobile responsive"],
        "acceptance_criteria": [
            "User creates task with title and deadline",
            "User drags tasks between columns",
            "Tasks persist after refresh",
            "Overdue tasks show red indicator",
        ],
    }
    result = score_ambiguity(state)
    assert result["milestone"]["name"] == "READY"


def test_milestone_initial_on_empty():
    """Empty state should be INITIAL milestone."""
    result = score_ambiguity({})
    assert result["milestone"]["name"] == "INITIAL"


def test_milestone_shape():
    """Milestone should have name, max_score, description."""
    result = score_ambiguity({})
    m = result["milestone"]
    assert "name" in m
    assert "max_score" in m
    assert "description" in m
    assert m["max_score"] > 0


# ── Component floor tests ──────────────────────────────────────


def test_floors_pass_on_well_defined():
    """Well-defined interview passes all floors."""
    state = {
        "target_user": "Freelance designers managing multiple client projects",
        "core_problem": "They lose track of deadlines across projects",
        "core_experience": "See all deadlines on a kanban board",
        "features": ["task-crud", "kanban-view", "deadline-alerts"],
        "exclusions": ["real-time collab", "file attachments"],
        "constraints": ["localStorage only", "mobile responsive"],
        "acceptance_criteria": [
            "User creates task with title and deadline",
            "User drags tasks between columns",
            "Tasks persist after refresh",
            "Overdue tasks show red indicator",
        ],
    }
    result = score_ambiguity(state)
    assert result["floors_passed"] is True
    assert result["floor_violations"] == []


def test_floors_violated_on_empty():
    """Empty state should have floor violations."""
    result = score_ambiguity({})
    assert result["floors_passed"] is False
    assert len(result["floor_violations"]) > 0


def test_converged_requires_floors_passed():
    """Converged = ambiguity ≤ target AND floors passed."""
    # Interview with good overall score but one weak dimension
    state = {
        "target_user": "Freelance designers managing multiple client projects",
        "core_problem": "They lose track of deadlines across projects",
        "core_experience": "See all deadlines on a kanban board",
        # All features mentioned but no exclusions → constraint_clarity will drop
        "features": ["task-crud", "kanban-view"],
        "exclusions": [],  # Empty — penalty
        "constraints": [],
        "acceptance_criteria": [
            "User creates task",
            "User views list",
            "Tasks persist",
        ],
    }
    result = score_ambiguity(state)
    # Even if overall is close to target, floors might block
    if not result["floors_passed"]:
        assert result["converged"] is False


# ── missing_items tests ────────────────────────────────────────


def test_missing_items_empty_state():
    """Empty state should list all missing fields."""
    result = score_ambiguity({})
    missing = result["missing_items"]
    assert "target_user" in missing
    assert "core_problem" in missing
    assert "features (must-have list)" in missing
    assert any("acceptance_criteria" in m for m in missing)


def test_missing_items_partial():
    """Partial state should list only missing."""
    state = {
        "target_user": "Designers",
        "core_problem": "Deadline tracking",
        "core_experience": "Kanban board",
        "features": ["crud"],
        # missing: exclusions, constraints, acceptance_criteria
    }
    result = score_ambiguity(state)
    missing = result["missing_items"]
    assert "target_user" not in missing
    assert "exclusions (out-of-scope)" in missing


def test_missing_items_ac_count_hint():
    """Fewer than 3 ACs should be flagged."""
    state = {
        "target_user": "Users",
        "core_problem": "P",
        "core_experience": "E",
        "features": ["f"],
        "exclusions": ["x"],
        "constraints": ["c"],
        "acceptance_criteria": ["only one"],
    }
    result = score_ambiguity(state)
    assert any("need at least 3" in m for m in result["missing_items"])


# ── update_streak (Rhythm Guard) tests ─────────────────────────


def test_streak_from_user_resets():
    """User answers reset streak to 0."""
    result = update_streak(current_streak=2, answer_source="from-user")
    assert result["new_streak"] == 0
    assert result["force_user_next"] is False


def test_streak_from_code_increments():
    """Code answers increment streak."""
    result = update_streak(current_streak=1, answer_source="from-code")
    assert result["new_streak"] == 2
    assert result["force_user_next"] is False


def test_streak_triggers_rhythm_guard_at_3():
    """3 consecutive AI answers triggers force_user_next."""
    result = update_streak(current_streak=2, answer_source="from-code-auto")
    assert result["new_streak"] == 3
    assert result["force_user_next"] is True
    assert "Rhythm Guard" in result["reason"]


def test_streak_from_research_increments():
    """Research answers count as AI-answered."""
    result = update_streak(current_streak=2, answer_source="from-research")
    assert result["new_streak"] == 3
    assert result["force_user_next"] is True


def test_streak_user_correction_resets():
    """User corrections also reset streak."""
    result = update_streak(current_streak=5, answer_source="from-user-correction")
    assert result["new_streak"] == 0
    assert result["force_user_next"] is False


# ── Tracks (Breadth-Keeper) tests ──────────────────────────────


def test_initialize_tracks():
    """Create tracks from feature list."""
    tracks = initialize_tracks(["auth", "payment", "admin"])
    assert len(tracks) == 3
    assert tracks[0]["name"] == "auth"
    assert tracks[0]["rounds_focused"] == 0
    assert tracks[0]["is_resolved"] is False


def test_update_track_increments():
    """Update a track → rounds_focused += 1."""
    tracks = initialize_tracks(["auth", "payment"])
    tracks = update_track(tracks, "auth")
    assert tracks[0]["rounds_focused"] == 1
    assert tracks[1]["rounds_focused"] == 0  # unchanged


def test_mark_track_resolved():
    """Resolving a track sets is_resolved=True."""
    tracks = initialize_tracks(["auth", "payment"])
    tracks = mark_track_resolved(tracks, "auth")
    assert tracks[0]["is_resolved"] is True
    assert tracks[1]["is_resolved"] is False


def test_should_force_breadth_not_triggered_initially():
    """Fresh tracks — no forcing."""
    tracks = initialize_tracks(["a", "b", "c"])
    result = should_force_breadth(tracks)
    assert result["force_breadth"] is False


def test_should_force_breadth_triggers_after_3_rounds():
    """3 rounds on same track with unresolved siblings → force breadth."""
    tracks = initialize_tracks(["a", "b"])
    for _ in range(3):
        tracks = update_track(tracks, "a")
    # tracks[0]['rounds_focused'] == 3, 'b' is unresolved
    result = should_force_breadth(tracks)
    assert result["force_breadth"] is True
    assert result["current_track"] == "a"
    assert "b" in result["unresolved_tracks"]


def test_should_force_breadth_skips_if_no_unresolved():
    """Even at 3 rounds, if all others resolved → no force."""
    tracks = initialize_tracks(["a", "b"])
    tracks = mark_track_resolved(tracks, "b")
    for _ in range(3):
        tracks = update_track(tracks, "a")
    result = should_force_breadth(tracks)
    # 'b' is resolved, so no unresolved siblings → no force
    assert result["force_breadth"] is False
