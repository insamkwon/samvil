"""MCP wrapper tests for run telemetry."""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.server import (
    append_retro_observations,
    build_run_report,
    derive_retro_observations,
    read_run_report,
    render_run_report,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".samvil").mkdir(parents=True)
    (root / "project.state.json").write_text(json.dumps({
        "session_id": "s1",
        "project_name": "proj",
        "current_stage": "seed",
        "samvil_tier": "minimal",
    }), encoding="utf-8")
    (root / ".samvil" / "next-skill.json").write_text(json.dumps({
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "next_skill": "samvil-design",
        "from_stage": "seed",
        "reason": "minimal tier skips council",
    }), encoding="utf-8")
    return root


def test_build_read_render_run_report_tools(tmp_path):
    root = _project(tmp_path)

    built = build_run_report(str(root), persist=True)
    read = read_run_report(str(root))
    rendered = render_run_report(str(root))

    assert built["status"] == "ok"
    assert Path(built["path"]).exists()
    assert read["status"] == "ok"
    assert rendered["status"] == "ok"
    assert "continue with samvil-design" in rendered["context"]


def test_derive_and_append_retro_observations_tools(tmp_path):
    root = _project(tmp_path)
    (root / ".samvil" / "events.jsonl").write_text(
        json.dumps({
            "event_type": "qa_blocked",
            "stage": "qa",
            "timestamp": "2026-04-26T01:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    build_run_report(str(root), persist=True)

    derived = derive_retro_observations(str(root))
    persisted = derive_retro_observations(str(root), persist=True)
    appended = append_retro_observations(str(root), json.dumps(derived["observations"]))

    assert derived["status"] == "ok"
    assert derived["count"] >= 1
    assert derived["observations"][0]["dedupe_key"] == "stage:qa:blocked"
    assert persisted["status"] == "ok"
    assert Path(persisted["path"]).exists()
    assert appended["status"] == "ok"


def test_read_run_report_missing(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()

    assert read_run_report(str(root)) == {"status": "missing"}


def test_build_run_report_validates_project_root():
    result = build_run_report("", persist=True)

    assert result["status"] == "error"
