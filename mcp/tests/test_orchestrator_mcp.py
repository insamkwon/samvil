"""Integration tests for orchestrator MCP tool wrappers."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

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


def test_read_chain_marker_recovers_rootless_legacy_session_before_read(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv

    project_root = tmp_path / "legacy-project"
    marker_path = project_root / ".samvil" / "next-skill.json"
    marker_path.parent.mkdir(parents=True)
    (project_root / "project.state.json").write_text(
        json.dumps({"session_id": "legacy-session", "current_stage": "build"}),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps({"next_skill": "samvil-build", "from_stage": "samvil-scaffold"}),
        encoding="utf-8",
    )

    class FakeStore:
        called = False

        async def recover_legacy_session_project_root(self, session_id, root):
            self.called = True
            assert session_id == "legacy-session"
            assert root == str(project_root)
            marker_path.write_text(
                json.dumps(
                    {"next_skill": "samvil-interview", "from_stage": "samvil"}
                ),
                encoding="utf-8",
            )
            return True

    fake_store = FakeStore()

    async def fake_get_store():
        return fake_store

    monkeypatch.setattr(srv, "get_store", fake_get_store)

    result = json.loads(_run(srv.read_chain_marker(str(project_root))))

    assert fake_store.called is True
    assert result["next_skill"] == "samvil-interview"


def test_rootless_recovery_rejects_a_cross_session_state_swap(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv
    from samvil_mcp.event_store import EventStore

    project_root = tmp_path / "legacy-project"
    marker_path = project_root / ".samvil" / "next-skill.json"
    state_path = project_root / "project.state.json"
    marker_path.parent.mkdir(parents=True)
    db_path = tmp_path / "samvil.db"
    store = EventStore(str(db_path))
    _run(store.initialize())
    session_a = _run(store.create_session("legacy-a"))
    session_b = _run(store.create_session("legacy-b"))
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE sessions SET current_stage = 'build'")
    state_path.write_text(
        json.dumps({"session_id": session_a.id, "current_stage": "build"}),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps({"next_skill": "samvil-build", "from_stage": "samvil-scaffold"}),
        encoding="utf-8",
    )

    class SwappingStore:
        async def recover_legacy_session_project_root(self, session_id, root):
            assert session_id == session_a.id
            state_path.write_text(
                json.dumps({"session_id": session_b.id, "current_stage": "build"}),
                encoding="utf-8",
            )
            return await store.recover_legacy_session_project_root(session_id, root)

    async def fake_get_store():
        return SwappingStore()

    monkeypatch.setattr(srv, "get_store", fake_get_store)

    assert _run(srv._recover_rootless_legacy_session(str(project_root))) is False
    recovered_a = _run(store.get_session(session_a.id))
    recovered_b = _run(store.get_session(session_b.id))
    assert recovered_a is not None and recovered_a.project_root == ""
    assert recovered_b is not None and recovered_b.project_root == ""
    assert json.loads(state_path.read_text()) == {
        "session_id": session_b.id,
        "current_stage": "build",
    }
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-build"


def test_rootless_recovery_accepts_the_legacy_state_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv
    from samvil_mcp.event_store import EventStore

    project_root = tmp_path / "legacy-project"
    legacy_state_path = project_root / ".samvil" / "state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    legacy_state_path.parent.mkdir(parents=True)
    db_path = tmp_path / "samvil.db"
    store = EventStore(str(db_path))
    _run(store.initialize())
    session = _run(store.create_session("legacy-app"))
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE sessions SET current_stage = 'build', stage_transition_id = 'old' "
            "WHERE id = ?",
            (session.id,),
        )
    legacy_state_path.write_text(
        json.dumps({"session_id": session.id, "current_stage": "build"}),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps({"next_skill": "samvil-build", "from_stage": "samvil-scaffold"}),
        encoding="utf-8",
    )

    async def fake_get_store():
        return store

    monkeypatch.setattr(srv, "get_store", fake_get_store)

    assert _run(srv._recover_rootless_legacy_session(str(project_root))) is True
    recovered = _run(store.get_session(session.id))
    assert recovered is not None
    assert recovered.project_root == str(project_root.resolve())
    assert recovered.current_stage.value == "interview"
    canonical_state = json.loads(
        (project_root / "project.state.json").read_text(encoding="utf-8")
    )
    assert canonical_state["session_id"] == session.id
    assert canonical_state["current_stage"] == "interview"
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-interview"


def _prepare_interview_exit(project_root: Path) -> None:
    (project_root / "interview-summary.md").write_text(
        "# Interview Summary\n\nValidated interview output.\n",
        encoding="utf-8",
    )
    ClaimLedger(project_root / ".samvil" / "claims.jsonl").post(
        type="gate_verdict",
        subject="interview_to_seed",
        statement="verdict=pass",
        authority_file="project.state.json",
        claimed_by="agent:test-interviewer",
        evidence=["interview-summary.md"],
        meta={"verdict": "pass"},
    )


def _write_valid_seed(
    project_root: Path,
    solution_type: str = "web-app",
) -> None:
    framework = {
        "automation": "python-script",
        "game": "phaser",
        "mobile-app": "expo",
    }.get(solution_type, "nextjs")
    core_experience = (
        {
            "primary_screen": "TaskBoard",
            "key_interactions": ["Create task"],
        }
        if solution_type in {"web-app", "dashboard"}
        else {
            "input": "User input",
            "output": "Verified output",
            "trigger": "User action",
        }
    )
    (project_root / "project.seed.json").write_text(
        json.dumps(
            {
                "schema_version": "3.2",
                "name": "evidence-demo",
                "description": "Exit evidence fixture",
                "solution_type": solution_type,
                "tech_stack": {"framework": framework},
                "core_experience": core_experience,
                "features": [
                    {
                        "name": "core-flow",
                        "priority": 1,
                        "acceptance_criteria": [
                            {"id": "F1.AC1", "description": "Flow completes"}
                        ],
                    }
                ],
                "constraints": ["No external API"],
                "out_of_scope": ["Team collaboration"],
                "version": 1,
            }
        ),
        encoding="utf-8",
    )


def _write_valid_blueprint(project_root: Path) -> None:
    (project_root / "project.blueprint.json").write_text(
        json.dumps(
            {
                "screens": ["TaskBoard"],
                "data_model": {"Task": {"title": "string"}},
                "api_routes": [],
                "state_management": "useState",
                "auth_strategy": "none",
                "key_libraries": ["react"],
                "component_structure": {
                    "shared_ui": ["Button"],
                    "feature_components": {"tasks": ["TaskList"]},
                },
                "routing": {"/": "TaskBoard"},
                "mobile_considerations": {},
            }
        ),
        encoding="utf-8",
    )


def _write_scaffold_result(project_root: Path) -> None:
    (project_root / ".samvil" / "scaffold-results.json").write_text(
        json.dumps({"all_passed": True}),
        encoding="utf-8",
    )


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
    _prepare_interview_exit(project_root)

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
        await store.save_event_and_update_stage(
            sess["session_id"],
            EventType.STAGE_CHANGE,
            Stage.SEED,
            {
                "event_type_raw": "interview_complete",
            },
            expected_stage=Stage.INTERVIEW,
        )
        for index in range(1001):
            await store.save_event(
                sess["session_id"],
                EventType.AC_VERDICT,
                Stage.BUILD,
                {"index": index, "trusted_transition": False},
            )

        original_get_events = store.get_events

        async def reject_unbounded_history(*args, **kwargs):
            if kwargs.get("limit") is None:
                raise AssertionError("orchestration must not materialize all telemetry")
            return await original_get_events(*args, **kwargs)

        monkeypatch.setattr(store, "get_events", reject_unbounded_history)
        original_get_orchestration_events = store.get_orchestration_events
        loaded_counts: list[int] = []

        async def track_orchestration_rows(*args, **kwargs):
            events = await original_get_orchestration_events(*args, **kwargs)
            loaded_counts.append(len(events))
            return events

        monkeypatch.setattr(
            store,
            "get_orchestration_events",
            track_orchestration_rows,
        )

        allowed = json.loads(await stage_can_proceed(sess["session_id"], "seed"))
        assert allowed["can_proceed"] is True
        assert loaded_counts == [1]

    _run(runner())


def test_get_orchestration_state_tool_reads_progress(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "orch-state"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)

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
        await store.save_event_and_update_stage(
            sess["session_id"],
            EventType.BUILD_FAIL,
            Stage.BUILD,
        )
        await store.save_event_and_update_stage(
            sess["session_id"],
            EventType.BUILD_PASS,
            Stage.QA,
        )

        state = json.loads(await get_orchestration_state(sess["session_id"]))
        assert "build" in state["completed_stages"]
        assert "build" not in state["failed_stages"]

    _run(runner())


def test_complete_stage_tool_emits_event_and_claim(tmp_path, monkeypatch) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prepare_interview_exit(project_root)

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


def test_complete_stage_rejects_interview_pass_without_exit_evidence(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "empty-project"
    project_root.mkdir()

    async def runner():
        sess = json.loads(
            await create_session(
                "empty-project",
                "standard",
                project_root=str(project_root),
            )
        )
        result = json.loads(
            await complete_stage(sess["session_id"], "interview", "pass")
        )
        state = json.loads(await get_orchestration_state(sess["session_id"]))
        stored_events = await (await srv.get_store()).get_events(sess["session_id"])

        assert result["status"] == "error"
        assert "interview exit evidence" in result["error"]
        assert state["current_stage"] == "interview"
        assert stored_events == []

    _run(runner())
    assert read_events(project_root)["entries"] == []


@pytest.mark.parametrize("latest_gate", ["missing", "block"])
def test_complete_stage_requires_latest_passing_interview_gate(
    tmp_path, monkeypatch, latest_gate
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / f"interview-gate-{latest_gate}"
    project_root.mkdir()
    (project_root / "interview-summary.md").write_text(
        "# Interview Summary\n\nReal output exists.\n",
        encoding="utf-8",
    )
    if latest_gate == "block":
        _prepare_interview_exit(project_root)
        ClaimLedger(project_root / ".samvil" / "claims.jsonl").post(
            type="gate_verdict",
            subject="interview_to_seed",
            statement="verdict=block",
            authority_file="project.state.json",
            claimed_by="agent:test-interviewer",
            evidence=["interview-summary.md"],
            meta={"verdict": "block"},
        )

    async def runner():
        sess = json.loads(
            await create_session(
                f"interview-gate-{latest_gate}",
                "standard",
                project_root=str(project_root),
            )
        )
        result = json.loads(
            await complete_stage(sess["session_id"], "interview", "pass")
        )
        stored_events = await (await srv.get_store()).get_events(sess["session_id"])

        assert result["status"] == "error"
        assert "latest interview_to_seed" in result["error"]
        assert stored_events == []

    _run(runner())


@pytest.mark.parametrize("stage", ["seed", "design", "scaffold", "build", "qa"])
def test_complete_stage_rejects_pass_without_stage_artifact(
    tmp_path, monkeypatch, stage
) -> None:
    from samvil_mcp import server as srv
    from samvil_mcp.models import EventType, Stage

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / f"missing-{stage}-evidence"
    project_root.mkdir()
    _prepare_interview_exit(project_root)

    async def runner():
        sess = json.loads(
            await create_session(
                f"missing-{stage}-evidence",
                "standard",
                project_root=str(project_root),
            )
        )
        store = await srv.get_store()
        sid = sess["session_id"]
        assert json.loads(await complete_stage(sid, "interview", "pass"))[
            "status"
        ] == "ok"

        if stage != "seed":
            _write_valid_seed(project_root)
            assert json.loads(await complete_stage(sid, "seed", "pass"))[
                "status"
            ] == "ok"
        if stage not in {"seed", "design"}:
            _write_valid_blueprint(project_root)
            assert json.loads(await complete_stage(sid, "design", "pass"))[
                "status"
            ] == "ok"
        if stage in {"build", "qa"}:
            _write_scaffold_result(project_root)
            assert json.loads(await complete_stage(sid, "scaffold", "pass"))[
                "status"
            ] == "ok"
        if stage == "qa":
            await store.save_event_and_update_stage(
                session_id=sid,
                event_type=EventType.BUILD_PASS,
                stage=Stage.QA,
                data={"trusted_transition": True},
                expected_stage=Stage.BUILD,
            )

        before = await store.get_events(sid)
        result = json.loads(await complete_stage(sid, stage, "pass"))
        stored_events = await store.get_events(sid)

        assert result["status"] == "error"
        assert f"{stage} exit evidence" in result["error"]
        assert len(stored_events) == len(before)

    _run(runner())


def test_build_completion_rejects_model_writable_static_receipt(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "static-build-receipt"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)
    _write_valid_blueprint(project_root)
    _write_scaffold_result(project_root)

    async def runner():
        sess = json.loads(
            await create_session(
                "static-build-receipt",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        for stage in ("interview", "seed", "design", "scaffold"):
            assert json.loads(await complete_stage(sid, stage, "pass"))[
                "status"
            ] == "ok"

        (project_root / ".samvil" / "build.log").write_text(
            "npm run build\nSAMVIL_EXIT:0\n",
            encoding="utf-8",
        )
        store = await srv.get_store()
        before = await store.get_events(sid, limit=None)
        result = json.loads(await complete_stage(sid, "build", "pass"))
        after = await store.get_events(sid, limit=None)

        assert result["status"] == "error"
        assert "trusted runtime" in result["error"]
        assert len(after) == len(before)

    _run(runner())


def test_qa_completion_rejects_self_authored_pass_without_runtime_receipt(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv
    from samvil_mcp.models import EventType, Stage

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "static-qa-receipt"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)
    _write_valid_blueprint(project_root)
    _write_scaffold_result(project_root)

    async def runner():
        sess = json.loads(
            await create_session(
                "static-qa-receipt",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        for stage in ("interview", "seed", "design", "scaffold"):
            assert json.loads(await complete_stage(sid, stage, "pass"))[
                "status"
            ] == "ok"

        store = await srv.get_store()
        await store.save_event_and_update_stage(
            session_id=sid,
            event_type=EventType.BUILD_PASS,
            stage=Stage.QA,
            data={"trusted_transition": True},
            expected_stage=Stage.BUILD,
        )
        (project_root / ".samvil" / "qa-results.json").write_text(
            json.dumps({"synthesis": {"verdict": "PASS"}}),
            encoding="utf-8",
        )
        (project_root / ".samvil" / "qa.log").write_text(
            "npm test\nSAMVIL_EXIT:0\n",
            encoding="utf-8",
        )
        (project_root / ".samvil" / "test-results.json").write_text(
            json.dumps(
                {
                    "stats": {
                        "expected": 1,
                        "flaky": 0,
                        "unexpected": 0,
                        "skipped": 0,
                    }
                }
            ),
            encoding="utf-8",
        )
        before = await store.get_events(sid, limit=None)
        result = json.loads(await complete_stage(sid, "qa", "pass"))
        after = await store.get_events(sid, limit=None)

        assert result["status"] == "error"
        assert "trusted runtime" in result["error"]
        assert len(after) == len(before)

    _run(runner())


def test_design_completion_rejects_nonempty_but_invalid_blueprint(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "invalid-blueprint"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)
    (project_root / "project.blueprint.json").write_text(
        json.dumps({"x": 1}),
        encoding="utf-8",
    )

    async def runner():
        sess = json.loads(
            await create_session(
                "invalid-blueprint",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        for stage in ("interview", "seed"):
            assert json.loads(await complete_stage(sid, stage, "pass"))[
                "status"
            ] == "ok"

        store = await srv.get_store()
        before = await store.get_events(sid, limit=None)
        result = json.loads(await complete_stage(sid, "design", "pass"))
        after = await store.get_events(sid, limit=None)

        assert result["status"] == "error"
        assert "design exit evidence is invalid" in result["error"]
        assert len(after) == len(before)

    _run(runner())


@pytest.mark.parametrize(
    ("solution_type", "blueprint"),
    [
        (
            "web-app",
            {
                "screens": ["Home"],
                "data_model": {},
                "api_routes": [],
                "state_management": "useState",
                "auth_strategy": "none",
                "key_libraries": [],
                "component_structure": {},
                "routing": {},
            },
        ),
        (
            "dashboard",
            {
                "screens": ["Dashboard"],
                "data_model": {},
                "api_routes": [],
                "state_management": "useState",
                "auth_strategy": "none",
                "key_libraries": [],
                "component_structure": {},
                "routing": {},
            },
        ),
        (
            "mobile-app",
            {
                "screens": ["HomeScreen"],
                "navigation": {},
                "data_model": {},
                "state_management": "zustand",
                "native_modules": [],
                "key_libraries": [],
                "component_structure": {},
            },
        ),
        (
            "automation",
            {
                "entry_point": "src/main.py",
                "modules": {},
                "fixtures": {},
                "dependencies": [],
                "error_handling": "retry_with_logging",
                "execution": {},
            },
        ),
        (
            "game",
            {
                "scenes": ["GameScene"],
                "entities": [],
                "game_config": {},
                "assets": {},
                "scene_flow": {},
                "key_libraries": [],
                "state_management": "phaser-scene",
                "component_structure": {},
            },
        ),
    ],
)
def test_blueprint_validator_rejects_empty_nested_contracts(
    solution_type, blueprint
) -> None:
    from samvil_mcp.server import (
        OrchestratorError,
        _validate_blueprint_exit_evidence,
    )

    with pytest.raises(OrchestratorError, match="design exit evidence is invalid"):
        _validate_blueprint_exit_evidence(blueprint, solution_type)


@pytest.mark.parametrize(
    ("solution_type", "case"),
    [
        ("web-app", "missing_mobile_considerations"),
        ("web-app", "invalid_state_management"),
        ("web-app", "invalid_api_route"),
        ("web-app", "unknown_routing_target"),
        ("dashboard", "invalid_data_source_type"),
        ("dashboard", "unknown_routing_target"),
        ("mobile-app", "invalid_navigation_type"),
        ("mobile-app", "invalid_tab"),
        ("mobile-app", "empty_tabs"),
        ("mobile-app", "unknown_tab_screen"),
        ("automation", "invalid_dependency"),
        ("automation", "invalid_execution_type"),
        ("automation", "invalid_error_handling"),
        ("game", "invalid_scene_flow"),
        ("game", "unknown_scene_source"),
        ("game", "unknown_scene_target"),
        ("game", "invalid_asset"),
    ],
)
def test_blueprint_validator_rejects_invalid_leaf_contracts(
    solution_type: str,
    case: str,
) -> None:
    from samvil_mcp.server import (
        OrchestratorError,
        _validate_blueprint_exit_evidence,
    )

    blueprints = {
        "web-app": {
            "screens": ["Home"],
            "data_model": {"Task": {"id": "string"}},
            "api_routes": [],
            "state_management": "useState",
            "auth_strategy": "none",
            "key_libraries": ["react"],
            "component_structure": {
                "shared_ui": ["Button"],
                "feature_components": {"tasks": ["TaskList"]},
            },
            "routing": {"/": "Home"},
            "mobile_considerations": {},
        },
        "dashboard": {
            "screens": ["DashboardOverview"],
            "data_model": {"Metric": {"value": "number"}},
            "api_routes": [],
            "state_management": "useState",
            "auth_strategy": "none",
            "key_libraries": ["recharts"],
            "component_structure": {
                "shared_ui": ["Card"],
                "feature_components": {"charts": ["LineChart"]},
            },
            "routing": {"/": "DashboardOverview"},
            "chart_components": ["LineChart"],
            "data_sources": [
                {"name": "primary", "type": "localStorage", "refresh_interval": None}
            ],
            "refresh_interval": None,
            "alert_thresholds": [],
            "mobile_considerations": {},
        },
        "mobile-app": {
            "screens": ["HomeScreen"],
            "navigation": {
                "type": "tabs",
                "tabs": [{"name": "Home", "screen": "HomeScreen", "icon": "home"}],
            },
            "data_model": {"Task": {"id": "string"}},
            "state_management": "zustand",
            "native_modules": [],
            "key_libraries": ["expo-router", "zustand"],
            "component_structure": {
                "shared_ui": ["Button"],
                "feature_components": {"tasks": ["TaskList"]},
            },
        },
        "automation": {
            "entry_point": "src/main.py",
            "modules": {"core": ["main.py"], "utils": ["logger.py"]},
            "fixtures": {
                "input": "fixtures/input/",
                "expected": "fixtures/expected/",
            },
            "dependencies": [],
            "error_handling": "retry_with_logging",
            "execution": {"type": "cli", "schedule": None},
        },
        "game": {
            "scenes": ["BootScene", "GameScene"],
            "entities": ["Player"],
            "game_config": {
                "width": 800,
                "height": 600,
                "physics": "arcade",
                "input": "keyboard",
            },
            "assets": {"sprites": [], "audio": []},
            "scene_flow": {"BootScene": "GameScene"},
            "key_libraries": ["phaser"],
            "state_management": "phaser-scene",
            "component_structure": {"scenes": [], "entities": [], "config": []},
        },
    }
    blueprint = blueprints[solution_type]
    if case == "missing_mobile_considerations":
        blueprint.pop("mobile_considerations")
    elif case == "invalid_state_management":
        blueprint["state_management"] = "redux-ish"
    elif case == "invalid_api_route":
        blueprint["api_routes"] = [42]
    elif case == "unknown_routing_target":
        blueprint["routing"]["/"] = "MissingScreen"
    elif case == "invalid_data_source_type":
        blueprint["data_sources"][0]["type"] = "spreadsheet-ish"
    elif case == "invalid_navigation_type":
        blueprint["navigation"]["type"] = "carousel"
    elif case == "invalid_tab":
        blueprint["navigation"]["tabs"] = [{"name": "Home"}]
    elif case == "empty_tabs":
        blueprint["navigation"]["tabs"] = []
    elif case == "unknown_tab_screen":
        blueprint["navigation"]["tabs"][0]["screen"] = "MissingScreen"
    elif case == "invalid_dependency":
        blueprint["dependencies"] = [42]
    elif case == "invalid_execution_type":
        blueprint["execution"]["type"] = "daemon-ish"
    elif case == "invalid_error_handling":
        blueprint["error_handling"] = "ignore_everything"
    elif case == "invalid_scene_flow":
        blueprint["scene_flow"] = {"BootScene": 42}
    elif case == "unknown_scene_source":
        blueprint["scene_flow"] = {"MissingScene": "GameScene"}
    elif case == "unknown_scene_target":
        blueprint["scene_flow"] = {"BootScene": "MissingScene"}
    elif case == "invalid_asset":
        blueprint["assets"]["sprites"] = [42]

    with pytest.raises(OrchestratorError, match="design exit evidence is invalid"):
        _validate_blueprint_exit_evidence(blueprint, solution_type)


@pytest.mark.parametrize(
    ("solution_type", "blueprint"),
    [
        (
            "dashboard",
            {
                "screens": ["DashboardOverview"],
                "data_model": {"Metric": {"value": "number"}},
                "api_routes": [],
                "state_management": "useState",
                "auth_strategy": "none",
                "key_libraries": ["recharts"],
                "component_structure": {
                    "shared_ui": ["Card"],
                    "feature_components": {"charts": ["LineChart"]},
                },
                "routing": {"/": "DashboardOverview"},
                "chart_components": ["LineChart"],
                "data_sources": [
                    {
                        "name": "primary",
                        "type": "localStorage",
                        "refresh_interval": None,
                    }
                ],
                "refresh_interval": None,
                "alert_thresholds": [],
                "mobile_considerations": {},
            },
        ),
        (
            "automation",
            {
                "entry_point": "src/main.py",
                "modules": {"core": ["main.py"], "utils": ["logger.py"]},
                "fixtures": {
                    "input": "fixtures/input/",
                    "expected": "fixtures/expected/",
                },
                "dependencies": [],
                "error_handling": "retry_with_logging",
                "execution": {"type": "cli", "schedule": None},
            },
        ),
        (
            "game",
            {
                "scenes": ["BootScene", "MenuScene", "GameScene", "GameOverScene"],
                "entities": ["Player"],
                "game_config": {
                    "width": 800,
                    "height": 600,
                    "physics": "arcade",
                    "input": "keyboard",
                },
                "assets": {"sprites": [], "audio": []},
                "scene_flow": {"BootScene": "MenuScene"},
                "key_libraries": ["phaser"],
                "state_management": "phaser-scene",
                "component_structure": {"scenes": [], "entities": [], "config": []},
            },
        ),
        (
            "mobile-app",
            {
                "screens": ["HomeScreen"],
                "navigation": {
                    "type": "tabs",
                    "tabs": [
                        {"name": "Home", "screen": "HomeScreen", "icon": "home"}
                    ],
                },
                "data_model": {"Task": {"id": "string"}},
                "state_management": "zustand",
                "native_modules": [],
                "key_libraries": ["expo-router", "zustand"],
                "component_structure": {"shared_ui": [], "feature_components": {}},
            },
        ),
    ],
)
def test_design_completion_accepts_canonical_blueprint_per_solution_type(
    tmp_path, monkeypatch, solution_type, blueprint
) -> None:
    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / solution_type
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root, solution_type)
    (project_root / "project.blueprint.json").write_text(
        json.dumps(blueprint),
        encoding="utf-8",
    )

    async def runner():
        sess = json.loads(
            await create_session(
                solution_type,
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        for stage in ("interview", "seed", "design"):
            assert json.loads(await complete_stage(sid, stage, "pass"))[
                "status"
            ] == "ok"

    _run(runner())


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
    _prepare_interview_exit(project_root)

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
    _prepare_interview_exit(project_root)

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
    _prepare_interview_exit(project_root)
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
    _prepare_interview_exit(project_root)

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


def test_concurrent_stage_completion_creates_only_one_trusted_transition(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "concurrent-completion"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)

    async def runner():
        sess = json.loads(
            await create_session(
                "concurrent-completion",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        assert json.loads(await complete_stage(sid, "interview", "pass"))[
            "status"
        ] == "ok"

        store = await srv.get_store()
        original_get_events = store.get_events
        original_get_orchestration_events = store.get_orchestration_events
        both_prechecked = asyncio.Event()
        arrivals = 0

        async def synchronized_get_orchestration_events(*args, **kwargs):
            nonlocal arrivals
            arrivals += 1
            if arrivals == 2:
                both_prechecked.set()
            await both_prechecked.wait()
            return await original_get_orchestration_events(*args, **kwargs)

        monkeypatch.setattr(
            store,
            "get_orchestration_events",
            synchronized_get_orchestration_events,
        )
        results = [
            json.loads(item)
            for item in await asyncio.gather(
                complete_stage(sid, "seed", "pass"),
                complete_stage(sid, "seed", "pass"),
            )
        ]

        assert arrivals == 2
        assert sorted(item["status"] for item in results) == ["error", "ok"]
        stored_events = await original_get_events(sid, limit=None)
        assert [event.data["event_type_raw"] for event in stored_events].count(
            "seed_generated"
        ) == 1

    _run(runner())
    canonical = read_events(project_root)["entries"]
    assert [item["event_type"] for item in canonical].count("seed_generated") == 1
    claims = ClaimLedger(project_root / ".samvil" / "claims.jsonl")
    assert len(claims.query_by_subject("gate:seed_exit")) == 1


def test_failed_canonical_append_blocks_dependent_transition_until_compensation(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "canonical-transition-lock"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)
    append_started = Event()
    release_append = Event()
    real_append = srv._append_project_event

    def delayed_failed_append(*args, **kwargs):
        if kwargs.get("event_type") == "interview_complete":
            append_started.set()
            assert release_append.wait(timeout=2)
            raise OSError("interview canonical append failed")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(srv, "_append_project_event", delayed_failed_append)

    async def runner():
        sess = json.loads(
            await create_session(
                "canonical-transition-lock",
                "standard",
                project_root=str(project_root),
            )
        )
        sid = sess["session_id"]
        interview_task = asyncio.create_task(
            complete_stage(sid, "interview", "pass")
        )
        assert await asyncio.to_thread(append_started.wait, 2)
        seed_task = asyncio.create_task(complete_stage(sid, "seed", "pass"))
        await asyncio.sleep(0.05)
        assert seed_task.done() is False
        release_append.set()

        interview_result, seed_result = [
            json.loads(item)
            for item in await asyncio.gather(interview_task, seed_task)
        ]
        session = await (await srv.get_store()).get_session(sid)
        events = await (await srv.get_store()).get_events(sid, limit=None)

        assert interview_result["status"] == "error"
        assert interview_result["db_rolled_back"] is True
        assert seed_result["status"] == "error"
        assert session is not None and session.current_stage.value == "interview"
        assert events == []

    _run(runner())
    assert read_events(project_root)["entries"] == []


@pytest.mark.skipif(os.name != "posix", reason="cross-process flock requires POSIX")
def test_complete_stage_serializes_compensation_across_mcp_processes(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "cross-process-transition-lock"
    project_root.mkdir()
    _prepare_interview_exit(project_root)
    _write_valid_seed(project_root)
    signal_path = tmp_path / "append-started"
    release_path = tmp_path / "release-append"
    interview_result_path = tmp_path / "interview-result.json"
    seed_result_path = tmp_path / "seed-result.json"

    async def create_test_session() -> str:
        result = json.loads(
            await create_session(
                "cross-process-transition-lock",
                "standard",
                project_root=str(project_root),
            )
        )
        return result["session_id"]

    sid = _run(create_test_session())
    env = os.environ.copy()
    env["SAMVIL_MCP_HEALTH_PATH"] = str(tmp_path / "mcp-health.jsonl")
    interview_script = """
import asyncio
import sys
import time
from pathlib import Path
from samvil_mcp import server as srv

db_path, session_id, signal_path, release_path, result_path = sys.argv[1:]
srv.DB_PATH = Path(db_path)
srv._store = None

def fail_after_db_commit(*args, **kwargs):
    Path(signal_path).write_text("started", encoding="utf-8")
    while not Path(release_path).exists():
        time.sleep(0.01)
    raise OSError("interview canonical append failed")

srv._append_project_event = fail_after_db_commit
result = asyncio.run(srv.complete_stage(session_id, "interview", "pass"))
Path(result_path).write_text(result, encoding="utf-8")
"""
    seed_script = """
import asyncio
import sys
from pathlib import Path
from samvil_mcp import server as srv

db_path, session_id, result_path = sys.argv[1:]
srv.DB_PATH = Path(db_path)
srv._store = None
result = asyncio.run(srv.complete_stage(session_id, "seed", "pass"))
Path(result_path).write_text(result, encoding="utf-8")
"""

    interview_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            interview_script,
            str(srv.DB_PATH),
            sid,
            str(signal_path),
            str(release_path),
            str(interview_result_path),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    seed_process: subprocess.Popen[str] | None = None
    try:
        deadline = time.monotonic() + 5
        while not signal_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert signal_path.exists(), interview_process.communicate(timeout=1)

        seed_process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                seed_script,
                str(srv.DB_PATH),
                sid,
                str(seed_result_path),
            ],
            cwd=Path(__file__).parents[2],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        seed_deadline = time.monotonic() + 3
        while not seed_result_path.exists() and time.monotonic() < seed_deadline:
            time.sleep(0.01)
        assert not seed_result_path.exists(), (
            "dependent transition escaped the cross-process compensation boundary"
        )
        release_path.write_text("release", encoding="utf-8")
        interview_stdout, interview_stderr = interview_process.communicate(timeout=5)
        seed_stdout, seed_stderr = seed_process.communicate(timeout=5)
        assert interview_process.returncode == 0, interview_stdout + interview_stderr
        assert seed_process.returncode == 0, seed_stdout + seed_stderr
    finally:
        release_path.touch()
        for process in (interview_process, seed_process):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    interview_result = json.loads(interview_result_path.read_text(encoding="utf-8"))
    seed_result = json.loads(seed_result_path.read_text(encoding="utf-8"))
    assert interview_result["status"] == "error"
    assert interview_result["db_rolled_back"] is True
    assert seed_result["status"] == "error"
    session = _run((srv.get_store()))
    persisted_session = _run(session.get_session(sid))
    persisted_events = _run(session.get_events(sid, limit=None))
    assert persisted_session is not None
    assert persisted_session.current_stage.value == "interview"
    assert persisted_events == []
    assert read_events(project_root)["entries"] == []


def test_complete_stage_reports_claim_degradation_without_reversing_completion(
    tmp_path, monkeypatch
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prepare_interview_exit(project_root)

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


def test_save_event_redacts_credentials_embedded_in_plain_strings(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    secrets = {
        "access": "-".join(("access", "fixture", "value")),
        "client": "-".join(("client", "fixture", "value")),
        "basic": "".join(("QWxh", "ZGRp", "bjpvcGVu", "IHNlc2FtZQ==")),
        "cookie": "-".join(("session", "fixture", "value")),
        "restricted": "_".join(("rk", "live", "fixture", "restricted", "value")),
    }
    raw_note = (
        f"access_token={secrets['access']} "
        f"client_secret={secrets['client']} "
        f"Authorization: Basic {secrets['basic']} "
        f"Cookie: session={secrets['cookie']} "
        f"STRIPE_RESTRICTED_KEY={secrets['restricted']}"
    )

    async def runner():
        sess = json.loads(
            await create_session(
                "embedded-credentials",
                "standard",
                project_root=str(project_root),
            )
        )
        result = json.loads(
            await save_event(
                sess["session_id"],
                "build_started",
                "build",
                json.dumps({"note": raw_note}),
            )
        )
        assert result["saved"] is True
        stored = await (await srv.get_store()).get_events(sess["session_id"])
        return json.dumps(stored[0].data)

    stored_data = _run(runner())
    canonical = (project_root / ".samvil" / "events.jsonl").read_text(
        encoding="utf-8"
    )
    for secret in secrets.values():
        assert secret not in stored_data
        assert secret not in canonical


def test_save_event_redacts_quoted_json_and_nonstandard_authorization(
    tmp_path,
    monkeypatch,
) -> None:
    from samvil_mcp import server as srv

    _isolated_server(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    secrets = {
        "access": "-".join(("json", "access", "value")),
        "credential": "".join(("AKIA", "FIXTURE", "CREDENTIAL")),
        "signature": "".join(("dead", "beef", "fixture")),
    }
    raw_note = (
        '{"access_token":"'
        + secrets["access"]
        + '","Authorization":"Digest Credential='
        + secrets["credential"]
        + ", Signature="
        + secrets["signature"]
        + '"}'
    )

    async def runner():
        sess = json.loads(
            await create_session(
                "quoted-credentials",
                "standard",
                project_root=str(project_root),
            )
        )
        await save_event(
            sess["session_id"],
            "build_started",
            "build",
            json.dumps({"note": raw_note}),
        )
        stored = await (await srv.get_store()).get_events(sess["session_id"])
        return json.dumps(stored[0].data)

    stored_data = _run(runner())
    canonical = (project_root / ".samvil" / "events.jsonl").read_text(
        encoding="utf-8"
    )
    for secret in secrets.values():
        assert secret not in stored_data
        assert secret not in canonical


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


def test_save_event_separates_existing_jsonl_tail_without_newline(tmp_path) -> None:
    from samvil_mcp import server as srv

    project_root = tmp_path / "project"
    events_path = project_root / ".samvil" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-25T00:00:00Z",
                "event_type": "build_started",
                "stage": "build",
                "session_id": "session-1",
                "data": {},
            }
        ),
        encoding="utf-8",
    )

    evidence = srv._append_project_event(
        project_root,
        timestamp="2026-07-25T00:00:01Z",
        event_type="build_pass",
        stage="build",
        session_id="session-1",
        data={},
    )

    assert evidence == ".samvil/events.jsonl:2"
    entries = read_events(project_root)["entries"]
    assert [entry["event_type"] for entry in entries] == [
        "build_started",
        "build_pass",
    ]


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
