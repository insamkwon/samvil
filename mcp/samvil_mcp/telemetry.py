"""Run telemetry snapshot for SAMVIL v3.5."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_REPORT_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def run_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "run-report.json"


def build_run_report(
    project_root: Path | str,
    *,
    mcp_health_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build a deterministic report from project-local telemetry files."""
    root = Path(project_root)
    samvil = root / ".samvil"
    state = _load_json(root / "project.state.json") or _load_json(samvil / "state.json")
    claims = _load_jsonl(samvil / "claims.jsonl")
    events = _load_jsonl(samvil / "events.jsonl")
    health_path = Path(mcp_health_path) if mcp_health_path else samvil / "mcp-health.jsonl"
    health = _load_jsonl(health_path)
    marker = _load_json(samvil / "next-skill.json")

    latest_claims = _latest_claims(claims)
    gate_verdicts = _latest_gate_verdicts(latest_claims)
    claim_counts = _count_by(latest_claims, "status", defaults=("pending", "verified", "rejected"))
    health_summary = _health_summary(health)
    event_summary = _event_summary(events)

    next_action = _next_action(marker, gate_verdicts, health_summary)

    return {
        "schema_version": RUN_REPORT_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "state": {
            "session_id": state.get("session_id"),
            "project_name": state.get("project_name") or root.name,
            "current_stage": state.get("current_stage") or state.get("stage"),
            "samvil_tier": state.get("samvil_tier") or state.get("selected_tier"),
            "seed_version": state.get("seed_version"),
        },
        "events": event_summary,
        "claims": {
            "total": len(latest_claims),
            "by_status": claim_counts,
            "by_type": _count_by(latest_claims, "type"),
            "pending_subjects": [
                c.get("subject", "?")
                for c in sorted(latest_claims, key=lambda c: c.get("ts", ""))
                if c.get("status") == "pending"
            ][:20],
            "latest_gate_verdicts": gate_verdicts,
        },
        "mcp_health": health_summary,
        "continuation": {
            "present": bool(marker),
            "next_skill": marker.get("next_skill"),
            "from_stage": marker.get("from_stage"),
            "reason": marker.get("reason"),
            "chain_via": marker.get("chain_via"),
        },
        "next_action": next_action,
    }


def write_run_report(report: dict[str, Any], project_root: Path | str) -> Path:
    target = run_report_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_run_report(project_root: Path | str) -> dict[str, Any] | None:
    path = run_report_path(project_root)
    if not path.exists():
        return None
    report = _load_json(path)
    return report or None


def render_run_report(report: dict[str, Any]) -> str:
    state = report.get("state", {}) or {}
    events = report.get("events", {}) or {}
    claims = report.get("claims", {}) or {}
    health = report.get("mcp_health", {}) or {}
    continuation = report.get("continuation", {}) or {}

    lines = [
        f"# Run Report — {state.get('project_name') or 'unknown'}",
        f"_generated: {report.get('generated_at', '')}_",
        "",
        f"- Stage: {state.get('current_stage') or '?'}",
        f"- Tier: {state.get('samvil_tier') or '?'}",
        f"- Session: {state.get('session_id') or '?'}",
        f"- Events: {events.get('total', 0)} total",
        f"- Claims: {claims.get('total', 0)} total",
        f"- MCP health: {health.get('failures', 0)} failures / {health.get('total', 0)} events",
    ]
    if continuation.get("present"):
        lines.append(
            f"- Continuation: {continuation.get('from_stage')} -> {continuation.get('next_skill')}"
        )
    lines.append(f"- Next action: {report.get('next_action')}")

    gate_verdicts = claims.get("latest_gate_verdicts") or []
    if gate_verdicts:
        lines.extend(["", "## Latest Gates"])
        for gate in gate_verdicts[:10]:
            lines.append(
                f"- {gate.get('subject')}: {gate.get('verdict')} ({gate.get('event_type') or gate.get('reason') or ''})"
            )

    failures_by_tool = health.get("failures_by_tool") or {}
    if failures_by_tool:
        lines.extend(["", "## MCP Failures"])
        for tool, count in sorted(failures_by_tool.items()):
            lines.append(f"- {tool}: {count}")

    pending = claims.get("pending_subjects") or []
    if pending:
        lines.extend(["", "## Pending Claims"])
        for subject in pending[:10]:
            lines.append(f"- {subject}")

    return "\n".join(lines) + "\n"


def _latest_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for claim in claims:
        cid = claim.get("claim_id")
        if cid:
            latest[cid] = claim
    return list(latest.values())


def _latest_gate_verdicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if claim.get("type") != "gate_verdict":
            continue
        subject = claim.get("subject", "")
        if subject not in latest or latest[subject].get("ts", "") < claim.get("ts", ""):
            latest[subject] = claim
    out: list[dict[str, Any]] = []
    for claim in sorted(latest.values(), key=lambda c: c.get("ts", ""), reverse=True):
        meta = claim.get("meta", {}) or {}
        out.append({
            "subject": claim.get("subject"),
            "verdict": meta.get("verdict") or _verdict_from_statement(claim.get("statement", "")),
            "reason": meta.get("reason", ""),
            "event_type": meta.get("event_type"),
            "ts": claim.get("ts"),
        })
    return out


def _verdict_from_statement(statement: str) -> str:
    if "verdict=" in statement:
        return statement.split("verdict=", 1)[1].split()[0]
    return "unknown"


def _count_by(rows: list[dict[str, Any]], key: str, defaults: tuple[str, ...] = ()) -> dict[str, int]:
    counts = Counter(str(row.get(key, "unknown")) for row in rows)
    for default in defaults:
        counts.setdefault(default, 0)
    return dict(sorted(counts.items()))


def _event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = _count_by(events, "event_type")
    by_stage = _count_by(events, "stage")
    failure_events = [
        e for e in events
        if "fail" in str(e.get("event_type", "")).lower()
        or "error" in str(e.get("event_type", "")).lower()
    ]
    latest = max((e.get("timestamp", "") for e in events), default="")
    return {
        "total": len(events),
        "by_type": by_type,
        "by_stage": by_stage,
        "failure_count": len(failure_events),
        "latest_event_at": latest,
    }


def _health_summary(health: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [h for h in health if h.get("status") == "fail"]
    failures_by_tool: dict[str, int] = defaultdict(int)
    for row in failures:
        failures_by_tool[str(row.get("tool", "unknown"))] += 1
    latest_failure = max(failures, key=lambda r: r.get("timestamp", ""), default={})
    return {
        "total": len(health),
        "failures": len(failures),
        "oks_sampled": sum(1 for h in health if h.get("status") == "ok"),
        "failures_by_tool": dict(sorted(failures_by_tool.items())),
        "latest_failure": latest_failure,
    }


def _next_action(
    marker: dict[str, Any],
    gate_verdicts: list[dict[str, Any]],
    health: dict[str, Any],
) -> str:
    blocking = [
        gate for gate in gate_verdicts
        if gate.get("verdict") not in (None, "pass", "skip", "unknown")
    ]
    if blocking:
        gate = blocking[0]
        return f"resolve gate {gate.get('subject')} ({gate.get('verdict')})"
    if marker.get("next_skill"):
        return f"continue with {marker['next_skill']}"
    if health.get("failures"):
        latest = health.get("latest_failure") or {}
        return f"inspect MCP failure in {latest.get('tool', 'unknown')}"
    return "no immediate action"
