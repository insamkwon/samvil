"""SAMVIL MCP Server — persistence and analysis tools for the harness.

Graceful Degradation (INV-7):
  - All state changes are first written to files (project.state.json, .samvil/metrics.json).
  - MCP is a secondary channel. Pipeline continues even when MCP is down.
  - MCP call failures are logged to .samvil/mcp-health.jsonl.
  - Skill-level MCP try/catch pattern:
      1. Write state to file (always)
      2. Attempt MCP call (best-effort)
      3. On failure, log to mcp-health.jsonl
      4. Continue pipeline without blocking
"""

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


def _log_mcp_health(status: str, tool: str, error: str = "") -> None:
    """Log MCP health event to .samvil/mcp-health.jsonl for retro reporting."""
    from datetime import datetime, timezone
    health_path = Path.home() / ".samvil" / "mcp-health.jsonl"
    health_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "status": status,
        "tool": tool,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(health_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Session tools ─────────────────────────────────────────────


@mcp.tool()
async def health_check() -> str:
    """Check MCP server health. Returns server status and DB connectivity."""
    try:
        store = await get_store()
        # Test DB connectivity with a lightweight query
        sessions = await store.list_sessions(limit=1)
        return json.dumps({
            "status": "ok",
            "db_path": str(DB_PATH),
            "sessions_accessible": True,
        })
    except Exception as e:
        _log_mcp_health("fail", "health_check", str(e))
        return json.dumps({
            "status": "error",
            "error": str(e),
            "db_path": str(DB_PATH),
        })





@mcp.tool()
async def create_session(project_name: str, agent_tier: str = "standard") -> str:
    """Create a new SAMVIL session for a project. Returns session ID."""
    try:
        store = await get_store()
        session = await store.create_session(project_name, agent_tier)
        return json.dumps({"session_id": session.id, "project_name": project_name, "tier": agent_tier})
    except Exception as e:
        _log_mcp_health("fail", "create_session", str(e))
        return json.dumps({"session_id": None, "error": str(e)})


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
    token_count: int | None = None,
) -> str:
    """Save a pipeline event. data is a JSON string. token_count is optional estimated token usage."""
    try:
        store = await get_store()
        event = await store.save_event(
            session_id=session_id,
            event_type=EventType(event_type),
            stage=Stage(stage),
            data=json.loads(data),
            token_count=token_count,
        )
        # Update session's current stage
        await store.update_session_stage(session_id, Stage(stage))
        return json.dumps({"event_id": event.id, "saved": True})
    except Exception as e:
        _log_mcp_health("fail", "save_event", str(e))
        return json.dumps({"event_id": None, "saved": False, "error": str(e)})


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
        "token_count": e.token_count,
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
    total_tokens = 0
    for e in events:
        event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1
        if e.token_count:
            total_tokens += e.token_count

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
        "total_tokens": total_tokens if total_tokens > 0 else None,
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


# ── Evolve tools ──────────────────────────────────────────────


@mcp.tool()
async def compare_seeds(seed_a: str, seed_b: str) -> str:
    """Compare two seed versions. Returns similarity (0-1) and changes.
    Similarity ≥ 0.95 = converged."""
    from .seed_manager import compare_seeds as _compare
    a = json.loads(seed_a)
    b = json.loads(seed_b)
    return json.dumps(_compare(a, b))


@mcp.tool()
async def check_convergence(seed_history: str) -> str:
    """Check if seed evolution has converged. seed_history is JSON array of seed dicts."""
    from .seed_manager import check_convergence as _check
    history = json.loads(seed_history)
    return json.dumps(_check(history))


@mcp.tool()
async def validate_evolved_seed(original_seed: str, evolved_seed: str) -> str:
    """Validate that an evolved seed is a legitimate improvement."""
    from .evolve_loop import validate_evolved_seed as _validate
    orig = json.loads(original_seed)
    evolved = json.loads(evolved_seed)
    return json.dumps(_validate(orig, evolved))


@mcp.tool()
async def get_evolve_context(session_id: str, qa_result: str) -> str:
    """Generate context for wonder/reflect agents. Includes convergence trend."""
    from .evolve_loop import generate_evolve_context as _context
    store = await get_store()
    session = await store.get_session(session_id)
    if not session:
        return json.dumps({"error": "Session not found"})

    # Get seed history
    versions = await store.get_seed_versions(session_id)
    seed_history = [json.loads(v.seed_json) for v in versions]

    # Current seed is the latest version
    current_seed = seed_history[-1] if seed_history else json.loads(qa_result)

    context = _context(current_seed, json.loads(qa_result), seed_history)
    return json.dumps(context)


# ── Ambiguity scoring tools ────────────────────────────────────


@mcp.tool()
async def score_ambiguity(interview_state: str, tier: str = "standard") -> str:
    """Score interview ambiguity. interview_state is JSON with keys:
    target_user, core_problem, core_experience, features, exclusions,
    constraints, acceptance_criteria. tier: minimal(0.10), standard(0.05),
    thorough(0.02), full(0.01). Returns ambiguity score + milestone + floors + missing_items (v2.4.0)."""
    from .interview_engine import score_ambiguity as _score
    state = json.loads(interview_state)
    result = _score(state, tier=tier)
    return json.dumps(result)


# ── PATH Routing tools (v2.4.0, Ouroboros #01) ──────────────────


@mcp.tool()
async def scan_manifest(project_path: str) -> str:
    """Scan project manifest files (package.json, pyproject.toml, prisma/schema.prisma)
    to extract facts. Returns dict with framework, language, database, etc.
    Used by PATH 1a auto-confirm routing."""
    try:
        from .path_router import scan_manifest as _scan
        facts = _scan(project_path)
        return json.dumps(facts)
    except Exception as e:
        _log_mcp_health("fail", "scan_manifest", str(e))
        return json.dumps({"detected": False, "error": str(e)})


@mcp.tool()
async def route_question(
    question: str,
    manifest_facts: str = "{}",
    force_user: bool = False,
) -> str:
    """Determine the routing path for an interview question.

    Args:
        question: The question text
        manifest_facts: JSON string from scan_manifest()
        force_user: If true (Rhythm Guard active), force PATH 2 (user)

    Returns: {path, rationale, auto_answer, icon}

    Paths:
        - auto_confirm (PATH 1a): AI auto-answers from manifest
        - code_confirm (PATH 1b): AI proposes, user Y/N confirms
        - user (PATH 2): direct user judgment
        - hybrid (PATH 3): code + user decision
        - research (PATH 4): web search needed
        - forced_user: Rhythm Guard override
    """
    try:
        from .path_router import detect_routing_path as _route
        facts = json.loads(manifest_facts) if manifest_facts else {}
        result = _route(question, manifest_facts=facts, force_user=force_user)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "route_question", str(e))
        # Safe fallback: always route to user
        return json.dumps({
            "path": "user",
            "rationale": f"Error in routing, fallback to user: {e}",
            "auto_answer": None,
            "icon": "💬",
        })


@mcp.tool()
async def update_answer_streak(current_streak: int, answer_source: str) -> str:
    """Update AI answer streak counter (Rhythm Guard).

    Args:
        current_streak: Current streak value
        answer_source: 'from-code', 'from-code-auto', 'from-user',
                       'from-user-correction', 'from-research'

    Returns: {new_streak, force_user_next, reason}
    """
    try:
        from .interview_engine import update_streak as _update
        result = _update(current_streak, answer_source)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "update_answer_streak", str(e))
        return json.dumps({
            "new_streak": current_streak,
            "force_user_next": False,
            "error": str(e),
        })


@mcp.tool()
async def manage_tracks(
    action: str,
    tracks_json: str = "[]",
    track_name: str = "",
    features: str = "[]",
) -> str:
    """Manage interview tracks (Breadth-Keeper).

    Actions:
        - 'init': Initialize tracks from features list. Returns new tracks.
        - 'update': Increment rounds_focused for track_name. Returns updated tracks.
        - 'resolve': Mark track_name as resolved. Returns updated tracks.
        - 'check': Check if Breadth-Keeper should intervene. Returns verdict.

    Args:
        action: One of 'init', 'update', 'resolve', 'check'
        tracks_json: Current tracks as JSON array
        track_name: Track name (for update/resolve)
        features: Features list as JSON array (for init)
    """
    try:
        from .interview_engine import (
            initialize_tracks as _init,
            update_track as _update,
            mark_track_resolved as _resolve,
            should_force_breadth as _check,
        )
        if action == "init":
            feats = json.loads(features)
            return json.dumps(_init(feats))
        if action == "update":
            tracks = json.loads(tracks_json)
            return json.dumps(_update(tracks, track_name))
        if action == "resolve":
            tracks = json.loads(tracks_json)
            return json.dumps(_resolve(tracks, track_name))
        if action == "check":
            tracks = json.loads(tracks_json)
            return json.dumps(_check(tracks))
        return json.dumps({"error": f"Unknown action: {action}"})
    except Exception as e:
        _log_mcp_health("fail", "manage_tracks", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def extract_answer_source(answer: str) -> str:
    """Extract source prefix from a prefixed answer string.

    Returns one of: 'from-code-auto', 'from-code', 'from-user',
                    'from-user-correction', 'from-research'
    Unprefixed → 'from-user' (safe default)"""
    try:
        from .path_router import extract_answer_source as _extract
        return json.dumps({"source": _extract(answer)})
    except Exception as e:
        return json.dumps({"source": "from-user", "error": str(e)})


# ── Schema validation tools (Inter-Stage Contract) ────────────


@mcp.tool()
async def validate_seed(seed_json: str) -> str:
    """Validate a seed JSON against seed-schema.json.
    Returns {valid: bool, errors: [...]}."""
    from .seed_manager import validate_seed as _validate
    seed = json.loads(seed_json)
    result = _validate(seed)
    return json.dumps(result)


@mcp.tool()
async def validate_state(state_json: str) -> str:
    """Validate a state JSON against state-schema.json.
    Returns {valid: bool, errors: [...]}."""
    from .seed_manager import validate_state as _validate
    state = json.loads(state_json)
    result = _validate(state)
    return json.dumps(result)


@mcp.tool()
async def check_db_integrity() -> str:
    """Check SQLite database integrity via PRAGMA integrity_check.
    Returns {status: 'ok'|'error', details: ...}."""
    store = await get_store()
    result = await store.check_integrity()
    return json.dumps(result)


# ── Entry point ───────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
