"""Build repair plans and before/after repair reports from inspection results."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

from .inspection import read_inspection_report

REPAIR_PLAN_SCHEMA_VERSION = "1.0"
REPAIR_REPORT_SCHEMA_VERSION = "1.0"


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


def repair_plan_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "repair-plan.json"


def repair_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "repair-report.json"


def after_inspection_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "inspection-report.after.json"


def build_repair_plan(
    project_root: Path | str,
    *,
    inspection_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an ordered repair plan from a failed inspection report."""
    root = Path(project_root)
    report = inspection_report if inspection_report is not None else read_inspection_report(root)
    report = report or {}
    failures = report.get("failures") or []
    actions = [_repair_action(index, failure) for index, failure in enumerate(failures, start=1)]
    status = "ready" if actions else "empty"
    return {
        "schema_version": REPAIR_PLAN_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "scenario": report.get("scenario") or root.name,
        "source_inspection_status": (report.get("summary", {}) or {}).get("status"),
        "summary": {
            "status": status,
            "total_actions": len(actions),
            "high_priority": sum(1 for action in actions if action["priority"] == "high"),
            "medium_priority": sum(1 for action in actions if action["priority"] == "medium"),
            "low_priority": sum(1 for action in actions if action["priority"] == "low"),
        },
        "actions": actions,
        "next_action": actions[0]["instruction"] if actions else "no repair needed",
    }


def write_repair_plan(plan: dict[str, Any], project_root: Path | str) -> Path:
    return _atomic_write_json(repair_plan_path(project_root), plan)


def read_repair_plan(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(repair_plan_path(project_root))
    return data or None


def render_repair_plan(plan: dict[str, Any]) -> str:
    summary = plan.get("summary", {}) or {}
    lines = [
        f"# Repair Plan — {plan.get('scenario') or 'unknown'}",
        f"_generated: {plan.get('generated_at', '')}_",
        "",
        f"- Status: {summary.get('status') or '?'}",
        f"- Actions: {summary.get('total_actions', 0)}",
        f"- High priority: {summary.get('high_priority', 0)}",
        f"- Next action: {plan.get('next_action') or '?'}",
    ]
    actions = plan.get("actions") or []
    if actions:
        lines.extend(["", "## Actions"])
        for action in actions:
            lines.append(
                f"- [{str(action.get('priority', '?')).upper()}] "
                f"{action.get('id')}: {action.get('instruction')}"
            )
            lines.append(f"  verify: {action.get('verification')}")
    return "\n".join(lines)


def build_repair_report(
    project_root: Path | str,
    *,
    plan: dict[str, Any] | None = None,
    before_report: dict[str, Any] | None = None,
    after_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a repair report comparing before and after inspection results."""
    root = Path(project_root)
    repair_plan = plan if plan is not None else read_repair_plan(root) or {}
    before = before_report if before_report is not None else read_inspection_report(root) or {}
    after = after_report if after_report is not None else _load_json(after_inspection_report_path(root))
    before_failures = _failure_map(before)
    after_failures = _failure_map(after)
    resolved = [
        _compact_failure(failure)
        for check_id, failure in before_failures.items()
        if check_id not in after_failures
    ]
    remaining = [_compact_failure(failure) for failure in after_failures.values()]
    after_status = (after.get("summary", {}) or {}).get("status")
    status = "verified" if before_failures and after_status == "pass" and not remaining else "pending"
    if remaining or after_status == "fail":
        status = "failed"
    if not after:
        status = "pending"

    return {
        "schema_version": REPAIR_REPORT_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "scenario": before.get("scenario") or repair_plan.get("scenario") or root.name,
        "summary": {
            "status": status,
            "planned_actions": len(repair_plan.get("actions") or []),
            "before_failed_checks": len(before_failures),
            "after_failed_checks": len(after_failures),
            "resolved_failures": len(resolved),
            "remaining_failures": len(remaining),
            "after_inspection_status": after_status,
        },
        "resolved": resolved,
        "remaining": remaining,
        "actions": _actions_with_status(repair_plan.get("actions") or [], after_failures),
        "next_action": _repair_report_next_action(status, remaining),
    }


def write_repair_report(report: dict[str, Any], project_root: Path | str) -> Path:
    return _atomic_write_json(repair_report_path(project_root), report)


def read_repair_report(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(repair_report_path(project_root))
    return data or None


def render_repair_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) or {}
    lines = [
        f"# Repair Report — {report.get('scenario') or 'unknown'}",
        f"_generated: {report.get('generated_at', '')}_",
        "",
        f"- Status: {summary.get('status') or '?'}",
        f"- Planned actions: {summary.get('planned_actions', 0)}",
        f"- Before failed checks: {summary.get('before_failed_checks', 0)}",
        f"- After failed checks: {summary.get('after_failed_checks', 0)}",
        f"- Resolved failures: {summary.get('resolved_failures', 0)}",
        f"- Next action: {report.get('next_action') or '?'}",
    ]
    resolved = report.get("resolved") or []
    if resolved:
        lines.extend(["", "## Resolved"])
        for failure in resolved:
            lines.append(f"- {failure.get('type')}: {failure.get('check_id')}")
    remaining = report.get("remaining") or []
    if remaining:
        lines.extend(["", "## Remaining"])
        for failure in remaining:
            lines.append(f"- {failure.get('type')}: {failure.get('check_id')}")
    return "\n".join(lines)


def evaluate_repair_gate(
    project_root: Path | str,
    *,
    inspection_report: dict[str, Any] | None = None,
    repair_plan: dict[str, Any] | None = None,
    repair_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic repair gate verdict for progression decisions."""
    root = Path(project_root)
    inspection = inspection_report if inspection_report is not None else read_inspection_report(root) or {}
    plan = repair_plan if repair_plan is not None else read_repair_plan(root) or {}
    report = repair_report if repair_report is not None else read_repair_report(root) or {}

    inspection_status = (inspection.get("summary", {}) or {}).get("status")
    report_status = (report.get("summary", {}) or {}).get("status")
    plan_status = (plan.get("summary", {}) or {}).get("status")
    failed_checks = int((inspection.get("summary", {}) or {}).get("failed_checks") or 0)
    plan_actions = int((plan.get("summary", {}) or {}).get("total_actions") or 0)
    remaining_failures = int((report.get("summary", {}) or {}).get("remaining_failures") or 0)

    if inspection_status in {None, "pass", "warn"} and not report:
        verdict = "not-applicable"
        reason = "inspection has no blocking failures"
        next_action = "continue"
    elif report_status == "verified":
        verdict = "pass"
        reason = "repair report verified after inspection"
        next_action = "continue to release checks"
    elif report_status == "failed" or remaining_failures > 0:
        verdict = "blocked"
        reason = "repair report still has remaining failures"
        next_action = report.get("next_action") or "continue repair"
    elif inspection_status == "fail" and not plan:
        verdict = "blocked"
        reason = "inspection failed but no repair plan exists"
        next_action = "build repair plan"
    elif inspection_status == "fail" and plan_status == "ready" and not report:
        verdict = "blocked"
        reason = "repair plan exists but repair is not verified"
        next_action = plan.get("next_action") or "execute repair plan"
    elif inspection_status == "fail":
        verdict = "blocked"
        reason = "inspection failure is not repaired"
        next_action = "build repair report after reinspection"
    else:
        verdict = "not-applicable"
        reason = "repair gate found no blocking state"
        next_action = "continue"

    return {
        "gate": "repair",
        "verdict": verdict,
        "reason": reason,
        "next_action": next_action,
        "inspection_status": inspection_status,
        "failed_checks": failed_checks,
        "repair_plan_status": plan_status,
        "repair_actions": plan_actions,
        "repair_report_status": report_status,
        "remaining_failures": remaining_failures,
    }


def repair_summary(project_root: Path | str) -> dict[str, Any]:
    """Read project repair artifacts into a compact run-report summary."""
    root = Path(project_root)
    inspection = read_inspection_report(root) or {}
    plan = read_repair_plan(root) or {}
    report = read_repair_report(root) or {}
    gate = evaluate_repair_gate(
        root,
        inspection_report=inspection,
        repair_plan=plan,
        repair_report=report,
    )
    return {
        "inspection_present": bool(inspection),
        "inspection_status": (inspection.get("summary", {}) or {}).get("status"),
        "inspection_failed_checks": (inspection.get("summary", {}) or {}).get("failed_checks", 0),
        "plan_present": bool(plan),
        "plan_status": (plan.get("summary", {}) or {}).get("status"),
        "plan_actions": (plan.get("summary", {}) or {}).get("total_actions", 0),
        "report_present": bool(report),
        "report_status": (report.get("summary", {}) or {}).get("status"),
        "resolved_failures": (report.get("summary", {}) or {}).get("resolved_failures", 0),
        "remaining_failures": (report.get("summary", {}) or {}).get("remaining_failures", 0),
        "gate": gate,
    }


def derive_repair_policy_signals(
    repair_reports: list[dict[str, Any]],
    *,
    threshold: int = 2,
) -> list[dict[str, Any]]:
    """Suggest policy candidates when the same repair type repeats."""
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for report in repair_reports:
        scenario = str(report.get("scenario") or "unknown")
        for action in report.get("actions") or []:
            failure_type = str(action.get("failure_type") or "")
            if not failure_type:
                continue
            counts[failure_type] = counts.get(failure_type, 0) + 1
            examples.setdefault(failure_type, []).append(f"{scenario}:{action.get('check_id')}")

    signals: list[dict[str, Any]] = []
    for failure_type, count in sorted(counts.items()):
        if count < threshold:
            continue
        dedupe_key = f"repair-policy:{failure_type}"
        signals.append({
            "id": f"retro_{sha1(dedupe_key.encode('utf-8')).hexdigest()[:12]}",
            "source": "repair.policy",
            "severity": "medium",
            "title": f"Repeated repair type: {failure_type}",
            "evidence": [
                f"failure_type={failure_type}",
                f"count={count}",
                f"examples={', '.join(examples.get(failure_type, [])[:5])}",
            ],
            "suggested_action": (
                f"Promote a reusable checklist or domain guidance item for {failure_type} repairs."
            ),
            "dedupe_key": dedupe_key,
        })
    return signals


def _repair_action(index: int, failure: dict[str, Any]) -> dict[str, Any]:
    failure_type = str(failure.get("type") or "inspection-failed")
    check_id = str(failure.get("check_id") or "unknown")
    priority = str(failure.get("severity") or "medium")
    return {
        "id": f"repair-{index:02d}",
        "failure_type": failure_type,
        "check_id": check_id,
        "priority": priority,
        "target": _repair_target(failure_type, failure),
        "instruction": failure.get("repair_hint") or _default_instruction(failure_type),
        "verification": _repair_verification(failure_type, check_id),
        "status": "pending",
    }


def _repair_target(failure_type: str, failure: dict[str, Any]) -> str:
    details = failure.get("details") or {}
    if failure_type == "layout-overflow" and isinstance(details, list) and details:
        first = details[0] if isinstance(details[0], dict) else {}
        return str(first.get("testid") or first.get("id") or first.get("tag") or "responsive layout")
    if failure_type.startswith("evidence"):
        return ".samvil/inspection-evidence.json"
    if failure_type == "screenshot-missing":
        return str(details.get("screenshot") if isinstance(details, dict) else "screenshot artifact")
    return str(failure.get("check_id") or failure_type)


def _default_instruction(failure_type: str) -> str:
    return f"Repair {failure_type} and re-run app inspection."


def _repair_verification(failure_type: str, check_id: str) -> str:
    return f"Re-run inspection and confirm {check_id} no longer fails ({failure_type})."


def _failure_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(failure.get("check_id")): failure
        for failure in report.get("failures") or []
        if failure.get("check_id")
    }


def _compact_failure(failure: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": failure.get("check_id"),
        "type": failure.get("type"),
        "severity": failure.get("severity"),
        "message": failure.get("message"),
    }


def _actions_with_status(actions: list[dict[str, Any]], after_failures: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for action in actions:
        row = dict(action)
        row["status"] = "pending" if action.get("check_id") in after_failures else "verified"
        updated.append(row)
    return updated


def _repair_report_next_action(status: str, remaining: list[dict[str, Any]]) -> str:
    if status == "verified":
        return "repair verified: re-run release checks"
    if remaining:
        first = remaining[0]
        return f"continue repair: {first.get('type')} ({first.get('check_id')})"
    return "run after-inspection to verify repair"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
