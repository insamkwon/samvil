"""Tests for build guard logic: build log parsing, error classification, metrics.

The scaffold skill (samvil-scaffold) uses a circuit breaker pattern for builds.
These tests validate the parsing and analysis logic that supports that pattern.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ── Build metrics JSONL parsing ──────────────────────────────────


SAMPLE_BUILD_METRICS = [
    {
        "timestamp": "2026-04-11T10:00:00Z",
        "event": "build_start",
        "stack": "nextjs14",
        "session_id": "sess-001",
    },
    {
        "timestamp": "2026-04-11T10:01:30Z",
        "event": "build_complete",
        "stack": "nextjs14",
        "session_id": "sess-001",
        "exit_code": 0,
        "duration_seconds": 90,
    },
    {
        "timestamp": "2026-04-11T11:00:00Z",
        "event": "build_start",
        "stack": "vite-react",
        "session_id": "sess-002",
    },
    {
        "timestamp": "2026-04-11T11:00:45Z",
        "event": "build_complete",
        "stack": "vite-react",
        "session_id": "sess-002",
        "exit_code": 1,
        "duration_seconds": 45,
        "error_category": "type_error",
        "error_count": 3,
    },
]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write a list of dicts as JSONL file."""
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_build_metrics_parse():
    """build-metrics.jsonl을 파싱하면 각 줄이 유효한 JSON이어야 함."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for rec in SAMPLE_BUILD_METRICS:
            f.write(json.dumps(rec) + "\n")
        tmp_path = Path(f.name)

    try:
        parsed = []
        with open(tmp_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    parsed.append(json.loads(line))

        assert len(parsed) == 4
        assert parsed[0]["event"] == "build_start"
        assert parsed[1]["event"] == "build_complete"
        assert parsed[1]["exit_code"] == 0
        assert parsed[3]["exit_code"] == 1
    finally:
        tmp_path.unlink()


def test_build_metrics_empty_file():
    """빈 파일은 빈 리스트를 반환해야 함."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        parsed = []
        with open(tmp_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    parsed.append(json.loads(line))
        assert parsed == []
    finally:
        tmp_path.unlink()


# ── Build time calculation ───────────────────────────────────────


def test_build_time_calculation():
    """build_start와 build_complete 간의 시간 차이를 올바르게 계산해야 함."""
    start = datetime(2026, 4, 11, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 11, 10, 1, 30, tzinfo=timezone.utc)
    duration = (end - start).total_seconds()
    assert duration == 90.0


def test_build_time_from_metrics_records():
    """JSONL 레코드에서 start/complete 짝을 찾아 duration을 계산."""
    records = SAMPLE_BUILD_METRICS
    # Find matching start/complete pairs
    starts = {r["session_id"]: r for r in records if r["event"] == "build_start"}
    completes = {r["session_id"]: r for r in records if r["event"] == "build_complete"}

    durations = {}
    for sid in starts:
        if sid in completes:
            s = datetime.fromisoformat(starts[sid]["timestamp"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(completes[sid]["timestamp"].replace("Z", "+00:00"))
            durations[sid] = (e - s).total_seconds()

    assert durations["sess-001"] == 90.0
    assert durations["sess-002"] == 45.0


# ── Error category classification ────────────────────────────────

# These patterns mirror what the scaffold skill's circuit breaker analyzes
# when reading build.log output.

ERROR_PATTERNS = {
    "type_error": [
        "Type 'string' is not assignable to type 'number'",
        "error TS2322: Type 'X' is not assignable to type 'Y'",
        "Type error: Property 'foo' does not exist on type 'Bar'",
    ],
    "lint_error": [
        "Error: 'x' is defined but never used (@typescript-eslint/no-unused-vars)",
        "eslint error: Unexpected any. Specify a different type",
        "  12:5  error  'unused' is defined but never used  no-unused-vars",
    ],
    "import_error": [
        "Module not found: Can't resolve '@/components/Button'",
        "Cannot find module '@/lib/utils' or its corresponding type declarations",
        "Error: Cannot find module 'react'",
    ],
    "build_error": [
        "SyntaxError: Unexpected token",
        "Build error occurred",
        "Failed to compile",
        "next build exited with 1",
    ],
}


def _classify_error(error_line: str) -> str:
    """Classify an error line into a category. Mirrors scaffold logic."""
    error_line_lower = error_line.lower()

    if "type" in error_line_lower and ("assignable" in error_line_lower or "ts2" in error_line_lower or "type error" in error_line_lower):
        return "type_error"
    if "eslint" in error_line_lower or "no-unused" in error_line_lower or "error  '" in error_line_lower:
        return "lint_error"
    if "module not found" in error_line_lower or "cannot find module" in error_line_lower or "can't resolve" in error_line_lower:
        return "import_error"
    return "build_error"


def test_error_category_type_error():
    """TypeScript 타입 에러를 type_error로 분류해야 함."""
    for msg in ERROR_PATTERNS["type_error"]:
        assert _classify_error(msg) == "type_error", f"Failed: {msg}"


def test_error_category_lint_error():
    """ESLint 에러를 lint_error로 분류해야 함."""
    for msg in ERROR_PATTERNS["lint_error"]:
        assert _classify_error(msg) == "lint_error", f"Failed: {msg}"


def test_error_category_import_error():
    """Import/resolve 에러를 import_error로 분류해야 함."""
    for msg in ERROR_PATTERNS["import_error"]:
        assert _classify_error(msg) == "import_error", f"Failed: {msg}"


def test_error_category_generic_build_error():
    """분류되지 않는 에러는 build_error로 분류해야 함."""
    for msg in ERROR_PATTERNS["build_error"]:
        assert _classify_error(msg) == "build_error", f"Failed: {msg}"


def test_error_category_empty_string():
    """빈 문자열은 build_error로 분류되어야 함 (기본값)."""
    assert _classify_error("") == "build_error"


# ── Pre-build result format validation ───────────────────────────


def test_pre_build_check_output_format():
    """pre-build-result.json 출력 포맷이 올바른 구조를 가져야 함."""
    result = {
        "status": "pass",
        "checks": {
            "next": {"expected": "14.2.35", "actual": "14.2.35", "match": True},
            "react": {"expected": "18.3.1", "actual": "18.3.1", "match": True},
            "tailwindcss": {"expected": "3.4.19", "actual": "3.4.19", "match": True},
        },
        "mismatches": [],
        "timestamp": "2026-04-11T10:00:00Z",
    }

    # Validate structure
    assert result["status"] in ("pass", "fail")
    assert isinstance(result["checks"], dict)
    assert isinstance(result["mismatches"], list)
    assert "timestamp" in result

    # All checks should have required sub-fields
    for dep, check in result["checks"].items():
        assert "expected" in check
        assert "actual" in check
        assert "match" in check
        assert isinstance(check["match"], bool)


def test_pre_build_check_with_mismatch():
    """버전 불일치가 있으면 status=fail, mismatches에 항목이 있어야 함."""
    result = {
        "status": "fail",
        "checks": {
            "next": {"expected": "14.2.35", "actual": "14.2.35", "match": True},
            "react": {"expected": "18.3.1", "actual": "19.0.0", "match": False},
        },
        "mismatches": [
            {"dependency": "react", "expected": "18.3.1", "actual": "19.0.0"},
        ],
        "timestamp": "2026-04-11T10:00:00Z",
    }

    assert result["status"] == "fail"
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["dependency"] == "react"
    assert result["mismatches"][0]["expected"] == "18.3.1"
    assert result["mismatches"][0]["actual"] == "19.0.0"


def test_pre_build_result_json_serializable():
    """pre-build-result는 JSON 직렬화가 가능해야 함."""
    result = {
        "status": "pass",
        "checks": {
            "next": {"expected": "14.2.35", "actual": "14.2.35", "match": True},
        },
        "mismatches": [],
        "timestamp": "2026-04-11T10:00:00Z",
    }

    serialized = json.dumps(result)
    deserialized = json.loads(serialized)
    assert deserialized == result


# ── Build log line parsing ───────────────────────────────────────


SAMPLE_BUILD_LOG = """\
  ▲ Next.js 14.2.35

   Creating an optimized production build ...

 ✓ Compiled successfully
 ✓ Linting and checking validity of types
 ✓ Collecting page data
 ✓ Generating static pages (5/5)
 ✓ Finalizing page optimization

Route (app)              Size     First Load JS
┌ ○ /                    5.23 kB        89.7 kB
└ ○ /api/hello           0 kB           74.5 kB

 ✓ Build completed in 12s
"""


def test_build_log_success_detection():
    """성공 빌드 로그에서 'Build completed' / exit code 0을 감지해야 함."""
    log_lines = SAMPLE_BUILD_LOG.strip().split("\n")
    success = any("Build completed" in line or "Compiled successfully" in line for line in log_lines)
    assert success is True


def test_build_log_failure_detection():
    """실패 빌드 로그에서 에러를 감지해야 함."""
    failure_log = """\
Type error: Property 'nonExistent' does not object of type 'undefined'.

  > 12 |   return data.nonExistent;
        |          ^^^^

Failed to compile.
"""
    log_lines = failure_log.strip().split("\n")
    has_type_error = any("Type error" in line for line in log_lines)
    has_failed = any("Failed to compile" in line for line in log_lines)
    assert has_type_error is True
    assert has_failed is True


def test_build_log_extracts_duration():
    """빌드 로그에서 소요 시간을 추출해야 함."""
    import re
    log_lines = SAMPLE_BUILD_LOG.strip().split("\n")
    duration = None
    for line in log_lines:
        match = re.search(r"completed in (\d+)s", line)
        if match:
            duration = int(match.group(1))
            break

    assert duration == 12
