"""Tests for event projection (v4.30 W5.4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from samvil_mcp.projection import query_projection

_SCHEMA = """
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    data TEXT DEFAULT '{}',
    token_count INTEGER DEFAULT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE seed_versions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    seed_json TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = tmp_path / "samvil.db"
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    events = [
        ("e1", "s1", "interview_start", "interview", "{}", "2026-06-12T10:00:00Z"),
        ("e2", "s1", "seed_started", "seed", "{}", "2026-06-12T10:10:00Z"),
        ("e3", "s1", "build_feature_start", "build", "{}", "2026-06-12T10:20:00Z"),
        ("e4", "s1", "build_fail", "build", '{"error_signature": "TS2304"}', "2026-06-12T10:25:00Z"),
        ("e5", "s1", "build_pass", "build", "{}", "2026-06-12T10:30:00Z"),
        ("e6", "s1", "qa_started", "qa", "{}", "2026-06-12T10:40:00Z"),
        ("e7", "s2", "interview_start", "interview", "{}", "2026-06-12T11:00:00Z"),
    ]
    con.executemany(
        "INSERT INTO events (id, session_id, event_type, stage, data, timestamp) VALUES (?,?,?,?,?,?)",
        events,
    )
    con.execute(
        "INSERT INTO seed_versions (id, session_id, version, seed_json, change_summary, created_at) "
        "VALUES ('v1', 's1', 1, '{}', 'initial', '2026-06-12T10:09:00Z')"
    )
    con.commit()
    con.close()
    return str(path)


def test_full_replay(db: str) -> None:
    snap = query_projection(db, "s1")
    assert snap["found"] is True
    assert snap["event_count"] == 6
    assert snap["current_stage"] == "qa"
    assert [s["stage"] for s in snap["stage_timeline"]] == [
        "interview",
        "seed",
        "build",
        "qa",
    ]
    assert snap["counts_by_type"]["build_fail"] == 1
    assert snap["failures"][0]["detail"] == "TS2304"
    assert snap["seed_version_at"]["version"] == 1


def test_point_in_time_replay(db: str) -> None:
    """State as of 10:25 — mid-build, before QA."""
    snap = query_projection(db, "s1", at_timestamp="2026-06-12T10:25:00Z")
    assert snap["event_count"] == 4
    assert snap["current_stage"] == "build"
    assert snap["last_event"]["event_type"] == "build_fail"


def test_session_isolation(db: str) -> None:
    snap = query_projection(db, "s2")
    assert snap["event_count"] == 1
    assert snap["current_stage"] == "interview"


def test_unknown_session(db: str) -> None:
    snap = query_projection(db, "nope")
    assert snap["found"] is False
    assert snap["event_count"] == 0


def test_missing_db_graceful(tmp_path: Path) -> None:
    snap = query_projection(str(tmp_path / "absent.db"), "s1")
    assert snap["found"] is False
    assert "db unavailable" in snap["error"]
