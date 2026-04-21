"""v3.1.0 Sprint 2 — tests for state.json-driven heartbeat (v3-016).

These complement the events.jsonl-based `detect_stall` tests by exercising
the new heartbeat API used by design/council/evolve skills, which don't
emit domain events during their long internal loops.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from samvil_mcp.stall_detector import (
    MAX_STALL_RETRIES,
    STALL_TIMEOUT_SECONDS,
    build_reawake_message,
    heartbeat_state,
    increment_stall_recovery_count,
    is_state_stalled,
)


def _iso(offset_seconds: float = 0.0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def test_heartbeat_creates_state_file_if_missing(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    assert not state_path.exists()

    state = heartbeat_state(str(state_path), now_iso="2026-04-21T12:00:00+00:00")

    assert state_path.exists()
    assert state["last_progress_at"] == "2026-04-21T12:00:00+00:00"
    assert state["stall_recovery_count"] == 0


def test_heartbeat_preserves_other_fields(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    state_path.write_text(
        json.dumps(
            {
                "seed_version": 1,
                "current_stage": "design",
                "stall_recovery_count": 2,
                "other_field": "preserved",
            }
        )
    )

    state = heartbeat_state(str(state_path), now_iso="2026-04-21T12:05:00+00:00")
    assert state["seed_version"] == 1
    assert state["current_stage"] == "design"
    assert state["stall_recovery_count"] == 2  # untouched
    assert state["other_field"] == "preserved"
    assert state["last_progress_at"] == "2026-04-21T12:05:00+00:00"


def test_is_state_stalled_missing_file(tmp_path: Path) -> None:
    verdict = is_state_stalled(str(tmp_path / "missing.json"))
    assert verdict["stalled"] is False
    assert verdict["reason"] == "state_missing"
    assert verdict["last_progress_at"] is None


def test_is_state_stalled_no_heartbeat_yet(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    state_path.write_text('{"current_stage":"design"}')
    verdict = is_state_stalled(str(state_path))
    assert verdict["stalled"] is False
    assert verdict["reason"] == "no_heartbeat_yet"


def test_is_state_stalled_within_threshold(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    heartbeat_state(str(state_path), now_iso="2026-04-21T12:00:00+00:00")
    verdict = is_state_stalled(
        str(state_path),
        now_iso="2026-04-21T12:02:00+00:00",  # 2 min later
        threshold_seconds=300,
    )
    assert verdict["stalled"] is False
    assert verdict["reason"] == "within_threshold"
    assert verdict["elapsed_seconds"] == 120.0


def test_is_state_stalled_threshold_exceeded(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    heartbeat_state(str(state_path), now_iso="2026-04-21T12:00:00+00:00")
    verdict = is_state_stalled(
        str(state_path),
        now_iso="2026-04-21T12:06:00+00:00",  # 6 min later
        threshold_seconds=300,
    )
    assert verdict["stalled"] is True
    assert verdict["reason"] == "threshold_exceeded"
    assert verdict["elapsed_seconds"] == 360.0


def test_increment_stall_recovery_count(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    heartbeat_state(str(state_path), now_iso="2026-04-21T12:00:00+00:00")

    assert increment_stall_recovery_count(str(state_path)) == 1
    assert increment_stall_recovery_count(str(state_path)) == 2
    assert increment_stall_recovery_count(str(state_path)) == 3


def test_build_reawake_message_normal_includes_stage_and_step(tmp_path: Path) -> None:
    detail = {
        "stalled": True,
        "reason": "threshold_exceeded",
        "elapsed_seconds": 320.4,
        "last_progress_at": "2026-04-21T12:00:00+00:00",
        "threshold_seconds": 300,
    }
    msg = build_reawake_message("design", detail, count=0)
    assert "design" in msg
    assert "Step 1" in msg
    assert "320.4s" in msg


def test_build_reawake_message_escalates_after_max_retries() -> None:
    detail = {
        "stalled": True,
        "reason": "threshold_exceeded",
        "elapsed_seconds": 900.0,
        "last_progress_at": "2026-04-21T12:00:00+00:00",
        "threshold_seconds": 300,
    }
    msg = build_reawake_message("council", detail, count=MAX_STALL_RETRIES + 1)
    assert "사용자 개입 필요" in msg


def test_stall_timeout_is_five_minutes_default() -> None:
    # Regression guard — v3-016 spec pins 5 min threshold for design/council/evolve.
    assert STALL_TIMEOUT_SECONDS == 300.0


def test_heartbeat_with_z_suffix_is_parsed(tmp_path: Path) -> None:
    state_path = tmp_path / "project.state.json"
    heartbeat_state(str(state_path), now_iso="2026-04-21T12:00:00Z")
    verdict = is_state_stalled(
        str(state_path),
        now_iso="2026-04-21T12:10:00Z",
        threshold_seconds=300,
    )
    assert verdict["stalled"] is True
