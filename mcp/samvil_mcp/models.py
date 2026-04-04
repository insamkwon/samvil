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


@dataclass
class Event:
    id: str
    session_id: str
    event_type: EventType
    stage: Stage
    data: dict = field(default_factory=dict)
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
