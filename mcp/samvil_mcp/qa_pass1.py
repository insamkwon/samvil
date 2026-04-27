"""Pass 1 (Mechanical) + Pass 1b (Smoke) digest for samvil-qa.

Single best-effort call that **digests** the build log + smoke probe
output the skill body just produced and returns a verdict + structured
issue list. The skill body still shells out (npm run build, npx tsc,
playwright MCP), because those calls are CC/host-bound (P8). This
module owns the **interpretation** of the resulting artifacts.

Inputs:
  - `project_path` — repo root (so we can read .samvil/build.log).
  - `pass1_exit_code` — the exit code from the build/typecheck command
    the skill body just ran. 0 == PASS, non-0 == FAIL with errors
    extracted from the build log.
  - `smoke_result_json` — JSON the skill body collected from Playwright
    MCP (or `null` for the "skipped"/automation case). Schema:
      {
        "method": "playwright" | "static" | "skipped",
        "console_errors": [str, ...],
        "empty_routes": [str, ...],
        "screenshots": [str, ...],
        "fallback_reason": str (optional, only when method == "static")
      }
  - `solution_type` — needed to choose the smoke verdict shape.

Outputs:
  - `pass1.status` — "PASS" | "FAIL"
  - `pass1.errors[]` — extracted error lines from build.log when FAIL
  - `pass1b.status` — "PASS" | "FAIL" | "SKIPPED"
  - `pass1b.method` — "playwright" | "static" | "skipped"
  - `pass1b.console_errors[]`, `pass1b.empty_routes[]`
  - `should_proceed_to_pass2` — bool. False if Pass 1 or Pass 1b FAIL.
  - `verdict_reason` — short string for handoff/event log.
  - `events[]` — event drafts ready for save_event (skill body emits).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QA_PASS1_SCHEMA_VERSION = "1.0"

# Errors we consider "real" (TypeScript / build / module). Excludes
# warnings, deprecation notices, and info lines. Tail-only — we never
# read the entire build log into memory.
_BUILD_ERROR_PATTERNS = [
    re.compile(r"^.*error TS\d+:.*$", re.MULTILINE),  # TypeScript errors
    re.compile(r"^.*Module not found:.*$", re.MULTILINE),  # webpack/Next.js
    re.compile(r"^.*Cannot find module.*$", re.MULTILINE),  # Node/TSC
    re.compile(r"^.*SyntaxError:.*$", re.MULTILINE),  # Python/JS
    re.compile(r"^.*ImportError:.*$", re.MULTILINE),  # Python
    re.compile(r"^.*ModuleNotFoundError:.*$", re.MULTILINE),  # Python
    re.compile(r"^Error: .*$", re.MULTILINE),  # generic
]

_MAX_ERRORS_RETURNED = 30
_MAX_LOG_TAIL_BYTES = 50_000


def _extract_build_errors(log_path: Path) -> list[str]:
    """Tail the build log and extract real error lines.

    Returns up to _MAX_ERRORS_RETURNED de-duped error strings, in the
    order they appear. Best-effort — empty list on missing/unreadable log.
    """
    if not log_path.is_file():
        return []
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fp:
            if size > _MAX_LOG_TAIL_BYTES:
                fp.seek(size - _MAX_LOG_TAIL_BYTES)
            tail = fp.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    errors: list[str] = []
    seen: set[str] = set()
    for pattern in _BUILD_ERROR_PATTERNS:
        for match in pattern.finditer(tail):
            line = match.group(0).strip()
            if line and line not in seen:
                seen.add(line)
                errors.append(line)
                if len(errors) >= _MAX_ERRORS_RETURNED:
                    return errors
    return errors


def _smoke_verdict(
    smoke_result: dict[str, Any] | None,
    solution_type: str,
) -> dict[str, Any]:
    """Reduce a Playwright/static/skipped probe payload to a verdict.

    Verdict rules:
      - method == "skipped" → SKIPPED (e.g., automation cc-skill)
      - any console_errors → FAIL
      - any empty_routes → FAIL
      - else → PASS (with method recorded in detail)
    """
    if smoke_result is None:
        return {
            "status": "SKIPPED",
            "method": "skipped",
            "console_errors": [],
            "empty_routes": [],
            "screenshots": [],
            "fallback_reason": "",
            "reason": "no smoke payload supplied",
        }

    method = str(smoke_result.get("method") or "skipped")
    console_errors = list(smoke_result.get("console_errors") or [])
    empty_routes = list(smoke_result.get("empty_routes") or [])
    screenshots = list(smoke_result.get("screenshots") or [])
    fallback_reason = str(smoke_result.get("fallback_reason") or "")

    if method == "skipped":
        return {
            "status": "SKIPPED",
            "method": "skipped",
            "console_errors": console_errors,
            "empty_routes": empty_routes,
            "screenshots": screenshots,
            "fallback_reason": fallback_reason,
            "reason": f"smoke skipped for solution_type={solution_type}",
        }

    if console_errors or empty_routes:
        reason_parts: list[str] = []
        if console_errors:
            reason_parts.append(f"{len(console_errors)} console error(s)")
        if empty_routes:
            reason_parts.append(f"{len(empty_routes)} empty route(s)")
        return {
            "status": "FAIL",
            "method": method,
            "console_errors": console_errors[:20],
            "empty_routes": empty_routes[:20],
            "screenshots": screenshots,
            "fallback_reason": fallback_reason,
            "reason": "; ".join(reason_parts),
        }

    return {
        "status": "PASS",
        "method": method,
        "console_errors": [],
        "empty_routes": [],
        "screenshots": screenshots,
        "fallback_reason": fallback_reason,
        "reason": "no console errors, no empty routes",
    }


@dataclass
class QAPass1Report:
    schema_version: str = QA_PASS1_SCHEMA_VERSION
    project_path: str = ""
    pass1: dict[str, Any] = field(default_factory=dict)
    pass1b: dict[str, Any] = field(default_factory=dict)
    should_proceed_to_pass2: bool = False
    verdict_reason: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_path": self.project_path,
            "pass1": self.pass1,
            "pass1b": self.pass1b,
            "should_proceed_to_pass2": self.should_proceed_to_pass2,
            "verdict_reason": self.verdict_reason,
            "events": self.events,
            "notes": self.notes,
            "errors": self.errors,
        }


def dispatch_qa_pass1_batch(
    project_path: str | Path,
    *,
    pass1_exit_code: int,
    smoke_result: dict[str, Any] | None = None,
    solution_type: str = "web-app",
    log_path_override: str | None = None,
) -> dict[str, Any]:
    """Digest Pass 1 + Pass 1b artifacts and return a structured verdict.

    The skill body owns the actual command execution + Playwright calls.
    This function owns the **interpretation**: which lines are real
    errors, which probe outcomes are FAIL vs PASS vs SKIPPED, what
    event drafts to emit.

    Args:
        project_path: Repo root (used to find `.samvil/build.log`).
        pass1_exit_code: Exit code from the mechanical command the
            skill body just ran (0 = pass).
        smoke_result: Optional dict with `method`, `console_errors`,
            `empty_routes`, `screenshots`, `fallback_reason`. None for
            automation/skipped paths.
        solution_type: For verdict-shape decisions (smoke method).
        log_path_override: Custom build.log location (defaults to
            `<project_path>/.samvil/build.log`).

    Returns:
        QAPass1Report dict.
    """
    report = QAPass1Report()
    root = Path(str(project_path)).expanduser()
    report.project_path = str(root)

    if log_path_override:
        log_path = Path(log_path_override)
    else:
        log_path = root / ".samvil" / "build.log"

    # Pass 1.
    if pass1_exit_code == 0:
        pass1_status = "PASS"
        pass1_errors: list[str] = []
        pass1_reason = "build/typecheck exited 0"
    else:
        pass1_status = "FAIL"
        pass1_errors = _extract_build_errors(log_path)
        if pass1_errors:
            pass1_reason = f"exit_code={pass1_exit_code}; {len(pass1_errors)} error line(s)"
        else:
            pass1_reason = f"exit_code={pass1_exit_code}; build log empty or unparseable"
            report.notes.append(
                f"build log {log_path} had no recognizable error lines — verify log path"
            )

    report.pass1 = {
        "status": pass1_status,
        "exit_code": pass1_exit_code,
        "errors": pass1_errors,
        "reason": pass1_reason,
        "log_path": str(log_path),
    }

    # Pass 1b.
    if pass1_status == "FAIL":
        # Pass 1 failed → skip Pass 1b entirely (per legacy SKILL.md
        # "If Pass 1 fails: Verdict = REVISE… Skip Pass 1b").
        report.pass1b = {
            "status": "SKIPPED",
            "method": "skipped",
            "console_errors": [],
            "empty_routes": [],
            "screenshots": [],
            "fallback_reason": "",
            "reason": "Pass 1 failed — smoke skipped",
        }
        report.should_proceed_to_pass2 = False
        report.verdict_reason = "Pass 1 (mechanical) failed"
    else:
        report.pass1b = _smoke_verdict(smoke_result, solution_type)
        smoke_status = report.pass1b["status"]
        if smoke_status == "FAIL":
            report.should_proceed_to_pass2 = False
            report.verdict_reason = f"Pass 1b smoke failed: {report.pass1b['reason']}"
        else:
            # SKIPPED or PASS both let Pass 2 run.
            report.should_proceed_to_pass2 = True
            report.verdict_reason = f"Pass 1 PASS; Pass 1b {smoke_status}"

    # Event drafts (skill body emits via save_event).
    if pass1_status == "PASS":
        report.events.append({
            "event_type": "qa_pass1_complete",
            "stage": "qa",
            "data": {"status": "PASS"},
        })
    else:
        report.events.append({
            "event_type": "qa_pass1_fail",
            "stage": "qa",
            "data": {
                "status": "FAIL",
                "exit_code": pass1_exit_code,
                "error_count": len(pass1_errors),
                "first_error": pass1_errors[0] if pass1_errors else "",
            },
        })

    p1b_status = report.pass1b["status"]
    if p1b_status != "SKIPPED":
        report.events.append({
            "event_type": "qa_smoke_complete" if p1b_status == "PASS" else "qa_smoke_fail",
            "stage": "qa",
            "data": {
                "status": p1b_status,
                "method": report.pass1b["method"],
                "console_error_count": len(report.pass1b["console_errors"]),
                "empty_route_count": len(report.pass1b["empty_routes"]),
            },
        })

    if report.pass1b.get("fallback_reason"):
        report.notes.append(
            f"Pass 1b fell back to static analysis: {report.pass1b['fallback_reason']}"
        )

    return report.to_dict()
