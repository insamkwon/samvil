"""Tests for retro aggregation DB fallback (#10, v4.30.x)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from samvil_mcp.retro_aggregate import (
    _events_from_db,
    _qa_pass_rate_from_events,
    aggregate_retro_metrics,
)


def test_qa_pass_rate_from_ac_verdict_events() -> None:
    events = [
        {"event_type": "ac_verdict", "data": {"leaf_id": "AC-1", "status": "PASS"}},
        {"event_type": "ac_verdict", "data": {"leaf_id": "AC-2", "status": "FAIL"}},
        # latest verdict per leaf wins
        {"event_type": "ac_verdict", "data": {"leaf_id": "AC-2", "status": "PASS"}},
        {"event_type": "build_pass", "data": {}},
    ]
    assert _qa_pass_rate_from_events(events) == 1.0


def test_qa_pass_rate_none_without_verdicts() -> None:
    assert _qa_pass_rate_from_events([{"event_type": "build_pass", "data": {}}]) is None


def test_events_from_db_missing_db_graceful(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _events_from_db("s1") == []
    assert _events_from_db("") == []


def test_aggregate_falls_back_to_db_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # fake HOME with a session store
    home = tmp_path / "home"
    (home / ".samvil").mkdir(parents=True)
    con = sqlite3.connect(home / ".samvil" / "samvil.db")
    con.execute(
        "CREATE TABLE events (id TEXT, session_id TEXT, event_type TEXT, "
        "stage TEXT, data TEXT, token_count INTEGER, timestamp TEXT)"
    )
    rows = [
        ("e1", "sess-x", "interview_start", "interview", "{}", None, "2026-06-13T01:00:00Z"),
        ("e2", "sess-x", "build_pass", "build", "{}", None, "2026-06-13T01:10:00Z"),
        ("e3", "sess-x", "ac_verdict", "qa", json.dumps({"leaf_id": "AC-1", "status": "PASS"}), None, "2026-06-13T01:20:00Z"),
    ]
    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    monkeypatch.setenv("HOME", str(home))

    # project with NO events.jsonl and no qa-results.json
    proj = tmp_path / "proj"
    (proj / ".samvil").mkdir(parents=True)
    (proj / "project.state.json").write_text(
        json.dumps({"session_id": "sess-x", "current_stage": "retro"})
    )

    result = aggregate_retro_metrics(str(proj))
    flow = result["flow_compliance"]
    assert "interview" in flow.get("actual_sequence", flow.get("sequence", []))
    assert result["metrics"]["qa_pass_rate"] == 1.0
    assert any("#10 fallback" in e for e in result["errors"])
