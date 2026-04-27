"""Tests for health_tiers module (M4 3-tier health)."""

import pytest

from samvil_mcp.health_tiers import (
    TierResult,
    classify_health,
    CRITICAL_TOOLS,
    HEALTHY_THRESHOLD,
    CRITICAL_THRESHOLD,
)


class TestClassifyHealth:
    def test_empty_entries_returns_healthy(self):
        result = classify_health([])
        assert result.tier == "healthy"
        assert result.total_calls == 0

    def test_all_ok_returns_healthy(self):
        entries = [{"status": "ok", "tool": f"tool_{i}"} for i in range(20)]
        result = classify_health(entries)
        assert result.tier == "healthy"
        assert result.fail_rate == 0.0
        assert result.ok_count == 20

    def test_low_fail_rate_healthy(self):
        entries = [{"status": "ok", "tool": "t"}] * 95 + [{"status": "fail", "tool": "t"}] * 5
        result = classify_health(entries)
        assert result.tier == "healthy"
        assert result.fail_rate == 0.05

    def test_medium_fail_rate_degraded(self):
        entries = [{"status": "ok", "tool": "t"}] * 85 + [{"status": "fail", "tool": "t"}] * 15
        result = classify_health(entries)
        assert result.tier == "degraded"
        assert result.recommendation != ""

    def test_high_fail_rate_critical(self):
        entries = [{"status": "ok", "tool": "t"}] * 70 + [{"status": "fail", "tool": "t"}] * 30
        result = classify_health(entries)
        assert result.tier == "critical"
        assert result.fail_rate == 0.3

    def test_critical_tool_failure_is_critical(self):
        entries = [
            {"status": "ok", "tool": "other_tool"},
            {"status": "fail", "tool": "save_event"},
        ]
        result = classify_health(entries)
        assert result.tier == "critical"
        assert "save_event" in result.critical_failures

    def test_multiple_critical_failures(self):
        entries = [
            {"status": "ok", "tool": "t"},
            {"status": "fail", "tool": "save_event"},
            {"status": "fail", "tool": "validate_seed"},
        ]
        result = classify_health(entries)
        assert result.tier == "critical"
        assert len(result.critical_failures) == 2

    def test_degraded_tool_detection(self):
        # Overall fail rate must be < 20% to show degraded_tools
        entries = (
            [{"status": "ok", "tool": "good_tool"}] * 10
            + [{"status": "ok", "tool": "flaky_tool"}] * 1
            + [{"status": "fail", "tool": "flaky_tool"}] * 2
        )
        result = classify_health(entries)
        assert result.tier == "degraded"
        assert "flaky_tool" in result.degraded_tools

    def test_degraded_tool_needs_3_calls(self):
        entries = [
            {"status": "fail", "tool": "rare_tool"},
            {"status": "fail", "tool": "rare_tool"},
        ]
        result = classify_health(entries)
        assert "rare_tool" not in result.degraded_tools

    def test_to_dict(self):
        entries = [{"status": "ok", "tool": "t"}, {"status": "fail", "tool": "t"}]
        result = classify_health(entries)
        d = result.to_dict()
        assert "tier" in d
        assert "fail_rate" in d
        assert "recommendation" in d
        assert d["total_calls"] == 2


class TestCriticalTools:
    def test_critical_tools_set(self):
        assert "save_event" in CRITICAL_TOOLS
        assert "validate_seed" in CRITICAL_TOOLS
        assert "gate_check" in CRITICAL_TOOLS

    def test_thresholds(self):
        assert HEALTHY_THRESHOLD == 0.05
        assert CRITICAL_THRESHOLD == 0.20


class TestTierResult:
    def test_default_fields(self):
        r = TierResult(tier="healthy", fail_rate=0.0, total_calls=0, fail_count=0, ok_count=0)
        assert r.critical_failures == []
        assert r.degraded_tools == []
        assert r.recommendation == ""

    def test_recommendations_exist(self):
        # healthy
        r = classify_health([{"status": "ok", "tool": "t"}] * 10)
        assert r.recommendation != ""

        # degraded
        r = classify_health([{"status": "ok", "tool": "t"}] * 85 + [{"status": "fail", "tool": "t"}] * 15)
        assert "above normal" in r.recommendation

        # critical
        r = classify_health([{"status": "ok", "tool": "t"}] * 70 + [{"status": "fail", "tool": "t"}] * 30)
        assert "critical" in r.recommendation.lower()
