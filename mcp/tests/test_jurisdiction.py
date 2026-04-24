"""Unit tests for jurisdiction (Sprint 5a, ⑦)."""

from __future__ import annotations

import pytest

from samvil_mcp.jurisdiction import (
    GrantLedger,
    Jurisdiction,
    check_jurisdiction,
    loop_should_stop,
)


def test_strictest_wins_ai_when_nothing_matches() -> None:
    v = check_jurisdiction(action_description="add a test helper")
    assert v.jurisdiction == Jurisdiction.AI.value


def test_user_keyword_escalates_to_user() -> None:
    v = check_jurisdiction(
        action_description="add password reset flow",
        diff_text="function resetPassword()",
    )
    assert v.jurisdiction == Jurisdiction.USER.value
    assert any("password" in r for r in v.matched_rules)


def test_external_keyword_escalates_to_external() -> None:
    v = check_jurisdiction(action_description="check license compatibility")
    assert v.jurisdiction == Jurisdiction.EXTERNAL.value


def test_user_overrides_external_when_both_match() -> None:
    v = check_jurisdiction(
        action_description="migration for billing pricing",
    )
    # `migration` and `payment`-like don't fire here; `pricing` fires
    # external, but `migration` fires user → user wins.
    assert v.jurisdiction == Jurisdiction.USER.value


def test_irreversible_command_always_user() -> None:
    v = check_jurisdiction(command="git push --force origin main")
    assert v.jurisdiction == Jurisdiction.USER.value
    assert v.irreversible is True


def test_rm_rf_is_irreversible() -> None:
    v = check_jurisdiction(command="rm -rf /tmp/somedir")
    assert v.irreversible is True


def test_npm_install_flags_external() -> None:
    v = check_jurisdiction(command="npm install express")
    assert v.jurisdiction == Jurisdiction.EXTERNAL.value


def test_cve_keyword_flags_external() -> None:
    v = check_jurisdiction(action_description="investigate CVE-2024-1234")
    assert v.jurisdiction == Jurisdiction.EXTERNAL.value


def test_sensitive_in_filenames_caught() -> None:
    v = check_jurisdiction(
        action_description="refactor utils",
        filenames=["src/auth/session.ts"],
    )
    assert v.jurisdiction == Jurisdiction.USER.value


def test_jurisdiction_rank_ordering() -> None:
    assert (
        Jurisdiction.AI.rank
        < Jurisdiction.EXTERNAL.rank
        < Jurisdiction.USER.rank
    )
    assert (
        Jurisdiction.strictest(Jurisdiction.AI, Jurisdiction.EXTERNAL)
        == Jurisdiction.EXTERNAL
    )
    assert (
        Jurisdiction.strictest(Jurisdiction.EXTERNAL, Jurisdiction.USER)
        == Jurisdiction.USER
    )


# ── Grant ledger ─────────────────────────────────────────────────────


def test_grant_ledger_scoped_to_session() -> None:
    g = GrantLedger()
    g.grant("s1", "action:push", "2026-04-24T00:00:00Z")
    assert g.has_grant("s1", "action:push")
    assert not g.has_grant("s2", "action:push")


def test_grant_ledger_clears_session() -> None:
    g = GrantLedger()
    g.grant("s1", "action:push", "2026-04-24T00:00:00Z")
    g.clear_session("s1")
    assert not g.has_grant("s1", "action:push")


# ── Loop stop detector ──────────────────────────────────────────────


def test_loop_stops_on_repeated_failure() -> None:
    stop, reason = loop_should_stop(
        last_failure_signature="build_fail",
        failure_history=["build_fail", "build_fail"],
    )
    assert stop
    assert "repeated" in reason


def test_loop_stops_on_ac_mutation() -> None:
    stop, reason = loop_should_stop(
        last_failure_signature="qa_fail",
        failure_history=["qa_fail"],
        ac_mutation_needed=True,
    )
    assert stop
    assert "AC mutation" in reason


def test_loop_continues_on_new_failure() -> None:
    stop, _ = loop_should_stop(
        last_failure_signature="build_fail",
        failure_history=["build_fail"],
    )
    assert not stop


def test_loop_stops_on_irreversibility() -> None:
    stop, reason = loop_should_stop(
        last_failure_signature="",
        failure_history=[],
        irreversible_next=True,
    )
    assert stop
    assert "irreversible" in reason
