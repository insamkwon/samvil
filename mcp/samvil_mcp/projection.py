"""Event projection — reconstruct session state at any point in time (W5.4).

Pattern from ouroboros's query_projection: the events table is already an
append-only stream; this replays it (optionally up to a timestamp) into a
snapshot — "what did the pipeline look like at 14:32?" — for debugging,
retro analysis, and stall forensics.

Read-only sync sqlite3 (WAL allows concurrent readers next to the async
writer). No imports from server.py — keeps the module cycle-free.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def query_projection(
    db_path: str,
    session_id: str,
    at_timestamp: str | None = None,
) -> dict[str, Any]:
    """Replay events for `session_id` up to `at_timestamp` (ISO, inclusive;
    None = all) and return a state snapshot."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        return {"found": False, "error": f"db unavailable: {e}"}

    try:
        con.row_factory = sqlite3.Row
        params: list[Any] = [session_id]
        where = "session_id = ?"
        if at_timestamp:
            where += " AND timestamp <= ?"
            params.append(at_timestamp)
        rows = con.execute(
            f"SELECT event_type, stage, data, timestamp FROM events "
            f"WHERE {where} ORDER BY timestamp ASC",
            params,
        ).fetchall()

        seed_row = None
        try:
            seed_params: list[Any] = [session_id]
            seed_where = "session_id = ?"
            if at_timestamp:
                seed_where += " AND created_at <= ?"
                seed_params.append(at_timestamp)
            seed_row = con.execute(
                f"SELECT version, change_summary, created_at FROM seed_versions "
                f"WHERE {seed_where} ORDER BY version DESC LIMIT 1",
                seed_params,
            ).fetchone()
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()

    if not rows:
        return {"found": False, "session_id": session_id, "event_count": 0}

    stage_timeline: list[dict[str, str]] = []
    counts_by_type: dict[str, int] = {}
    counts_by_stage: dict[str, int] = {}
    failures: list[dict[str, str]] = []

    for row in rows:
        et, stage, ts = row["event_type"], row["stage"], row["timestamp"]
        counts_by_type[et] = counts_by_type.get(et, 0) + 1
        counts_by_stage[stage] = counts_by_stage.get(stage, 0) + 1
        if not stage_timeline or stage_timeline[-1]["stage"] != stage:
            stage_timeline.append({"stage": stage, "entered_at": ts})
        if "fail" in et or "blocked" in et:
            detail = ""
            try:
                detail = str(json.loads(row["data"] or "{}").get("error_signature", ""))
            except (json.JSONDecodeError, TypeError):
                pass
            failures.append({"event_type": et, "stage": stage, "timestamp": ts, "detail": detail})

    last = rows[-1]
    return {
        "found": True,
        "session_id": session_id,
        "as_of": at_timestamp or last["timestamp"],
        "event_count": len(rows),
        "current_stage": last["stage"],
        "last_event": {
            "event_type": last["event_type"],
            "stage": last["stage"],
            "timestamp": last["timestamp"],
        },
        "stage_timeline": stage_timeline,
        "counts_by_type": counts_by_type,
        "counts_by_stage": counts_by_stage,
        "failures": failures[-20:],
        "seed_version_at": (
            {
                "version": seed_row["version"],
                "change_summary": seed_row["change_summary"],
                "created_at": seed_row["created_at"],
            }
            if seed_row
            else None
        ),
    }
