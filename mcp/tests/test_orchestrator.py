"""Unit tests for v3.3 orchestrator stage logic."""

from __future__ import annotations

import pytest

from samvil_mcp.orchestrator import (
    PIPELINE_STAGES,
    StageEvent,
    OrchestratorError,
    complete_stage_plan,
    get_next_stage,
    get_orchestration_state,
    stage_can_proceed,
    should_skip_stage,
)


def test_pipeline_stage_order_is_canonical() -> None:
    assert PIPELINE_STAGES == (
        "interview",
        "seed",
        "council",
        "design",
        "scaffold",
        "build",
        "qa",
        "deploy",
        "retro",
        "evolve",
        "complete",
    )


@pytest.mark.parametrize("tier", ["minimal", "standard", "thorough", "full"])
def test_deploy_is_skipped_for_all_phase1_tiers(tier: str) -> None:
    assert should_skip_stage("deploy", tier) is True


def test_minimal_skips_council() -> None:
    assert should_skip_stage("council", "minimal") is True


@pytest.mark.parametrize("tier", ["standard", "thorough", "full"])
def test_non_minimal_keeps_council(tier: str) -> None:
    assert should_skip_stage("council", tier) is False


def test_get_next_stage_skips_minimal_council() -> None:
    assert get_next_stage("seed", "minimal") == "design"


def test_get_next_stage_skips_deploy() -> None:
    assert get_next_stage("qa", "standard") == "retro"


def test_get_next_stage_complete_has_no_next() -> None:
    assert get_next_stage("complete", "standard") is None


def test_unknown_stage_raises() -> None:
    with pytest.raises(OrchestratorError, match="stage"):
        get_next_stage("unknown", "standard")


def test_unknown_tier_raises() -> None:
    with pytest.raises(OrchestratorError, match="tier"):
        should_skip_stage("council", "enterprise")


def test_stage_can_proceed_allows_first_stage_without_events() -> None:
    session = {"current_stage": "interview", "samvil_tier": "standard"}
    result = stage_can_proceed(session, [], "interview")
    assert result["can_proceed"] is True
    assert result["blockers"] == []


def test_stage_can_proceed_requires_prior_successful_exits() -> None:
    session = {"current_stage": "seed", "samvil_tier": "standard"}
    result = stage_can_proceed(session, [], "seed")
    assert result["can_proceed"] is False
    assert result["blockers"] == ["stage interview is not complete"]

    result = stage_can_proceed(
        session,
        [StageEvent(event_type="interview_complete", stage="seed")],
        "seed",
    )
    assert result["can_proceed"] is True


def test_stage_can_proceed_skips_minimal_council_prereq() -> None:
    session = {"current_stage": "design", "samvil_tier": "minimal"}
    events = [
        StageEvent(event_type="interview_complete", stage="seed"),
        StageEvent(event_type="seed_generated", stage="design"),
    ]

    result = stage_can_proceed(session, events, "design")

    assert result["can_proceed"] is True


def test_stage_can_proceed_blocks_on_failed_prior_stage() -> None:
    session = {"current_stage": "qa", "samvil_tier": "standard"}
    events = [
        StageEvent(event_type="interview_complete", stage="seed"),
        StageEvent(event_type="seed_generated", stage="council"),
        StageEvent(event_type="council_verdict", stage="design"),
        StageEvent(event_type="design_complete", stage="scaffold"),
        StageEvent(event_type="scaffold_complete", stage="build"),
        StageEvent(event_type="build_fail", stage="build"),
    ]

    result = stage_can_proceed(session, events, "qa")

    assert result["can_proceed"] is False
    assert result["blockers"] == ["stage build failed"]


def test_later_success_clears_earlier_failure() -> None:
    session = {"current_stage": "qa", "samvil_tier": "standard"}
    events = [
        StageEvent(event_type="interview_complete", stage="seed"),
        StageEvent(event_type="seed_generated", stage="council"),
        StageEvent(event_type="council_verdict", stage="design"),
        StageEvent(event_type="design_complete", stage="scaffold"),
        StageEvent(event_type="scaffold_complete", stage="build"),
        StageEvent(event_type="build_fail", stage="build"),
        StageEvent(event_type="build_pass", stage="qa"),
    ]

    result = stage_can_proceed(session, events, "qa")

    assert result["can_proceed"] is True


def test_stage_can_proceed_rejects_skipped_target() -> None:
    session = {"current_stage": "deploy", "samvil_tier": "standard"}
    result = stage_can_proceed(session, [], "deploy")
    assert result["can_proceed"] is False
    assert result["blockers"] == ["stage deploy is skipped for tier standard"]


def test_get_orchestration_state_summarizes_progress() -> None:
    session = {"current_stage": "design", "samvil_tier": "minimal"}
    events = [
        StageEvent(event_type="interview_complete", stage="seed"),
        StageEvent(event_type="seed_generated", stage="design"),
    ]

    state = get_orchestration_state(session, events)

    assert state["current_stage"] == "design"
    assert state["next_stage"] == "scaffold"
    assert state["completed_stages"] == ["interview", "seed"]
    assert state["skipped_stages"] == ["council", "deploy"]
    assert state["failed_stages"] == []
    assert state["can_proceed"]["can_proceed"] is True


def test_unknown_events_do_not_affect_state() -> None:
    session = {"current_stage": "seed", "samvil_tier": "standard"}
    events = [StageEvent(event_type="custom_metric", stage="interview")]

    state = get_orchestration_state(session, events)

    assert state["completed_stages"] == []
    assert state["failed_stages"] == []


def test_complete_stage_plan_for_pass_verdict() -> None:
    session = {"current_stage": "interview", "samvil_tier": "standard"}

    plan = complete_stage_plan(session, "interview", "pass")

    assert plan["event_type"] == "interview_complete"
    assert plan["event_stage"] == "seed"
    assert plan["event_data"]["verdict"] == "pass"
    assert plan["claim"]["type"] == "gate_verdict"
    assert plan["claim"]["subject"] == "gate:interview_exit"
    assert plan["claim"]["statement"] == "verdict=pass via complete_stage"
    assert plan["next_stage"] == "seed"


def test_complete_stage_plan_for_complete_verdict() -> None:
    session = {"current_stage": "build", "samvil_tier": "standard"}

    plan = complete_stage_plan(session, "build", "complete")

    assert plan["event_type"] == "build_stage_complete"
    assert plan["event_stage"] == "qa"
    assert plan["next_stage"] == "qa"


def test_complete_stage_plan_for_fail_verdict_has_no_next_stage() -> None:
    session = {"current_stage": "build", "samvil_tier": "standard"}

    plan = complete_stage_plan(session, "build", "fail")

    assert plan["event_type"] == "build_fail"
    assert plan["event_stage"] == "build"
    assert plan["next_stage"] is None
    assert plan["claim"]["statement"] == "verdict=fail via complete_stage"


def test_complete_stage_plan_for_blocked_verdict() -> None:
    session = {"current_stage": "qa", "samvil_tier": "standard"}

    plan = complete_stage_plan(session, "qa", "blocked")

    assert plan["event_type"] == "qa_blocked"
    assert plan["event_stage"] == "qa"
    assert plan["next_stage"] is None


def test_complete_stage_plan_rejects_skipped_stage() -> None:
    session = {"current_stage": "council", "samvil_tier": "minimal"}

    with pytest.raises(OrchestratorError, match="skipped"):
        complete_stage_plan(session, "council", "pass")


def test_complete_stage_plan_rejects_unknown_verdict() -> None:
    session = {"current_stage": "build", "samvil_tier": "standard"}

    with pytest.raises(OrchestratorError, match="verdict"):
        complete_stage_plan(session, "build", "maybe")
