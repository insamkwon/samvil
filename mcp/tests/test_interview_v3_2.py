"""Unit tests for interview v3.2 (Sprint 4, ②)."""

from __future__ import annotations

import pytest

from samvil_mcp.interview_v3_2 import (
    InterviewLevel,
    LEVEL_TO_TECHNIQUES,
    Technique,
    build_adversarial_prompt,
    build_meta_probe_prompt,
    confidence_follow_up,
    pal_select_level,
    parse_meta_probe_result,
    resolve_level,
    scenario_simulate,
    techniques_for_level,
)


# ── Enum + level mapping ──────────────────────────────────────────────


def test_interview_level_values_match_glossary() -> None:
    """v3.2 glossary: interview_level uses quick/normal/deep/max/auto;
    no collision with samvil_tier."""
    vals = {lvl.value for lvl in InterviewLevel}
    assert vals == {"quick", "normal", "deep", "max", "auto"}
    assert not vals & {"minimal", "standard", "thorough", "full"}


def test_normal_is_default_techniques() -> None:
    t = techniques_for_level(InterviewLevel.NORMAL)
    assert Technique.SEED_READINESS in t
    assert Technique.META_SELF_PROBE in t
    assert Technique.SCENARIO_SIMULATION in t


def test_auto_uses_pal_adaptive() -> None:
    t = techniques_for_level(InterviewLevel.AUTO)
    assert t == (Technique.PAL_ADAPTIVE,)


def test_max_includes_adversarial() -> None:
    t = techniques_for_level(InterviewLevel.MAX)
    assert Technique.ADVERSARIAL in t


# ── T1: seed_readiness ────────────────────────────────────────────────


# ── T2: meta probe ────────────────────────────────────────────────────


def test_meta_probe_prompt_shape() -> None:
    p = build_meta_probe_prompt(phase="core_experience", answers_summary="X: Y")
    assert "core_experience" in p
    assert "X: Y" in p
    assert "JSON" in p


def test_parse_meta_probe_json() -> None:
    raw = """
    {"blind_spots": ["ac_testability weak"], "followups": ["How do you test X?"]}
    """
    out = parse_meta_probe_result(raw)
    assert out["blind_spots"] == ["ac_testability weak"]
    assert out["followups"] == ["How do you test X?"]


def test_parse_meta_probe_heuristic_fallback() -> None:
    raw = """
    Notes:
    - This area feels thin on evidence gap
    - How do you test the login flow?
    - How will you measure latency?
    """
    out = parse_meta_probe_result(raw)
    assert any("evidence gap" in s for s in out["blind_spots"])
    assert any("how do you" in s.lower() for s in out["followups"])


def test_parse_meta_probe_empty_response_ok() -> None:
    out = parse_meta_probe_result("")
    assert out == {"blind_spots": [], "followups": []}


# ── T3: confidence ────────────────────────────────────────────────────


def test_confidence_low_triggers_follow_up() -> None:
    msg = confidence_follow_up(answer="users want dark mode", confidence=2)
    assert msg is not None
    assert "example" in msg.lower()


def test_confidence_high_skips() -> None:
    assert confidence_follow_up(answer="x", confidence=4) is None
    assert confidence_follow_up(answer="x", confidence=5) is None


def test_confidence_custom_threshold() -> None:
    assert confidence_follow_up(answer="x", confidence=3, low_threshold=3) is not None


# ── T4: scenario simulation ───────────────────────────────────────────


def test_scenario_flags_independent_with_deps() -> None:
    features = [
        {"name": "login", "independent": True, "depends_on": ["auth"]},
        {"name": "auth", "independent": False, "depends_on": []},
    ]
    steps = scenario_simulate(features=features)
    flat = sum((s.contradictions for s in steps), [])
    assert any("independent" in c for c in flat)


def test_scenario_flags_missing_dependency() -> None:
    features = [
        {"name": "cart", "independent": False, "depends_on": ["checkout"]},
        # 'checkout' is not declared
    ]
    steps = scenario_simulate(features=features)
    flat = sum((s.contradictions for s in steps), [])
    assert any("not declared" in c for c in flat)


def test_scenario_empty_features_is_clean() -> None:
    steps = scenario_simulate(features=[])
    assert all(s.contradictions == [] for s in steps)


# ── T5: adversarial prompt ────────────────────────────────────────────


def test_adversarial_prompt_includes_tier_and_summary() -> None:
    p = build_adversarial_prompt(summary="simple todo", samvil_tier="thorough")
    assert "thorough" in p
    assert "simple todo" in p


# ── T6: PAL adaptive ──────────────────────────────────────────────────


def test_pal_low_complexity_picks_quick() -> None:
    assert pal_select_level(project_prompt="countdown timer") == InterviewLevel.QUICK


def test_pal_high_complexity_picks_deep() -> None:
    lvl = pal_select_level(
        project_prompt="multi-tenant billing SaaS with real-time sync"
    )
    assert lvl == InterviewLevel.DEEP


def test_pal_high_complexity_on_thorough_picks_max() -> None:
    lvl = pal_select_level(
        project_prompt="payments and compliance system",
        samvil_tier="thorough",
    )
    assert lvl == InterviewLevel.MAX


def test_pal_medium_complexity_picks_normal() -> None:
    lvl = pal_select_level(project_prompt="simple admin dashboard")
    assert lvl == InterviewLevel.NORMAL


def test_pal_solution_type_overrides() -> None:
    # automation gets quick even if the prompt is complex
    assert (
        pal_select_level(
            project_prompt="multi-tenant real-time",
            solution_type="automation",
        )
        == InterviewLevel.QUICK
    )
    assert (
        pal_select_level(project_prompt="whatever", solution_type="game")
        == InterviewLevel.NORMAL
    )


# ── resolve_level ─────────────────────────────────────────────────────


def test_resolve_level_auto_dispatches_via_pal() -> None:
    lvl = resolve_level(
        InterviewLevel.AUTO,
        project_prompt="countdown timer",
    )
    assert lvl == InterviewLevel.QUICK


def test_resolve_level_max_downgrades_without_router() -> None:
    lvl = resolve_level(
        InterviewLevel.MAX,
        provider_router_ready=False,
    )
    assert lvl == InterviewLevel.DEEP


def test_resolve_level_max_keeps_with_router() -> None:
    lvl = resolve_level(
        InterviewLevel.MAX,
        provider_router_ready=True,
    )
    assert lvl == InterviewLevel.MAX


def test_resolve_level_string_input_accepted() -> None:
    lvl = resolve_level("normal")
    assert lvl == InterviewLevel.NORMAL
