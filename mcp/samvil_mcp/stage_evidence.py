"""Collect bounded artifact observations without overstating host trust."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_EXIT_MARKER = re.compile(r"^SAMVIL_EXIT:(-?\d+)\s*$", re.MULTILINE)
_MAX_LOG_BYTES = 2_000_000
_MAX_REPORT_BYTES = 10_000_000
_BUILD_TRUST_REASON = (
    "artifact-only build evidence is model-writable; a trusted host receipt "
    "is required before runtime_verified can be true"
)


def _read_tail(path: Path, limit: int = _MAX_LOG_BYTES) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        data = handle.read(limit)
    return data.decode("utf-8", errors="replace")


def _read_bounded(path: Path, limit: int) -> str:
    if path.stat().st_size > limit:
        raise ValueError(f"artifact exceeds {limit} bytes")
    return path.read_text(encoding="utf-8")


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
                "artifact_build_passed": False,
                "runtime_verified": False,
                "static_only": True,
                "trust_reason": _BUILD_TRUST_REASON,
            },
            [],
            [relative],
        )

    log_text = _read_tail(path)
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
            "artifact_build_passed": exit_code == 0,
            "runtime_verified": False,
            "static_only": True,
            "trust_reason": _BUILD_TRUST_REASON,
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
            _read_tail(log_path)
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
            report = json.loads(_read_bounded(report_path, _MAX_REPORT_BYTES))
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
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            missing.append(report_relative)
    else:
        missing.append(report_relative)

    artifact_runtime_passed = (
        report_valid
        and exit_code == 0
        and passed > 0
        and failed == 0
    )
    runtime_verified = False
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
            "artifact_runtime_passed": artifact_runtime_passed,
            "runtime_verified": runtime_verified,
            "static_only": True,
            "trust_reason": (
                "artifact-only QA evidence is model-writable; a trusted host "
                "receipt is required before runtime_verified can be true"
            ),
        },
        evidence_files,
        missing,
    )


def _trusted_runtime_matches(
    root: Path,
    stage: str,
    evidence: dict[str, Any],
    receipt: dict[str, Any] | None,
) -> bool:
    if not isinstance(receipt, dict):
        return False
    expected_path = f".samvil/{'build' if stage == 'build' else 'qa'}.log"
    authority = root / expected_path
    if (
        receipt.get("trusted_by") != "samvil_mcp_subprocess"
        or receipt.get("stage") != f"samvil-{stage}"
        or receipt.get("authority_path") != expected_path
        or not authority.is_file()
    ):
        return False
    authority_hash = hashlib.sha256(authority.read_bytes()).hexdigest()
    return (
        receipt.get("authority_sha256") == authority_hash
        and receipt.get("exit_code") == evidence.get("exit_code")
        and evidence.get("exit_code") == 0
    )


def collect_stage_evidence(
    project_root: str | Path,
    stage: str,
    *,
    trusted_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return artifact-derived observations for ``build`` or ``qa``.

    Missing or malformed artifacts are reported explicitly and never inferred as
    successful from caller-provided prose or metrics. A receipt produced by the
    MCP subprocess runner is accepted only when it matches the current log hash
    and exit code.
    """

    normalized_stage = stage.strip().casefold()
    if normalized_stage not in {"build", "qa"}:
        raise ValueError("stage must be build or qa")

    root = Path(project_root).expanduser().resolve()
    if normalized_stage == "build":
        evidence, evidence_files, missing = _collect_build(root)
    else:
        evidence, evidence_files, missing = _collect_qa(root)

    runtime_verified = _trusted_runtime_matches(
        root,
        normalized_stage,
        evidence if normalized_stage == "build" else {
            "exit_code": (evidence.get("npm_test") or {}).get("exit_code")
        },
        trusted_receipt,
    )
    evidence["runtime_verified"] = runtime_verified
    evidence["static_only"] = not runtime_verified
    if runtime_verified:
        evidence["trust_reason"] = "verified by samvil_mcp subprocess receipt"
        if normalized_stage == "qa":
            evidence["artifact_runtime_passed"] = True

    return {
        normalized_stage: evidence,
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence_files": evidence_files,
        "missing": missing,
    }
