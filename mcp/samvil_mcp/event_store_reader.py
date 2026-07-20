"""MCP-free EventStore reader (v4.24.0).

samvil-resume traditionally depends on MCP to surface in-flight sessions.
When MCP is down (network glitch, server restart, plugin reload), the
user is stranded — recovery requires reviving MCP first. v4.24 closes
that gap by reading the file-based SSOT (``.samvil/events.jsonl`` +
``project.state.json``) directly with no MCP dependency.

This module is invoked via the CLI:

    python -m samvil_mcp.event_store_reader --project=. --list-sessions
    python -m samvil_mcp.event_store_reader --project=. --session=<id>

It is also a clean Python API for any tool that wants to inspect a
project's session history without going through MCP.

Aligns with INV-1 (File is SSOT), INV-5 (Graceful Degradation), and
W7 (Recovery requires MCP — eliminated).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVENTS_FILENAME = "events.jsonl"
STATE_FILENAME = "project.state.json"
SAMVIL_DIR = ".samvil"

# Stages considered "in-flight" (not terminal). Aligned with state-schema
# enum minus 'complete' and 'retro' (retro is terminal per samvil-retro
# Chain "No chain — retro is terminal").
IN_FLIGHT_STAGES = frozenset({
    "interview", "seed", "council", "design",
    "scaffold", "build", "qa", "deploy", "evolve",
})


def _project_paths(project_root: str | Path) -> tuple[Path, Path]:
    root = Path(project_root)
    return (
        root / SAMVIL_DIR / EVENTS_FILENAME,
        root / STATE_FILENAME,
    )


def _event_timestamp(entry: dict) -> str:
    """Read the canonical timestamp while accepting legacy ``ts`` rows."""
    value = entry.get("timestamp")
    if value is None or value == "":
        value = entry.get("ts")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def read_events(project_root: str | Path) -> dict:
    """Read `.samvil/events.jsonl` and return entries + summary.

    Returns:
        {
            "ok": bool,
            "exists": bool,
            "entries": [...],
            "by_stage": {stage: [entries]},
            "by_session": {session_id: [entries]},
            "first_ts": "ISO" | None,
            "last_ts": "ISO" | None,
            "path": "...",
        }

    Malformed lines are silently skipped. The reader never raises —
    file errors are captured into the result so the caller can decide
    how to surface them.
    """
    events_path, _ = _project_paths(project_root)
    result: dict = {
        "ok": True,
        "exists": events_path.exists(),
        "entries": [],
        "by_stage": {},
        "by_session": {},
        "first_ts": None,
        "last_ts": None,
        "path": str(events_path),
    }
    if not events_path.exists():
        return result
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except (OSError, PermissionError) as exc:
        return {**result, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        result["entries"].append(entry)

        stage = entry.get("stage", "")
        if stage:
            result["by_stage"].setdefault(stage, []).append(entry)
        session_id = entry.get("session_id", "")
        if session_id:
            result["by_session"].setdefault(session_id, []).append(entry)

    if result["entries"]:
        timestamps = [timestamp for e in result["entries"] if (timestamp := _event_timestamp(e))]
        if timestamps:
            timestamps.sort()
            result["first_ts"] = timestamps[0]
            result["last_ts"] = timestamps[-1]

    return result


def read_state(project_root: str | Path) -> dict:
    """Read project.state.json. Returns the parsed dict or {ok: False, error}."""
    _, state_path = _project_paths(project_root)
    if not state_path.exists():
        return {"ok": False, "exists": False, "path": str(state_path)}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "exists": True, "error": "state file is not a JSON object"}
        return {"ok": True, "exists": True, "state": data, "path": str(state_path)}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {
            "ok": False, "exists": True,
            "error": f"{type(exc).__name__}: {exc}",
            "path": str(state_path),
        }


def list_in_flight_sessions(project_root: str | Path) -> dict:
    """Return active sessions from events + state, MCP-free.

    A session is "in-flight" if:
      - it appears in events.jsonl, AND
      - its current_stage (from state.json) is in IN_FLIGHT_STAGES, AND
      - no `*_complete` terminal event is its latest entry, OR
        the latest entry is not in {complete, retro}.

    Output:
        {
            "ok": bool,
            "in_flight_sessions": [
                {
                    "session_id": "...",
                    "current_stage": "...",
                    "last_event_type": "...",
                    "last_event_ts": "...",
                    "event_count": N,
                    "stages_touched": [...],
                }, ...
            ],
            "current_stage": "...",  # from state.json (single project)
            "events_summary": {...},
            "state_summary": {...},
            "notes": [...],
        }
    """
    events = read_events(project_root)
    state = read_state(project_root)
    notes: list[str] = []

    if not events["ok"]:
        return {"ok": False, "error": events.get("error", "events read failed"), "notes": notes}
    if not events["exists"]:
        return {
            "ok": True,
            "in_flight_sessions": [],
            "current_stage": None,
            "events_summary": {"exists": False, "entries": 0},
            "state_summary": {"exists": state["exists"]},
            "notes": ["No events.jsonl found — pipeline never ran in this project."],
        }

    if not state["ok"]:
        notes.append(f"state.json could not be read: {state.get('error', 'missing')}")
        current_stage_from_state = None
        current_session_from_state = None
    else:
        current_stage_from_state = state["state"].get("current_stage")
        current_session_from_state = state["state"].get("session_id")

    in_flight: list[dict] = []
    for session_id, entries in events["by_session"].items():
        if not entries:
            continue
        # Sort by timestamp to find last event
        sorted_entries = sorted(entries, key=_event_timestamp)
        last = sorted_entries[-1]
        last_event_type = last.get("event_type", "")
        last_stage = last.get("stage", "")
        stages = sorted({e.get("stage", "") for e in entries if e.get("stage")})

        state_applies_to_session = (
            bool(current_stage_from_state)
            and (
                not current_session_from_state
                or current_session_from_state == session_id
            )
        )
        active_stage = last_stage
        if last_event_type.endswith("_complete"):
            if state_applies_to_session and current_stage_from_state in IN_FLIGHT_STAGES:
                active_stage = str(current_stage_from_state)
                is_in_flight = True
            else:
                is_in_flight = False
        else:
            # Heuristic: in-flight if the last observed event points at a
            # non-terminal stage. Completed-stage rows record the stage that
            # finished, so they must not be mistaken for the resume target.
            is_in_flight = last_stage in IN_FLIGHT_STAGES
        if not is_in_flight:
            continue

        in_flight.append({
            "session_id": session_id,
            "current_stage": active_stage,
            "last_event_type": last_event_type,
            "last_event_ts": _event_timestamp(last),
            "event_count": len(entries),
            "stages_touched": stages,
        })

    in_flight.sort(key=lambda s: s["last_event_ts"], reverse=True)

    return {
        "ok": True,
        "in_flight_sessions": in_flight,
        "current_stage": current_stage_from_state,
        "events_summary": {
            "exists": True,
            "entries": len(events["entries"]),
            "first_ts": events["first_ts"],
            "last_ts": events["last_ts"],
        },
        "state_summary": {
            "exists": state["exists"],
            "current_stage": current_stage_from_state,
        },
        "notes": notes,
    }


def format_in_flight_text(result: dict) -> str:
    """Format list_in_flight_sessions output as human-readable text."""
    if not result.get("ok"):
        return f"⚠ Reader error: {result.get('error', 'unknown')}\n"

    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("SAMVIL In-Flight Sessions (MCP-free, file-based)")
    lines.append("=" * 64)

    es = result.get("events_summary", {})
    if not es.get("exists"):
        lines.append("")
        lines.append("No events.jsonl found.")
        lines.append("This project has never run a SAMVIL pipeline, or the")
        lines.append("file was deleted. To start fresh: /samvil \"<idea>\"")
        return "\n".join(lines) + "\n"

    lines.append("")
    lines.append(f"Events:  {es.get('entries', 0)} (first: {es.get('first_ts', '?')}  last: {es.get('last_ts', '?')})")
    lines.append(f"State current_stage: {result.get('current_stage') or '(state.json missing)'}")
    lines.append("")

    sessions = result.get("in_flight_sessions", [])
    if not sessions:
        lines.append("No in-flight sessions — pipeline completed or no active work.")
        if result.get("notes"):
            lines.append("")
            for n in result["notes"]:
                lines.append(f"  Note: {n}")
        return "\n".join(lines) + "\n"

    lines.append(f"In-flight sessions ({len(sessions)}):")
    lines.append("-" * 64)
    for i, s in enumerate(sessions, 1):
        lines.append(f"  {i}. session_id={s['session_id']}")
        lines.append(f"     current_stage={s['current_stage']}")
        lines.append(f"     last_event={s['last_event_type']}  ts={s['last_event_ts']}")
        lines.append(f"     event_count={s['event_count']}  stages={s['stages_touched']}")
    lines.append("")
    lines.append("To resume: invoke samvil-resume skill (or read state.json + handoff.md directly)")
    if result.get("notes"):
        lines.append("")
        for n in result["notes"]:
            lines.append(f"  Note: {n}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="samvil_mcp.event_store_reader",
        description="MCP-free EventStore reader for SAMVIL recovery.",
    )
    parser.add_argument("--project", default=".", help="Project root (default: cwd)")
    parser.add_argument("--list-sessions", action="store_true", help="List in-flight sessions")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    if args.list_sessions or True:  # default action == list
        result = list_in_flight_sessions(args.project)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_in_flight_text(result))
        return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
