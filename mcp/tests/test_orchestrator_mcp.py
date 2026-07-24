"""Integration tests for orchestrator MCP tool wrappers."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

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
    project_root = tmp_path / "orch-test"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                "orch-test", "standard", project_root=str(project_root)
            )
        )
        sid = sess["session_id"]
        blocked = json.loads(await stage_can_proceed(sid, "seed"))
        assert blocked["can_proceed"] is False

        await save_event(sid, "interview_complete", "seed", "{}")
        still_blocked = json.loads(await stage_can_proceed(sid, "seed"))
        assert still_blocked["can_proceed"] is False

        await complete_stage(sid, "interview", "pass")
        allowed = json.loads(await stage_can_proceed(sid, "seed"))
        assert allowed["can_proceed"] is True

    _run(runner())


def test_stage_history_is_not_truncated_by_large_telemetry_volume(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv
    from samvil_mcp.models import EventType, Stage

    _isolated_server(monkeypatch, tmp_path)

    async def runner():
        sess = json.loads(await create_session("long-history", "standard"))
        store = await srv.get_store()
        await store.save_event(
            sess["session_id"],
            EventType.STAGE_CHANGE,
            Stage.SEED,
            {
                "event_type_raw": "interview_complete",
                "trusted_transition": True,
            },
        )
        for index in range(1001):
            await store.save_event(
                sess["session_id"],
                EventType.AC_VERDICT,
                Stage.BUILD,
                {"index": index, "trusted_transition": False},
            )

        allowed = json.loads(await stage_can_proceed(sess["session_id"], "seed"))
        assert allowed["can_proceed"] is True

    _run(runner())


def test_get_orchestration_state_tool_reads_progress(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "orch-state"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                "orch-state", "minimal", project_root=str(project_root)
            )
        )
        sid = sess["session_id"]
        await complete_stage(sid, "interview", "pass")
        await complete_stage(sid, "seed", "pass")

        state = json.loads(await get_orchestration_state(sid))
        assert state["current_stage"] == "design"
        assert state["next_stage"] == "scaffold"
        assert state["completed_stages"] == ["interview", "seed"]
        assert state["skipped_stages"] == ["council", "deploy"]

    _run(runner())


def test_same_timestamp_uses_later_inserted_stage_outcome(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import event_store
    from samvil_mcp import server as srv
    from samvil_mcp.models import EventType, Stage

    _isolated_server(monkeypatch, tmp_path)
    monkeypatch.setattr(
        event_store, "_now", lambda: "2026-07-25T00:00:00+00:00"
    )

    async def runner():
        sess = json.loads(await create_session("same-timestamp", "standard"))
        store = await srv.get_store()
        await store.save_event(
            sess["session_id"],
            EventType.BUILD_FAIL,
            Stage.BUILD,
            {"trusted_transition": True},
        )
        await store.save_event(
            sess["session_id"],
            EventType.BUILD_PASS,
            Stage.QA,
            {"trusted_transition": True},
        )

        state = json.loads(await get_orchestration_state(sess["session_id"]))
        assert "build" in state["completed_stages"]
        assert "build" not in state["failed_stages"]

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
        assert result["claim_saved"] is True

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


def test_complete_stage_rejects_out_of_order_stage_completion(
    tmp_path, monkeypatch
) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                "orch-out-of-order",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]

        result = json.loads(await complete_stage(sid, "qa", "pass"))
        state = json.loads(await get_orchestration_state(sid))
        stored_events = await (await __import__(
            "samvil_mcp.server", fromlist=["get_store"]
        ).get_store()).get_events(sid)

        assert result["status"] == "error"
        assert "current stage is interview" in result["error"]
        assert state["current_stage"] == "interview"
        assert state["completed_stages"] == []
        assert stored_events == []

    _run(runner())
    assert read_events(project_root)["entries"] == []


def test_complete_stage_fails_closed_when_canonical_event_append_fails(
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
                "orch-complete-failure",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]

        result = json.loads(await complete_stage(sid, "interview", "pass"))
        state = json.loads(await get_orchestration_state(sid))
        stored_events = await (await srv.get_store()).get_events(sid)

        assert result["status"] == "error"
        assert result["canonical_saved"] is False
        assert result["db_rolled_back"] is True
        assert state["current_stage"] == "interview"
        assert state["completed_stages"] == []
        assert stored_events == []

    _run(runner())

    claims = ClaimLedger(project_root / ".samvil" / "claims.jsonl")
    assert claims.query_by_subject("gate:interview_exit") == []
    assert read_events(project_root)["entries"] == []


@pytest.mark.parametrize("operation", ["save_event", "complete_stage"])
def test_canonical_event_non_oserror_still_compensates_database(
    tmp_path, monkeypatch, operation
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    def fail_decode(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")

    monkeypatch.setattr(srv, "_append_project_event", fail_decode)

    async def runner():
        sess = json.loads(
            await create_session(
                f"canonical-non-oserror-{operation}",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        if operation == "save_event":
            result = json.loads(await save_event(sid, "build_started", "build", "{}"))
            assert result["saved"] is False
        else:
            result = json.loads(await complete_stage(sid, "interview", "pass"))
            assert result["status"] == "error"

        state = json.loads(await get_orchestration_state(sid))
        stored_events = await (await srv.get_store()).get_events(sid)
        assert result["db_rolled_back"] is True
        assert state["current_stage"] == "interview"
        assert stored_events == []

    _run(runner())


def test_canonical_event_close_failure_removes_written_ghost_row(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    events_path = project_root / ".samvil" / "events.jsonl"
    original_open = Path.open

    class FailAfterClose:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.handle.__exit__(exc_type, exc, traceback)
            raise OSError("close failed after write")

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def __iter__(self):
            return iter(self.handle)

    def open_with_close_failure(path, mode="r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if Path(path) == events_path and mode == "a+":
            return FailAfterClose(handle)
        return handle

    monkeypatch.setattr(Path, "open", open_with_close_failure)

    async def runner():
        sess = json.loads(
            await create_session(
                "canonical-close-failure",
                "standard",
                project_root=str(project_root),
            )
        )
        result = json.loads(
            await complete_stage(sess["session_id"], "interview", "pass")
        )
        stored_events = await (await srv.get_store()).get_events(sess["session_id"])

        assert result["status"] == "error"
        assert result["db_rolled_back"] is True
        assert stored_events == []

    _run(runner())
    assert events_path.read_bytes() == b""


@pytest.mark.parametrize("operation", ["save_event", "complete_stage"])
def test_event_and_stage_update_are_atomic_and_retry_safe(
    tmp_path, monkeypatch, operation
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                f"atomic-{operation}",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]

        with sqlite3.connect(srv.DB_PATH) as db:
            db.execute(
                """CREATE TRIGGER fail_session_stage_update
                BEFORE UPDATE OF current_stage ON sessions
                BEGIN
                    SELECT RAISE(ABORT, 'stage update failed');
                END"""
            )

        if operation == "save_event":
            first = json.loads(
                await save_event(sid, "interview_complete", "seed", "{}")
            )
        else:
            first = json.loads(await complete_stage(sid, "interview", "pass"))

        state_after_failure = json.loads(await get_orchestration_state(sid))
        events_after_failure = await (await srv.get_store()).get_events(sid)

        if operation == "save_event":
            assert first["saved"] is True
            assert first["stage_transitioned"] is False
            assert state_after_failure["current_stage"] == "interview"
            assert state_after_failure["completed_stages"] == []
            assert len(events_after_failure) == 1
            assert len(read_events(project_root)["entries"]) == 1
            return

        assert first.get("saved", first.get("status") == "ok") is False
        assert state_after_failure["current_stage"] == "interview"
        assert state_after_failure["completed_stages"] == []
        assert events_after_failure == []
        assert read_events(project_root)["entries"] == []

        with sqlite3.connect(srv.DB_PATH) as db:
            db.execute("DROP TRIGGER fail_session_stage_update")

        if operation == "save_event":
            retry = json.loads(
                await save_event(sid, "interview_complete", "seed", "{}")
            )
            assert retry["saved"] is True
        else:
            retry = json.loads(await complete_stage(sid, "interview", "pass"))
            assert retry["status"] == "ok"

        state_after_retry = json.loads(await get_orchestration_state(sid))
        events_after_retry = await (await srv.get_store()).get_events(sid)

        assert state_after_retry["current_stage"] == "seed"
        assert state_after_retry["completed_stages"] == ["interview"]
        assert len(events_after_retry) == 1
        assert len(read_events(project_root)["entries"]) == 1

    _run(runner())


def test_complete_stage_reports_claim_degradation_without_reversing_completion(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    def fail_post(self, **kwargs):
        raise OSError("claims disk unavailable")

    monkeypatch.setattr(ClaimLedger, "post", fail_post)

    async def runner():
        sess = json.loads(
            await create_session(
                "orch-claim-degradation",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]

        result = json.loads(await complete_stage(sid, "interview", "pass"))
        state = json.loads(await get_orchestration_state(sid))
        stored_events = await (await srv.get_store()).get_events(sid)

        assert result["status"] == "ok"
        assert result["claim_id"] is None
        assert result["claim_saved"] is False
        assert result["claim_error"] == "claims disk unavailable"
        assert state["current_stage"] == "seed"
        assert state["completed_stages"] == ["interview"]
        assert len(stored_events) == 1

    _run(runner())

    assert len(read_events(project_root)["entries"]) == 1


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


def test_complete_stage_fails_closed_when_project_root_is_unresolved(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    monkeypatch.setattr(srv, "_resolve_project_path", lambda _name: None)

    async def runner():
        sess = json.loads(await create_session("missing-events-root", "standard"))
        result = json.loads(
            await complete_stage(sess["session_id"], "interview", "pass")
        )
        state = json.loads(await get_orchestration_state(sess["session_id"]))
        stored_events = await (await srv.get_store()).get_events(sess["session_id"])

        assert result["status"] == "error"
        assert "project root unresolved" in result["error"]
        assert state["current_stage"] == "interview"
        assert stored_events == []

    _run(runner())


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
            "trusted_transition": False,
        },
    }


def test_save_event_never_persists_raw_prompt_email_or_token(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    raw_prompt = "Build payroll for person@example.com token=fixture-secret"

    async def runner():
        sess = json.loads(await create_session(
            "redacted-events", "standard", project_root=str(project_root)
        ))
        result = json.loads(await save_event(
            sess["session_id"],
            raw_prompt,
            raw_prompt,
            json.dumps({"app": raw_prompt, "note": raw_prompt}),
        ))
        assert result["saved"] is True
        stored = await (await srv.get_store()).get_events(sess["session_id"])
        assert len(stored) == 1
        assert raw_prompt not in json.dumps(stored[0].data)
        assert stored[0].data["stage_raw"] == "redacted_stage"

    _run(runner())

    persisted = (project_root / ".samvil" / "events.jsonl").read_text(encoding="utf-8")
    claims_path = project_root / ".samvil" / "claims.jsonl"
    claims = claims_path.read_text(encoding="utf-8") if claims_path.exists() else ""
    assert raw_prompt not in persisted
    assert "person@example.com" not in persisted
    assert "fixture-secret" not in persisted
    assert "redacted_event_type" in persisted
    assert raw_prompt not in claims


def test_save_event_uses_valid_line_index_without_rescanning_jsonl(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv

    project_root = tmp_path / "project"
    project_root.mkdir()
    first = srv._append_project_event(
        project_root,
        timestamp="2026-07-25T00:00:00Z",
        event_type="build_started",
        stage="build",
        session_id="session-1",
        data={},
    )
    assert first == ".samvil/events.jsonl:1"

    def unexpected_scan(_handle):
        raise AssertionError("valid line index must avoid a full JSONL scan")

    monkeypatch.setattr(srv, "_scan_event_line_count", unexpected_scan)
    second = srv._append_project_event(
        project_root,
        timestamp="2026-07-25T00:00:01Z",
        event_type="build_pass",
        stage="build",
        session_id="session-1",
        data={},
    )
    assert second == ".samvil/events.jsonl:2"

    index = json.loads(
        (project_root / ".samvil" / "events.jsonl.index").read_text(encoding="utf-8")
    )
    assert index["line_count"] == 2


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


def test_save_event_stage_exit_stays_pending_without_gate_or_user_verification(
    tmp_path,
    monkeypatch,
) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                "exit-claim-evidence",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        started = json.loads(await save_event(sid, "build_started", "build", "{}"))
        completed = json.loads(
            await save_event(sid, "build_stage_complete", "qa", "{}")
        )
        assert started["saved"] is True
        assert completed["saved"] is True

    _run(runner())

    ledger = ClaimLedger(project_root / ".samvil" / "claims.jsonl")
    evidence_claims = [
        claim
        for claim in ledger.query_by_subject("stage:build")
        if claim.type == "evidence_posted"
    ]
    assert len(evidence_claims) == 2
    assert all(claim.status == "pending" for claim in evidence_claims)
    assert all(claim.verified_by is None for claim in evidence_claims)
    assert evidence_claims[-1].evidence == [".samvil/events.jsonl:2"]
    assert ledger.query_by_subject("gate:build_exit") == []


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
