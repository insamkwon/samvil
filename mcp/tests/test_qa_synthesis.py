"""Tests for central QA synthesis."""

from __future__ import annotations

import json

from samvil_mcp.qa_synthesis import (
    evaluate_qa_convergence,
    materialize_qa_synthesis,
    qa_summary,
    read_qa_results,
    render_qa_synthesis,
    synthesize_qa_evidence,
)


def _base(pass2_items: list[dict], pass3: dict | None = None) -> dict:
    return {
        "iteration": 1,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": pass2_items},
        "pass3": pass3 or {"verdict": "PASS"},
    }


def test_synthesis_passes_with_partial_functional_evidence():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
        {"id": "AC-2", "criterion": "Drag feel", "verdict": "PARTIAL", "reason": "runtime feel"},
    ]))

    assert result["verdict"] == "PASS"
    assert result["pass2"]["counts"]["PARTIAL"] == 1
    assert any(event["event_type"] == "qa_partial" for event in result["events"])


def test_synthesis_labels_pass_by_verification_mode() -> None:
    static = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS"},
    ]))
    runtime_input = _base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS"},
    ])
    runtime_input["verification_mode"] = "runtime"
    runtime = synthesize_qa_evidence(runtime_input)

    assert static["verdict"] == "PASS"
    assert static["verification_mode"] == "static"
    assert runtime["verification_mode"] == "runtime"
    assert "PASS(static)" in render_qa_synthesis(static)
    assert "PASS(runtime)" in render_qa_synthesis(runtime)


def test_synthesis_revises_on_unimplemented_non_core_ac():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"},
    ]))

    assert result["verdict"] == "REVISE"
    assert result["next_action"] == "replace stubs or hardcoded paths with real implementation"
    assert result["issue_ids"] == ["pass2:AC-1:UNIMPLEMENTED"]
    assert any(event["event_type"] == "qa_unimplemented" for event in result["events"])


def test_qa_convergence_blocks_identical_consecutive_issues():
    previous = [{
        "iteration": 1,
        "verdict": "REVISE",
        "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
    }]
    synthesis = synthesize_qa_evidence({
        "iteration": 2,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })

    gate = evaluate_qa_convergence(synthesis, previous)

    assert gate["gate"] == "qa_convergence"
    assert gate["verdict"] == "blocked"
    assert gate["reason"] == "identical QA issues persisted across two consecutive iterations"
    assert gate["issue_count"] == 1
    assert gate["previous_issue_count"] == 1


def test_qa_convergence_allows_decreasing_revise_cycle():
    previous = [{
        "iteration": 1,
        "verdict": "REVISE",
        "issue_ids": ["pass2:AC-1:UNIMPLEMENTED", "pass3:missing-focus-state"],
    }]
    synthesis = synthesize_qa_evidence({
        "iteration": 2,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })

    gate = evaluate_qa_convergence(synthesis, previous)

    assert gate["verdict"] == "continue"
    assert gate["resolved_issue_ids"] == ["pass3:missing-focus-state"]


def test_synthesis_fails_on_core_unimplemented():
    result = synthesize_qa_evidence(_base([
        {
            "id": "AC-core",
            "criterion": "Primary flow",
            "verdict": "UNIMPLEMENTED",
            "is_core_experience": True,
        },
    ]))

    assert result["verdict"] == "FAIL"
    assert result["reason"] == "core experience is unimplemented"


def test_synthesis_revises_for_quality_only_issue():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ], pass3={"verdict": "REVISE", "issues": ["missing focus state"]}))

    assert result["verdict"] == "REVISE"
    assert result["reason"] == "quality QA requires revision"


def test_synthesis_blocks_independent_protected_writes():
    data = _base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ])
    data["agent_writes"] = [{"agent": "qa-functional", "path": ".samvil/qa-report.md"}]

    result = synthesize_qa_evidence(data)

    assert result["verdict"] == "REVISE"
    assert result["reason"] == "independent QA attempted protected writes"
    assert result["ownership_violations"] == [{"agent": "qa-functional", "path": ".samvil/qa-report.md"}]


def test_render_qa_synthesis_includes_verdict_and_counts():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ]))

    rendered = render_qa_synthesis(result)

    assert "# QA Synthesis" in rendered
    assert "- Verdict: PASS" in rendered
    assert "PASS=1" in rendered


def test_materialize_qa_synthesis_writes_report_results_events_and_state(tmp_path):
    (tmp_path / "project.state.json").write_text(
        json.dumps({"session_id": "s1", "current_stage": "qa", "qa_history": []}),
        encoding="utf-8",
    )
    synthesis = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"},
    ]))

    result = materialize_qa_synthesis(tmp_path, synthesis)

    assert result["status"] == "ok"
    assert result["verdict"] == "REVISE"
    assert result["events_appended"] == 2
    persisted = read_qa_results(tmp_path)
    assert persisted["synthesis"]["verdict"] == "REVISE"
    assert persisted["convergence"]["verdict"] == "continue"
    assert (tmp_path / ".samvil" / "qa-report.md").read_text(encoding="utf-8").startswith("# QA Synthesis")
    events = [
        json.loads(line)
        for line in (tmp_path / ".samvil" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == ["qa_unimplemented", "qa_verdict"]
    assert events[0]["session_id"] == "s1"
    assert events[0]["timestamp"]
    assert "ts" not in events[0]
    state = json.loads((tmp_path / "project.state.json").read_text(encoding="utf-8"))
    assert state["last_qa_verdict"] == "REVISE"
    assert state["last_qa_verification_mode"] == "static"
    assert state["last_qa_convergence"]["verdict"] == "continue"
    assert state["qa_history"][0]["issue_ids"] == ["pass2:AC-1:UNIMPLEMENTED"]
    assert state["qa_history"][0]["pass2_counts"]["UNIMPLEMENTED"] == 1
    summary = qa_summary(tmp_path)
    assert summary["present"] is True
    assert summary["verdict"] == "REVISE"
    assert summary["convergence"]["verdict"] == "continue"
    assert summary["pass2_counts"]["UNIMPLEMENTED"] == 1


def test_materialize_qa_synthesis_marks_blocked_on_repeated_issues(tmp_path):
    (tmp_path / "project.state.json").write_text(
        json.dumps({
            "session_id": "s1",
            "current_stage": "qa",
            "qa_history": [{
                "iteration": 1,
                "verdict": "REVISE",
                "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
            }],
        }),
        encoding="utf-8",
    )
    synthesis = synthesize_qa_evidence({
        "iteration": 2,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"},
        ]},
        "pass3": {"verdict": "PASS"},
    })

    result = materialize_qa_synthesis(tmp_path, synthesis)

    assert result["convergence"]["verdict"] == "blocked"
    persisted = read_qa_results(tmp_path)
    assert persisted["convergence"]["next_action"] == "manual intervention: evolve seed, skip to retro, or fix manually"
    events = [
        json.loads(line)
        for line in (tmp_path / ".samvil" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == ["qa_unimplemented", "qa_verdict", "qa_blocked"]


# ── W4.2 oscillation detection (MCP-owned ralph loop control) ──────


def test_oscillation_a_b_a_is_blocked() -> None:
    """Issue set A recurs after an intermediate different set B."""
    from samvil_mcp.qa_synthesis import evaluate_qa_convergence

    set_a = ["pass2:ac-1:fail", "pass3:perf"]
    set_b = ["pass2:ac-2:fail"]
    history = [
        {"iteration": 1, "verdict": "REVISE", "issue_ids": set_a},
        {"iteration": 2, "verdict": "REVISE", "issue_ids": set_b},
    ]
    synthesis = {
        "verdict": "REVISE",
        "iteration": 3,
        "max_iterations": 5,
        "issue_ids": set_a,  # A again — fixes are cycling
    }
    gate = evaluate_qa_convergence(synthesis, history)
    assert gate["verdict"] == "blocked"
    assert "oscillation" in gate["reason"]


def test_shrinking_issue_set_continues() -> None:
    from samvil_mcp.qa_synthesis import evaluate_qa_convergence

    history = [
        {"iteration": 1, "verdict": "REVISE", "issue_ids": ["a", "b", "c"]},
        {"iteration": 2, "verdict": "REVISE", "issue_ids": ["a", "b"]},
    ]
    synthesis = {
        "verdict": "REVISE",
        "iteration": 3,
        "max_iterations": 5,
        "issue_ids": ["a"],
    }
    gate = evaluate_qa_convergence(synthesis, history)
    assert gate["verdict"] == "continue"


def test_oscillation_needs_two_history_rows() -> None:
    """With a single history row the oscillation rule must not fire —
    any block here comes from the (stricter) count rule instead."""
    from samvil_mcp.qa_synthesis import evaluate_qa_convergence

    history = [{"iteration": 1, "verdict": "REVISE", "issue_ids": ["x"]}]
    synthesis = {
        "verdict": "REVISE",
        "iteration": 2,
        "max_iterations": 5,
        "issue_ids": ["y"],
    }
    gate = evaluate_qa_convergence(synthesis, history)
    assert "oscillation" not in gate["reason"]
    # same count as previous -> existing no-decrease rule blocks
    assert gate["verdict"] == "blocked"
