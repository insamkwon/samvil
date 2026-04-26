"""MCP wrapper tests for release readiness reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.server import (
    build_release_report,
    evaluate_release_gate,
    read_release_report,
    render_release_report,
    run_release_checks,
)


def _checks() -> str:
    return json.dumps([
        {"name": "phase12_release_readiness", "status": "pass", "command": "phase12"},
        {"name": "phase11_repair_orchestration", "status": "pass", "command": "phase11"},
        {"name": "phase10_repair_regression", "status": "pass", "command": "phase10"},
        {"name": "phase8_browser_inspection", "status": "pass", "command": "phase8"},
        {"name": "pre_commit", "status": "fail", "command": "pre-commit"},
    ])


def test_release_report_tools(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    built = build_release_report(str(root), checks_json=_checks(), persist=True)
    read = read_release_report(str(root))
    rendered = render_release_report(str(root))
    gate = evaluate_release_gate(str(root))

    assert built["status"] == "ok"
    assert Path(built["path"]).exists()
    assert built["report"]["summary"]["status"] == "blocked"
    assert read["status"] == "ok"
    assert rendered["status"] == "ok"
    assert "Release Readiness Report" in rendered["context"]
    assert gate["status"] == "ok"
    assert gate["gate"]["verdict"] == "blocked"


def test_release_tools_validate_project_root():
    assert build_release_report("", checks_json="[]", persist=True)["status"] == "error"
    assert read_release_report("")["status"] == "error"
    assert render_release_report("")["status"] == "error"
    assert evaluate_release_gate("")["status"] == "error"
    assert run_release_checks("", commands_json="[]")["status"] == "error"


def test_release_report_rejects_non_list_checks(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    result = build_release_report(str(root), checks_json=json.dumps({"checks": "bad"}))

    assert result["status"] == "error"
    assert "checks_json" in result["error"]


def test_run_release_checks_tool(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    commands = json.dumps([
        {"name": "ok", "command": "python3 -c 'print(\"ok\")'", "timeout_seconds": 5},
    ])

    result = run_release_checks(str(root), commands_json=commands, persist=True)

    assert result["status"] == "ok"
    assert result["report"]["source"] == "runner"
    assert result["report"]["summary"]["status"] == "pass"
    assert result["report"]["checks"][0]["exit_code"] == 0
    assert result["gate"]["verdict"] in {"blocked", "pass", "not-applicable"}
