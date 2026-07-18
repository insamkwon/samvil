"""Mechanical build and QA evidence collection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.stage_evidence import collect_stage_evidence


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_uses_last_exit_marker_and_execution_block(tmp_path: Path) -> None:
    _write(
        tmp_path / ".samvil" / "build.log",
        "old warning\nSAMVIL_EXIT:1\ncompiled\nnew warning\nSAMVIL_EXIT:0\n",
    )

    result = collect_stage_evidence(tmp_path, "build")

    assert result["build"] == {
        "exit_code": 0,
        "from": ".samvil/build.log last execution block",
        "typecheck_ok": True,
        "warnings_count": 1,
    }
    assert result["evidence_files"] == [".samvil/build.log"]
    assert result["missing"] == []


def test_qa_parses_playwright_json_report_and_exit_marker(tmp_path: Path) -> None:
    _write(tmp_path / ".samvil" / "qa.log", "playwright output\nSAMVIL_EXIT:0\n")
    _write(
        tmp_path / ".samvil" / "test-results.json",
        json.dumps(
            {
                "stats": {
                    "expected": 7,
                    "unexpected": 2,
                    "flaky": 1,
                    "skipped": 3,
                }
            }
        ),
    )

    result = collect_stage_evidence(tmp_path, "qa")

    assert result["qa"] == {
        "npm_test": {
            "ran": True,
            "exit_code": 0,
            "passed": 8,
            "failed": 2,
            "skipped": 3,
            "from": ".samvil/test-results.json",
        },
        "runtime_verified": True,
        "static_only": False,
    }
    assert result["evidence_files"] == [
        ".samvil/qa.log",
        ".samvil/test-results.json",
    ]
    assert result["missing"] == []


def test_missing_evidence_fails_closed(tmp_path: Path) -> None:
    build = collect_stage_evidence(tmp_path, "build")
    qa = collect_stage_evidence(tmp_path, "qa")

    assert build["build"]["exit_code"] is None
    assert build["build"]["typecheck_ok"] is False
    assert build["missing"] == [".samvil/build.log"]
    assert qa["qa"]["npm_test"]["ran"] is False
    assert qa["qa"]["npm_test"]["exit_code"] is None
    assert qa["qa"]["runtime_verified"] is False
    assert qa["qa"]["static_only"] is True
    assert qa["missing"] == [
        ".samvil/qa.log",
        ".samvil/test-results.json",
    ]


def test_zero_test_report_is_not_runtime_verified(tmp_path: Path) -> None:
    _write(tmp_path / ".samvil" / "qa.log", "SAMVIL_EXIT:0\n")
    _write(
        tmp_path / ".samvil" / "test-results.json",
        json.dumps({"stats": {"expected": 0, "unexpected": 0, "skipped": 0}}),
    )

    result = collect_stage_evidence(tmp_path, "qa")

    assert result["qa"]["npm_test"]["ran"] is True
    assert result["qa"]["runtime_verified"] is False
    assert result["qa"]["static_only"] is True


def test_unknown_stage_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="stage must be build or qa"):
        collect_stage_evidence(tmp_path, "deploy")


def test_mcp_tool_returns_collected_evidence(tmp_path: Path) -> None:
    import asyncio

    from samvil_mcp.server import collect_stage_evidence as collect_tool

    _write(tmp_path / ".samvil" / "build.log", "done\nSAMVIL_EXIT:0\n")

    result = json.loads(asyncio.run(collect_tool(str(tmp_path), "build")))

    assert result["build"]["exit_code"] == 0
    assert result["missing"] == []
