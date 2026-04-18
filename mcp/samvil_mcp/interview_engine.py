"""Ambiguity scoring engine for SAMVIL interviews (v2.4.0).

Scores interview state across 3 dimensions:
  - Goal clarity (40%) — Can we write a 1-sentence problem statement?
  - Constraint clarity (30%) — Are limits explicit and non-contradictory?
  - Criteria testability (30%) — Are acceptance criteria verifiable?

Each dimension: 0.0 (clear) → 1.0 (ambiguous)
Overall: weighted average. Target: ≤ tier threshold.

v2.4.0 (Phase 2):
  - Adds Milestones (INITIAL/PROGRESS/REFINED/READY) — Ouroboros #05
  - Adds Component Floors — prevents average-trap convergence
  - Adds missing_items extraction for UI feedback
  - Keeps backward compatibility with v2.3.x score_ambiguity return.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── Milestone definitions (v2.4.0, Ouroboros #05) ─────────────

MILESTONES = [
    # (name, max_ambiguity, description)
    ("READY", 0.20, "모든 기준 구체화. Seed 생성 준비."),
    ("REFINED", 0.30, "AC 부분 정의. 엣지 케이스/non-goals 일부 남음."),
    ("PROGRESS", 0.40, "요구사항 대부분 포착. 세부사항 일부 미흡."),
    ("INITIAL", 1.00, "핵심 요구 식별. 제약/성공기준 상당 미정."),
]

# Component floors — one dimension below floor blocks seed-ready
FLOORS = {
    "goal_clarity": 0.75,
    "constraint_clarity": 0.65,
    "criteria_testability": 0.70,
}

TIER_TARGETS = {
    "minimal": 0.10,
    "standard": 0.05,
    "thorough": 0.02,
    "full": 0.01,
}


def score_ambiguity(interview_state: dict, tier: str = "standard") -> dict:
    """Score ambiguity of an interview state.

    Args:
        interview_state: Dict with keys:
            - target_user: str (who uses this)
            - core_problem: str (what problem)
            - core_experience: str (30-second action)
            - features: list[str] (must-have features)
            - exclusions: list[str] (out of scope)
            - constraints: list[str] (technical limits)
            - acceptance_criteria: list[str] (testable criteria)
        tier: Agent tier determining the target threshold.
            minimal=0.10, standard=0.05, thorough=0.02, full=0.01

    Returns:
        Dict with per-dimension scores, overall ambiguity, milestone,
        floors_passed, and missing_items.
    """
    target = TIER_TARGETS.get(tier, 0.05)

    goal_score = _score_goal(interview_state)
    constraint_score = _score_constraints(interview_state)
    criteria_score = _score_criteria(interview_state)

    overall = goal_score * 0.4 + constraint_score * 0.3 + criteria_score * 0.3

    # v2.4.0 additions ───────────────────────────────────────
    goal_clarity = round(1.0 - goal_score, 3)
    constraint_clarity = round(1.0 - constraint_score, 3)
    criteria_testability = round(1.0 - criteria_score, 3)

    milestone = _match_milestone(overall)
    floors_passed, floor_violations = _check_floors({
        "goal_clarity": goal_clarity,
        "constraint_clarity": constraint_clarity,
        "criteria_testability": criteria_testability,
    })
    missing_items = _extract_missing_items(interview_state)

    # converged = below tier target AND all floors passed
    converged = overall <= target and floors_passed

    return {
        # Backward-compatible fields ───────────────────────────
        "goal_clarity": goal_clarity,
        "constraint_clarity": constraint_clarity,
        "criteria_testability": criteria_testability,
        "ambiguity": round(overall, 3),
        "converged": converged,
        "target": target,
        "tier": tier,
        # v2.4.0 additions ──────────────────────────────────────
        "milestone": milestone,
        "floors_passed": floors_passed,
        "floor_violations": floor_violations,
        "missing_items": missing_items,
    }


def _match_milestone(ambiguity: float) -> dict:
    """Match ambiguity score to a milestone. Top-down (first match wins)."""
    for name, max_score, description in MILESTONES:
        if ambiguity <= max_score:
            return {"name": name, "max_score": max_score, "description": description}
    return {"name": "INITIAL", "max_score": 1.0, "description": MILESTONES[-1][2]}


def _check_floors(clarities: dict) -> tuple[bool, list[str]]:
    """Check if all component clarities meet their floor. Returns (all_passed, violations)."""
    violations = []
    for component, floor in FLOORS.items():
        if clarities.get(component, 0) < floor:
            violations.append(
                f"{component} ({clarities[component]}) < floor ({floor})"
            )
    return (len(violations) == 0, violations)


def _extract_missing_items(state: dict) -> list[str]:
    """Extract a human-readable list of missing items from state."""
    missing = []

    if not state.get("target_user"):
        missing.append("target_user")
    if not state.get("core_problem"):
        missing.append("core_problem")
    if not state.get("core_experience"):
        missing.append("core_experience")
    if not state.get("features"):
        missing.append("features (must-have list)")
    if not state.get("exclusions"):
        missing.append("exclusions (out-of-scope)")
    if not state.get("constraints"):
        missing.append("constraints (technical limits)")
    if not state.get("acceptance_criteria"):
        missing.append("acceptance_criteria (testable)")
    elif len(state.get("acceptance_criteria", [])) < 3:
        missing.append("acceptance_criteria (need at least 3)")

    return missing


def _score_goal(state: dict) -> float:
    """Score goal ambiguity (0=clear, 1=ambiguous)."""
    penalties = 0.0

    # Target user defined?
    target_user = state.get("target_user", "")
    if not target_user:
        penalties += 0.4
    elif len(target_user) < 10:  # Too vague ("users", "people")
        penalties += 0.2
    elif any(vague in target_user.lower() for vague in ["everyone", "anyone", "people", "users"]):
        penalties += 0.15

    # Core problem defined?
    core_problem = state.get("core_problem", "")
    if not core_problem:
        penalties += 0.3
    elif len(core_problem) < 15:
        penalties += 0.15

    # Core experience defined?
    core_exp = state.get("core_experience", "")
    if not core_exp:
        penalties += 0.3
    elif len(core_exp) < 10:
        penalties += 0.15

    return min(penalties, 1.0)


def _score_constraints(state: dict) -> float:
    """Score constraint ambiguity (0=clear, 1=ambiguous)."""
    penalties = 0.0

    # Features defined?
    features = state.get("features", [])
    if not features:
        penalties += 0.3
    elif len(features) > 7:  # Too many = unclear priorities
        penalties += 0.2

    # Exclusions defined?
    exclusions = state.get("exclusions", [])
    if not exclusions:
        penalties += 0.3
    elif len(exclusions) < 1:
        penalties += 0.15

    # Constraints defined?
    constraints = state.get("constraints", [])
    if not constraints:
        penalties += 0.2

    # Contradiction check: feature in both features and exclusions
    feature_set = {f.lower() for f in features}
    exclusion_set = {e.lower() for e in exclusions}
    if feature_set & exclusion_set:
        penalties += 0.3

    return min(penalties, 1.0)


def _score_criteria(state: dict) -> float:
    """Score criteria testability (0=clear, 1=ambiguous)."""
    penalties = 0.0

    criteria = state.get("acceptance_criteria", [])
    if not criteria:
        return 1.0
    if len(criteria) < 3:
        penalties += 0.3

    # Check each criterion for testability
    vague_patterns = [
        r"\bgood\b", r"\bnice\b", r"\bfast\b", r"\bclean\b",
        r"\buser.?friendly\b", r"\bintuitive\b", r"\bsmooth\b",
        r"\bprofessional\b", r"\bmodern\b", r"\bresponsive\b",
    ]
    vague_count = 0
    for criterion in criteria:
        for pattern in vague_patterns:
            if re.search(pattern, criterion, re.IGNORECASE):
                vague_count += 1
                break

    if criteria:
        vague_ratio = vague_count / len(criteria)
        penalties += vague_ratio * 0.5

    # Compound criteria penalty ("create, edit, delete" = 3 criteria in 1)
    compound_count = sum(1 for c in criteria if c.count(",") >= 2 or " and " in c.lower())
    if criteria:
        penalties += (compound_count / len(criteria)) * 0.2

    return min(penalties, 1.0)


# ── Answer Streak Manager (v2.4.0, Ouroboros #02) ──────────────

MAX_AI_STREAK = 3


def update_streak(current_streak: int, answer_source: str) -> dict:
    """Update AI answer streak counter based on answer source.

    Args:
        current_streak: Current streak value (from state)
        answer_source: One of 'from-code', 'from-code-auto', 'from-user',
                       'from-user-correction', 'from-research'

    Returns:
        Dict with new_streak and force_user_next flag.
    """
    # User answers reset streak
    if answer_source in ("from-user", "from-user-correction"):
        new_streak = 0
    # AI auto-answers increment streak
    elif answer_source in ("from-code", "from-code-auto", "from-research"):
        new_streak = current_streak + 1
    else:
        # Unknown source — treat conservatively
        new_streak = current_streak

    return {
        "new_streak": new_streak,
        "force_user_next": new_streak >= MAX_AI_STREAK,
        "reason": (
            f"Rhythm Guard: {new_streak} consecutive AI answers → next must be user"
            if new_streak >= MAX_AI_STREAK
            else None
        ),
    }


# ── Tracks Manager (v2.4.0, Ouroboros #P4 simplified) ──────────


def initialize_tracks(features_or_scope: list[str]) -> list[dict]:
    """Initialize interview tracks from features or scope items.

    Args:
        features_or_scope: List of feature names or scope areas.

    Returns:
        List of Track dicts with rounds_focused=0, is_resolved=False.
    """
    return [
        {
            "name": item,
            "description": item,
            "rounds_focused": 0,
            "is_resolved": False,
        }
        for item in features_or_scope
    ]


def update_track(tracks: list[dict], active_track_name: str) -> list[dict]:
    """Increment rounds_focused for the active track. Returns updated list."""
    updated = []
    for t in tracks:
        new_t = dict(t)
        if t["name"] == active_track_name:
            new_t["rounds_focused"] = t.get("rounds_focused", 0) + 1
        updated.append(new_t)
    return updated


MAX_ROUNDS_ON_SAME_TRACK = 3


def should_force_breadth(tracks: list[dict]) -> dict:
    """Check if Breadth-Keeper should intervene.

    Returns:
        Dict with force_breadth, current_track, unresolved_tracks, reason.
    """
    if not tracks:
        return {
            "force_breadth": False,
            "current_track": None,
            "unresolved_tracks": [],
            "reason": None,
        }

    # Find track with max rounds_focused
    active = max(tracks, key=lambda t: t.get("rounds_focused", 0))
    unresolved = [t["name"] for t in tracks if not t.get("is_resolved", False) and t["name"] != active["name"]]

    force = (
        active.get("rounds_focused", 0) >= MAX_ROUNDS_ON_SAME_TRACK
        and len(unresolved) > 0
    )

    return {
        "force_breadth": force,
        "current_track": active["name"] if force else None,
        "unresolved_tracks": unresolved if force else [],
        "reason": (
            f"{active['name']}에 {active['rounds_focused']}라운드 집중. "
            f"미해결: {', '.join(unresolved)}"
            if force
            else None
        ),
    }


def mark_track_resolved(tracks: list[dict], track_name: str) -> list[dict]:
    """Mark a track as resolved. Returns updated list."""
    updated = []
    for t in tracks:
        new_t = dict(t)
        if t["name"] == track_name:
            new_t["is_resolved"] = True
        updated.append(new_t)
    return updated
