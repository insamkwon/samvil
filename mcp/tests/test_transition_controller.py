"""Stage envelope and idempotent begin-stage controller tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from samvil_mcp.event_store import EventStore
from samvil_mcp.models import Stage
from samvil_mcp.transition_controller import TransitionController, TransitionError


@pytest_asyncio.fixture
async def controller(tmp_path: Path):
    store = EventStore(str(tmp_path / "events.db"))
    await store.initialize()
    return TransitionController(store)


@pytest.mark.asyncio
async def test_envelope_is_read_only_and_reports_fresh_then_ready(controller, tmp_path):
    project = tmp_path / "fresh-app"
    project.mkdir()
    envelope = await controller.get_stage_envelope(str(project), "codex_cli")
    assert envelope["status"] == "fresh"

    session = await controller.store.create_session("fresh-app", "standard", str(project))
    ready = await controller.get_stage_envelope(str(project), "codex_cli")
    assert ready["run_id"] == session.id
    assert ready["status"] == "ready"
    assert ready["stage"] == "samvil-interview"
    assert not (project / ".samvil").exists()


@pytest.mark.asyncio
async def test_begin_stage_uses_revision_cas_and_duplicate_claim_is_idempotent(controller, tmp_path):
    project = tmp_path / "claim-app"
    project.mkdir()
    session = await controller.store.create_session("claim-app", "standard", str(project))

    first = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    second = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    assert first["claim_id"] == second["claim_id"]
    assert first["status"] == "in_progress"
    assert (project / ".samvil" / "next-skill.json").is_file()

    with pytest.raises(TransitionError, match="stale marker revision"):
        await controller.begin_stage(str(project), session.id, "samvil-interview", 1)


@pytest.mark.asyncio
async def test_conflicting_stage_claim_is_rejected_without_mutation(controller, tmp_path):
    project = tmp_path / "conflict-app"
    project.mkdir()
    session = await controller.store.create_session("conflict-app", "standard", str(project))
    await controller.begin_stage(str(project), session.id, "samvil-interview", 0)

    with pytest.raises(TransitionError, match="conflicting stage claim"):
        await controller.begin_stage(str(project), session.id, "samvil-design", 0)


@pytest.mark.asyncio
async def test_checkpoint_envelope_does_not_auto_begin(controller, tmp_path):
    project = tmp_path / "checkpoint-app"
    project.mkdir()
    session = await controller.store.create_session("checkpoint-app", "standard", str(project))
    await controller.store.update_session_stage(session.id, Stage.DEPLOY)
    envelope = await controller.get_stage_envelope(str(project), "codex_cli")
    assert envelope["status"] == "waiting_user"
    assert await controller.store.get_stage_claim(session.id, "samvil-deploy", 0) is None


@pytest.mark.asyncio
async def test_marker_write_failure_compensates_new_claim(controller, tmp_path, monkeypatch):
    project = tmp_path / "compensation-app"
    project.mkdir()
    session = await controller.store.create_session("compensation-app", "standard", str(project))

    def fail_marker(*args, **kwargs):
        raise OSError("marker unavailable")

    monkeypatch.setattr("samvil_mcp.transition_controller.write_driver_marker", fail_marker)
    with pytest.raises(OSError, match="marker unavailable"):
        await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    assert await controller.store.get_stage_claim(session.id, "samvil-interview", 0) is None
