"""Tests for SAMVIL EventStore."""

import json
import os
import tempfile

import pytest
import pytest_asyncio

from samvil_mcp.event_store import EventStore
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
