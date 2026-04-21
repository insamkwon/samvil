"""v3.1.0 Sprint 1 — tests for Deep Mode tier (v3-022) and required-phase map.

Covers:
  - TIER_TARGETS has 'deep' entry with 0.005 threshold
  - score_ambiguity accepts tier='deep' and returns target=0.005
  - tier_phases() returns expected sets per tier
  - lifecycle phase is mandatory for standard and above (v3-023)
"""
from __future__ import annotations

from samvil_mcp.interview_engine import (
    TIER_REQUIRED_PHASES,
    TIER_TARGETS,
    score_ambiguity,
    tier_phases,
)


def test_deep_tier_threshold_is_half_of_full() -> None:
    assert TIER_TARGETS["deep"] == 0.005
    assert TIER_TARGETS["deep"] < TIER_TARGETS["full"] == 0.01


def test_score_ambiguity_accepts_deep_tier() -> None:
    state = {
        "target_user": "solo indie developer",
        "core_problem": "간단한 생각을 빠르게 저장할 장소",
        "core_experience": "앱을 열면 즉시 타이핑 가능",
        "features": ["quick-capture", "search"],
        "exclusions": ["team-share"],
        "constraints": ["localStorage only"],
        "acceptance_criteria": [
            "엔터만으로 한 줄 저장",
            "검색은 300ms 이내 응답",
            "offline에서도 입력 가능",
        ],
    }
    result = score_ambiguity(state, tier="deep")
    assert result["tier"] == "deep"
    assert result["target"] == 0.005


def test_tier_phases_minimal_is_core_plus_scope() -> None:
    phases = tier_phases("minimal")
    assert "core" in phases
    assert "scope" in phases
    assert "lifecycle" not in phases  # minimal skips lifecycle


def test_tier_phases_standard_requires_lifecycle() -> None:
    phases = tier_phases("standard")
    assert "lifecycle" in phases, (
        "Customer Lifecycle Journey (v3-023) must be mandatory from standard tier"
    )


def test_tier_phases_thorough_adds_nonfunc_and_inversion() -> None:
    phases = tier_phases("thorough")
    assert {"nonfunc", "inversion", "unknown"} <= phases


def test_tier_phases_full_adds_stakeholder_and_research() -> None:
    phases = tier_phases("full")
    assert "stakeholder" in phases
    assert "research" in phases


def test_tier_phases_deep_adds_domain_deep() -> None:
    phases = tier_phases("deep")
    assert "domain_deep" in phases
    # Deep should be a superset of full
    assert tier_phases("full") <= phases


def test_tier_required_phases_dict_has_all_five_tiers() -> None:
    assert set(TIER_REQUIRED_PHASES.keys()) == {
        "minimal",
        "standard",
        "thorough",
        "full",
        "deep",
    }


def test_tier_phases_unknown_tier_falls_back_to_standard() -> None:
    assert tier_phases("nonexistent") == tier_phases("standard")
