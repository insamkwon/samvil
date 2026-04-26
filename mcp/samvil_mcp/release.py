"""Release readiness report and gate evaluation for SAMVIL."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repair import evaluate_repair_gate

RELEASE_REPORT_SCHEMA_VERSION = "1.0"
RELEASE_BUNDLE_SCHEMA_VERSION = "1.0"
DEFAULT_REQUIRED_CHECKS: tuple[str, ...] = (
    "phase29_evolve_cycle_closure",
    "phase28_post_rebuild_qa",
    "phase27_rebuild_reentry",
    "phase26_evolve_rebuild",
    "phase25_evolve_apply",
    "phase24_evolve_proposal",
    "phase23_evolve_intake_context",
    "phase22_qa_recovery_routing",
    "phase21_qa_convergence_gate",
    "phase20_qa_materialization",
    "phase19_qa_synthesis_gate",
    "phase18_independent_evidence",
    "phase12_release_readiness",
    "phase11_repair_orchestration",
    "phase10_repair_regression",
    "phase8_browser_inspection",
    "pre_commit",
)
DEFAULT_RELEASE_COMMANDS: tuple[dict[str, Any], ...] = (
    {
        "name": "phase29_evolve_cycle_closure",
        "label": "Phase 29 evolve cycle closure dogfood",
        "command": "python3 scripts/phase29-evolve-cycle-closure-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase28_post_rebuild_qa",
        "label": "Phase 28 post-rebuild QA dogfood",
        "command": "python3 scripts/phase28-post-rebuild-qa-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase27_rebuild_reentry",
        "label": "Phase 27 rebuild reentry dogfood",
        "command": "python3 scripts/phase27-rebuild-reentry-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase26_evolve_rebuild",
        "label": "Phase 26 evolve rebuild handoff dogfood",
        "command": "python3 scripts/phase26-evolve-rebuild-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase25_evolve_apply",
        "label": "Phase 25 evolve apply dogfood",
        "command": "python3 scripts/phase25-evolve-apply-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase24_evolve_proposal",
        "label": "Phase 24 evolve proposal dogfood",
        "command": "python3 scripts/phase24-evolve-proposal-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase23_evolve_intake_context",
        "label": "Phase 23 evolve intake context dogfood",
        "command": "python3 scripts/phase23-evolve-intake-context-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase22_qa_recovery_routing",
        "label": "Phase 22 QA recovery routing dogfood",
        "command": "python3 scripts/phase22-qa-recovery-routing-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase21_qa_convergence_gate",
        "label": "Phase 21 QA convergence gate dogfood",
        "command": "python3 scripts/phase21-qa-convergence-gate-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase20_qa_materialization",
        "label": "Phase 20 QA materialization dogfood",
        "command": "python3 scripts/phase20-qa-materialization-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase19_qa_synthesis_gate",
        "label": "Phase 19 QA synthesis gate dogfood",
        "command": "python3 scripts/phase19-qa-synthesis-gate-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase18_independent_evidence",
        "label": "Phase 18 independent evidence contract dogfood",
        "command": "python3 scripts/phase18-independent-evidence-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase12_release_readiness",
        "label": "Phase 12 release readiness dogfood",
        "command": "python3 scripts/phase12-release-readiness-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase11_repair_orchestration",
        "label": "Phase 11 repair orchestration regression",
        "command": "python3 scripts/phase11-repair-orchestration-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase10_repair_regression",
        "label": "Phase 10 repair regression",
        "command": "python3 scripts/phase10-inspection-repair-dogfood.py",
        "timeout_seconds": 60,
    },
    {
        "name": "phase8_browser_inspection",
        "label": "Phase 8 browser inspection regression",
        "command": "python3 scripts/phase8-real-app-inspection.py",
        "timeout_seconds": 180,
    },
    {
        "name": "pre_commit",
        "label": "Full pre-commit check",
        "command": "bash scripts/pre-commit-check.sh",
        "timeout_seconds": 180,
    },
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def release_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "release-report.json"


def release_summary_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "release-summary.md"


def build_release_report(
    project_root: Path | str,
    *,
    checks: list[dict[str, Any]] | None = None,
    required_checks: list[str] | tuple[str, ...] | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Build a normalized release readiness report from named check results."""
    root = Path(project_root)
    required = list(required_checks or DEFAULT_REQUIRED_CHECKS)
    normalized = _normalize_checks(checks or [], required)
    failed = [check for check in normalized if check["status"] == "fail"]
    missing = [check for check in normalized if check["status"] == "missing"]
    passed = [check for check in normalized if check["status"] == "pass"]
    status = "pass" if not failed and not missing else "blocked"
    return {
        "schema_version": RELEASE_REPORT_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": source,
        "required_checks": required,
        "summary": {
            "status": status,
            "total_checks": len(normalized),
            "passed_checks": len(passed),
            "failed_checks": len(failed),
            "missing_checks": len(missing),
        },
        "checks": normalized,
        "next_action": _release_report_next_action(failed, missing),
    }


def run_release_checks(
    project_root: Path | str,
    *,
    commands: list[dict[str, Any]] | None = None,
    required_checks: list[str] | tuple[str, ...] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Execute release check commands and return a runner-generated report."""
    root = Path(project_root)
    command_rows = commands if commands is not None else [dict(row) for row in DEFAULT_RELEASE_COMMANDS]
    checks = [_run_release_command(root, command) for command in command_rows]
    report = build_release_report(
        root,
        checks=checks,
        required_checks=required_checks or [str(row.get("name")) for row in command_rows],
        source="runner",
    )
    if persist:
        write_release_report(report, root)
    return report


def write_release_report(report: dict[str, Any], project_root: Path | str) -> Path:
    return _atomic_write_json(release_report_path(project_root), report)


def read_release_report(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(release_report_path(project_root))
    return data or None


def build_release_evidence_bundle(
    project_root: Path | str,
    *,
    release_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a one-file release evidence bundle from the latest report."""
    root = Path(project_root)
    report = release_report if release_report is not None else read_release_report(root) or {}
    gate = evaluate_release_gate(root, release_report=report)
    summary = report.get("summary", {}) or {}
    return {
        "schema_version": RELEASE_BUNDLE_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "path": str(release_summary_path(root)),
        "release_report_path": str(release_report_path(root)),
        "release": {
            "status": summary.get("status"),
            "source": report.get("source") or "manual",
            "generated_at": report.get("generated_at"),
            "total_checks": summary.get("total_checks", 0),
            "passed_checks": summary.get("passed_checks", 0),
            "failed_checks": summary.get("failed_checks", 0),
            "missing_checks": summary.get("missing_checks", 0),
            "next_action": report.get("next_action"),
        },
        "gate": gate,
        "git": _git_summary(root),
        "versions": _version_summary(root),
        "checks": [_bundle_check(row) for row in report.get("checks") or []],
    }


def write_release_evidence_bundle(bundle: dict[str, Any], project_root: Path | str) -> Path:
    target = release_summary_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(render_release_evidence_bundle(bundle), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_release_evidence_bundle(project_root: Path | str) -> str | None:
    path = release_summary_path(project_root)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def render_release_evidence_bundle(bundle: dict[str, Any]) -> str:
    """Render a release bundle as review-friendly markdown."""
    release = bundle.get("release", {}) or {}
    gate = bundle.get("gate", {}) or {}
    git = bundle.get("git", {}) or {}
    versions = bundle.get("versions", {}) or {}
    checks = bundle.get("checks") or []
    tags = git.get("tags_at_head") or []
    lines = [
        "# Release Evidence Bundle",
        f"_generated: {bundle.get('generated_at', '')}_",
        "",
        "## Verdict",
        f"- Gate: {gate.get('verdict') or '?'}",
        f"- Reason: {gate.get('reason') or '?'}",
        f"- Next action: {gate.get('next_action') or '?'}",
        "",
        "## Release Report",
        f"- Source: {release.get('source') or '?'}",
        f"- Status: {release.get('status') or '?'}",
        f"- Checks: {release.get('passed_checks', 0)} passed / "
        f"{release.get('failed_checks', 0)} failed / "
        f"{release.get('missing_checks', 0)} missing",
        f"- Report path: {bundle.get('release_report_path') or '?'}",
        "",
        "## Git",
        f"- Branch: {git.get('branch') or '?'}",
        f"- HEAD: {git.get('head') or '?'}",
        f"- Tags at HEAD: {', '.join(tags) if tags else '(none)'}",
        f"- Dirty: {git.get('dirty')}",
        "",
        "## Versions",
        f"- Plugin: {versions.get('plugin') or '?'}",
        f"- Package: {versions.get('package') or '?'}",
        f"- README: {versions.get('readme') or '?'}",
        f"- Synced: {versions.get('synced')}",
        "",
        "## Checks",
    ]
    if not checks:
        lines.append("- (no checks recorded)")
    for check in checks:
        lines.append(
            f"- [{str(check.get('status', '?')).upper()}] {check.get('name')}: "
            f"exit={check.get('exit_code')} duration={check.get('duration_seconds')}s"
        )
        if check.get("command"):
            lines.append(f"  command: `{check.get('command')}`")
        if check.get("message"):
            lines.append(f"  message: {check.get('message')}")
        if check.get("status") != "pass":
            stdout = str(check.get("stdout_tail") or "").strip()
            stderr = str(check.get("stderr_tail") or "").strip()
            if stdout:
                lines.extend(["  stdout tail:", "  ```text", _indent_block(stdout), "  ```"])
            if stderr:
                lines.extend(["  stderr tail:", "  ```text", _indent_block(stderr), "  ```"])
    return "\n".join(lines) + "\n"


def render_release_report(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) or {}
    lines = [
        "# Release Readiness Report",
        f"_generated: {report.get('generated_at', '')}_",
        "",
        f"- Source: {report.get('source') or 'manual'}",
        f"- Status: {summary.get('status') or '?'}",
        f"- Checks: {summary.get('passed_checks', 0)} passed / "
        f"{summary.get('failed_checks', 0)} failed / "
        f"{summary.get('missing_checks', 0)} missing",
        f"- Next action: {report.get('next_action') or '?'}",
    ]
    checks = report.get("checks") or []
    if checks:
        lines.extend(["", "## Checks"])
        for check in checks:
            lines.append(
                f"- [{str(check.get('status', '?')).upper()}] "
                f"{check.get('name')}: {check.get('label') or check.get('message') or ''}"
            )
            command = check.get("command")
            if command:
                lines.append(f"  command: `{command}`")
            duration = check.get("duration_seconds")
            if isinstance(duration, (int, float)):
                lines.append(f"  duration: {duration:.2f}s")
            if check.get("exit_code") is not None:
                lines.append(f"  exit_code: {check.get('exit_code')}")
            if check.get("message"):
                lines.append(f"  message: {check.get('message')}")
    return "\n".join(lines)


def evaluate_release_gate(
    project_root: Path | str,
    *,
    release_report: dict[str, Any] | None = None,
    repair_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic release gate verdict for final progression."""
    root = Path(project_root)
    report = release_report if release_report is not None else read_release_report(root) or {}
    repair = repair_gate if repair_gate is not None else evaluate_repair_gate(root)
    repair_verdict = repair.get("verdict")
    summary = report.get("summary", {}) or {}
    report_status = summary.get("status")
    failed_checks = int(summary.get("failed_checks") or 0)
    missing_checks = int(summary.get("missing_checks") or 0)

    if repair_verdict == "blocked":
        verdict = "blocked"
        reason = "repair gate is blocked"
        next_action = repair.get("next_action") or "clear repair gate"
    elif not report and repair_verdict == "pass":
        verdict = "blocked"
        reason = "repair is verified but release checks are missing"
        next_action = "run release checks"
    elif not report:
        verdict = "not-applicable"
        reason = "release checks have not started"
        next_action = "continue"
    elif report_status == "pass" and failed_checks == 0 and missing_checks == 0:
        verdict = "pass"
        reason = "all required release checks passed"
        next_action = "ready to tag release"
    else:
        verdict = "blocked"
        reason = "required release checks are failed or missing"
        next_action = report.get("next_action") or "fix release checks"

    return {
        "gate": "release",
        "verdict": verdict,
        "reason": reason,
        "next_action": next_action,
        "repair_gate_verdict": repair_verdict,
        "release_report_status": report_status,
        "failed_checks": failed_checks,
        "missing_checks": missing_checks,
    }


def release_summary(project_root: Path | str) -> dict[str, Any]:
    """Read release artifacts into a compact run-report summary."""
    root = Path(project_root)
    report = read_release_report(root) or {}
    gate = evaluate_release_gate(root, release_report=report)
    summary = report.get("summary", {}) or {}
    return {
        "report_present": bool(report),
        "report_status": summary.get("status"),
        "total_checks": summary.get("total_checks", 0),
        "passed_checks": summary.get("passed_checks", 0),
        "failed_checks": summary.get("failed_checks", 0),
        "missing_checks": summary.get("missing_checks", 0),
        "source": report.get("source"),
        "gate": gate,
    }


def _normalize_checks(checks: list[dict[str, Any]], required: list[str]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for check in checks:
        name = str(check.get("name") or "").strip()
        if not name:
            continue
        status = str(check.get("status") or "").strip().lower()
        if status not in {"pass", "fail", "missing"}:
            status = "fail"
        by_name[name] = {
            "name": name,
            "label": check.get("label") or name.replace("_", " "),
            "status": status,
            "command": check.get("command") or "",
            "message": check.get("message") or "",
            "evidence": check.get("evidence") or [],
            "exit_code": check.get("exit_code"),
            "duration_seconds": check.get("duration_seconds"),
            "stdout_tail": check.get("stdout_tail") or "",
            "stderr_tail": check.get("stderr_tail") or "",
            "timeout_seconds": check.get("timeout_seconds"),
        }

    normalized: list[dict[str, Any]] = []
    for name in required:
        if name in by_name:
            normalized.append(by_name.pop(name))
        else:
            normalized.append({
                "name": name,
                "label": name.replace("_", " "),
                "status": "missing",
                "command": "",
                "message": "required release check has no evidence",
                "evidence": [],
                "exit_code": None,
                "duration_seconds": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "timeout_seconds": None,
            })
    normalized.extend(by_name[name] for name in sorted(by_name))
    return normalized


def _release_report_next_action(
    failed: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> str:
    if failed:
        first = failed[0]
        return f"fix release check: {first.get('name')}"
    if missing:
        first = missing[0]
        return f"run release check: {first.get('name')}"
    return "release checks passed"


def _run_release_command(root: Path, command: dict[str, Any]) -> dict[str, Any]:
    name = str(command.get("name") or "").strip()
    if not name:
        name = "unnamed_check"
    command_text = str(command.get("command") or "").strip()
    timeout = float(command.get("timeout_seconds") or 120)
    label = command.get("label") or name.replace("_", " ")
    if not command_text:
        return {
            "name": name,
            "label": label,
            "status": "fail",
            "command": command_text,
            "timeout_seconds": timeout,
            "exit_code": None,
            "duration_seconds": 0.0,
            "message": "release check has no command",
            "stdout_tail": "",
            "stderr_tail": "",
            "evidence": [],
        }

    started = time.monotonic()
    try:
        result = subprocess.run(
            shlex.split(command_text),
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration = time.monotonic() - started
        status = "pass" if result.returncode == 0 else "fail"
        return {
            "name": name,
            "label": label,
            "status": status,
            "command": command_text,
            "timeout_seconds": timeout,
            "exit_code": result.returncode,
            "duration_seconds": round(duration, 3),
            "message": "command passed" if status == "pass" else f"command exited {result.returncode}",
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
            "evidence": [f"exit_code={result.returncode}", f"duration_seconds={duration:.3f}"],
        }
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "name": name,
            "label": label,
            "status": "fail",
            "command": command_text,
            "timeout_seconds": timeout,
            "exit_code": None,
            "duration_seconds": round(duration, 3),
            "message": f"command timed out after {timeout:g}s",
            "stdout_tail": _tail(stdout),
            "stderr_tail": _tail(stderr),
            "evidence": [f"timeout_seconds={timeout:g}", f"duration_seconds={duration:.3f}"],
        }


def _tail(text: str, *, limit: int = 2000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _bundle_check(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": check.get("name"),
        "label": check.get("label"),
        "status": check.get("status"),
        "command": check.get("command"),
        "message": check.get("message"),
        "exit_code": check.get("exit_code"),
        "duration_seconds": check.get("duration_seconds"),
        "stdout_tail": check.get("stdout_tail") or "",
        "stderr_tail": check.get("stderr_tail") or "",
    }


def _git_summary(root: Path) -> dict[str, Any]:
    return {
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git(root, "rev-parse", "HEAD"),
        "short_head": _git(root, "rev-parse", "--short", "HEAD"),
        "tags_at_head": [
            tag for tag in _git(root, "tag", "--points-at", "HEAD").splitlines() if tag
        ],
        "dirty": bool(_git(root, "status", "--porcelain")),
    }


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _version_summary(root: Path) -> dict[str, Any]:
    plugin = _json_version(root / ".claude-plugin" / "plugin.json")
    package = _package_version(root / "mcp" / "samvil_mcp" / "__init__.py")
    readme = _readme_version(root / "README.md")
    values = [v for v in (plugin, package, readme) if v]
    return {
        "plugin": plugin,
        "package": package,
        "readme": readme,
        "synced": bool(values) and len(set(values)) == 1 and len(values) == 3,
    }


def _json_version(path: Path) -> str:
    data = _load_json(path)
    value = data.get("version")
    return str(value) if value else ""


def _package_version(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    marker = '__version__ = "'
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split('"', 1)[0]


def _readme_version(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    marker = "`v"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("`", 1)[0]


def _indent_block(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
