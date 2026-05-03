"""Tests for trace module — L1 execution observability."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from samvil_mcp.trace import (
    write_trace_entry,
    read_trace,
    clear_trace,
    TRACE_FILENAME,
    SAMVIL_DIR,
)


@pytest.fixture
def project_root(tmp_path):
    return str(tmp_path)


class TestWriteTraceEntry:
    def test_creates_samvil_dir(self, project_root):
        d = Path(project_root) / SAMVIL_DIR
        assert not d.exists()
        write_trace_entry(project_root, "build", "leaf_start", "samvil-build")
        assert d.exists()

    def test_creates_trace_file(self, project_root):
        write_trace_entry(project_root, "build", "leaf_start", "samvil-build")
        trace = Path(project_root) / SAMVIL_DIR / TRACE_FILENAME
        assert trace.exists()

    def test_returns_entry_dict(self, project_root):
        entry = write_trace_entry(project_root, "qa", "pass3_done", "samvil-qa", result="pass")
        assert entry["stage"] == "qa"
        assert entry["action"] == "pass3_done"
        assert entry["skill"] == "samvil-qa"
        assert entry["result"] == "pass"
        assert "ts" in entry
        assert "details" in entry

    def test_default_result_is_ok(self, project_root):
        entry = write_trace_entry(project_root, "build", "start", "samvil-build")
        assert entry["result"] == "ok"

    def test_details_stored(self, project_root):
        entry = write_trace_entry(
            project_root, "build", "leaf_start", "samvil-build",
            details={"leaf_id": "ac_1_2", "feature_id": "feat_auth"}
        )
        assert entry["details"]["leaf_id"] == "ac_1_2"

    def test_appends_multiple_entries(self, project_root):
        write_trace_entry(project_root, "build", "start", "samvil-build")
        write_trace_entry(project_root, "build", "leaf_done", "samvil-build")
        entries = read_trace(project_root)
        assert len(entries) == 2

    def test_ts_is_iso_format(self, project_root):
        entry = write_trace_entry(project_root, "build", "start", "samvil-build")
        ts = entry["ts"]
        assert "T" in ts
        assert ts.endswith("Z")

    def test_empty_details_default(self, project_root):
        entry = write_trace_entry(project_root, "qa", "start", "samvil-qa")
        assert entry["details"] == {}


class TestReadTrace:
    def test_empty_when_no_file(self, project_root):
        assert read_trace(project_root) == []

    def test_returns_entries_in_order(self, project_root):
        write_trace_entry(project_root, "build", "start", "samvil-build")
        write_trace_entry(project_root, "build", "end", "samvil-build")
        entries = read_trace(project_root)
        assert entries[0]["action"] == "start"
        assert entries[1]["action"] == "end"

    def test_limit_returns_last_n(self, project_root):
        for i in range(10):
            write_trace_entry(project_root, "build", f"action_{i}", "samvil-build")
        entries = read_trace(project_root, limit=3)
        assert len(entries) == 3
        assert entries[-1]["action"] == "action_9"

    def test_corrupt_lines_skipped(self, project_root):
        trace_path = Path(project_root) / SAMVIL_DIR / TRACE_FILENAME
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text('{"stage":"build","action":"ok"}\nnot-json-at-all\n{"stage":"qa","action":"done"}\n')
        entries = read_trace(project_root)
        assert len(entries) == 2
        assert entries[0]["stage"] == "build"
        assert entries[1]["stage"] == "qa"

    def test_limit_zero_returns_all(self, project_root):
        for i in range(5):
            write_trace_entry(project_root, "build", f"a{i}", "samvil-build")
        entries = read_trace(project_root, limit=0)
        assert len(entries) == 5


class TestClearTrace:
    def test_returns_true_when_file_exists(self, project_root):
        write_trace_entry(project_root, "build", "start", "samvil-build")
        assert clear_trace(project_root) is True

    def test_removes_file(self, project_root):
        write_trace_entry(project_root, "build", "start", "samvil-build")
        clear_trace(project_root)
        assert read_trace(project_root) == []

    def test_returns_false_when_no_file(self, project_root):
        assert clear_trace(project_root) is False
