"""Shared API Rate Budget (v3.0.0, T3).

File-based cooperative budget tracker. Not a strict semaphore — the goal is to
give the main skill a cheap way to see current concurrency across all Agent
workers so it can throttle the next spawn. SAMVIL's dispatch is single-threaded
(one main skill), so race conditions are not a concern in practice.

Events live in `.samvil/rate-budget.jsonl`:
    {"ts": 1712345678.1, "worker_id": "w1", "kind": "acquire"}
    {"ts": 1712345679.2, "worker_id": "w1", "kind": "release"}

Stats are computed by replaying the log.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

try:  # POSIX
    import fcntl  # type: ignore[import-not-found]
    _HAS_FLOCK = True
except ImportError:  # pragma: no cover — Windows fallback
    fcntl = None  # type: ignore[assignment]
    _HAS_FLOCK = False

Kind = Literal["acquire", "release"]


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on a sibling `.lock` file.

    Falls back to a no-op on platforms without fcntl (Windows) — in that
    environment SAMVIL's single main-skill assumption already prevents races.
    """
    if not _HAS_FLOCK:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _append_locked(path: Path, kind: Kind, worker_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(),
            "worker_id": worker_id,
            "kind": kind,
        }) + "\n")


def _replay(path: Path) -> tuple[set[str], list[dict]]:
    """Return (active_workers, all_events). Caller holds the file lock."""
    events: list[dict] = []
    if not path.exists():
        return set(), events
    active: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(ev)
        wid = ev.get("worker_id")
        kind = ev.get("kind")
        if not wid:
            continue
        if kind == "acquire":
            active.add(wid)
        elif kind == "release":
            active.discard(wid)
    return active, events


def acquire(budget_path: str, worker_id: str, max_concurrent: int) -> dict:
    """Try to claim a slot under an exclusive file lock."""
    p = Path(budget_path)
    with _locked(p):
        active, _ = _replay(p)
        if worker_id in active:
            return {
                "acquired": True,
                "current": len(active),
                "max_concurrent": max_concurrent,
                "note": "already held",
            }
        if len(active) >= max_concurrent:
            return {
                "acquired": False,
                "current": len(active),
                "max_concurrent": max_concurrent,
                "note": "budget exhausted",
            }
        _append_locked(p, "acquire", worker_id)
        return {
            "acquired": True,
            "current": len(active) + 1,
            "max_concurrent": max_concurrent,
        }


def release(budget_path: str, worker_id: str) -> dict:
    """Append a `release` event under the file lock. Idempotent."""
    p = Path(budget_path)
    with _locked(p):
        active, _ = _replay(p)
        if worker_id not in active:
            return {"released": False, "current": len(active), "note": "not held"}
        _append_locked(p, "release", worker_id)
        return {"released": True, "current": len(active) - 1}


def stats(budget_path: str) -> dict:
    """Return {active, peak, total_acquired, total_released, active_workers}."""
    p = Path(budget_path)
    with _locked(p):
        active, events = _replay(p)
        peak = 0
        running = 0
        total_acq = 0
        total_rel = 0
        for ev in events:
            if ev.get("kind") == "acquire":
                running += 1
                total_acq += 1
                peak = max(peak, running)
            elif ev.get("kind") == "release":
                running = max(0, running - 1)
                total_rel += 1
        return {
            "active": len(active),
            "peak": peak,
            "total_acquired": total_acq,
            "total_released": total_rel,
            "active_workers": sorted(active),
        }


def reset(budget_path: str) -> dict:
    """Truncate the budget log. Returns stats before reset."""
    p = Path(budget_path)
    before = stats(budget_path)
    with _locked(p):
        if p.exists():
            p.unlink()
    return {"reset": True, "previous": before}
