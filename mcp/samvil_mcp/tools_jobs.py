"""Background-job MCP tool registrations (W5.3 first slice).

This file establishes the server.py decomposition pattern: a domain
module exposes ``register_*_tools(mcp, log_mcp_health)`` and server.py
calls it once after the FastMCP instance exists. Tool behavior is
byte-identical to the previous inline definitions — only the file moved.

Why this pattern: server.py at ~5,700 lines is a single point of failure
(one syntax error kills all tools — CLAUDE.md's most common regression).
Each extracted module shrinks that blast radius. Follow-up migrations
are mechanical: move tool defs into ``tools_<domain>.py``, add a
``register`` call, keep the audit scripts' multi-file scan green.
"""

from __future__ import annotations

import json
from typing import Any, Callable


def register_job_tools(mcp: Any, log_mcp_health: Callable[..., None]) -> None:
    """Register job_start / job_status / job_result / job_cancel."""

    @mcp.tool()
    async def job_start(
        project_root: str,
        command: str,
        log_path: str = "",
        timeout_seconds: int = 1800,
        kind: str = "build",
    ) -> str:
        """Start a long shell command as a background job (W4.1).

        Returns immediately with {job_id, status:"running", pid, log_path}.
        Job state lives in .samvil/jobs/<job_id>.json (INV-1) and survives
        MCP restarts. Poll with job_status; fetch outcome with job_result;
        stop with job_cancel. Output appends to log_path (INV-2); empty
        log_path defaults to a per-job file (shared logs interleave).
        """
        try:
            from .background_jobs import start_job as _start_job

            record = _start_job(
                project_root,
                command,
                log_path=log_path,
                timeout_seconds=timeout_seconds,
                kind=kind,
            )
            log_mcp_health("ok", "job_start")
            return json.dumps(record)
        except Exception as e:
            log_mcp_health("fail", "job_start", str(e))
            return json.dumps({"job_id": None, "status": "error", "error": str(e)})

    @mcp.tool()
    async def job_status(project_root: str, job_id: str) -> str:
        """Snapshot of a background job: status, elapsed_seconds, log_tail.

        Detects orphaned jobs (MCP died mid-run) and marks them interrupted.
        """
        try:
            from .background_jobs import job_status as _job_status

            result = _job_status(project_root, job_id)
            log_mcp_health("ok", "job_status")
            return json.dumps(result)
        except Exception as e:
            log_mcp_health("fail", "job_status", str(e))
            return json.dumps({"job_id": job_id, "status": "error", "error": str(e)})

    @mcp.tool()
    async def job_result(project_root: str, job_id: str) -> str:
        """Final result of a background job (done=false while still running).

        Includes exit_code and the full log tail for failure diagnosis.
        """
        try:
            from .background_jobs import job_result as _job_result

            result = _job_result(project_root, job_id)
            log_mcp_health("ok", "job_result")
            return json.dumps(result)
        except Exception as e:
            log_mcp_health("fail", "job_result", str(e))
            return json.dumps({"job_id": job_id, "status": "error", "error": str(e)})

    @mcp.tool()
    async def job_cancel(project_root: str, job_id: str) -> str:
        """Cancel a running background job (SIGTERM to its process group)."""
        try:
            from .background_jobs import cancel_job as _cancel_job

            result = _cancel_job(project_root, job_id)
            log_mcp_health("ok", "job_cancel")
            return json.dumps(result)
        except Exception as e:
            log_mcp_health("fail", "job_cancel", str(e))
            return json.dumps({"job_id": job_id, "status": "error", "error": str(e)})
