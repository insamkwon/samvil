"""Data models for SAMVIL MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Stage(str, Enum):
    INTERVIEW = "interview"
    SEED = "seed"
    COUNCIL = "council"
    DESIGN = "design"
    SCAFFOLD = "scaffold"
    BUILD = "build"
    QA = "qa"
    RETRO = "retro"
    EVOLVE = "evolve"
    COMPLETE = "complete"


class EventType(str, Enum):
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    FEATURE_START = "feature_start"
    FEATURE_COMPLETE = "feature_complete"
    FEATURE_FAILED = "feature_failed"
    BUILD_PASS = "build_pass"
    BUILD_FAIL = "build_fail"
    QA_PASS = "qa_pass"
    QA_REVISE = "qa_revise"
    QA_FAIL = "qa_fail"
    COUNCIL_VERDICT = "council_verdict"
    DECISION = "decision"
    SEED_VERSION = "seed_version"
    USER_EDIT = "user_edit"
    ERROR = "error"
    # v2.6.0+ — pre-v3 events that were also silently failing
    AC_SATISFIED_EXTERNALLY = "ac_satisfied_externally"
    BUILD_FEATURE_START = "build_feature_start"
    BUILD_FEATURE_SUCCESS = "build_feature_success"
    BUILD_FEATURE_FAIL = "build_feature_fail"
    BUILD_STAGE_COMPLETE = "build_stage_complete"
    FIX_APPLIED = "fix_applied"
    STAGE_CHANGE = "stage_change"
    STALL_DETECTED = "stall_detected"
    STALL_ABANDONED = "stall_abandoned"
    EVOLVE_GEN = "evolve_gen"
    RETRO_COMPLETE = "retro_complete"
    # v3.0.0+ — AC tree, dependency planning, rate budget, PM mode
    AC_LEAF_COMPLETE = "ac_leaf_complete"
    AC_VERDICT = "ac_verdict"
    FEATURE_TREE_START = "feature_tree_start"
    FEATURE_TREE_COMPLETE = "feature_tree_complete"
    SEED_MIGRATED = "seed_migrated"
    DEPENDENCY_PLAN_BUILT = "dependency_plan_built"
    RATE_BUDGET_SUMMARY = "rate_budget_summary"
    RATE_BUDGET_STARVED = "rate_budget_starved"
    RATE_BUDGET_STALE_RECOVERY = "rate_budget_stale_recovery"
    PM_SEED_COMPLETE = "pm_seed_complete"
    PM_SEED_CONVERTED = "pm_seed_converted"
    TIER_MISSING = "tier_missing"


@dataclass
class Event:
    id: str
    session_id: str
    event_type: EventType
    stage: Stage
    data: dict = field(default_factory=dict)
    token_count: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Session:
    id: str
    project_name: str
    seed_version: int = 1
    current_stage: Stage = Stage.INTERVIEW
    agent_tier: str = "standard"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SeedVersion:
    id: str
    session_id: str
    version: int
    seed_json: str  # JSON string
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    change_summary: str = ""
