"""Consolidates release_publish + remote_release (T2.3).

Both gate release-time decisions but cover different surfaces — local publish
vs remote CI evidence. Single module reduces overhead. No MCP exposure
(these are internal helpers; release.py orchestrates).

The publish guard ultimately consumes the remote-release gate as one of its
inputs (`state["remote_release_gate"]`), so co-locating the two reduces the
mental hop between author site and consumer site.
"""

from __future__ import annotations

from typing import Any

PUBLISH_SCHEMA_VERSION = "1.0"
REMOTE_RELEASE_SCHEMA_VERSION = "1.0"


# ── Publish Guard ──────────────────────────────────────────────────────────


def release_tag(version: str) -> str:
    version = str(version or "").strip()
    return version if version.startswith("v") else f"v{version}"


def evaluate_publish_guard(state: dict[str, Any]) -> dict[str, Any]:
    """Return pass/blocked for the final tag publishing guard."""
    reasons: list[str] = []
    next_action = "publish release tag"

    if state.get("branch") != state.get("target_branch"):
        reasons.append(f"current branch {state.get('branch') or '?'} is not {state.get('target_branch') or '?'}")
        next_action = "checkout target release branch"
    if not state.get("clean"):
        reasons.append("working tree is not clean")
        next_action = "commit or discard local changes"
    if not state.get("version_synced"):
        reasons.append("version files are not synchronized")
        next_action = "synchronize release version files"
    if state.get("local_tag_exists"):
        reasons.append(f"local tag already exists: {state.get('tag')}")
        next_action = "choose a new version or delete the local tag"
    if state.get("remote_tag_exists"):
        reasons.append(f"remote tag already exists: {state.get('tag')}")
        next_action = "choose a new version"
    if not state.get("remote_branch_pushed"):
        reasons.append("remote branch does not point at release HEAD")
        next_action = "push release branch"

    local_gate = state.get("local_release_gate") or {}
    if local_gate and local_gate.get("verdict") != "pass":
        reasons.append(f"local release gate is not pass: {local_gate.get('verdict') or '?'}")
        next_action = local_gate.get("next_action") or "fix local release gate"

    remote_gate = state.get("remote_release_gate") or {}
    if not remote_gate:
        reasons.append("remote release gate is missing")
        next_action = "run remote release gate"
    elif remote_gate.get("verdict") != "pass":
        reasons.append(f"remote release gate is not pass: {remote_gate.get('verdict') or '?'}")
        next_action = remote_gate.get("next_action") or "fix remote release gate"

    verdict = "blocked" if reasons else "pass"
    return {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "gate": "verified_release_publish",
        "verdict": verdict,
        "reason": "; ".join(reasons) if reasons else "local and remote release evidence passed",
        "next_action": next_action,
        "version": state.get("version") or "",
        "tag": state.get("tag") or release_tag(str(state.get("version") or "")),
        "branch": state.get("branch") or "",
        "target_branch": state.get("target_branch") or "",
        "head": state.get("head") or "",
        "remote_run_id": ((remote_gate.get("run") or {}).get("id") if remote_gate else "") or "",
    }


def render_publish_guard(gate: dict[str, Any]) -> str:
    lines = [
        "# Verified Release Publisher",
        "",
        f"- Verdict: {gate.get('verdict') or '?'}",
        f"- Reason: {gate.get('reason') or '?'}",
        f"- Next action: {gate.get('next_action') or '?'}",
        f"- Version: {gate.get('version') or '?'}",
        f"- Tag: {gate.get('tag') or '?'}",
        f"- Branch: {gate.get('branch') or '?'}",
        f"- Head: {gate.get('head') or '?'}",
    ]
    if gate.get("remote_run_id"):
        lines.append(f"- Remote run: {gate.get('remote_run_id')}")
    return "\n".join(lines) + "\n"


# ── Remote Release Gate ────────────────────────────────────────────────────


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
