"""Locked, durable atomic writes for file-backed SAMVIL SSOT artifacts."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from .claim_ledger import _locked


def _fsync_directory(path: Path) -> None:
    """Persist directory metadata after an atomic replacement."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text_unlocked(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write and fsync a temporary sibling, then atomically replace ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with tmp.open("w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Lock ``path`` and perform a durable atomic text replacement."""
    target = Path(path)
    with _locked(target):
        atomic_write_text_unlocked(target, text, encoding=encoding)
