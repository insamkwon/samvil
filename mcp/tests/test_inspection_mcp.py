"""MCP wrapper tests for app inspection reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.server import (
    build_inspection_report,
    read_inspection_report,
    render_inspection_report,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".samvil").mkdir(parents=True)
    (root / "shot.png").write_text("png", encoding="utf-8")
    (root / ".samvil" / "inspection-evidence.json").write_text(
        json.dumps({
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
        }),
        encoding="utf-8",
    )
    return root


def test_build_read_render_inspection_report_tools(tmp_path):
    root = _project(tmp_path)

    built = build_inspection_report(str(root), persist=True)
    read = read_inspection_report(str(root))
    rendered = render_inspection_report(str(root))

    assert built["status"] == "ok"
    assert Path(built["path"]).exists()
    assert built["report"]["summary"]["status"] == "pass"
    assert read["status"] == "ok"
    assert rendered["status"] == "ok"
    assert "primary flow worked" in rendered["context"]


def test_read_inspection_report_missing(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()

    assert read_inspection_report(str(root)) == {"status": "missing"}


def test_build_inspection_report_validates_project_root():
    result = build_inspection_report("", persist=True)

    assert result["status"] == "error"
