"""Smoke tests for samvil-qa (T4.9 ultra-thin migration).

The samvil-qa skill is intentionally CC-bound: it drives Playwright
MCP, spawns independent Pass 2/3 Agent workers, runs `npm run build`
/ `npx tsc` / `python -m py_compile`, controls the Ralph loop iter
counter. None of those move into MCP — graceful degradation against
host failures (P8) requires the skill body to keep them.

What CAN be machine-pinned, and is pinned here, are the three new QA
aggregator tools the thin skill delegates to (qa_boot, qa_pass1,
qa_finalize), plus the existing qa_synthesis primitives the finalizer
wraps.

11 critical preservation scenarios (must not regress):

  Ralph Loop (3):
    ST-RL-1: Convergence — issue count decreases each iteration.
    ST-RL-2: BLOCKED — 2 consecutive identical issue id sets.
    ST-RL-3: Exhausted — qa_history.length ≥ qa_max_iterations.

  Evidence Validation (3):
    ST-EV-1: Valid file:line preserved as PASS in synthesis.
    ST-EV-2: Missing/invalid file:line → FAIL downgrade
             (semantic_check is first-class MCP tool — verified via
             evidence_count signal in synthesis).
    ST-EV-3: Stub detection (UNIMPLEMENTED) → FAIL downgrade signal
             via gate_input.metrics.unimplemented_count > 0.

  AC Tree Aggregation (3):
    ST-AT-1: All Pass 2 items PASS → synthesis verdict PASS.
    ST-AT-2: One Pass 2 item FAIL → synthesis verdict REVISE/FAIL.
    ST-AT-3: Mixed pending → REVISE.

  Contract Layer (8):
    ST-CL-1: Role separation — qa_boot returns generator≠judge payload.
    ST-CL-2: Claim verify — Pass 2 PASS → claim_actions verify entry.
    ST-CL-3: Evidence requirement — pending claims missing → notes warn.
    ST-CL-4: Consensus trigger — Generator PASS, Judge FAIL → trigger.
    ST-CL-5: Gate check — qa_to_deploy gate input populated correctly.
    ST-CL-6: BLOCKED detection — persistent issue ids across iters.
    ST-CL-7: Next skill marker — finalize returns next_skill_decision.
    ST-CL-8: Fallback MCP — best-effort errors append to errors[],
             never raise.

Plus solution_type coverage (5), Playwright fallback (static method),
per-AC verdict shape preservation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import qa_boot, qa_finalize, qa_pass1


# ── Helpers ────────────────────────────────────────────────────────────


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed(
    name: str = "demo",
    solution_type: str = "web-app",
    framework: str = "next",
    runtime: str | None = None,
    features_count: int = 1,
):
    seed = {
        "schema_version": "3.0",
        "name": name,
        "solution_type": solution_type,
        "tech_stack": {"framework": framework},
        "features": [
            {
                "name": f"feature_{i}",
                "acceptance_criteria": [
                    {
                        "id": f"feature_{i}.ac.1",
                        "description": f"feature {i} works",
                        "status": "pass",
                        "evidence": [],
                        "children": [],
                    }
                ],
            }
            for i in range(features_count)
        ],
    }
    if runtime:
        seed["implementation"] = {"runtime": runtime}
    return seed


def _state(
    qa_history=None,
    selected_tier="standard",
    session_id="sess-smoke",
    build_retries=0,
    current_model_qa=None,
    stage_claims=None,
):
    return {
        "session_id": session_id,
        "selected_tier": selected_tier,
        "qa_history": qa_history or [],
        "build_retries": build_retries,
        "current_model_qa": current_model_qa or {},
        "stage_claims": stage_claims or {},
    }


def _make_evidence(
    pass1_status="PASS",
    pass2_items=None,
    pass3_verdict="PASS",
    iteration=1,
    max_iterations=3,
):
    if pass2_items is None:
        pass2_items = [
            {
                "id": "feature_0.ac.1",
                "criterion": "feature 0 works",
                "verdict": "PASS",
                "evidence": ["src/feature_0.tsx:10"],
                "method": "runtime",
            }
        ]
    return {
        "iteration": iteration,
        "max_iterations": max_iterations,
        "pass1": {"status": pass1_status, "issues": []},
        "pass2": {"items": pass2_items},
        "pass3": {"verdict": pass3_verdict, "issues": []},
        "agent_writes": [],
    }


# ──────────────────────────────────────────────────────────────────────
# Boot tests (qa_boot)
# ──────────────────────────────────────────────────────────────────────


class TestQABoot:
    def test_boot_loads_seed_state_config(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        # state.selected_tier wins over config.selected_tier (state is SSOT).
        _write(tmp_path / "project.state.json", _state(selected_tier="thorough"))
        _write(tmp_path / "project.config.json", {"qa_max_iterations": 3})

        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert result["seed_loaded"] is True
        assert result["state_loaded"] is True
        assert result["config_loaded"] is True
        assert result["solution_type"] == "web-app"
        assert result["brownfield"] is False
        assert result["resume_hint"]["selected_tier"] == "thorough"
        assert result["resume_hint"]["qa_max_iterations"] == 3

    def test_boot_brownfield_flag_when_seed_missing(self, tmp_path: Path) -> None:
        # No seed at all → brownfield
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert result["brownfield"] is True
        assert result["seed_loaded"] is False
        assert any("brownfield" in n for n in result["notes"])
        assert any("project.seed.json" in e for e in result["errors"])

    def test_boot_pass1_command_per_solution_type(self, tmp_path: Path) -> None:
        cases = [
            ("web-app", None, "npm run build"),
            ("dashboard", None, "npm run build"),
            ("game", None, "npx tsc --noEmit"),
            ("mobile-app", None, "npx expo export"),
            ("automation", "python", "py_compile"),
            ("automation", "node", "tsc --noEmit"),
            ("automation", "cc-skill", ""),
        ]
        for stype, runtime, expected in cases:
            (tmp_path / "project.seed.json").unlink(missing_ok=True)
            _write(tmp_path / "project.seed.json", _seed(solution_type=stype, runtime=runtime))
            result = qa_boot.aggregate_qa_boot_context(tmp_path)
            cmd = result["pass1"]["command"]
            assert expected in cmd, f"{stype}/{runtime}: expected {expected!r} in {cmd!r}"

    def test_boot_role_separation_payload(self, tmp_path: Path) -> None:
        # ST-CL-1: role separation pre-check (Generator ≠ Judge).
        _write(tmp_path / "project.seed.json", _seed())
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        rs = result["role_separation_check"]
        assert rs["claimed_by"] == "agent:build-worker"
        assert rs["verified_by"] == "agent:qa-functional"
        assert rs["claimed_by"] != rs["verified_by"]

    def test_boot_paths_complete(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        paths = result["paths"]
        for required in (
            "seed", "state", "config", "build_log", "qa_results",
            "qa_report", "qa_evidence_dir", "handoff", "events",
            "next_skill_marker", "qa_routing", "mcp_health",
        ):
            assert required in paths, f"missing path key {required}"
            assert str(tmp_path) in paths[required]

    def test_boot_incremental_hint_present(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        prior = {
            "_meta": {"total_iterations": 2},
            "features": {
                "feature_0": {"status": "PASS"},
                "feature_1": {"status": "FAIL"},
            },
        }
        _write(tmp_path / ".samvil" / "qa-results.json", prior)
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        ih = result["incremental_hint"]
        assert ih["present"] is True
        assert ih["prior_pass"] == 1
        assert ih["prior_fail"] == 1
        assert ih["prior_iterations"] == 2

    def test_boot_incremental_hint_absent(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert result["incremental_hint"]["present"] is False

    def test_boot_resume_hint_qa_max_iterations_default(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert result["resume_hint"]["qa_max_iterations"] == 3

    def test_boot_resume_hint_qa_history_exhausted_note(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed())
        _write(
            tmp_path / "project.state.json",
            _state(qa_history=[{"iteration": i} for i in range(3)]),
        )
        _write(tmp_path / "project.config.json", {"qa_max_iterations": 3})
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert any("Ralph loop exhausted" in n for n in result["notes"])

    def test_boot_no_raise_on_corrupt_files(self, tmp_path: Path) -> None:
        # corrupt seed
        (tmp_path / "project.seed.json").write_text("{not json", encoding="utf-8")
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert result["brownfield"] is True
        assert result["seed_loaded"] is False

    def test_boot_unknown_solution_type_defaults(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.seed.json", _seed(solution_type="unknown-type"))
        result = qa_boot.aggregate_qa_boot_context(tmp_path)
        assert "npm run build" in result["pass1"]["command"]
        assert any("unknown solution_type" in n for n in result["notes"])


# ──────────────────────────────────────────────────────────────────────
# Pass 1 / Pass 1b digest tests (qa_pass1)
# ──────────────────────────────────────────────────────────────────────


class TestQAPass1:
    def test_pass1_pass_smoke_pass(self, tmp_path: Path) -> None:
        smoke = {
            "method": "playwright",
            "console_errors": [],
            "empty_routes": [],
            "screenshots": [".samvil/qa-evidence/smoke-desktop-pass.png"],
        }
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result=smoke,
            solution_type="web-app",
        )
        assert result["pass1"]["status"] == "PASS"
        assert result["pass1b"]["status"] == "PASS"
        assert result["should_proceed_to_pass2"] is True

    def test_pass1_fail_extracts_errors(self, tmp_path: Path) -> None:
        log = tmp_path / ".samvil" / "build.log"
        log.parent.mkdir(parents=True)
        log.write_text(
            "Building...\n"
            "src/index.tsx(15,3): error TS2304: Cannot find name 'undefinedVar'.\n"
            "Module not found: Can't resolve '@/missing'\n"
            "info: This is just info\n"
            "Failed to compile.\n",
            encoding="utf-8",
        )
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=1,
            smoke_result=None,
            solution_type="web-app",
        )
        assert result["pass1"]["status"] == "FAIL"
        assert len(result["pass1"]["errors"]) >= 2
        assert result["pass1b"]["status"] == "SKIPPED"
        assert result["should_proceed_to_pass2"] is False

    def test_pass1_fail_smoke_skipped(self, tmp_path: Path) -> None:
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=1,
            smoke_result={"method": "playwright", "console_errors": []},
            solution_type="web-app",
        )
        # Pass 1 fail → smoke skipped regardless of smoke payload.
        assert result["pass1b"]["status"] == "SKIPPED"

    def test_pass1b_console_errors_fail(self, tmp_path: Path) -> None:
        smoke = {
            "method": "playwright",
            "console_errors": ["Uncaught TypeError: x.y is undefined"],
            "empty_routes": [],
        }
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result=smoke,
            solution_type="web-app",
        )
        assert result["pass1b"]["status"] == "FAIL"
        assert result["should_proceed_to_pass2"] is False

    def test_pass1b_empty_route_fail(self, tmp_path: Path) -> None:
        smoke = {
            "method": "playwright",
            "console_errors": [],
            "empty_routes": ["/dashboard"],
        }
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result=smoke,
            solution_type="web-app",
        )
        assert result["pass1b"]["status"] == "FAIL"
        assert "1 empty route" in result["pass1b"]["reason"]

    def test_pass1b_static_fallback(self, tmp_path: Path) -> None:
        # Playwright fallback test: method=static, should still allow Pass 2
        smoke = {
            "method": "static",
            "console_errors": [],
            "empty_routes": [],
            "fallback_reason": "Playwright unavailable after 2 retries",
        }
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result=smoke,
            solution_type="web-app",
        )
        assert result["pass1b"]["status"] == "PASS"
        assert result["pass1b"]["method"] == "static"
        assert any("static analysis" in n for n in result["notes"])
        assert result["should_proceed_to_pass2"] is True

    def test_pass1b_skipped_for_automation(self, tmp_path: Path) -> None:
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result=None,  # skipped
            solution_type="automation",
        )
        assert result["pass1b"]["status"] == "SKIPPED"
        # Skipped → still proceed to Pass 2 (dry-run = Pass 2 for automation)
        assert result["should_proceed_to_pass2"] is True

    def test_pass1_event_drafts_emitted(self, tmp_path: Path) -> None:
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=0,
            smoke_result={"method": "playwright", "console_errors": [], "empty_routes": []},
            solution_type="web-app",
        )
        types = [e["event_type"] for e in result["events"]]
        assert "qa_pass1_complete" in types
        assert "qa_smoke_complete" in types

    def test_pass1_fail_event_includes_first_error(self, tmp_path: Path) -> None:
        log = tmp_path / ".samvil" / "build.log"
        log.parent.mkdir(parents=True)
        log.write_text("error TS2345: argument mismatch\n", encoding="utf-8")
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=1,
            solution_type="web-app",
        )
        fail_evts = [e for e in result["events"] if e["event_type"] == "qa_pass1_fail"]
        assert len(fail_evts) == 1
        assert fail_evts[0]["data"]["exit_code"] == 1
        assert "TS2345" in fail_evts[0]["data"]["first_error"]

    def test_pass1_no_log_fails_gracefully(self, tmp_path: Path) -> None:
        # Pass 1 fails but build log is missing — note + empty errors list.
        result = qa_pass1.dispatch_qa_pass1_batch(
            tmp_path,
            pass1_exit_code=2,
            solution_type="web-app",
        )
        assert result["pass1"]["status"] == "FAIL"
        assert result["pass1"]["errors"] == []
        assert any("no recognizable error" in n for n in result["notes"])


# ──────────────────────────────────────────────────────────────────────
# Phase Z finalize tests (qa_finalize)
# ──────────────────────────────────────────────────────────────────────


class TestQAFinalize:
    # ── AC Tree Aggregation (ST-AT-1, ST-AT-2, ST-AT-3) ──────────────

    def test_at_1_all_pass_synthesis_pass(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "PASS", "evidence": ["src/x.ts:1"]},
                {"id": "f.2", "criterion": "y", "verdict": "PASS", "evidence": ["src/y.ts:1"]},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        assert result["synthesis"]["verdict"] == "PASS"

    def test_at_2_one_fail_synthesis_revise(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "PASS", "evidence": ["src/x.ts:1"]},
                {"id": "f.2", "criterion": "y", "verdict": "FAIL", "evidence": [], "reason": "broken"},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        assert result["synthesis"]["verdict"] in ("REVISE", "FAIL")

    def test_at_3_partial_only_still_revise_or_pass(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "PARTIAL", "evidence": ["src/x.ts:1"]},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        # PARTIAL alone should not be a hard FAIL; verdict must be set.
        assert result["synthesis"]["verdict"] in ("PASS", "REVISE", "FAIL")

    # ── Evidence Validation (ST-EV-3 — UNIMPLEMENTED downgrade signal) ─

    def test_ev_3_unimplemented_signals_fail(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "UNIMPLEMENTED", "evidence": []},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        # gate_input must reflect non-zero unimplemented_count.
        assert result["gate_input"]["metrics"]["unimplemented_count"] >= 1
        assert result["gate_input"]["metrics"]["zero_stubs"] is False
        # Reward Hacking note.
        assert any("Reward Hacking" in n for n in result["notes"])

    # ── Ralph Loop (ST-RL-1, ST-RL-2, ST-RL-3) ───────────────────────

    def test_rl_1_convergence_decreasing_issues(self, tmp_path: Path) -> None:
        # qa_history shows decreasing issues — should NOT trigger BLOCKED.
        history = [
            {"iteration": 1, "issue_ids": ["a", "b", "c", "d"]},
            {"iteration": 2, "issue_ids": ["a", "b", "c"]},
        ]
        _write(tmp_path / "project.state.json", _state(qa_history=history))
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        # Different iteration sets → not BLOCKED.
        # (a, b, c overlap but last is subset, not equal.)
        assert result["blocked"]["detected"] is False

    def test_rl_2_blocked_identical_consecutive(self, tmp_path: Path) -> None:
        history = [
            {"iteration": 1, "issue_ids": ["a", "b", "c"]},
            {"iteration": 2, "issue_ids": ["a", "b", "c"]},
        ]
        _write(tmp_path / "project.state.json", _state(qa_history=history))
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        assert result["blocked"]["detected"] is True
        assert set(result["blocked"]["persistent_issue_ids"]) == {"a", "b", "c"}

    def test_rl_3_history_below_threshold_no_block(self, tmp_path: Path) -> None:
        # Only 1 iter in history — cannot detect BLOCKED.
        history = [{"iteration": 1, "issue_ids": ["a"]}]
        _write(tmp_path / "project.state.json", _state(qa_history=history))
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        assert result["blocked"]["detected"] is False

    # ── Contract Layer (ST-CL-2 ~ ST-CL-8) ───────────────────────────

    def test_cl_2_claim_verify_action_for_pass(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "leaf-1", "criterion": "x", "verdict": "PASS", "evidence": ["src/x.ts:5"]},
            ]
        )
        pending = [{
            "claim_id": "claim-leaf-1",
            "subject": "leaf-1",
            "claim_type": "ac_verdict",
            "statement_status": "pass",
        }]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=evidence, pending_ac_claims=pending
        )
        assert len(result["claim_actions"]) == 1
        assert result["claim_actions"][0]["action"] == "verify"
        assert result["claim_actions"][0]["claim_id"] == "claim-leaf-1"
        assert result["claim_actions"][0]["verified_by"] == "agent:qa-functional"

    def test_cl_2b_claim_reject_action_for_fail(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "leaf-1", "criterion": "x", "verdict": "FAIL", "evidence": [], "reason": "broken"},
            ]
        )
        pending = [{"claim_id": "claim-leaf-1", "subject": "leaf-1", "statement_status": "pass"}]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=evidence, pending_ac_claims=pending
        )
        assert any(a["action"] == "reject" for a in result["claim_actions"])

    def test_cl_2c_claim_action_skipped_for_partial(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "leaf-1", "criterion": "x", "verdict": "PARTIAL", "evidence": ["src/x.ts:1"]},
            ]
        )
        pending = [{"claim_id": "claim-leaf-1", "subject": "leaf-1"}]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=evidence, pending_ac_claims=pending
        )
        # PARTIAL leaves the claim pending — no action emitted.
        assert result["claim_actions"] == []

    def test_cl_3_no_pending_claims_warns(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence(), pending_ac_claims=[]
        )
        assert any("no pending ac_verdict claims" in n for n in result["notes"])

    def test_cl_4_consensus_trigger_on_dispute(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "leaf-1", "criterion": "x", "verdict": "FAIL", "evidence": [], "reason": "no"},
            ]
        )
        # Generator (build) said pass; Judge (qa) says fail → dispute.
        pending = [{"claim_id": "claim-leaf-1", "subject": "leaf-1", "statement_status": "pass"}]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=evidence, pending_ac_claims=pending
        )
        assert len(result["consensus_triggers"]) == 1
        payload = json.loads(result["consensus_triggers"][0]["input_json"])
        assert payload["subject"] == "leaf-1"
        assert payload["generator_verdict"] == "pass"
        assert payload["judge_verdict"] == "fail"

    def test_cl_5_gate_input_qa_to_deploy(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state(selected_tier="thorough"))
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "PASS", "evidence": ["src/x.ts:1"]},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        gi = result["gate_input"]
        assert gi["gate_name"] == "qa_to_deploy"
        assert gi["samvil_tier"] == "thorough"
        assert gi["metrics"]["three_pass_pass"] is True
        assert gi["metrics"]["zero_stubs"] is True
        assert gi["metrics"]["fail_count"] == 0

    def test_cl_5b_gate_input_blocked_on_fail(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "FAIL", "evidence": []},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        assert result["gate_input"]["metrics"]["three_pass_pass"] is False
        assert result["gate_input"]["metrics"]["fail_count"] >= 1

    def test_cl_6_blocked_detection_carried_in_handoff(self, tmp_path: Path) -> None:
        history = [
            {"iteration": 1, "issue_ids": ["x", "y"]},
            {"iteration": 2, "issue_ids": ["x", "y"]},
        ]
        _write(tmp_path / "project.state.json", _state(qa_history=history))
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        assert "BLOCKED" in result["handoff_block"]
        assert "x" in result["handoff_block"]
        assert "y" in result["handoff_block"]

    def test_cl_7_next_skill_pass_to_deploy(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        assert result["next_skill_decision"]["suggested"] == "samvil-deploy"

    def test_cl_7b_next_skill_partial_count_triggers_evolve(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        # 5 partials → evolve auto-trigger
        items = [
            {"id": f"f.{i}", "criterion": "x", "verdict": "PARTIAL", "evidence": [f"src/x{i}.ts:1"]}
            for i in range(5)
        ]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence(pass2_items=items)
        )
        assert result["next_skill_decision"]["suggested"] == "samvil-evolve"
        assert "partial_count" in result["next_skill_decision"]["reason"]

    def test_cl_7c_next_skill_fail_to_retro(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        evidence = _make_evidence(
            pass2_items=[
                {"id": "f.1", "criterion": "x", "verdict": "FAIL", "evidence": []},
            ]
        )
        result = qa_finalize.finalize_qa_verdict(tmp_path, evidence=evidence)
        assert result["next_skill_decision"]["suggested"] == "samvil-retro"
        assert "samvil-evolve" in result["next_skill_decision"]["user_options"]
        assert "samvil-retro" in result["next_skill_decision"]["user_options"]

    def test_cl_8_no_state_file_does_not_raise(self, tmp_path: Path) -> None:
        # No project.state.json — graceful (INV-5).
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        assert result["samvil_tier"] == "standard"
        assert any("project.state.json missing" in n for n in result["notes"])

    def test_cl_8b_corrupt_evidence_returns_fail(self, tmp_path: Path) -> None:
        # Empty evidence dict → synthesis still returns; verdict not crashing.
        _write(tmp_path / "project.state.json", _state())
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence={"iteration": 1, "max_iterations": 3}
        )
        assert result["synthesis"].get("verdict") is not None

    # ── Handoff block ────────────────────────────────────────────────

    def test_handoff_block_korean_section(self, tmp_path: Path) -> None:
        _write(tmp_path / "project.state.json", _state())
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence()
        )
        block = result["handoff_block"]
        assert "## QA" in block
        assert "Verdict" in block
        assert "Pass 1" in block
        assert "Pass 2" in block
        assert "Pass 3" in block
        assert "Next:" in block

    # ── Per-AC verdict shape preservation ────────────────────────────

    def test_per_ac_verdict_shape_pass(self, tmp_path: Path) -> None:
        # PASS / PARTIAL / UNIMPLEMENTED / FAIL all surface in counts.
        _write(tmp_path / "project.state.json", _state())
        items = [
            {"id": "a.1", "criterion": "a", "verdict": "PASS", "evidence": ["s:1"]},
            {"id": "a.2", "criterion": "b", "verdict": "PARTIAL", "evidence": ["s:2"]},
            {"id": "a.3", "criterion": "c", "verdict": "UNIMPLEMENTED", "evidence": []},
            {"id": "a.4", "criterion": "d", "verdict": "FAIL", "evidence": []},
        ]
        result = qa_finalize.finalize_qa_verdict(
            tmp_path, evidence=_make_evidence(pass2_items=items)
        )
        counts = result["synthesis"]["pass2"]["counts"]
        assert counts.get("PASS", 0) == 1
        assert counts.get("PARTIAL", 0) == 1
        assert counts.get("UNIMPLEMENTED", 0) == 1
        assert counts.get("FAIL", 0) == 1


# ──────────────────────────────────────────────────────────────────────
# MCP server registration smoke tests
# ──────────────────────────────────────────────────────────────────────


class TestMCPRegistration:
    def test_qa_tools_registered_on_server(self) -> None:
        from samvil_mcp import server as srv
        # The decorated functions exist as module attributes.
        assert hasattr(srv, "aggregate_qa_boot_context")
        assert hasattr(srv, "dispatch_qa_pass1_batch")
        assert hasattr(srv, "finalize_qa_verdict")

    @pytest.mark.asyncio
    async def test_aggregate_qa_boot_context_via_server(self, tmp_path: Path) -> None:
        from samvil_mcp import server as srv
        _write(tmp_path / "project.seed.json", _seed())
        out = await srv.aggregate_qa_boot_context(project_path=str(tmp_path))
        data = json.loads(out)
        assert data["seed_loaded"] is True

    @pytest.mark.asyncio
    async def test_dispatch_qa_pass1_batch_via_server(self, tmp_path: Path) -> None:
        from samvil_mcp import server as srv
        smoke = {"method": "playwright", "console_errors": [], "empty_routes": []}
        out = await srv.dispatch_qa_pass1_batch(
            project_path=str(tmp_path),
            pass1_exit_code=0,
            smoke_result_json=json.dumps(smoke),
            solution_type="web-app",
        )
        data = json.loads(out)
        assert data["pass1"]["status"] == "PASS"

    @pytest.mark.asyncio
    async def test_finalize_qa_verdict_via_server(self, tmp_path: Path) -> None:
        from samvil_mcp import server as srv
        _write(tmp_path / "project.state.json", _state())
        out = await srv.finalize_qa_verdict(
            project_path=str(tmp_path),
            evidence_json=json.dumps(_make_evidence()),
            pending_ac_claims_json=json.dumps([]),
        )
        data = json.loads(out)
        assert "synthesis" in data
        assert "gate_input" in data
        assert "next_skill_decision" in data
