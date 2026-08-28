from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

import samvil_mcp.gate_snapshot as gate_snapshot
from samvil_mcp.gate_snapshot import (
    GateSnapshotError,
    capture_gate_input_snapshot,
    read_json_projection,
    snapshot_sha256,
)


def test_gate_snapshot_binds_content_and_file_generation(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    build_log = samvil / "build.log"
    build_log.write_text("PASS\nSAMVIL_EXIT:0\n", encoding="utf-8")
    (tmp_path / "project.seed.json").write_text(
        json.dumps({"features": []}),
        encoding="utf-8",
    )

    first = capture_gate_input_snapshot(tmp_path, "build_to_qa")
    original_bytes = build_log.read_bytes()
    temporary = samvil / "replacement.log"
    temporary.write_bytes(original_bytes)
    os.replace(temporary, build_log)
    second = capture_gate_input_snapshot(tmp_path, "build_to_qa")

    assert snapshot_sha256(first, ".samvil/build.log") == hashlib.sha256(
        original_bytes
    ).hexdigest()
    assert first[".samvil/build.log"]["sha256"] == second[".samvil/build.log"][
        "sha256"
    ]
    assert first[".samvil/build.log"]["inode"] != second[".samvil/build.log"][
        "inode"
    ]
    assert first != second


def test_gate_snapshot_rejects_symlinked_authority(tmp_path: Path) -> None:
    outside = tmp_path / "outside.log"
    outside.write_text("PASS\n", encoding="utf-8")
    samvil = tmp_path / "project" / ".samvil"
    samvil.mkdir(parents=True)
    (samvil / "build.log").symlink_to(outside)

    with pytest.raises(GateSnapshotError, match="unsafe gate input path"):
        capture_gate_input_snapshot(tmp_path / "project", "build_to_qa")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "failed"}, {"status": "failed"}),
        (["not", "an", "object"], None),
        ("not-an-object", None),
    ],
)
def test_read_json_projection_distinguishes_presence_from_validity(
    tmp_path: Path,
    payload: object,
    expected: dict[str, object] | None,
) -> None:
    path = tmp_path / ".samvil" / "runtime-receipts" / "qa.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    exists, result = read_json_projection(
        tmp_path,
        ".samvil/runtime-receipts/qa.json",
    )

    assert exists is True
    assert result == expected


def test_read_json_projection_reports_absent_and_rejects_symlink(
    tmp_path: Path,
) -> None:
    relative = ".samvil/runtime-receipts/qa.json"
    assert read_json_projection(tmp_path, relative) == (False, None)
    outside = tmp_path / "outside.json"
    outside.write_text('{"status":"passed"}', encoding="utf-8")
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.symlink_to(outside)

    assert read_json_projection(tmp_path, relative) == (True, None)


def test_gate_snapshot_rejects_intermediate_directory_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    samvil = project / ".samvil"
    samvil.mkdir(parents=True)
    (samvil / "build.log").write_text("ORIGINAL\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "build.log").write_text("OUTSIDE\n", encoding="utf-8")
    saved = project / ".samvil-original"
    real_open = os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        target = Path(os.fspath(path)) if not isinstance(path, int) else None
        if not swapped and target == project:
            descriptor = real_open(path, flags, *args, **kwargs)
            samvil.rename(saved)
            samvil.symlink_to(outside, target_is_directory=True)
            swapped = True
            return descriptor
        if not swapped and target == samvil / "build.log":
            samvil.rename(saved)
            samvil.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(gate_snapshot.os, "open", racing_open)

    with pytest.raises(GateSnapshotError, match="unsafe gate input path"):
        capture_gate_input_snapshot(project, "build_to_qa")


def test_runtime_projection_does_not_hide_or_follow_swapped_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    receipts = project / ".samvil" / "runtime-receipts"
    receipts.mkdir(parents=True)
    (receipts / "qa.json").write_text('{"status":"failed"}', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "qa.json").write_text('{"status":"passed"}', encoding="utf-8")
    saved = project / ".samvil-original"
    samvil = project / ".samvil"
    real_open = os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        target = Path(os.fspath(path)) if not isinstance(path, int) else None
        if not swapped and target == project:
            descriptor = real_open(path, flags, *args, **kwargs)
            samvil.rename(saved)
            samvil.symlink_to(outside, target_is_directory=True)
            swapped = True
            return descriptor
        if not swapped and target == receipts / "qa.json":
            samvil.rename(saved)
            samvil.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(gate_snapshot.os, "open", racing_open)

    assert read_json_projection(
        project,
        ".samvil/runtime-receipts/qa.json",
    ) == (True, None)


def test_build_snapshot_declares_every_phase_z_input(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    inputs = {
        ".samvil/build.log": "PASS\n",
        ".samvil/events.jsonl": "{}\n",
        "project.seed.json": "{}",
        "project.state.json": "{}",
        "project.config.json": "{}",
    }
    for relative, contents in inputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    snapshot = capture_gate_input_snapshot(tmp_path, "build_to_qa")

    assert inputs.keys() <= snapshot.keys()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
@pytest.mark.parametrize(
    ("relative", "reader"),
    [
        (
            ".samvil/build.log",
            lambda root: capture_gate_input_snapshot(root, "build_to_qa"),
        ),
        (
            ".samvil/runtime-receipts/qa.json",
            lambda root: read_json_projection(
                root, ".samvil/runtime-receipts/qa.json"
            ),
        ),
    ],
)
def test_gate_snapshot_readers_do_not_block_on_fifo(
    tmp_path: Path,
    relative: str,
    reader: Callable[[Path], object],
) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(target)

    started = threading.Event()
    finished = threading.Event()

    def invoke() -> None:
        started.set()
        try:
            reader(tmp_path)
        except GateSnapshotError:
            pass
        finally:
            finished.set()

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    assert started.wait(1)
    assert finished.wait(1), "reader blocked while opening a FIFO"


def test_gate_snapshot_fails_closed_above_per_file_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "build.log").write_bytes(b"12345")
    monkeypatch.setattr(gate_snapshot, "_MAX_GATE_INPUT_BYTES", 4)

    with pytest.raises(GateSnapshotError, match="exceeds 4 bytes"):
        capture_gate_input_snapshot(tmp_path, "build_to_qa")


def test_oversized_projection_is_present_but_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = tmp_path / ".samvil" / "runtime-receipts" / "qa.json"
    projection.parent.mkdir(parents=True)
    projection.write_bytes(b"12345")
    monkeypatch.setattr(gate_snapshot, "_MAX_PROJECTION_BYTES", 4)

    assert read_json_projection(
        tmp_path,
        ".samvil/runtime-receipts/qa.json",
    ) == (True, None)
    snapshot = capture_gate_input_snapshot(tmp_path, "qa_to_evolve")
    assert snapshot[".samvil/runtime-receipts/qa.json"] == {
        "present": True,
        "valid": False,
    }
