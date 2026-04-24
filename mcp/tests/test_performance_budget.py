"""Unit tests for performance_budget (Sprint 6, ⑬)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.performance_budget import (
    DEFAULT_BUDGET,
    BudgetStatus,
    Consumption,
    ceiling_for_tier,
    evaluate_status,
    load_budget,
)


def test_default_budget_shape() -> None:
    assert "per_run" in DEFAULT_BUDGET
    assert "enforcement" in DEFAULT_BUDGET


def test_ceiling_for_tier_matches_defaults() -> None:
    c = ceiling_for_tier(DEFAULT_BUDGET, "standard")
    assert c["wall_time_minutes"] == 40
    assert c["llm_calls"] == 150
    assert c["estimated_cost_usd"] == 2


def test_load_budget_fallback(tmp_path: Path) -> None:
    b = load_budget(tmp_path / "nope.yaml")
    assert b == DEFAULT_BUDGET


def test_evaluate_status_pass() -> None:
    c = Consumption(wall_time_minutes=10, llm_calls=50, estimated_cost_usd=0.5)
    s = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="standard",
        consumed=c,
    )
    assert not s.hard_stop
    assert s.warnings == []


def test_evaluate_status_warn_at_80() -> None:
    # standard: wall_time 40min, 80% = 32min
    c = Consumption(wall_time_minutes=32, llm_calls=50, estimated_cost_usd=0.5)
    s = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="standard",
        consumed=c,
    )
    assert any("wall_time_minutes" in w for w in s.warnings)
    assert not s.hard_stop


def test_evaluate_status_hard_stop() -> None:
    # standard: llm_calls 150, hard_stop 150% = 225
    c = Consumption(wall_time_minutes=10, llm_calls=300, estimated_cost_usd=0.5)
    s = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="standard",
        consumed=c,
    )
    assert s.hard_stop
    assert any("llm_calls" in w for w in s.warnings)


def test_consensus_exemption_reduces_ratio() -> None:
    c = Consumption(wall_time_minutes=35, llm_calls=50, estimated_cost_usd=0.5)
    consensus = Consumption(wall_time_minutes=10)
    s_no_exempt = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="standard",
        consumed=c,
        exempt_consensus=False,
    )
    s_exempt = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="standard",
        consumed=c,
        exempt_consensus=True,
        consensus_cost=consensus,
    )
    assert (
        s_exempt.ratios["wall_time_minutes"]
        < s_no_exempt.ratios["wall_time_minutes"]
    )


def test_unknown_tier_yields_empty_ceiling() -> None:
    c = Consumption(wall_time_minutes=10, llm_calls=1, estimated_cost_usd=0.1)
    s = evaluate_status(
        budget=DEFAULT_BUDGET,
        samvil_tier="nonexistent",
        consumed=c,
    )
    assert s.ratios == {
        "wall_time_minutes": 0.0,
        "llm_calls": 0.0,
        "estimated_cost_usd": 0.0,
    }
