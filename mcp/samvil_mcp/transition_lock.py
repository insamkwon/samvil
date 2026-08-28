"""Shared in-process and cross-process serialization for stage transitions."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any

from .claim_ledger import _HAS_FLOCK as _HAS_INTERPROCESS_LOCK
from .claim_ledger import _locked as _file_locked


_PROCESS_LOCKS: dict[str, asyncio.Lock] = {}


class InterprocessLockUnavailable(RuntimeError):
    """Raised instead of silently weakening a cross-process state lock."""


def stage_transition_lock_path(store: Any, session_id: str) -> Path:
    """Return one stable lock target for a DB/session pair across processes."""
    db_path = Path(store.db_path).expanduser().resolve()
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return db_path.parent / f".{db_path.name}.stage-transitions" / session_key


def verification_execution_lock_path(
    store: Any,
    session_id: str,
    stage: str,
) -> Path:
    """Return a stable lock target for one session/stage verification stream."""
    db_path = Path(store.db_path).expanduser().resolve()
    normalized_stage = stage if stage.startswith("samvil-") else f"samvil-{stage}"
    key = hashlib.sha256(
        f"{session_id}\x00{normalized_stage}".encode("utf-8")
    ).hexdigest()
    return db_path.parent / f".{db_path.name}.verification-executions" / key


async def _acquire_file_lock(context: Any) -> None:
    """Acquire a blocking flock without leaving a cancelled waiter behind."""
    acquisition = asyncio.create_task(asyncio.to_thread(context.__enter__))
    cancelled = False
    while True:
        try:
            await asyncio.shield(acquisition)
            break
        except asyncio.CancelledError:
            cancelled = True
            continue
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        await _release_file_lock(context)
        raise asyncio.CancelledError


async def _release_file_lock(context: Any) -> None:
    """Complete unlock even when cancellation arrives during cleanup."""
    release = asyncio.create_task(
        asyncio.to_thread(context.__exit__, None, None, None)
    )
    cancelled = False
    while True:
        try:
            await asyncio.shield(release)
            break
        except asyncio.CancelledError:
            cancelled = True
            continue
    await release
    if cancelled:
        raise asyncio.CancelledError


@asynccontextmanager
async def _shared_lock(path: Path) -> AsyncIterator[None]:
    if not _HAS_INTERPROCESS_LOCK:
        raise InterprocessLockUnavailable(
            "interprocess file locking is unavailable on this platform"
        )
    process_lock = _PROCESS_LOCKS.setdefault(str(path), asyncio.Lock())
    async with process_lock:
        context = _file_locked(path)
        await _acquire_file_lock(context)
        try:
            yield
        finally:
            await _release_file_lock(context)


@asynccontextmanager
async def stage_transition_lock(store: Any, session_id: str) -> AsyncIterator[None]:
    """Serialize all transition implementations without blocking the event loop."""
    async with _shared_lock(stage_transition_lock_path(store, session_id)):
        yield


@asynccontextmanager
async def verification_execution_lock(
    store: Any,
    session_id: str,
    stage: str,
) -> AsyncIterator[None]:
    """Serialize same-session/stage verification commands across MCP processes."""
    async with _shared_lock(
        verification_execution_lock_path(store, session_id, stage)
    ):
        yield
