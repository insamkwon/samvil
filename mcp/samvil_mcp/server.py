"""SAMVIL MCP Server — persistence and analysis tools for the harness."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .event_store import EventStore
from .models import Event, EventType, Session, SeedVersion, Stage

mcp = FastMCP("samvil-mcp")

# Default DB path — can be overridden via environment
DB_PATH = Path.home() / ".samvil" / "samvil.db"
_store: EventStore | None = None


async def get_store() -> EventStore:
    global _store
    if _store is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _store = EventStore(str(DB_PATH))
        await _store.initialize()
    return _store


# ── Session tools ─────────────────────────────────────────────


@mcp.tool()
async def create_session(project_name: str, agent_tier: str = "standard") -> str:
    """Create a new SAMVIL session for a project. Returns session ID."""
    store = await get_store()
    session = await store.create_session(project_name, agent_tier)
    return json.dumps({"session_id": session.id, "project_name": project_name, "tier": agent_tier})


@mcp.tool()
async def get_session(session_id: str) -> str:
    """Get session status including current stage and progress."""
    store = await get_store()
    session = await store.get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session {session_id} not found"})
    return json.dumps({
        "id": session.id,
        "project_name": session.project_name,
        "current_stage": session.current_stage,
        "seed_version": session.seed_version,
        "agent_tier": session.agent_tier,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    })


@mcp.tool()
async def list_sessions(limit: int = 10) -> str:
    """List recent sessions, newest first."""
    store = await get_store()
    sessions = await store.list_sessions(limit)
    return json.dumps([{
        "id": s.id,
        "project_name": s.project_name,
        "current_stage": s.current_stage,
        "updated_at": s.updated_at,
    } for s in sessions])


@mcp.tool()
async def resume_session(project_name: str) -> str:
    """Find the most recent session for a project. Returns session data or null."""
    store = await get_store()
    session = await store.find_session_by_project(project_name)
    if not session:
        return json.dumps({"found": False})
    return json.dumps({
        "found": True,
        "session_id": session.id,
        "current_stage": session.current_stage,
        "seed_version": session.seed_version,
    })


# ── Event tools ───────────────────────────────────────────────


@mcp.tool()
async def save_event(
    session_id: str,
    event_type: str,
    stage: str,
    data: str = "{}",
) -> str:
    """Save a pipeline event. data is a JSON string."""
    store = await get_store()
    event = await store.save_event(
        session_id=session_id,
        event_type=EventType(event_type),
        stage=Stage(stage),
        data=json.loads(data),
    )
    # Update session's current stage
    await store.update_session_stage(session_id, Stage(stage))
    return json.dumps({"event_id": event.id, "saved": True})


@mcp.tool()
async def get_events(session_id: str, event_type: str = "", limit: int = 50) -> str:
    """Get events for a session, optionally filtered by type."""
    store = await get_store()
    et = EventType(event_type) if event_type else None
    events = await store.get_events(session_id, event_type=et, limit=limit)
    return json.dumps([{
        "id": e.id,
        "event_type": e.event_type,
        "stage": e.stage,
        "data": e.data,
        "timestamp": e.timestamp,
    } for e in events])


@mcp.tool()
async def session_status(session_id: str) -> str:
    """Get comprehensive session status: stage, events summary, seed version."""
    store = await get_store()
    session = await store.get_session(session_id)
    if not session:
        return json.dumps({"error": "Session not found"})

    events = await store.get_events(session_id, limit=100)
    event_counts: dict[str, int] = {}
    for e in events:
        event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1

    return json.dumps({
        "session": {
            "id": session.id,
            "project_name": session.project_name,
            "current_stage": session.current_stage,
            "seed_version": session.seed_version,
            "agent_tier": session.agent_tier,
        },
        "event_summary": event_counts,
        "total_events": len(events),
    })


# ── Seed version tools ────────────────────────────────────────


@mcp.tool()
async def save_seed_version(
    session_id: str,
    version: int,
    seed_json: str,
    change_summary: str = "",
) -> str:
    """Save a new seed version. seed_json is the full seed as JSON string."""
    store = await get_store()
    sv = await store.save_seed_version(session_id, version, seed_json, change_summary)
    # Update session seed version
    await store.update_session_seed_version(session_id, version)
    return json.dumps({"id": sv.id, "version": version, "saved": True})


@mcp.tool()
async def get_seed_history(session_id: str) -> str:
    """Get all seed versions for a session, ordered by version."""
    store = await get_store()
    versions = await store.get_seed_versions(session_id)
    return json.dumps([{
        "version": v.version,
        "change_summary": v.change_summary,
        "created_at": v.created_at,
    } for v in versions])


# ── Entry point ───────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
