"""Verified release publishing guard for SAMVIL."""

from __future__ import annotations

from typing import Any

PUBLISH_SCHEMA_VERSION = "1.0"


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
