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


import threading

# v3.1.0, v3-010 — atomic counter for multi-threaded/multi-instance MCP.
# Historically `_HEALTH_OK_COUNTS[tool] += 1` was a read-modify-write pattern,
# which is racy under Python's GIL-free contention window and outright broken
# if the MCP server is run in threads or multiple instances simultaneously.
# Using threading.Lock serializes the counter bump. Multi-process safety is
# still out of scope — for that see the BG discussion in
# references/cost-aware-mode.md; each MCP instance keeps its own counter
# (accepted trade-off: a few duplicate samples across instances vs a shared
# file-lock on every call).
_HEALTH_OK_COUNTS: dict[str, int] = {}
_HEALTH_OK_COUNTS_LOCK = threading.Lock()
# Sample 1-in-N successful calls per tool. `fail` is always logged.
_HEALTH_OK_SAMPLE_RATE = 10


def _log_mcp_health(status: str, tool: str, error: str = "") -> None:
    """Log MCP health event to .samvil/mcp-health.jsonl for retro reporting.

    - `fail` events are always recorded (with the error message).
    - `ok` events are sampled (1/10 by default) + total call count is
      persisted on every sampled entry so retro can compute real volume.

    v3.1.0 (v3-010): the per-tool counter bump is now guarded by a Lock so
    concurrent tool calls don't lose increments or mis-sample.
    """
    from datetime import datetime, timezone

    total_calls: int | None = None
    if status == "ok":
        with _HEALTH_OK_COUNTS_LOCK:
            _HEALTH_OK_COUNTS[tool] = _HEALTH_OK_COUNTS.get(tool, 0) + 1
            total_calls = _HEALTH_OK_COUNTS[tool]
        if total_calls % _HEALTH_OK_SAMPLE_RATE != 0:
            return  # sampled out

    health_path = Path.home() / ".samvil" / "mcp-health.jsonl"
    health_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "status": status,
        "tool": tool,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if total_calls is not None:
        entry["ok_total_so_far"] = total_calls
        entry["sample_rate"] = _HEALTH_OK_SAMPLE_RATE
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
        from .security import sanitize_filename, detect_dangerous
        detected = detect_dangerous(project_name)
        if detected:
            return json.dumps({"session_id": None, "error": f"Blocked patterns: {detected}"})
        project_name = sanitize_filename(project_name, max_len=100)
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


# ── Phase 3: QA Enhancement tools (v2.5.0) ────────────────────


@mcp.tool()
async def build_checklist(ac_id: str, ac_description: str, items_json: str) -> str:
    """Build an ACChecklist from item dicts.

    Args:
        ac_id: AC identifier
        ac_description: AC text
        items_json: JSON array of {description, passed, evidence[], rationale}

    Returns: dict with verdict, passed_count, total_count, violations[]
    """
    try:
        from .checklist import ACCheckItem, ACChecklist, validate_evidence_mandatory
        items_data = json.loads(items_json)
        items = tuple(
            ACCheckItem(
                description=i.get("description", ""),
                passed=bool(i.get("passed", False)),
                evidence=tuple(i.get("evidence", [])),
                rationale=i.get("rationale", ""),
                verification_questions=tuple(i.get("verification_questions", [])),
            )
            for i in items_data
        )
        checklist = ACChecklist(ac_id=ac_id, ac_description=ac_description, items=items)
        violations = validate_evidence_mandatory(checklist)
        result = checklist.to_dict()
        result["violations"] = violations
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "build_checklist", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_run_feedback(checklists_json: str) -> str:
    """Aggregate multiple ACChecklists into RunFeedback.

    Args:
        checklists_json: JSON array of checklist dicts (from build_checklist)

    Returns: RunFeedback dict with overall_verdict
    """
    try:
        from .checklist import aggregate, checklist_from_dict
        data = json.loads(checklists_json)
        checklists = [checklist_from_dict(c) for c in data]
        feedback = aggregate(checklists)
        return json.dumps(feedback.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "aggregate_run_feedback", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def validate_evidence(evidences_json: str, project_root: str) -> str:
    """Validate a list of file:line evidence strings against project files.

    Args:
        evidences_json: JSON array of evidence strings ("src/auth.ts:15")
        project_root: Absolute project path

    Returns: {all_valid, valid_count, total, results[]}
    """
    try:
        from .evidence_validator import validate_evidence_list
        evidences = json.loads(evidences_json)
        result = validate_evidence_list(evidences, project_root)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "validate_evidence", str(e))
        return json.dumps({"all_valid": False, "error": str(e)})


@mcp.tool()
async def semantic_check(code: str, context_hint: str = "") -> str:
    """Detect reward hacking signals in a code snippet.

    Args:
        code: Source code to analyze
        context_hint: Optional AC description for context

    Returns: {risk_level: LOW|MEDIUM|HIGH, findings[], socratic_questions[]}
    """
    try:
        from .semantic_checker import analyze_code_snippet
        return json.dumps(analyze_code_snippet(code, context_hint))
    except Exception as e:
        _log_mcp_health("fail", "semantic_check", str(e))
        return json.dumps({"risk_level": "LOW", "error": str(e)})


@mcp.tool()
async def semantic_check_llm(code: str, ac_description: str, tier: str = "standard") -> str:
    """Enhanced semantic check with LLM support for thorough+ tiers.

    Returns heuristic result + llm_prompt (for skill to call LLM) + should_use_llm flag.
    The actual LLM call is done by the skill, not MCP.

    Args:
        code: Source code to analyze
        ac_description: AC description for context
        tier: Agent tier (minimal/standard/thorough/full)

    Returns: heuristic result + {llm_prompt, should_use_llm}
    """
    try:
        from .semantic_checker import (
            analyze_code_snippet,
            build_llm_prompt,
            should_use_llm,
        )
        result = analyze_code_snippet(code, ac_description)
        use_llm = should_use_llm(tier, result["risk_level"])
        result["should_use_llm"] = use_llm
        if use_llm:
            result["llm_prompt"] = build_llm_prompt(code, ac_description)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "semantic_check_llm", str(e))
        return json.dumps({"risk_level": "LOW", "error": str(e), "should_use_llm": False})


@mcp.tool()
async def merge_llm_result(heuristic_json: str, llm_response_json: str) -> str:
    """Merge LLM verdict into heuristic result after skill calls LLM.

    Args:
        heuristic_json: Original heuristic result from semantic_check_llm
        llm_response_json: LLM response {is_real_implementation, confidence, reasoning}
    """
    try:
        from .semantic_checker import merge_llm_verdict
        heuristic = json.loads(heuristic_json)
        llm_resp = json.loads(llm_response_json)
        return json.dumps(merge_llm_verdict(heuristic, llm_resp))
    except Exception as e:
        _log_mcp_health("fail", "merge_llm_result", str(e))
        return heuristic_json


# ── Research WebFetch tools (v2.7.0, PATH 4) ─────────────────


@mcp.tool()
async def extract_query(question: str) -> str:
    """Extract searchable query from a research-routed question.

    Strips common prefixes like 'What are...', '최신...' to produce
    a concise search query.
    """
    from .research import extract_research_query
    return json.dumps({"query": extract_research_query(question)})


@mcp.tool()
async def format_research(results_json: str) -> str:
    """Format Tavily search results for user confirmation.

    Args:
        results_json: JSON array of search results from Tavily

    Returns: {has_results, summary_markdown, sources[], count}
    """
    from .research import format_research_results
    results = json.loads(results_json)
    return json.dumps(format_research_results(results))


# ── Skip Externally Satisfied ACs tools (v2.6.0, #08) ────────


@mcp.tool()
async def mark_externally_satisfied(seed_json: str, project_path: str) -> str:
    """Mark ACs that are already satisfied by existing code (from analysis.json).

    Args:
        seed_json: Full seed as JSON string
        project_path: Project root path containing .samvil/analysis.json

    Returns: Updated seed JSON with external_satisfied annotations
    """
    try:
        from .skip_ac import mark_seed_with_external
        seed = json.loads(seed_json)
        seed = mark_seed_with_external(seed, project_path)
        return json.dumps(seed)
    except Exception as e:
        _log_mcp_health("fail", "mark_externally_satisfied", str(e))
        return seed_json  # Return unchanged on failure (INV-5)


@mcp.tool()
async def load_external_satisfactions(project_path: str) -> str:
    """Load existing feature matches from .samvil/analysis.json.

    Args:
        project_path: Project root path

    Returns: JSON array of ExternalSatisfaction objects
    """
    try:
        from .skip_ac import load_analysis
        sats = load_analysis(project_path)
        return json.dumps([
            {
                "ac_description": s.ac_description,
                "evidence": s.evidence,
                "commit": s.commit,
                "reason": s.reason,
                "detected_at": s.detected_at,
            }
            for s in sats
        ])
    except Exception as e:
        _log_mcp_health("fail", "load_external_satisfactions", str(e))
        return json.dumps([])


# ── Checkpoint Store tools (v2.6.0, #07) ─────────────────────


@mcp.tool()
async def save_checkpoint(
    seed_id: str,
    phase: str,
    state_json: str,
    base_dir: str = "",
) -> str:
    """Save a checkpoint for crash recovery.

    Args:
        seed_id: Session/seed identifier
        phase: Current pipeline phase (build, qa, etc.)
        state_json: State to persist (completed features, progress, etc.)
        base_dir: Checkpoint storage directory (default: ~/.samvil/checkpoints/)
    """
    try:
        from .checkpoint import CheckpointData, CheckpointStore
        base = Path(base_dir) if base_dir else Path.home() / ".samvil" / "checkpoints"
        store = CheckpointStore(base)
        state = json.loads(state_json)
        cp = CheckpointData.create(seed_id, phase, state)
        store.save(cp)
        return json.dumps({"saved": True, "timestamp": cp.timestamp})
    except Exception as e:
        _log_mcp_health("fail", "save_checkpoint", str(e))
        return json.dumps({"saved": False, "error": str(e)})


@mcp.tool()
async def load_checkpoint(seed_id: str, base_dir: str = "") -> str:
    """Load latest valid checkpoint for crash recovery."""
    try:
        from .checkpoint import CheckpointStore
        base = Path(base_dir) if base_dir else Path.home() / ".samvil" / "checkpoints"
        store = CheckpointStore(base)
        cp = store.load(seed_id)
        if cp is None:
            return json.dumps({"found": False})
        return json.dumps({
            "found": True,
            "seed_id": cp.seed_id,
            "phase": cp.phase,
            "state": cp.state,
            "timestamp": cp.timestamp,
        })
    except Exception as e:
        _log_mcp_health("fail", "load_checkpoint", str(e))
        return json.dumps({"found": False, "error": str(e)})


@mcp.tool()
async def list_checkpoints(base_dir: str = "") -> str:
    """List all sessions with checkpoints."""
    try:
        from .checkpoint import CheckpointStore
        base = Path(base_dir) if base_dir else Path.home() / ".samvil" / "checkpoints"
        store = CheckpointStore(base)
        return json.dumps({"seed_ids": store.list_checkpoints()})
    except Exception as e:
        return json.dumps({"seed_ids": [], "error": str(e)})


# ── Stall Detection tool (v2.6.0, #24) ───────────────────────


@mcp.tool()
async def check_stall(
    events_path: str,
    timeout: float = 300.0,
    retry_count: int = 0,
) -> str:
    """Check if pipeline is stalled based on last event timestamp.

    Args:
        events_path: Path to .samvil/events.jsonl
        timeout: Seconds before stall declared (default 300 = 5 min)
        retry_count: Current retry attempt count
    """
    try:
        from .stall_detector import detect_stall
        status = detect_stall(events_path, timeout, retry_count)
        return json.dumps({
            "is_stalled": status.is_stalled,
            "last_event_age_seconds": status.last_event_age_seconds,
            "last_event_type": status.last_event_type,
            "retry_count": status.retry_count,
            "should_retry": status.should_retry,
        })
    except Exception as e:
        _log_mcp_health("fail", "check_stall", str(e))
        return json.dumps({"is_stalled": False, "error": str(e)})


# ── v3.1.0 Sprint 2 — state.json heartbeat + stall detection (v3-016) ────


@mcp.tool()
async def heartbeat_state(state_path: str, now_iso: str | None = None) -> str:
    """Update ``last_progress_at`` on project.state.json (v3-016).

    Call from design/council/evolve skills between long-running substeps so
    `is_state_stalled` and the main session know the run is alive.

    Args:
        state_path: Path to project.state.json
        now_iso: Override "now" with a specific ISO timestamp (for tests).
    """
    try:
        from .stall_detector import heartbeat_state as _heartbeat
        state = _heartbeat(state_path, now_iso)
        return json.dumps({
            "ok": True,
            "last_progress_at": state.get("last_progress_at"),
            "stall_recovery_count": state.get("stall_recovery_count", 0),
        })
    except Exception as e:
        _log_mcp_health("fail", "heartbeat_state", str(e))
        return json.dumps({"ok": False, "error": str(e)})


@mcp.tool()
async def is_state_stalled(
    state_path: str,
    now_iso: str | None = None,
    threshold_seconds: int = 300,
) -> str:
    """Return stall verdict based on project.state.json last_progress_at (v3-016).

    Complements ``check_stall`` which reads events.jsonl — this one is for
    skills that don't emit domain events during long loops (design, council,
    evolve).
    """
    try:
        from .stall_detector import is_state_stalled as _is_stalled
        verdict = _is_stalled(state_path, now_iso, threshold_seconds)
        return json.dumps(verdict)
    except Exception as e:
        _log_mcp_health("fail", "is_state_stalled", str(e))
        return json.dumps({
            "stalled": False,
            "reason": f"error: {e}",
            "elapsed_seconds": None,
            "last_progress_at": None,
            "threshold_seconds": threshold_seconds,
        })


@mcp.tool()
async def build_reawake_message(stage: str, detail_json: str, count: int) -> str:
    """Construct the recovery message the main session should inject (v3-016).

    Args:
        stage: Current stage name (design/council/evolve/...)
        detail_json: JSON-serialised output of is_state_stalled
        count: Current reawake count (0-based)
    """
    try:
        from .stall_detector import build_reawake_message as _build
        detail = json.loads(detail_json)
        message = _build(stage, detail, count)
        return json.dumps({"ok": True, "message": message})
    except Exception as e:
        _log_mcp_health("fail", "build_reawake_message", str(e))
        return json.dumps({"ok": False, "error": str(e)})


@mcp.tool()
async def increment_stall_recovery_count(state_path: str) -> str:
    """Bump ``stall_recovery_count`` on project.state.json (v3-016)."""
    try:
        from .stall_detector import increment_stall_recovery_count as _bump
        count = _bump(state_path)
        return json.dumps({"ok": True, "count": count})
    except Exception as e:
        _log_mcp_health("fail", "increment_stall_recovery_count", str(e))
        return json.dumps({"ok": False, "error": str(e)})


# ── v3.1.0 Sprint 1 — tier phase wiring (v3-022 Polish #5) ───


@mcp.tool()
async def get_tier_phases(tier: str = "standard") -> str:
    """Return the required interview phases for a tier (v3-022).

    Consumers: samvil-interview SKILL reads this to decide which Phase 2.x
    blocks are mandatory for a given tier. Previously this lived as a dict
    constant in interview_engine.py and was only reachable from Python tests —
    the SKILL had no way to consult it, so the tier→phases mapping was
    duplicated in prose form. This tool closes the loop.

    Args:
        tier: minimal / standard / thorough / full / deep
    """
    try:
        from .interview_engine import TIER_REQUIRED_PHASES, TIER_TARGETS, tier_phases
        phases = sorted(tier_phases(tier))
        target = TIER_TARGETS.get(tier, TIER_TARGETS["standard"])
        return json.dumps({
            "tier": tier,
            "phases": phases,
            "ambiguity_target": target,
            "all_tiers": sorted(TIER_REQUIRED_PHASES.keys()),
        })
    except Exception as e:
        _log_mcp_health("fail", "get_tier_phases", str(e))
        return json.dumps({"tier": tier, "phases": [], "error": str(e)})


# ── v3.1.0 Sprint 6 — AC split heuristic (v3-011) ─────────────


@mcp.tool()
async def suggest_ac_split(description: str) -> str:
    """Check whether an AC leaf should be decomposed into children (v3-011).

    Returns a verdict dict with reasons and a heuristic child split. The
    evolve skill consumes this verdict and asks an LLM for a polished split
    when `should_split` is true.
    """
    try:
        from .ac_split import should_split
        result = should_split(description)
        _log_mcp_health("ok", "suggest_ac_split")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log_mcp_health("fail", "suggest_ac_split", str(e))
        return json.dumps({"should_split": False, "error": str(e)})


# ── Phase 4: Evolve Gates tools (v2.5.0) ──────────────────────


@mcp.tool()
async def check_convergence_gates(eval_result_json: str, history_json: str = "[]") -> str:
    """Run 5-gate convergence check.

    Args:
        eval_result_json: Current eval result (score, ac_states, validation_status, ...)
        history_json: Array of prior cycle snapshots

    Returns: ConvergenceVerdict with converged, blocked_by[], reasons[], regressions[]
    """
    try:
        from .convergence_gate import check_all_gates, GateConfig
        eval_result = json.loads(eval_result_json)
        history = json.loads(history_json)
        verdict = check_all_gates(eval_result, history, GateConfig())
        return json.dumps(verdict.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "check_convergence_gates", str(e))
        return json.dumps({"converged": False, "error": str(e)})


@mcp.tool()
async def detect_ac_regressions(current_states_json: str, history_json: str) -> str:
    """Detect ACs that regressed (PASS → FAIL) across cycles.

    Args:
        current_states_json: {ac_id: "PASS" | "FAIL" | "PARTIAL"}
        history_json: Array of cycle snapshots

    Returns: list of ACRegression dicts
    """
    try:
        from .regression_detector import detect_regressions
        current = json.loads(current_states_json)
        history = json.loads(history_json)
        regressions = detect_regressions(current, history)
        return json.dumps([r.to_dict() for r in regressions])
    except Exception as e:
        _log_mcp_health("fail", "detect_ac_regressions", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def record_qa_failure(
    project_path: str,
    ac_id: str,
    ac_description: str,
    cycle: int,
    reason: str,
    suggestions_json: str = "[]",
) -> str:
    """Record a QA failure for the Self-Correction Circuit.

    Args:
        project_path: Project root
        ac_id, ac_description, cycle, reason: failure details
        suggestions_json: JSON array of suggestion strings

    Returns: {path, total_failures}
    """
    try:
        from .self_correction import record_qa_failure as _record
        suggestions = json.loads(suggestions_json)
        result = _record(project_path, ac_id, ac_description, cycle, reason, suggestions)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "record_qa_failure", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def load_failures_for_wonder(project_path: str) -> str:
    """Load accumulated failures + summary for Evolve Wonder stage.

    Args:
        project_path: Project root

    Returns: {failures: [...], summary: str}
    """
    try:
        from .self_correction import load_failed_acs_for_wonder, summarize_for_wonder
        failures = load_failed_acs_for_wonder(project_path)
        summary = summarize_for_wonder(failures)
        return json.dumps({"failures": failures, "summary": summary})
    except Exception as e:
        _log_mcp_health("fail", "load_failures_for_wonder", str(e))
        return json.dumps({"failures": [], "summary": "", "error": str(e)})


# ── Phase 5: Resilience tools (v2.5.0) ────────────────────────


@mcp.tool()
async def update_progress(project_path: str, state_json: str, features_json: str = "[]") -> str:
    """Render Double Diamond + AC progress to .samvil/progress.md.

    Args:
        project_path: Project root
        state_json: Current state.json content
        features_json: Optional per-feature AC progress

    Returns: {path, bytes}
    """
    try:
        from .progress_renderer import update_progress_file
        state = json.loads(state_json)
        features = json.loads(features_json) if features_json else None
        result = update_progress_file(project_path, state, features)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "update_progress", str(e))
        return json.dumps({"error": str(e)})


# ── Phase 6: AC Tree tools (v2.5.0, backward-compat) ──────────


@mcp.tool()
async def parse_ac_tree(ac_data_json: str) -> str:
    """Parse AC from either flat string or tree dict.

    Args:
        ac_data_json: JSON of either a string or ACNode dict

    Returns: ACNode dict
    """
    try:
        from .ac_tree import load_ac_from_schema, count_nodes
        data = json.loads(ac_data_json)
        node = load_ac_from_schema(data)
        result = node.to_dict()
        result["counts"] = count_nodes(node)
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "parse_ac_tree", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def render_ac_tree_hud(ac_tree_json: str) -> str:
    """Render AC tree as ASCII HUD.

    Args:
        ac_tree_json: ACNode dict

    Returns: {ascii: str, counts: {...}}
    """
    try:
        from .ac_tree import ACNode, render_tree_ascii, count_nodes
        data = json.loads(ac_tree_json)
        node = ACNode.from_dict(data)
        return json.dumps({
            "ascii": render_tree_ascii(node),
            "counts": count_nodes(node),
        })
    except Exception as e:
        _log_mcp_health("fail", "render_ac_tree_hud", str(e))
        return json.dumps({"error": str(e), "ascii": ""})


@mcp.tool()
async def suggest_ac_decomposition(ac_description: str) -> str:
    """Heuristic suggestion for AC decomposition (pre-LLM).

    Args:
        ac_description: The AC text

    Returns: {suggested_children: [str], needs_llm: bool}
    """
    try:
        from .ac_tree import simple_decompose_suggestion
        suggestions = simple_decompose_suggestion(ac_description)
        return json.dumps({
            "suggested_children": suggestions,
            "needs_llm": len(suggestions) == 0,
        })
    except Exception as e:
        return json.dumps({"suggested_children": [], "needs_llm": True, "error": str(e)})


# ── v3.0.0 T1.1: AC Tree traversal tools ──────────────────────


@mcp.tool()
async def next_buildable_leaves(
    ac_tree_json: str,
    completed_ids_json: str = "[]",
    max_parallel: int = 2,
) -> str:
    """Return next AC leaves that can be built in parallel.

    Args:
        ac_tree_json: ACNode dict
        completed_ids_json: JSON array of already-completed leaf IDs
        max_parallel: max concurrent workers (default 2)

    Returns: {leaves: [ACNode dict, ...], count: int, max_parallel: int}
    """
    try:
        from .ac_tree import ACNode, next_buildable_leaves as _nbl
        node = ACNode.from_dict(json.loads(ac_tree_json))
        completed = set(json.loads(completed_ids_json))
        batch = _nbl(node, completed, max_parallel=max_parallel)
        result = {
            "leaves": [l.to_dict() for l in batch],
            "count": len(batch),
            "max_parallel": max_parallel,
        }
        _log_mcp_health("ok", "next_buildable_leaves")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "next_buildable_leaves", str(e))
        return json.dumps({"error": str(e), "leaves": [], "count": 0})


@mcp.tool()
async def tree_progress(ac_tree_json: str) -> str:
    """Compute leaf-level progress stats.

    Args:
        ac_tree_json: ACNode dict

    Returns: {total_leaves, completed, passed, failed, pending, progress_pct, all_done}
    """
    try:
        from .ac_tree import ACNode, tree_progress as _tp, all_done as _all_done
        node = ACNode.from_dict(json.loads(ac_tree_json))
        stats = _tp(node)
        stats["all_done"] = _all_done(node)
        _log_mcp_health("ok", "tree_progress")
        return json.dumps(stats)
    except Exception as e:
        _log_mcp_health("fail", "tree_progress", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def update_leaf_status(
    ac_tree_json: str,
    leaf_id: str,
    status: str,
    evidence_json: str = "[]",
) -> str:
    """Update a leaf's status (and optional evidence) in the AC tree.

    Args:
        ac_tree_json: ACNode dict
        leaf_id: target leaf ID
        status: new status (pending/in_progress/pass/fail/blocked/skipped)
        evidence_json: JSON array of evidence strings to append

    Returns:
        {"found": bool, "tree": <ACNode dict>, "leaf_id": str, "status": str}
        - tree is a clean ACNode that callers can round-trip back into
          parse_ac_tree / next_buildable_leaves without pruning extra keys.
    """
    try:
        from .ac_tree import ACNode, walk
        valid = {"pending", "in_progress", "pass", "fail", "blocked", "skipped"}
        if status not in valid:
            return json.dumps({
                "found": False,
                "tree": None,
                "error": f"invalid status: {status}",
            })
        node = ACNode.from_dict(json.loads(ac_tree_json))
        evidence = json.loads(evidence_json)
        found = False
        for n in walk(node):
            if n.id == leaf_id:
                n.status = status  # type: ignore[assignment]
                if evidence:
                    n.evidence.extend(evidence)
                found = True
                break
        result = {
            "found": found,
            "tree": node.to_dict(),
            "leaf_id": leaf_id,
            "status": status,
        }
        _log_mcp_health("ok", "update_leaf_status")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "update_leaf_status", str(e))
        return json.dumps({"found": False, "tree": None, "error": str(e)})


# ── v3.0.0 T1.4: Seed migration tools ─────────────────────────


@mcp.tool()
async def migrate_seed(
    seed_json: str,
    from_version: str = "2",
    to_version: str = "3",
) -> str:
    """Migrate a seed between schema versions (currently v2→v3).

    Args:
        seed_json: seed dict as JSON
        from_version: source major version (default "2")
        to_version: target major version (default "3")

    Returns: {migrated: seed dict, from, to, migrated_version}
    """
    try:
        from .migrations import migrate_seed_v2_to_v3
        seed = json.loads(seed_json)
        if str(from_version).startswith("2") and str(to_version).startswith("3"):
            migrated = migrate_seed_v2_to_v3(seed)
        else:
            return json.dumps({
                "error": f"Unsupported migration path: {from_version} → {to_version}",
            })
        result = {
            "migrated": migrated,
            "from": from_version,
            "to": to_version,
            "migrated_version": migrated.get("schema_version", "3.0"),
        }
        _log_mcp_health("ok", "migrate_seed")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "migrate_seed", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def migrate_seed_file(seed_path: str) -> str:
    """Migrate an on-disk seed file v2 → v3, creating a .v2.backup.json next to it.

    Idempotent: if already v3, returns without rewriting.

    Args:
        seed_path: absolute path to project.seed.json

    Returns: {status, path, backup_path, schema_version, already_v3: bool}
    """
    try:
        from .migrations import migrate_with_backup
        p = Path(seed_path)
        if not p.exists():
            return json.dumps({"error": f"Seed not found: {seed_path}"})
        # detect pre-state
        pre = json.loads(p.read_text())
        already_v3 = str(pre.get("schema_version", "")).startswith("3.")
        migrated = migrate_with_backup(str(p))
        backup = p.with_suffix(".v2.backup.json")
        result = {
            "status": "ok",
            "path": str(p),
            "backup_path": str(backup) if backup.exists() else "",
            "schema_version": migrated.get("schema_version", "3.0"),
            "already_v3": already_v3,
        }
        _log_mcp_health("ok", "migrate_seed_file")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "migrate_seed_file", str(e))
        return json.dumps({"error": str(e)})


# ── v3.0.0 T2: Dependency Planning ────────────────────────────


@mcp.tool()
async def analyze_ac_dependencies(
    acs_json: str,
    llm_deps_json: str = "[]",
    llm_mode: str = "augment",
) -> str:
    """Build a dependency DAG from ACs and return the execution plan.

    Args:
        acs_json: JSON list of AC dicts. Each may include
            id, description, depends_on, prerequisites,
            shared_runtime_resources, serial_only.
        llm_deps_json: JSON list of LLM-inferred dependency entries of the
            form {"ac_id": str, "depends_on": [str], "reason": str}.
            Defaults to no LLM input.
        llm_mode: "augment" (default — keep structured deps, add LLM deps)
                  or "replace" (for ACs in llm_deps, discard structured and
                  use LLM only).

    Returns: execution plan dict with nodes / execution_levels /
             is_parallelizable / total_levels / total_acs
    """
    try:
        from .dependency_analyzer import (
            analyze_structured,
            build_plan,
            compute_execution_levels,
            merge_llm,
        )
        acs = json.loads(acs_json)
        llm_deps = json.loads(llm_deps_json) if llm_deps_json else []
        structured = analyze_structured(acs)
        merged = merge_llm(structured, llm_deps, mode=llm_mode)
        levels = compute_execution_levels(merged)
        plan = build_plan(merged, levels)
        _log_mcp_health("ok", "analyze_ac_dependencies")
        return json.dumps(plan)
    except Exception as e:
        _log_mcp_health("fail", "analyze_ac_dependencies", str(e))
        return json.dumps({"error": str(e)})


# ── v3.0.0 T3: Shared Rate Budget ─────────────────────────────


@mcp.tool()
async def rate_budget_acquire(
    budget_path: str,
    worker_id: str,
    max_concurrent: int = 2,
) -> str:
    """Cooperatively acquire a slot in the shared worker budget.

    Appends an `acquire` event to budget_path (JSONL) iff current < max.
    Returns {acquired: bool, current, max_concurrent}.
    """
    try:
        from .rate_budget import acquire as _acquire
        result = _acquire(budget_path, worker_id, max_concurrent)
        _log_mcp_health("ok", "rate_budget_acquire")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "rate_budget_acquire", str(e))
        return json.dumps({"error": str(e), "acquired": False})


@mcp.tool()
async def rate_budget_release(budget_path: str, worker_id: str) -> str:
    """Append a `release` event for worker_id. Idempotent."""
    try:
        from .rate_budget import release as _release
        result = _release(budget_path, worker_id)
        _log_mcp_health("ok", "rate_budget_release")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "rate_budget_release", str(e))
        return json.dumps({"error": str(e), "released": False})


@mcp.tool()
async def rate_budget_stats(budget_path: str) -> str:
    """Return budget stats {active, peak, total_acquired, total_released}."""
    try:
        from .rate_budget import stats as _stats
        result = _stats(budget_path)
        _log_mcp_health("ok", "rate_budget_stats")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "rate_budget_stats", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def rate_budget_reset(budget_path: str) -> str:
    """Truncate the budget log. Returns pre-reset stats."""
    try:
        from .rate_budget import reset as _reset
        result = _reset(budget_path)
        _log_mcp_health("ok", "rate_budget_reset")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "rate_budget_reset", str(e))
        return json.dumps({"error": str(e)})


# ── v3.0.0 T4: PM Interview Mode ──────────────────────────────


@mcp.tool()
async def validate_pm_seed(pm_seed_json: str) -> str:
    """Validate a PM seed structure. Returns {valid, errors}."""
    try:
        from .pm_seed import validate_pm_seed as _validate
        pm_seed = json.loads(pm_seed_json)
        errors = _validate(pm_seed)
        _log_mcp_health("ok", "validate_pm_seed")
        return json.dumps({"valid": not errors, "errors": errors})
    except Exception as e:
        _log_mcp_health("fail", "validate_pm_seed", str(e))
        return json.dumps({"valid": False, "errors": [str(e)]})


@mcp.tool()
async def pm_seed_to_eng_seed(
    pm_seed_json: str,
    defaults_json: str = "{}",
) -> str:
    """Convert a PM seed to an engineering seed (features[]).

    Args:
        pm_seed_json: PM seed
        defaults_json: engineering-field overrides
            (tech_stack, solution_type, core_experience, constraints,
             out_of_scope, version, description). Anything missing is filled
            with conservative placeholders so validate_seed accepts the result.

    Output includes schema_version: "3.0" and preserves vision / users / metrics.
    """
    try:
        from .pm_seed import pm_seed_to_eng_seed as _convert
        pm_seed = json.loads(pm_seed_json)
        defaults = json.loads(defaults_json) if defaults_json else {}
        eng_seed = _convert(pm_seed, defaults=defaults)
        _log_mcp_health("ok", "pm_seed_to_eng_seed")
        return json.dumps(eng_seed)
    except Exception as e:
        _log_mcp_health("fail", "pm_seed_to_eng_seed", str(e))
        return json.dumps({"error": str(e)})


# ── Entry point ───────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
