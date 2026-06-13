"""Regression tests for the v4.30.4 adversarial-review fixes.

Each test pins a bug that was proven (or constructed) during the
post-release code review: jobs lost-update race, orphan misclassification,
~ expansion, qa_history key mismatch, oscillation window stretch, and
drift's blindness to criterion/children AC shapes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from samvil_mcp.background_jobs import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    _exit_path,
    _job_path,
    _mutate_job,
    cancel_job,
    job_status,
    start_job,
)


def _wait_terminal(root: str, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = job_status(root, job_id)
        if snap["status"] != "running":
            return snap
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} still running")


def test_heartbeat_cannot_resurrect_cancelled_job(tmp_path: Path) -> None:
    """The proven lost-update race: cancel wins, heartbeat must no-op."""
    rec = start_job(str(tmp_path), "sleep 30")
    path = _job_path(tmp_path, rec["job_id"])
    out = cancel_job(str(tmp_path), rec["job_id"])
    assert out["status"] == STATUS_CANCELLED

    # Simulate the watcher's heartbeat arriving AFTER the cancel write —
    # exactly the interleaving from the review repro.
    def _heartbeat(data):
        if data.get("status") in {"completed", "failed", "cancelled", "interrupted"}:
            return None
        data["last_heartbeat_at"] = time.time()
        return data

    result = _mutate_job(path, _heartbeat)
    assert result["status"] == STATUS_CANCELLED  # not resurrected to running

    # And it stays cancelled after the watcher loop runs its course.
    time.sleep(0.5)
    assert job_status(str(tmp_path), rec["job_id"])["status"] == STATUS_CANCELLED


def test_orphan_with_exit_sidecar_finalizes_as_completed(tmp_path: Path) -> None:
    """MCP died mid-job but the command finished fine: the sidecar must
    yield COMPLETED + exit code, not INTERRUPTED."""
    jobs_dir = tmp_path / ".samvil" / "jobs"
    jobs_dir.mkdir(parents=True)
    job_file = jobs_dir / "job_deadbeef0001.json"
    job_file.write_text(
        json.dumps(
            {
                "job_id": "job_deadbeef0001",
                "kind": "build",
                "command": "echo done",
                "status": "running",
                "pid": 99999999,
                "log_path": ".samvil/jobs/job_deadbeef0001.log",
                "started_at": time.time() - 600,
                "last_heartbeat_at": time.time() - 600,
                "exit_code": None,
                "finished_at": None,
                "reason": "",
            }
        )
    )
    _exit_path(job_file).write_text("0")

    snap = job_status(str(tmp_path), "job_deadbeef0001")
    assert snap["status"] == STATUS_COMPLETED
    assert snap["exit_code"] == 0
    assert "sidecar" in snap["reason"]


def test_cancel_on_stale_record_reconciles_instead_of_killing(tmp_path: Path) -> None:
    jobs_dir = tmp_path / ".samvil" / "jobs"
    jobs_dir.mkdir(parents=True)
    job_file = jobs_dir / "job_deadbeef0002.json"
    job_file.write_text(
        json.dumps(
            {
                "job_id": "job_deadbeef0002",
                "kind": "build",
                "command": "exit 3",
                "status": "running",
                "pid": 99999999,
                "log_path": ".samvil/jobs/job_deadbeef0002.log",
                "started_at": time.time() - 600,
                "last_heartbeat_at": time.time() - 600,
                "exit_code": None,
                "finished_at": None,
                "reason": "",
            }
        )
    )
    _exit_path(job_file).write_text("3")

    out = cancel_job(str(tmp_path), "job_deadbeef0002")
    assert out["status"] == "failed"  # real outcome from the sidecar
    assert "reconciled" in out.get("note", "")


def test_project_root_tilde_is_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SKILL.md wires job_start(project_root='~/dev/<name>')."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "dev" / "myapp").mkdir(parents=True)
    rec = start_job("~/dev/myapp", "echo hi")
    _wait_terminal(str(tmp_path / "dev" / "myapp"), rec["job_id"])


def test_default_log_path_is_per_job(tmp_path: Path) -> None:
    a = start_job(str(tmp_path), "echo A")
    b = start_job(str(tmp_path), "echo B")
    assert a["log_path"] != b["log_path"]
    assert a["job_id"] in a["log_path"]


def test_qa_history_issues_key_fallback() -> None:
    """qa_finalize accepts `issues`; the loop gate must see it too."""
    from samvil_mcp.qa_synthesis import evaluate_qa_convergence

    history = [{"iteration": 1, "verdict": "REVISE", "issues": ["bug-a"]}]
    synthesis = {
        "verdict": "REVISE",
        "iteration": 2,
        "max_iterations": 5,
        "issue_ids": ["bug-a"],  # identical to previous iteration
    }
    gate = evaluate_qa_convergence(synthesis, history)
    assert gate["verdict"] == "blocked"
    assert "identical" in gate["reason"]


def test_oscillation_window_is_raw_rows_not_filtered() -> None:
    """Rows without ids must not stretch the window to ancient sets."""
    from samvil_mcp.qa_synthesis import _oscillating

    ancient = {"old-bug"}
    history = [
        {"iteration": 1, "issue_ids": ["old-bug"]},
        # five id-less rows push iteration 1 far outside window=3
        *({"iteration": i} for i in range(2, 7)),
        {"iteration": 7, "issue_ids": ["recent-bug"]},
    ]
    assert _oscillating(ancient, history, window=3) is False


def test_drift_sees_criterion_and_children() -> None:
    from samvil_mcp.drift import measure_drift

    base = {
        "description": "todo app",
        "features": [
            {
                "name": "todo",
                "acceptance_criteria": [
                    {
                        "criterion": "user adds a task quickly",
                        "children": [{"criterion": "enter key submits the form"}],
                    }
                ],
            }
        ],
    }
    rewritten = json.loads(json.dumps(base))
    rewritten["features"][0]["acceptance_criteria"] = [
        {
            "criterion": "player deals poker cards",
            "children": [{"criterion": "shuffle uses crypto randomness"}],
        }
    ]
    result = measure_drift(base, rewritten)
    assert result["ontology_drift"] > 0.5  # was 0.0 before the fix
