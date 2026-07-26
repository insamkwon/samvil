"""Integration coverage for the Codex same-task driver decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from samvil_mcp.event_store import EventStore
from samvil_mcp.models import Stage
from samvil_mcp.transition_controller import TransitionController


@pytest_asyncio.fixture
async def controller(tmp_path: Path):
    store = EventStore(str(tmp_path / "driver.db"))
    await store.initialize()
    return TransitionController(store)


def test_driver_decisions_cover_catalog_and_checkpoint_boundaries():
    assert TransitionController.decide_next_stage("samvil-interview", "PASS")["next_skill"] == "samvil-seed"
    assert TransitionController.decide_next_stage("samvil-seed", "PASS")["next_skill"] == "samvil-design"
    assert TransitionController.decide_next_stage("samvil-seed", "PASS", council_opt_in=False)["next_skill"] == "samvil-design"
    assert TransitionController.decide_next_stage("samvil-seed", "PASS", council_opt_in=True)["next_skill"] == "samvil-council"
    assert TransitionController.decide_next_stage("samvil-qa", "REVISE")["next_skill"] == "samvil-qa"
    assert TransitionController.decide_next_stage("samvil-deploy", "PASS")["status"] == "waiting_user"


def test_driver_circuit_breaker_requires_same_consecutive_root_cause():
    assert TransitionController.circuit_breaker(["network", "schema"])["halt"] is False
    result = TransitionController.circuit_breaker(["schema", "schema"])
    assert result["halt"] is True
    assert result["consecutive"] == 2


@pytest.mark.asyncio
async def test_real_controller_replays_interview_to_seed_without_duplicate_transition(controller, tmp_path):
    project = tmp_path / "driver-app"
    project.mkdir()
    (project / "project.state.json").write_text(
        json.dumps({"current_stage": "interview", "completed_stages": [], "conversation_note": "preserve"}),
        encoding="utf-8",
    )
    session = await controller.store.create_session("driver-app", "standard", str(project))
    envelope = await controller.get_stage_envelope(str(project), "codex_cli")
    assert envelope["status"] == "ready"
    claim = await controller.begin_stage(str(project), session.id, envelope["stage"], envelope["marker_revision"])
    receipt = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"], envelope["stage"], "samvil-seed", envelope["marker_revision"],
        data={"evidence": {"instruction": "references/codex-commands/samvil-interview.md"}},
        transition_id="driver-interview-seed",
    )
    duplicate = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"], envelope["stage"], "samvil-seed", envelope["marker_revision"],
        transition_id="driver-interview-seed",
    )
    assert receipt == duplicate
    assert json.loads((project / "project.state.json").read_text())["conversation_note"] == "preserve"


@pytest.mark.asyncio
async def test_checkpoint_and_compaction_reentry_use_durable_envelope(controller, tmp_path):
    project = tmp_path / "checkpoint-driver"
    project.mkdir()
    session = await controller.store.create_session("checkpoint-driver", "standard", str(project))
    await controller.store.update_session_stage(session.id, Stage.DEPLOY)
    envelope = await controller.get_stage_envelope(str(project), "codex_cli")
    assert envelope["status"] == "waiting_user"
    assert envelope["run_id"] == session.id
    assert envelope["marker_revision"] == 0
