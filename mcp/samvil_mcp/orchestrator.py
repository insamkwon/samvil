"""Orchestrator stage logic for SAMVIL v3.3.

The orchestrator is the read-mostly decision layer that skills can ask:
"what stage is next?", "can I proceed?", and "how should completion be
recorded?". It does not own persistence. MCP wrappers in `server.py` adapt
these pure functions to EventStore + ClaimLedger.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIPELINE_STAGES: tuple[str, ...] = (
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
    "complete",
)

SAMVIL_TIERS: tuple[str, ...] = ("minimal", "standard", "thorough", "full")

SUCCESS_EVENT_TO_STAGE: dict[str, str] = {
    "interview_complete": "interview",
    "seed_generated": "seed",
    "pm_seed_complete": "seed",
    "pm_seed_converted": "seed",
    "council_complete": "council",
    "council_verdict": "council",
    "design_complete": "design",
    "blueprint_generated": "design",
    "blueprint_feasibility_checked": "design",
    "scaffold_complete": "scaffold",
    "build_pass": "build",
    "build_stage_complete": "build",
    "build_feature_success": "build",
    "feature_tree_complete": "build",
    "qa_pass": "qa",
    "deploy_complete": "deploy",
    "retro_complete": "retro",
    "evolve_converge": "evolve",
    "stage_end": "",
}

FAIL_EVENT_TO_STAGE: dict[str, str] = {
    "build_fail": "build",
    "build_feature_fail": "build",
    "feature_failed": "build",
    "qa_fail": "qa",
    "qa_revise": "qa",
    "qa_blocked": "qa",
    "qa_unimplemented": "qa",
    "stall_detected": "",
    "stall_abandoned": "",
}

SUCCESS_COMPLETE_EVENTS: dict[str, str] = {
    "interview": "interview_complete",
    "seed": "seed_generated",
    "council": "council_verdict",
    "design": "design_complete",
    "scaffold": "scaffold_complete",
    "build": "build_stage_complete",
    "qa": "qa_pass",
    "deploy": "deploy_complete",
    "retro": "retro_complete",
    "evolve": "evolve_converge",
    "complete": "stage_end",
}

FAIL_COMPLETE_EVENTS: dict[str, str] = {
    "build": "build_fail",
    "qa": "qa_fail",
}

BLOCKED_COMPLETE_EVENTS: dict[str, str] = {
    "qa": "qa_blocked",
}

COMPLETE_VERDICTS: tuple[str, ...] = ("pass", "complete", "fail", "blocked")


@dataclass(frozen=True)
class StageEvent:
    """Reduced event-store row used by pure orchestrator decisions."""

    event_type: str
    stage: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class OrchestratorError(ValueError):
    """Raised when an orchestration decision would be invalid."""


def _validate_stage(stage: str) -> None:
    if stage not in PIPELINE_STAGES:
        raise OrchestratorError(f"unknown stage: {stage!r}")


def _validate_tier(samvil_tier: str) -> None:
    if samvil_tier not in SAMVIL_TIERS:
        raise OrchestratorError(f"unknown samvil_tier: {samvil_tier!r}")


def should_skip_stage(stage: str, samvil_tier: str) -> bool:
    """Return whether `stage` is skipped for the current tier in v3.3 Phase 1."""
    _validate_stage(stage)
    _validate_tier(samvil_tier)

    if stage == "council" and samvil_tier == "minimal":
        return True
    if stage == "deploy":
        return True
    return False


def get_next_stage(current: str, samvil_tier: str) -> str | None:
    """Return the next non-skipped stage after `current`."""
    _validate_stage(current)
    _validate_tier(samvil_tier)

    current_index = PIPELINE_STAGES.index(current)
    for stage in PIPELINE_STAGES[current_index + 1:]:
        if not should_skip_stage(stage, samvil_tier):
            return stage
    return None


def stage_can_proceed(
    session: Any,
    events: list[StageEvent],
    target_stage: str,
) -> dict[str, Any]:
    """Return whether `target_stage` can run based on prior stage outcomes."""
    samvil_tier = _session_tier(session)
    _validate_stage(target_stage)
    _validate_tier(samvil_tier)

    if should_skip_stage(target_stage, samvil_tier):
        return {
            "can_proceed": False,
            "blockers": [f"stage {target_stage} is skipped for tier {samvil_tier}"],
        }

    statuses = _stage_statuses(events)
    blockers: list[str] = []

    target_index = PIPELINE_STAGES.index(target_stage)
    for stage in PIPELINE_STAGES[:target_index]:
        if should_skip_stage(stage, samvil_tier):
            continue
        status = statuses.get(stage)
        if status == "failed":
            blockers.append(f"stage {stage} failed")
        elif status != "complete":
            blockers.append(f"stage {stage} is not complete")

    return {"can_proceed": not blockers, "blockers": blockers}


def get_orchestration_state(session: Any, events: list[StageEvent]) -> dict[str, Any]:
    """Summarize progress from session + event stream without mutating state."""
    current_stage = _session_stage(session)
    samvil_tier = _session_tier(session)
    _validate_stage(current_stage)
    _validate_tier(samvil_tier)

    statuses = _stage_statuses(events)
    skipped = [
        stage for stage in PIPELINE_STAGES if should_skip_stage(stage, samvil_tier)
    ]
    completed = [
        stage
        for stage in PIPELINE_STAGES
        if statuses.get(stage) == "complete" and stage not in skipped
    ]
    failed = [
        stage
        for stage in PIPELINE_STAGES
        if statuses.get(stage) == "failed" and stage not in skipped
    ]
    next_stage = get_next_stage(current_stage, samvil_tier)
    can_proceed = stage_can_proceed(session, events, current_stage)

    executable_stages = [s for s in PIPELINE_STAGES if s not in skipped]
    return {
        "current_stage": current_stage,
        "samvil_tier": samvil_tier,
        "next_stage": next_stage,
        "completed_stages": completed,
        "failed_stages": failed,
        "skipped_stages": skipped,
        "can_proceed": can_proceed,
        "progress": {
            "completed": len(completed),
            "total": len(executable_stages),
            "percent": round((len(completed) / len(executable_stages)) * 100, 1),
        },
    }


def complete_stage_plan(session: Any, stage: str, verdict: str) -> dict[str, Any]:
    """Return the event + claim payloads needed to mark a stage complete.

    This function is intentionally pure. The server wrapper owns EventStore and
    ClaimLedger mutation.
    """
    samvil_tier = _session_tier(session)
    _validate_stage(stage)
    _validate_tier(samvil_tier)
    if should_skip_stage(stage, samvil_tier):
        raise OrchestratorError(f"stage {stage} is skipped for tier {samvil_tier}")
    if verdict not in COMPLETE_VERDICTS:
        raise OrchestratorError(f"unknown verdict: {verdict!r}")

    success = verdict in ("pass", "complete")
    if success:
        event_type = SUCCESS_COMPLETE_EVENTS[stage]
        next_stage = get_next_stage(stage, samvil_tier)
        event_stage = next_stage or stage
    elif verdict == "blocked":
        event_type = BLOCKED_COMPLETE_EVENTS.get(stage, f"{stage}_blocked")
        next_stage = None
        event_stage = stage
    else:
        event_type = FAIL_COMPLETE_EVENTS.get(stage, f"{stage}_fail")
        next_stage = None
        event_stage = stage

    return {
        "event_type": event_type,
        "event_stage": event_stage,
        "event_data": {"verdict": verdict, "stage": stage},
        "claim": {
            "type": "gate_verdict",
            "subject": f"gate:{stage}_exit",
            "statement": f"verdict={verdict} via complete_stage",
            "authority_file": "project.state.json",
            "evidence": [f"event:{event_type}"],
            "meta": {
                "via": "complete_stage",
                "verdict": verdict,
                "stage": stage,
                "next_stage": next_stage,
            },
        },
        "next_stage": next_stage,
    }


def _stage_statuses(events: list[StageEvent]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for event in events:
        event_type = _as_value(event.event_type)
        stage = _stage_for_event(event_type, _as_value(event.stage))
        if stage not in PIPELINE_STAGES:
            continue
        if event_type in SUCCESS_EVENT_TO_STAGE:
            statuses[stage] = "complete"
        elif event_type in FAIL_EVENT_TO_STAGE:
            statuses[stage] = "failed"
    return statuses


def _stage_for_event(event_type: str, fallback_stage: str) -> str:
    if event_type in SUCCESS_EVENT_TO_STAGE:
        return SUCCESS_EVENT_TO_STAGE[event_type] or fallback_stage
    if event_type in FAIL_EVENT_TO_STAGE:
        return FAIL_EVENT_TO_STAGE[event_type] or fallback_stage
    return fallback_stage


def _session_stage(session: Any) -> str:
    if isinstance(session, dict):
        return _as_value(session.get("current_stage", ""))
    return _as_value(getattr(session, "current_stage", ""))


def _session_tier(session: Any) -> str:
    if isinstance(session, dict):
        return _as_value(session.get("samvil_tier", "standard"))
    return _as_value(getattr(session, "samvil_tier", "standard"))


def _as_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


# ──────────────────────────────────────────────────────────────────────
# Boot-time aggregator for the samvil orchestrator skill (T4.5).
#
# The orchestrator skill body is the *entry point* of `/samvil`. It needs
# four pieces of pre-flight info before chaining anything:
#
#   1. tier — resolved from CLI flag, project.config.json, or default.
#   2. solution_type — 3-layer keyword/context detection on the prompt
#      (L3 user-confirmation step still happens in the skill body).
#   3. brownfield/resume — whether project_root looks like an existing
#      project (state.json exists, artifacts present, mode hint).
#   4. first_skill — which skill to chain into based on PM-vs-Eng
#      signals + brownfield mode.
#
# The skill body still owns: AskUserQuestion checkpoints, the actual
# Health Check shell calls, and chain dispatch via HostCapability. This
# aggregator only collects the structural facts so the skill can render
# + branch in a single pass.
# ──────────────────────────────────────────────────────────────────────

ORCHESTRATOR_AGGREGATE_SCHEMA_VERSION = "1.0"

# Layer-1 keyword tables. Order matters: most-specific first so that
# e.g. "automation script" doesn't get classified as "web-app" by the
# bare word "app".
_L1_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "automation",
        (
            "자동화", "스크립트", "크롤링", "봇 ", "cron",
            "automation", "scraper", "crawler", "webhook bot",
        ),
    ),
    (
        "game",
        (
            "게임", "phaser", "플랫포머", "퍼즐", "슈팅",
            "game", "platformer", "shooter",
        ),
    ),
    (
        "mobile-app",
        (
            "모바일 앱", "ios 앱", "android 앱", "앱스토어", "play store",
            "스마트폰", "react native", "expo",
        ),
    ),
    (
        "dashboard",
        (
            "대시보드", "dashboard", "차트", "chart", "analytics",
            "kpi", "모니터링", "리포트",
        ),
    ),
)

# Layer-2 context phrases that nudge an ambiguous prompt one way.
_L2_CONTEXT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("automation", ("자동으로", "주기적으로", "트리거", "스케줄", "이메일 들어오면")),
    ("game", ("플레이", "점수", "레벨", "보스", "아이템", "캐릭터")),
    ("mobile-app", ("앱스토어", "스마트폰에서", "푸시 알림", "네이티브")),
    ("dashboard", ("지표", "실시간 그래프", "kpi", "리포트")),
)

# PM-mode signals on the one-line prompt.
_PM_SIGNALS: tuple[str, ...] = (
    "mvp", "vision", "user segment", "user segments", "metrics",
    "epic", "epics", "pm mode", "/samvil pm", "pm:",
)


def _read_json_safe(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_solution_type(prompt: str) -> dict[str, Any]:
    """3-layer (keyword + context) detection. Layer-3 is user confirmation
    in the skill body and is not done here.

    Returns: {solution_type, layer, matched, confidence}.
    """
    text = (prompt or "").lower()
    matched: list[str] = []
    for stype, keywords in _L1_KEYWORD_RULES:
        hits = [kw for kw in keywords if kw in text]
        if hits:
            matched.extend(hits)
            return {
                "solution_type": stype,
                "layer": "L1_keyword",
                "matched": hits,
                "confidence": "high",
            }
    for stype, phrases in _L2_CONTEXT_RULES:
        hits = [p for p in phrases if p in text]
        if hits:
            matched.extend(hits)
            return {
                "solution_type": stype,
                "layer": "L2_context",
                "matched": hits,
                "confidence": "medium",
            }
    return {
        "solution_type": "web-app",
        "layer": "default",
        "matched": [],
        "confidence": "low",
    }


def detect_pm_mode(prompt: str) -> bool:
    """Detect PM-mode interview hint from the one-line prompt."""
    text = (prompt or "").lower()
    return any(signal in text for signal in _PM_SIGNALS)


def _kebab_case(name: str) -> str:
    """Derive a kebab-case slug from an arbitrary prompt for project_name."""
    if not name:
        return "samvil-project"
    # Keep alphanumerics, replace whitespace + punctuation with '-'.
    text = name.strip().lower()
    text = re.sub(r"[^a-z0-9가-힣]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "samvil-project"


def _resolve_tier(
    cli_tier: str,
    config: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Resolve tier with precedence CLI > state > config > default."""
    requested = (cli_tier or "").strip().lower()
    state_tier = (
        (state.get("samvil_tier") or state.get("selected_tier") or "")
        .strip()
        .lower()
        if isinstance(state, dict)
        else ""
    )
    config_tier = (
        (config.get("samvil_tier") or config.get("selected_tier") or "")
        .strip()
        .lower()
        if isinstance(config, dict)
        else ""
    )
    valid = set(SAMVIL_TIERS) | {"deep"}  # accept v3.1 deep alias
    chosen = ""
    source = "default"
    for candidate, src in (
        (requested, "cli"),
        (state_tier, "state"),
        (config_tier, "config"),
    ):
        if candidate in valid:
            chosen = candidate
            source = src
            break
    if not chosen:
        chosen = "standard"
        source = "default"
    # Map deprecated v3.1 alias if seen.
    aliased_from = ""
    if chosen == "deep":
        aliased_from = "deep"
        chosen = "full"
    return {
        "samvil_tier": chosen,
        "source": source,
        "aliased_from": aliased_from,
        "valid_tiers": list(SAMVIL_TIERS),
    }


def _detect_brownfield(
    project_root: Path,
    mode_hint: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Decide whether to suggest brownfield mode + collect resume signals."""
    artifacts = {
        "seed": (project_root / "project.seed.json").exists(),
        "blueprint": (project_root / "project.blueprint.json").exists(),
        "package_json": (project_root / "package.json").exists(),
        "src_dir": (project_root / "src").is_dir(),
    }
    has_state = bool(state)
    completed_stages: list[str] = []
    current_stage: str = ""
    if isinstance(state, dict):
        stages = state.get("completed_stages")
        if isinstance(stages, list):
            completed_stages = [str(s) for s in stages if isinstance(s, str)]
        current_stage = _as_value(state.get("current_stage", ""))

    mode_hint_norm = (mode_hint or "").strip().lower()
    is_brownfield = mode_hint_norm == "brownfield" or (
        artifacts["package_json"] and not has_state
    )
    can_resume = has_state or any(artifacts.values())
    return {
        "is_brownfield": is_brownfield,
        "can_resume": can_resume,
        "mode_hint": mode_hint_norm or "auto",
        "artifacts": artifacts,
        "state_present": has_state,
        "current_stage": current_stage,
        "completed_stages": completed_stages,
    }


def _decide_first_skill(
    *,
    is_brownfield: bool,
    can_resume: bool,
    completed_stages: list[str],
    current_stage: str,
    samvil_tier: str,
    is_pm_mode: bool,
) -> dict[str, Any]:
    """Pick the first skill to chain into.

    Precedence: brownfield → samvil-analyze; resume → next stage skill;
    PM hint → samvil-pm-interview; else samvil-interview.
    """
    if is_brownfield:
        return {
            "next_skill": "samvil-analyze",
            "reason": "brownfield mode selected",
            "resume_point": "",
        }
    if can_resume and completed_stages:
        # Find the next non-skipped stage after the last completed.
        last = completed_stages[-1]
        try:
            next_stage = get_next_stage(last, samvil_tier)
        except OrchestratorError:
            next_stage = None
        if next_stage and next_stage != "complete":
            return {
                "next_skill": f"samvil-{next_stage}"
                if next_stage != "interview"
                else ("samvil-pm-interview" if is_pm_mode else "samvil-interview"),
                "reason": f"resume after {last}",
                "resume_point": next_stage,
            }
        if current_stage and current_stage != "complete":
            return {
                "next_skill": f"samvil-{current_stage}"
                if current_stage != "interview"
                else ("samvil-pm-interview" if is_pm_mode else "samvil-interview"),
                "reason": f"resume in-progress {current_stage}",
                "resume_point": current_stage,
            }
    if is_pm_mode:
        return {
            "next_skill": "samvil-pm-interview",
            "reason": "PM signals detected in prompt",
            "resume_point": "interview",
        }
    return {
        "next_skill": "samvil-interview",
        "reason": "fresh greenfield run",
        "resume_point": "interview",
    }


def aggregate_orchestrator_state(
    project_root: str | Path,
    *,
    prompt: str = "",
    cli_tier: str = "",
    mode_hint: str = "",
    host_name: str = "",
) -> dict[str, Any]:
    """Boot-time aggregator for the samvil orchestrator skill body (T4.5).

    Reads (best-effort) from `project_root`:
      - `project.state.json` — for resume + completed_stages.
      - `project.config.json` — for prior tier selection.
      - filesystem artifacts (`project.seed.json`, `package.json`, `src/`).

    The skill body still does:
      - Health Check shell calls (Node/Python/uv/gh/MCP).
      - AskUserQuestion checkpoints (mode + tier + L3 confirm + resume).
      - Chain dispatch via HostCapability (skill_tool / file_marker).

    Returns a dict with:
      - schema_version, project_root, project_name (kebab-case slug)
      - tier: {samvil_tier, source, aliased_from, valid_tiers}
      - solution_type: {solution_type, layer, matched, confidence}
      - is_pm_mode: bool
      - brownfield: {is_brownfield, can_resume, artifacts, state_present,
                     current_stage, completed_stages, mode_hint}
      - chain: {next_skill, reason, resume_point}
      - errors: [str]   (non-fatal)

    Never raises. On unexpected exception, the offending section is
    left as its empty default and a string is appended to `errors`.
    """
    errors: list[str] = []
    root = Path(project_root) if project_root else Path(".")

    state = _read_json_safe(root / "project.state.json")
    if not state:
        # Tolerate state at .samvil/state.json (older layout).
        state = _read_json_safe(root / ".samvil" / "state.json")
    config = _read_json_safe(root / "project.config.json")

    try:
        tier_block = _resolve_tier(cli_tier, config, state)
    except Exception as exc:  # pragma: no cover — defensive
        tier_block = {
            "samvil_tier": "standard",
            "source": "default",
            "aliased_from": "",
            "valid_tiers": list(SAMVIL_TIERS),
        }
        errors.append(f"tier: {exc}")

    try:
        stype_block = detect_solution_type(prompt)
    except Exception as exc:  # pragma: no cover — defensive
        stype_block = {
            "solution_type": "web-app",
            "layer": "default",
            "matched": [],
            "confidence": "low",
        }
        errors.append(f"solution_type: {exc}")

    try:
        is_pm_mode = detect_pm_mode(prompt)
    except Exception as exc:  # pragma: no cover — defensive
        is_pm_mode = False
        errors.append(f"pm_mode: {exc}")

    try:
        brownfield = _detect_brownfield(root, mode_hint, state)
    except Exception as exc:  # pragma: no cover — defensive
        brownfield = {
            "is_brownfield": False,
            "can_resume": False,
            "mode_hint": "auto",
            "artifacts": {},
            "state_present": False,
            "current_stage": "",
            "completed_stages": [],
        }
        errors.append(f"brownfield: {exc}")

    try:
        chain = _decide_first_skill(
            is_brownfield=brownfield["is_brownfield"],
            can_resume=brownfield["can_resume"],
            completed_stages=brownfield["completed_stages"],
            current_stage=brownfield["current_stage"],
            samvil_tier=tier_block["samvil_tier"],
            is_pm_mode=is_pm_mode,
        )
    except Exception as exc:  # pragma: no cover — defensive
        chain = {
            "next_skill": "samvil-interview",
            "reason": "fallback",
            "resume_point": "interview",
        }
        errors.append(f"chain: {exc}")

    return {
        "schema_version": ORCHESTRATOR_AGGREGATE_SCHEMA_VERSION,
        "project_root": str(root),
        "project_name": _kebab_case(prompt),
        "host_name": (host_name or "").strip().lower() or "generic",
        "tier": tier_block,
        "solution_type": stype_block,
        "is_pm_mode": is_pm_mode,
        "brownfield": brownfield,
        "chain": chain,
        "errors": errors,
    }
