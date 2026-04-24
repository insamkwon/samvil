"""Unit tests for the gate framework (Sprint 1, ⑥)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.gates import (
    DEFAULT_CONFIG,
    ESCALATION_CHECKS,
    GateName,
    GateVerdict,
    Verdict,
    _required_action_for,
    _version_ge,
    gate_check,
    load_config,
    should_force_user_decision,
)


# ── Threshold math ─────────────────────────────────────────────────────


def test_build_to_qa_pass_above_floor() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.90},
    )
    assert v.verdict == Verdict.PASS.value


def test_build_to_qa_blocks_below_floor() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.70},
    )
    assert v.verdict == Verdict.BLOCK.value
    assert "implementation_rate" in v.failed_checks


def test_build_to_qa_exact_floor_is_pass() -> None:
    """0.85 is the standard floor — equality should pass, not block."""
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.85},
    )
    assert v.verdict == Verdict.PASS.value


def test_minimal_tier_has_lower_floor() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="minimal",
        metrics={"implementation_rate": 0.70},
    )
    assert v.verdict == Verdict.PASS.value


def test_deep_tier_has_higher_floor() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="deep",
        metrics={"implementation_rate": 0.96},
    )
    assert v.verdict == Verdict.BLOCK.value


# ── Skip + boolean thresholds ─────────────────────────────────────────


def test_council_to_design_skips_for_minimal() -> None:
    v = gate_check(
        GateName.COUNCIL_TO_DESIGN.value,
        samvil_tier="minimal",
        metrics={},
    )
    assert v.verdict == Verdict.SKIP.value


def test_council_to_design_requires_consensus_standard() -> None:
    v = gate_check(
        GateName.COUNCIL_TO_DESIGN.value,
        samvil_tier="standard",
        metrics={"consensus_required": True},
    )
    assert v.verdict == Verdict.PASS.value


def test_council_to_design_blocks_without_consensus() -> None:
    v = gate_check(
        GateName.COUNCIL_TO_DESIGN.value,
        samvil_tier="standard",
        metrics={"consensus_required": False},
    )
    assert v.verdict == Verdict.BLOCK.value


# ── Schema version comparison ─────────────────────────────────────────


def test_schema_version_ge_3_2() -> None:
    assert _version_ge("3.2", "3.2")
    assert _version_ge("3.2.1", "3.2")
    assert _version_ge("3.3", "3.2")
    assert not _version_ge("3.1", "3.2")
    assert not _version_ge("2.7", "3.2")


def test_seed_to_council_passes_with_valid_schema() -> None:
    v = gate_check(
        GateName.SEED_TO_COUNCIL.value,
        samvil_tier="standard",
        metrics={"schema_valid": True, "schema_version_min": "3.2"},
    )
    assert v.verdict == Verdict.PASS.value


def test_seed_to_council_blocks_on_old_schema_version() -> None:
    v = gate_check(
        GateName.SEED_TO_COUNCIL.value,
        samvil_tier="standard",
        metrics={"schema_valid": True, "schema_version_min": "3.0"},
    )
    assert v.verdict == Verdict.BLOCK.value
    assert "schema_version_min" in v.failed_checks


# ── Escalation behavior ───────────────────────────────────────────────


def test_ac_testability_escalates_in_standard(tmp_path: Path) -> None:
    """ac_testability is an escalation check. In standard+ tiers, failing it
    should escalate (route to stronger model / research), not hard-block.

    To trigger it we need a gate that actually checks ac_testability. We
    inject a mock gate via a config override so the core escalation path is
    exercised without coupling tests to which real gate carries the check.
    """
    mock_cfg = {
        "gates": {
            "mock_gate": {
                "policy": "hard",
                "thresholds": {
                    "minimal": {"ac_testability": 0.60},
                    "standard": {"ac_testability": 0.85},
                },
            }
        },
        "escalation": DEFAULT_CONFIG["escalation"],
    }
    v = gate_check(
        "mock_gate",
        samvil_tier="standard",
        metrics={"ac_testability": 0.70},
        config=mock_cfg,
    )
    assert v.verdict == Verdict.ESCALATE.value
    assert "ac_testability" in v.failed_checks
    assert v.required_action.type == "split_ac"


def test_ac_testability_hard_blocks_in_minimal() -> None:
    """minimal tier always hard-blocks even on escalation-eligible checks."""
    mock_cfg = {
        "gates": {
            "mock_gate": {
                "policy": "hard",
                "thresholds": {
                    "minimal": {"ac_testability": 0.60},
                },
            }
        },
        "escalation": DEFAULT_CONFIG["escalation"],
    }
    v = gate_check(
        "mock_gate",
        samvil_tier="minimal",
        metrics={"ac_testability": 0.30},
        config=mock_cfg,
    )
    assert v.verdict == Verdict.BLOCK.value


def test_non_escalation_check_never_escalates() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.30},
    )
    assert v.verdict == Verdict.BLOCK.value
    assert v.verdict != Verdict.ESCALATE.value


def test_escalation_loop_safety_triggers_on_second_occurrence() -> None:
    history = [
        {
            "gate": "mock_gate",
            "subject": "AC-1.1",
            "verdict": Verdict.ESCALATE.value,
            "failed_checks": ["ac_testability"],
        },
        {
            "gate": "mock_gate",
            "subject": "AC-1.1",
            "verdict": Verdict.ESCALATE.value,
            "failed_checks": ["ac_testability"],
        },
    ]
    assert should_force_user_decision(
        gate="mock_gate",
        subject="AC-1.1",
        failed_check="ac_testability",
        history=history,
    )


def test_escalation_loop_safety_allows_single_occurrence() -> None:
    history = [
        {
            "gate": "mock_gate",
            "subject": "AC-1.1",
            "verdict": Verdict.ESCALATE.value,
            "failed_checks": ["ac_testability"],
        },
    ]
    assert not should_force_user_decision(
        gate="mock_gate",
        subject="AC-1.1",
        failed_check="ac_testability",
        history=history,
    )


def test_escalation_scoped_per_subject() -> None:
    """Two different subjects should not cross-contaminate."""
    history = [
        {
            "gate": "g",
            "subject": "AC-1.1",
            "verdict": Verdict.ESCALATE.value,
            "failed_checks": ["ac_testability"],
        },
        {
            "gate": "g",
            "subject": "AC-2.1",
            "verdict": Verdict.ESCALATE.value,
            "failed_checks": ["ac_testability"],
        },
    ]
    assert not should_force_user_decision(
        gate="g",
        subject="AC-1.1",
        failed_check="ac_testability",
        history=history,
    )


# ── Flag behavior ─────────────────────────────────────────────────────


def test_allow_warn_downgrades_block_to_pass() -> None:
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.30},
        allow_warn=True,
    )
    assert v.verdict == Verdict.PASS.value
    # Still tracks what would have failed.
    assert "implementation_rate" in v.failed_checks


# ── Required-action routing ───────────────────────────────────────────


def test_required_action_for_schema() -> None:
    a = _required_action_for(["schema_valid"], {})
    assert a.type == "fix_schema"


def test_required_action_for_lifecycle() -> None:
    a = _required_action_for(["lifecycle_coverage"], {})
    assert a.type == "run_research"


def test_required_action_for_unknown_falls_back_to_ask_user() -> None:
    a = _required_action_for(["some_unknown_check"], {"foo": 1})
    assert a.type == "ask_user"
    assert a.payload.get("checks") == ["some_unknown_check"]


# ── Config & misc ─────────────────────────────────────────────────────


def test_unknown_gate_raises() -> None:
    with pytest.raises(ValueError, match="not configured"):
        gate_check(
            "not_a_gate",
            samvil_tier="standard",
            metrics={},
        )


def test_unknown_tier_raises() -> None:
    with pytest.raises(ValueError, match="samvil_tier"):
        gate_check(
            GateName.BUILD_TO_QA.value,
            samvil_tier="turbo",
            metrics={},
        )


def test_load_config_falls_back_to_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "does-not-exist.yaml")
    assert "gates" in cfg
    assert "interview_to_seed" in cfg["gates"]


def test_load_config_merges_overrides(tmp_path: Path) -> None:
    path = tmp_path / "gate_config.yaml"
    path.write_text(
        "gates:\n"
        "  build_to_qa:\n"
        "    thresholds:\n"
        "      standard:\n"
        "        implementation_rate: 0.99\n"
    )
    try:
        cfg = load_config(path)
    except Exception:
        pytest.skip("yaml unavailable")
    assert (
        cfg["gates"]["build_to_qa"]["thresholds"]["standard"]["implementation_rate"]
        == 0.99
    )
    # Unchanged defaults remain:
    assert (
        cfg["gates"]["build_to_qa"]["thresholds"]["minimal"]["implementation_rate"]
        == 0.70
    )


def test_all_gate_names_in_enum_exist_in_default_config() -> None:
    for gn in GateName:
        assert gn.value in DEFAULT_CONFIG["gates"]


def test_escalation_checks_set_matches_config() -> None:
    assert set(DEFAULT_CONFIG["escalation"]["checks"]) == ESCALATION_CHECKS
