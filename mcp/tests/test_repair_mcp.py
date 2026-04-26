"""MCP wrapper tests for inspection repair plans and reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.inspection import build_inspection_report, write_inspection_report
from samvil_mcp.repair import after_inspection_report_path
from samvil_mcp.server import (
    build_repair_plan,
    build_repair_report,
    read_repair_plan,
    read_repair_report,
    render_repair_plan,
    render_repair_report,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "shot.png").write_text("png", encoding="utf-8")
    before = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "proj",
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
        "scenario": "proj",
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
    return root


def test_repair_plan_and_report_tools(tmp_path):
    root = _project(tmp_path)

    plan = build_repair_plan(str(root), persist=True)
    read_plan = read_repair_plan(str(root))
    rendered_plan = render_repair_plan(str(root))
    report = build_repair_report(str(root), persist=True)
    read_report = read_repair_report(str(root))
    rendered_report = render_repair_report(str(root))

    assert plan["status"] == "ok"
    assert Path(plan["path"]).exists()
    assert read_plan["status"] == "ok"
    assert rendered_plan["status"] == "ok"
    assert report["status"] == "ok"
    assert report["report"]["summary"]["status"] == "verified"
    assert Path(report["path"]).exists()
    assert read_report["status"] == "ok"
    assert rendered_report["status"] == "ok"
    assert "repair verified" in rendered_report["context"]


def test_repair_tools_validate_project_root():
    assert build_repair_plan("", persist=True)["status"] == "error"
    assert build_repair_report("", persist=True)["status"] == "error"
