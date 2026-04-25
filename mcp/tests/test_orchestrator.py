"""Unit tests for v3.3 orchestrator stage logic."""

from __future__ import annotations

import pytest

from samvil_mcp.orchestrator import (
    PIPELINE_STAGES,
    OrchestratorError,
    get_next_stage,
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
