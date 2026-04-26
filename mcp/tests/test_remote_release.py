from __future__ import annotations

from samvil_mcp.remote_release import evaluate_remote_release_gate, render_remote_release_gate


def _run(**overrides):
    data = {
        "databaseId": 123,
        "workflowName": "SAMVIL Release Checks",
        "status": "completed",
        "conclusion": "success",
        "headSha": "abc123",
        "url": "https://example.invalid/run/123",
    }
    data.update(overrides)
    return data


def _runner(**summary_overrides):
    summary = {
        "status": "pass",
        "total_checks": 5,
        "passed_checks": 5,
        "failed_checks": 0,
        "missing_checks": 0,
    }
    summary.update(summary_overrides)
    return {
        "report": {
            "summary": summary,
            "checks": [
                {"name": "phase8_browser_inspection", "status": "pass", "exit_code": 0},
                {"name": "pre_commit", "status": "pass", "exit_code": 0},
            ],
            "next_action": "release checks passed",
        },
        "gate": {
            "verdict": "pass",
            "next_action": "ready to tag release",
        },
    }


def test_remote_release_gate_passes_when_run_and_runner_pass() -> None:
    gate = evaluate_remote_release_gate(run=_run(), runner=_runner(), expected_head="abc123")

    assert gate["verdict"] == "pass"
    assert gate["release_report_status"] == "pass"
    assert gate["failed_checks"] == 0
    assert "remote CI release evidence passed" in gate["reason"]


def test_remote_release_gate_blocks_failed_run_even_if_artifact_passes() -> None:
    gate = evaluate_remote_release_gate(
        run=_run(conclusion="failure"),
        runner=_runner(),
        expected_head="abc123",
    )

    assert gate["verdict"] == "blocked"
    assert gate["next_action"] == "fix remote release check run"
    assert "conclusion is not success" in gate["reason"]


def test_remote_release_gate_blocks_blocked_artifact_even_if_run_succeeded() -> None:
    gate = evaluate_remote_release_gate(
        run=_run(),
        runner=_runner(status="blocked", passed_checks=4, failed_checks=1),
        expected_head="abc123",
    )

    assert gate["verdict"] == "blocked"
    assert gate["failed_checks"] == 1
    assert "remote release report is not pass" in gate["reason"]


def test_remote_release_gate_blocks_head_mismatch() -> None:
    gate = evaluate_remote_release_gate(
        run=_run(headSha="old999"),
        runner=_runner(),
        expected_head="abc123",
    )

    assert gate["verdict"] == "blocked"
    assert "does not match expected" in gate["reason"]
    assert gate["next_action"] == "run release checks for current HEAD"


def test_render_remote_release_gate_includes_verdict_run_and_checks() -> None:
    gate = evaluate_remote_release_gate(run=_run(), runner=_runner(), expected_head="abc123")
    text = render_remote_release_gate(gate)

    assert "# Remote Release Gate" in text
    assert "Verdict: pass" in text
    assert "Run: 123" in text
    assert "5 passed / 0 failed / 0 missing" in text
