"""Remote CI release gate evaluation for SAMVIL."""

from __future__ import annotations

from typing import Any

REMOTE_RELEASE_SCHEMA_VERSION = "1.0"


def evaluate_remote_release_gate(
    *,
    run: dict[str, Any] | None,
    runner: dict[str, Any] | None,
    expected_head: str = "",
) -> dict[str, Any]:
    """Return a deterministic verdict for remote CI release evidence."""
    run = run or {}
    runner = runner or {}
    runner_report = runner.get("report") or {}
    runner_gate = runner.get("gate") or {}
    summary = runner_report.get("summary") or {}
    checks = runner_report.get("checks") or []

    verdict = "pass"
    reasons: list[str] = []
    next_action = "ready to tag release"

    if not run:
        verdict = "blocked"
        reasons.append("remote CI run metadata is missing")
        next_action = "find remote release check run"
    elif run.get("status") != "completed":
        verdict = "blocked"
        reasons.append(f"remote CI run is not completed: {run.get('status') or '?'}")
        next_action = "wait for remote release check run"
    elif run.get("conclusion") != "success":
        verdict = "blocked"
        reasons.append(f"remote CI run conclusion is not success: {run.get('conclusion') or '?'}")
        next_action = "fix remote release check run"

    head_sha = str(run.get("headSha") or run.get("head_sha") or "")
    if expected_head and head_sha and not head_sha.startswith(expected_head):
        verdict = "blocked"
        reasons.append(f"remote CI head {head_sha} does not match expected {expected_head}")
        next_action = "run release checks for current HEAD"

    if not runner:
        verdict = "blocked"
        reasons.append("remote release-runner artifact is missing")
        next_action = "download remote release evidence artifact"
    elif summary.get("status") != "pass":
        verdict = "blocked"
        reasons.append(f"remote release report is not pass: {summary.get('status') or '?'}")
        next_action = runner_report.get("next_action") or "fix remote release report"
    elif runner_gate.get("verdict") != "pass":
        verdict = "blocked"
        reasons.append(f"remote release gate is not pass: {runner_gate.get('verdict') or '?'}")
        next_action = runner_gate.get("next_action") or "fix remote release gate"

    failed_checks = int(summary.get("failed_checks") or 0)
    missing_checks = int(summary.get("missing_checks") or 0)
    if failed_checks or missing_checks:
        verdict = "blocked"
        reasons.append(f"remote checks failed/missing: {failed_checks} failed, {missing_checks} missing")
        next_action = runner_report.get("next_action") or "fix remote release checks"

    return {
        "schema_version": REMOTE_RELEASE_SCHEMA_VERSION,
        "gate": "remote_release",
        "verdict": verdict,
        "reason": "; ".join(reasons) if reasons else "remote CI release evidence passed",
        "next_action": next_action,
        "run": {
            "id": run.get("databaseId") or run.get("id") or "",
            "workflow": run.get("workflowName") or run.get("workflow") or "",
            "status": run.get("status") or "",
            "conclusion": run.get("conclusion") or "",
            "head_sha": head_sha,
            "url": run.get("url") or "",
        },
        "release_report_status": summary.get("status"),
        "passed_checks": int(summary.get("passed_checks") or 0),
        "failed_checks": failed_checks,
        "missing_checks": missing_checks,
        "runner_gate_verdict": runner_gate.get("verdict"),
        "checks": [_check_summary(check) for check in checks],
    }


def render_remote_release_gate(gate: dict[str, Any]) -> str:
    """Render remote release gate evidence as concise markdown."""
    run = gate.get("run") or {}
    lines = [
        "# Remote Release Gate",
        "",
        f"- Verdict: {gate.get('verdict') or '?'}",
        f"- Reason: {gate.get('reason') or '?'}",
        f"- Next action: {gate.get('next_action') or '?'}",
        f"- Workflow: {run.get('workflow') or '?'}",
        f"- Run: {run.get('id') or '?'}",
        f"- Status: {run.get('status') or '?'} / {run.get('conclusion') or '?'}",
        f"- Head: {run.get('head_sha') or '?'}",
        f"- Report: {gate.get('release_report_status') or '?'}",
        f"- Checks: {gate.get('passed_checks', 0)} passed / "
        f"{gate.get('failed_checks', 0)} failed / "
        f"{gate.get('missing_checks', 0)} missing",
    ]
    if run.get("url"):
        lines.append(f"- URL: {run.get('url')}")
    checks = gate.get("checks") or []
    if checks:
        lines.extend(["", "## Checks"])
        for check in checks:
            lines.append(f"- [{str(check.get('status') or '?').upper()}] {check.get('name')}")
    return "\n".join(lines) + "\n"


def _check_summary(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": check.get("name") or "",
        "status": check.get("status") or "",
        "exit_code": check.get("exit_code"),
        "message": check.get("message") or "",
    }
