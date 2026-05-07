"""Interview State Persistence (v4.19.0).

Per-Q&A and per-AC-candidate persistence for samvil-interview to give
the interview a structural (not behavioral) recovery guarantee. Replaces
v4.18.0's bash `echo >> interview-progress.json` pattern.

File format: JSONL at ``<project_root>/.samvil/interview-progress.json``.

Three entry types:
    {"type": "qa", "phase": "core", "q": "...", "a": "...", "source": "from-user", "ts": "..."}
    {"type": "ac_candidate", "phase": "core", "ac_text": "...", "ts": "..."}
    {"type": "phase_complete", "phase": "core", "ts": "..."}

Resume-time replay groups ac_candidate entries under their phase using
the most recent phase_complete marker.

Aligns with INV-3 (Interview to file) + INV-5 (Graceful Degradation).
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

try:  # POSIX
    import fcntl  # type: ignore[import-not-found]
    _HAS_FLOCK = True
except ImportError:  # pragma: no cover — Windows fallback
    fcntl = None  # type: ignore[assignment]
    _HAS_FLOCK = False

EntryType = Literal["qa", "ac_candidate", "phase_complete"]

PROGRESS_FILENAME = "interview-progress.json"


def _progress_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".samvil" / PROGRESS_FILENAME


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on a sibling .lock file.

    Falls back to a no-op on Windows (no fcntl). SAMVIL's main skill is
    single-threaded so races are not a practical concern, but workers
    might persist concurrently in future use.
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


def _append_entry(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def persist_answer(
    project_root: str | Path,
    phase: str,
    question: str,
    answer: str,
    source: str = "from-user",
    ac_candidates: list[str] | None = None,
    ts: str | None = None,
) -> dict:
    """Append a Q&A entry (and optionally AC candidates) atomically.

    Returns a dict with ok/error + counts. Best-effort: any exception
    is captured into the result rather than re-raised, so an interview
    is never blocked by persistence failure (INV-5).
    """
    if not phase or not question:
        return {"ok": False, "error": "phase and question are required"}

    timestamp = ts or _now_iso()
    path = _progress_path(project_root)
    counts = {"qa": 0, "ac_candidate": 0}

    try:
        with _locked(path):
            _append_entry(path, {
                "type": "qa",
                "phase": phase,
                "q": question,
                "a": answer,
                "source": source,
                "ts": timestamp,
            })
            counts["qa"] += 1

            for ac_text in (ac_candidates or []):
                if not ac_text or not ac_text.strip():
                    continue
                _append_entry(path, {
                    "type": "ac_candidate",
                    "phase": phase,
                    "ac_text": ac_text.strip(),
                    "ts": timestamp,
                })
                counts["ac_candidate"] += 1

        return {"ok": True, "path": str(path), "counts": counts}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(path)}


def mark_phase_complete(
    project_root: str | Path,
    phase: str,
    ts: str | None = None,
) -> dict:
    """Append a phase_complete marker entry.

    Used at the end of each Phase loop iteration so resume-time replay
    can group AC candidates by completed phase.
    """
    if not phase:
        return {"ok": False, "error": "phase is required"}

    timestamp = ts or _now_iso()
    path = _progress_path(project_root)

    try:
        with _locked(path):
            _append_entry(path, {
                "type": "phase_complete",
                "phase": phase,
                "ts": timestamp,
            })
        return {"ok": True, "path": str(path)}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(path)}


def load_progress(project_root: str | Path) -> dict:
    """Load and group all entries from interview-progress.json.

    Returns:
        {
            "ok": bool,
            "exists": bool,
            "qa_entries": [...],
            "ac_candidates": [...],     # all candidates in order
            "completed_phases": [...],  # phases marked complete
            "ac_by_phase": {phase: [ac_text, ...]},
            "answers_by_phase": {phase: [{q, a, source, ts}, ...]},
        }

    Malformed lines are silently skipped to keep the interview robust.
    """
    path = _progress_path(project_root)
    result: dict = {
        "ok": True,
        "exists": path.exists(),
        "qa_entries": [],
        "ac_candidates": [],
        "completed_phases": [],
        "ac_by_phase": {},
        "answers_by_phase": {},
        "path": str(path),
    }

    if not path.exists():
        return result

    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, PermissionError) as exc:
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        etype = entry.get("type")
        phase = entry.get("phase", "")

        if etype == "qa":
            result["qa_entries"].append(entry)
            if phase:
                result["answers_by_phase"].setdefault(phase, []).append({
                    "q": entry.get("q", ""),
                    "a": entry.get("a", ""),
                    "source": entry.get("source", ""),
                    "ts": entry.get("ts", ""),
                })
        elif etype == "ac_candidate":
            result["ac_candidates"].append(entry)
            if phase:
                ac_text = entry.get("ac_text", "")
                if ac_text:
                    result["ac_by_phase"].setdefault(phase, []).append(ac_text)
        elif etype == "phase_complete":
            if phase and phase not in result["completed_phases"]:
                result["completed_phases"].append(phase)

    return result


def clear_progress(project_root: str | Path) -> dict:
    """Delete interview-progress.json (after summary write completes).

    Best-effort. Returns ok=True when file is gone (whether or not it
    existed to begin with). The interview-summary.md is the authoritative
    record once it has been written.
    """
    path = _progress_path(project_root)
    try:
        if path.exists():
            path.unlink()
        # Also clear the lock file if any
        lock_path = path.with_suffix(path.suffix + ".lock")
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass
        return {"ok": True, "path": str(path)}
    except (OSError, PermissionError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "path": str(path)}
