"""Tests for inspection repair plans and reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.inspection import build_inspection_report, write_inspection_report
from samvil_mcp.repair import (
    after_inspection_report_path,
    build_repair_plan,
    build_repair_report,
    derive_repair_policy_signals,
    evaluate_repair_gate,
    read_repair_plan,
    read_repair_report,
    render_repair_plan,
    render_repair_report,
    repair_summary,
    repair_plan_path,
    repair_report_path,
    write_repair_plan,
    write_repair_report,
)


def _evidence(*, broken: bool) -> dict:
    viewport = {
        "name": "desktop",
        "loaded": True,
        "console_errors": ["ReferenceError: broken"] if broken else [],
        "overflow_count": 1 if broken else 0,
        "overflow": [{"tag": "button", "text": "overflow"}] if broken else [],
        "screenshot": "shot.png",
    }
    interaction = {
        "id": "primary-flow",
        "status": "fail" if broken else "pass",
        "message": "primary flow failed" if broken else "primary flow worked",
    }
    return {
        "schema_version": "1.0",
        "scenario": "repair-app",
        "viewports": [viewport],
        "interactions": [interaction],
    }


def _reports(root: Path) -> tuple[dict, dict]:
    root.mkdir()
    (root / "shot.png").write_text("png", encoding="utf-8")
    before = build_inspection_report(root, evidence=_evidence(broken=True))
    after = build_inspection_report(root, evidence=_evidence(broken=False))
    write_inspection_report(before, root)
    after_inspection_report_path(root).write_text(json.dumps(after), encoding="utf-8")
    return before, after


def test_build_write_read_render_repair_plan(tmp_path):
    root = tmp_path / "project"
    before, _after = _reports(root)

    plan = build_repair_plan(root, inspection_report=before)
    path = write_repair_plan(plan, root)
    read = read_repair_plan(root)
    text = render_repair_plan(plan)

    assert path == repair_plan_path(root)
    assert read is not None
    assert plan["summary"]["status"] == "ready"
    assert plan["summary"]["total_actions"] == 3
    assert plan["actions"][0]["status"] == "pending"
    assert "Repair Plan" in text
    assert "ReferenceError" not in text


def test_build_write_read_render_verified_repair_report(tmp_path):
    root = tmp_path / "project"
    before, after = _reports(root)
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)

    report = build_repair_report(root, before_report=before, after_report=after, plan=plan)
    path = write_repair_report(report, root)
    read = read_repair_report(root)
    text = render_repair_report(report)

    assert path == repair_report_path(root)
    assert read is not None
    assert report["summary"]["status"] == "verified"
    assert report["summary"]["before_failed_checks"] == 3
    assert report["summary"]["after_failed_checks"] == 0
    assert report["summary"]["resolved_failures"] == 3
    assert all(action["status"] == "verified" for action in report["actions"])
    assert "repair verified" in report["next_action"]
    assert "Repair Report" in text


def test_repair_report_keeps_remaining_failures(tmp_path):
    root = tmp_path / "project"
    before, _after = _reports(root)
    plan = build_repair_plan(root, inspection_report=before)

    report = build_repair_report(root, before_report=before, after_report=before, plan=plan)

    assert report["summary"]["status"] == "failed"
    assert report["summary"]["remaining_failures"] == 3
    assert report["next_action"].startswith("continue repair:")


def test_repair_gate_blocks_missing_repair_plan(tmp_path):
    root = tmp_path / "project"
    before, _after = _reports(root)

    gate = evaluate_repair_gate(root, inspection_report=before)

    assert gate["verdict"] == "blocked"
    assert gate["reason"] == "inspection failed but no repair plan exists"
    assert gate["next_action"] == "build repair plan"


def test_repair_gate_blocks_unverified_plan_and_passes_verified_report(tmp_path):
    root = tmp_path / "project"
    before, after = _reports(root)
    plan = build_repair_plan(root, inspection_report=before)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)

    blocked = evaluate_repair_gate(root, inspection_report=before, repair_plan=plan)
    passed = evaluate_repair_gate(root, inspection_report=before, repair_plan=plan, repair_report=report)

    assert blocked["verdict"] == "blocked"
    assert blocked["reason"] == "repair plan exists but repair is not verified"
    assert passed["verdict"] == "pass"
    assert passed["next_action"] == "continue to release checks"


def test_repair_summary_includes_gate(tmp_path):
    root = tmp_path / "project"
    before, after = _reports(root)
    plan = build_repair_plan(root, inspection_report=before)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_plan(plan, root)
    write_repair_report(report, root)

    summary = repair_summary(root)

    assert summary["inspection_status"] == "fail"
    assert summary["plan_actions"] == 3
    assert summary["report_status"] == "verified"
    assert summary["gate"]["verdict"] == "pass"


def test_derive_repair_policy_signals_for_repeated_failure_types(tmp_path):
    root = tmp_path / "project"
    before, after = _reports(root)
    plan = build_repair_plan(root, inspection_report=before)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    other = {**report, "scenario": "repair-app-2"}

    signals = derive_repair_policy_signals([report, other], threshold=2)

    keys = {signal["dedupe_key"] for signal in signals}
    assert "repair-policy:console-error" in keys
    assert "repair-policy:layout-overflow" in keys
    assert "repair-policy:interaction-failed" in keys
