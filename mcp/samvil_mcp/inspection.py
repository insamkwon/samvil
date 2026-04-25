"""Build user-visible app inspection reports from browser evidence."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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
        },
        "checks": checks,
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
    checks = report.get("checks") or []
    if checks:
        lines.extend(["", "## Checks"])
        for check in checks:
            lines.append(
                f"- [{str(check.get('status', '?')).upper()}] "
                f"{check.get('id')}: {check.get('message')}"
            )
    return "\n".join(lines)


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
