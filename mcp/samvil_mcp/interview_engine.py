"""Ambiguity scoring engine for SAMVIL interviews (v2.5.0).

Scores interview state across 10 dimensions:
  Core (60%):
    - Goal clarity (22%) — Can we write a 1-sentence problem statement?
    - Constraint clarity (18%) — Are limits explicit and non-contradictory?
    - Criteria testability (15%) — Are acceptance criteria verifiable?
  Enriched (40%):
    - Technical specificity (10%) — Are tech choices named?
    - Failure modes depth (8%) — Are edge cases / exclusions specific?
    - Non-functional coverage (8%) — Are perf/security/a11y addressed?
    - Stakeholder specificity (7%) — Is the primary user role+context specific?
    - Scope boundary sharpness (5%) — Are exclusions concrete?
    - Success metrics quality (4%) — Do ACs contain measurable numbers?
    - Lifecycle awareness (3%) — Is onboarding/retention considered?

Each dimension: 0.0 (clear) → 1.0 (ambiguous)
Overall: weighted average. Converged when:
  overall ≤ tier threshold AND floors_passed AND questions_asked ≥ MIN_QUESTIONS[tier]

v2.5.0 changes:
  - 10-dimension scoring (was 3)
  - MIN_QUESTIONS enforcement per tier: 5/10/20/30/40
  - questions_asked added to score_ambiguity signature
  - min_questions_met and min_questions_required added to result

v2.6.0 changes (brownfield):
  - pre_filled_dimensions: force named dimensions to 0.0 (already answered by
    code analysis). Reduces effective MIN_QUESTIONS by one per pre-filled dim.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── Milestone definitions ───────────────────────────────────────

MILESTONES = [
    ("READY",    0.20, "모든 기준 구체화. Seed 생성 준비."),
    ("REFINED",  0.30, "AC 부분 정의. 엣지 케이스/non-goals 일부 남음."),
    ("PROGRESS", 0.40, "요구사항 대부분 포착. 세부사항 일부 미흡."),
    ("INITIAL",  1.00, "핵심 요구 식별. 제약/성공기준 상당 미정."),
]

# Component floors — one dimension below floor blocks seed-ready (v2.4.0)
FLOORS = {
    "goal_clarity": 0.75,
    "constraint_clarity": 0.65,
    "criteria_testability": 0.70,
}

TIER_TARGETS = {
    "minimal":  0.10,
    "standard": 0.05,
    "thorough": 0.02,
    "full":     0.01,
    "deep":     0.005,
}

# Minimum questions that must be asked before convergence is possible (v2.5.0)
MIN_QUESTIONS = {
    "minimal":  5,
    "standard": 10,
    "thorough": 20,
    "full":     30,
    "deep":     40,
}

# Required interview phases per tier (v3.1.0, Sprint 1)
TIER_REQUIRED_PHASES = {
    "minimal":  {"core", "scope"},
    "standard": {"core", "scope", "lifecycle"},
    "thorough": {"core", "scope", "lifecycle", "unknown", "nonfunc", "inversion"},
    "full":     {"core", "scope", "lifecycle", "unknown", "nonfunc", "inversion", "stakeholder", "research"},
    "deep":     {"core", "scope", "lifecycle", "unknown", "nonfunc", "inversion", "stakeholder", "research", "domain_deep"},
}


def tier_phases(tier: str) -> set[str]:
    """Return the required phases for a tier. Falls back to standard."""
    return TIER_REQUIRED_PHASES.get(tier, TIER_REQUIRED_PHASES["standard"])


def score_ambiguity(
    interview_state: dict,
    tier: str = "standard",
    questions_asked: int = 0,
    pre_filled_dimensions: list[str] | None = None,
) -> dict:
    """Score ambiguity of an interview state across 10 dimensions.

    Args:
        interview_state: Dict with keys: target_user, core_problem,
            core_experience, features, exclusions, constraints,
            acceptance_criteria.
        tier: Agent tier determining threshold and minimum questions.
        questions_asked: Number of questions asked so far. Convergence
            requires this to meet the adjusted MIN_QUESTIONS.
        pre_filled_dimensions: Dimension names already answered by code analysis
            (e.g. ["technical", "stakeholder"]). Each pre-filled dim is forced
            to 0.0 and reduces MIN_QUESTIONS by 1 (floor 2). Used in brownfield
            mode where the existing codebase answers tech/nonfunctional dims.

    Returns:
        Dict with per-dimension scores, overall ambiguity, milestone,
        floors_passed, missing_items, min_questions_met, and converged.
    """
    target = TIER_TARGETS.get(tier, 0.05)
    base_min_q = MIN_QUESTIONS.get(tier, 10)
    pre_filled = set(pre_filled_dimensions or [])

    # Reduce MIN_QUESTIONS by one per pre-filled dimension (floor 2)
    min_q = max(2, base_min_q - len(pre_filled))

    def _maybe_prefill(name: str, raw_score: float) -> float:
        return 0.0 if name in pre_filled else raw_score

    # ── Core dimensions (v2.4.0) ──────────────────────────────────
    goal_score        = _maybe_prefill("goal",        _score_goal(interview_state))
    constraint_score  = _maybe_prefill("constraint",  _score_constraints(interview_state))
    criteria_score    = _maybe_prefill("criteria",    _score_criteria(interview_state))

    # ── Enriched dimensions (v2.5.0) ─────────────────────────────
    technical_score    = _maybe_prefill("technical",      _score_technical(interview_state))
    failure_score      = _maybe_prefill("failure_modes",  _score_failure_modes(interview_state))
    nonfunctional_score = _maybe_prefill("nonfunctional", _score_nonfunctional(interview_state))
    stakeholder_score  = _maybe_prefill("stakeholder",    _score_stakeholder(interview_state))
    scope_score        = _maybe_prefill("scope_boundary", _score_scope_boundary(interview_state))
    metrics_score      = _maybe_prefill("success_metrics", _score_success_metrics(interview_state))
    lifecycle_score    = _maybe_prefill("lifecycle",      _score_lifecycle(interview_state))

    overall = (
        goal_score          * 0.22
        + constraint_score  * 0.18
        + criteria_score    * 0.15
        + technical_score   * 0.10
        + failure_score     * 0.08
        + nonfunctional_score * 0.08
        + stakeholder_score * 0.07
        + scope_score       * 0.05
        + metrics_score     * 0.04
        + lifecycle_score   * 0.03
    )

    # ── Clarities (inverse of raw scores) ────────────────────────
    goal_clarity         = round(1.0 - goal_score, 3)
    constraint_clarity   = round(1.0 - constraint_score, 3)
    criteria_testability = round(1.0 - criteria_score, 3)

    milestone = _match_milestone(overall)
    floors_passed, floor_violations = _check_floors({
        "goal_clarity":         goal_clarity,
        "constraint_clarity":   constraint_clarity,
        "criteria_testability": criteria_testability,
    })
    missing_items = _extract_missing_items(interview_state)

    min_questions_met = questions_asked >= min_q
    converged = overall <= target and floors_passed and min_questions_met

    return {
        # Core dimension clarities (backward-compatible) ──────────
        "goal_clarity":         goal_clarity,
        "constraint_clarity":   constraint_clarity,
        "criteria_testability": criteria_testability,
        "ambiguity":            round(overall, 3),
        "converged":            converged,
        "target":               target,
        "tier":                 tier,
        # v2.4.0 additions ────────────────────────────────────────
        "milestone":            milestone,
        "floors_passed":        floors_passed,
        "floor_violations":     floor_violations,
        "missing_items":        missing_items,
        # v2.5.0 additions ────────────────────────────────────────
        "questions_asked":      questions_asked,
        "min_questions_required": min_q,
        "min_questions_met":    min_questions_met,
        "pre_filled_dimensions": sorted(pre_filled),
        "dimension_scores": {
            "goal":           round(goal_score, 3),
            "constraint":     round(constraint_score, 3),
            "criteria":       round(criteria_score, 3),
            "technical":      round(technical_score, 3),
            "failure_modes":  round(failure_score, 3),
            "nonfunctional":  round(nonfunctional_score, 3),
            "stakeholder":    round(stakeholder_score, 3),
            "scope_boundary": round(scope_score, 3),
            "success_metrics": round(metrics_score, 3),
            "lifecycle":      round(lifecycle_score, 3),
        },
    }


# ── Milestone + Floors helpers ──────────────────────────────────

def _match_milestone(ambiguity: float) -> dict:
    for name, max_score, description in MILESTONES:
        if ambiguity <= max_score:
            return {"name": name, "max_score": max_score, "description": description}
    return {"name": "INITIAL", "max_score": 1.0, "description": MILESTONES[-1][2]}


def _check_floors(clarities: dict) -> tuple[bool, list[str]]:
    violations = []
    for component, floor in FLOORS.items():
        if clarities.get(component, 0) < floor:
            violations.append(
                f"{component} ({clarities[component]}) < floor ({floor})"
            )
    return (len(violations) == 0, violations)


def _extract_missing_items(state: dict) -> list[str]:
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


# ── Core dimension scorers (v2.4.0) ────────────────────────────

def _score_goal(state: dict) -> float:
    """Score goal ambiguity (0=clear, 1=ambiguous)."""
    penalties = 0.0
    target_user = state.get("target_user", "")
    if not target_user:
        penalties += 0.4
    elif len(target_user) < 10:
        penalties += 0.2
    elif any(v in target_user.lower() for v in ["everyone", "anyone", "people", "users"]):
        penalties += 0.15

    core_problem = state.get("core_problem", "")
    if not core_problem:
        penalties += 0.3
    elif len(core_problem) < 15:
        penalties += 0.15

    core_exp = state.get("core_experience", "")
    if not core_exp:
        penalties += 0.3
    elif len(core_exp) < 10:
        penalties += 0.15

    return min(penalties, 1.0)


def _score_constraints(state: dict) -> float:
    """Score constraint ambiguity (0=clear, 1=ambiguous)."""
    penalties = 0.0
    features = state.get("features", [])
    if not features:
        penalties += 0.3
    elif len(features) > 7:
        penalties += 0.2

    exclusions = state.get("exclusions", [])
    if not exclusions:
        penalties += 0.3
    elif len(exclusions) < 1:
        penalties += 0.15

    constraints = state.get("constraints", [])
    if not constraints:
        penalties += 0.2

    feature_set  = {f.lower() for f in features}
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

    vague_patterns = [
        r"\bgood\b", r"\bnice\b", r"\bfast\b", r"\bclean\b",
        r"\buser.?friendly\b", r"\bintuitive\b", r"\bsmooth\b",
        r"\bprofessional\b", r"\bmodern\b", r"\bresponsive\b",
    ]
    vague_count = sum(
        1 for c in criteria
        if any(re.search(p, c, re.IGNORECASE) for p in vague_patterns)
    )
    if criteria:
        penalties += (vague_count / len(criteria)) * 0.5

    compound_count = sum(
        1 for c in criteria if c.count(",") >= 2 or " and " in c.lower()
    )
    if criteria:
        penalties += (compound_count / len(criteria)) * 0.2

    return min(penalties, 1.0)


# ── Enriched dimension scorers (v2.5.0) ────────────────────────

def _score_technical(state: dict) -> float:
    """Score technical specificity: are tech choices named? (0=yes, 1=no)"""
    constraints = state.get("constraints", [])
    tech_keywords = [
        "supabase", "postgresql", "mysql", "sqlite", "mongodb", "firebase",
        "localstorage", "indexeddb",
        "oauth", "jwt", "magic link", "kakao", "google auth",
        "vercel", "railway", "docker",
        "next.js", "nextjs", "react", "vue", "node", "python", "fastapi",
        "rest", "graphql", "websocket", "sse",
        "no backend", "serverless",
    ]
    text = " ".join(constraints).lower()
    matches = sum(1 for kw in tech_keywords if kw in text)
    if matches >= 2:
        return 0.0
    if matches >= 1:
        return 0.3
    return 0.8


def _score_failure_modes(state: dict) -> float:
    """Score failure/edge case coverage: specific exclusions + constraints? (0=good, 1=missing)"""
    exclusions = state.get("exclusions", [])
    constraints = state.get("constraints", [])
    vague = {"nothing", "none", "n/a", "na", "tbd", "unknown"}
    real_excl = [e for e in exclusions if e.strip().lower() not in vague and len(e) > 3]
    if len(real_excl) >= 3 and len(constraints) >= 2:
        return 0.0
    if len(real_excl) >= 2 or len(constraints) >= 2:
        return 0.3
    if len(real_excl) >= 1:
        return 0.6
    return 1.0


def _score_nonfunctional(state: dict) -> float:
    """Score non-functional coverage: perf/security/a11y addressed? (0=yes, 1=no)"""
    constraints = state.get("constraints", [])
    criteria = state.get("acceptance_criteria", [])
    text = " ".join(constraints + criteria).lower()
    nonfunc_groups = [
        ["second", "ms", "millisecond", "performance", "load time", "ttfb", "lcp"],
        ["secure", "https", "encrypt", "auth", "xss", "csrf", "pii", "no login"],
        ["wcag", "accessible", "a11y", "keyboard", "screen reader"],
        ["offline", "cache", "service worker", "pwa"],
        ["mobile", "responsive", "320px", "touch"],
    ]
    covered = sum(1 for group in nonfunc_groups if any(kw in text for kw in group))
    if covered >= 3:
        return 0.0
    if covered >= 2:
        return 0.3
    if covered >= 1:
        return 0.6
    return 1.0


def _score_stakeholder(state: dict) -> float:
    """Score stakeholder specificity: role + context? (0=specific, 1=vague)"""
    target_user = state.get("target_user", "")
    if not target_user or len(target_user) < 10:
        return 1.0
    vague_only = target_user.strip().lower() in {"users", "people", "everyone", "anyone", "customers"}
    if vague_only:
        return 0.9
    has_number = bool(re.search(r'\d+', target_user))
    has_context = any(kw in target_user.lower() for kw in [
        "who", "that", "with", "at", "managing", "working", "using",
        "freelance", "startup", "enterprise", "solo", "team", "small",
    ])
    if has_number and has_context:
        return 0.0
    if has_number or has_context:
        return 0.2
    return 0.5


def _score_scope_boundary(state: dict) -> float:
    """Score scope sharpness: exclusions concrete and ≥3? (0=sharp, 1=vague)"""
    exclusions = state.get("exclusions", [])
    vague = {"nothing", "none", "n/a", "na", "tbd", "unknown", "all"}
    real = [e for e in exclusions if e.strip().lower() not in vague and len(e) > 3]
    if len(real) >= 3:
        return 0.0
    if len(real) >= 2:
        return 0.2
    if len(real) >= 1:
        return 0.5
    return 0.9


def _score_success_metrics(state: dict) -> float:
    """Score measurability: do ACs have numbers/time targets? (0=measurable, 1=vague)"""
    criteria = state.get("acceptance_criteria", [])
    if not criteria:
        return 1.0
    measurable = sum(
        1 for c in criteria
        if (re.search(r'\d+\s*(ms|s\b|sec|%|items?|px|mb|kb)', c, re.I)
            or re.search(r'[<>≤≥]\s*\d|\d+\s*[-–]\s*\d+', c))
    )
    ratio = measurable / len(criteria)
    if ratio >= 0.3:
        return 0.0
    return round(1.0 - ratio, 3)


def _score_lifecycle(state: dict) -> float:
    """Score lifecycle awareness: onboarding/retention mentioned? (0=yes, 1=no)"""
    all_text = " ".join([
        state.get("core_experience", ""),
        str(state.get("features", [])),
        str(state.get("acceptance_criteria", [])),
    ]).lower()
    lifecycle_keywords = [
        "onboard", "first time", "first-time", "sign up", "register", "new user",
        "return", "notification", "remind", "email", "push",
        "empty state", "tutorial", "welcome", "churn", "inactive",
    ]
    hits = sum(1 for kw in lifecycle_keywords if kw in all_text)
    if hits >= 3:
        return 0.0
    if hits >= 1:
        return 0.4
    return 1.0


# ── Answer Streak Manager (v2.4.0, Ouroboros #02) ───────────────

MAX_AI_STREAK = 3


def update_streak(current_streak: int, answer_source: str) -> dict:
    """Update AI answer streak counter based on answer source."""
    if answer_source in ("from-user", "from-user-correction"):
        new_streak = 0
    elif answer_source in ("from-code", "from-code-auto", "from-research"):
        new_streak = current_streak + 1
    else:
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


# ── Tracks Manager (v2.4.0, Ouroboros #P4 simplified) ───────────

def initialize_tracks(features_or_scope: list[str]) -> list[dict]:
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
    return [
        {**t, "rounds_focused": t.get("rounds_focused", 0) + 1}
        if t["name"] == active_track_name else dict(t)
        for t in tracks
    ]


MAX_ROUNDS_ON_SAME_TRACK = 3


def should_force_breadth(tracks: list[dict]) -> dict:
    if not tracks:
        return {"force_breadth": False, "current_track": None, "unresolved_tracks": [], "reason": None}

    active = max(tracks, key=lambda t: t.get("rounds_focused", 0))
    unresolved = [t["name"] for t in tracks if not t.get("is_resolved", False) and t["name"] != active["name"]]
    force = active.get("rounds_focused", 0) >= MAX_ROUNDS_ON_SAME_TRACK and len(unresolved) > 0

    return {
        "force_breadth": force,
        "current_track": active["name"] if force else None,
        "unresolved_tracks": unresolved if force else [],
        "reason": (
            f"{active['name']}에 {active['rounds_focused']}라운드 집중. 미해결: {', '.join(unresolved)}"
            if force else None
        ),
    }


def mark_track_resolved(tracks: list[dict], track_name: str) -> list[dict]:
    return [
        {**t, "is_resolved": True} if t["name"] == track_name else dict(t)
        for t in tracks
    ]
