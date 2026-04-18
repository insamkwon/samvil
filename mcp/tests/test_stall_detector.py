"""Tests for stall_detector.py (v2.6.0, #24)."""

import json
import time

import pytest

from samvil_mcp.stall_detector import (
    MAX_STALL_RETRIES,
    STALL_TIMEOUT_SECONDS,
    StallStatus,
    detect_stall,
)


def test_no_events_file(tmp_path):
    status = detect_stall(str(tmp_path / "nonexistent.jsonl"))
    assert not status.is_stalled
    assert status.should_retry is False


def test_empty_events_file(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text("")
    status = detect_stall(str(p))
    assert not status.is_stalled


def test_recent_event_not_stalled(tmp_path):
    p = tmp_path / "events.jsonl"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps({
        "event_type": "build_feature_start",
        "timestamp": ts,
    }) + "\n")
    status = detect_stall(str(p), timeout=300.0)
    assert not status.is_stalled
    assert status.last_event_type == "build_feature_start"


def test_old_event_is_stalled(tmp_path):
    p = tmp_path / "events.jsonl"
    # 10 minutes ago
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    p.write_text(json.dumps({
        "event_type": "build_feature_start",
        "timestamp": old_ts,
    }) + "\n")
    status = detect_stall(str(p), timeout=300.0)
    assert status.is_stalled
    assert status.should_retry is True  # retry_count=0 < MAX_STALL_RETRIES=2


def test_stalled_max_retries_exceeded(tmp_path):
    p = tmp_path / "events.jsonl"
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    p.write_text(json.dumps({
        "event_type": "build_feature_start",
        "timestamp": old_ts,
    }) + "\n")
    status = detect_stall(str(p), timeout=300.0, retry_count=MAX_STALL_RETRIES)
    assert status.is_stalled
    assert status.should_retry is False  # exceeded


def test_corrupt_event_line_skipped(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text("garbage\n")
    status = detect_stall(str(p))
    assert not status.is_stalled


def test_multiple_events_uses_last(tmp_path):
    p = tmp_path / "events.jsonl"
    old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    recent_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps({"event_type": "old", "timestamp": old_ts}) + "\n")
    p.write_text(json.dumps({"event_type": "recent", "timestamp": recent_ts}) + "\n")
    status = detect_stall(str(p), timeout=300.0)
    assert not status.is_stalled
    assert status.last_event_type == "recent"


def test_constants():
    assert STALL_TIMEOUT_SECONDS == 300.0
    assert MAX_STALL_RETRIES == 2
