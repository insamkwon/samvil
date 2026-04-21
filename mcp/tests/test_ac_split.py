"""v3-011: tests for AC split heuristic."""
from __future__ import annotations

from samvil_mcp.ac_split import should_split


def test_short_description_should_not_split() -> None:
    result = should_split("User can add tasks")
    assert result["should_split"] is False
    assert "too_short" in result["reasons"]


def test_compound_and_triggers_split() -> None:
    desc = (
        "User can create a task with a title and description, edit it later, "
        "and delete it from the list"
    )
    result = should_split(desc)
    assert result["should_split"] is True
    assert any("compound_connectors" in r for r in result["reasons"])


def test_multi_verb_triggers_split() -> None:
    desc = "Authenticated user can create, edit, and delete their own saved workouts"
    result = should_split(desc)
    assert result["should_split"] is True


def test_many_commas_triggers_split() -> None:
    desc = "Dashboard shows daily revenue, weekly trend, user retention, churn rate, and growth"
    result = should_split(desc)
    assert result["should_split"] is True
    assert any("many_commas" in r for r in result["reasons"])


def test_suggested_children_are_split_parts() -> None:
    desc = "User can sign up and log in and reset password and delete account"
    result = should_split(desc)
    assert result["should_split"] is True
    assert result["suggested_children"] is not None
    assert len(result["suggested_children"]) >= 2


def test_korean_compound_triggers_split() -> None:
    desc = "사용자가 일정을 생성하고 편집할 수 있으며 또는 공유 링크로 다른 사람과 공유할 수 있다"
    result = should_split(desc)
    # Korean connectors ("그리고", "또는") should trigger
    assert result["should_split"] is True
