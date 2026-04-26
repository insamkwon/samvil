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


def test_status_includes_verified_repair_report(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / "project.state.json", {
        "project_name": "proj",
        "current_stage": "qa",
        "samvil_tier": "standard",
    })
    _write_json(root / ".samvil" / "repair-plan.json", {
        "summary": {"status": "ready", "total_actions": 1},
        "actions": [
            {"instruction": "Fix browser console/page errors first."}
        ],
        "next_action": "Fix browser console/page errors first.",
    })
    _write_json(root / ".samvil" / "repair-report.json", {
        "summary": {
            "status": "verified",
            "resolved_failures": 1,
            "remaining_failures": 0,
        },
        "next_action": "repair verified: re-run release checks",
    })

    data = json.loads(status.render_json(root))
    text = status.render_human(root)

    assert data["repair"]["plan_present"] is True
    assert data["repair"]["report_status"] == "verified"
    assert data["repair"]["resolved_failures"] == 1
    assert data["next_recommended_action"] == "repair verified: re-run release checks"
    assert "Repair:  verified (1 resolved / 0 remaining)" in text


def test_status_exposes_run_report_repair_gate(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "run-report.json", {
        "state": {"current_stage": "qa", "samvil_tier": "standard"},
        "claims": {"pending_subjects": []},
        "timeline": {},
        "mcp_health": {},
        "repair": {
            "gate": {
                "verdict": "blocked",
                "reason": "repair plan exists but repair is not verified",
                "next_action": "execute repair plan",
            }
        },
        "next_action": "execute repair plan",
    })

    data = json.loads(status.render_json(root))
    text = status.render_human(root)

    assert data["run_report"]["repair"]["gate"]["verdict"] == "blocked"
    assert "Gate:    repair=blocked" in text
    assert "Repair gate:     blocked - repair plan exists" in text


def test_status_exposes_run_report_release_gate(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "run-report.json", {
        "state": {"current_stage": "qa", "samvil_tier": "standard"},
        "claims": {"pending_subjects": []},
        "timeline": {},
        "mcp_health": {},
        "release": {
            "gate": {
                "verdict": "blocked",
                "reason": "required release checks are failed or missing",
                "next_action": "fix release check: pre_commit",
            }
        },
        "next_action": "fix release check: pre_commit",
    })
    _write_json(root / ".samvil" / "release-report.json", {
        "source": "runner",
        "summary": {
            "status": "blocked",
            "passed_checks": 3,
            "failed_checks": 1,
            "missing_checks": 0,
        },
        "next_action": "fix release check: pre_commit",
    })
    bundle_path = root / ".samvil" / "release-summary.md"
    bundle_path.write_text("# Release Evidence Bundle\n", encoding="utf-8")

    data = json.loads(status.render_json(root))
    text = status.render_human(root)

    assert data["run_report"]["release"]["gate"]["verdict"] == "blocked"
    assert data["release"]["report_status"] == "blocked"
    assert data["release"]["source"] == "runner"
    assert data["release"]["bundle_present"] is True
    assert data["release"]["bundle_path"] == str(bundle_path)
    assert data["next_recommended_action"] == "fix release check: pre_commit"
    assert "Gate:    release=blocked" in text
    assert "Release gate:    blocked - required release checks" in text
    assert f"Release bundle: {bundle_path}" in text


def test_status_exposes_qa_materialization(tmp_path):
    status = _load_status_module()
    root = tmp_path / "proj"
    _write_json(root / ".samvil" / "qa-results.json", {
        "synthesis": {
            "verdict": "REVISE",
            "reason": "functional QA found unimplemented ACs",
            "next_action": "replace stubs or hardcoded paths with real implementation",
            "pass2": {"counts": {"PASS": 1, "PARTIAL": 0, "UNIMPLEMENTED": 1, "FAIL": 0}},
            "pass3": {"verdict": "PASS"},
        }
    })
    (root / ".samvil" / "qa-report.md").write_text("# QA Synthesis\n", encoding="utf-8")

    data = json.loads(status.render_json(root))
    text = status.render_human(root)

    assert data["qa"]["results_present"] is True
    assert data["qa"]["verdict"] == "REVISE"
    assert data["qa"]["pass2_counts"]["UNIMPLEMENTED"] == 1
    assert data["next_recommended_action"] == "replace stubs or hardcoded paths with real implementation"
    assert "QA:      REVISE (P=1 / Pa=0 / U=1 / F=0)" in text
    assert "QA:" in text
    assert "replace stubs or hardcoded paths with real implementation" in text


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
