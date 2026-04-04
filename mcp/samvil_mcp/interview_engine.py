"""Ambiguity scoring engine for SAMVIL interviews.

Scores interview state across 3 dimensions:
  - Goal clarity (40%) — Can we write a 1-sentence problem statement?
  - Constraint clarity (30%) — Are limits explicit and non-contradictory?
  - Criteria testability (30%) — Are acceptance criteria verifiable?

Each dimension: 0.0 (clear) → 1.0 (ambiguous)
Overall: weighted average. Target: ≤ 0.05.
"""

from __future__ import annotations

import json
import re


def score_ambiguity(interview_state: dict) -> dict:
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

    Returns:
        Dict with per-dimension scores and overall ambiguity.
    """
    goal_score = _score_goal(interview_state)
    constraint_score = _score_constraints(interview_state)
    criteria_score = _score_criteria(interview_state)

    overall = goal_score * 0.4 + constraint_score * 0.3 + criteria_score * 0.3

    return {
        "goal_clarity": round(1.0 - goal_score, 3),
        "constraint_clarity": round(1.0 - constraint_score, 3),
        "criteria_testability": round(1.0 - criteria_score, 3),
        "ambiguity": round(overall, 3),
        "converged": overall <= 0.05,
        "target": 0.05,
    }


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
