"""Stage envelope and idempotent begin-stage controller tests."""

from __future__ import annotations

import os
import tempfile
import json
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

    session = await controller.store.create_session("display-name-does-not-match-root", "standard", str(project))
    ready = await controller.get_stage_envelope(str(project), "codex_cli")
    assert ready["run_id"] == session.id
    assert ready["status"] == "ready"
    assert ready["stage"] == "samvil-interview"
    assert Path(ready["instruction_path"]).is_absolute()
    assert Path(ready["instruction_path"]).is_file()
    assert not (project / ".samvil").exists()


@pytest.mark.asyncio
async def test_envelope_preserves_in_progress_marker_owner(controller, tmp_path):
    project = tmp_path / "same-root-sessions"
    project.mkdir()
    first = await controller.store.create_session("first-display", "standard", str(project))
    await controller.begin_stage(str(project), first.id, "samvil-interview", 0)
    await controller.store.create_session("second-display", "standard", str(project))

    envelope = await controller.get_stage_envelope(str(project), "codex_cli")

    assert envelope["run_id"] == first.id
    assert envelope["status"] == "in_progress"


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

    with pytest.raises(TransitionError, match="does not match current session stage"):
        await controller.begin_stage(str(project), session.id, "samvil-design", 0)


@pytest.mark.asyncio
async def test_begin_stage_rejects_stage_that_is_not_session_current_stage(controller, tmp_path):
    project = tmp_path / "wrong-first-claim"
    project.mkdir()
    session = await controller.store.create_session("wrong-first-claim", "standard", str(project))

    with pytest.raises(TransitionError, match="does not match current session stage"):
        await controller.begin_stage(str(project), session.id, "samvil-design", 0)

    assert await controller.store.get_stage_claims_for_revision(session.id, 0) == []


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


@pytest.mark.asyncio
async def test_commit_stage_transition_materializes_each_ssot_once(controller, tmp_path):
    project = tmp_path / "commit-app"
    project.mkdir()
    (project / "project.state.json").write_text(
        '{"current_stage":"interview","completed_stages":[],"unrelated":"keep"}',
        encoding="utf-8",
    )
    session = await controller.store.create_session("commit-app", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)

    first = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"], "samvil-interview", "samvil-seed", 0,
    )
    second = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"], "samvil-interview", "samvil-seed", 0,
        transition_id=first["transition_id"],
    )
    assert first == second
    assert json.loads((project / "project.state.json").read_text())["unrelated"] == "keep"
    assert len((project / ".samvil" / "events.jsonl").read_text().splitlines()) == 1
    assert not (project / ".samvil" / "transition-journal.json").exists()
    assert await controller.store.get_pending_project_events(session.id) == []


@pytest.mark.asyncio
async def test_db_committed_journal_replays_remaining_materialization(
    controller, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import samvil_mcp.server as server

    project = tmp_path / "journal-replay"
    project.mkdir()
    session = await controller.store.create_session("journal-replay", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    original_append = server._append_project_event
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("injected canonical append failure")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(server, "_append_project_event", fail_once)
    with pytest.raises(OSError, match="injected canonical append failure"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            transition_id="journal-replay-transition",
        )

    recovered = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"],
        "samvil-interview", "samvil-seed", 0,
        transition_id="journal-replay-transition",
    )

    assert recovered["status"] == "committed"
    assert len((project / ".samvil" / "events.jsonl").read_text().splitlines()) == 1
    assert await controller.store.get_pending_project_events(session.id) == []
    assert not (project / ".samvil" / "transition-journal.json").exists()


@pytest.mark.asyncio
async def test_prepared_journal_with_committed_db_event_recovers_on_retry(
    controller, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "prepared-db-replay"
    project.mkdir()
    session = await controller.store.create_session("prepared-db-replay", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    original_write = controller._write_journal
    failed = False

    def fail_db_committed(root, journal, phase):
        nonlocal failed
        if phase == "DB_COMMITTED" and not failed:
            failed = True
            raise OSError("injected DB_COMMITTED journal failure")
        return original_write(root, journal, phase)

    monkeypatch.setattr(controller, "_write_journal", fail_db_committed)
    with pytest.raises(OSError, match="DB_COMMITTED"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            transition_id="prepared-db-replay-transition",
        )

    recovered = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"],
        "samvil-interview", "samvil-seed", 0,
        transition_id="prepared-db-replay-transition",
    )

    assert recovered["status"] == "committed"
    assert len((project / ".samvil" / "events.jsonl").read_text().splitlines()) == 1
    assert await controller.store.get_pending_project_events(session.id) == []


@pytest.mark.asyncio
async def test_envelope_exposes_interrupted_transition_retry_context(
    controller, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import samvil_mcp.server as server

    project = tmp_path / "reopen-recovery"
    project.mkdir()
    session = await controller.store.create_session("reopen-recovery", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)

    monkeypatch.setattr(server, "_append_project_event", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("stop")))
    with pytest.raises(OSError, match="stop"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            data={"verdict": "PASS", "evidence": {"artifact": "interview-summary.md:1"}},
            transition_id="reopen-recovery-transition",
        )

    envelope = await controller.get_stage_envelope(str(project), "codex_cli")

    assert envelope["status"] == "in_progress"
    assert envelope["stage"] == "samvil-interview"
    assert envelope["recovery_mode"] == "retry_commit"
    assert envelope["transition_id"] == "reopen-recovery-transition"
    assert envelope["claim_id"] == claim["claim_id"]
    assert envelope["requested_next_skill"] == "samvil-seed"


@pytest.mark.asyncio
async def test_recovery_rejects_tampered_journal_payload(controller, tmp_path, monkeypatch):
    import samvil_mcp.server as server

    project = tmp_path / "tampered-journal"
    project.mkdir()
    session = await controller.store.create_session("tampered-journal", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    monkeypatch.setattr(server, "_append_project_event", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("stop")))
    with pytest.raises(OSError, match="stop"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            transition_id="tampered-journal-transition",
        )

    journal_path = project / ".samvil" / "transition-journal.json"
    journal = json.loads(journal_path.read_text())
    journal["target_state"] = "deploy"
    journal["event_payload"]["forged"] = True
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(TransitionError, match="journal integrity"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            transition_id="tampered-journal-transition",
        )


@pytest.mark.asyncio
async def test_db_committed_recovery_uses_persisted_event_not_rehashed_journal(
    controller, tmp_path, monkeypatch
):
    import hashlib
    import samvil_mcp.server as server

    project = tmp_path / "db-authoritative-journal"
    project.mkdir()
    session = await controller.store.create_session("db-authoritative", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    original_append = server._append_project_event
    monkeypatch.setattr(
        server,
        "_append_project_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("stop")),
    )
    with pytest.raises(OSError, match="stop"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            data={"evidence": {"artifact": "interview-summary.md:1"}},
            transition_id="db-authoritative-transition",
        )

    journal_path = project / ".samvil" / "transition-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["event_payload"]["evidence"] = {"artifact": "forged.txt:1"}
    journal["event_type"] = "qa_pass"
    journal["event_payload_hash"] = hashlib.sha256(
        json.dumps(journal["event_payload"], sort_keys=True).encode()
    ).hexdigest()
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    monkeypatch.setattr(server, "_append_project_event", original_append)

    receipt = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"],
        "samvil-interview", "samvil-seed", 0,
        transition_id="db-authoritative-transition",
    )
    canonical = json.loads((project / ".samvil" / "events.jsonl").read_text(encoding="utf-8"))

    assert receipt["status"] == "committed"
    assert canonical["event_type"] == "stage_end"
    assert canonical["data"]["evidence"]["artifact"] == "interview-summary.md:1"


@pytest.mark.asyncio
async def test_existing_receipt_retry_finishes_claim_completion(controller, tmp_path, monkeypatch):
    project = tmp_path / "receipt-claim-recovery"
    project.mkdir()
    session = await controller.store.create_session("receipt-claim-recovery", "standard", str(project))
    claim = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    original_complete = controller.store.mark_stage_claim_completed
    failed = False

    async def fail_once(claim_id, transition_id):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("claim completion interrupted")
        return await original_complete(claim_id, transition_id)

    monkeypatch.setattr(controller.store, "mark_stage_claim_completed", fail_once)
    with pytest.raises(OSError, match="claim completion interrupted"):
        await controller.commit_stage_transition(
            str(project), session.id, claim["claim_id"],
            "samvil-interview", "samvil-seed", 0,
            transition_id="receipt-claim-recovery-transition",
        )

    receipt = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"],
        "samvil-interview", "samvil-seed", 0,
        transition_id="receipt-claim-recovery-transition",
    )
    recovered_claim = await controller.store.get_stage_claim(session.id, "samvil-interview", 0)

    assert receipt["status"] == "committed"
    assert recovered_claim["status"] == "completed"


@pytest.mark.asyncio
async def test_retro_runs_before_terminal_completion(controller, tmp_path):
    project = tmp_path / "retro-terminal"
    project.mkdir()
    session = await controller.store.create_session("retro-terminal", "standard", str(project))
    await controller.store.update_session_stage(session.id, Stage.EVOLVE)
    evolve_claim = await controller.begin_stage(str(project), session.id, "samvil-evolve", 0)

    entered = await controller.commit_stage_transition(
        str(project), session.id, evolve_claim["claim_id"],
        "samvil-evolve", "samvil-retro", 0, transition_id="enter-retro",
    )
    envelope = await controller.get_stage_envelope(str(project), "codex_cli")

    assert entered["status"] == "committed"
    assert envelope["stage"] == "samvil-retro"
    assert envelope["status"] == "ready"
    retro_claim = await controller.begin_stage(str(project), session.id, "samvil-retro", 1)
    completed = await controller.commit_stage_transition(
        str(project), session.id, retro_claim["claim_id"],
        "samvil-retro", "complete", 1, transition_id="complete-retro",
    )
    terminal = await controller.get_stage_envelope(str(project), "codex_cli")

    assert completed["to_stage"] == "complete"
    assert terminal["status"] == "complete"
    assert terminal["stage"] == "complete"


@pytest.mark.asyncio
async def test_transition_claim_points_to_its_actual_event_line(controller, tmp_path):
    project = tmp_path / "claim-lines"
    project.mkdir()
    session = await controller.store.create_session("claim-lines", "standard", str(project))
    interview = await controller.begin_stage(str(project), session.id, "samvil-interview", 0)
    await controller.commit_stage_transition(
        str(project), session.id, interview["claim_id"],
        "samvil-interview", "samvil-seed", 0, transition_id="line-one",
    )
    seed = await controller.begin_stage(str(project), session.id, "samvil-seed", 1)
    await controller.commit_stage_transition(
        str(project), session.id, seed["claim_id"],
        "samvil-seed", "samvil-design", 1, transition_id="line-two",
    )

    claims = [
        json.loads(line)
        for line in (project / ".samvil" / "claims.jsonl").read_text().splitlines()
    ]
    assert claims[0]["evidence"] == [".samvil/events.jsonl:1"]
    assert claims[1]["evidence"] == [".samvil/events.jsonl:2"]


@pytest.mark.asyncio
async def test_transition_id_cannot_replay_another_projects_receipt(controller, tmp_path):
    first_project = tmp_path / "first-project"
    second_project = tmp_path / "second-project"
    first_project.mkdir()
    second_project.mkdir()
    first_session = await controller.store.create_session("first", "standard", str(first_project))
    second_session = await controller.store.create_session("second", "standard", str(second_project))
    first_claim = await controller.begin_stage(
        str(first_project), first_session.id, "samvil-interview", 0
    )
    second_claim = await controller.begin_stage(
        str(second_project), second_session.id, "samvil-interview", 0
    )
    await controller.commit_stage_transition(
        str(first_project),
        first_session.id,
        first_claim["claim_id"],
        "samvil-interview",
        "samvil-seed",
        0,
        transition_id="shared-transition-id",
    )

    with pytest.raises(TransitionError, match="another run"):
        await controller.commit_stage_transition(
            str(second_project),
            second_session.id,
            second_claim["claim_id"],
            "samvil-interview",
            "samvil-seed",
            0,
            transition_id="shared-transition-id",
        )


@pytest.mark.asyncio
async def test_qa_commit_without_evidence_stays_blocked(controller, tmp_path):
    project = tmp_path / "qa-blocked-app"
    project.mkdir()
    session = await controller.store.create_session("qa-blocked-app", "standard", str(project))
    await controller.store.update_session_stage(session.id, Stage.QA)
    claim = await controller.store.create_stage_claim(session.id, "samvil-qa", 0)
    receipt = await controller.commit_stage_transition(
        str(project), session.id, claim["claim_id"], "samvil-qa", "samvil-deploy", 0,
    )
    assert receipt["status"] == "blocked"
    assert await controller.store.get_events(session.id) == []
