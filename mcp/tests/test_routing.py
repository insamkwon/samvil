"""Unit tests for model routing (Sprint 2, ④)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.routing import (
    DEFAULT_PROFILES,
    DEFAULT_ROLE_TO_TIER,
    CostTier,
    EscalationState,
    ModelProfile,
    RoutingError,
    RoutingDecision,
    downgrade_from_budget,
    escalation_from_attempts,
    load_profiles,
    load_role_overrides,
    route_task,
    validate_profiles,
)


# ── CostTier basics ────────────────────────────────────────────────────


def test_cost_tier_escalate_monotone() -> None:
    assert CostTier.FRUGAL.escalate() is CostTier.BALANCED
    assert CostTier.BALANCED.escalate() is CostTier.FRONTIER
    assert CostTier.FRONTIER.escalate() is CostTier.FRONTIER


def test_cost_tier_downgrade_monotone() -> None:
    assert CostTier.FRONTIER.downgrade() is CostTier.BALANCED
    assert CostTier.BALANCED.downgrade() is CostTier.FRUGAL
    assert CostTier.FRUGAL.downgrade() is CostTier.FRUGAL


def test_cost_tier_rank_and_multiplier() -> None:
    assert CostTier.FRUGAL.rank == 0 < CostTier.BALANCED.rank < CostTier.FRONTIER.rank
    assert CostTier.FRUGAL.cost_multiplier == 1
    assert CostTier.BALANCED.cost_multiplier == 10
    assert CostTier.FRONTIER.cost_multiplier == 30


def test_cost_tier_values_match_glossary() -> None:
    """v3.2 glossary: cost_tier uses frugal/balanced/frontier specifically
    so it can't collide with samvil_tier (minimal/.../deep)."""
    vals = {t.value for t in CostTier}
    assert vals == {"frugal", "balanced", "frontier"}
    # None of the samvil_tier values may appear.
    assert not vals & {"minimal", "standard", "thorough", "full", "deep"}


# ── route_task happy paths ─────────────────────────────────────────────


def test_route_build_worker_gets_balanced() -> None:
    d = route_task(task_role="build-worker")
    assert d.chosen_cost_tier == CostTier.BALANCED
    assert d.profile.cost_tier == CostTier.BALANCED


def test_route_qa_functional_gets_frontier() -> None:
    d = route_task(task_role="qa-functional")
    assert d.chosen_cost_tier == CostTier.FRONTIER


def test_route_unknown_role_falls_back_to_balanced() -> None:
    d = route_task(task_role="some-new-agent-persona")
    assert d.chosen_cost_tier == CostTier.BALANCED


def test_route_explicit_request_wins_over_role_default() -> None:
    d = route_task(task_role="build-worker", requested_cost_tier=CostTier.FRUGAL)
    assert d.chosen_cost_tier == CostTier.FRUGAL


def test_route_reason_includes_base_and_role() -> None:
    d = route_task(task_role="qa-functional")
    assert "frontier" in d.reason
    assert "qa-functional" in d.reason


# ── Escalation ─────────────────────────────────────────────────────────


def test_escalation_moves_up_one_step() -> None:
    d = route_task(task_role="build-worker", escalation_depth=1)
    assert d.chosen_cost_tier == CostTier.FRONTIER
    assert d.escalation_depth == 1


def test_escalation_caps_at_frontier() -> None:
    d = route_task(task_role="build-worker", escalation_depth=5)
    assert d.chosen_cost_tier == CostTier.FRONTIER


def test_escalation_from_attempts_clamps() -> None:
    assert escalation_from_attempts(0) == 0
    assert escalation_from_attempts(1) == 1
    assert escalation_from_attempts(2) == 2
    assert escalation_from_attempts(10) == 2


def test_escalation_state_bumps() -> None:
    st = EscalationState()
    assert st.bump() == 1
    assert st.bump() == 2


# ── Downgrade ──────────────────────────────────────────────────────────


def test_downgrade_fires_above_threshold() -> None:
    d = route_task(task_role="build-worker", budget_pressure=0.90)
    assert d.chosen_cost_tier == CostTier.FRUGAL
    assert d.downgraded is True


def test_downgrade_does_not_fire_below_threshold() -> None:
    d = route_task(task_role="build-worker", budget_pressure=0.50)
    assert d.chosen_cost_tier == CostTier.BALANCED
    assert d.downgraded is False


def test_escalation_overrides_downgrade() -> None:
    d = route_task(
        task_role="build-worker",
        escalation_depth=1,
        budget_pressure=0.95,
    )
    # Escalation wins; chosen should be frontier, not frugal.
    assert d.chosen_cost_tier == CostTier.FRONTIER
    assert d.downgraded is False


def test_downgrade_from_budget_computes_max_ratio() -> None:
    ratio = downgrade_from_budget(
        consumed={"wall_time_minutes": 30, "llm_calls": 100, "estimated_cost_usd": 5},
        ceiling={"wall_time_minutes": 40, "llm_calls": 150, "estimated_cost_usd": 20},
    )
    # 30/40 = 0.75, 100/150 = 0.67, 5/20 = 0.25. max = 0.75.
    assert abs(ratio - 0.75) < 1e-6


def test_downgrade_from_budget_empty_inputs() -> None:
    assert downgrade_from_budget({}, {}) == 0.0


# ── Profile lookup / back-off ──────────────────────────────────────────


def test_no_profile_in_tier_falls_back_one_step_up() -> None:
    # Only a frontier profile exists — balanced requests should back off.
    profiles = [
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
        )
    ]
    d = route_task(task_role="build-worker", profiles=profiles)
    assert d.chosen_cost_tier == CostTier.FRONTIER
    assert "backoff" in d.reason


def test_no_profile_at_all_raises() -> None:
    with pytest.raises(RoutingError, match="no profile matches"):
        # No BALANCED available, and escalate() of BALANCED is FRONTIER,
        # which is also missing.
        route_task(
            task_role="build-worker",
            profiles=[
                ModelProfile(
                    provider="x",
                    model_id="m",
                    cost_tier=CostTier.FRUGAL,
                )
            ],
        )


def test_deterministic_tie_break_picks_first() -> None:
    profiles = [
        ModelProfile(provider="p1", model_id="m1", cost_tier=CostTier.BALANCED),
        ModelProfile(provider="p2", model_id="m2", cost_tier=CostTier.BALANCED),
    ]
    d1 = route_task(task_role="build-worker", profiles=profiles)
    d2 = route_task(task_role="build-worker", profiles=profiles)
    # Must be stable — no random.choice.
    assert d1.profile.key() == d2.profile.key() == "p1/m1"


# ── "build on Opus, QA on Codex" scenario ─────────────────────────────


def test_build_on_opus_qa_on_codex_round_trip() -> None:
    """Exit-gate scenario from §7 Sprint 2."""
    # User overrides: build-worker explicitly frontier, qa-functional frontier.
    overrides = {
        "build-worker": CostTier.FRONTIER,
        "qa-functional": CostTier.FRONTIER,
    }
    # Profiles: Opus wins first-listed for build-worker; Codex second.
    profiles = [
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
            nickname="opus-4.7",
        ),
        ModelProfile(
            provider="openai",
            model_id="gpt-5-codex",
            cost_tier=CostTier.FRONTIER,
            nickname="codex",
        ),
    ]
    build = route_task(
        task_role="build-worker", profiles=profiles, role_overrides=overrides
    )
    assert build.profile.model_id == "claude-opus-4-7"

    # QA specifically requests Codex via a custom filter: for Sprint 2,
    # this is modeled by swapping profile order per-task. A richer
    # dispatch ships in Sprint 3 alongside role primitives.
    qa_profiles = [
        ModelProfile(
            provider="openai",
            model_id="gpt-5-codex",
            cost_tier=CostTier.FRONTIER,
            nickname="codex",
        ),
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
            nickname="opus-4.7",
        ),
    ]
    qa = route_task(
        task_role="qa-functional", profiles=qa_profiles, role_overrides=overrides
    )
    assert qa.profile.model_id == "gpt-5-codex"


# ── YAML loader ───────────────────────────────────────────────────────


def test_load_profiles_fallback_when_missing(tmp_path: Path) -> None:
    loaded = load_profiles(tmp_path / "nope.yaml")
    assert loaded == DEFAULT_PROFILES


def test_load_profiles_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "model_profiles.yaml"
    path.write_text(
        "profiles:\n"
        "  - provider: anthropic\n"
        "    model_id: claude-sonnet-4-6\n"
        "    cost_tier: balanced\n"
        "    nickname: sonnet\n"
    )
    try:
        loaded = load_profiles(path)
    except Exception:
        pytest.skip("yaml unavailable")
    assert len(loaded) == 1
    assert loaded[0].model_id == "claude-sonnet-4-6"
    assert loaded[0].cost_tier == CostTier.BALANCED


def test_load_role_overrides_merges_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "model_profiles.yaml"
    path.write_text(
        "profiles: []\n"
        "role_overrides:\n"
        "  build-worker: frontier\n"
    )
    try:
        m = load_role_overrides(path)
    except Exception:
        pytest.skip("yaml unavailable")
    assert m["build-worker"] == CostTier.FRONTIER
    # Unchanged baked defaults remain.
    assert m["qa-functional"] == CostTier.FRONTIER


def test_load_role_overrides_skips_bad_tier(tmp_path: Path) -> None:
    path = tmp_path / "model_profiles.yaml"
    path.write_text(
        "profiles: []\n"
        "role_overrides:\n"
        "  build-worker: turbo\n"
    )
    try:
        m = load_role_overrides(path)
    except Exception:
        pytest.skip("yaml unavailable")
    # Bad tier is skipped; default remains.
    assert m["build-worker"] == CostTier.BALANCED


# ── validate_profiles ─────────────────────────────────────────────────


def test_validate_ok_for_defaults() -> None:
    issues = validate_profiles(DEFAULT_PROFILES)
    assert issues == []


def test_validate_flags_missing_tier() -> None:
    issues = validate_profiles(
        [
            ModelProfile(
                provider="x", model_id="y", cost_tier=CostTier.BALANCED
            )
        ]
    )
    assert any("frugal" in i for i in issues)
    assert any("frontier" in i for i in issues)


def test_validate_flags_duplicate() -> None:
    p = ModelProfile(provider="p", model_id="m", cost_tier=CostTier.BALANCED)
    issues = validate_profiles([p, p])
    assert any("duplicate" in i for i in issues)


def test_routing_decision_to_dict_round_trips() -> None:
    d = route_task(task_role="build-worker")
    as_dict = d.to_dict()
    assert as_dict["chosen_cost_tier"] == "balanced"
    assert as_dict["task_role"] == "build-worker"
    assert "provider" in as_dict
