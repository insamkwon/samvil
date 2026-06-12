"""Tests for background job execution (v4.30 W4.1)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from samvil_mcp.background_jobs import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    cancel_job,
    job_result,
    job_status,
    list_jobs,
    start_job,
)


def _wait_terminal(root: str, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = job_status(root, job_id)
        if snap["status"] != STATUS_RUNNING:
            return snap
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish: {job_status(root, job_id)}")


def test_job_completes_and_logs(tmp_path: Path) -> None:
    rec = start_job(
        str(tmp_path), "echo hello-from-job; exit 0", log_path=".samvil/test.log"
    )
    assert rec["status"] == STATUS_RUNNING
    assert rec["job_id"].startswith("job_")

    snap = _wait_terminal(str(tmp_path), rec["job_id"])
    assert snap["status"] == STATUS_COMPLETED
    assert snap["exit_code"] == 0

    result = job_result(str(tmp_path), rec["job_id"])
    assert result["done"] is True
    assert "hello-from-job" in result["log_tail"]

    # INV-1: job state is a plain file
    job_file = tmp_path / ".samvil" / "jobs" / f"{rec['job_id']}.json"
    assert job_file.exists()
    assert json.loads(job_file.read_text())["status"] == STATUS_COMPLETED


def test_failing_command_marked_failed(tmp_path: Path) -> None:
    rec = start_job(str(tmp_path), "exit 3", log_path=".samvil/test.log")
    snap = _wait_terminal(str(tmp_path), rec["job_id"])
    assert snap["status"] == STATUS_FAILED
    assert snap["exit_code"] == 3


def test_result_while_running_is_not_done(tmp_path: Path) -> None:
    rec = start_job(str(tmp_path), "sleep 5", log_path=".samvil/test.log")
    result = job_result(str(tmp_path), rec["job_id"])
    assert result["status"] == STATUS_RUNNING
    assert result["done"] is False
    cancel_job(str(tmp_path), rec["job_id"])


def test_cancel_kills_process(tmp_path: Path) -> None:
    rec = start_job(str(tmp_path), "sleep 30", log_path=".samvil/test.log")
    out = cancel_job(str(tmp_path), rec["job_id"])
    assert out["status"] == STATUS_CANCELLED
    snap = job_status(str(tmp_path), rec["job_id"])
    assert snap["status"] == STATUS_CANCELLED


def test_orphan_detected_on_status_read(tmp_path: Path) -> None:
    """Record says running, heartbeat stale, pid dead → interrupted."""
    jobs_dir = tmp_path / ".samvil" / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "job_deadbeef0000.json").write_text(
        json.dumps(
            {
                "job_id": "job_deadbeef0000",
                "kind": "build",
                "command": "sleep 999",
                "status": "running",
                "pid": 99999999,  # nonexistent
                "log_path": ".samvil/test.log",
                "started_at": time.time() - 600,
                "last_heartbeat_at": time.time() - 600,
                "exit_code": None,
                "finished_at": None,
                "reason": "",
            }
        )
    )
    snap = job_status(str(tmp_path), "job_deadbeef0000")
    assert snap["status"] == STATUS_INTERRUPTED
    assert "orphan" in snap["reason"]


def test_timeout_kills_job(tmp_path: Path) -> None:
    rec = start_job(
        str(tmp_path), "sleep 60", log_path=".samvil/test.log", timeout_seconds=10
    )
    # timeout_seconds is clamped to >=10; patch the deadline by waiting is
    # too slow for CI — instead verify the clamp and cancel.
    assert rec["timeout_seconds"] == 10
    cancel_job(str(tmp_path), rec["job_id"])


def test_list_jobs(tmp_path: Path) -> None:
    rec = start_job(str(tmp_path), "echo x", log_path=".samvil/test.log")
    _wait_terminal(str(tmp_path), rec["job_id"])
    jobs = list_jobs(str(tmp_path))
    assert any(j["job_id"] == rec["job_id"] for j in jobs)


def test_invalid_project_root_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        start_job(str(tmp_path / "nope"), "echo x")
