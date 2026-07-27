"""Shared in-process and cross-process serialization for stage transitions."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any

from .claim_ledger import _locked as _file_locked


_PROCESS_LOCKS: dict[str, asyncio.Lock] = {}


def stage_transition_lock_path(store: Any, session_id: str) -> Path:
    """Return one stable lock target for a DB/session pair across processes."""
    db_path = Path(store.db_path).expanduser().resolve()
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return db_path.parent / f".{db_path.name}.stage-transitions" / session_key


@asynccontextmanager
async def stage_transition_lock(store: Any, session_id: str) -> AsyncIterator[None]:
    """Serialize all transition implementations without blocking the event loop."""
    path = stage_transition_lock_path(store, session_id)
    process_lock = _PROCESS_LOCKS.setdefault(str(path), asyncio.Lock())
    async with process_lock:
        context = _file_locked(path)
        await asyncio.to_thread(context.__enter__)
        try:
            yield
        finally:
            await asyncio.to_thread(context.__exit__, None, None, None)
