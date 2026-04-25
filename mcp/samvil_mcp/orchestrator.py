"""Orchestrator stage logic for SAMVIL v3.3.

The orchestrator is the read-mostly decision layer that skills can ask:
"what stage is next?", "can I proceed?", and "how should completion be
recorded?". It does not own persistence. MCP wrappers in `server.py` adapt
these pure functions to EventStore + ClaimLedger.
"""

from __future__ import annotations

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
