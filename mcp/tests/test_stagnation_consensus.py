"""Unit tests for stagnation (⑩) and consensus (⑨) — Sprint 5b."""

from __future__ import annotations

import pytest

from samvil_mcp.consensus_v3_2 import (
    DEPRECATION_WARNING,
    DisputeInput,
    DisputeTrigger,
    build_judge_prompt,
    build_reviewer_prompt,
    detect_dispute,
)
from samvil_mcp.stagnation_v3_2 import (
    FILE_UNCHANGED_MINUTES,
    QA_SCORE_DELTA_FLOOR,
    Severity,
    Signal,
    StagnationInput,
    build_lateral_prompt,
    evaluate,
)


# ── Stagnation ────────────────────────────────────────────────────────


def test_no_signals_low() -> None:
    v = evaluate(StagnationInput())
    assert v.severity == Severity.LOW.value
    assert v.should_halt is False


def test_repeated_error_single_signal_medium() -> None:
    v = evaluate(
        StagnationInput(
            error_history=["build_fail", "build_fail"],
            current_error="build_fail",
        )
    )
    assert Signal.REPEATED_ERROR.value in v.signals
    assert v.severity == Severity.MEDIUM.value
    assert v.should_halt is False


def test_qa_score_flat_single_signal_medium() -> None:
    v = evaluate(
        StagnationInput(
            qa_score_history=[0.70, 0.71, 0.705],
            qa_iterations_window=3,
        )
    )
    assert Signal.QA_SCORE_FLAT.value in v.signals
    assert v.severity == Severity.MEDIUM.value


def test_qa_score_changing_no_signal() -> None:
    v = evaluate(
        StagnationInput(
            qa_score_history=[0.70, 0.80, 0.90],
            qa_iterations_window=3,
        )
    )
    assert Signal.QA_SCORE_FLAT.value not in v.signals


def test_seed_changed_build_same_signal() -> None:
    v = evaluate(
        StagnationInput(
            seed_version_changed=True,
            build_output_changed=False,
        )
    )
    assert Signal.SEED_CHANGED_BUILD_SAME.value in v.signals


def test_two_signals_escalate_to_high() -> None:
    v = evaluate(
        StagnationInput(
            error_history=["f", "f"],
            current_error="f",
            seed_version_changed=True,
            build_output_changed=False,
        )
    )
    assert v.severity == Severity.HIGH.value
    assert v.should_halt is True


def test_file_unchanged_requires_active_work() -> None:
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=FILE_UNCHANGED_MINUTES + 5)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # work_active=False → no signal even though long silence
    v = evaluate(
        StagnationInput(
            last_file_change_ts=old,
            now_ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            work_active=False,
        )
    )
    assert Signal.FILE_HASH_UNCHANGED.value not in v.signals

    # work_active=True → signal fires
    v = evaluate(
        StagnationInput(
            last_file_change_ts=old,
            now_ts=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            work_active=True,
        )
    )
    assert Signal.FILE_HASH_UNCHANGED.value in v.signals


def test_lateral_prompt_shape() -> None:
    v = evaluate(
        StagnationInput(
            error_history=["x", "x"],
            current_error="x",
            seed_version_changed=True,
            build_output_changed=False,
        )
    )
    prompt = build_lateral_prompt(subject="AC-1.1", verdict=v)
    assert "AC-1.1" in prompt
    assert "alternative" in prompt.lower()
    assert "smallest" in prompt.lower()


# ── Consensus ────────────────────────────────────────────────────────


def test_generator_judge_mismatch_triggers() -> None:
    d = detect_dispute(
        DisputeInput(
            subject="AC-1", generator_verdict="pass", judge_verdict="fail"
        )
    )
    assert d.should_invoke
    assert DisputeTrigger.GENERATOR_JUDGE_MISMATCH.value in d.triggers


def test_no_trigger_when_aligned() -> None:
    d = detect_dispute(
        DisputeInput(
            subject="AC-1", generator_verdict="pass", judge_verdict="pass"
        )
    )
    assert not d.should_invoke


def test_weak_evidence_triggers() -> None:
    d = detect_dispute(
        DisputeInput(subject="AC-1", reviewer_flags=["weak_evidence"])
    )
    assert d.should_invoke


def test_architecture_tradeoff_triggers() -> None:
    d = detect_dispute(
        DisputeInput(
            subject="design:queue",
            architecture_note="Kafka vs SQS unresolved for the event bus",
        )
    )
    assert d.should_invoke
    assert DisputeTrigger.ARCHITECTURE_TRADEOFF.value in d.triggers


def test_ambiguous_intent_below_threshold_triggers() -> None:
    d = detect_dispute(DisputeInput(subject="project", intent_clarity=0.50))
    assert d.should_invoke


def test_intent_above_threshold_does_not_trigger() -> None:
    d = detect_dispute(DisputeInput(subject="project", intent_clarity=0.90))
    assert not d.should_invoke


def test_reviewer_prompt_shape() -> None:
    p = build_reviewer_prompt(
        subject="AC-1",
        triggers=["generator_judge_mismatch"],
        context="previous claim history",
    )
    assert "AC-1" in p
    assert "generator_judge_mismatch" in p


def test_judge_prompt_uses_reviewer_position() -> None:
    p = build_judge_prompt(
        subject="AC-1",
        triggers=["weak_evidence"],
        reviewer_position="I accept — evidence is sufficient.",
    )
    assert "I accept" in p
    assert "weak_evidence" in p


def test_deprecation_warning_points_to_migration_doc() -> None:
    assert "council-retirement-migration" in DEPRECATION_WARNING
