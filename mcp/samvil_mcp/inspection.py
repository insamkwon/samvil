"""Build user-visible app inspection reports from browser evidence."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any

INSPECTION_REPORT_SCHEMA_VERSION = "1.0"
INSPECTION_EVIDENCE_SCHEMA_VERSION = "1.0"


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


def inspection_evidence_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "inspection-evidence.json"


def inspection_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "inspection-report.json"


def build_inspection_report(
    project_root: Path | str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic inspection report from browser evidence."""
    root = Path(project_root)
    evidence_data = evidence if evidence is not None else _load_json(inspection_evidence_path(root))
    checks = _checks_from_evidence(root, evidence_data)
    passed = sum(1 for check in checks if check["status"] == "pass")
    warnings = sum(1 for check in checks if check["status"] == "warn")
    failed = sum(1 for check in checks if check["status"] == "fail")
    failures = _failures_from_checks(checks)
    console_errors = _console_error_count(evidence_data)
    screenshots = _screenshots(evidence_data)
    status = "fail" if failed else "warn" if warnings else "pass"

    return {
        "schema_version": INSPECTION_REPORT_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "scenario": evidence_data.get("scenario") or root.name,
        "url": evidence_data.get("url") or "",
        "summary": {
            "status": status,
            "total_checks": len(checks),
            "passed_checks": passed,
            "warning_checks": warnings,
            "failed_checks": failed,
            "console_errors": console_errors,
            "screenshots": len(screenshots),
            "viewports": len(evidence_data.get("viewports") or []),
            "failure_types": sorted({failure["type"] for failure in failures}),
        },
        "checks": checks,
        "failures": failures,
        "next_action": _next_action(failures),
        "artifacts": screenshots,
        "evidence_schema_version": evidence_data.get("schema_version"),
        "viewports": evidence_data.get("viewports") or [],
        "interactions": evidence_data.get("interactions") or [],
    }


def write_inspection_report(report: dict[str, Any], project_root: Path | str) -> Path:
    target = inspection_report_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_inspection_report(project_root: Path | str) -> dict[str, Any] | None:
    report = _load_json(inspection_report_path(project_root))
    return report or None


def render_inspection_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) or {}
    lines = [
        f"# Inspection Report — {report.get('scenario') or 'unknown'}",
        f"_generated: {report.get('generated_at', '')}_",
        "",
        f"- Status: {summary.get('status') or '?'}",
        f"- Checks: {summary.get('passed_checks', 0)} passed / {summary.get('failed_checks', 0)} failed / {summary.get('warning_checks', 0)} warnings",
        f"- Console errors: {summary.get('console_errors', 0)}",
        f"- Viewports: {summary.get('viewports', 0)}",
        f"- Screenshots: {summary.get('screenshots', 0)}",
    ]
    artifacts = report.get("artifacts") or []
    if artifacts:
        lines.extend(["", "## Artifacts"])
        for artifact in artifacts[:8]:
            lines.append(f"- {artifact}")
    failures = report.get("failures") or []
    if failures:
        lines.extend(["", "## Failures"])
        for failure in failures:
            lines.append(
                f"- {failure.get('type')}: {failure.get('repair_hint')} "
                f"({failure.get('check_id')})"
            )
    checks = report.get("checks") or []
    if checks:
        lines.extend(["", "## Checks"])
        for check in checks:
            lines.append(
                f"- [{str(check.get('status', '?')).upper()}] "
                f"{check.get('id')}: {check.get('message')}"
            )
    return "\n".join(lines)


def derive_inspection_observations(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert failed inspection checks into retro observation candidates."""
    observations: list[dict[str, Any]] = []
    scenario = str(report.get("scenario") or "unknown")
    for failure in report.get("failures") or []:
        failure_type = str(failure.get("type") or "unknown")
        check_id = str(failure.get("check_id") or "unknown")
        repair_hint = str(failure.get("repair_hint") or "Inspect the failed UI check.")
        dedupe_key = f"inspection:{scenario}:{failure_type}:{check_id}"
        observations.append({
            "id": f"retro_{sha1(dedupe_key.encode('utf-8')).hexdigest()[:12]}",
            "source": "inspection.report",
            "severity": failure.get("severity") or "medium",
            "title": f"Inspection failed: {failure_type}",
            "evidence": [
                f"scenario={scenario}",
                f"check_id={check_id}",
                f"message={failure.get('message') or ''}",
            ],
            "suggested_action": repair_hint,
            "dedupe_key": dedupe_key,
        })
    return observations


def _checks_from_evidence(root: Path, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not evidence:
        return [_check("evidence.present", "fail", "inspection evidence is missing")]
    _add_bool_check(checks, "evidence.schema", evidence.get("schema_version") == INSPECTION_EVIDENCE_SCHEMA_VERSION, "inspection evidence schema is valid")

    viewports = evidence.get("viewports") or []
    _add_bool_check(checks, "viewports.present", bool(viewports), "at least one viewport was inspected")
    for viewport in viewports:
        name = str(viewport.get("name") or "viewport")
        _add_bool_check(checks, f"viewport.{name}.loaded", bool(viewport.get("loaded")), f"{name} loaded")
        _add_bool_check(
            checks,
            f"viewport.{name}.console",
            not viewport.get("console_errors"),
            f"{name} has no console errors",
            details=viewport.get("console_errors") or [],
        )
        _add_bool_check(
            checks,
            f"viewport.{name}.overflow",
            int(viewport.get("overflow_count") or 0) == 0,
            f"{name} has no detected layout overflow",
            details=viewport.get("overflow") or [],
        )
        screenshot = str(viewport.get("screenshot") or "")
        _add_bool_check(
            checks,
            f"viewport.{name}.screenshot",
            bool(screenshot) and (root / screenshot).exists(),
            f"{name} screenshot artifact exists",
            details={"screenshot": screenshot},
        )
        if "canvas_nonblank" in viewport:
            _add_bool_check(
                checks,
                f"viewport.{name}.canvas",
                bool(viewport.get("canvas_nonblank")),
                f"{name} canvas is nonblank",
            )

    interactions = evidence.get("interactions") or []
    _add_bool_check(checks, "interactions.present", bool(interactions), "at least one interaction was inspected")
    for interaction in interactions:
        interaction_id = str(interaction.get("id") or "interaction")
        _add_bool_check(
            checks,
            f"interaction.{interaction_id}",
            interaction.get("status") == "pass",
            str(interaction.get("message") or interaction_id),
            details=interaction.get("details") or {},
        )
    return checks


def _add_bool_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    message: str,
    *,
    details: Any = None,
) -> None:
    checks.append(_check(check_id, "pass" if passed else "fail", message, details=details))


def _check(check_id: str, status: str, message: str, *, details: Any = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "message": message,
        "details": details if details is not None else {},
    }


def _failures_from_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for check in checks:
        if check.get("status") != "fail":
            continue
        check_id = str(check.get("id") or "unknown")
        failure_type = _failure_type(check_id)
        failures.append({
            "check_id": check_id,
            "type": failure_type,
            "severity": _failure_severity(failure_type),
            "message": check.get("message") or "",
            "repair_hint": _repair_hint(failure_type, check),
            "details": check.get("details") or {},
        })
    return failures


def _failure_type(check_id: str) -> str:
    if check_id == "evidence.present":
        return "evidence-missing"
    if check_id == "evidence.schema":
        return "evidence-invalid"
    if check_id == "viewports.present":
        return "viewport-missing"
    if check_id.endswith(".loaded"):
        return "viewport-load-failed"
    if check_id.endswith(".console"):
        return "console-error"
    if check_id.endswith(".overflow"):
        return "layout-overflow"
    if check_id.endswith(".screenshot"):
        return "screenshot-missing"
    if check_id.endswith(".canvas"):
        return "canvas-blank"
    if check_id.startswith("interaction."):
        return "interaction-failed"
    return "inspection-failed"


def _failure_severity(failure_type: str) -> str:
    if failure_type in {
        "evidence-missing",
        "evidence-invalid",
        "viewport-load-failed",
        "console-error",
        "interaction-failed",
        "canvas-blank",
    }:
        return "high"
    if failure_type in {"layout-overflow", "screenshot-missing", "viewport-missing"}:
        return "medium"
    return "low"


def _repair_hint(failure_type: str, check: dict[str, Any]) -> str:
    hints = {
        "evidence-missing": "Generate browser inspection evidence before judging app quality.",
        "evidence-invalid": "Regenerate inspection evidence with schema_version=1.0.",
        "viewport-missing": "Run inspection against at least one viewport.",
        "viewport-load-failed": "Start the dev server and fix page load errors before re-running inspection.",
        "console-error": "Fix browser console/page errors first; inspect the recorded console error details.",
        "layout-overflow": "Fix responsive layout for the failing viewport and elements listed in overflow details.",
        "screenshot-missing": "Ensure Playwright writes the screenshot artifact and the relative path is correct.",
        "canvas-blank": "Render visible canvas content before passing the browser game inspection.",
        "interaction-failed": "Fix the failing user interaction handler or the DOM state asserted by inspection.",
    }
    return hints.get(failure_type, f"Inspect failed check {check.get('id')}.")


def _next_action(failures: list[dict[str, Any]]) -> str:
    if not failures:
        return "inspection passed"
    ordered = sorted(
        failures,
        key=lambda failure: {"high": 0, "medium": 1, "low": 2}.get(str(failure.get("severity")), 3),
    )
    first = ordered[0]
    return f"repair inspection failure: {first['type']} ({first['check_id']})"


def _console_error_count(evidence: dict[str, Any]) -> int:
    total = 0
    for viewport in evidence.get("viewports") or []:
        total += len(viewport.get("console_errors") or [])
    return total


def _screenshots(evidence: dict[str, Any]) -> list[str]:
    screenshots: list[str] = []
    for viewport in evidence.get("viewports") or []:
        screenshot = viewport.get("screenshot")
        if screenshot:
            screenshots.append(str(screenshot))
    return screenshots
