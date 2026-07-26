"""v3.1.0 Polish #7 — runtime smoke tests for v3.1.0 MCP tools.

These go through the async tool functions directly (as opposed to unit tests
against helper modules) so we catch wiring regressions between `server.py`
and the underlying modules — the kind of bug that unit tests pass but the
real MCP round-trip fails.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from samvil_mcp.server import (
    build_reawake_message,
    build_qa_recovery_routing,
    build_rebuild_reentry,
    build_post_rebuild_qa,
    build_final_e2e_bundle,
    evaluate_qa_convergence,
    get_tier_phases,
    heartbeat_state,
    increment_stall_recovery_count,
    is_state_stalled,
    materialize_qa_synthesis,
    materialize_qa_recovery_routing,
    materialize_evolve_context,
    materialize_evolve_proposal,
    materialize_evolve_apply_plan,
    apply_evolve_apply_plan,
    materialize_evolve_rebuild_handoff,
    materialize_rebuild_reentry,
    materialize_post_rebuild_qa,
    materialize_final_e2e_bundle,
    suggest_ac_split,
    synthesize_qa_evidence,
    get_stage_envelope,
    begin_stage,
    commit_stage_transition,
    gate_check,
)
from samvil_mcp.event_store import EventStore


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_codex_transition_tools_are_thin_and_fail_closed(tmp_path: Path) -> None:
    envelope = json.loads(_run(get_stage_envelope(str(tmp_path), "codex_cli")))
    assert envelope["status"] == "fresh"
    invalid = json.loads(_run(begin_stage(str(tmp_path), "run", "samvil-interview", True)))
    assert invalid["status"] == "blocked"
    malformed = json.loads(_run(commit_stage_transition(
        str(tmp_path), "run", "samvil-interview", 0, "claim", "PASS", "[]"
    )))
    assert malformed["status"] == "blocked"


def test_commit_stage_transition_wrapper_retries_with_same_transition_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "wrapper-idempotency"
    project.mkdir()
    store = EventStore(str(tmp_path / "events.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    (project / "interview-summary.md").write_text("verified interview\n", encoding="utf-8")

    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))
    empty = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", "{}", "", "wrapper-empty-evidence",
    )))
    assert empty["status"] == "blocked"
    first = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"interview-summary.md:1"}', "", "wrapper-transition-1",
    )))
    second = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"interview-summary.md:1"}', "", "wrapper-transition-1",
    )))

    assert first["status"] == "committed"
    assert second == first


def test_commit_stage_transition_wrapper_rejects_failed_verdict_and_sanitizes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "wrapper-authority"
    project.mkdir()
    store = EventStore(str(tmp_path / "authority.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    (project / "interview-summary.md").write_text("verified interview\n", encoding="utf-8")
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))

    rejected = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "FAIL", "{}", "samvil-seed", "failed-transition",
    )))

    assert rejected["status"] == "ready"
    assert rejected["next_skill"] == "samvil-interview"
    assert _run(store.get_events(session.id)) == []

    secret = "ghp_fixture_secret"
    committed = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS",
        json.dumps({
            "artifact": "interview-summary.md:1",
            "contact": "person@example.com",
            "token": secret,
        }),
        "samvil-seed", "sanitized-transition",
    )))
    assert committed["status"] == "committed"
    serialized = str(_run(store.get_events(session.id))[0].data)
    assert "person@example.com" not in serialized
    assert secret not in serialized


def test_commit_stage_transition_rejects_evidence_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server

    project = tmp_path / "contained-evidence"
    project.mkdir()
    (tmp_path / "interview-summary.md").write_text("outside\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "contained.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-interview", 0)))

    result = json.loads(_run(commit_stage_transition(
        str(project), session.id, "samvil-interview", 0,
        claim["claim_id"], "PASS", '{"artifact":"../interview-summary.md:1"}',
        "", "outside-evidence-transition",
    )))

    assert result["status"] == "blocked"
    assert result["evidence_validation"]["all_valid"] is False


def test_terminal_transition_wrapper_retry_returns_identical_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "terminal-wrapper"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "retro-results.md").write_text("complete\n", encoding="utf-8")
    store = EventStore(str(tmp_path / "terminal.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.RETRO))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-retro", 0)))
    args = (
        str(project), session.id, "samvil-retro", 0, claim["claim_id"],
        "PASS", '{"artifact":".samvil/retro-results.md:1"}', "", "terminal-wrapper-id",
    )

    first = json.loads(_run(commit_stage_transition(*args)))
    second = json.loads(_run(commit_stage_transition(*args)))

    assert first["status"] == "committed"
    assert second == first


def test_qa_recovery_transition_requires_current_pass_gate_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.server as server
    from samvil_mcp.models import Stage

    project = tmp_path / "qa-recovery-receipt"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "qa-results.json").write_text(
        json.dumps({"synthesis": {"verdict": "FAIL"}, "convergence": {"verdict": "blocked"}}),
        encoding="utf-8",
    )
    store = EventStore(str(tmp_path / "qa-recovery.db"))
    _run(store.initialize())
    session = _run(store.create_session("display-name", "minimal", str(project)))
    _run(store.update_session_stage(session.id, Stage.QA))
    monkeypatch.setattr(server, "_store", store)
    claim = json.loads(_run(begin_stage(str(project), session.id, "samvil-qa", 0)))
    import hashlib
    qa_hash = hashlib.sha256((project / ".samvil" / "qa-results.json").read_bytes()).hexdigest()
    fake_receipt = project / ".samvil" / "gate-receipts" / "any_to_retro.json"
    fake_receipt.parent.mkdir(parents=True)
    fake_receipt.write_text(
        json.dumps({
            "kind": "gate_receipt",
            "gate": "any_to_retro",
            "verdict": "pass",
            "qa_results_sha256": qa_hash,
        }),
        encoding="utf-8",
    )
    args = (
        str(project), session.id, "samvil-qa", 0, claim["claim_id"], "FAIL",
        '{"artifact":".samvil/qa-results.json:1"}', "samvil-retro", "qa-recovery-transition",
    )

    blocked = json.loads(_run(commit_stage_transition(*args)))
    gate = json.loads(_run(gate_check(
        "any_to_retro", "minimal", '{"always_run":true}', str(project)
    )))
    committed = json.loads(_run(commit_stage_transition(*args)))

    assert blocked["status"] == "blocked"
    assert gate["verdict"] == "pass"
    assert committed["status"] == "committed"


# ── Tier phases (Polish #5) ────────────────────────────────────


def test_get_tier_phases_returns_expected_structure() -> None:
    out = _run(get_tier_phases(tier="thorough"))
    data = json.loads(out)
    assert data["tier"] == "thorough"
    assert "phases" in data and isinstance(data["phases"], list)
    assert data["ambiguity_target"] == 0.02
    assert "deep" in data["all_tiers"]


def test_get_tier_phases_deep_includes_domain_deep() -> None:
    data = json.loads(_run(get_tier_phases(tier="deep")))
    assert "domain_deep" in data["phases"]
    assert data["ambiguity_target"] == 0.005


def test_synthesize_qa_evidence_tool_returns_central_verdict() -> None:
    out = _run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })))
    data = json.loads(out)
    assert data["gate"] == "qa_synthesis"
    assert data["verdict"] == "REVISE"
    assert data["next_action"] == "replace stubs or hardcoded paths with real implementation"


def test_materialize_qa_synthesis_tool_writes_results(tmp_path: Path) -> None:
    synthesis = json.loads(_run(synthesize_qa_evidence(evidence_json=json.dumps({
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]}
        ]},
        "pass3": {"verdict": "PASS"},
    }))))

    out = _run(materialize_qa_synthesis(project_root=str(tmp_path), synthesis_json=json.dumps(synthesis)))
    data = json.loads(out)

    assert data["status"] == "ok"
    assert data["verdict"] == "PASS"
    assert (tmp_path / ".samvil" / "qa-results.json").exists()
    assert (tmp_path / ".samvil" / "qa-report.md").exists()


def test_evaluate_qa_convergence_tool_reads_history(tmp_path: Path) -> None:
    (tmp_path / "project.state.json").write_text(json.dumps({
        "qa_history": [{
            "iteration": 1,
            "verdict": "REVISE",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        }]
    }), encoding="utf-8")
    synthesis = json.loads(_run(synthesize_qa_evidence(evidence_json=json.dumps({
        "iteration": 2,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    }))))

    out = _run(evaluate_qa_convergence(project_root=str(tmp_path), synthesis_json=json.dumps(synthesis)))
    data = json.loads(out)

    assert data["gate"] == "qa_convergence"
    assert data["verdict"] == "blocked"


def test_qa_recovery_routing_tools_write_next_skill_marker(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {
            "verdict": "REVISE",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
        "convergence": {
            "verdict": "blocked",
            "reason": "identical QA issues persisted across two consecutive iterations",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
    }), encoding="utf-8")

    built = json.loads(_run(build_qa_recovery_routing(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_qa_recovery_routing(project_root=str(tmp_path))))

    assert built["primary_route"]["next_skill"] == "samvil-retro"
    assert materialized["primary_route"]["next_skill"] == "samvil-retro"
    assert (tmp_path / ".samvil" / "next-skill.json").exists()


def test_evolve_context_tools_write_context(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "name": "task-app",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Create tasks"},
        "features": [{"name": "tasks"}],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {"verdict": "REVISE", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "convergence": {"verdict": "blocked", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-routing.json").write_text(json.dumps({
        "primary_route": {"next_skill": "samvil-evolve", "route_type": "seed_evolve"},
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_context(project_root=str(tmp_path))))

    assert materialized["next_skill"] == "samvil-evolve"
    assert (tmp_path / ".samvil" / "evolve-context.json").exists()


def test_evolve_proposal_tools_write_artifacts(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-context.json").write_text(json.dumps({
        "current_seed": {"name": "task-app", "version": 1},
        "qa": {"issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "focus": {"area": "functional_spec", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "routing": {"next_skill": "samvil-evolve", "route_type": "seed_evolve"},
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_proposal(project_root=str(tmp_path))))

    assert materialized["changes"] == 1
    assert (tmp_path / ".samvil" / "evolve-proposal.json").exists()
    assert (tmp_path / ".samvil" / "evolve-proposal.md").exists()


def test_evolve_apply_tools_write_and_apply_seed(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "schema_version": "3.2",
        "name": "task-app",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Create tasks"},
        "features": [{
            "name": "tasks",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "Create task", "children": [], "status": "pending", "evidence": []}
            ],
        }],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "evolve-proposal.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
        "proposed_changes": [{"type": "clarify_or_split_ac", "target": "AC-1"}],
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_apply_plan(project_root=str(tmp_path))))
    applied = json.loads(_run(apply_evolve_apply_plan(project_root=str(tmp_path))))

    assert materialized["mutations"] == 1
    assert applied["status"] == "applied"
    assert (tmp_path / "seed_history" / "v1.json").exists()


def test_evolve_rebuild_tools_write_next_skill_marker(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-apply-plan.json").write_text(json.dumps({
        "status": "applied",
        "from_version": 1,
        "to_version": 2,
    }), encoding="utf-8")

    materialized = json.loads(_run(materialize_evolve_rebuild_handoff(project_root=str(tmp_path))))
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert materialized["next_skill"] == "samvil-scaffold"
    assert marker["from_stage"] == "evolve"


def test_rebuild_reentry_tools_write_scaffold_input(tmp_path: Path) -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "name": "task-app",
        "version": 2,
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "evolve-rebuild.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "next-skill.json").write_text(json.dumps({
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "next_skill": "samvil-scaffold",
        "from_stage": "evolve",
        "reason": "rebuild",
    }), encoding="utf-8")

    built = json.loads(_run(build_rebuild_reentry(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_rebuild_reentry(project_root=str(tmp_path))))

    assert built["status"] == "ready"
    assert materialized["status"] == "ready"
    assert (tmp_path / ".samvil" / "scaffold-input.json").exists()


def test_post_rebuild_qa_tools_write_next_skill_marker(tmp_path: Path) -> None:
    import hashlib

    seed = {"name": "task-app", "version": 2}
    digest = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / ".samvil" / "rebuild-reentry.json").write_text(json.dumps({
        "status": "ready",
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "scaffold-input.json").write_text(json.dumps({
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "scaffold-output.json").write_text(json.dumps({
        "status": "built",
        "seed_version": 2,
        "seed_sha256": digest,
        "artifacts": ["package.json"],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "qa-results.json").write_text(json.dumps({
        "synthesis": {"verdict": "REVISE", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "convergence": {"verdict": "blocked", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
    }), encoding="utf-8")

    built = json.loads(_run(build_post_rebuild_qa(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_post_rebuild_qa(project_root=str(tmp_path))))
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert built["status"] == "ready"
    assert materialized["next_skill"] == "samvil-qa"
    assert marker["from_stage"] == "scaffold"


def test_final_e2e_tools_write_bundle(tmp_path: Path) -> None:
    import hashlib

    seed = {"name": "task-app", "version": 2}
    digest = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    fixtures = {
        "qa-results.json": {"synthesis": {"verdict": "PASS", "iteration": 3}, "convergence": {"verdict": "pass"}},
        "qa-routing.json": {"primary_route": {"next_skill": "samvil-evolve"}},
        "evolve-context.json": {"focus": {"area": "functional_spec"}},
        "evolve-proposal.json": {"status": "ready"},
        "evolve-apply-plan.json": {"status": "applied"},
        "evolve-rebuild.json": {"status": "ready", "next_skill": "samvil-scaffold"},
        "rebuild-reentry.json": {"status": "ready", "next_skill": "samvil-scaffold", "seed_version": 2, "seed_sha256": digest},
        "scaffold-input.json": {"seed_version": 2, "seed_sha256": digest},
        "scaffold-output.json": {"status": "built", "seed_version": 2, "seed_sha256": digest},
        "post-rebuild-qa.json": {"status": "ready", "next_skill": "samvil-qa", "seed_version": 2, "seed_sha256": digest},
        "evolve-cycle.json": {"status": "ready", "verdict": "closed", "next_skill": "samvil-retro", "seed_version": 2, "seed_sha256": digest},
        "run-report.json": {"evolve_cycle": {"present": True, "verdict": "closed"}},
    }
    for name, payload in fixtures.items():
        (tmp_path / ".samvil" / name).write_text(json.dumps(payload), encoding="utf-8")

    built = json.loads(_run(build_final_e2e_bundle(project_root=str(tmp_path))))
    materialized = json.loads(_run(materialize_final_e2e_bundle(project_root=str(tmp_path))))

    assert built["status"] == "pass"
    assert materialized["status"] == "pass"
    assert (tmp_path / ".samvil" / "final-e2e-bundle.json").exists()


# ── AC split (v3-011) ──────────────────────────────────────────


def test_suggest_ac_split_short_desc_returns_no_split() -> None:
    data = json.loads(_run(suggest_ac_split(description="User can add")))
    assert data["should_split"] is False


def test_suggest_ac_split_compound_returns_split() -> None:
    desc = (
        "Authenticated user can create, edit, and delete their own saved "
        "workouts, and share them with other users"
    )
    data = json.loads(_run(suggest_ac_split(description=desc)))
    assert data["should_split"] is True


# ── heartbeat + stall round-trip (v3-016) ─────────────────────


def test_heartbeat_and_stall_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"

    # 1. heartbeat creates the file
    out1 = _run(heartbeat_state(state_path=str(state_path), now_iso="2026-04-21T12:00:00+00:00"))
    d1 = json.loads(out1)
    assert d1["ok"] is True
    assert d1["last_progress_at"] == "2026-04-21T12:00:00+00:00"

    # 2. within threshold: not stalled
    out2 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:03:00+00:00",
        threshold_seconds=300,
    ))
    d2 = json.loads(out2)
    assert d2["stalled"] is False
    assert d2["elapsed_seconds"] == 180.0

    # 3. past threshold: stalled
    out3 = _run(is_state_stalled(
        state_path=str(state_path),
        now_iso="2026-04-21T12:06:00+00:00",
        threshold_seconds=300,
    ))
    d3 = json.loads(out3)
    assert d3["stalled"] is True

    # 4. recovery count bumps
    out4 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d4 = json.loads(out4)
    assert d4["ok"] is True
    assert d4["count"] == 1

    out5 = _run(increment_stall_recovery_count(state_path=str(state_path)))
    d5 = json.loads(out5)
    assert d5["count"] == 2

    # 5. reawake message
    out6 = _run(build_reawake_message(
        stage="design",
        detail_json=out3,  # stalled verdict
        count=1,
    ))
    d6 = json.loads(out6)
    assert d6["ok"] is True
    assert "design" in d6["message"]


def test_is_state_stalled_missing_file_does_not_raise(tmp_path: Path) -> None:
    out = _run(is_state_stalled(state_path=str(tmp_path / "missing.json")))
    data = json.loads(out)
    assert data["stalled"] is False
    assert data["reason"] == "state_missing"


def test_health_check_returns_required_fields() -> None:
    from samvil_mcp.server import health_check
    out = _run(health_check())
    data = json.loads(out)
    assert "samvil_version" in data
    assert "tool_count" in data
    assert "db_ok" in data
    assert "python_version" in data
    assert "summary" in data
    assert data["samvil_version"]
    assert isinstance(data["tool_count"], int)
    assert isinstance(data["db_ok"], bool)
    assert "." in data["python_version"]
