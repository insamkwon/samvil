"""Run telemetry snapshot for SAMVIL v3.5."""

from __future__ import annotations

import json
import os
from hashlib import sha1
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repair import repair_summary as _repair_summary
from .release import release_summary as _release_summary
from .qa_synthesis import qa_summary as _qa_summary
from .qa_routing import qa_routing_summary as _qa_routing_summary
from .evolve_loop import evolve_context_summary as _evolve_context_summary
from .evolve_execution import (
    evolve_apply_summary as _evolve_apply_summary,
    evolve_proposal_summary as _evolve_proposal_summary,
)
from .evolve_rebuild import evolve_rebuild_summary as _evolve_rebuild_summary
from .evolve_reentry import rebuild_reentry_summary as _rebuild_reentry_summary
from .post_rebuild_qa import post_rebuild_qa_summary as _post_rebuild_qa_summary
from .evolve_cycle import evolve_cycle_summary as _evolve_cycle_summary
from .final_e2e import final_e2e_summary as _final_e2e_summary

RUN_REPORT_SCHEMA_VERSION = "1.0"
RETRO_OBSERVATION_SCHEMA_VERSION = "1.0"


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


def retro_observation_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "retro-observations.jsonl"


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
    timeline_summary = _timeline_summary(events)
    repair_summary = _repair_summary(root)
    release_summary = _release_summary(root)
    qa_summary = _qa_summary(root)
    qa_routing_summary = _qa_routing_summary(root)
    evolve_context_summary = _evolve_context_summary(root)
    evolve_proposal_summary = _evolve_proposal_summary(root)
    evolve_apply_summary = _evolve_apply_summary(root)
    evolve_rebuild_summary = _evolve_rebuild_summary(root)
    rebuild_reentry_summary = _rebuild_reentry_summary(root)
    post_rebuild_qa_summary = _post_rebuild_qa_summary(root)
    evolve_cycle_summary = _evolve_cycle_summary(root)
    final_e2e_summary = _final_e2e_summary(root)

    next_action = _next_action(
        marker,
        gate_verdicts,
        health_summary,
        repair_summary,
        release_summary,
        qa_summary,
        qa_routing_summary,
    )

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
        "timeline": timeline_summary,
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
        "repair": repair_summary,
        "release": release_summary,
        "qa": qa_summary,
        "qa_routing": qa_routing_summary,
        "evolve_context": evolve_context_summary,
        "evolve_proposal": evolve_proposal_summary,
        "evolve_apply": evolve_apply_summary,
        "evolve_rebuild": evolve_rebuild_summary,
        "rebuild_reentry": rebuild_reentry_summary,
        "post_rebuild_qa": post_rebuild_qa_summary,
        "evolve_cycle": evolve_cycle_summary,
        "final_e2e": final_e2e_summary,
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


def derive_retro_observations(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert deterministic run report findings into retro candidates."""
    observations: list[dict[str, Any]] = []
    timeline = report.get("timeline", {}) or {}
    claims = report.get("claims", {}) or {}
    health = report.get("mcp_health", {}) or {}

    for stage in timeline.get("stages") or []:
        stage_name = str(stage.get("stage") or "unknown")
        status = str(stage.get("status") or "observed")
        if status in {"failed", "blocked"}:
            observations.append(_retro_observation(
                source="telemetry.timeline",
                severity="high" if status == "failed" else "medium",
                title=f"Stage {stage_name} is {status}",
                evidence=[
                    f"status={status}",
                    f"events={stage.get('event_count', 0)}",
                    f"duration_seconds={stage.get('duration_seconds')}",
                ],
                suggested_action=(
                    f"Review the {stage_name} stage events and add a prevention item "
                    "for the blocking or failing condition."
                ),
                dedupe_key=f"stage:{stage_name}:{status}",
            ))

        retry_count = int((stage.get("categories") or {}).get("retry", 0) or 0)
        if retry_count > 0:
            observations.append(_retro_observation(
                source="telemetry.timeline",
                severity="medium",
                title=f"Stage {stage_name} required {retry_count} retry event(s)",
                evidence=[
                    f"stage={stage_name}",
                    f"retry_count={retry_count}",
                    f"status={status}",
                ],
                suggested_action=(
                    f"Capture why {stage_name} needed retries and decide whether a "
                    "checklist, fixture, or gate should catch it earlier."
                ),
                dedupe_key=f"retry:{stage_name}",
            ))

    for signature in health.get("failure_signatures") or []:
        tool = str(signature.get("tool") or "unknown")
        error_signature = str(signature.get("signature") or "unknown")
        count = int(signature.get("count") or 0)
        observations.append(_retro_observation(
            source="telemetry.mcp_health",
            severity="high" if count >= 3 else "medium",
            title=f"MCP tool {tool} failed {count} time(s)",
            evidence=[
                f"tool={tool}",
                f"signature={error_signature}",
                f"latest_at={signature.get('latest_at') or ''}",
            ],
            suggested_action=(
                f"Inspect {tool} failure handling and add a regression fixture for "
                "this signature if it is reproducible."
            ),
            dedupe_key=f"mcp:{tool}:{error_signature}",
        ))

    pending_subjects = claims.get("pending_subjects") or []
    if pending_subjects:
        preview = ", ".join(str(s) for s in pending_subjects[:5])
        observations.append(_retro_observation(
            source="telemetry.claims",
            severity="low",
            title=f"{len(pending_subjects)} claim(s) remained pending",
            evidence=[f"pending_subjects={preview}"],
            suggested_action=(
                "Close or verify pending claims before release so the run can be "
                "reconstructed from committed evidence."
            ),
            dedupe_key="claims:pending",
        ))

    return _dedupe_observations(observations)


def append_retro_observations(
    project_root: Path | str,
    observations: list[dict[str, Any]],
) -> Path:
    target = retro_observation_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_keys = {
        str(row.get("dedupe_key"))
        for row in _load_jsonl(target)
        if row.get("dedupe_key")
    }
    now = _now_iso()
    with target.open("a", encoding="utf-8") as f:
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            dedupe_key = str(observation.get("dedupe_key") or "")
            if dedupe_key and dedupe_key in existing_keys:
                continue
            row = {
                "schema_version": RETRO_OBSERVATION_SCHEMA_VERSION,
                "recorded_at": now,
                **observation,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if dedupe_key:
                existing_keys.add(dedupe_key)
    return target


def render_run_report(report: dict[str, Any]) -> str:
    state = report.get("state", {}) or {}
    events = report.get("events", {}) or {}
    claims = report.get("claims", {}) or {}
    health = report.get("mcp_health", {}) or {}
    timeline = report.get("timeline", {}) or {}
    continuation = report.get("continuation", {}) or {}
    repair = report.get("repair", {}) or {}
    repair_gate = repair.get("gate", {}) or {}
    release = report.get("release", {}) or {}
    release_gate = release.get("gate", {}) or {}

    lines = [
        f"# Run Report — {state.get('project_name') or 'unknown'}",
        f"_generated: {report.get('generated_at', '')}_",
        "",
        f"- Stage: {state.get('current_stage') or '?'}",
        f"- Tier: {state.get('samvil_tier') or '?'}",
        f"- Session: {state.get('session_id') or '?'}",
        f"- Events: {events.get('total', 0)} total",
        f"- Failures/retries: {timeline.get('failure_count', 0)} failures, {timeline.get('retry_count', 0)} retries",
        f"- Claims: {claims.get('total', 0)} total",
        f"- MCP health: {health.get('failures', 0)} failures / {health.get('total', 0)} events",
    ]
    if repair_gate:
        lines.append(
            f"- Repair gate: {repair_gate.get('verdict')} ({repair_gate.get('reason')})"
        )
    if release_gate:
        lines.append(
            f"- Release gate: {release_gate.get('verdict')} ({release_gate.get('reason')})"
        )
    if continuation.get("present"):
        lines.append(
            f"- Continuation: {continuation.get('from_stage')} -> {continuation.get('next_skill')}"
        )
    lines.append(f"- Next action: {report.get('next_action')}")

    stages = timeline.get("stages") or []
    if stages:
        lines.extend(["", "## Stage Timeline"])
        for stage in stages:
            duration = stage.get("duration_seconds")
            duration_text = f"{duration:.1f}s" if isinstance(duration, (int, float)) else "?"
            lines.append(
                f"- {stage.get('stage')}: {stage.get('status')} "
                f"({duration_text}, events={stage.get('event_count', 0)})"
            )

    if repair:
        lines.extend(["", "## Repair"])
        lines.append(f"- Inspection: {repair.get('inspection_status')} ({repair.get('inspection_failed_checks', 0)} failed checks)")
        lines.append(f"- Plan: {repair.get('plan_status')} ({repair.get('plan_actions', 0)} actions)")
        lines.append(
            f"- Report: {repair.get('report_status')} "
            f"({repair.get('resolved_failures', 0)} resolved / {repair.get('remaining_failures', 0)} remaining)"
        )
        if repair_gate:
            lines.append(f"- Gate next action: {repair_gate.get('next_action')}")

    if release:
        lines.extend(["", "## Release"])
        lines.append(
            f"- Report: {release.get('report_status')} "
            f"({release.get('passed_checks', 0)} passed / "
            f"{release.get('failed_checks', 0)} failed / "
            f"{release.get('missing_checks', 0)} missing)"
        )
        if release_gate:
            lines.append(f"- Gate next action: {release_gate.get('next_action')}")

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


def _timeline_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_counts: Counter[str] = Counter()
    retry_count = 0
    failure_count = 0
    for event in events:
        category = _event_category(str(event.get("event_type", "")))
        event["category"] = category
        category_counts[category] += 1
        if category == "retry":
            retry_count += 1
        if category == "fail":
            failure_count += 1
        by_stage[str(event.get("stage") or "unknown")].append(event)

    stages: list[dict[str, Any]] = []
    for stage, rows in sorted(by_stage.items()):
        ordered = sorted(rows, key=lambda r: r.get("timestamp", ""))
        categories = [str(r.get("category")) for r in ordered]
        start_ts = _first_ts(ordered, {"start"}) or _first_ts(ordered)
        end_ts = _last_ts(ordered, {"complete", "fail", "blocked", "skip"}) or _last_ts(ordered)
        status = _stage_status_from_categories(categories)
        duration = _duration_seconds(start_ts, end_ts)
        stages.append({
            "stage": stage,
            "status": status,
            "event_count": len(ordered),
            "start_at": start_ts,
            "end_at": end_ts,
            "duration_seconds": duration,
            "categories": dict(Counter(categories)),
        })

    return {
        "category_counts": dict(sorted(category_counts.items())),
        "failure_count": failure_count,
        "retry_count": retry_count,
        "stages": stages,
    }


def _event_category(event_type: str) -> str:
    et = event_type.lower()
    tokens = _event_tokens(et)
    token_set = set(tokens)
    if "repair" in token_set and {"applied", "verified"} & token_set:
        return "complete"
    if {"retry", "retried", "retries", "reawake"} & token_set or et == "fix_applied":
        return "retry"
    if {"blocked", "stall", "stalled"} & token_set:
        return "blocked"
    if "skip" in et:
        return "skip"
    if "fail" in et or "error" in et or "revise" in et or "unimplemented" in et:
        return "fail"
    if (
        "complete" in et
        or et.endswith("_pass")
        or et in {"seed_generated", "council_verdict", "blueprint_generated"}
    ):
        return "complete"
    if "start" in et or "started" in et:
        return "start"
    return "other"


def _event_tokens(event_type: str) -> list[str]:
    normalized = "".join(ch if ch.isalnum() else " " for ch in event_type.lower())
    return [token for token in normalized.split() if token]


def _stage_status_from_categories(categories: list[str]) -> str:
    if "fail" in categories:
        return "failed"
    if "blocked" in categories:
        return "blocked"
    if "complete" in categories:
        return "complete"
    if "start" in categories:
        return "in_progress"
    if "skip" in categories:
        return "skipped"
    return "observed"


def _first_ts(rows: list[dict[str, Any]], categories: set[str] | None = None) -> str:
    for row in rows:
        if categories is None or row.get("category") in categories:
            return str(row.get("timestamp") or "")
    return ""


def _last_ts(rows: list[dict[str, Any]], categories: set[str] | None = None) -> str:
    for row in reversed(rows):
        if categories is None or row.get("category") in categories:
            return str(row.get("timestamp") or "")
    return ""


def _duration_seconds(start_ts: str, end_ts: str) -> float | None:
    if not start_ts or not end_ts:
        return None
    try:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


def _health_summary(health: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [h for h in health if h.get("status") == "fail"]
    failures_by_tool: dict[str, int] = defaultdict(int)
    failure_signatures: dict[tuple[str, str], dict[str, Any]] = {}
    for row in failures:
        tool = str(row.get("tool", "unknown"))
        signature = _failure_signature(row)
        failures_by_tool[tool] += 1
        key = (tool, signature)
        if key not in failure_signatures:
            failure_signatures[key] = {
                "tool": tool,
                "signature": signature,
                "count": 0,
                "latest_at": "",
            }
        failure_signatures[key]["count"] += 1
        ts = str(row.get("timestamp") or "")
        if ts > str(failure_signatures[key].get("latest_at") or ""):
            failure_signatures[key]["latest_at"] = ts
    latest_failure = max(failures, key=lambda r: r.get("timestamp", ""), default={})
    return {
        "total": len(health),
        "failures": len(failures),
        "oks_sampled": sum(1 for h in health if h.get("status") == "ok"),
        "failures_by_tool": dict(sorted(failures_by_tool.items())),
        "failure_signatures": sorted(
            failure_signatures.values(),
            key=lambda item: (str(item.get("tool")), str(item.get("signature"))),
        ),
        "latest_failure": latest_failure,
    }


def _retro_observation(
    *,
    source: str,
    severity: str,
    title: str,
    evidence: list[str],
    suggested_action: str,
    dedupe_key: str,
) -> dict[str, Any]:
    return {
        "id": "retro_" + sha1(dedupe_key.encode("utf-8")).hexdigest()[:12],
        "source": source,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "dedupe_key": dedupe_key,
    }


def _dedupe_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for observation in observations:
        key = str(observation.get("dedupe_key") or observation.get("id"))
        if key and key not in by_key:
            by_key[key] = observation
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        by_key.values(),
        key=lambda obs: (
            severity_rank.get(str(obs.get("severity")), 9),
            str(obs.get("source")),
            str(obs.get("dedupe_key")),
        ),
    )


def _failure_signature(row: dict[str, Any]) -> str:
    raw = str(row.get("error") or row.get("message") or row.get("reason") or "unknown")
    return " ".join(raw.strip().split())[:160] or "unknown"


def _next_action(
    marker: dict[str, Any],
    gate_verdicts: list[dict[str, Any]],
    health: dict[str, Any],
    repair: dict[str, Any] | None = None,
    release: dict[str, Any] | None = None,
    qa: dict[str, Any] | None = None,
    qa_routing: dict[str, Any] | None = None,
) -> str:
    repair_gate = (repair or {}).get("gate", {}) or {}
    if repair_gate.get("verdict") == "blocked":
        return str(repair_gate.get("next_action") or "repair gate blocked")
    release_gate = (release or {}).get("gate", {}) or {}
    if release_gate.get("verdict") == "blocked":
        return str(release_gate.get("next_action") or "release gate blocked")
    if release_gate.get("verdict") == "pass":
        return str(release_gate.get("next_action") or "release ready")
    qa = qa or {}
    qa_convergence = qa.get("convergence") or {}
    if qa.get("present") and qa_convergence.get("verdict") in {"blocked", "failed"}:
        qa_routing = qa_routing or {}
        if qa_routing.get("present") and qa_routing.get("next_action"):
            return str(qa_routing.get("next_action"))
        return str(qa_convergence.get("next_action") or "resolve QA convergence gate")
    if qa.get("present") and qa.get("verdict") in {"REVISE", "FAIL"}:
        return str(qa.get("next_action") or "fix QA findings")
    blocking = [
        gate for gate in gate_verdicts
        if gate.get("verdict") not in (None, "pass", "skip", "unknown")
    ]
    if blocking:
        gate = blocking[0]
        return f"resolve gate {gate.get('subject')} ({gate.get('verdict')})"
    if repair_gate.get("verdict") == "pass":
        return str(repair_gate.get("next_action") or "continue after verified repair")
    if marker.get("next_skill"):
        return f"continue with {marker['next_skill']}"
    if health.get("failures"):
        latest = health.get("latest_failure") or {}
        return f"inspect MCP failure in {latest.get('tool', 'unknown')}"
    return "no immediate action"
