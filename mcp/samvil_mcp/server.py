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

from .ac_leaf_schema import (
    ACLeaf,
    Stage as ACStage,
    compute_parallel_safety as _compute_parallel_safety,
    validate_leaf as _validate_leaf_core,
)
from .claim_ledger import ClaimLedger, ClaimLedgerError
from .decision_log import (
    DecisionADR,
    DecisionLogError,
    adr_from_council_decision as _adr_from_council_decision,
    adr_path as _decision_adr_path,
    find_adrs_referencing as _find_adrs_referencing,
    list_adrs as _list_decision_adrs,
    read_adr as _read_decision_adr,
    supersede_adr as _supersede_decision_adr,
    write_adr as _write_decision_adr,
)
from .migrate_v3_2 import (
    apply_migration as _apply_migration,
    plan_migration as _plan_migration,
)
from .performance_budget import (
    Consumption,
    evaluate_status as _budget_evaluate_status,
    load_budget as _load_budget,
)
from .consensus_v3_2 import (
    DEPRECATION_WARNING as COUNCIL_DEPRECATION_WARNING,
    DisputeInput,
    build_judge_prompt as _consensus_judge_prompt,
    build_reviewer_prompt as _consensus_reviewer_prompt,
    detect_dispute as _detect_dispute,
)
from .stagnation_v3_2 import (
    StagnationInput,
    build_lateral_prompt as _lateral_prompt,
    evaluate as _stagnation_evaluate,
)
from .jurisdiction import (
    Jurisdiction,
    check_jurisdiction as _check_jurisdiction_core,
    loop_should_stop as _loop_should_stop,
)
from .diagnostic import (
    diagnose_environment_async as _diagnose_environment_async,
)
from .deploy_targets import (
    evaluate_deploy_target as _evaluate_deploy_target,
)
from .scaffold_targets import (
    evaluate_scaffold_target as _evaluate_scaffold_target,
)
from .build_phase_a import (
    aggregate_build_phase_a as _aggregate_build_phase_a,
)
from .build_phase_b import (
    dispatch_build_batch as _dispatch_build_batch,
)
from .build_phase_z import (
    finalize_build_phase_z as _finalize_build_phase_z,
)
from .qa_boot import (
    aggregate_qa_boot_context as _aggregate_qa_boot_context,
)
from .qa_pass1 import (
    dispatch_qa_pass1_batch as _dispatch_qa_pass1_batch,
)
from .qa_finalize import (
    finalize_qa_verdict as _finalize_qa_verdict,
)
from .retro_aggregate import (
    aggregate_retro_metrics as _aggregate_retro_metrics,
)
from .evolve_aggregate import (
    aggregate_evolve_context as _aggregate_evolve_context,
)
from .interview_aggregate import (
    aggregate_interview_state as _aggregate_interview_state,
)
from .council_synthesis import (
    synthesize_council_verdicts as _synthesize_council_verdicts,
)
from .brownfield_analyzer import (
    analyze_brownfield_project as _analyze_brownfield_project,
)
from .manifest import (
    build_manifest,
    write_manifest,
    manifest_path,
    read_manifest as _read_manifest_file,
    render_for_context,
)
from .pattern_registry import (
    get_pattern as _get_pattern,
    list_patterns as _list_patterns,
    render_patterns as _render_patterns,
)
from .domain_packs import (
    get_domain_pack as _get_domain_pack,
    list_domain_packs as _list_domain_packs,
    match_domain_packs as _match_domain_packs,
    render_domain_packs as _render_domain_packs,
)
from .module_boundary import (
    validate_contract as _validate_contract,
    enforce_boundary as _enforce_boundary,
    aggregate_module_state as _aggregate_module_state,
)
from .retro_v3_2 import (
    ExperimentRun as _ExperimentRun,
    Observation as _Observation,
    PolicyExperiment as _PolicyExperiment,
    RetroReport as _RetroReport,
    load_retro as _load_retro,
    promote as _retro_promote,
    reject as _retro_reject,
    save_retro as _save_retro,
)
from .interview_v3_2 import (
    InterviewLevel,
    build_adversarial_prompt as _build_adv_prompt,
    build_meta_probe_prompt as _build_meta_prompt,
    compute_seed_readiness as _compute_seed_readiness_core,
    confidence_follow_up as _confidence_follow_up,
    pal_select_level as _pal_select_level,
    parse_meta_probe_result as _parse_meta_result,
    resolve_level as _resolve_level,
    scenario_simulate as _scenario_simulate,
    techniques_for_level as _techniques_for_level,
)
from .narrate import (
    build_context as _build_narrate_context,
    build_narrate_prompt as _build_narrate_prompt,
    parse_narrative as _parse_narrative,
)
from .orchestrator import (
    OrchestratorError,
    StageEvent as _OrchestratorStageEvent,
    aggregate_orchestrator_state as _aggregate_orchestrator_state,
    complete_stage_plan as _complete_stage_plan,
    get_next_stage as _orchestrator_get_next_stage,
    get_orchestration_state as _orchestrator_get_state,
    should_skip_stage as _orchestrator_should_skip_stage,
    stage_can_proceed as _orchestrator_stage_can_proceed,
)
from .event_store import EventStore
from .gates import (
    DEFAULT_CONFIG as GATE_DEFAULT_CONFIG,
    GateName,
    gate_check as _gate_check_core,
    load_config as _load_gate_config,
    should_force_user_decision as _should_force_user_decision,
)
from .host import (
    chain_strategy as _host_chain_strategy,
    resolve_host_capability as _resolve_host_capability,
)
from .host_adapters import (
    get_adapter as _get_adapter,
    get_chain_continuation as _get_chain_continuation,
    list_adapters as _list_adapters,
)
from .chain_markers import (
    advance_chain as _advance_chain,
    clear_chain_marker as _clear_chain_marker,
    get_pipeline_status as _get_pipeline_status,
    read_chain_marker as _read_chain_marker,
    write_chain_marker as _write_chain_marker,
)
from .health_tiers import (
    get_health_tier as _get_health_tier,
    get_health_tier_summary as _get_health_tier_summary,
)
from .regression_suite import (
    snapshot_generation as _snapshot_generation,
    validate_against_snapshot as _validate_against_snapshot,
    aggregate_regression_state as _aggregate_regression_state,
    compare_generations as _compare_generations,
)
from .model_role import (
    ModelRole,
    agents_by_role as _agents_by_role,
    inventory as _role_inventory,
    validate_role_separation as _validate_role_separation_core,
)
from .models import Event, EventType, Session, SeedVersion, Stage
from .routing import (
    CostTier,
    DEFAULT_PROFILES,
    RoutingError,
    downgrade_from_budget as _downgrade_from_budget,
    escalation_from_attempts as _escalation_from_attempts,
    load_profiles as _load_profiles,
    load_role_overrides as _load_role_overrides,
    route_task as _route_task_core,
    validate_profiles as _validate_profiles_core,
)
from .telemetry import (
    append_retro_observations as _append_retro_observations,
    build_run_report as _build_run_report,
    derive_retro_observations as _derive_retro_observations,
    read_run_report as _read_run_report_file,
    render_run_report as _render_run_report,
    write_run_report as _write_run_report,
)
from .repair import (
    build_repair_report as _build_repair_report,
    read_repair_report as _read_repair_report_file,
    render_repair_report as _render_repair_report,
)
from .release import (
    build_release_evidence_bundle as _build_release_evidence_bundle,
    build_release_report as _build_release_report,
    evaluate_release_gate as _evaluate_release_gate,
    read_release_evidence_bundle as _read_release_evidence_bundle_file,
    read_release_report as _read_release_report_file,
    render_release_evidence_bundle as _render_release_evidence_bundle,
    render_release_report as _render_release_report,
    run_release_checks as _run_release_checks,
    write_release_evidence_bundle as _write_release_evidence_bundle,
    write_release_report as _write_release_report,
)

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
async def create_session(
    project_name: str,
    samvil_tier: str = "standard",
    agent_tier: str | None = None,  # glossary-allow: deprecated alias, removed in v3.3
) -> str:
    """Create a new SAMVIL session for a project. Returns session ID.

    v3.2: the legacy parameter was renamed to ``samvil_tier`` in the
    glossary sweep. The old parameter name is still accepted for one
    minor-version window to avoid breaking in-flight skills, and
    dispatches to the same field. Emits a health warning when the legacy
    name is used.
    """
    try:
        from .security import sanitize_filename, detect_dangerous
        if agent_tier is not None:  # glossary-allow: deprecated-param shim
            _log_mcp_health(
                "fail",
                "create_session",
                "deprecated parameter agent_tier; use samvil_tier",  # glossary-allow: warning text
            )
            samvil_tier = agent_tier  # glossary-allow: deprecated-param shim
        detected = detect_dangerous(project_name)
        if detected:
            return json.dumps({"session_id": None, "error": f"Blocked patterns: {detected}"})
        project_name = sanitize_filename(project_name, max_len=100)
        store = await get_store()
        session = await store.create_session(project_name, samvil_tier)
        return json.dumps({"session_id": session.id, "project_name": project_name, "tier": samvil_tier})
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
        "samvil_tier": session.samvil_tier,
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


# ── Event tools ───────────────────────────────────────────────


# ── v3.2 L1.5 — save_event auto-posts contract-layer claims ─────────
#
# Our Sprint 6 dogfood showed that Claude's Skill invocation does not
# reliably trigger PreToolUse/PostToolUse hooks under the current plugin
# runtime, which left .samvil/claims.jsonl empty. Instead of relying on
# the hook layer alone, we piggyback on `save_event` — a tool the
# existing v3.1 skills already call at every stage transition — and
# synthesize claim ledger rows there. This gives the contract layer a
# **deterministic backup path**: even if the shell hook never fires, the
# ledger still fills as long as skills call `save_event`, which they do.
#
# Lenient EventType — v3.1 skills sometimes invent types ("interview_
# start", "seed_generated"). We accept any string now; unknown types are
# stored under the enum value "stage_change" so the existing schema
# stays valid, with the raw name preserved in data.event_type_raw.


# Mapping built from `scripts/audit-save-event-callers.sh` — every
# event_type string grepped out of skills/*/SKILL.md is categorized below.
# Keep this in sync when adding a new save_event call.
_STAGE_ENTRY_EVENTS = {
    # generic
    "stage_start",
    # per-stage entry markers actually emitted by v3.1 skills
    "interview_start",
    "seed_started",
    "council_started",
    "design_started",
    "scaffold_started",
    "build_feature_start",
    "feature_tree_start",
    "feature_start",
    "qa_started",
    "deploy_started",
    "retro_started",
}
_STAGE_EXIT_EVENTS = {
    # generic
    "stage_end",
    "stage_change",
    # interview
    "interview_complete",
    # seed / pm seed
    "seed_generated",
    "pm_seed_complete",
    "pm_seed_converted",
    # analyze (brownfield mode)
    "analyze_complete",
    # council
    "council_complete",
    "council_verdict",
    # design
    "design_complete",
    "blueprint_generated",
    "blueprint_feasibility_checked",
    # scaffold
    "scaffold_complete",
    # build
    "build_pass",
    "build_stage_complete",
    "build_feature_success",
    "feature_tree_complete",
    # qa
    "qa_pass",
    "qa_revise",
    "qa_fail",
    "qa_verdict",
    "qa_partial",
    "qa_blocked",
    "qa_unimplemented",
    "ac_satisfied_externally",
    # evolve
    "evolve_converge",
    "evolve_gen",
    # deploy
    "deploy_complete",
    # retro
    "retro_complete",
}
_STAGE_FAIL_EVENTS = {
    "build_fail",
    "build_feature_fail",
    "feature_failed",
    "stall_detected",
    "stall_abandoned",
    "rate_budget_starved",
}


def _resolve_project_path(project_name: str | None) -> "Path | None":
    """Best-effort lookup of a SAMVIL project dir given the session's
    project_name. Convention: `~/dev/<name>`."""
    if not project_name:
        return None
    guess = Path.home() / "dev" / project_name
    return guess if guess.exists() else None


# Map event_type → canonical stage name. The v3.1 skill convention is
# that `save_event(event_type, stage, ...)` uses `stage` as the NEXT
# stage (what the pipeline is transitioning into). For claim subjects we
# need the stage that this event is ABOUT — derived from event_type.
#
# Without this, `save_event("interview_complete", stage="seed", ...)`
# gets mapped to subject=`stage:seed` and never matches the pending
# `stage:interview` entry claim, so verify never fires. The Sprint 6
# dogfood surfaced this.
_EVENT_TYPE_TO_STAGE: dict[str, str] = {
    "interview_start": "interview",
    "interview_complete": "interview",
    "seed_started": "seed",
    "seed_generated": "seed",
    "pm_seed_complete": "seed",
    "pm_seed_converted": "seed",
    "analyze_complete": "interview",  # brownfield analyze lives in interview
    "council_started": "council",
    "council_complete": "council",
    "council_verdict": "council",
    "design_started": "design",
    "design_complete": "design",
    "blueprint_generated": "design",
    "blueprint_feasibility_checked": "design",
    "blueprint_concern": "design",
    "scaffold_started": "scaffold",
    "scaffold_complete": "scaffold",
    "feature_tree_start": "build",
    "feature_tree_complete": "build",
    "build_feature_start": "build",
    "build_feature_success": "build",
    "build_feature_fail": "build",
    "build_pass": "build",
    "build_fail": "build",
    "build_stage_complete": "build",
    "fix_applied": "build",
    "feature_start": "build",
    "feature_failed": "build",
    "qa_started": "qa",
    "qa_pass": "qa",
    "qa_revise": "qa",
    "qa_fail": "qa",
    "qa_verdict": "qa",
    "qa_partial": "qa",
    "qa_blocked": "qa",
    "qa_unimplemented": "qa",
    "ac_satisfied_externally": "qa",
    "deploy_started": "deploy",
    "deploy_complete": "deploy",
    "retro_started": "retro",
    "retro_complete": "retro",
    "evolve_converge": "evolve",
    "evolve_gen": "evolve",
}


def _canonical_stage_for_event(event_type_raw: str, fallback_stage: str) -> str:
    """Return the pipeline stage this event is about. Falls back to the
    `stage` arg the skill passed when no explicit mapping exists."""
    et = (event_type_raw or "").strip().lower()
    if et in _EVENT_TYPE_TO_STAGE:
        return _EVENT_TYPE_TO_STAGE[et]
    # Prefix match — handles new event types whose name starts with the
    # stage name (e.g. "interview_foo" → "interview").
    for prefix in (
        "interview",
        "seed",
        "council",
        "design",
        "scaffold",
        "build",
        "qa",
        "deploy",
        "retro",
        "evolve",
    ):
        if et.startswith(prefix + "_") or et == prefix:
            return prefix
    return (fallback_stage or "unknown").lower()


async def _auto_post_claim_for_event(
    session_id: str,
    event_type_raw: str,
    stage: str,
    data: dict,
) -> None:
    """Best-effort append to the project's .samvil/claims.jsonl based on
    the event type. Never raises — on failure we log to health and move
    on. This runs alongside the v3.1 event write so nothing regresses."""
    try:
        store = await get_store()
        session = await store.get_session(session_id)
        if session is None:
            return
        project_path = _resolve_project_path(session.project_name)
        if project_path is None:
            return
        ledger = ClaimLedger(project_path / ".samvil" / "claims.jsonl")

        # Derive the canonical stage name from event_type, not from the
        # `stage` arg (which is the NEXT stage per v3.1 skill convention).
        canonical_stage = _canonical_stage_for_event(event_type_raw, stage)
        subject = f"stage:{canonical_stage}"
        et = event_type_raw.lower()

        if et in _STAGE_ENTRY_EVENTS:
            ledger.post(
                type="evidence_posted",
                subject=subject,
                statement=f"{event_type_raw} @ {stage}",
                authority_file="project.state.json",
                claimed_by=f"agent:orchestrator-agent",
                evidence=["project.state.json"],
                meta={"via": "save_event", "event_type": event_type_raw},
            )
        elif et in _STAGE_EXIT_EVENTS:
            # Verify the most recent stage_start claim (if any) and post
            # a gate_verdict claim if we have enough signal.
            pending = [
                c
                for c in ledger.query_by_subject(subject)
                if c.status == "pending" and c.type == "evidence_posted"
            ]
            if pending:
                target = sorted(pending, key=lambda c: c.ts)[-1]
                try:
                    ledger.verify(
                        target.claim_id,
                        verified_by="agent:user",
                        evidence=[f"event:{event_type_raw}"],
                        skip_file_resolution=True,
                    )
                except ClaimLedgerError:
                    pass
            # Gate verdict synthesis (light: PASS if event is *_pass /
            # *_complete, else leave untagged).
            verdict = "pass" if et.endswith("_pass") or et.endswith("_complete") else "unknown"
            ledger.post(
                type="gate_verdict",
                subject=f"gate:{canonical_stage}_exit",
                statement=f"verdict={verdict} via {event_type_raw}",
                authority_file="state.json",
                claimed_by="agent:orchestrator-agent",
                evidence=["project.state.json"],
                meta={
                    "verdict": verdict,
                    "event_type": event_type_raw,
                    "data": data,
                },
            )
        elif et in _STAGE_FAIL_EVENTS:
            ledger.post(
                type="evidence_posted",
                subject=subject,
                statement=f"{event_type_raw} failure @ {stage}",
                authority_file="project.state.json",
                claimed_by="agent:orchestrator-agent",
                evidence=["project.state.json"],
                meta={"via": "save_event", "failure": True, "event_type": event_type_raw},
            )
        # Other event types: not stage transitions; skip.
    except Exception as e:
        _log_mcp_health("fail", "save_event.auto_claim", str(e))


@mcp.tool()
async def save_event(
    session_id: str,
    event_type: str,
    stage: str,
    data: str = "{}",
    token_count: int | None = None,
) -> str:
    """Save a pipeline event. data is a JSON string. token_count is
    optional estimated token usage.

    v3.2: the event_type is lenient — unknown types are stored as
    ``stage_change`` with the original name preserved in
    ``data.event_type_raw``. In addition, a contract-layer claim is
    auto-posted to the project's .samvil/claims.jsonl when the event
    matches a stage transition (deterministic backup when the plugin
    hook path fails).
    """
    try:
        parsed_data = json.loads(data) if data else {}

        # Lenient EventType: try the enum, fall back to STAGE_CHANGE.
        try:
            event_type_enum = EventType(event_type)
        except ValueError:
            event_type_enum = EventType.STAGE_CHANGE
            parsed_data.setdefault("event_type_raw", event_type)

        # Lenient Stage: fall back to STAGE_CHANGE's stage if unknown.
        try:
            stage_enum = Stage(stage)
        except ValueError:
            stage_enum = Stage.INTERVIEW  # default rather than crash
            parsed_data.setdefault("stage_raw", stage)

        store = await get_store()
        event = await store.save_event(
            session_id=session_id,
            event_type=event_type_enum,
            stage=stage_enum,
            data=parsed_data,
            token_count=token_count,
        )
        # Update session's current stage
        await store.update_session_stage(session_id, stage_enum)

        # v3.2 contract-layer auto-claim (best-effort, never blocks).
        await _auto_post_claim_for_event(
            session_id, event_type, stage, parsed_data
        )

        _log_mcp_health("ok", "save_event")
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
            "samvil_tier": session.samvil_tier,
        },
        "event_summary": event_counts,
        "total_events": len(events),
        "total_tokens": total_tokens if total_tokens > 0 else None,
    })


# ── Orchestrator (v3.3) ───────────────────────────────────────


def _events_to_orchestrator(events: list[Event]) -> list[_OrchestratorStageEvent]:
    # EventStore returns newest first; orchestrator status is chronological.
    ordered = sorted(events, key=lambda event: event.timestamp)
    return [
        _OrchestratorStageEvent(
            event_type=event.data.get("event_type_raw", event.event_type.value),
            stage=event.stage.value,
            data=event.data,
            timestamp=event.timestamp,
        )
        for event in ordered
    ]


async def _session_and_events(session_id: str) -> tuple[Session | None, list[_OrchestratorStageEvent]]:
    store = await get_store()
    session = await store.get_session(session_id)
    if session is None:
        return None, []
    events = await store.get_events(session_id, limit=1000)
    return session, _events_to_orchestrator(events)


@mcp.tool()
async def get_next_stage(current: str, samvil_tier: str) -> str:
    """Return the next non-skipped stage for a tier."""
    try:
        next_stage = _orchestrator_get_next_stage(current, samvil_tier)
        _log_mcp_health("ok", "get_next_stage")
        return json.dumps({"next_stage": next_stage})
    except OrchestratorError as e:
        _log_mcp_health("fail", "get_next_stage", str(e))
        return json.dumps({"error": str(e), "next_stage": None})


@mcp.tool()
async def should_skip_stage(stage: str, samvil_tier: str) -> str:
    """Return whether a stage should be skipped for a tier."""
    try:
        skip = _orchestrator_should_skip_stage(stage, samvil_tier)
        _log_mcp_health("ok", "should_skip_stage")
        return json.dumps({"skip": skip})
    except OrchestratorError as e:
        _log_mcp_health("fail", "should_skip_stage", str(e))
        return json.dumps({"error": str(e), "skip": None})


@mcp.tool()
async def stage_can_proceed(session_id: str, target_stage: str) -> str:
    """Return whether target_stage can proceed for a session."""
    try:
        session, events = await _session_and_events(session_id)
        if session is None:
            return json.dumps({
                "can_proceed": False,
                "blockers": [f"session {session_id} not found"],
            })
        result = _orchestrator_stage_can_proceed(session, events, target_stage)
        _log_mcp_health("ok", "stage_can_proceed")
        return json.dumps(result)
    except OrchestratorError as e:
        _log_mcp_health("fail", "stage_can_proceed", str(e))
        return json.dumps({"can_proceed": False, "blockers": [str(e)]})


@mcp.tool()
async def get_orchestration_state(session_id: str) -> str:
    """Return event-derived orchestration progress for a session."""
    try:
        session, events = await _session_and_events(session_id)
        if session is None:
            return json.dumps({"error": f"session {session_id} not found"})
        state = _orchestrator_get_state(session, events)
        _log_mcp_health("ok", "get_orchestration_state")
        return json.dumps(state)
    except OrchestratorError as e:
        _log_mcp_health("fail", "get_orchestration_state", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def complete_stage(session_id: str, stage: str, verdict: str) -> str:
    """Complete a stage by emitting an event and posting a gate claim."""
    try:
        store = await get_store()
        session = await store.get_session(session_id)
        if session is None:
            return json.dumps({"status": "error", "error": f"session {session_id} not found"})

        plan = _complete_stage_plan(session, stage, verdict)
        event_data = dict(plan["event_data"])
        try:
            event_type_enum = EventType(plan["event_type"])
        except ValueError:
            event_type_enum = EventType.STAGE_CHANGE
            event_data.setdefault("event_type_raw", plan["event_type"])
        stage_enum = Stage(plan["event_stage"])

        event = await store.save_event(
            session_id=session_id,
            event_type=event_type_enum,
            stage=stage_enum,
            data=event_data,
        )
        await store.update_session_stage(session_id, stage_enum)

        claim_id = None
        project_path = _resolve_project_path(session.project_name)
        if project_path is not None:
            claim_data = plan["claim"]
            ledger = ClaimLedger(project_path / ".samvil" / "claims.jsonl")
            claim = ledger.post(
                type=claim_data["type"],
                subject=claim_data["subject"],
                statement=claim_data["statement"],
                authority_file=claim_data["authority_file"],
                claimed_by="agent:orchestrator-agent",
                evidence=claim_data["evidence"],
                meta=claim_data["meta"],
            )
            claim_id = claim.claim_id

        _log_mcp_health("ok", "complete_stage")
        return json.dumps({
            "status": "ok",
            "event_id": event.id,
            "claim_id": claim_id,
            "next_stage": plan["next_stage"],
        })
    except (OrchestratorError, ClaimLedgerError) as e:
        _log_mcp_health("fail", "complete_stage", str(e))
        return json.dumps({"status": "error", "error": str(e)})
    except Exception as e:
        _log_mcp_health("fail", "complete_stage", str(e))
        return json.dumps({"status": "error", "error": str(e)})


# ── Host Capability (v3.3) ───────────────────────────────────


@mcp.tool()
async def resolve_host_capability(host_name: str = "") -> str:
    """Return host capability data for Claude Code, Codex CLI, OpenCode, or generic."""
    try:
        cap = _resolve_host_capability(host_name)
        _log_mcp_health("ok", "resolve_host_capability")
        return json.dumps(cap.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "resolve_host_capability", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def host_chain_strategy(host_name: str = "") -> str:
    """Return the recommended next-skill chaining mechanism for a host."""
    try:
        cap = _resolve_host_capability(host_name)
        strategy = _host_chain_strategy(cap)
        _log_mcp_health("ok", "host_chain_strategy")
        return json.dumps({
            "host": cap.name,
            "chain_via": strategy,
            "file_marker": ".samvil/next-skill.json",
        })
    except Exception as e:
        _log_mcp_health("fail", "host_chain_strategy", str(e))
        return json.dumps({"error": str(e)})


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
async def synthesize_qa_evidence(evidence_json: str) -> str:
    """Centrally synthesize independent QA evidence into PASS/REVISE/FAIL.

    Args:
        evidence_json: JSON object with pass1, pass2.items, pass3, and optional agent_writes

    Returns: QA synthesis gate dict with verdict, reason, next_action, counts, and event drafts
    """
    try:
        from .qa_synthesis import synthesize_qa_evidence as _synthesize
        evidence = json.loads(evidence_json)
        return json.dumps(_synthesize(evidence))
    except Exception as e:
        _log_mcp_health("fail", "synthesize_qa_evidence", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_qa_synthesis(project_root: str, synthesis_json: str) -> str:
    """Persist QA synthesis into qa-results, qa-report, events, and state.

    Args:
        project_root: Project root containing .samvil/
        synthesis_json: JSON object returned by synthesize_qa_evidence

    Returns: materialization result with written paths and event count
    """
    try:
        from .qa_synthesis import materialize_qa_synthesis as _materialize
        synthesis = json.loads(synthesis_json)
        return json.dumps(_materialize(project_root, synthesis))
    except Exception as e:
        _log_mcp_health("fail", "materialize_qa_synthesis", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def evaluate_qa_convergence(project_root: str, synthesis_json: str) -> str:
    """Evaluate whether QA revise iterations are converging or blocked.

    Args:
        project_root: Project root containing project.state.json or .samvil/state.json
        synthesis_json: JSON object returned by synthesize_qa_evidence

    Returns: qa_convergence gate dict with verdict, reason, next_action, and issue deltas
    """
    try:
        from .qa_synthesis import evaluate_qa_convergence as _evaluate, _load_project_state
        synthesis = json.loads(synthesis_json)
        state = _load_project_state(Path(project_root))
        return json.dumps(_evaluate(synthesis, state.get("qa_history") or []))
    except Exception as e:
        _log_mcp_health("fail", "evaluate_qa_convergence", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def build_qa_recovery_routing(project_root: str) -> str:
    """Build the recommended next skill route for blocked QA convergence."""
    try:
        from .qa_routing import build_qa_recovery_routing as _build
        return json.dumps(_build(project_root))
    except Exception as e:
        _log_mcp_health("fail", "build_qa_recovery_routing", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_qa_recovery_routing(project_root: str, persist_next_skill: bool = True) -> str:
    """Persist QA recovery route and optional .samvil/next-skill.json marker."""
    try:
        from .qa_routing import materialize_qa_recovery_routing as _materialize
        return json.dumps(_materialize(project_root, persist_next_skill=persist_next_skill))
    except Exception as e:
        _log_mcp_health("fail", "materialize_qa_recovery_routing", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_evolve_context(project_root: str) -> str:
    """Persist file-based evolve intake context to .samvil/evolve-context.json."""
    try:
        from .evolve_loop import materialize_evolve_context as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_evolve_context", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_evolve_proposal(project_root: str) -> str:
    """Persist evolve proposal JSON and markdown report."""
    try:
        from .evolve_execution import materialize_evolve_proposal as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_evolve_proposal", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_evolve_apply_plan(project_root: str) -> str:
    """Persist evolve apply plan and evolved seed preview."""
    try:
        from .evolve_execution import materialize_evolve_apply_plan as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_evolve_apply_plan", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def apply_evolve_apply_plan(project_root: str) -> str:
    """Apply a ready evolve apply plan after current seed hash verification."""
    try:
        from .evolve_execution import apply_evolve_apply_plan as _apply
        return json.dumps(_apply(project_root))
    except Exception as e:
        _log_mcp_health("fail", "apply_evolve_apply_plan", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_evolve_rebuild_handoff(project_root: str) -> str:
    """Persist evolve rebuild handoff and .samvil/next-skill.json."""
    try:
        from .evolve_rebuild import materialize_evolve_rebuild_handoff as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_evolve_rebuild_handoff", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def build_rebuild_reentry(project_root: str) -> str:
    """Build scaffold reentry input from evolved seed and rebuild handoff."""
    try:
        from .evolve_reentry import build_rebuild_reentry as _build
        return json.dumps(_build(project_root))
    except Exception as e:
        _log_mcp_health("fail", "build_rebuild_reentry", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_rebuild_reentry(project_root: str) -> str:
    """Persist scaffold reentry contract and scaffold input."""
    try:
        from .evolve_reentry import materialize_rebuild_reentry as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_rebuild_reentry", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def build_post_rebuild_qa(project_root: str) -> str:
    """Build QA rejudge input from rebuilt evolved seed output."""
    try:
        from .post_rebuild_qa import build_post_rebuild_qa as _build
        return json.dumps(_build(project_root))
    except Exception as e:
        _log_mcp_health("fail", "build_post_rebuild_qa", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_post_rebuild_qa(project_root: str, persist_next_skill: bool = True) -> str:
    """Persist post-rebuild QA request and optional .samvil/next-skill.json marker."""
    try:
        from .post_rebuild_qa import materialize_post_rebuild_qa as _materialize
        return json.dumps(_materialize(project_root, persist_next_skill=persist_next_skill))
    except Exception as e:
        _log_mcp_health("fail", "materialize_post_rebuild_qa", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def build_final_e2e_bundle(project_root: str) -> str:
    """Build final E2E bundle from all evolve/rebuild/QA closure artifacts."""
    try:
        from .final_e2e import build_final_e2e_bundle as _build
        return json.dumps(_build(project_root))
    except Exception as e:
        _log_mcp_health("fail", "build_final_e2e_bundle", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def materialize_final_e2e_bundle(project_root: str) -> str:
    """Persist final E2E bundle."""
    try:
        from .final_e2e import materialize_final_e2e_bundle as _materialize
        return json.dumps(_materialize(project_root))
    except Exception as e:
        _log_mcp_health("fail", "materialize_final_e2e_bundle", str(e))
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
        from .convergence_check import check_all_gates, GateConfig
        eval_result = json.loads(eval_result_json)
        history = json.loads(history_json)
        verdict = check_all_gates(eval_result, history, GateConfig())
        return json.dumps(verdict.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "check_convergence_gates", str(e))
        return json.dumps({"converged": False, "error": str(e)})


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


# ── v3.2.0 Sprint 1 — Claim Ledger (①) ────────────────────────
#
# The ledger lives at `<project_root>/.samvil/claims.jsonl`. Every tool here
# takes an explicit `project_root` argument so one MCP instance can service
# multiple concurrent project directories. Callers (skills) pass the absolute
# or relative path. Graceful degradation: on failure we still log health and
# return an error payload — the pipeline never hard-crashes on ledger issues.


def _ledger_for(project_root: str) -> ClaimLedger:
    return ClaimLedger(Path(project_root) / ".samvil" / "claims.jsonl")


@mcp.tool()
async def claim_post(
    project_root: str,
    claim_type: str,
    subject: str,
    statement: str,
    authority_file: str,
    claimed_by: str,
    evidence_json: str = "[]",
    meta_json: str = "{}",
) -> str:
    """Append a new `pending` claim to the project's claim ledger.

    claim_type must be one of the typed whitelist (see claim_ledger.CLAIM_TYPES).
    Returns JSON: {"claim_id": "...", "status": "pending"} on success,
    {"error": "..."} on failure.
    """
    try:
        evidence = json.loads(evidence_json or "[]")
        meta = json.loads(meta_json or "{}")
        ledger = _ledger_for(project_root)
        claim = ledger.post(
            type=claim_type,
            subject=subject,
            statement=statement,
            authority_file=authority_file,
            claimed_by=claimed_by,
            evidence=evidence,
            meta=meta,
        )
        _log_mcp_health("ok", "claim_post")
        return json.dumps({"claim_id": claim.claim_id, "status": claim.status})
    except Exception as e:
        _log_mcp_health("fail", "claim_post", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def claim_verify(
    project_root: str,
    claim_id: str,
    verified_by: str,
    evidence_json: str = "[]",
    skip_file_resolution: bool = False,
) -> str:
    """Flip a pending claim to `verified`. Enforces Generator ≠ Judge and
    resolves file:line evidence against `project_root`.

    Returns JSON: {"claim_id": "...", "status": "verified", "evidence": [...]}
    on success, {"error": "..."} on failure.
    """
    try:
        evidence = json.loads(evidence_json or "[]")
        ledger = _ledger_for(project_root)
        claim = ledger.verify(
            claim_id,
            verified_by=verified_by,
            evidence=evidence,
            project_root=project_root,
            skip_file_resolution=skip_file_resolution,
        )
        _log_mcp_health("ok", "claim_verify")
        return json.dumps(
            {
                "claim_id": claim.claim_id,
                "status": claim.status,
                "evidence": claim.evidence,
                "verified_by": claim.verified_by,
            }
        )
    except ClaimLedgerError as e:
        _log_mcp_health("fail", "claim_verify", str(e))
        return json.dumps({"error": str(e)})
    except Exception as e:
        _log_mcp_health("fail", "claim_verify", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def claim_reject(
    project_root: str,
    claim_id: str,
    verified_by: str,
    reason: str = "",
) -> str:
    """Flip a pending claim to `rejected`. Reason stored under meta.reject_reason."""
    try:
        ledger = _ledger_for(project_root)
        claim = ledger.reject(claim_id, verified_by=verified_by, reason=reason)
        _log_mcp_health("ok", "claim_reject")
        return json.dumps(
            {"claim_id": claim.claim_id, "status": claim.status, "reason": reason}
        )
    except Exception as e:
        _log_mcp_health("fail", "claim_reject", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 1 — Gate framework (⑥) ──────────────────────
#
# `gate_check` is the single entry point. Callers gather runtime metrics
# (seed_readiness from interview_engine, implementation_rate from build,
# etc.) and invoke this tool. On non-pass, callers branch on `verdict` and
# `required_action.type`. The Judge role then writes a `gate_verdict` claim
# via `claim_post` so the result is auditable and G ≠ J is enforced.


def _config_path_for(project_root: str) -> str | None:
    """Resolve gate_config.yaml from the project first, then the repo root."""
    candidates = [
        Path(project_root) / ".samvil" / "gate_config.yaml",
        Path(project_root) / "gate_config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Fall back to packaged default (references/gate_config.yaml at repo root).
    repo_default = Path(__file__).resolve().parents[2] / "references" / "gate_config.yaml"
    return str(repo_default) if repo_default.exists() else None


@mcp.tool()
async def gate_check(
    gate_name: str,
    samvil_tier: str,
    metrics_json: str,
    project_root: str = ".",
    subject: str = "",
    allow_warn: bool = False,
) -> str:
    """Evaluate a stage gate. Returns the verdict as JSON.

    Verdict schema:
      {
        "gate": "build_to_qa",
        "verdict": "pass" | "block" | "escalate" | "skip",
        "samvil_tier": "standard",
        "threshold": { "implementation_rate": 0.85 },
        "failed_checks": [...],
        "reason": "human-readable",
        "required_action": { "type": "split_ac" | ..., "payload": {...} }
      }
    """
    try:
        from dataclasses import asdict

        metrics = json.loads(metrics_json or "{}")
        cfg_path = _config_path_for(project_root)
        cfg = _load_gate_config(cfg_path) if cfg_path else _load_gate_config(None)
        verdict = _gate_check_core(
            gate_name,
            samvil_tier=samvil_tier,
            metrics=metrics,
            subject=subject,
            config=cfg,
            allow_warn=allow_warn,
        )
        _log_mcp_health("ok", "gate_check")
        return json.dumps(asdict(verdict))
    except Exception as e:
        _log_mcp_health("fail", "gate_check", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def gate_should_force_user(
    gate_name: str,
    subject: str,
    failed_check: str,
    history_json: str,
) -> str:
    """Escalation loop safety. Returns {"force_user": bool}.

    Same check escalating twice for the same subject forces a user decision
    (no infinite loop). Caller passes the prior verdicts for that subject.
    """
    try:
        history = json.loads(history_json or "[]")
        force = _should_force_user_decision(
            gate=gate_name,
            subject=subject,
            failed_check=failed_check,
            history=history,
        )
        _log_mcp_health("ok", "gate_should_force_user")
        return json.dumps({"force_user": force})
    except Exception as e:
        _log_mcp_health("fail", "gate_should_force_user", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 2 — Model routing (④) ───────────────────────
#
# The routing module lives at `samvil_mcp.routing`. These MCP tools are
# thin wrappers that let skills ask for a routing decision and validate
# their profile file. Callers record the returned decision as a
# `policy_adoption` claim — Sprint 3 wires that into the build/QA skills.


def _profiles_path_for(project_root: str) -> str | None:
    """Resolve .samvil/model_profiles.yaml from the project; fall back to
    the packaged defaults reference yaml at repo root."""
    p = Path(project_root) / ".samvil" / "model_profiles.yaml"
    if p.exists():
        return str(p)
    repo_default = (
        Path(__file__).resolve().parents[2]
        / "references"
        / "model_profiles.defaults.yaml"
    )
    return str(repo_default) if repo_default.exists() else None


@mcp.tool()
async def route_task(
    task_role: str,
    project_root: str = ".",
    requested_cost_tier: str = "",
    attempts: int = 0,
    consumed_json: str = "{}",
    ceiling_json: str = "{}",
    downgrade_threshold: float = 0.80,
) -> str:
    """Pick a model for the given task_role and return the decision.

    * `requested_cost_tier`: optional override ("frugal" | "balanced" |
      "frontier"). Empty string uses the role default.
    * `attempts`: number of prior failures for this subject (controls
      escalation depth).
    * `consumed_json` / `ceiling_json`: performance budget snapshot used
      to compute downgrade pressure.
    """
    try:
        profiles_path = _profiles_path_for(project_root)
        profiles = _load_profiles(profiles_path)
        overrides = _load_role_overrides(profiles_path)

        requested: CostTier | None = None
        if requested_cost_tier:
            try:
                requested = CostTier(requested_cost_tier)
            except ValueError:
                return json.dumps(
                    {
                        "error": (
                            f"unknown cost_tier {requested_cost_tier!r}; "
                            "expected frugal|balanced|frontier"
                        )
                    }
                )

        consumed = json.loads(consumed_json or "{}")
        ceiling = json.loads(ceiling_json or "{}")
        budget_pressure = _downgrade_from_budget(consumed, ceiling)
        escalation_depth = _escalation_from_attempts(attempts)

        decision = _route_task_core(
            task_role=task_role,
            profiles=profiles,
            role_overrides=overrides,
            requested_cost_tier=requested,
            escalation_depth=escalation_depth,
            budget_pressure=budget_pressure,
            downgrade_threshold=downgrade_threshold,
        )
        _log_mcp_health("ok", "route_task")
        return json.dumps(decision.to_dict())
    except RoutingError as e:
        _log_mcp_health("fail", "route_task", str(e))
        return json.dumps({"error": str(e)})
    except Exception as e:
        _log_mcp_health("fail", "route_task", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def validate_profiles(project_root: str = ".") -> str:
    """Validate the project's model_profiles.yaml. Returns
    {"issues": [...]}. Empty list means valid.
    """
    try:
        profiles_path = _profiles_path_for(project_root)
        profiles = _load_profiles(profiles_path)
        issues = _validate_profiles_core(profiles)
        _log_mcp_health("ok", "validate_profiles")
        return json.dumps({"issues": issues, "profiles_path": profiles_path})
    except Exception as e:
        _log_mcp_health("fail", "validate_profiles", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 3 — Role primitive (⑤) ──────────────────────


@mcp.tool()
async def validate_role_separation(claimed_by: str, verified_by: str) -> str:
    """Enforce Generator ≠ Judge at the semantic layer.

    The claim ledger already blocks `verified_by == claimed_by`. This
    tool adds the role-level check: verified_by must resolve to a Judge
    role (or an out-of-band verifier like user / orchestrator), and a
    Judge cannot self-claim.
    """
    try:
        r = _validate_role_separation_core(
            claimed_by=claimed_by,
            verified_by=verified_by,
        )
        _log_mcp_health("ok", "validate_role_separation")
        return json.dumps(
            {
                "valid": r.valid,
                "reason": r.reason,
                "claimed_role": r.claimed_role.value if r.claimed_role else None,
                "verified_role": r.verified_role.value if r.verified_role else None,
            }
        )
    except Exception as e:
        _log_mcp_health("fail", "validate_role_separation", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def list_model_roles() -> str:
    """Return the full role inventory. Used by ROLE-INVENTORY.md render
    and by retro when auditing drift.
    """
    try:
        _log_mcp_health("ok", "list_model_roles")
        return json.dumps(
            {
                "inventory": _role_inventory(),
                "rollup": _agents_by_role(),
            }
        )
    except Exception as e:
        _log_mcp_health("fail", "list_model_roles", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 3 — AC leaf schema (③) ──────────────────────


@mcp.tool()
async def validate_ac_leaf(leaf_json: str, stage: str) -> str:
    """Validate one AC leaf against its required fields for the given
    pipeline stage (interview / seed / design / build / qa).

    Returns `{"issues": [...]}`. Empty list means valid.
    """
    try:
        d = json.loads(leaf_json)
        leaf = ACLeaf.from_dict(d)
        stage_enum = ACStage(stage)
        issues = _validate_leaf_core(leaf, stage=stage_enum)
        _log_mcp_health("ok", "validate_ac_leaf")
        return json.dumps(
            {
                "issues": [
                    {"field": i.field, "code": i.code, "message": i.message}
                    for i in issues
                ]
            }
        )
    except ValueError as e:
        _log_mcp_health("fail", "validate_ac_leaf", str(e))
        return json.dumps({"error": f"bad input: {e}"})
    except Exception as e:
        _log_mcp_health("fail", "validate_ac_leaf", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def compute_parallel_safety(leaves_json: str) -> str:
    """Compute parallel_safety for a batch of leaves. Input is a JSON
    list of leaf dicts (must have `id`, `likely_files`, `shared_resources`).

    Returns `{"safety": {"AC-1.1": true, ...}}`.
    """
    try:
        rows = json.loads(leaves_json)
        leaves = [ACLeaf.from_dict(r) for r in rows]
        safety = _compute_parallel_safety(leaves)
        _log_mcp_health("ok", "compute_parallel_safety")
        return json.dumps({"safety": safety})
    except Exception as e:
        _log_mcp_health("fail", "compute_parallel_safety", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 4 — Interview (②) + narrate ─────────────────


@mcp.tool()
async def compute_seed_readiness(
    dimensions_json: str,
    samvil_tier: str = "standard",
) -> str:
    """Compute the multi-dimensional seed_readiness score (T1).

    `dimensions_json` is a JSON object with keys `intent_clarity`,
    `constraint_clarity`, `ac_testability`, `lifecycle_coverage`,
    `decision_boundary` (values in [0, 1]).
    """
    try:
        dims = json.loads(dimensions_json)
        score = _compute_seed_readiness_core(dims, samvil_tier=samvil_tier)
        _log_mcp_health("ok", "compute_seed_readiness")
        return json.dumps(score.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "compute_seed_readiness", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def meta_probe_prompt(phase: str, answers_summary: str) -> str:
    """Build the T2 Meta Self-Probe prompt. Caller runs the LLM and pipes
    the raw response into `meta_probe_parse`.
    """
    try:
        prompt = _build_meta_prompt(phase=phase, answers_summary=answers_summary)
        _log_mcp_health("ok", "meta_probe_prompt")
        return json.dumps({"prompt": prompt})
    except Exception as e:
        _log_mcp_health("fail", "meta_probe_prompt", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def scenario_simulation(features_json: str) -> str:
    """Run the T4 scenario simulation. Returns a list of steps with any
    contradictions found."""
    try:
        features = json.loads(features_json)
        steps = _scenario_simulate(features=features)
        _log_mcp_health("ok", "scenario_simulation")
        from dataclasses import asdict

        return json.dumps({"steps": [asdict(s) for s in steps]})
    except Exception as e:
        _log_mcp_health("fail", "scenario_simulation", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def adversarial_prompt(summary: str, samvil_tier: str = "standard") -> str:
    """Build the T5 adversarial interviewer prompt."""
    try:
        prompt = _build_adv_prompt(summary=summary, samvil_tier=samvil_tier)
        _log_mcp_health("ok", "adversarial_prompt")
        return json.dumps({"prompt": prompt})
    except Exception as e:
        _log_mcp_health("fail", "adversarial_prompt", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def narrate_build_prompt(project_root: str = ".", since: str = "") -> str:
    """Assemble the narrate context and build the Compressor prompt.

    Returns `{"prompt": "...", "context_summary": "..."}`. Caller runs
    the LLM and pipes the response through `narrate_parse`.
    """
    try:
        ctx = _build_narrate_context(project_root, since=since or None)
        prompt = _build_narrate_prompt(ctx)
        _log_mcp_health("ok", "narrate_build_prompt")
        return json.dumps(
            {"prompt": prompt, "context_summary": ctx.to_summary()}
        )
    except Exception as e:
        _log_mcp_health("fail", "narrate_build_prompt", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def narrate_parse(raw: str) -> str:
    """Parse a narrate response. Returns `{"narrative": {...},
    "markdown": "..."}`."""
    try:
        n = _parse_narrative(raw)
        _log_mcp_health("ok", "narrate_parse")
        return json.dumps(
            {
                "narrative": {
                    "what_happened": n.what_happened,
                    "where_stuck": n.where_stuck,
                    "next_actions": n.next_actions,
                },
                "markdown": n.to_markdown(),
            }
        )
    except Exception as e:
        _log_mcp_health("fail", "narrate_parse", str(e))
        return json.dumps({"error": str(e)})


# ── v3.2.0 Sprint 5a — Jurisdiction (⑦) + Retro (⑧) ──────────


@mcp.tool()
async def check_jurisdiction(
    action_description: str = "",
    command: str = "",
    filenames_json: str = "[]",
    diff_text: str = "",
) -> str:
    """Return jurisdiction (ai / external / user) for a candidate action.

    Strictest-wins resolution. Callers branch on the verdict — AI
    autonomous, External lookup required, or User explicit confirmation.
    """
    try:
        filenames = json.loads(filenames_json or "[]")
        v = _check_jurisdiction_core(
            action_description=action_description,
            command=command,
            filenames=filenames,
            diff_text=diff_text,
        )
        _log_mcp_health("ok", "check_jurisdiction")
        return json.dumps(v.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "check_jurisdiction", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def loop_should_stop(
    last_failure_signature: str,
    failure_history_json: str,
    ac_mutation_needed: bool = False,
    seed_contradiction: bool = False,
    irreversible_next: bool = False,
    model_confidence_below: bool = False,
) -> str:
    """Auto-stop checker. Returns `{"stop": bool, "reason": "..."}`."""
    try:
        history = json.loads(failure_history_json or "[]")
        stop, reason = _loop_should_stop(
            last_failure_signature=last_failure_signature,
            failure_history=history,
            ac_mutation_needed=ac_mutation_needed,
            seed_contradiction=seed_contradiction,
            irreversible_next=irreversible_next,
            model_confidence_below=model_confidence_below,
        )
        _log_mcp_health("ok", "loop_should_stop")
        return json.dumps({"stop": stop, "reason": reason})
    except Exception as e:
        _log_mcp_health("fail", "loop_should_stop", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def retro_load(path: str) -> str:
    """Load a retro report. Returns the serialized dict form."""
    try:
        r = _load_retro(path)
        _log_mcp_health("ok", "retro_load")
        return json.dumps(r.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "retro_load", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def retro_save(path: str, report_json: str) -> str:
    """Persist a retro report to disk (YAML preferred, JSON fallback)."""
    try:
        data = json.loads(report_json)
        r = _retro_from_dict(data)
        _save_retro(r, path)
        _log_mcp_health("ok", "retro_save")
        return json.dumps({"ok": True, "path": str(path)})
    except Exception as e:
        _log_mcp_health("fail", "retro_save", str(e))
        return json.dumps({"error": str(e)})


def _retro_from_dict(d: dict) -> _RetroReport:
    # Thin wrapper so callers can pass plain dicts.
    from .retro_v3_2 import _from_dict  # local import to avoid leaking name

    return _from_dict(d)


# ── v3.2.0 Sprint 5b — Stagnation (⑩) + Consensus (⑨) ─────────


@mcp.tool()
async def stagnation_evaluate(input_json: str) -> str:
    """Run the stagnation detector on a per-cycle snapshot.

    Input shape matches `StagnationInput` — see
    `mcp/samvil_mcp/stagnation_v3_2.py` for fields.
    """
    try:
        data = json.loads(input_json or "{}")
        inp = StagnationInput(**data)
        v = _stagnation_evaluate(inp)
        _log_mcp_health("ok", "stagnation_evaluate")
        return json.dumps(v.to_dict())
    except TypeError as e:
        # Unknown fields in input_json → user error, not a 500.
        _log_mcp_health("fail", "stagnation_evaluate", str(e))
        return json.dumps({"error": f"bad input shape: {e}"})
    except Exception as e:
        _log_mcp_health("fail", "stagnation_evaluate", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def lateral_propose(subject: str, verdict_json: str) -> str:
    """Build the lateral-diagnosis prompt for a stagnation=HIGH subject.

    `verdict_json` is the `StagnationVerdict.to_dict()` output.
    """
    try:
        from .stagnation_v3_2 import StagnationVerdict

        data = json.loads(verdict_json)
        v = StagnationVerdict(**data)
        prompt = _lateral_prompt(subject=subject, verdict=v)
        _log_mcp_health("ok", "lateral_propose")
        return json.dumps({"prompt": prompt})
    except Exception as e:
        _log_mcp_health("fail", "lateral_propose", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def consensus_trigger(input_json: str) -> str:
    """Detect whether a dispute should invoke consensus.

    Input shape matches `DisputeInput`. Output:
      {"triggers": [...], "should_invoke": bool, "reason": "..."}
    """
    try:
        data = json.loads(input_json or "{}")
        inp = DisputeInput(**data)
        d = _detect_dispute(inp)
        _log_mcp_health("ok", "consensus_trigger")
        return json.dumps(d.to_dict())
    except TypeError as e:
        _log_mcp_health("fail", "consensus_trigger", str(e))
        return json.dumps({"error": f"bad input shape: {e}"})
    except Exception as e:
        _log_mcp_health("fail", "consensus_trigger", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def consensus_reviewer_prompt(
    subject: str, triggers_json: str, context: str = ""
) -> str:
    """Build the Reviewer prompt for a dispute."""
    try:
        triggers = json.loads(triggers_json or "[]")
        p = _consensus_reviewer_prompt(
            subject=subject, triggers=triggers, context=context
        )
        _log_mcp_health("ok", "consensus_reviewer_prompt")
        return json.dumps({"prompt": p})
    except Exception as e:
        _log_mcp_health("fail", "consensus_reviewer_prompt", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def consensus_judge_prompt(
    subject: str, triggers_json: str, reviewer_position: str
) -> str:
    """Build the Judge prompt using the Reviewer's position."""
    try:
        triggers = json.loads(triggers_json or "[]")
        p = _consensus_judge_prompt(
            subject=subject,
            triggers=triggers,
            reviewer_position=reviewer_position,
        )
        _log_mcp_health("ok", "consensus_judge_prompt")
        return json.dumps({"prompt": p})
    except Exception as e:
        _log_mcp_health("fail", "consensus_judge_prompt", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def council_deprecation_warning() -> str:
    """Return the one-line deprecation notice for v3.1 `--council` users."""
    _log_mcp_health("ok", "council_deprecation_warning")
    return json.dumps({"warning": COUNCIL_DEPRECATION_WARNING})


# ── v3.2.0 Sprint 6 — Migration (⑫) + Budget (⑬) ──────────────


@mcp.tool()
async def migrate_plan(project_root: str = ".") -> str:
    """Return the v3.1 → v3.2 migration plan without writing."""
    try:
        plan = _plan_migration(project_root)
        _log_mcp_health("ok", "migrate_plan")
        return json.dumps(plan.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "migrate_plan", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def migrate_apply(project_root: str = ".", dry_run: bool = False) -> str:
    """Run the migration. `dry_run=true` only prints the plan."""
    try:
        plan = _apply_migration(project_root, dry_run=dry_run)
        _log_mcp_health("ok", "migrate_apply")
        return json.dumps(plan.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "migrate_apply", str(e))
        return json.dumps({"error": str(e)})


# ── Codebase Manifest (v3.3) ──────────────────────────────────────────


def _validate_project_root(project_root: str) -> dict | None:
    """Return an error dict if project_root is invalid, else None.

    Empty strings would silently pollute the MCP server's CWD; nonexistent
    paths would silently materialise a directory tree on write. Both are
    unsafe for the AI's first interaction surface, so we reject them here.
    """
    if not project_root:
        return {"status": "error", "error": "project_root is empty"}
    root = Path(project_root)
    if not root.is_dir():
        return {
            "status": "error",
            "error": f"project_root not a directory: {project_root!r}",
        }
    return None


def _build_and_persist_manifest_impl(
    project_root: str,
    project_name: str,
) -> dict:
    """Build the manifest from filesystem and write to .samvil/manifest.json."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    m = build_manifest(project_root, project_name=project_name)
    write_manifest(m, project_root)
    return {
        "status": "ok",
        "module_count": len(m.modules),
        "convention_count": len(m.conventions),
        "path": str(manifest_path(project_root)),
    }


def _read_manifest_impl(project_root: str) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    p = manifest_path(project_root)
    if not p.exists():
        return {"status": "missing"}
    m = _read_manifest_file(project_root)
    if m is None:
        # File exists but couldn't parse — corrupted or unreadable.
        return {"status": "corrupted", "path": str(p)}
    return {"status": "ok", "manifest": m.to_dict()}


def _render_manifest_context_impl(
    project_root: str,
    focus: list[str] | None = None,
    max_modules: int = 30,
) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    p = manifest_path(project_root)
    if not p.exists():
        return {"status": "missing"}
    m = _read_manifest_file(project_root)
    if m is None:
        return {"status": "corrupted", "path": str(p)}
    text = render_for_context(m, focus=focus, max_modules=max_modules)
    return {"status": "ok", "context": text, "module_count": len(m.modules)}


@mcp.tool()
def build_and_persist_manifest(project_root: str, project_name: str) -> dict:
    """Build a Codebase Manifest and write it to .samvil/manifest.json.

    Args:
        project_root: absolute path to the project directory.
        project_name: human-readable project name.

    Returns:
        dict with status, module_count, convention_count, path.
    """
    try:
        result = _build_and_persist_manifest_impl(project_root, project_name)
        _log_mcp_health("ok", "build_and_persist_manifest")
        return result
    except Exception as e:
        _log_mcp_health("fail", "build_and_persist_manifest", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_manifest(project_root: str) -> dict:
    """Read .samvil/manifest.json. Returns {status: 'missing'} if absent."""
    try:
        result = _read_manifest_impl(project_root)
        _log_mcp_health("ok", "read_manifest")
        return result
    except Exception as e:
        _log_mcp_health("fail", "read_manifest", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_manifest_context(
    project_root: str,
    focus: list[str] | None = None,
    max_modules: int = 30,
) -> dict:
    """Render manifest as a compressed markdown summary for AI context.

    Args:
        project_root: absolute path.
        focus: optional list of module names to include (others omitted).
        max_modules: hard cap; default 30.
    """
    try:
        result = _render_manifest_context_impl(project_root, focus, max_modules)
        _log_mcp_health("ok", "render_manifest_context")
        return result
    except Exception as e:
        _log_mcp_health("fail", "render_manifest_context", str(e))
        return {"status": "error", "error": str(e)}


# ── Pattern Registry (v3.4) ─────────────────────────────────────────


@mcp.tool()
def list_patterns(
    solution_type: str = "",
    framework: str = "",
    category: str = "",
) -> dict:
    """List Pattern Registry entries, optionally filtered."""
    try:
        patterns = _list_patterns(
            solution_type=solution_type or None,
            framework=framework or None,
            category=category or None,
        )
        _log_mcp_health("ok", "list_patterns")
        return {
            "status": "ok",
            "count": len(patterns),
            "patterns": [p.to_dict() for p in patterns],
        }
    except Exception as e:
        _log_mcp_health("fail", "list_patterns", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_pattern(pattern_id: str) -> dict:
    """Read one Pattern Registry entry by id."""
    try:
        pattern = _get_pattern(pattern_id)
        _log_mcp_health("ok", "read_pattern")
        if pattern is None:
            return {"status": "missing"}
        return {"status": "ok", "pattern": pattern.to_dict()}
    except Exception as e:
        _log_mcp_health("fail", "read_pattern", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_pattern_context(
    solution_type: str = "",
    framework: str = "",
    category: str = "",
) -> dict:
    """Render matching Pattern Registry entries as compact markdown context."""
    try:
        patterns = _list_patterns(
            solution_type=solution_type or None,
            framework=framework or None,
            category=category or None,
        )
        _log_mcp_health("ok", "render_pattern_context")
        return {
            "status": "ok",
            "count": len(patterns),
            "context": _render_patterns(patterns),
        }
    except Exception as e:
        _log_mcp_health("fail", "render_pattern_context", str(e))
        return {"status": "error", "error": str(e)}


# ── Domain Packs (v3.6) ─────────────────────────────────────────────


@mcp.tool()
def list_domain_packs(
    solution_type: str = "",
    domain: str = "",
    stage: str = "",
) -> dict:
    """List Domain Pack entries, optionally filtered."""
    try:
        packs = _list_domain_packs(
            solution_type=solution_type or None,
            domain=domain or None,
            stage=stage or None,
        )
        _log_mcp_health("ok", "list_domain_packs")
        return {
            "status": "ok",
            "count": len(packs),
            "packs": [pack.to_dict() for pack in packs],
        }
    except Exception as e:
        _log_mcp_health("fail", "list_domain_packs", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_domain_pack(pack_id: str) -> dict:
    """Read one Domain Pack entry by id."""
    try:
        pack = _get_domain_pack(pack_id)
        _log_mcp_health("ok", "read_domain_pack")
        if pack is None:
            return {"status": "missing"}
        return {"status": "ok", "pack": pack.to_dict()}
    except Exception as e:
        _log_mcp_health("fail", "read_domain_pack", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_domain_context(
    solution_type: str = "",
    domain: str = "",
    stage: str = "",
) -> dict:
    """Render matching Domain Pack entries as compact markdown context."""
    try:
        packs = _list_domain_packs(
            solution_type=solution_type or None,
            domain=domain or None,
            stage=stage or None,
        )
        _log_mcp_health("ok", "render_domain_context")
        return {
            "status": "ok",
            "count": len(packs),
            "context": _render_domain_packs(packs, stage=stage or None),
        }
    except Exception as e:
        _log_mcp_health("fail", "render_domain_context", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def match_domain_packs(seed_json: str) -> dict:
    """Rank Domain Packs from deterministic seed fields and text signals."""
    try:
        seed = json.loads(seed_json)
        if not isinstance(seed, dict):
            return {"status": "error", "error": "seed_json must be an object"}
        matches = _match_domain_packs(seed)
        _log_mcp_health("ok", "match_domain_packs")
        return {
            "status": "ok",
            "count": len(matches),
            "matches": matches,
        }
    except Exception as e:
        _log_mcp_health("fail", "match_domain_packs", str(e))
        return {"status": "error", "error": str(e)}


# ── Run Telemetry (v3.5) ────────────────────────────────────────────


@mcp.tool()
def build_run_report(
    project_root: str,
    persist: bool = True,
    mcp_health_path: str = "",
) -> dict:
    """Build a run telemetry report from project-local .samvil files."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _build_run_report(
            project_root,
            mcp_health_path=mcp_health_path or None,
        )
        path = ""
        if persist:
            path = str(_write_run_report(report, project_root))
        _log_mcp_health("ok", "build_run_report")
        return {"status": "ok", "path": path, "report": report}
    except Exception as e:
        _log_mcp_health("fail", "build_run_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_run_report(project_root: str) -> dict:
    """Read .samvil/run-report.json if present."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _read_run_report_file(project_root)
        _log_mcp_health("ok", "read_run_report")
        if report is None:
            return {"status": "missing"}
        return {"status": "ok", "report": report}
    except Exception as e:
        _log_mcp_health("fail", "read_run_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_run_report(project_root: str, refresh: bool = False) -> dict:
    """Render a run report as markdown; optionally refresh it first."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _build_run_report(project_root) if refresh else _read_run_report_file(project_root)
        if report is None:
            return {"status": "missing"}
        text = _render_run_report(report)
        _log_mcp_health("ok", "render_run_report")
        return {"status": "ok", "context": text}
    except Exception as e:
        _log_mcp_health("fail", "render_run_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def derive_retro_observations(
    project_root: str,
    refresh: bool = False,
    persist: bool = False,
) -> dict:
    """Derive actionable retro observation candidates from a run report."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _build_run_report(project_root) if refresh else _read_run_report_file(project_root)
        if report is None:
            return {"status": "missing"}
        observations = _derive_retro_observations(report)
        path = ""
        if persist:
            path = str(_append_retro_observations(project_root, observations))
        _log_mcp_health("ok", "derive_retro_observations")
        return {
            "status": "ok",
            "count": len(observations),
            "path": path,
            "observations": observations,
        }
    except Exception as e:
        _log_mcp_health("fail", "derive_retro_observations", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def append_retro_observations(project_root: str, observations_json: str) -> dict:
    """Append selected retro observations to .samvil/retro-observations.jsonl."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        data = json.loads(observations_json)
        observations = data if isinstance(data, list) else data.get("observations", [])
        if not isinstance(observations, list):
            return {"status": "error", "error": "observations_json must contain a list"}
        path = _append_retro_observations(project_root, observations)
        _log_mcp_health("ok", "append_retro_observations")
        return {"status": "ok", "count": len(observations), "path": str(path)}
    except Exception as e:
        _log_mcp_health("fail", "append_retro_observations", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_repair_report(project_root: str) -> dict:
    """Read .samvil/repair-report.json if present."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _read_repair_report_file(project_root)
        _log_mcp_health("ok", "read_repair_report")
        if report is None:
            return {"status": "missing"}
        return {"status": "ok", "report": report}
    except Exception as e:
        _log_mcp_health("fail", "read_repair_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_repair_report(project_root: str, refresh: bool = False) -> dict:
    """Render a repair report as markdown; optionally refresh it first."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _build_repair_report(project_root) if refresh else _read_repair_report_file(project_root)
        if report is None:
            return {"status": "missing"}
        _log_mcp_health("ok", "render_repair_report")
        return {"status": "ok", "context": _render_repair_report(report)}
    except Exception as e:
        _log_mcp_health("fail", "render_repair_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def build_release_report(project_root: str, checks_json: str = "", persist: bool = True) -> dict:
    """Build a release readiness report from release check evidence."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        checks = []
        if checks_json:
            data = json.loads(checks_json)
            checks = data if isinstance(data, list) else data.get("checks", [])
            if not isinstance(checks, list):
                return {"status": "error", "error": "checks_json must contain a list"}
        report = _build_release_report(project_root, checks=checks)
        path = ""
        if persist:
            path = str(_write_release_report(report, project_root))
        _log_mcp_health("ok", "build_release_report")
        return {"status": "ok", "path": path, "report": report}
    except Exception as e:
        _log_mcp_health("fail", "build_release_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_release_report(project_root: str) -> dict:
    """Read .samvil/release-report.json if present."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        report = _read_release_report_file(project_root)
        _log_mcp_health("ok", "read_release_report")
        if report is None:
            return {"status": "missing"}
        return {"status": "ok", "report": report}
    except Exception as e:
        _log_mcp_health("fail", "read_release_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_release_report(project_root: str, refresh: bool = False, checks_json: str = "") -> dict:
    """Render release readiness as markdown; optionally refresh it first."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        if refresh:
            checks = []
            if checks_json:
                data = json.loads(checks_json)
                checks = data if isinstance(data, list) else data.get("checks", [])
                if not isinstance(checks, list):
                    return {"status": "error", "error": "checks_json must contain a list"}
            report = _build_release_report(project_root, checks=checks)
        else:
            report = _read_release_report_file(project_root)
        if report is None:
            return {"status": "missing"}
        _log_mcp_health("ok", "render_release_report")
        return {"status": "ok", "context": _render_release_report(report)}
    except Exception as e:
        _log_mcp_health("fail", "render_release_report", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def evaluate_release_gate(project_root: str) -> dict:
    """Evaluate whether release readiness blocks final progression."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        gate = _evaluate_release_gate(project_root)
        _log_mcp_health("ok", "evaluate_release_gate")
        return {"status": "ok", "gate": gate}
    except Exception as e:
        _log_mcp_health("fail", "evaluate_release_gate", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def run_release_checks(project_root: str, commands_json: str = "", persist: bool = True) -> dict:
    """Run release check commands and write a runner-generated release report."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        commands = None
        if commands_json:
            data = json.loads(commands_json)
            commands = data if isinstance(data, list) else data.get("commands", [])
            if not isinstance(commands, list):
                return {"status": "error", "error": "commands_json must contain a list"}
        report = _run_release_checks(project_root, commands=commands, persist=persist)
        gate = _evaluate_release_gate(project_root, release_report=report)
        _log_mcp_health("ok", "run_release_checks")
        return {"status": "ok", "report": report, "gate": gate}
    except Exception as e:
        _log_mcp_health("fail", "run_release_checks", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def build_release_evidence_bundle(project_root: str, persist: bool = True) -> dict:
    """Build a markdown release evidence bundle from the latest release report."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        bundle = _build_release_evidence_bundle(project_root)
        path = ""
        if persist:
            path = str(_write_release_evidence_bundle(bundle, project_root))
        _log_mcp_health("ok", "build_release_evidence_bundle")
        return {"status": "ok", "path": path, "bundle": bundle}
    except Exception as e:
        _log_mcp_health("fail", "build_release_evidence_bundle", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_release_evidence_bundle(project_root: str) -> dict:
    """Read .samvil/release-summary.md if present."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        context = _read_release_evidence_bundle_file(project_root)
        _log_mcp_health("ok", "read_release_evidence_bundle")
        if context is None:
            return {"status": "missing"}
        return {"status": "ok", "context": context}
    except Exception as e:
        _log_mcp_health("fail", "read_release_evidence_bundle", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def render_release_evidence_bundle(project_root: str, refresh: bool = False) -> dict:
    """Render release evidence bundle context; optionally refresh it first."""
    err = _validate_project_root(project_root)
    if err is not None:
        return err
    try:
        if refresh:
            bundle = _build_release_evidence_bundle(project_root)
            context = _render_release_evidence_bundle(bundle)
        else:
            context = _read_release_evidence_bundle_file(project_root)
        if context is None:
            return {"status": "missing"}
        _log_mcp_health("ok", "render_release_evidence_bundle")
        return {"status": "ok", "context": context}
    except Exception as e:
        _log_mcp_health("fail", "render_release_evidence_bundle", str(e))
        return {"status": "error", "error": str(e)}


# ── Decision Log / ADR (v3.3) ────────────────────────────────────────


def _decision_adr_from_json(adr_json: str) -> DecisionADR:
    data = json.loads(adr_json)
    if "adr_id" in data and "id" not in data:
        data["id"] = data.pop("adr_id")
    return DecisionADR.from_dict(data)


def _write_decision_adr_impl(project_root: str, adr_json: str) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        adr = _decision_adr_from_json(adr_json)
        path = _write_decision_adr(adr, project_root)
        return {"status": "ok", "adr_id": adr.adr_id, "path": str(path)}
    except (json.JSONDecodeError, KeyError, TypeError, DecisionLogError) as e:
        return {"status": "error", "error": str(e)}


def _read_decision_adr_impl(project_root: str, adr_id: str) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        path = _decision_adr_path(project_root, adr_id)
    except DecisionLogError as e:
        return {"status": "error", "error": str(e)}
    if not path.exists():
        return {"status": "missing"}

    adr = _read_decision_adr(project_root, adr_id)
    if adr is None:
        return {"status": "corrupted", "path": str(path)}
    return {"status": "ok", "adr": adr.to_dict()}


def _list_decision_adrs_impl(project_root: str, status: str | None = None) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        adrs = _list_decision_adrs(project_root, status=status)
    except DecisionLogError as e:
        return {"status": "error", "error": str(e)}
    return {
        "status": "ok",
        "count": len(adrs),
        "adrs": [adr.to_dict() for adr in adrs],
    }


def _supersede_decision_adr_impl(
    project_root: str,
    old_id: str,
    new_id: str,
    reason: str,
) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        adr = _supersede_decision_adr(project_root, old_id, new_id, reason)
        return {"status": "ok", "adr": adr.to_dict()}
    except DecisionLogError as e:
        return {"status": "error", "error": str(e)}


def _find_decision_adrs_referencing_impl(project_root: str, target: str) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        adr_ids = _find_adrs_referencing(project_root, target)
        return {"status": "ok", "count": len(adr_ids), "adr_ids": adr_ids}
    except DecisionLogError as e:
        return {"status": "error", "error": str(e)}


def _promote_council_decision_impl(project_root: str, decision_json: str) -> dict:
    err = _validate_project_root(project_root)
    if err is not None:
        return err

    try:
        decision = json.loads(decision_json)
        adr = _adr_from_council_decision(decision)
        path = _write_decision_adr(adr, project_root)
        return {"status": "ok", "adr": adr.to_dict(), "path": str(path)}
    except (json.JSONDecodeError, TypeError, DecisionLogError) as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def write_decision_adr(project_root: str, adr_json: str) -> dict:
    """Write one decision ADR markdown file under `.samvil/decisions/`."""
    try:
        result = _write_decision_adr_impl(project_root, adr_json)
        _log_mcp_health("ok", "write_decision_adr")
        return result
    except Exception as e:
        _log_mcp_health("fail", "write_decision_adr", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def read_decision_adr(project_root: str, adr_id: str) -> dict:
    """Read one decision ADR by id."""
    try:
        result = _read_decision_adr_impl(project_root, adr_id)
        _log_mcp_health("ok", "read_decision_adr")
        return result
    except Exception as e:
        _log_mcp_health("fail", "read_decision_adr", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def list_decision_adrs(project_root: str, status: str | None = None) -> dict:
    """List decision ADRs, optionally filtered by status."""
    try:
        result = _list_decision_adrs_impl(project_root, status)
        _log_mcp_health("ok", "list_decision_adrs")
        return result
    except Exception as e:
        _log_mcp_health("fail", "list_decision_adrs", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def supersede_decision_adr(
    project_root: str,
    old_id: str,
    new_id: str,
    reason: str,
) -> dict:
    """Mark an existing decision ADR as superseded by another ADR."""
    try:
        result = _supersede_decision_adr_impl(project_root, old_id, new_id, reason)
        _log_mcp_health("ok", "supersede_decision_adr")
        return result
    except Exception as e:
        _log_mcp_health("fail", "supersede_decision_adr", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def find_decision_adrs_referencing(project_root: str, target: str) -> dict:
    """Find ADR ids that mention target in evidence, tags, or body text."""
    try:
        result = _find_decision_adrs_referencing_impl(project_root, target)
        _log_mcp_health("ok", "find_decision_adrs_referencing")
        return result
    except Exception as e:
        _log_mcp_health("fail", "find_decision_adrs_referencing", str(e))
        return {"status": "error", "error": str(e)}


@mcp.tool()
def promote_council_decision(project_root: str, decision_json: str) -> dict:
    """Promote a legacy council decision JSON row into an ADR markdown file."""
    try:
        result = _promote_council_decision_impl(project_root, decision_json)
        _log_mcp_health("ok", "promote_council_decision")
        return result
    except Exception as e:
        _log_mcp_health("fail", "promote_council_decision", str(e))
        return {"status": "error", "error": str(e)}


# ── Diagnostic aggregator (T3.1, samvil-doctor) ───────────────


@mcp.tool()
async def diagnose_environment() -> str:
    """Aggregate MCP-side facts the samvil-doctor skill needs.

    Returns a JSON string with:
      - mcp_health: summary of ~/.samvil/mcp-health.jsonl
      - tool_inventory: registered tool names + v3 expected coverage
      - model_recommendation: per-stage model recommendation table
    """
    try:
        result = await _diagnose_environment_async(mcp_server=mcp)
        _log_mcp_health("ok", "diagnose_environment")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "diagnose_environment", str(e))
        return json.dumps({"error": str(e)})


# ── Deploy target evaluator (T3.4, samvil-deploy) ─────────────


@mcp.tool()
async def evaluate_deploy_target(
    project_root: str,
    platform: str = "",
) -> str:
    """Aggregate the deploy-readiness facts samvil-deploy needs.

    Reads `project.state.json`, `project.seed.json`, and `.env.example`
    from `project_root` and returns a JSON string with:
      - qa_gate: pass/blocked verdict + reason (QA must be PASS).
      - platforms: per-`solution_type` deploy-target catalog rows.
      - selected_platform: caller-pinned, then seed-pinned, then
        recommended catalog entry.
      - env_vars: required keys + placeholder/missing keys parsed from
        `.env.example`.
      - build_artifact: existence check for `.next/` (web-app/dashboard)
        or `dist/` (game).
      - ready: bool — true only when no blockers remain.
      - blockers: human-readable strings the skill renders to the user.

    `platform` is optional — empty string means "let MCP pick".
    """
    try:
        result = _evaluate_deploy_target(
            project_root,
            platform=platform or None,
        )
        _log_mcp_health("ok", "evaluate_deploy_target")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "evaluate_deploy_target", str(e))
        return json.dumps({"error": str(e)})


# ── Scaffold target evaluator (T4.7, samvil-scaffold) ─────────


@mcp.tool()
async def evaluate_scaffold_target(
    project_path: str,
    framework: str = "",
    seed_json: str = "",
    run_sanity_checks: bool = False,
) -> str:
    """Aggregate the scaffold-readiness facts samvil-scaffold needs.

    Reads `project.seed.json` from `project_path` (or accepts a
    pre-loaded `seed_json` string) and `references/dependency-matrix.json`
    from the SAMVIL repo, then returns a JSON string with:
      - framework: resolved framework name (caller arg → seed →
        solution_type default → `nextjs`).
      - framework_source: which input determined the framework.
      - cli_command: ready-to-run scaffold CLI with `<seed.name>`
        substituted.
      - post_install_steps: ordered checklist the skill renders.
      - sanity_checks: Phase A.6 file/contents requirements.
      - sanity_result: present only when `run_sanity_checks=True` and
        the project tree exists.
      - build_command + build_log_path: per-stack INV-2 build line.
      - version_pins: matrix-derived pins for post-install verification.
      - env_vars_needed: per-stack `.env.example` keys.
      - existing_project: incremental-scaffold detection (`package.json`
        / `requirements.txt` / `SKILL.md` signal).
      - notes / blockers: human-readable diagnostics.

    `framework` is optional — empty string means "let MCP pick from seed".
    `seed_json` is optional — empty string means "read project.seed.json".
    """
    try:
        seed_dict: dict | None = None
        if seed_json:
            try:
                seed_dict = json.loads(seed_json)
            except json.JSONDecodeError as exc:
                return json.dumps({"error": f"invalid seed_json: {exc}"})

        result = _evaluate_scaffold_target(
            project_path,
            framework=framework or None,
            seed=seed_dict,
            run_sanity_checks=bool(run_sanity_checks),
        )
        _log_mcp_health("ok", "evaluate_scaffold_target")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "evaluate_scaffold_target", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def analyze_brownfield_project(
    project_root: str,
    project_name: str = "",
) -> str:
    """Aggregate every fact samvil-analyze needs to reverse-engineer a seed.

    Reads `package.json` (or pyproject.toml), config files, and walks `src/`
    to detect:
      - framework / language / runtime / package_manager (with signal source)
      - UI library, state management, data sources
      - solution_type (web-app / mobile-app / game / automation / dashboard)
      - feature modules (each becomes a v3 seed feature with status=existing)
      - confidence tags (high / medium / low) per inferred field
      - ADR-EXISTING-NNN entries explaining each heuristic decision

    Returns a JSON string shaped per `BrownfieldReport.to_dict()`:
      - seed: complete v3.0-shaped reverse-seed dict ready to write
      - confidence_tags: per-field confidence (skill renders for review)
      - adrs: ADR-EXISTING-NNN entries the skill appends to decisions.log
      - summary_lines: pre-formatted Korean lines for the analysis pane
      - warnings: re-confirm-with-user items (unknown framework, no features)

    `project_name` is optional — falls back to package.json:name then to
    the directory's basename.
    """
    try:
        result = _analyze_brownfield_project(
            project_root,
            project_name=project_name or None,
        )
        _log_mcp_health("ok", "analyze_brownfield_project")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "analyze_brownfield_project", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_retro_metrics(
    project_root: str,
    plugin_root: str = "",
    suggestion_major: int = 3,
) -> str:
    """Aggregate the run-feedback facts samvil-retro needs.

    Reads (best-effort) from `project_root`:
      - `project.seed.json`, `project.state.json`
      - `.samvil/metrics.json`, `.samvil/events.jsonl`
      - `.samvil/mcp-health.jsonl`
      - `interview-summary.md`

    And `harness-feedback.log` from `plugin_root` (or auto-detected
    cache path) for cross-run pattern detection + ID assignment.

    Returns a JSON string with:
      - metrics: per-run counters + stage durations + bottlenecks.
      - recurring_patterns: keywords seen in 3+ historical suggestions.
      - flow_compliance: planned vs. actual stage sequence.
      - agent_utilization: tier-configured vs. spawned agents.
      - v3_leaf_stats: AC tree leaf events grouped by status.
      - mcp_health: ok/fail counts + failed-tool top list.
      - next_suggestion_id: `v<major>-NNN` for the new entry.

    `suggestion_major` defaults to 3 (current schema). Bump when SAMVIL
    crosses a major-version boundary that resets ID space.
    """
    try:
        result = _aggregate_retro_metrics(
            project_root,
            plugin_root=plugin_root or "",
            suggestion_major=int(suggestion_major or 3),
        )
        _log_mcp_health("ok", "aggregate_retro_metrics")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_retro_metrics", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_evolve_context(project_root: str) -> str:
    """Boot-time aggregator for the samvil-evolve skill body (T4.2 ultra-thin).

    Reads (best-effort) from `project_root`:
      - `project.seed.json`, `project.state.json`, `project.config.json`
      - `.samvil/qa-results.json`
      - `interview-summary.md`

    Returns a JSON string with:
      - auto_trigger: whether Evolve should be auto-suggested + reasons.
      - mode: resolved evolve_mode + cycle/build quota state.
      - cycle: current cycle index + max + cap status.
      - four_dim_baseline: raw inputs for Quality/Intent/Purpose/Beyond eval.
      - errors: non-fatal warnings.

    Companion to existing `materialize_evolve_context`,
    `check_convergence_gates`, `record_qa_failure`, etc. — this tool covers
    the auto-trigger / mode / 4-dim pre-flight that were inline in the
    legacy 482-LOC skill body.
    """
    try:
        result = _aggregate_evolve_context(project_root)
        _log_mcp_health("ok", "aggregate_evolve_context")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_evolve_context", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_orchestrator_state(
    project_root: str = ".",
    prompt: str = "",
    cli_tier: str = "",
    mode_hint: str = "",
    host_name: str = "",
) -> str:
    """Boot-time aggregator for the samvil orchestrator skill (T4.5 ultra-thin).

    Reads (best-effort) from `project_root`:
      - `project.state.json`, `project.config.json`
      - filesystem artifacts (`project.seed.json`, `package.json`, `src/`)

    Returns a JSON string with:
      - tier: resolved samvil_tier with precedence cli > state > config > default
        (deprecated v3.1 'deep' alias is mapped to 'full' with `aliased_from`).
      - solution_type: 3-layer keyword/context detection
        (web-app | automation | game | mobile-app | dashboard).
        Layer-3 user confirmation still happens in the skill body.
      - is_pm_mode: true when the prompt contains PM-mode signals.
      - brownfield: artifact + state-based detection of resume / brownfield mode.
      - chain: which skill the orchestrator should invoke first
        (samvil-analyze | samvil-interview | samvil-pm-interview | resume target).
      - errors: non-fatal warnings (missing files, etc.)

    Companion to `get_orchestration_state` / `stage_can_proceed`. This tool
    covers the entry-point pre-flight (tier resolution, solution_type
    detection, brownfield/resume routing) that was inline in the legacy
    766-LOC orchestrator skill body.
    """
    try:
        result = _aggregate_orchestrator_state(
            project_root or ".",
            prompt=prompt or "",
            cli_tier=cli_tier or "",
            mode_hint=mode_hint or "",
            host_name=host_name or "",
        )
        _log_mcp_health("ok", "aggregate_orchestrator_state")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_orchestrator_state", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_interview_state(
    project_root: str = ".",
    prompt: str = "",
) -> str:
    """Boot-time aggregator for the samvil-interview skill (T4.6 ultra-thin).

    Reads (best-effort) from `project_root`:
      - `project.state.json` / `.samvil/state.json` (session_id + tier)
      - `project.config.json` (tier fallback)
      - `<project_root>/package.json` etc. via `scan_manifest`

    Reads (best-effort) from `~/.samvil/presets/*.json` (or
    `$SAMVIL_PRESET_DIR/*.json` when set).

    Returns a JSON string with:
      - tier: resolved interview tier (`minimal/standard/thorough/full/deep`)
        with precedence state > config > default.
      - ambiguity_target: float threshold matching `interview_engine`.
      - required_phases: list[str] in pipeline order
        (`core/scope/lifecycle/...`).
      - mode: `{is_zero_question, matched_signals}` from prompt scan.
      - preset: best-match preset (custom > built-in).
      - custom_presets_count: total `*.json` under preset dir.
      - manifest: `scan_manifest()` output (may be `{}` for greenfield).
      - paths: target locations for interview-summary.md, state.json,
        config.json, and the preset directory.
      - errors: non-fatal warnings.

    Companion to existing `score_ambiguity`, `route_question`,
    `update_answer_streak`, `manage_tracks`, `get_tier_phases`,
    `compute_seed_readiness`, `gate_check` — this tool covers the boot
    pre-flight (tier, mode, preset match, manifest scan) that was
    inline in the legacy 1259-LOC interview skill body.
    """
    try:
        result = _aggregate_interview_state(
            project_root or ".",
            prompt=prompt or "",
        )
        _log_mcp_health("ok", "aggregate_interview_state")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_interview_state", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def synthesize_council_verdicts(
    round1_verdicts_json: str = "",
    round2_verdicts_json: str = "",
) -> str:
    """Single-source-of-truth synthesis for Council Gate A (T4.3 ultra-thin).

    The samvil-council skill spawns Round 1 + Round 2 agents in parallel
    via the CC Agent tool (host-bound), then calls this tool to:

      1. Extract Round 1 debate points (consensus / debate / blind_spots)
         into a markdown block ready for Round 2 prompt injection.
      2. Aggregate Round 2 per-section verdicts into consensus scores
         (≥80% strong, 60-79% moderate, <60% weak), preserve dissenting
         opinions (Devil's Advocate), and surface BLOCKING-severity
         challenges as `blocking_objections`.
      3. Decide the overall verdict:
           PROCEED              — strong consensus on all sections.
           PROCEED_WITH_CHANGES — moderate consensus, no blocking.
           HOLD                 — weak consensus, blocking objection,
                                  or majority-reject on any section.

    Args:
      round1_verdicts_json: JSON-encoded list of Round 1 outputs:
        `[{"agent": "...", "topics": [{"topic": "...", "stance": "...",
        "is_blind_spot": bool}]}, ...]`. Empty → Round 1 was skipped
        (standard tier or below).
      round2_verdicts_json: JSON-encoded list of Round 2 outputs:
        `[{"agent": "...", "sections": [{"section": "...",
        "verdict": "approve|challenge|reject", "severity": "minor|blocking",
        "reasoning": "..."}]}, ...]`. Empty → no synthesis possible
        (returns well-formed empty result).

    Returns the synthesis dict described in
    `samvil_mcp.council_synthesis.synthesize_council_verdicts`. Pure
    function; idempotent; never raises.

    Companion to `consensus_v3_2.py` (which is the v3.3-bound dispute
    resolver). This tool is the legacy v3.1 Council Gate A that survives
    in v3.2 only behind the `--council` opt-in flag.
    """
    try:
        round1 = json.loads(round1_verdicts_json) if round1_verdicts_json else None
        round2 = json.loads(round2_verdicts_json) if round2_verdicts_json else None
        if round1 is not None and not isinstance(round1, list):
            round1 = None
        if round2 is not None and not isinstance(round2, list):
            round2 = None
        result = _synthesize_council_verdicts(
            round1_verdicts=round1,
            round2_verdicts=round2,
        )
        _log_mcp_health("ok", "synthesize_council_verdicts")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "synthesize_council_verdicts", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_build_phase_a(
    project_path: str = ".",
    run_sanity_checks: bool = True,
) -> str:
    """Boot-time aggregator for the samvil-build skill (T4.8 ultra-thin).

    Reads (best-effort) from `project_path`:
      - `project.seed.json` (solution_type, framework, features, name)
      - `project.state.json` (session_id, current_stage, completed_features)
      - `project.config.json` (samvil_tier, max_total_builds)
      - `project.blueprint.json` (architecture, key_libraries)

    Returns a JSON string with:
      - solution_type / framework: resolved from seed.
      - build_verify: per-stack {command, log_path, language} tuple.
      - recipe_path: per-`solution_type` recipe markdown reference.
      - paths: every file path the skill touches (handoff, fix-log,
        events, rate-budget, sanity log).
      - sanity: Phase A.6 result {passed, failures[], warnings[]}.
      - resume_hint: completed_features + last current_model_build for
        Worker dispatch.
      - errors / notes: non-fatal warnings.

    Companion to existing `route_task`, `render_pattern_context`,
    `render_domain_context`, `save_event`. This tool covers the boot
    pre-flight (stack identification, recipe lookup, sanity scan,
    resume detection) that was inline in the legacy 1432-LOC build
    skill body.
    """
    try:
        result = _aggregate_build_phase_a(
            project_path or ".",
            run_sanity_checks=bool(run_sanity_checks),
        )
        _log_mcp_health("ok", "aggregate_build_phase_a")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_build_phase_a", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def dispatch_build_batch(
    seed_json: str,
    feature_json: str,
    feature_num: int,
    tree_json: str,
    completed_ids_json: str = "[]",
    blueprint_json: str = "",
    config_json: str = "",
    consecutive_fail_batches: int = 0,
) -> str:
    """Per-batch dispatch aggregator for samvil-build Phase B (T4.8).

    Composes the next build batch for one feature: resolves
    MAX_PARALLEL (CPU + memory heuristic), picks the next leaves via
    `next_buildable_leaves`, and renders ≤2000-token Worker context
    bundles for each leaf so the skill body can spawn N agents in one
    parallel message.

    Args:
        seed_json: Loaded seed JSON string.
        feature_json: Single feature dict JSON string.
        feature_num: 1-based feature index.
        tree_json: Current AC tree JSON.
        completed_ids_json: JSON array of leaf IDs already done.
        blueprint_json: Optional blueprint JSON ("" → none).
        config_json: Optional config JSON ("" → none).
        consecutive_fail_batches: Carried from checkpoint or last
            iteration. ≥2 trips the circuit breaker.

    Returns: JSON string with `max_parallel`, `parallel_meta`, `batch`,
    `worker_bundles[]`, `independence` (when multiple features),
    `circuit_breaker {consecutive_fail_batches, max_retries, halt}`,
    `notes`, `errors`.
    """
    try:
        seed = json.loads(seed_json) if seed_json else {}
        feature = json.loads(feature_json) if feature_json else {}
        blueprint = json.loads(blueprint_json) if blueprint_json else None
        config = json.loads(config_json) if config_json else None
        completed_ids = json.loads(completed_ids_json) if completed_ids_json else []
        result = _dispatch_build_batch(
            seed=seed,
            blueprint=blueprint,
            config=config,
            feature=feature,
            feature_num=int(feature_num),
            tree_json=tree_json,
            completed_ids=completed_ids,
            consecutive_fail_batches=int(consecutive_fail_batches),
        )
        _log_mcp_health("ok", "dispatch_build_batch")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "dispatch_build_batch", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def finalize_build_phase_z(
    project_path: str = ".",
    rate_budget_stats_json: str = "",
    failed_features_json: str = "",
    retries: int = 0,
) -> str:
    """Post-stage finalize aggregator for samvil-build (T4.8).

    Runs ONCE at the end of the build stage. Owns the v3.2 Contract
    Layer post_stage prep: per-leaf `ac_verdict` claim payloads,
    `gate_check` input (implementation_rate), stagnation-evaluate
    hint, pre-rendered handoff.md block.

    Args:
        project_path: Project root.
        rate_budget_stats_json: Optional pre-fetched
            `rate_budget_stats(...)` result. Skill body passes it in
            to avoid a second roundtrip.
        failed_features_json: JSON array of feature names that hit
            the circuit breaker. Empty string → derive from leaf
            statuses.
        retries: Total retries in this build stage (for handoff).

    Returns: JSON string with `samvil_tier`, `metrics
    {features_total/passed/failed, implementation_rate,
    total/passed/failed/pending leaves}`, `ac_verdict_claims[]`,
    `stage_claim_id`, `gate_input`, `stagnation_hint`,
    `handoff_block`, `notes`, `errors`.
    """
    try:
        rate_budget_stats = (
            json.loads(rate_budget_stats_json) if rate_budget_stats_json else None
        )
        failed_features = (
            json.loads(failed_features_json) if failed_features_json else None
        )
        result = _finalize_build_phase_z(
            project_path or ".",
            rate_budget_stats=rate_budget_stats,
            failed_features=failed_features,
            retries=int(retries),
        )
        _log_mcp_health("ok", "finalize_build_phase_z")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "finalize_build_phase_z", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_qa_boot_context(
    project_path: str = ".",
) -> str:
    """Boot-time aggregator for samvil-qa (T4.9 ultra-thin migration).

    Single best-effort call collecting everything the now-thin samvil-qa
    SKILL needs at the **start** of QA: solution_type/framework, Pass 1
    mechanical command per stack, paths (seed/state/build_log/qa_results
    /qa_evidence/handoff/events), role-separation pre-check payload,
    incremental QA hint (prior qa-results.json summary), resume hint
    (selected_tier, qa_max_iterations, current_model_qa, qa_history
    length).

    Args:
        project_path: Project root (default cwd).

    Returns: JSON string with `solution_type`, `framework`, `pass1
    {command, log_path, language, smoke}`, `qa_checklist_path`, `paths`,
    `role_separation_check`, `incremental_hint`, `resume_hint`,
    `brownfield`, `notes[]`, `errors[]`.
    """
    try:
        result = _aggregate_qa_boot_context(project_path or ".")
        _log_mcp_health("ok", "aggregate_qa_boot_context")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_qa_boot_context", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def dispatch_qa_pass1_batch(
    project_path: str = ".",
    pass1_exit_code: int = 0,
    smoke_result_json: str = "",
    solution_type: str = "web-app",
    log_path_override: str = "",
) -> str:
    """Pass 1 (mechanical) + Pass 1b (smoke) digest for samvil-qa.

    Skill body shells out npm run build / npx tsc / py_compile and
    drives Playwright MCP probes; this tool **interprets** the
    artifacts: extracts real error lines from `.samvil/build.log`,
    reduces the smoke probe payload to PASS/FAIL/SKIPPED, decides
    whether Pass 2 should run, returns event drafts ready for
    `save_event`.

    Args:
        project_path: Repo root.
        pass1_exit_code: Exit code from the mechanical command.
        smoke_result_json: JSON `{method, console_errors, empty_routes,
            screenshots, fallback_reason}` or empty for skipped.
        solution_type: Selects smoke verdict shape.
        log_path_override: Custom build log path (default
            `<project_path>/.samvil/build.log`).

    Returns: JSON with `pass1 {status, exit_code, errors, reason,
    log_path}`, `pass1b {status, method, console_errors, empty_routes,
    screenshots, fallback_reason, reason}`, `should_proceed_to_pass2`,
    `verdict_reason`, `events[]`, `notes[]`, `errors[]`.
    """
    try:
        smoke_result = json.loads(smoke_result_json) if smoke_result_json else None
        result = _dispatch_qa_pass1_batch(
            project_path or ".",
            pass1_exit_code=int(pass1_exit_code),
            smoke_result=smoke_result,
            solution_type=solution_type or "web-app",
            log_path_override=log_path_override or None,
        )
        _log_mcp_health("ok", "dispatch_qa_pass1_batch")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "dispatch_qa_pass1_batch", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def finalize_qa_verdict(
    project_path: str = ".",
    evidence_json: str = "",
    pending_ac_claims_json: str = "",
) -> str:
    """QA Phase Z (post-stage) finalizer for samvil-qa.

    Aggregates: synthesize_qa_evidence + per-AC claim_verify/reject
    payloads + consensus_trigger payloads (Generator≠Judge dispute) +
    qa_to_deploy gate input + Ralph-loop BLOCKED detection from
    qa_history + next-skill decision (PASS→deploy/evolve, FAIL→retro)
    + Korean handoff block.

    The actual `materialize_qa_synthesis` (which writes qa-results.json,
    qa-report.md, events.jsonl, project.state.json) stays a separate
    MCP call so the skill body can preview before persisting.

    Args:
        project_path: Repo root.
        evidence_json: Same shape `synthesize_qa_evidence` consumes.
        pending_ac_claims_json: JSON array of pending build-stage
            ac_verdict claims (e.g., from `claim_query_by_subject`).

    Returns: JSON with `synthesis`, `convergence`, `claim_actions[]`,
    `consensus_triggers[]`, `gate_input`, `blocked
    {detected, persistent_issue_ids}`, `next_skill_decision
    {verdict, suggested, reason, user_options}`, `handoff_block`,
    `samvil_tier`, `notes[]`, `errors[]`.
    """
    try:
        evidence = json.loads(evidence_json) if evidence_json else {}
        pending = json.loads(pending_ac_claims_json) if pending_ac_claims_json else []
        result = _finalize_qa_verdict(
            project_path or ".",
            evidence=evidence,
            pending_ac_claims=pending,
        )
        _log_mcp_health("ok", "finalize_qa_verdict")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "finalize_qa_verdict", str(e))
        return json.dumps({"error": str(e)})


# ── Module Boundary (M1, samvil-build / samvil-qa) ─────────────


@mcp.tool()
async def validate_contract(project_root: str, module_name: str) -> str:
    """Validate a module's contract.json for schema compliance.

    Checks required fields, name consistency, version format,
    file_patterns validity, and dependency correctness.

    Returns JSON with: module_name, valid (bool), errors[], warnings[].
    """
    try:
        result = _validate_contract(project_root, module_name)
        _log_mcp_health("ok", "validate_contract")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "validate_contract", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def enforce_boundary(
    project_root: str,
    module_name: str,
    file_paths: list[str] | None = None,
) -> str:
    """Detect cross-module boundary violations for a module.

    Scans the module's files (or provided file_paths) and checks
    each import against other modules' file_patterns. Any import
    landing in a module not listed in depends_on is flagged.

    Returns JSON with: violations[], modules_checked, files_scanned,
    violation_count.
    """
    try:
        result = _enforce_boundary(project_root, module_name, file_paths)
        _log_mcp_health("ok", "enforce_boundary")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "enforce_boundary", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_module_state(project_root: str) -> str:
    """Aggregate full module inventory, dependency graph, and health.

    Single-source-of-truth call for rendering the module overview.
    Returns JSON with: modules[], dependency_graph, cycles[],
    total_modules, total_public_apis, contract_errors[].
    """
    try:
        result = _aggregate_module_state(project_root)
        _log_mcp_health("ok", "aggregate_module_state")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_module_state", str(e))
        return json.dumps({"error": str(e)})


# ── Host Adapters (M2) ────────────────────────────────────────


@mcp.tool()
async def get_host_adapter(host_name: str | None = None) -> str:
    """Get the full adapter configuration for a host environment.

    Returns HostAdapter dict with capability, skill_mappings,
    tool_aliases, chain_format, and setup_instructions.
    """
    try:
        result = _get_adapter(host_name)
        _log_mcp_health("ok", "get_host_adapter")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "get_host_adapter", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_chain_continuation(
    host_name: str | None,
    current_skill: str,
) -> str:
    """Determine how to continue the skill chain after current_skill.

    Returns dict with: next_skill, chain_via, marker_path, command,
    host_name.
    """
    try:
        result = _get_chain_continuation(host_name, current_skill)
        _log_mcp_health("ok", "get_chain_continuation")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "get_chain_continuation", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def list_host_adapters() -> str:
    """List all available host adapters with summary info.

    Returns list of {host_name, chain_format, skill_count,
    mcp_tools, parallel_agents}.
    """
    try:
        result = _list_adapters()
        _log_mcp_health("ok", "list_host_adapters")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "list_host_adapters", str(e))
        return json.dumps({"error": str(e)})


# ── Chain Markers (M2) ────────────────────────────────────────


@mcp.tool()
async def write_chain_marker(
    project_root: str,
    host_name: str | None,
    current_skill: str,
) -> str:
    """Write next-skill marker after current_skill completes.

    Creates .samvil/next-skill.json with chain continuation data.
    """
    try:
        result = _write_chain_marker(project_root, host_name, current_skill)
        _log_mcp_health("ok", "write_chain_marker")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "write_chain_marker", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def read_chain_marker(project_root: str) -> str:
    """Read current next-skill marker.

    Returns marker dict or null if no marker exists.
    """
    try:
        result = _read_chain_marker(project_root)
        _log_mcp_health("ok", "read_chain_marker")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "read_chain_marker", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def clear_chain_marker(project_root: str) -> str:
    """Remove the chain marker (after pipeline completes)."""
    try:
        result = _clear_chain_marker(project_root)
        _log_mcp_health("ok", "clear_chain_marker")
        return json.dumps({"cleared": result})
    except Exception as e:
        _log_mcp_health("fail", "clear_chain_marker", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def advance_chain(
    project_root: str,
    host_name: str | None,
) -> str:
    """Read current marker and advance to next skill in chain.

    Returns new marker or pipeline_complete status.
    """
    try:
        result = _advance_chain(project_root, host_name)
        _log_mcp_health("ok", "advance_chain")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "advance_chain", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pipeline_status(project_root: str) -> str:
    """Get current pipeline position from chain marker.

    Returns has_marker, current_position, next_skill, progress.
    """
    try:
        result = _get_pipeline_status(project_root)
        _log_mcp_health("ok", "get_pipeline_status")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "get_pipeline_status", str(e))
        return json.dumps({"error": str(e)})


# ── Health Tiers (M4) ─────────────────────────────────────────


@mcp.tool()
async def get_health_tier(
    project_root: str,
    mcp_health_path: str | None = None,
) -> str:
    """Get 3-tier health classification (healthy/degraded/critical).

    Reads MCP health log and classifies system health based on
    fail rate and critical tool status.
    """
    try:
        result = _get_health_tier(project_root, mcp_health_path)
        _log_mcp_health("ok", "get_health_tier")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "get_health_tier", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_health_tier_summary(
    project_root: str,
    mcp_health_path: str | None = None,
) -> str:
    """Get human-readable 3-tier health summary with icon.

    Returns markdown-formatted health status with recommendations.
    """
    try:
        result = _get_health_tier_summary(project_root, mcp_health_path)
        _log_mcp_health("ok", "get_health_tier_summary")
        return result
    except Exception as e:
        _log_mcp_health("fail", "get_health_tier_summary", str(e))
        return json.dumps({"error": str(e)})


# ── Regression Suite (Option B) ───────────────────────────────


@mcp.tool()
async def snapshot_generation(
    project_root: str,
    generation_id: str | None = None,
    qa_results_path: str | None = None,
) -> str:
    """Capture current passing ACs into a generation snapshot.

    Writes .samvil/generations/<generation_id>/snapshot.json.
    Auto-generates gen-N id if not provided.
    Returns JSON with generation_id, passing_ac_count, total_ac_count.
    """
    try:
        result = _snapshot_generation(project_root, generation_id, qa_results_path)
        _log_mcp_health("ok", "snapshot_generation")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "snapshot_generation", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def validate_against_snapshot(
    project_root: str,
    snapshot_id: str,
    qa_results_path: str | None = None,
) -> str:
    """Validate current QA results against a previously saved generation snapshot.

    Returns JSON with status ("clean"|"regression"), regressed count,
    and regressed_ids list.
    """
    try:
        result = _validate_against_snapshot(project_root, snapshot_id, qa_results_path)
        _log_mcp_health("ok", "validate_against_snapshot")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "validate_against_snapshot", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_regression_state(project_root: str) -> str:
    """Return a summary of all generation snapshots for a project.

    Returns JSON with generation_count, generations list,
    latest_generation_id, has_regression_history.
    """
    try:
        result = _aggregate_regression_state(project_root)
        _log_mcp_health("ok", "aggregate_regression_state")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_regression_state", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def compare_generations(
    project_root: str,
    gen_a: str,
    gen_b: str,
) -> str:
    """Compare two generation snapshots — added/removed/changed AC ids.

    gen_a and gen_b are generation ids (e.g., "gen-1", "gen-2").
    Returns JSON with added, removed, changed lists.
    """
    try:
        result = _compare_generations(project_root, gen_a, gen_b)
        _log_mcp_health("ok", "compare_generations")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "compare_generations", str(e))
        return json.dumps({"error": str(e)})


# ── Entry point ───────────────────────────────────────────────


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
