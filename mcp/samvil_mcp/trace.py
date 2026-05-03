"""Execution trace writer — L1 pipeline observability.

Each skill appends structured entries to `.samvil/trace.jsonl`:
    {"ts": "2026-05-03T10:00:00Z", "stage": "build", "action": "leaf_start",
     "skill": "samvil-build", "result": "ok", "details": {}}

Design:
  - Append-only file (never overwrites mid-run).
  - Corrupt lines are skipped on read (INV-5 Graceful Degradation).
  - No locking needed: SAMVIL's single-main-skill assumption means one writer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACE_FILENAME = "trace.jsonl"
SAMVIL_DIR = ".samvil"


def _samvil_dir(project_root: str) -> Path:
    root = Path(project_root) if project_root else Path(".")
    return root / SAMVIL_DIR


def write_trace_entry(
    project_root: str,
    stage: str,
    action: str,
    skill: str,
    result: str = "ok",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one trace entry and return it."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": stage,
        "action": action,
        "skill": skill,
        "result": result,
        "details": details or {},
    }
    d = _samvil_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    trace_path = d / TRACE_FILENAME
    with trace_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_trace(project_root: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the last *limit* trace entries (newest last). Corrupt lines skipped."""
    trace_path = _samvil_dir(project_root) / TRACE_FILENAME
    if not trace_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries[-limit:] if limit > 0 else entries


def clear_trace(project_root: str) -> bool:
    """Remove the trace file. Returns True if it existed, False otherwise."""
    trace_path = _samvil_dir(project_root) / TRACE_FILENAME
    if trace_path.exists():
        trace_path.unlink()
        return True
    return False
