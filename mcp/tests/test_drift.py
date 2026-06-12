"""Tests for seed drift measurement (v4.30 W5.2)."""

from __future__ import annotations

import asyncio
import json

from samvil_mcp.drift import measure_drift
from samvil_mcp.server import measure_seed_drift


def _seed(description: str, constraints: list[str], features: list[dict]) -> dict:
    return {
        "description": description,
        "constraints": constraints,
        "features": features,
    }


def test_identical_seed_zero_drift() -> None:
    seed = _seed(
        "할일 관리 앱 with deadline alerts",
        ["no backend", "localStorage only"],
        [{"name": "todo-list", "acceptance_criteria": ["사용자가 할일을 추가할 수 있다"]}],
    )
    result = measure_drift(seed, seed)
    assert result["total_drift"] == 0.0
    assert result["verdict"] == "ok"


def test_complete_rewrite_is_excessive() -> None:
    original = _seed(
        "todo list app for personal tasks",
        ["offline first"],
        [{"name": "todo-list", "acceptance_criteria": ["add a task"]}],
    )
    pivoted = _seed(
        "realtime multiplayer poker game",
        ["websocket server required"],
        [{"name": "poker-table", "acceptance_criteria": ["deal cards to players"]}],
    )
    result = measure_drift(original, pivoted)
    assert result["verdict"] == "excessive"
    assert result["total_drift"] >= 0.6
    assert result["goal_drift"] > 0.8


def test_feature_addition_is_moderate() -> None:
    original = _seed(
        "todo list app for personal tasks with deadline alerts",
        ["offline first", "no login"],
        [{"name": "todo-list", "acceptance_criteria": ["add a task", "complete a task"]}],
    )
    grown = _seed(
        "todo list app for personal tasks with deadline alerts",
        ["offline first", "no login"],
        [
            {"name": "todo-list", "acceptance_criteria": ["add a task", "complete a task"]},
            {"name": "todo-stats", "acceptance_criteria": ["show completion rate"]},
        ],
    )
    result = measure_drift(original, grown)
    assert result["goal_drift"] == 0.0
    assert result["constraint_drift"] == 0.0
    assert 0 < result["ontology_drift"] < 1
    assert result["verdict"] == "ok"


def test_empty_constraints_no_drift() -> None:
    a = _seed("an app", [], [])
    result = measure_drift(a, a)
    assert result["constraint_drift"] == 0.0


def test_weights_sum_to_one() -> None:
    from samvil_mcp.drift import CONSTRAINT_WEIGHT, GOAL_WEIGHT, ONTOLOGY_WEIGHT

    assert GOAL_WEIGHT + CONSTRAINT_WEIGHT + ONTOLOGY_WEIGHT == 1.0


def test_mcp_tool_roundtrip() -> None:
    a = json.dumps(_seed("todo app", ["offline"], []))
    b = json.dumps(_seed("poker game", ["server"], []))
    result = json.loads(asyncio.run(measure_seed_drift(a, b)))
    assert result["verdict"] in {"ok", "warning", "excessive"}
    assert "total_drift" in result


def test_mcp_tool_invalid_json_is_error() -> None:
    result = json.loads(asyncio.run(measure_seed_drift("not json", "{}")))
    assert result["verdict"] == "error"
