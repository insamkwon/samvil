"""Tests for scripts/samvil-status.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_status_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_status_human_uses_run_report_when_present(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / "project.state.json", {
        "project_name": "proj",
        "current_stage": "seed",
        "samvil_tier": "minimal",
    })
    _write_json(root / ".samvil" / "run-report.json", {
        "generated_at": "2026-04-26T02:00:00Z",
        "state": {
            "project_name": "proj",
            "current_stage": "qa",
            "samvil_tier": "standard",
        },
        "events": {"total": 4},
        "timeline": {
            "failure_count": 1,
            "retry_count": 1,
            "stages": [
                {
                    "stage": "build",
                    "status": "failed",
                    "duration_seconds": 120.0,
                },
            ],
        },
        "claims": {
            "pending_subjects": ["stage:qa"],
            "latest_gate_verdicts": [
                {
                    "subject": "gate:build_exit",
                    "verdict": "fail",
                    "reason": "test failed",
                },
            ],
        },
        "mcp_health": {"failures": 2, "total": 5},
        "continuation": {
            "present": True,
            "from_stage": "qa",
            "next_skill": "samvil-qa",
        },
        "next_action": "resolve gate gate:build_exit (fail)",
    })

    text = status.render_human(root)

    assert "Stage:   qa" in text
    assert "Tier:    standard" in text
    assert "Report:  2026-04-26T02:00:00Z" in text
    assert "gate:build_exit" in text
    assert "Pending claims:    1" in text
    assert "MCP health:      2 failures / 5 events" in text
    assert "Continuation:    qa -> samvil-qa" in text
    assert "Next action:       resolve gate gate:build_exit (fail)" in text


def test_status_json_includes_run_report_summary(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "state.json", {
        "current_stage": "seed",
        "samvil_tier": "minimal",
    })
    _write_json(root / ".samvil" / "run-report.json", {
        "generated_at": "2026-04-26T02:00:00Z",
        "state": {
            "current_stage": "design",
            "samvil_tier": "standard",
        },
        "events": {"total": 2},
        "timeline": {
            "failure_count": 0,
            "retry_count": 1,
            "stages": [{"stage": "design", "status": "complete"}],
        },
        "claims": {"pending_subjects": []},
        "mcp_health": {"failures": 0, "total": 3},
        "continuation": {"present": False},
        "next_action": "continue",
    })
    _write_json(root / ".samvil" / "inspection-report.json", {
        "generated_at": "2026-04-26T03:00:00Z",
        "scenario": "proj",
        "summary": {
            "status": "pass",
            "total_checks": 8,
            "failed_checks": 0,
            "console_errors": 0,
            "screenshots": 2,
        },
    })

    data = json.loads(status.render_json(root))

    assert data["stage"] == "design"
    assert data["samvil_tier"] == "standard"
    assert data["pending_claims_count"] == 0
    assert data["run_report"]["present"] is True
    assert data["run_report"]["events_total"] == 2
    assert data["run_report"]["retry_count"] == 1
    assert data["run_report"]["stage_timeline"][0]["stage"] == "design"
    assert data["inspection_report"]["present"] is True
    assert data["inspection_report"]["status"] == "pass"
    assert data["inspection_report"]["screenshots"] == 2
    assert data["next_recommended_action"] == "continue"


def test_status_human_includes_inspection_report(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / "project.state.json", {
        "project_name": "proj",
        "current_stage": "qa",
        "samvil_tier": "standard",
    })
    _write_json(root / ".samvil" / "inspection-report.json", {
        "generated_at": "2026-04-26T03:00:00Z",
        "scenario": "proj",
        "summary": {
            "status": "pass",
            "passed_checks": 9,
            "failed_checks": 0,
            "warning_checks": 0,
            "viewports": 2,
            "console_errors": 0,
            "screenshots": 2,
        },
    })

    text = status.render_human(root)

    assert "Inspect: pass (9 pass / 0 fail)" in text
    assert "Inspection:" in text
    assert "2 viewports, 0 console errors, 2 screenshots" in text


def test_status_prioritizes_failed_inspection_next_action(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "run-report.json", {
        "state": {"current_stage": "qa", "samvil_tier": "standard"},
        "claims": {"pending_subjects": []},
        "timeline": {},
        "mcp_health": {},
        "next_action": "continue with samvil-build",
    })
    _write_json(root / ".samvil" / "inspection-report.json", {
        "scenario": "proj",
        "summary": {
            "status": "fail",
            "total_checks": 4,
            "failed_checks": 1,
            "console_errors": 1,
            "screenshots": 1,
            "failure_types": ["console-error"],
        },
        "failures": [
            {
                "type": "console-error",
                "check_id": "viewport.desktop.console",
                "repair_hint": "Fix browser console/page errors first.",
            }
        ],
        "next_action": "repair inspection failure: console-error (viewport.desktop.console)",
    })

    data = json.loads(status.render_json(root))
    text = status.render_human(root)

    assert data["next_recommended_action"] == "repair inspection failure: console-error (viewport.desktop.console)"
    assert data["inspection_report"]["failure_types"] == ["console-error"]
    assert "Fix browser console/page errors first." in text
    assert "Next action:       repair inspection failure: console-error" in text


def test_status_json_uses_unknown_stage_fallback(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "run-report.json", {
        "state": {"current_stage": None},
        "claims": {"pending_subjects": []},
        "timeline": {},
        "mcp_health": {},
    })

    data = json.loads(status.render_json(root))

    assert data["stage"] == "?"
