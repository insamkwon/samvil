from __future__ import annotations

from samvil_mcp.release_guards import (
    evaluate_publish_guard,
    evaluate_remote_release_gate,
    release_tag,
    render_publish_guard,
    render_remote_release_gate,
)


# ── Publish Guard ──────────────────────────────────────────────────────────


def _state(**overrides):
    state = {
        "version": "3.19.0",
        "tag": "v3.19.0",
        "branch": "main",
        "target_branch": "main",
        "head": "abc123",
        "clean": True,
        "version_synced": True,
        "local_tag_exists": False,
        "remote_tag_exists": False,
        "remote_branch_pushed": True,
        "local_release_gate": {"verdict": "pass", "next_action": "ready to tag release"},
        "remote_release_gate": {
            "verdict": "pass",
            "next_action": "ready to tag release",
            "run": {"id": 123},
        },
    }
    state.update(overrides)
    return state


def test_release_tag_adds_v_prefix() -> None:
    assert release_tag("3.19.0") == "v3.19.0"
    assert release_tag("v3.19.0") == "v3.19.0"


def test_publish_guard_passes_when_all_evidence_is_ready() -> None:
    gate = evaluate_publish_guard(_state())

    assert gate["verdict"] == "pass"
    assert gate["tag"] == "v3.19.0"
    assert gate["remote_run_id"] == 123


def test_publish_guard_blocks_dirty_tree() -> None:
    gate = evaluate_publish_guard(_state(clean=False))

    assert gate["verdict"] == "blocked"
    assert "working tree is not clean" in gate["reason"]
    assert gate["next_action"] == "commit or discard local changes"


def test_publish_guard_blocks_existing_remote_tag() -> None:
    gate = evaluate_publish_guard(_state(remote_tag_exists=True))

    assert gate["verdict"] == "blocked"
    assert "remote tag already exists" in gate["reason"]
    assert gate["next_action"] == "choose a new version"


def test_publish_guard_blocks_remote_gate_failure() -> None:
    gate = evaluate_publish_guard(
        _state(remote_release_gate={"verdict": "blocked", "next_action": "fix remote release check run"})
    )

    assert gate["verdict"] == "blocked"
    assert "remote release gate is not pass" in gate["reason"]
    assert gate["next_action"] == "fix remote release check run"


def test_render_publish_guard_includes_decision() -> None:
    text = render_publish_guard(evaluate_publish_guard(_state()))

    assert "# Verified Release Publisher" in text
    assert "Verdict: pass" in text
    assert "Tag: v3.19.0" in text


# ── Remote Release Gate ────────────────────────────────────────────────────


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
