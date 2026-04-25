"""Integration tests for orchestrator MCP tool wrappers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from samvil_mcp.claim_ledger import ClaimLedger
from samvil_mcp.server import (
    complete_stage,
    create_session,
    get_next_stage,
    get_orchestration_state,
    save_event,
    should_skip_stage,
    stage_can_proceed,
)


def _run(coro):
    return asyncio.run(coro)


def _isolated_server(monkeypatch, tmp_path: Path) -> None:
    from samvil_mcp import server as srv

    monkeypatch.setattr(srv, "DB_PATH", tmp_path / "samvil.db")
    monkeypatch.setattr(srv, "_store", None)


def test_get_next_stage_tool_returns_next_stage() -> None:
    out = _run(get_next_stage("seed", "minimal"))
    data = json.loads(out)
    assert data == {"next_stage": "design"}


def test_should_skip_stage_tool_returns_bool() -> None:
    out = _run(should_skip_stage("council", "minimal"))
    data = json.loads(out)
    assert data == {"skip": True}


def test_stage_can_proceed_tool_reads_session_events(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)

    async def runner():
        sess = json.loads(await create_session("orch-test", "standard"))
        sid = sess["session_id"]
        blocked = json.loads(await stage_can_proceed(sid, "seed"))
        assert blocked["can_proceed"] is False

        await save_event(sid, "interview_complete", "seed", "{}")
        allowed = json.loads(await stage_can_proceed(sid, "seed"))
        assert allowed["can_proceed"] is True

    _run(runner())


def test_get_orchestration_state_tool_reads_progress(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)

    async def runner():
        sess = json.loads(await create_session("orch-state", "minimal"))
        sid = sess["session_id"]
        await save_event(sid, "interview_complete", "seed", "{}")
        await save_event(sid, "seed_generated", "design", "{}")

        state = json.loads(await get_orchestration_state(sid))
        assert state["current_stage"] == "design"
        assert state["next_stage"] == "scaffold"
        assert state["completed_stages"] == ["interview", "seed"]
        assert state["skipped_stages"] == ["council", "deploy"]

    _run(runner())


def test_complete_stage_tool_emits_event_and_claim(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    from samvil_mcp import server as srv

    monkeypatch.setattr(srv, "_resolve_project_path", lambda _name: project_root)

    async def runner():
        sess = json.loads(await create_session("orch-complete", "standard"))
        sid = sess["session_id"]

        result = json.loads(await complete_stage(sid, "interview", "pass"))
        assert result["status"] == "ok"
        assert result["next_stage"] == "seed"
        assert result["event_id"]
        assert result["claim_id"]

        state = json.loads(await get_orchestration_state(sid))
        assert state["current_stage"] == "seed"
        assert state["completed_stages"] == ["interview"]

    _run(runner())

    claims = ClaimLedger(project_root / ".samvil" / "claims.jsonl")
    posted = claims.query_by_subject("gate:interview_exit")
    assert len(posted) == 1
    assert posted[0].statement == "verdict=pass via complete_stage"


def test_complete_stage_tool_returns_error_for_missing_session(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)

    out = _run(complete_stage("missing", "interview", "pass"))
    data = json.loads(out)
    assert data["status"] == "error"
    assert "not found" in data["error"]
