"""Tests for run telemetry reports."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.telemetry import (
    append_retro_observations,
    build_run_report,
    derive_retro_observations,
    read_run_report,
    retro_observation_path,
    render_run_report,
    write_run_report,
)
from samvil_mcp.inspection import build_inspection_report, write_inspection_report
from samvil_mcp.repair import build_repair_plan, build_repair_report, write_repair_plan, write_repair_report
from samvil_mcp.release import build_release_report, write_release_report


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _sample_project(tmp_path: Path) -> Path:
    root = tmp_path / "todo-app"
    samvil = root / ".samvil"
    samvil.mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "session_id": "sess-1",
        "project_name": "todo-app",
        "current_stage": "design",
        "samvil_tier": "minimal",
        "seed_version": 1,
    }), encoding="utf-8")
    (samvil / "next-skill.json").write_text(json.dumps({
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "host": "codex_cli",
        "next_skill": "samvil-design",
        "reason": "minimal tier skips council",
        "from_stage": "seed",
        "created_by": "samvil-seed",
    }), encoding="utf-8")
    _jsonl(samvil / "events.jsonl", [
        {"event_type": "interview_complete", "stage": "seed", "timestamp": "2026-04-26T01:00:00Z"},
        {"event_type": "seed_generated", "stage": "design", "timestamp": "2026-04-26T01:01:00Z"},
    ])
    _jsonl(samvil / "claims.jsonl", [
        {
            "claim_id": "claim_1",
            "type": "gate_verdict",
            "subject": "gate:seed_exit",
            "statement": "verdict=pass via complete_stage",
            "authority_file": "project.state.json",
            "evidence": ["event:seed_generated"],
            "claimed_by": "agent:orchestrator-agent",
            "status": "pending",
            "ts": "2026-04-26T01:01:00Z",
            "meta": {"verdict": "pass", "event_type": "seed_generated"},
        },
        {
            "claim_id": "claim_2",
            "type": "evidence_posted",
            "subject": "stage:design",
            "statement": "design_started",
            "authority_file": "project.state.json",
            "evidence": [],
            "claimed_by": "agent:design",
            "status": "pending",
            "ts": "2026-04-26T01:02:00Z",
            "meta": {},
        },
    ])
    _jsonl(samvil / "mcp-health.jsonl", [
        {"status": "ok", "tool": "stage_can_proceed", "timestamp": "2026-04-26T01:00:00Z"},
        {"status": "fail", "tool": "read_manifest", "error": "missing", "timestamp": "2026-04-26T01:02:00Z"},
    ])
    return root


def test_build_run_report_summarizes_project_files(tmp_path):
    root = _sample_project(tmp_path)

    report = build_run_report(root)

    assert report["schema_version"] == "1.0"
    assert report["state"]["current_stage"] == "design"
    assert report["events"]["total"] == 2
    assert report["claims"]["by_type"]["gate_verdict"] == 1
    assert report["claims"]["pending_subjects"] == ["gate:seed_exit", "stage:design"]
    assert report["mcp_health"]["failures_by_tool"] == {"read_manifest": 1}
    assert report["continuation"]["next_skill"] == "samvil-design"
    assert report["next_action"] == "continue with samvil-design"


def test_write_and_read_run_report_roundtrip(tmp_path):
    root = _sample_project(tmp_path)
    report = build_run_report(root)

    path = write_run_report(report, root)
    read = read_run_report(root)

    assert path == root / ".samvil" / "run-report.json"
    assert read is not None
    assert read["state"]["project_name"] == "todo-app"


def test_render_run_report_includes_operator_summary(tmp_path):
    root = _sample_project(tmp_path)
    report = build_run_report(root)

    text = render_run_report(report)

    assert "# Run Report" in text
    assert "Continuation: seed -> samvil-design" in text
    assert "read_manifest: 1" in text
    assert "Pending Claims" in text


def test_run_report_includes_blocking_repair_gate(tmp_path):
    root = tmp_path / "repair-blocked"
    root.mkdir()
    (root / "shot.png").write_text("png", encoding="utf-8")
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "repair-blocked",
        "current_stage": "qa",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    before = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "repair-blocked",
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
    write_inspection_report(before, root)
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)

    report = build_run_report(root)
    rendered = render_run_report(report)

    assert report["repair"]["gate"]["verdict"] == "blocked"
    assert report["repair"]["gate"]["reason"] == "repair plan exists but repair is not verified"
    assert report["next_action"].startswith("Fix browser console")
    assert "Repair gate: blocked" in rendered


def test_run_report_includes_blocking_release_gate(tmp_path):
    root = tmp_path / "release-blocked"
    root.mkdir()
    (root / "shot.png").write_text("png", encoding="utf-8")
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "release-blocked",
        "current_stage": "qa",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    before = build_inspection_report(root, evidence={
        "schema_version": "1.0",
        "scenario": "release-blocked",
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
        "scenario": "release-blocked",
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
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    repair_report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_report(repair_report, root)
    release_report = build_release_report(root, checks=[
        {"name": "phase11_repair_orchestration", "status": "pass"},
        {"name": "phase10_repair_regression", "status": "pass"},
        {"name": "phase8_browser_inspection", "status": "pass"},
        {"name": "pre_commit", "status": "fail"},
    ])
    write_release_report(release_report, root)

    report = build_run_report(root)
    rendered = render_run_report(report)

    assert report["release"]["gate"]["verdict"] == "blocked"
    assert report["release"]["gate"]["reason"] == "required release checks are failed or missing"
    assert report["next_action"] == "fix release check: pre_commit"
    assert "Release gate: blocked" in rendered


def test_run_report_categorizes_events_and_stage_durations(tmp_path):
    root = tmp_path / "retry-app"
    samvil = root / ".samvil"
    samvil.mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "retry-app",
        "current_stage": "qa",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    _jsonl(samvil / "events.jsonl", [
        {"event_type": "build_feature_start", "stage": "build", "timestamp": "2026-04-26T01:00:00Z"},
        {"event_type": "build_fail", "stage": "build", "timestamp": "2026-04-26T01:02:00Z"},
        {"event_type": "fix_applied", "stage": "build", "timestamp": "2026-04-26T01:03:00Z"},
        {"event_type": "build_stage_complete", "stage": "build", "timestamp": "2026-04-26T01:05:00Z"},
        {"event_type": "qa_started", "stage": "qa", "timestamp": "2026-04-26T01:06:00Z"},
        {"event_type": "qa_blocked", "stage": "qa", "timestamp": "2026-04-26T01:07:00Z"},
    ])

    report = build_run_report(root)
    timeline = report["timeline"]
    by_stage = {stage["stage"]: stage for stage in timeline["stages"]}

    assert timeline["category_counts"]["start"] == 2
    assert timeline["category_counts"]["fail"] == 1
    assert timeline["category_counts"]["retry"] == 1
    assert timeline["category_counts"]["blocked"] == 1
    assert timeline["failure_count"] == 1
    assert timeline["retry_count"] == 1
    assert by_stage["build"]["status"] == "failed"
    assert by_stage["build"]["duration_seconds"] == 300.0
    assert by_stage["qa"]["status"] == "blocked"


def test_install_stage_is_not_blocked_by_stall_substring(tmp_path):
    root = tmp_path / "install-app"
    samvil = root / ".samvil"
    samvil.mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "install-app",
        "current_stage": "install",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    _jsonl(samvil / "events.jsonl", [
        {"event_type": "install_started", "stage": "install", "timestamp": "2026-04-26T01:00:00Z"},
        {"event_type": "install_complete", "stage": "install", "timestamp": "2026-04-26T01:01:00Z"},
        {"event_type": "qa_stall_detected", "stage": "qa", "timestamp": "2026-04-26T01:02:00Z"},
        {"event_type": "deploy_blocked", "stage": "deploy", "timestamp": "2026-04-26T01:03:00Z"},
    ])

    report = build_run_report(root)
    by_stage = {stage["stage"]: stage for stage in report["timeline"]["stages"]}

    assert report["timeline"]["category_counts"]["start"] == 1
    assert report["timeline"]["category_counts"]["complete"] == 1
    assert report["timeline"]["category_counts"]["blocked"] == 2
    assert by_stage["install"]["status"] == "complete"
    assert by_stage["qa"]["status"] == "blocked"
    assert by_stage["deploy"]["status"] == "blocked"


def test_repair_lifecycle_events_are_visible(tmp_path):
    root = tmp_path / "repair-events"
    samvil = root / ".samvil"
    samvil.mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "repair-events",
        "current_stage": "repair",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    _jsonl(samvil / "events.jsonl", [
        {"event_type": "repair_started", "stage": "repair", "timestamp": "2026-04-26T01:00:00Z"},
        {"event_type": "repair_plan_generated", "stage": "repair", "timestamp": "2026-04-26T01:01:00Z"},
        {"event_type": "repair_applied", "stage": "repair", "timestamp": "2026-04-26T01:02:00Z"},
        {"event_type": "repair_verified", "stage": "repair", "timestamp": "2026-04-26T01:03:00Z"},
    ])

    report = build_run_report(root)
    by_stage = {stage["stage"]: stage for stage in report["timeline"]["stages"]}

    assert by_stage["repair"]["status"] == "complete"
    assert by_stage["repair"]["categories"]["complete"] == 2


def test_derive_retro_observations_from_report_findings(tmp_path):
    root = tmp_path / "retro-app"
    samvil = root / ".samvil"
    samvil.mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "project_name": "retro-app",
        "current_stage": "qa",
        "samvil_tier": "standard",
    }), encoding="utf-8")
    _jsonl(samvil / "events.jsonl", [
        {"event_type": "build_feature_start", "stage": "build", "timestamp": "2026-04-26T01:00:00Z"},
        {"event_type": "build_fail", "stage": "build", "timestamp": "2026-04-26T01:02:00Z"},
        {"event_type": "fix_applied", "stage": "build", "timestamp": "2026-04-26T01:03:00Z"},
        {"event_type": "qa_blocked", "stage": "qa", "timestamp": "2026-04-26T01:07:00Z"},
    ])
    _jsonl(samvil / "claims.jsonl", [
        {
            "claim_id": "claim_1",
            "type": "evidence_posted",
            "subject": "stage:qa",
            "statement": "qa blocked",
            "authority_file": "project.state.json",
            "status": "pending",
            "ts": "2026-04-26T01:07:00Z",
        },
    ])
    _jsonl(samvil / "mcp-health.jsonl", [
        {"status": "fail", "tool": "read_manifest", "error": "missing manifest", "timestamp": "2026-04-26T01:02:00Z"},
        {"status": "fail", "tool": "read_manifest", "error": "missing manifest", "timestamp": "2026-04-26T01:03:00Z"},
    ])

    observations = derive_retro_observations(build_run_report(root))
    keys = {obs["dedupe_key"] for obs in observations}

    assert "stage:build:failed" in keys
    assert "stage:qa:blocked" in keys
    assert "retry:build" in keys
    assert "mcp:read_manifest:missing manifest" in keys
    assert "claims:pending" in keys
    assert len(keys) == len(observations)


def test_append_retro_observations_deduplicates_existing_keys(tmp_path):
    root = tmp_path / "retro-log"
    root.mkdir()
    observations = [
        {
            "id": "retro_one",
            "source": "telemetry.timeline",
            "severity": "medium",
            "title": "Build retried",
            "evidence": ["retry_count=1"],
            "suggested_action": "Add a fixture.",
            "dedupe_key": "retry:build",
        },
        {
            "id": "retro_two",
            "source": "telemetry.timeline",
            "severity": "medium",
            "title": "Build retried duplicate",
            "evidence": ["retry_count=1"],
            "suggested_action": "Add a fixture.",
            "dedupe_key": "retry:build",
        },
    ]

    path = append_retro_observations(root, observations)
    append_retro_observations(root, observations)
    rows = [json.loads(line) for line in retro_observation_path(root).read_text(encoding="utf-8").splitlines()]

    assert path == root / ".samvil" / "retro-observations.jsonl"
    assert len(rows) == 1
    assert rows[0]["schema_version"] == "1.0"
    assert rows[0]["dedupe_key"] == "retry:build"


def test_render_run_report_includes_stage_timeline(tmp_path):
    root = _sample_project(tmp_path)
    report = build_run_report(root)

    text = render_run_report(report)

    assert "Stage Timeline" in text
    assert "- design:" in text
