"""Tests for SAMVIL EventStore."""

import asyncio
import json
import os
import sqlite3
import tempfile

import pytest
import pytest_asyncio
import aiosqlite

from samvil_mcp.event_store import EventStore, _migration_plan
from samvil_mcp.models import EventType, Stage


@pytest_asyncio.fixture
async def store():
    """Create a temporary EventStore for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = EventStore(path)
    await s.initialize()
    yield s
    os.unlink(path)


@pytest.mark.asyncio
async def test_create_and_get_session(store: EventStore):
    session = await store.create_session("test-app", "standard")
    assert session.id
    assert session.project_name == "test-app"
    assert session.samvil_tier == "standard"
    assert session.current_stage == Stage.INTERVIEW

    fetched = await store.get_session(session.id)
    assert fetched is not None
    assert fetched.project_name == "test-app"


@pytest.mark.asyncio
async def test_find_session_by_project(store: EventStore):
    await store.create_session("app-one", "minimal")
    await store.create_session("app-two", "standard")

    found = await store.find_session_by_project("app-one")
    assert found is not None
    assert found.project_name == "app-one"

    not_found = await store.find_session_by_project("app-three")
    assert not_found is None


@pytest.mark.asyncio
async def test_stage_transition_keeps_pending_canonical_event_for_crash_recovery(
    store: EventStore,
) -> None:
    session = await store.create_session("crash-recovery")

    transition = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_END,
        Stage.SEED,
        data={"event_type_raw": "interview_complete"},
        expected_stage=Stage.INTERVIEW,
    )

    pending = await store.get_pending_project_events(session.id)
    assert [item["event_id"] for item in pending] == [transition.event.id]
    assert pending[0]["stage"] == "seed"


@pytest.mark.asyncio
async def test_find_session_by_project_root_disambiguates_same_name(store: EventStore):
    first = await store.create_session("same-app", "standard", "/tmp/team-a/same-app")
    second = await store.create_session("same-app", "standard", "/tmp/team-b/same-app")

    found_first = await store.find_session_by_project(
        "same-app", "/tmp/team-a/same-app"
    )
    found_second = await store.find_session_by_project(
        "same-app", "/tmp/team-b/same-app"
    )

    assert found_first is not None and found_first.id == first.id
    assert found_second is not None and found_second.id == second.id
    assert await store.find_session_by_project("same-app") is None


@pytest.mark.asyncio
async def test_initialize_adds_project_root_to_existing_sessions_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                seed_version INTEGER DEFAULT 1,
                current_stage TEXT DEFAULT 'interview',
                samvil_tier TEXT DEFAULT 'standard',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    legacy_store = EventStore(str(db_path))
    await legacy_store.initialize()

    with sqlite3.connect(db_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
    assert "project_root" in columns
    assert "stage_transition_id" in columns


def test_migration_plan_only_contains_missing_schema_changes() -> None:
    plan = _migration_plan(
        events_columns={"id", "token_count"},
        sessions_columns={"id", "samvil_tier"},
    )

    assert plan == [
        "ALTER TABLE events ADD COLUMN trusted_transition INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN project_root TEXT DEFAULT ''",
        "ALTER TABLE sessions ADD COLUMN stage_transition_id TEXT DEFAULT ''",
    ]

    legacy = _migration_plan(
        events_columns={"id"},
        sessions_columns={"id", "agent_tier"},  # glossary-allow: legacy fixture
    )
    assert legacy == [
        "ALTER TABLE events ADD COLUMN token_count INTEGER DEFAULT NULL",
        "ALTER TABLE events ADD COLUMN trusted_transition INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions RENAME COLUMN agent_tier TO samvil_tier",  # glossary-allow: expected migration
        "ALTER TABLE sessions ADD COLUMN project_root TEXT DEFAULT ''",
        "ALTER TABLE sessions ADD COLUMN stage_transition_id TEXT DEFAULT ''",
    ]


def _create_legacy_trust_db(db_path, project_root) -> None:
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL,
                project_root TEXT DEFAULT '', seed_version INTEGER DEFAULT 1,
                current_stage TEXT DEFAULT 'interview',
                stage_transition_id TEXT DEFAULT '',
                samvil_tier TEXT DEFAULT 'standard', created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                event_type TEXT NOT NULL, stage TEXT NOT NULL,
                data TEXT DEFAULT '{}', token_count INTEGER DEFAULT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE seed_versions (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                version INTEGER NOT NULL, seed_json TEXT NOT NULL,
                change_summary TEXT DEFAULT '', created_at TEXT NOT NULL,
                UNIQUE(session_id, version)
            );
            CREATE INDEX idx_events_trusted_transition
            ON events(session_id, json_extract(data, '$.trusted_transition'), timestamp DESC);
            """
        )
        db.execute(
            """INSERT INTO sessions
            (id, project_name, project_root, current_stage, stage_transition_id,
             created_at, updated_at)
            VALUES ('session', 'legacy-app', ?, 'build', 'legacy',
                    '2026-07-25', '2026-07-25')""",
            (str(project_root),),
        )
        db.execute(
            """INSERT INTO events
            (id, session_id, event_type, stage, data, timestamp)
            VALUES ('legacy', 'session', 'stage_change', 'build', ?, '2026-07-25')""",
            (
                json.dumps(
                    {
                        "event_type_raw": "interview_complete",
                        "trusted_transition": True,
                    }
                ),
            ),
        )


def _create_rootless_legacy_trust_db(db_path) -> None:
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL,
                seed_version INTEGER DEFAULT 1,
                current_stage TEXT DEFAULT 'interview',
                stage_transition_id TEXT DEFAULT '',
                samvil_tier TEXT DEFAULT 'standard', created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                event_type TEXT NOT NULL, stage TEXT NOT NULL,
                data TEXT DEFAULT '{}', token_count INTEGER DEFAULT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE seed_versions (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                version INTEGER NOT NULL, seed_json TEXT NOT NULL,
                change_summary TEXT DEFAULT '', created_at TEXT NOT NULL,
                UNIQUE(session_id, version)
            );
            CREATE INDEX idx_events_trusted_transition
            ON events(session_id, json_extract(data, '$.trusted_transition'), timestamp DESC);
            """
        )
        db.execute(
            """INSERT INTO sessions
            (id, project_name, current_stage, stage_transition_id, created_at, updated_at)
            VALUES ('session', 'legacy-app', 'build', 'legacy',
                    '2026-07-25', '2026-07-25')"""
        )
        db.execute(
            """INSERT INTO events
            (id, session_id, event_type, stage, data, timestamp)
            VALUES ('legacy', 'session', 'stage_change', 'build', ?, '2026-07-25')""",
            (json.dumps({"event_type_raw": "interview_complete"}),),
        )


@pytest.mark.asyncio
async def test_trusted_transition_migration_does_not_promote_legacy_json_flags(
    tmp_path,
) -> None:
    db_path = tmp_path / "legacy-trust.db"
    project_root = tmp_path / "legacy-project"
    (project_root / ".samvil").mkdir(parents=True)
    state_path = project_root / "project.state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": "session",
                "current_stage": "build",
                "completed_stages": ["interview", "seed", "design", "scaffold"],
            }
        ),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps(
            {
                "next_skill": "samvil-build",
                "from_stage": "samvil-scaffold",
                "host_name": "codex_cli",
            }
        ),
        encoding="utf-8",
    )
    _create_legacy_trust_db(db_path, project_root)

    legacy_store = EventStore(str(db_path))
    await legacy_store.initialize()
    recovered_session = await legacy_store.get_session("session")
    assert recovered_session is not None
    assert recovered_session.current_stage == Stage.INTERVIEW
    recovered_state = json.loads(state_path.read_text(encoding="utf-8"))
    recovered_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert recovered_state["current_stage"] == "interview"
    assert recovered_state["completed_stages"] == []
    assert recovered_marker["next_skill"] == "samvil-interview"
    from samvil_mcp.resume import resume_session

    assert resume_session(str(project_root))["next_skill"] == "samvil-interview"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """INSERT INTO events
            (id, session_id, event_type, stage, data, timestamp)
            VALUES ('forged', 'session', 'stage_change', 'seed', ?, '2026-07-26')""",
            (json.dumps({"trusted_transition": True}),),
        )

    await legacy_store.initialize()

    with sqlite3.connect(db_path) as db:
        provenance = dict(
            db.execute("SELECT id, trusted_transition FROM events").fetchall()
        )
        index_sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'idx_events_trusted_transition'"
        ).fetchone()[0]
    events = await legacy_store.get_orchestration_events(
        "session",
        frozenset({"interview_complete"}),
    )
    assert provenance == {"legacy": 0, "forged": 0}
    assert events == []
    assert "trusted_transition" in index_sql
    assert "json_extract" not in index_sql

    await legacy_store.save_event_and_update_stage(
        "session",
        EventType.STAGE_CHANGE,
        Stage.SEED,
        {"event_type_raw": "interview_complete"},
        expected_stage=Stage.INTERVIEW,
    )
    await legacy_store.initialize()
    migrated_session = await legacy_store.get_session("session")
    assert migrated_session is not None
    assert migrated_session.current_stage == Stage.SEED


@pytest.mark.asyncio
async def test_rootless_legacy_migration_waits_for_project_attach_before_rewind(
    tmp_path,
) -> None:
    db_path = tmp_path / "rootless-legacy.db"
    project_root = tmp_path / "legacy-project"
    (project_root / ".samvil").mkdir(parents=True)
    state_path = project_root / "project.state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": "session",
                "current_stage": "build",
                "completed_stages": ["interview", "seed", "design", "scaffold"],
            }
        ),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps(
            {
                "next_skill": "samvil-build",
                "from_stage": "samvil-scaffold",
                "host_name": "codex_cli",
            }
        ),
        encoding="utf-8",
    )
    _create_rootless_legacy_trust_db(db_path)

    store = EventStore(str(db_path))
    await store.initialize()

    pending = await store.get_session("session")
    assert pending is not None
    assert pending.current_stage == Stage.BUILD
    assert pending.project_root == ""
    assert json.loads(state_path.read_text())["current_stage"] == "build"
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-build"

    assert await store.recover_legacy_session_project_root(
        "session",
        str(project_root),
    ) is True
    recovered = await store.get_session("session")
    assert recovered is not None
    assert recovered.current_stage == Stage.INTERVIEW
    assert recovered.project_root == str(project_root.resolve())
    assert json.loads(state_path.read_text())["current_stage"] == "interview"
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-interview"
    assert await store.recover_legacy_session_project_root(
        "session",
        str(project_root),
    ) is False


@pytest.mark.asyncio
async def test_rootless_attach_revalidates_a_stale_chain_marker(tmp_path) -> None:
    db_path = tmp_path / "rootless-legacy.db"
    project_root = tmp_path / "legacy-project"
    (project_root / ".samvil").mkdir(parents=True)
    state_path = project_root / "project.state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    state_path.write_text(
        json.dumps({"session_id": "session", "current_stage": "interview"}),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps(
            {
                "next_skill": "samvil-build",
                "from_stage": "samvil-scaffold",
                "host_name": "codex_cli",
            }
        ),
        encoding="utf-8",
    )
    _create_rootless_legacy_trust_db(db_path)

    store = EventStore(str(db_path))
    await store.initialize()
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE sessions SET current_stage = 'interview', stage_transition_id = '' "
            "WHERE id = 'session'"
        )

    assert await store.recover_legacy_session_project_root(
        "session",
        str(project_root),
    ) is True
    recovered = await store.get_session("session")
    assert recovered is not None
    assert recovered.current_stage == Stage.INTERVIEW
    assert recovered.project_root == str(project_root.resolve())
    assert json.loads(state_path.read_text())["current_stage"] == "interview"
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-interview"


@pytest.mark.asyncio
async def test_rootless_attach_rejects_file_marker_mismatch_after_trusted_transition(
    tmp_path,
) -> None:
    db_path = tmp_path / "rootless-trusted-mismatch.db"
    project_root = tmp_path / "legacy-project"
    (project_root / ".samvil").mkdir(parents=True)
    state_path = project_root / "project.state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    state_path.write_text(
        json.dumps({"session_id": "session", "current_stage": "build"}),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps({"next_skill": "samvil-build", "from_stage": "samvil-scaffold"}),
        encoding="utf-8",
    )
    _create_rootless_legacy_trust_db(db_path)

    store = EventStore(str(db_path))
    await store.initialize()
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE sessions SET current_stage = 'seed', stage_transition_id = 'trusted' "
            "WHERE id = 'session'"
        )
        db.execute(
            "UPDATE events SET trusted_transition = 1 WHERE id = 'legacy'"
        )

    assert await store.recover_legacy_session_project_root(
        "session",
        str(project_root),
    ) is False
    recovered = await store.get_session("session")
    assert recovered is not None
    assert recovered.project_root == ""
    assert json.loads(state_path.read_text())["current_stage"] == "build"
    assert json.loads(marker_path.read_text())["next_skill"] == "samvil-build"


@pytest.mark.parametrize(
    "failure_mode",
    ["marker", "marker_persistent", "database"],
)
@pytest.mark.asyncio
async def test_trusted_transition_migration_restores_file_ssot_when_recovery_fails(
    tmp_path,
    monkeypatch,
    failure_mode,
) -> None:
    from samvil_mcp import event_store as event_store_module

    db_path = tmp_path / "legacy-trust-failure.db"
    project_root = tmp_path / "legacy-project"
    (project_root / ".samvil").mkdir(parents=True)
    state_path = project_root / "project.state.json"
    marker_path = project_root / ".samvil" / "next-skill.json"
    original_state = json.dumps(
        {
            "session_id": "session",
            "current_stage": "build",
            "completed_stages": ["interview", "seed", "design", "scaffold"],
        }
    )
    original_marker = json.dumps(
        {
            "next_skill": "samvil-build",
            "from_stage": "samvil-scaffold",
            "host_name": "codex_cli",
        }
    )
    state_path.write_text(original_state, encoding="utf-8")
    marker_path.write_text(original_marker, encoding="utf-8")
    _create_legacy_trust_db(db_path, project_root)

    if failure_mode == "marker":
        real_atomic_write = event_store_module.atomic_write_text_unlocked
        failed = False

        def fail_recovery_marker(path, text, **kwargs):
            nonlocal failed
            if path.name == "next-skill.json" and not failed:
                failed = True
                raise OSError("injected recovery marker failure")
            return real_atomic_write(path, text, **kwargs)

        monkeypatch.setattr(
            event_store_module,
            "atomic_write_text_unlocked",
            fail_recovery_marker,
        )
        expected_error = "injected recovery marker failure"
    elif failure_mode == "marker_persistent":
        real_atomic_write = event_store_module.atomic_write_text_unlocked

        def fail_recovery_marker_persistently(path, text, **kwargs):
            if path.name == "next-skill.json":
                raise OSError("injected persistent recovery marker failure")
            return real_atomic_write(path, text, **kwargs)

        monkeypatch.setattr(
            event_store_module,
            "atomic_write_text_unlocked",
            fail_recovery_marker_persistently,
        )
        expected_error = "injected persistent recovery marker failure"
    else:
        real_execute = aiosqlite.Connection.execute

        def fail_database_rewind(connection, sql, *args, **kwargs):
            if "UPDATE sessions" in sql and "current_stage = 'interview'" in sql:
                raise sqlite3.OperationalError("injected recovery database failure")
            return real_execute(connection, sql, *args, **kwargs)

        monkeypatch.setattr(aiosqlite.Connection, "execute", fail_database_rewind)
        expected_error = "injected recovery database failure"

    with pytest.raises(Exception, match=expected_error):
        await EventStore(str(db_path)).initialize()

    with sqlite3.connect(db_path) as db:
        stage = db.execute(
            "SELECT current_stage FROM sessions WHERE id = 'session'"
        ).fetchone()[0]
        columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
    assert stage == "build"
    assert "trusted_transition" not in columns
    assert state_path.read_text(encoding="utf-8") == original_state
    assert marker_path.read_text(encoding="utf-8") == original_marker


@pytest.mark.asyncio
async def test_list_sessions(store: EventStore):
    await store.create_session("a", "minimal")
    await store.create_session("b", "standard")
    await store.create_session("c", "full")

    sessions = await store.list_sessions(limit=2)
    assert len(sessions) == 2
    # Newest first
    assert sessions[0].project_name == "c"


@pytest.mark.asyncio
async def test_update_session_stage(store: EventStore):
    session = await store.create_session("test-app")
    await store.update_session_stage(session.id, Stage.BUILD)

    fetched = await store.get_session(session.id)
    assert fetched.current_stage == Stage.BUILD


@pytest.mark.asyncio
async def test_save_and_get_events(store: EventStore):
    session = await store.create_session("test-app")

    await store.save_event(session.id, EventType.STAGE_START, Stage.INTERVIEW)
    await store.save_event(session.id, EventType.STAGE_END, Stage.INTERVIEW, {"questions": 5})
    await store.save_event(session.id, EventType.STAGE_START, Stage.SEED)

    events = await store.get_events(session.id)
    assert len(events) == 3

    # Filter by type
    starts = await store.get_events(session.id, event_type=EventType.STAGE_START)
    assert len(starts) == 2


@pytest.mark.asyncio
async def test_compensation_does_not_rewind_a_newer_same_stage_transition(
    store: EventStore,
    monkeypatch,
) -> None:
    from samvil_mcp import event_store

    session = await store.create_session("concurrent-stage")
    monkeypatch.setattr(event_store, "_now", lambda: "2026-07-25T00:00:00+00:00")
    failed = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_END,
        Stage.SEED,
        {"attempt": 1},
    )
    succeeded = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_END,
        Stage.SEED,
        {"attempt": 2},
    )

    compensated = await store.delete_event_and_restore_stage(failed)

    current = await store.get_session(session.id)
    events = await store.get_events(session.id)
    assert compensated is False
    assert current is not None and current.current_stage == Stage.SEED
    assert [event.id for event in events] == [succeeded.event.id, failed.event.id]


@pytest.mark.asyncio
async def test_compensation_preserves_prerequisite_owned_by_newer_stage(
    store: EventStore,
) -> None:
    session = await store.create_session("dependent-stage")
    interview = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_CHANGE,
        Stage.SEED,
        {"event_type_raw": "interview_complete", "trusted_transition": True},
    )
    seed = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_CHANGE,
        Stage.DESIGN,
        {"event_type_raw": "seed_generated", "trusted_transition": True},
    )

    compensated = await store.delete_event_and_restore_stage(interview)

    current = await store.get_session(session.id)
    events = await store.get_orchestration_events(
        session.id,
        frozenset({"interview_complete", "seed_generated"}),
    )
    assert compensated is False
    assert current is not None and current.current_stage == Stage.DESIGN
    assert [event.id for event in events] == [seed.event.id, interview.event.id]


@pytest.mark.asyncio
async def test_orchestration_events_require_transaction_provenance(
    store: EventStore,
) -> None:
    session = await store.create_session("trusted-boundary")
    legacy = await store.save_event(
        session.id,
        EventType.STAGE_END,
        Stage.SEED,
        {"event_type_raw": "interview_complete"},
    )
    forged = await store.save_event(
        session.id,
        EventType.STAGE_CHANGE,
        Stage.SEED,
        {"event_type_raw": "interview_complete", "trusted_transition": True},
    )
    trusted = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_CHANGE,
        Stage.SEED,
        {"event_type_raw": "interview_complete"},
        expected_stage=Stage.INTERVIEW,
    )

    events = await store.get_orchestration_events(
        session.id,
        frozenset({"interview_complete"}),
    )

    assert [event.id for event in events] == [trusted.event.id]
    assert forged.id not in {event.id for event in events}
    assert legacy.id not in {event.id for event in events}


@pytest.mark.asyncio
async def test_raw_event_insert_cannot_forge_transition_provenance(
    store: EventStore,
) -> None:
    session = await store.create_session("raw-insert-boundary")
    with sqlite3.connect(store.db_path) as db:
        db.execute(
            """INSERT INTO events
            (id, session_id, event_type, stage, data, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "forged-event",
                session.id,
                EventType.STAGE_CHANGE.value,
                Stage.SEED.value,
                json.dumps(
                    {
                        "event_type_raw": "interview_complete",
                        "trusted_transition": True,
                    }
                ),
                "2026-07-25T00:00:00+00:00",
            ),
        )

    events = await store.get_orchestration_events(
        session.id,
        frozenset({"interview_complete"}),
    )

    assert events == []


@pytest.mark.asyncio
async def test_orchestration_query_uses_trusted_transition_index(
    store: EventStore,
) -> None:
    session = await store.create_session("trusted-query-plan")
    await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_CHANGE,
        Stage.SEED,
        {"event_type_raw": "interview_complete"},
        expected_stage=Stage.INTERVIEW,
    )

    with sqlite3.connect(store.db_path) as db:
        plan = db.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT * FROM events INDEXED BY idx_events_trusted_transition
            WHERE session_id = ?
              AND trusted_transition = 1
              AND (
                event_type IN (?)
                OR json_extract(data, '$.event_type_raw') IN (?)
              )
            ORDER BY timestamp DESC, rowid DESC
            """,
            (session.id, "interview_complete", "interview_complete"),
        ).fetchall()

    assert any(
        "idx_events_trusted_transition" in str(row[3])
        for row in plan
    ), plan


@pytest.mark.asyncio
async def test_transition_captures_previous_stage_inside_write_transaction(
    store: EventStore,
) -> None:
    session = await store.create_session("transaction-stage")
    await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_END,
        Stage.SEED,
    )
    failed = await store.save_event_and_update_stage(
        session.id,
        EventType.STAGE_END,
        Stage.DESIGN,
    )

    compensated = await store.delete_event_and_restore_stage(failed)

    current = await store.get_session(session.id)
    assert compensated is True
    assert failed.previous_stage == Stage.SEED
    assert current is not None and current.current_stage == Stage.SEED


@pytest.mark.asyncio
async def test_transition_timestamp_is_created_after_write_lock_acquisition(
    store: EventStore,
    monkeypatch,
) -> None:
    from samvil_mcp import event_store

    session = await store.create_session("locked-timestamp")
    timestamps: list[str] = []

    def tracked_now() -> str:
        timestamps.append("2026-07-25T00:00:00+00:00")
        return timestamps[-1]

    monkeypatch.setattr(event_store, "_now", tracked_now)
    blocker = await aiosqlite.connect(store.db_path)
    await blocker.execute("BEGIN IMMEDIATE")
    transition_task = asyncio.create_task(
        store.save_event_and_update_stage(
            session.id,
            EventType.STAGE_END,
            Stage.SEED,
        )
    )

    await asyncio.sleep(0.05)
    timestamps_before_unlock = list(timestamps)
    await blocker.rollback()
    await blocker.close()
    transition = await transition_task
    assert timestamps_before_unlock == []
    assert transition.event.timestamp == "2026-07-25T00:00:00+00:00"
    assert timestamps == ["2026-07-25T00:00:00+00:00"]


@pytest.mark.asyncio
async def test_save_and_get_seed_versions(store: EventStore):
    session = await store.create_session("test-app")

    seed_v1 = {"name": "test-app", "version": 1, "features": []}
    await store.save_seed_version(session.id, 1, json.dumps(seed_v1))

    seed_v2 = {"name": "test-app", "version": 2, "features": ["auth"]}
    await store.save_seed_version(session.id, 2, json.dumps(seed_v2), "Added auth feature")

    versions = await store.get_seed_versions(session.id)
    assert len(versions) == 2
    assert versions[0].version == 1
    assert versions[1].version == 2
    assert versions[1].change_summary == "Added auth feature"

    # Verify JSON roundtrip
    parsed = json.loads(versions[1].seed_json)
    assert parsed["features"] == ["auth"]


@pytest.mark.asyncio
async def test_session_not_found(store: EventStore):
    result = await store.get_session("nonexistent")
    assert result is None
