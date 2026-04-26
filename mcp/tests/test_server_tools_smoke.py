"""v3.1.0 Polish #7 — runtime smoke tests for v3.1.0 MCP tools.

These go through the async tool functions directly (as opposed to unit tests
against helper modules) so we catch wiring regressions between `server.py`
and the underlying modules — the kind of bug that unit tests pass but the
real MCP round-trip fails.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from samvil_mcp.server import (
    build_reawake_message,
    get_tier_phases,
    heartbeat_state,
    increment_stall_recovery_count,
    is_state_stalled,
    materialize_qa_synthesis,
    suggest_ac_split,
    synthesize_qa_evidence,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ── Tier phases (Polish #5) ────────────────────────────────────


def test_get_tier_phases_returns_expected_structure() -> None:
    out = _run(get_tier_phases(tier="thorough"))
    data = json.loads(out)
    assert data["tier"] == "thorough"
    assert "phases" in data and isinstance(data["phases"], list)
    assert data["ambiguity_target"] == 0.02
    assert "deep" in data["all_tiers"]


def test_get_tier_phases_deep_includes_domain_deep() -> None:
    data = json.loads(_run(get_tier_phases(tier="deep")))
    assert "domain_deep" in data["phases"]
    assert data["ambiguity_target"] == 0.005


def test_synthesize_qa_evidence_tool_returns_central_verdict() -> None:
    out = _run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })))
    data = json.loads(out)
    assert data["gate"] == "qa_synthesis"
    assert data["verdict"] == "REVISE"
    assert data["next_action"] == "replace stubs or hardcoded paths with real implementation"


def test_materialize_qa_synthesis_tool_writes_results(tmp_path: Path) -> None:
    synthesis = json.loads(_run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]}
        ]},
        "pass3": {"verdict": "PASS"},
    }))))

    out = _run(materialize_qa_synthesis(project_root=str(tmp_path), synthesis_json=json.dumps(synthesis)))
    data = json.loads(out)

    assert data["status"] == "ok"
    assert data["verdict"] == "PASS"
    assert (tmp_path / ".samvil" / "qa-results.json").exists()
    assert (tmp_path / ".samvil" / "qa-report.md").exists()


# ── AC split (v3-011) ──────────────────────────────────────────


def test_suggest_ac_split_short_desc_returns_no_split() -> None:
    data = json.loads(_run(suggest_ac_split(description="User can add")))
    assert data["should_split"] is False


def test_suggest_ac_split_compound_returns_split() -> None:
    desc = (
        "Authenticated user can create, edit, and delete their own saved "
        "workouts, and share them with other users"
    )
    data = json.loads(_run(suggest_ac_split(description=desc)))
    assert data["should_split"] is True


# ── heartbeat + stall round-trip (v3-016) ─────────────────────


def test_heartbeat_and_stall_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"

    # 1. heartbeat creates the file
    out1 = _run(heartbeat_state(state_path=str(state_path), now_iso="2026-04-21T12:00:00+00:00"))
    d1 = json.loads(out1)
    assert d1["ok"] is True
    assert d1["last_progress_at"] == "2026-04-21T12:00:00+00:00"

    # 2. within threshold: not stalled
    out2 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:03:00+00:00",
        threshold_seconds=300,
    ))
    d2 = json.loads(out2)
    assert d2["stalled"] is False
    assert d2["elapsed_seconds"] == 180.0

    # 3. past threshold: stalled
    out3 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:06:00+00:00",
        threshold_seconds=300,
    ))
    d3 = json.loads(out3)
    assert d3["stalled"] is True

    # 4. recovery count bumps
    out4 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d4 = json.loads(out4)
    assert d4["ok"] is True
    assert d4["count"] == 1

    out5 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d5 = json.loads(out5)
    assert d5["count"] == 2

    # 5. reawake message
    out6 = _run(build_reawake_message(
        stage="design",
        detail_json=out3,  # stalled verdict
        count=1,
    ))
    d6 = json.loads(out6)
    assert d6["ok"] is True
    assert "design" in d6["message"]


def test_is_state_stalled_missing_file_does_not_raise(tmp_path: Path) -> None:
    out = _run(is_state_stalled(state_path=str(tmp_path / "missing.json")))
    data = json.loads(out)
    assert data["stalled"] is False
    assert data["reason"] == "state_missing"
