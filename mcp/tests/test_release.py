"""Tests for release readiness reports and gates."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.inspection import build_inspection_report, write_inspection_report
from samvil_mcp.repair import (
    after_inspection_report_path,
    build_repair_plan,
    build_repair_report,
    write_repair_plan,
    write_repair_report,
)
from samvil_mcp.release import (
    build_release_report,
    evaluate_release_gate,
    read_release_report,
    release_summary,
    render_release_report,
    write_release_report,
)


def _checks(status: str = "pass") -> list[dict]:
    return [
        {"name": "phase11_repair_orchestration", "status": status, "command": "phase11"},
        {"name": "phase10_repair_regression", "status": status, "command": "phase10"},
        {"name": "phase8_browser_inspection", "status": status, "command": "phase8"},
        {"name": "pre_commit", "status": status, "command": "pre-commit"},
    ]


def _repair_verified(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "shot.png").write_text("png", encoding="utf-8")
    before = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "release-test",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": ["ReferenceError: broken"],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
        "interactions": [
            {"id": "primary-flow", "status": "pass", "message": "primary flow worked"}
        ],
    })
    after = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "release-test",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
        "interactions": [
            {"id": "primary-flow", "status": "pass", "message": "primary flow worked"}
        ],
    })
    write_inspection_report(before, root)
    after_inspection_report_path(root).write_text(json.dumps(after), encoding="utf-8")
    plan = build_repair_plan(root, inspection_report=before)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_plan(plan, root)
    write_repair_report(report, root)


def test_release_report_normalizes_missing_required_checks(tmp_path):
    report = build_release_report(tmp_path / "project", checks=[{"name": "pre_commit", "status": "pass"}])

    assert report["summary"]["status"] == "blocked"
    assert report["summary"]["passed_checks"] == 1
    assert report["summary"]["missing_checks"] == 3
    assert report["next_action"] == "run release check: phase11_repair_orchestration"


def test_release_gate_blocks_repair_gate_before_release_checks(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "shot.png").write_text("png", encoding="utf-8")
    before = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "blocked-repair",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": ["ReferenceError: broken"],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
    })
    write_inspection_report(before, root)
    release = build_release_report(root, checks=_checks("pass"))

    gate = evaluate_release_gate(root, release_report=release)

    assert gate["verdict"] == "blocked"
    assert gate["reason"] == "repair gate is blocked"
    assert gate["next_action"] == "build repair plan"


def test_release_gate_blocks_failed_release_check_and_passes_all_clear(tmp_path):
    root = tmp_path / "project"
    _repair_verified(root)
    failed = _checks("pass")
    failed[-1]["status"] = "fail"
    failed_report = build_release_report(root, checks=failed)
    pass_report = build_release_report(root, checks=_checks("pass"))

    blocked = evaluate_release_gate(root, release_report=failed_report)
    passed = evaluate_release_gate(root, release_report=pass_report)

    assert blocked["verdict"] == "blocked"
    assert blocked["next_action"] == "fix release check: pre_commit"
    assert passed["verdict"] == "pass"
    assert passed["next_action"] == "ready to tag release"


def test_release_summary_and_render(tmp_path):
    root = tmp_path / "project"
    _repair_verified(root)
    report = build_release_report(root, checks=_checks("pass"))
    path = write_release_report(report, root)

    summary = release_summary(root)
    rendered = render_release_report(read_release_report(root) or {})

    assert path.exists()
    assert summary["report_status"] == "pass"
    assert summary["gate"]["verdict"] == "pass"
    assert "Release Readiness Report" in rendered
    assert "pre_commit" in rendered
