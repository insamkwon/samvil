"""Integration tests for orchestrator MCP tool wrappers."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from samvil_mcp.claim_ledger import ClaimLedger
from samvil_mcp.event_store_reader import read_events
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
    out = _run(get_next_stage("seed", "standard"))
    data = json.loads(out)
    assert data == {"next_stage": "design"}


def test_get_next_stage_tool_allows_explicit_council() -> None:
    out = _run(get_next_stage("seed", "standard", council_opt_in=True))
    data = json.loads(out)
    assert data == {"next_stage": "council"}


def test_should_skip_stage_tool_returns_bool() -> None:
    out = _run(should_skip_stage("council", "standard"))
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

    async def runner():
        sess = json.loads(
            await create_session(
                "orch-complete",
                "standard",
                project_root=str(project_root),
            )
        )
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

    rows = read_events(project_root)
    assert rows["ok"] is True
    assert len(rows["entries"]) == 1
    assert rows["entries"][0]["event_type"] == "interview_complete"
    assert rows["entries"][0]["stage"] == "interview"
    assert rows["entries"][0]["session_id"]
    assert rows["entries"][0]["data"]["verdict"] == "pass"


def test_save_event_file_lock_work_is_offloaded(tmp_path, monkeypatch) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    original = srv._append_project_event

    def slow_append(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(srv, "_append_project_event", slow_append)

    async def runner():
        sess = json.loads(
            await create_session(
                "nonblocking-event",
                "standard",
                project_root=str(project_root),
            )
        )
        started = asyncio.get_running_loop().time()

        async def ticker():
            await asyncio.sleep(0.01)
            return asyncio.get_running_loop().time() - started

        _, tick_delay = await asyncio.gather(
            save_event(sess["session_id"], "qa_started", "qa", "{}"),
            ticker(),
        )
        assert tick_delay < 0.1

    _run(runner())

def test_complete_stage_tool_returns_error_for_missing_session(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)

    out = _run(complete_stage("missing", "interview", "pass"))
    data = json.loads(out)
    assert data["status"] == "error"
    assert "not found" in data["error"]


def test_save_event_writes_project_events_ssot(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(await create_session(
            "events-ssot", "standard", project_root=str(project_root)
        ))
        assert sess["project_root"] == str(project_root.resolve())
        result = json.loads(await save_event(
            sess["session_id"],
            "interview_complete",
            "seed",
            '{"questions_asked": 4}',
        ))
        assert result["saved"] is True

    _run(runner())

    rows = read_events(project_root)
    assert rows["ok"] is True
    assert len(rows["entries"]) == 1
    assert rows["entries"][0] == {
        "timestamp": rows["entries"][0]["timestamp"],
        "event_type": "interview_complete",
        "stage": "interview",
        "session_id": rows["entries"][0]["session_id"],
        "data": {
            "questions_asked": 4,
            "event_type_raw": "interview_complete",
        },
    }


def test_save_event_fails_closed_when_project_events_append_fails(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    def fail_append(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(srv, "_append_project_event", fail_append)

    async def runner():
        sess = json.loads(
            await create_session(
                "events-ssot-failure",
                "standard",
                project_root=str(project_root),
            )
        )
        result = json.loads(
            await save_event(
                sess["session_id"],
                "build_stage_complete",
                "qa",
                "{}",
            )
        )
        state = json.loads(await get_orchestration_state(sess["session_id"]))
        stored_events = await (await srv.get_store()).get_events(sess["session_id"])

        assert result["saved"] is False
        assert result["canonical_saved"] is False
        assert result["db_rolled_back"] is True
        assert "disk full" in result["error"]
        assert state["current_stage"] == "interview"
        assert stored_events == []

    _run(runner())


def test_save_event_retry_after_canonical_failure_does_not_duplicate_db_event(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    original_append = srv._append_project_event
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("disk full")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(srv, "_append_project_event", fail_once)

    async def runner():
        sess = json.loads(
            await create_session(
                "events-ssot-retry",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        first = json.loads(await save_event(sid, "build_started", "build", "{}"))
        second = json.loads(await save_event(sid, "build_started", "build", "{}"))
        stored_events = await (await srv.get_store()).get_events(sid)
        canonical_events = read_events(project_root)["entries"]

        assert first["saved"] is False
        assert first["db_rolled_back"] is True
        assert second["saved"] is True
        assert len(stored_events) == 1
        assert len(canonical_events) == 1

    _run(runner())


def test_save_event_auto_claims_current_stage_entry_events(
    tmp_path,
    monkeypatch,
) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(await create_session(
            "entry-claims", "standard", project_root=str(project_root)
        ))
        sid = sess["session_id"]
        build = json.loads(await save_event(sid, "build_started", "build", "{}"))
        analyze = json.loads(await save_event(sid, "analyze_start", "analyze", "{}"))
        assert build["saved"] is True
        assert analyze["saved"] is True

    _run(runner())

    ledger = ClaimLedger(project_root / ".samvil" / "claims.jsonl")
    build_claims = ledger.query_by_subject("stage:build")
    analyze_claims = ledger.query_by_subject("stage:analyze")
    assert [claim.type for claim in build_claims] == ["evidence_posted"]
    assert [claim.type for claim in analyze_claims] == ["evidence_posted"]


def test_save_event_warns_when_project_root_cannot_be_resolved(
    tmp_path,
    monkeypatch,
    isolate_mcp_health_log: Path,
) -> None:
    _isolated_server(monkeypatch, tmp_path)

    from samvil_mcp import server as srv

    monkeypatch.setattr(srv, "_resolve_project_path", lambda _name: None)

    async def runner():
        sess = json.loads(await create_session("missing-events-root", "standard"))
        result = json.loads(await save_event(
            sess["session_id"], "interview_complete", "seed", "{}"
        ))
        assert result["saved"] is True

    _run(runner())

    health_rows = [
        json.loads(line)
        for line in isolate_mcp_health_log.read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        row["status"] == "warn" and row["tool"] == "save_event.events_ssot"
        for row in health_rows
    )
