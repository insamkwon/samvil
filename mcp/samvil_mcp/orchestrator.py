"""Orchestrator stage logic for SAMVIL v3.3.

The orchestrator is the read-mostly decision layer that skills can ask:
"what stage is next?", "can I proceed?", and "how should completion be
recorded?". It does not own persistence. MCP wrappers in `server.py` adapt
these pure functions to EventStore + ClaimLedger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PIPELINE_STAGES: tuple[str, ...] = (
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

SAMVIL_TIERS: tuple[str, ...] = ("minimal", "standard", "thorough", "full")

SUCCESS_EVENT_TO_STAGE: dict[str, str] = {
    "interview_complete": "interview",
    "seed_generated": "seed",
    "pm_seed_complete": "seed",
    "pm_seed_converted": "seed",
    "council_complete": "council",
    "council_verdict": "council",
    "design_complete": "design",
    "blueprint_generated": "design",
    "blueprint_feasibility_checked": "design",
    "scaffold_complete": "scaffold",
    "build_pass": "build",
    "build_stage_complete": "build",
    "build_feature_success": "build",
    "feature_tree_complete": "build",
    "qa_pass": "qa",
    "deploy_complete": "deploy",
    "retro_complete": "retro",
    "evolve_converge": "evolve",
    "stage_end": "",
}

FAIL_EVENT_TO_STAGE: dict[str, str] = {
    "build_fail": "build",
    "build_feature_fail": "build",
    "feature_failed": "build",
    "qa_fail": "qa",
    "qa_revise": "qa",
    "qa_blocked": "qa",
    "qa_unimplemented": "qa",
    "stall_detected": "",
    "stall_abandoned": "",
}

SUCCESS_COMPLETE_EVENTS: dict[str, str] = {
    "interview": "interview_complete",
    "seed": "seed_generated",
    "council": "council_verdict",
    "design": "design_complete",
    "scaffold": "scaffold_complete",
    "build": "build_stage_complete",
    "qa": "qa_pass",
    "deploy": "deploy_complete",
    "retro": "retro_complete",
    "evolve": "evolve_converge",
    "complete": "stage_end",
}

FAIL_COMPLETE_EVENTS: dict[str, str] = {
    "build": "build_fail",
    "qa": "qa_fail",
}

BLOCKED_COMPLETE_EVENTS: dict[str, str] = {
    "qa": "qa_blocked",
}

COMPLETE_VERDICTS: tuple[str, ...] = ("pass", "complete", "fail", "blocked")


@dataclass(frozen=True)
class StageEvent:
    """Reduced event-store row used by pure orchestrator decisions."""

    event_type: str
    stage: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class OrchestratorError(ValueError):
    """Raised when an orchestration decision would be invalid."""


def _validate_stage(stage: str) -> None:
    if stage not in PIPELINE_STAGES:
        raise OrchestratorError(f"unknown stage: {stage!r}")


def _validate_tier(samvil_tier: str) -> None:
    if samvil_tier not in SAMVIL_TIERS:
        raise OrchestratorError(f"unknown samvil_tier: {samvil_tier!r}")


def should_skip_stage(stage: str, samvil_tier: str) -> bool:
    """Return whether `stage` is skipped for the current tier in v3.3 Phase 1."""
    _validate_stage(stage)
    _validate_tier(samvil_tier)

    if stage == "council" and samvil_tier == "minimal":
        return True
    if stage == "deploy":
        return True
    return False


def get_next_stage(current: str, samvil_tier: str) -> str | None:
    """Return the next non-skipped stage after `current`."""
    _validate_stage(current)
    _validate_tier(samvil_tier)

    current_index = PIPELINE_STAGES.index(current)
    for stage in PIPELINE_STAGES[current_index + 1:]:
        if not should_skip_stage(stage, samvil_tier):
            return stage
    return None


def stage_can_proceed(
    session: Any,
    events: list[StageEvent],
    target_stage: str,
) -> dict[str, Any]:
    """Return whether `target_stage` can run based on prior stage outcomes."""
    samvil_tier = _session_tier(session)
    _validate_stage(target_stage)
    _validate_tier(samvil_tier)

    if should_skip_stage(target_stage, samvil_tier):
        return {
            "can_proceed": False,
            "blockers": [f"stage {target_stage} is skipped for tier {samvil_tier}"],
        }

    statuses = _stage_statuses(events)
    blockers: list[str] = []

    target_index = PIPELINE_STAGES.index(target_stage)
    for stage in PIPELINE_STAGES[:target_index]:
        if should_skip_stage(stage, samvil_tier):
            continue
        status = statuses.get(stage)
        if status == "failed":
            blockers.append(f"stage {stage} failed")
        elif status != "complete":
            blockers.append(f"stage {stage} is not complete")

    return {"can_proceed": not blockers, "blockers": blockers}


def get_orchestration_state(session: Any, events: list[StageEvent]) -> dict[str, Any]:
    """Summarize progress from session + event stream without mutating state."""
    current_stage = _session_stage(session)
    samvil_tier = _session_tier(session)
    _validate_stage(current_stage)
    _validate_tier(samvil_tier)

    statuses = _stage_statuses(events)
    skipped = [
        stage for stage in PIPELINE_STAGES if should_skip_stage(stage, samvil_tier)
    ]
    completed = [
        stage
        for stage in PIPELINE_STAGES
        if statuses.get(stage) == "complete" and stage not in skipped
    ]
    failed = [
        stage
        for stage in PIPELINE_STAGES
        if statuses.get(stage) == "failed" and stage not in skipped
    ]
    next_stage = get_next_stage(current_stage, samvil_tier)
    can_proceed = stage_can_proceed(session, events, current_stage)

    executable_stages = [s for s in PIPELINE_STAGES if s not in skipped]
    return {
        "current_stage": current_stage,
        "samvil_tier": samvil_tier,
        "next_stage": next_stage,
        "completed_stages": completed,
        "failed_stages": failed,
        "skipped_stages": skipped,
        "can_proceed": can_proceed,
        "progress": {
            "completed": len(completed),
            "total": len(executable_stages),
            "percent": round((len(completed) / len(executable_stages)) * 100, 1),
        },
    }


def complete_stage_plan(session: Any, stage: str, verdict: str) -> dict[str, Any]:
    """Return the event + claim payloads needed to mark a stage complete.

    This function is intentionally pure. The server wrapper owns EventStore and
    ClaimLedger mutation.
    """
    samvil_tier = _session_tier(session)
    _validate_stage(stage)
    _validate_tier(samvil_tier)
    if should_skip_stage(stage, samvil_tier):
        raise OrchestratorError(f"stage {stage} is skipped for tier {samvil_tier}")
    if verdict not in COMPLETE_VERDICTS:
        raise OrchestratorError(f"unknown verdict: {verdict!r}")

    success = verdict in ("pass", "complete")
    if success:
        event_type = SUCCESS_COMPLETE_EVENTS[stage]
        next_stage = get_next_stage(stage, samvil_tier)
        event_stage = next_stage or stage
    elif verdict == "blocked":
        event_type = BLOCKED_COMPLETE_EVENTS.get(stage, f"{stage}_blocked")
        next_stage = None
        event_stage = stage
    else:
        event_type = FAIL_COMPLETE_EVENTS.get(stage, f"{stage}_fail")
        next_stage = None
        event_stage = stage

    return {
        "event_type": event_type,
        "event_stage": event_stage,
        "event_data": {"verdict": verdict, "stage": stage},
        "claim": {
            "type": "gate_verdict",
            "subject": f"gate:{stage}_exit",
            "statement": f"verdict={verdict} via complete_stage",
            "authority_file": "project.state.json",
            "evidence": [f"event:{event_type}"],
            "meta": {
                "via": "complete_stage",
                "verdict": verdict,
                "stage": stage,
                "next_stage": next_stage,
            },
        },
        "next_stage": next_stage,
    }


def _stage_statuses(events: list[StageEvent]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for event in events:
        event_type = _as_value(event.event_type)
        stage = _stage_for_event(event_type, _as_value(event.stage))
        if stage not in PIPELINE_STAGES:
            continue
        if event_type in SUCCESS_EVENT_TO_STAGE:
            statuses[stage] = "complete"
        elif event_type in FAIL_EVENT_TO_STAGE:
            statuses[stage] = "failed"
    return statuses


def _stage_for_event(event_type: str, fallback_stage: str) -> str:
    if event_type in SUCCESS_EVENT_TO_STAGE:
        return SUCCESS_EVENT_TO_STAGE[event_type] or fallback_stage
    if event_type in FAIL_EVENT_TO_STAGE:
        return FAIL_EVENT_TO_STAGE[event_type] or fallback_stage
    return fallback_stage


def _session_stage(session: Any) -> str:
    if isinstance(session, dict):
        return _as_value(session.get("current_stage", ""))
    return _as_value(getattr(session, "current_stage", ""))


def _session_tier(session: Any) -> str:
    if isinstance(session, dict):
        return _as_value(session.get("samvil_tier", "standard"))
    return _as_value(getattr(session, "samvil_tier", "standard"))


def _as_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
