"""Tests for convergence_gate.py + regression_detector.py (v2.5.0, Phase 4)."""

import pytest

from samvil_mcp.convergence_gate import (
    check_all_gates,
    check_eval_gate,
    check_per_ac_gate,
    check_regression_gate,
    check_evolution_gate,
    check_validation_gate,
    GateConfig,
)
from samvil_mcp.regression_detector import detect_regressions, has_regressions


# ── Regression detector ──────────────────────────────────────


def test_no_regressions_fresh_history():
    current = {"AC-1": "PASS", "AC-2": "PASS"}
    regressions = detect_regressions(current, history=[])
    assert regressions == []


def test_no_regression_if_still_passing():
    history = [{"cycle": 1, "ac_states": {"AC-1": "PASS"}}]
    current = {"AC-1": "PASS"}
    regressions = detect_regressions(current, history)
    assert regressions == []


def test_regression_detected_pass_to_fail():
    history = [{"cycle": 1, "ac_states": {"AC-1": "PASS"}}]
    current = {"AC-1": "FAIL"}
    regressions = detect_regressions(current, history)
    assert len(regressions) == 1
    assert regressions[0].ac_id == "AC-1"
    assert regressions[0].last_pass_cycle == 1


def test_regression_detected_pass_to_partial():
    history = [{"cycle": 2, "ac_states": {"AC-2": "PASS"}}]
    current = {"AC-2": "PARTIAL"}
    regressions = detect_regressions(current, history)
    assert len(regressions) == 1


def test_no_regression_if_never_passed():
    history = [{"cycle": 1, "ac_states": {"AC-1": "FAIL"}}]
    current = {"AC-1": "FAIL"}
    regressions = detect_regressions(current, history)
    assert regressions == []


# ── Individual gates ──────────────────────────────────────────


def test_eval_gate_pass():
    result = check_eval_gate(
        {"score": 0.8, "final_approved": True},
        GateConfig(),
    )
    assert result["passed"] is True


def test_eval_gate_low_score():
    result = check_eval_gate({"score": 0.5, "final_approved": True}, GateConfig())
    assert result["passed"] is False


def test_eval_gate_not_approved():
    result = check_eval_gate({"score": 0.9, "final_approved": False}, GateConfig())
    assert result["passed"] is False


def test_per_ac_gate_all_pass():
    result = check_per_ac_gate(
        {"ac_states": {"AC-1": "PASS", "AC-2": "PASS"}},
        GateConfig(ac_gate_mode="all"),
    )
    assert result["passed"] is True


def test_per_ac_gate_any_fail_blocks():
    result = check_per_ac_gate(
        {"ac_states": {"AC-1": "PASS", "AC-2": "FAIL"}},
        GateConfig(ac_gate_mode="all"),
    )
    assert result["passed"] is False
    assert "AC-2" in result["failed_acs"]


def test_per_ac_gate_majority_mode():
    result = check_per_ac_gate(
        {"ac_states": {"AC-1": "PASS", "AC-2": "PASS", "AC-3": "FAIL"}},
        GateConfig(ac_gate_mode="majority"),
    )
    # 2/3 pass = majority, so allowed
    assert result["passed"] is True


def test_evolution_gate_blocks_stagnant():
    result = check_evolution_gate(
        [{"cycle": 1, "mutations": []}, {"cycle": 2, "mutations": []}],
        GateConfig(),
    )
    assert result["passed"] is False
    assert "stagnant" in result["reason"].lower()


def test_evolution_gate_allows_evolved():
    result = check_evolution_gate(
        [{"cycle": 1, "mutations": ["m1"]}, {"cycle": 2, "mutations": ["m2"]}],
        GateConfig(),
    )
    assert result["passed"] is True


def test_validation_gate_skipped_blocks():
    result = check_validation_gate({"validation_status": "skipped"}, GateConfig())
    assert result["passed"] is False


def test_validation_gate_error_blocks():
    result = check_validation_gate({"validation_status": "error"}, GateConfig())
    assert result["passed"] is False


def test_validation_gate_ok_passes():
    result = check_validation_gate({"validation_status": "ok"}, GateConfig())
    assert result["passed"] is True


# ── check_all_gates integration ───────────────────────────────


def test_converged_when_all_pass():
    eval_result = {
        "score": 0.9,
        "final_approved": True,
        "ac_states": {"AC-1": "PASS", "AC-2": "PASS"},
        "validation_status": "ok",
    }
    history = [{"cycle": 1, "ac_states": {"AC-1": "PASS"}, "mutations": ["m1"]}]
    verdict = check_all_gates(eval_result, history)
    assert verdict.converged is True
    assert verdict.blocked_by == ()


def test_blocked_by_regression():
    eval_result = {
        "score": 0.9,
        "final_approved": True,
        "ac_states": {"AC-1": "FAIL"},  # Was PASS, now FAIL
        "validation_status": "ok",
    }
    history = [{"cycle": 1, "ac_states": {"AC-1": "PASS"}, "mutations": ["m1"]}]
    verdict = check_all_gates(eval_result, history)
    assert verdict.converged is False
    assert "regression" in verdict.blocked_by
    assert "per_ac" in verdict.blocked_by  # also blocks per-AC


def test_blocked_by_stagnant():
    eval_result = {
        "score": 0.9,
        "final_approved": True,
        "ac_states": {"AC-1": "PASS"},
        "validation_status": "ok",
    }
    history = [{"cycle": 1, "ac_states": {"AC-1": "PASS"}, "mutations": []}]  # no mutations
    verdict = check_all_gates(eval_result, history)
    assert verdict.converged is False
    assert "evolution" in verdict.blocked_by


def test_blocked_by_multiple_gates():
    eval_result = {
        "score": 0.4,  # below threshold
        "final_approved": False,
        "ac_states": {"AC-1": "FAIL"},
        "validation_status": "error",
    }
    history = []
    verdict = check_all_gates(eval_result, history)
    assert verdict.converged is False
    # All gates should block: eval, per_ac, evolution, validation
    assert len(verdict.blocked_by) >= 3
