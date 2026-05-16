"""Active Pain Capture (v4.22.0).

Per-stage user pain signal collection. Closes the gap where SAMVIL's
retro could only see *build/mechanical* failures and missed the
*semantic* pain (e.g. "seed didn't match what I said", "had to manually
edit constraints"). Without this signal, samvil-retro can only suggest
incremental improvements; with it, retro can detect systematic gaps.

File format: JSONL at ``<project_root>/.samvil/pain-feedback.jsonl``.

Entry shape:
    {
      "stage": "interview" | "seed" | "scaffold" | "build" | "qa" | "deploy" | "retro",
      "severity": 1..5,        # 1=다 좋아 ... 5=재작업 필요
      "pain_text": "<text>",   # optional, mandatory when severity >= 4
      "session_id": "<id>",    # optional
      "ts": "ISO-8601"
    }

Aligns with INV-3 (file SSOT) + INV-5 (Graceful Degradation).
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:  # POSIX
    import fcntl  # type: ignore[import-not-found]
    _HAS_FLOCK = True
except ImportError:  # pragma: no cover — Windows fallback
    fcntl = None  # type: ignore[assignment]
    _HAS_FLOCK = False

FEEDBACK_FILENAME = "pain-feedback.jsonl"

VALID_STAGES = frozenset({
    "interview", "seed", "council", "design", "scaffold",
    "build", "qa", "deploy", "retro", "evolve",
})


def _feedback_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".samvil" / FEEDBACK_FILENAME


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Exclusive advisory lock on sibling .lock file (no-op on Windows)."""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_pain(
    project_root: str | Path,
    stage: str,
    severity: int,
    pain_text: str = "",
    session_id: str = "",
    ts: str | None = None,
) -> dict:
    """Append a single pain-feedback entry. Best-effort.

    Returns ``{ok, path, severity, pain_required_but_missing?}``. Never
    raises — file errors are captured into the result so the pipeline
    is never blocked.
    """
    if stage not in VALID_STAGES:
        return {"ok": False, "error": f"invalid stage: {stage}", "valid_stages": sorted(VALID_STAGES)}
    try:
        sev = int(severity)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"severity must be int 1..5, got {severity!r}"}
    if not (1 <= sev <= 5):
        return {"ok": False, "error": f"severity must be in 1..5, got {sev}"}

    # severity >= 4 should carry pain_text — we still accept the write, but
    # report the requirement so the caller can ask a follow-up.
    pain_required_but_missing = (sev >= 4 and not pain_text.strip())

    timestamp = ts or _now_iso()
    path = _feedback_path(project_root)
    entry = {
        "stage": stage,
        "severity": sev,
        "pain_text": pain_text.strip(),
        "session_id": session_id,
        "ts": timestamp,
    }

    try:
        with _locked(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {
            "ok": True,
            "path": str(path),
            "severity": sev,
            "pain_required_but_missing": pain_required_but_missing,
        }
    except (OSError, PermissionError) as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "path": str(path),
        }


def load_pain_feedback(project_root: str | Path) -> dict:
    """Load all pain entries with summary aggregations.

    Returns:
        {
          "ok": bool,
          "exists": bool,
          "entries": [...],
          "by_stage": {stage: [entries]},
          "by_severity": {1..5: count},
          "severity_avg": float (overall),
          "high_severity_count": int (>= 4),
          "high_severity_texts": [pain_text, ...] (entries with sev >= 4),
          "path": "...",
        }

    Malformed lines and unknown stages are silently skipped.
    """
    path = _feedback_path(project_root)
    result: dict = {
        "ok": True,
        "exists": path.exists(),
        "entries": [],
        "by_stage": {},
        "by_severity": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        "severity_avg": 0.0,
        "high_severity_count": 0,
        "high_severity_texts": [],
        "path": str(path),
    }

    if not path.exists():
        return result

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, PermissionError) as exc:
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    sev_total = 0
    count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        stage = entry.get("stage", "")
        sev = entry.get("severity")
        if stage not in VALID_STAGES or not isinstance(sev, int) or not (1 <= sev <= 5):
            continue

        result["entries"].append(entry)
        result["by_stage"].setdefault(stage, []).append(entry)
        result["by_severity"][sev] += 1
        sev_total += sev
        count += 1
        if sev >= 4:
            result["high_severity_count"] += 1
            txt = entry.get("pain_text", "")
            if txt:
                result["high_severity_texts"].append(txt)

    if count > 0:
        result["severity_avg"] = round(sev_total / count, 2)

    return result
