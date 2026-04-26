"""Tests for app inspection reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.inspection import (
    build_inspection_report,
    derive_inspection_observations,
    inspection_report_path,
    read_inspection_report,
    render_inspection_report,
    write_inspection_report,
)


def _write_evidence(root: Path, *, console_errors: list[str] | None = None) -> None:
    (root / ".samvil").mkdir(parents=True)
    (root / "artifacts").mkdir()
    (root / "artifacts" / "desktop.png").write_text("png", encoding="utf-8")
    evidence = {
        "schema_version": "1.0",
        "scenario": "inspection-app",
        "url": "http://127.0.0.1:5173/",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": console_errors or [],
                "overflow_count": 0,
                "overflow": [],
                "screenshot": "artifacts/desktop.png",
            }
        ],
        "interactions": [
            {"id": "filter-click", "status": "pass", "message": "filter changed table"}
        ],
    }
    (root / ".samvil" / "inspection-evidence.json").write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )


def test_build_write_read_render_inspection_report(tmp_path):
    root = tmp_path / "project"
    _write_evidence(root)

    report = build_inspection_report(root)
    path = write_inspection_report(report, root)
    read = read_inspection_report(root)
    text = render_inspection_report(report)

    assert path == inspection_report_path(root)
    assert read is not None
    assert report["summary"]["status"] == "pass"
    assert report["summary"]["failed_checks"] == 0
    assert report["summary"]["screenshots"] == 1
    assert "Inspection Report" in text
    assert "filter changed table" in text


def test_inspection_report_fails_on_console_errors(tmp_path):
    root = tmp_path / "project"
    _write_evidence(root, console_errors=["ReferenceError: broken"])

    report = build_inspection_report(root)

    assert report["summary"]["status"] == "fail"
    assert report["summary"]["console_errors"] == 1
    assert report["summary"]["failure_types"] == ["console-error"]
    assert report["failures"][0]["repair_hint"].startswith("Fix browser console")
    assert report["next_action"].startswith("repair inspection failure: console-error")
    assert any(check["id"] == "viewport.desktop.console" for check in report["checks"])


def test_inspection_report_fails_when_evidence_missing(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    report = build_inspection_report(root)

    assert report["summary"]["status"] == "fail"
    assert report["checks"][0]["id"] == "evidence.present"
    assert report["failures"][0]["type"] == "evidence-missing"


def test_inspection_report_classifies_multiple_failure_types(tmp_path):
    root = tmp_path / "project"
    (root / ".samvil").mkdir(parents=True)
    evidence = {
        "schema_version": "1.0",
        "scenario": "broken-app",
        "viewports": [
            {
                "name": "mobile",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 1,
                "overflow": [{"tag": "button", "text": "long label"}],
                "screenshot": "missing.png",
                "canvas_nonblank": False,
            }
        ],
        "interactions": [
            {"id": "restart", "status": "fail", "message": "restart did not reset score"}
        ],
    }
    (root / ".samvil" / "inspection-evidence.json").write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )

    report = build_inspection_report(root)

    assert report["summary"]["status"] == "fail"
    assert report["summary"]["failure_types"] == [
        "canvas-blank",
        "interaction-failed",
        "layout-overflow",
        "screenshot-missing",
    ]
    assert {failure["type"] for failure in report["failures"]} == {
        "layout-overflow",
        "screenshot-missing",
        "canvas-blank",
        "interaction-failed",
    }


def test_derive_inspection_observations_from_failures(tmp_path):
    root = tmp_path / "project"
    _write_evidence(root, console_errors=["ReferenceError: broken"])
    report = build_inspection_report(root)

    observations = derive_inspection_observations(report)

    assert len(observations) == 1
    assert observations[0]["source"] == "inspection.report"
    assert observations[0]["severity"] == "high"
    assert observations[0]["dedupe_key"].startswith("inspection:inspection-app:console-error")
    assert "console" in observations[0]["suggested_action"]
