"""Crash-safety regressions for durable SAMVIL SSOT writers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from samvil_mcp.chain_markers import write_chain_marker
from samvil_mcp.checkpoint import CheckpointData, CheckpointStore
from samvil_mcp.resume import write_leaf_checkpoint
from samvil_mcp.self_correction import (
    accumulate_failed_acs,
    load_failed_acs_for_wonder,
    record_qa_failure,
)
from samvil_mcp.stall_detector import heartbeat_state, increment_stall_recovery_count


def _forbid_direct_final_write(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    original = Path.write_text

    def guarded(path: Path, *args, **kwargs):
        if path == target:
            raise AssertionError(f"direct SSOT write: {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded)


def test_atomic_write_preserves_original_when_replace_fails(tmp_path, monkeypatch) -> None:
    from samvil_mcp.ssot_io import atomic_write_text

    target = tmp_path / "state.json"
    target.write_text('{"current_stage":"build"}', encoding="utf-8")

    def crash_before_replace(_src, _dst):
        raise OSError("simulated crash before replace")

    monkeypatch.setattr(os, "replace", crash_before_replace)

    with pytest.raises(OSError, match="simulated crash"):
        atomic_write_text(target, '{"current_stage":"qa"}')

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "current_stage": "build"
    }
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_stall_state_writers_never_write_final_path_directly(tmp_path, monkeypatch) -> None:
    path = tmp_path / "project.state.json"
    path.write_text('{"current_stage":"build"}', encoding="utf-8")
    _forbid_direct_final_write(monkeypatch, path)

    heartbeat_state(str(path), now_iso="2026-07-18T00:00:00Z")
    assert increment_stall_recovery_count(str(path)) == 1


def test_chain_marker_writer_never_writes_final_path_directly(tmp_path, monkeypatch) -> None:
    target = tmp_path / ".samvil" / "next-skill.json"
    _forbid_direct_final_write(monkeypatch, target)

    write_chain_marker(str(tmp_path), "codex_cli", "samvil-build")

    assert json.loads(target.read_text(encoding="utf-8"))["next_skill"] == "samvil-qa"


def test_self_correction_writers_never_write_final_path_directly(tmp_path, monkeypatch) -> None:
    qa_path = tmp_path / ".samvil" / "qa-failures.json"
    failed_path = tmp_path / ".samvil" / "failed_acs.json"
    _forbid_direct_final_write(monkeypatch, qa_path)

    record_qa_failure(str(tmp_path), "AC-1", "desc", 1, "reason")

    _forbid_direct_final_write(monkeypatch, failed_path)
    accumulate_failed_acs(str(tmp_path), [{"ac_id": "AC-1", "cycle": 1}])


def test_self_correction_backs_up_corrupt_accumulator(tmp_path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    path = samvil / "failed_acs.json"
    path.write_text('{"partial":', encoding="utf-8")

    result = accumulate_failed_acs(
        str(tmp_path), [{"ac_id": "AC-2", "cycle": 2, "reason": "retry"}]
    )

    assert result["total_accumulated"] == 1
    backups = list(samvil.glob("failed_acs.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == '{"partial":'


def test_self_correction_backs_up_schema_invalid_accumulator(tmp_path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    path = samvil / "failed_acs.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")

    result = accumulate_failed_acs(
        str(tmp_path), [{"ac_id": "AC-2", "cycle": 2, "reason": "retry"}]
    )

    assert result["total_accumulated"] == 1
    backups = list(samvil.glob("failed_acs.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == '{"not": "a list"}'


def test_failed_ac_reader_backs_up_and_reinitializes_corrupt_file(tmp_path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    path = samvil / "failed_acs.json"
    path.write_text('[{"partial"', encoding="utf-8")

    assert load_failed_acs_for_wonder(str(tmp_path)) == []

    assert json.loads(path.read_text(encoding="utf-8")) == []
    assert len(list(samvil.glob("failed_acs.json.corrupt-*"))) == 1


def test_checkpoint_save_fsyncs_before_replace(tmp_path, monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    store = CheckpointStore(tmp_path)

    store.save(CheckpointData.create("seed", "build", {"step": 1}))

    assert calls


def test_leaf_checkpoint_writer_never_writes_final_path_directly(tmp_path, monkeypatch) -> None:
    target = tmp_path / ".samvil" / "leaf-checkpoint.json"
    _forbid_direct_final_write(monkeypatch, target)

    write_leaf_checkpoint(str(tmp_path), "feature", "AC-1")

    assert json.loads(target.read_text(encoding="utf-8"))["leaf_id"] == "AC-1"
