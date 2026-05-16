"""Tests for event_store_reader module (v4.24.0).

Covers:
- read_events happy path / missing file / malformed lines
- read_state happy path / missing / malformed JSON
- list_in_flight_sessions: in-flight detection, terminal exclusion
- format_in_flight_text shape
- Korean content preserved
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.event_store_reader import (
    IN_FLIGHT_STAGES,
    format_in_flight_text,
    list_in_flight_sessions,
    read_events,
    read_state,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def _seed_events(project_root: Path, entries: list[dict]) -> Path:
    samvil = project_root / ".samvil"
    samvil.mkdir(exist_ok=True)
    path = samvil / "events.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def _seed_state(project_root: Path, state: dict) -> Path:
    path = project_root / "project.state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


# ── read_events ─────────────────────────────────────────────


def test_read_events_missing_file(project_root: Path) -> None:
    result = read_events(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["entries"] == []


def test_read_events_happy(project_root: Path) -> None:
    _seed_events(project_root, [
        {"session_id": "s1", "event_type": "interview_start", "stage": "interview",
         "timestamp": "2026-05-16T10:00:00Z"},
        {"session_id": "s1", "event_type": "interview_complete", "stage": "seed",
         "timestamp": "2026-05-16T10:30:00Z"},
        {"session_id": "s2", "event_type": "build_start", "stage": "build",
         "timestamp": "2026-05-16T11:00:00Z"},
    ])
    result = read_events(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["entries"]) == 3
    assert "s1" in result["by_session"]
    assert "s2" in result["by_session"]
    assert "interview" in result["by_stage"]
    assert "seed" in result["by_stage"]
    assert result["first_ts"] == "2026-05-16T10:00:00Z"
    assert result["last_ts"] == "2026-05-16T11:00:00Z"


def test_read_events_skips_malformed(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / "events.jsonl").write_text(
        '{"session_id": "s1", "event_type": "interview_start", "stage": "interview"}\n'
        'not json\n'
        '"just a string"\n'
        '{"session_id": "s2", "event_type": "build_start", "stage": "build"}\n',
        encoding="utf-8",
    )
    result = read_events(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["entries"]) == 2


def test_read_events_korean(project_root: Path) -> None:
    _seed_events(project_root, [
        {"session_id": "s1", "event_type": "interview_start", "stage": "interview",
         "data": {"note": "한국어 인터뷰 시작"}},
    ])
    result = read_events(project_root=str(project_root))
    assert result["entries"][0]["data"]["note"] == "한국어 인터뷰 시작"


# ── read_state ──────────────────────────────────────────────


def test_read_state_missing(project_root: Path) -> None:
    result = read_state(project_root=str(project_root))
    assert result["ok"] is False
    assert result["exists"] is False


def test_read_state_happy(project_root: Path) -> None:
    _seed_state(project_root, {"current_stage": "build", "session_id": "abc"})
    result = read_state(project_root=str(project_root))
    assert result["ok"] is True
    assert result["state"]["current_stage"] == "build"


def test_read_state_malformed(project_root: Path) -> None:
    (project_root / "project.state.json").write_text("not json", encoding="utf-8")
    result = read_state(project_root=str(project_root))
    assert result["ok"] is False
    assert "error" in result


def test_read_state_non_object(project_root: Path) -> None:
    (project_root / "project.state.json").write_text('"just a string"', encoding="utf-8")
    result = read_state(project_root=str(project_root))
    assert result["ok"] is False


# ── list_in_flight_sessions ─────────────────────────────────


def test_list_no_events(project_root: Path) -> None:
    result = list_in_flight_sessions(project_root=str(project_root))
    assert result["ok"] is True
    assert result["in_flight_sessions"] == []
    assert "never ran" in result["notes"][0]


def test_list_in_flight_detected(project_root: Path) -> None:
    _seed_events(project_root, [
        {"session_id": "s1", "event_type": "interview_start", "stage": "interview",
         "timestamp": "2026-05-16T10:00:00Z"},
        {"session_id": "s1", "event_type": "build_start", "stage": "build",
         "timestamp": "2026-05-16T11:00:00Z"},
    ])
    _seed_state(project_root, {"current_stage": "build", "session_id": "s1"})
    result = list_in_flight_sessions(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["in_flight_sessions"]) == 1
    s = result["in_flight_sessions"][0]
    assert s["session_id"] == "s1"
    assert s["current_stage"] == "build"
    assert s["event_count"] == 2
    assert "interview" in s["stages_touched"]
    assert "build" in s["stages_touched"]


def test_list_terminal_session_excluded(project_root: Path) -> None:
    """A session whose last event is retro_complete should NOT be in-flight."""
    _seed_events(project_root, [
        {"session_id": "s_done", "event_type": "interview_start", "stage": "interview",
         "timestamp": "2026-05-16T10:00:00Z"},
        {"session_id": "s_done", "event_type": "retro_complete", "stage": "retro",
         "timestamp": "2026-05-16T11:00:00Z"},
    ])
    result = list_in_flight_sessions(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["in_flight_sessions"]) == 0


def test_list_multiple_sessions_sorted(project_root: Path) -> None:
    """Multiple in-flight sessions sorted by last_ts descending."""
    _seed_events(project_root, [
        {"session_id": "s_old", "event_type": "build_start", "stage": "build",
         "timestamp": "2026-05-16T08:00:00Z"},
        {"session_id": "s_new", "event_type": "interview_start", "stage": "interview",
         "timestamp": "2026-05-16T12:00:00Z"},
    ])
    result = list_in_flight_sessions(project_root=str(project_root))
    assert len(result["in_flight_sessions"]) == 2
    assert result["in_flight_sessions"][0]["session_id"] == "s_new"
    assert result["in_flight_sessions"][1]["session_id"] == "s_old"


def test_in_flight_stages_constants_sanity() -> None:
    """Sanity: IN_FLIGHT_STAGES doesn't include terminal stages."""
    assert "interview" in IN_FLIGHT_STAGES
    assert "build" in IN_FLIGHT_STAGES
    assert "complete" not in IN_FLIGHT_STAGES
    assert "retro" not in IN_FLIGHT_STAGES


# ── format_in_flight_text ───────────────────────────────────


def test_format_text_no_events(project_root: Path) -> None:
    result = list_in_flight_sessions(project_root=str(project_root))
    text = format_in_flight_text(result)
    assert "No events.jsonl" in text
    assert "/samvil" in text


def test_format_text_with_sessions(project_root: Path) -> None:
    _seed_events(project_root, [
        {"session_id": "abc123", "event_type": "build_start", "stage": "build",
         "timestamp": "2026-05-16T10:00:00Z"},
    ])
    _seed_state(project_root, {"current_stage": "build"})
    result = list_in_flight_sessions(project_root=str(project_root))
    text = format_in_flight_text(result)
    assert "abc123" in text
    assert "current_stage=build" in text
    assert "samvil-resume" in text
