"""Stable, no-follow snapshots for files that authorize stage gates."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .runtime_layout import RuntimeLayoutError, safe_child_directory


_MAX_GATE_INPUT_BYTES = 10_000_000
_MAX_PROJECTION_BYTES = 2_000_000
_HAS_OPENAT = os.open in getattr(os, "supports_dir_fd", set())


_GATE_INPUT_PATHS: dict[str, tuple[str, ...]] = {
    "build_to_qa": (
        ".samvil/build.log",
        ".samvil/mechanical.toml",
        ".samvil/runtime-receipts/build.json",
        "project.seed.json",
        "project.state.json",
        "project.config.json",
        ".samvil/events.jsonl",
        ".samvil/gate_config.yaml",
        "gate_config.yaml",
    ),
    "qa_to_evolve": (
        ".samvil/qa.log",
        ".samvil/mechanical.toml",
        ".samvil/runtime-receipts/qa.json",
        ".samvil/qa-results.json",
        ".samvil/test-results.json",
        ".samvil/gate_config.yaml",
        "gate_config.yaml",
    ),
    "qa_to_deploy": (
        ".samvil/qa.log",
        ".samvil/mechanical.toml",
        ".samvil/runtime-receipts/qa.json",
        ".samvil/qa-results.json",
        ".samvil/test-results.json",
        ".samvil/gate_config.yaml",
        "gate_config.yaml",
    ),
    "any_to_retro": (
        ".samvil/qa.log",
        ".samvil/runtime-receipts/qa.json",
        ".samvil/qa-results.json",
        ".samvil/gate_config.yaml",
        "gate_config.yaml",
    ),
}


class GateSnapshotError(RuntimeLayoutError):
    """Raised when a gate input cannot be captured without a race or escape."""


@dataclass(frozen=True)
class GateInputBundle:
    """Immutable bytes plus the filesystem generation that supplied them."""

    snapshot: dict[str, dict[str, Any]]
    contents: dict[str, bytes | None]


def gate_input_paths(gate_name: str) -> tuple[str, ...]:
    """Return the project-relative files that can change one gate verdict."""
    return _GATE_INPUT_PATHS.get(gate_name, ())


def _gate_input_limit(relative: str) -> int:
    """Keep projected receipts within their stricter parsing boundary."""
    if relative.startswith(".samvil/runtime-receipts/"):
        return _MAX_PROJECTION_BYTES
    return _MAX_GATE_INPUT_BYTES


def _missing_snapshot() -> dict[str, Any]:
    return {"present": False}


def _validate_relative_path(root: Path, relative: str, *, label: str) -> Path:
    relative_path = Path(relative)
    if (
        root == Path(root.anchor)
        or relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise GateSnapshotError(f"unsafe {label} path: {relative_path}")
    return relative_path


def _parent_was_present(root: Path, relative_path: Path, *, label: str) -> bool:
    """Record whether the parent existed before descriptor traversal began."""
    cursor = root
    for part in relative_path.parts[:-1]:
        cursor = cursor / part
        try:
            metadata = os.lstat(cursor)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise GateSnapshotError(f"unsafe {label} path: {relative_path}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise GateSnapshotError(f"unsafe {label} path: {cursor}")
    return True


def _open_regular_file_at(
    root: Path,
    relative: str,
    *,
    label: str,
) -> tuple[int | None, bool]:
    """Open a regular-file candidate without following any path component."""
    relative_path = _validate_relative_path(root, relative, label=label)
    parent_present = _parent_was_present(root, relative_path, label=label)
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    if not _HAS_OPENAT:  # pragma: no cover - Windows compatibility fallback
        try:
            target = safe_child_directory(root, relative_path, label=label)
        except RuntimeLayoutError as exc:
            raise GateSnapshotError(str(exc)) from exc
        try:
            return os.open(target, file_flags), False
        except FileNotFoundError:
            return None, False
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return None, False
            raise GateSnapshotError(f"unsafe {label} path: {relative}") from exc

    directories: list[int] = []
    try:
        try:
            current = os.open(root, directory_flags)
        except OSError as exc:
            raise GateSnapshotError(f"unsafe {label} owner root: {root}") from exc
        directories.append(current)
        for part in relative_path.parts[:-1]:
            try:
                current = os.open(part, directory_flags, dir_fd=current)
            except FileNotFoundError:
                return None, parent_present
            except OSError as exc:
                raise GateSnapshotError(f"unsafe {label} path: {relative}") from exc
            directories.append(current)
        try:
            return os.open(relative_path.name, file_flags, dir_fd=current), False
        except FileNotFoundError:
            return None, False
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return None, False
            raise GateSnapshotError(f"unsafe {label} path: {relative}") from exc
    finally:
        for descriptor in reversed(directories):
            os.close(descriptor)


def _read_regular_file(
    root: Path,
    relative: str,
    *,
    label: str,
    limit: int,
    retain_content: bool = True,
) -> tuple[dict[str, Any], bytes | None]:
    descriptor, parent_missing = _open_regular_file_at(root, relative, label=label)
    if descriptor is None:
        if parent_missing:
            raise GateSnapshotError(f"{label} parent disappeared: {relative}")
        confirmation, confirmation_parent_missing = _open_regular_file_at(
            root,
            relative,
            label=label,
        )
        if confirmation is not None:
            os.close(confirmation)
            raise GateSnapshotError(f"{label} changed while reading: {relative}")
        if confirmation_parent_missing:
            raise GateSnapshotError(f"{label} parent disappeared: {relative}")
        return _missing_snapshot(), None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise GateSnapshotError(f"{label} is not a regular file: {relative}")
        if before.st_size > limit:
            raise GateSnapshotError(f"{label} exceeds {limit} bytes: {relative}")
        digest = hashlib.sha256()
        chunks: list[bytes] | None = [] if retain_content else None
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise GateSnapshotError(f"{label} exceeds {limit} bytes: {relative}")
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise GateSnapshotError(f"{label} changed while reading: {relative}")
    return (
        {
            "present": True,
            "sha256": digest.hexdigest(),
            "size": after.st_size,
            "device": after.st_dev,
            "inode": after.st_ino,
            "mtime_ns": after.st_mtime_ns,
            "ctime_ns": after.st_ctime_ns,
        },
        b"".join(chunks) if chunks is not None else None,
    )


def capture_gate_input_bundle(
    project_root: str | Path,
    gate_name: str,
) -> GateInputBundle:
    """Capture the exact bytes later consumed by one gate evaluation."""
    root = Path(project_root).expanduser().resolve(strict=False)
    snapshot: dict[str, dict[str, Any]] = {}
    contents: dict[str, bytes | None] = {}
    for relative in gate_input_paths(gate_name):
        try:
            item, data = _read_regular_file(
                root,
                relative,
                label="gate input",
                limit=_gate_input_limit(relative),
            )
        except GateSnapshotError:
            if not relative.startswith(".samvil/runtime-receipts/"):
                raise
            item, data = {"present": True, "valid": False}, None
        snapshot[relative] = item
        contents[relative] = data
    return GateInputBundle(snapshot=snapshot, contents=contents)


def capture_gate_input_snapshot(
    project_root: str | Path,
    gate_name: str,
) -> dict[str, dict[str, Any]]:
    """Capture a generation without retaining a second full content bundle."""
    root = Path(project_root).expanduser().resolve(strict=False)
    snapshot: dict[str, dict[str, Any]] = {}
    for relative in gate_input_paths(gate_name):
        try:
            item, _data = _read_regular_file(
                root,
                relative,
                label="gate input",
                limit=_gate_input_limit(relative),
                retain_content=False,
            )
        except GateSnapshotError:
            if not relative.startswith(".samvil/runtime-receipts/"):
                raise
            item = {"present": True, "valid": False}
        snapshot[relative] = item
    return snapshot


@contextmanager
def materialized_gate_input_bundle(bundle: GateInputBundle) -> Iterator[Path]:
    """Expose captured bytes to legacy evidence readers through a private root."""
    with tempfile.TemporaryDirectory(prefix="samvil-gate-inputs-") as temporary:
        root = Path(temporary)
        for relative, data in bundle.contents.items():
            if data is None:
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        yield root


def snapshot_sha256(
    snapshot: dict[str, dict[str, Any]],
    relative: str,
) -> str:
    """Return a captured file digest, or an empty value for an absent file."""
    item = snapshot.get(relative)
    if not isinstance(item, dict) or item.get("present") is not True:
        return ""
    return str(item.get("sha256") or "")


def json_projection_from_bundle(
    bundle: GateInputBundle,
    relative: str,
) -> tuple[bool, dict[str, Any] | None]:
    """Decode a projected JSON object from the exact captured generation."""
    data = bundle.contents.get(relative)
    if data is None:
        item = bundle.snapshot.get(relative) or {}
        return bool(item.get("present")), None
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return True, None
    return True, parsed if isinstance(parsed, dict) else None


def read_json_projection(
    project_root: str | Path,
    relative: str,
) -> tuple[bool, dict[str, Any] | None]:
    """Read one projected JSON object through the same no-follow boundary."""
    root = Path(project_root).expanduser().resolve(strict=False)
    try:
        item, data = _read_regular_file(
            root,
            relative,
            label="runtime receipt",
            limit=_MAX_PROJECTION_BYTES,
        )
    except GateSnapshotError:
        return True, None
    if item.get("present") is not True or data is None:
        return False, None
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return True, None
    return True, parsed if isinstance(parsed, dict) else None


__all__ = [
    "GateInputBundle",
    "GateSnapshotError",
    "capture_gate_input_bundle",
    "capture_gate_input_snapshot",
    "gate_input_paths",
    "json_projection_from_bundle",
    "materialized_gate_input_bundle",
    "read_json_projection",
    "snapshot_sha256",
]
