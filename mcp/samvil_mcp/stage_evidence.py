"""Collect mechanical build and QA evidence from persisted artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_EXIT_MARKER = re.compile(r"^SAMVIL_EXIT:(-?\d+)\s*$", re.MULTILINE)


def _last_exit_code(log_text: str) -> int | None:
    matches = list(_EXIT_MARKER.finditer(log_text))
    return int(matches[-1].group(1)) if matches else None


def _last_execution_block(log_text: str) -> str:
    matches = list(_EXIT_MARKER.finditer(log_text))
    if not matches:
        return log_text
    start = matches[-2].end() if len(matches) > 1 else 0
    return log_text[start : matches[-1].start()]


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _collect_build(root: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    relative = ".samvil/build.log"
    path = root / relative
    if not path.is_file():
        return (
            {
                "exit_code": None,
                "from": f"{relative} last execution block",
                "typecheck_ok": False,
                "warnings_count": 0,
            },
            [],
            [relative],
        )

    log_text = path.read_text(encoding="utf-8", errors="replace")
    exit_code = _last_exit_code(log_text)
    last_block = _last_execution_block(log_text)
    warnings_count = sum(
        1 for line in last_block.splitlines() if "warning" in line.casefold()
    )
    return (
        {
            "exit_code": exit_code,
            "from": f"{relative} last execution block",
            "typecheck_ok": exit_code == 0,
            "warnings_count": warnings_count,
        },
        [relative],
        [] if exit_code is not None else [relative],
    )


def _collect_qa(root: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    log_relative = ".samvil/qa.log"
    report_relative = ".samvil/test-results.json"
    log_path = root / log_relative
    report_path = root / report_relative
    evidence_files: list[str] = []
    missing: list[str] = []

    exit_code: int | None = None
    if log_path.is_file():
        evidence_files.append(log_relative)
        exit_code = _last_exit_code(
            log_path.read_text(encoding="utf-8", errors="replace")
        )
        if exit_code is None:
            missing.append(log_relative)
    else:
        missing.append(log_relative)

    report_valid = False
    passed = failed = skipped = 0
    if report_path.is_file():
        evidence_files.append(report_relative)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            stats = report.get("stats") if isinstance(report, dict) else None
            if isinstance(stats, dict):
                passed = _nonnegative_int(stats.get("expected")) + _nonnegative_int(
                    stats.get("flaky")
                )
                failed = _nonnegative_int(stats.get("unexpected"))
                skipped = _nonnegative_int(stats.get("skipped"))
                report_valid = True
            else:
                missing.append(report_relative)
        except (OSError, json.JSONDecodeError):
            missing.append(report_relative)
    else:
        missing.append(report_relative)

    runtime_verified = report_valid and (passed + failed + skipped > 0)
    return (
        {
            "npm_test": {
                "ran": report_valid,
                "exit_code": exit_code,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "from": report_relative,
            },
            "runtime_verified": runtime_verified,
            "static_only": not runtime_verified,
        },
        evidence_files,
        missing,
    )


def collect_stage_evidence(project_root: str | Path, stage: str) -> dict[str, Any]:
    """Return artifact-derived evidence for ``build`` or ``qa``.

    Missing or malformed artifacts are reported explicitly and never inferred as
    successful from caller-provided prose or metrics.
    """

    normalized_stage = stage.strip().casefold()
    if normalized_stage not in {"build", "qa"}:
        raise ValueError("stage must be build or qa")

    root = Path(project_root).expanduser().resolve()
    if normalized_stage == "build":
        evidence, evidence_files, missing = _collect_build(root)
    else:
        evidence, evidence_files, missing = _collect_qa(root)

    return {
        normalized_stage: evidence,
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence_files": evidence_files,
        "missing": missing,
    }
