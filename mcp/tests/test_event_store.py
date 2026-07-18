"""Tests for SAMVIL EventStore."""

import json
import os
import sqlite3
import tempfile

import pytest
import pytest_asyncio

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


def test_migration_plan_only_contains_missing_schema_changes() -> None:
    plan = _migration_plan(
        events_columns={"id", "token_count"},
        sessions_columns={"id", "samvil_tier"},
    )

    assert plan == ["ALTER TABLE sessions ADD COLUMN project_root TEXT DEFAULT ''"]

    legacy = _migration_plan(
        events_columns={"id"},
        sessions_columns={"id", "agent_tier"},  # glossary-allow: legacy fixture
    )
    assert legacy == [
        "ALTER TABLE events ADD COLUMN token_count INTEGER DEFAULT NULL",
        "ALTER TABLE sessions RENAME COLUMN agent_tier TO samvil_tier",  # glossary-allow: expected migration
        "ALTER TABLE sessions ADD COLUMN project_root TEXT DEFAULT ''",
    ]


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
