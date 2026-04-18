"""Checkpoint Store (v2.6.0, #07).

Execution state snapshot persistence for crash recovery.
- SHA-256 integrity verification
- 4-level rotation (current + 3 backups)
- Atomic write (tmp → rename)
- Periodic checkpointing support

Aligns with P10 (Reversibility) + INV-5 (Graceful Degradation).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True, slots=True)
class CheckpointData:
    seed_id: str
    phase: str
    state: dict
    timestamp: str
    hash: str

    @classmethod
    def create(cls, seed_id: str, phase: str, state: dict) -> CheckpointData:
        from .security import sanitize_filename
        payload = json.dumps(state, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        return cls(
            seed_id=sanitize_filename(seed_id),
            phase=phase,
            state=state,
            timestamp=datetime.now(timezone.utc).isoformat(),
            hash=h,
        )

    def verify(self) -> bool:
        payload = json.dumps(self.state, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest() == self.hash


class CheckpointStore:
    def __init__(self, base_dir: Path):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, cp: CheckpointData) -> None:
        base_name = f"checkpoint_{cp.seed_id}.json"
        current = self.base / base_name

        # Rotation: .2 → .3, .1 → .2, current → .1
        for level in (3, 2, 1):
            src = self.base / f"{base_name}.{level}"
            dst = self.base / f"{base_name}.{level + 1}"
            if level == 3 and src.exists():
                src.unlink()
                continue
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)

        if current.exists():
            dst = self.base / f"{base_name}.1"
            if dst.exists():
                dst.unlink()
            current.rename(dst)

        # Atomic write
        tmp = current.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "seed_id": cp.seed_id,
            "phase": cp.phase,
            "state": cp.state,
            "timestamp": cp.timestamp,
            "hash": cp.hash,
        }))
        tmp.rename(current)

    def load(self, seed_id: str) -> Optional[CheckpointData]:
        from .security import sanitize_filename
        safe = sanitize_filename(seed_id)
        base_name = f"checkpoint_{safe}.json"

        for suffix in ["", ".1", ".2", ".3"]:
            path = self.base / f"{base_name}{suffix}"
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text())
                cp = CheckpointData(**data)
                if cp.verify():
                    return cp
            except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                continue
        return None

    def list_checkpoints(self) -> list[str]:
        seen = set()
        for f in self.base.glob("checkpoint_*.json"):
            parts = f.stem.split("_", 1)
            if len(parts) == 2:
                seen.add(parts[1])
        return sorted(seen)


class PeriodicCheckpointer:
    """Periodic checkpoint saver for async contexts."""

    def __init__(
        self,
        store: CheckpointStore,
        callback: Callable[[], CheckpointData],
        interval_sec: float = 180,
    ):
        self.store = store
        self.callback = callback
        self.interval = interval_sec
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self, final_save: bool = True) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if final_save:
            try:
                cp = self.callback()
                self.store.save(cp)
            except Exception:
                pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                break
            except asyncio.TimeoutError:
                pass
            try:
                cp = self.callback()
                self.store.save(cp)
            except Exception:
                pass


class RecoveryManager:
    def __init__(self, store: CheckpointStore):
        self.store = store

    def recover(self, seed_id: str) -> Optional[CheckpointData]:
        return self.store.load(seed_id)
