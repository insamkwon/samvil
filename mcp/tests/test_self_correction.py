"""Tests for self_correction.py (v2.5.0, Phase 4)."""

import json
from pathlib import Path

import pytest

from samvil_mcp.self_correction import (
    record_qa_failure,
    accumulate_failed_acs,
    load_failed_acs_for_wonder,
    summarize_for_wonder,
)


def test_record_qa_failure_creates_file(tmp_path):
    result = record_qa_failure(
        project_path=str(tmp_path),
        ac_id="AC-1",
        ac_description="test AC",
        cycle=1,
        reason="stub detected",
        suggestions=["implement real logic"],
    )
    assert result["total_failures"] == 1
    failures_path = Path(result["path"])
    assert failures_path.exists()
    data = json.loads(failures_path.read_text())
    assert len(data) == 1
    assert data[0]["ac_id"] == "AC-1"
    assert data[0]["suggestions"] == ["implement real logic"]


def test_record_multiple_failures_append(tmp_path):
    record_qa_failure(str(tmp_path), "AC-1", "x", 1, "reason 1")
    result = record_qa_failure(str(tmp_path), "AC-2", "y", 1, "reason 2")
    assert result["total_failures"] == 2


def test_accumulate_failed_acs(tmp_path):
    failures = [
        {"ac_id": "AC-1", "cycle": 1, "reason": "r1"},
        {"ac_id": "AC-2", "cycle": 1, "reason": "r2"},
    ]
    result = accumulate_failed_acs(str(tmp_path), failures)
    assert result["total_accumulated"] == 2

    # Add more from another cycle
    more = [{"ac_id": "AC-1", "cycle": 2, "reason": "r1 again"}]
    result = accumulate_failed_acs(str(tmp_path), more)
    assert result["total_accumulated"] == 3


def test_load_failed_acs_empty(tmp_path):
    failures = load_failed_acs_for_wonder(str(tmp_path))
    assert failures == []


def test_load_failed_acs_sorted(tmp_path):
    accumulate_failed_acs(str(tmp_path), [
        {"ac_id": "AC-1", "cycle": 1, "reason": "r1"},
        {"ac_id": "AC-2", "cycle": 3, "reason": "r2"},
        {"ac_id": "AC-3", "cycle": 2, "reason": "r3"},
    ])
    failures = load_failed_acs_for_wonder(str(tmp_path))
    # Sorted by cycle desc
    assert failures[0]["cycle"] == 3
    assert failures[-1]["cycle"] == 1


def test_summarize_empty():
    summary = summarize_for_wonder([])
    assert "No prior failures" in summary


def test_summarize_with_recurring():
    failures = [
        {"ac_id": "AC-1", "cycle": 1, "reason": "stub"},
        {"ac_id": "AC-1", "cycle": 2, "reason": "still stub"},
        {"ac_id": "AC-2", "cycle": 1, "reason": "missing"},
    ]
    summary = summarize_for_wonder(failures)
    assert "Recurring Failures" in summary
    assert "AC-1" in summary
    assert "One-off Failures" in summary or "AC-2" in summary


def test_summarize_includes_wonder_questions():
    failures = [{"ac_id": "AC-1", "cycle": 1, "reason": "r"}]
    summary = summarize_for_wonder(failures)
    assert "Wonder Questions" in summary
