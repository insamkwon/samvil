"""Unit tests for model_role (Sprint 3, ⑤)."""

from __future__ import annotations

import pytest

from samvil_mcp.model_role import (
    DEFAULT_ROLES,
    ModelRole,
    OUT_OF_BAND,
    agents_by_role,
    get_role,
    inventory,
    is_judge_role,
    validate_role_separation,
)


def test_every_known_agent_has_a_role() -> None:
    # Every entry in DEFAULT_ROLES maps to a ModelRole.
    for agent, role in DEFAULT_ROLES.items():
        assert isinstance(role, ModelRole)


def test_out_of_band_is_not_double_registered() -> None:
    assert not (OUT_OF_BAND & set(DEFAULT_ROLES.keys()))


def test_get_role_bare_name() -> None:
    assert get_role("build-worker") == ModelRole.GENERATOR
    assert get_role("qa-functional") == ModelRole.JUDGE


def test_get_role_agent_prefix() -> None:
    assert get_role("agent:build-worker") == ModelRole.GENERATOR
    assert get_role("agent:qa-functional") == ModelRole.JUDGE


def test_get_role_returns_none_for_out_of_band() -> None:
    assert get_role("orchestrator-agent") is None
    assert get_role("agent:socratic-interviewer") is None


def test_get_role_returns_none_for_unknown() -> None:
    assert get_role("agent:random-new-agent") is None


def test_is_judge_role() -> None:
    assert is_judge_role("qa-functional")
    assert not is_judge_role("build-worker")


# ── validate_role_separation ──────────────────────────────────────────


def test_generator_claims_judge_verifies_ok() -> None:
    r = validate_role_separation(
        claimed_by="agent:build-worker",
        verified_by="agent:qa-functional",
    )
    assert r.valid
    assert r.claimed_role == ModelRole.GENERATOR
    assert r.verified_role == ModelRole.JUDGE


def test_same_identity_rejected() -> None:
    r = validate_role_separation(
        claimed_by="agent:qa-functional",
        verified_by="agent:qa-functional",
    )
    assert not r.valid
    assert "self-verify" in r.reason


def test_generator_verifying_other_generator_rejected() -> None:
    r = validate_role_separation(
        claimed_by="agent:build-worker",
        verified_by="agent:frontend-dev",
    )
    assert not r.valid
    assert "Judge role" in r.reason


def test_judge_claiming_rejected() -> None:
    """Judge cannot claim its own subject (anti reward-hacking)."""
    r = validate_role_separation(
        claimed_by="agent:qa-functional",
        verified_by="agent:product-owner",
    )
    assert not r.valid
    assert "Judge" in r.reason


def test_user_can_always_verify() -> None:
    r = validate_role_separation(
        claimed_by="agent:build-worker",
        verified_by="agent:user",
    )
    assert r.valid
    assert "out-of-band" in r.reason


def test_orchestrator_can_verify() -> None:
    r = validate_role_separation(
        claimed_by="agent:build-worker",
        verified_by="agent:orchestrator-agent",
    )
    assert r.valid


def test_empty_args_rejected() -> None:
    r = validate_role_separation(claimed_by="", verified_by="agent:qa-functional")
    assert not r.valid
    assert "required" in r.reason


def test_reviewer_cannot_verify() -> None:
    r = validate_role_separation(
        claimed_by="agent:build-worker",
        verified_by="agent:tech-lead",
    )
    assert not r.valid
    assert "Judge" in r.reason


# ── inventory / rollup ─────────────────────────────────────────────────


def test_inventory_shape() -> None:
    inv = inventory()
    assert "build-worker" in inv
    assert inv["build-worker"]["primary"] == "generator"
    # Build-worker's secondary repairer role was declared.
    assert "repairer" in inv["build-worker"]["allowed_secondary"]


def test_inventory_marks_out_of_band() -> None:
    inv = inventory()
    assert inv["orchestrator-agent"]["out_of_band"] is True


def test_agents_by_role_counts_make_sense() -> None:
    rollup = agents_by_role()
    # The six categories plus out_of_band.
    assert set(rollup.keys()) == {
        "generator",
        "reviewer",
        "judge",
        "repairer",
        "researcher",
        "compressor",
        "out_of_band",
    }
    # Each role has at least one agent except compressor (inline
    # function; one slot registered in DEFAULT_ROLES).
    assert len(rollup["generator"]) >= 5
    assert len(rollup["reviewer"]) >= 5
    assert len(rollup["judge"]) >= 4  # qa-* + product-owner
    assert rollup["repairer"] == ["error-handler"]
    assert len(rollup["out_of_band"]) >= 5
