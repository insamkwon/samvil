"""Interview v3.2 — ② full.

Per HANDOFF-v3.2-DECISIONS.md §3.②: the interview axis becomes
`interview_level` (quick / normal / deep / max / auto), orthogonal to
`samvil_tier`. Six techniques ship as independent modules:

  T1 — multi-dimensional seed_readiness scoring
  T2 — meta self-probe ("what did I miss?")
  T3 — user confidence marking
  T4 — scenario simulation
  T5 — adversarial interviewer (needs ④ different provider)
  T6 — PAL adaptive level selection

This module owns:
  * The `InterviewLevel` enum and level → techniques mapping.
  * `seed_readiness` scoring (T1): pure-Python weighted sum over 5 dims.
  * Meta-probe heuristic (T2): prompt generator + blind-spot list.
  * User confidence marking (T3): tacit-extraction follow-ups.
  * Scenario simulation (T4): walk a draft seed through a toy timeline.
  * Adversarial pass (T5): prompt hints; actual execution requires ④.
  * PAL adaptive selection (T6): complexity → level.

Everything that needs an LLM call is exposed as a *prompt* + *result
parser*. Skills drive the LLM call; this module owns the logic and
thresholds so tests can cover the numeric paths deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gates import ESCALATION_CHECKS  # for hinting which checks escalate


# ── Enums ─────────────────────────────────────────────────────────────


class InterviewLevel(str, Enum):
    QUICK = "quick"
    NORMAL = "normal"
    DEEP = "deep"
    MAX = "max"
    AUTO = "auto"


class Technique(str, Enum):
    SEED_READINESS = "seed_readiness"
    META_SELF_PROBE = "meta_self_probe"
    USER_CONFIDENCE = "user_confidence"
    SCENARIO_SIMULATION = "scenario_simulation"
    ADVERSARIAL = "adversarial"
    PAL_ADAPTIVE = "pal_adaptive"


LEVEL_TO_TECHNIQUES: dict[InterviewLevel, tuple[Technique, ...]] = {
    InterviewLevel.QUICK: (Technique.SEED_READINESS,),
    InterviewLevel.NORMAL: (
        Technique.SEED_READINESS,
        Technique.META_SELF_PROBE,
        Technique.SCENARIO_SIMULATION,
    ),
    InterviewLevel.DEEP: (
        Technique.SEED_READINESS,
        Technique.META_SELF_PROBE,
        Technique.USER_CONFIDENCE,
        Technique.SCENARIO_SIMULATION,
    ),
    InterviewLevel.MAX: (
        Technique.SEED_READINESS,
        Technique.META_SELF_PROBE,
        Technique.USER_CONFIDENCE,
        Technique.SCENARIO_SIMULATION,
        Technique.ADVERSARIAL,
    ),
    InterviewLevel.AUTO: (Technique.PAL_ADAPTIVE,),
}


# ── T1 — seed_readiness scoring ───────────────────────────────────────


# Weights are `(initial estimate)` per §3.②. They're registered as
# experimental_policy entries by scripts/seed-experiments.py.
READINESS_WEIGHTS: dict[str, float] = {
    "intent_clarity": 0.25,
    "constraint_clarity": 0.20,
    "ac_testability": 0.25,
    "lifecycle_coverage": 0.20,
    "decision_boundary": 0.10,
}
assert abs(sum(READINESS_WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"

# Per-dimension floors (initial estimates, scoped by samvil_tier).
READINESS_FLOORS: dict[str, dict[str, float]] = {
    "minimal": {
        "intent_clarity": 0.60,
        "constraint_clarity": 0.60,
        "ac_testability": 0.60,
        "lifecycle_coverage": 0.50,
        "decision_boundary": 0.40,
    },
    "standard": {
        "intent_clarity": 0.75,
        "constraint_clarity": 0.70,
        "ac_testability": 0.85,
        "lifecycle_coverage": 0.80,
        "decision_boundary": 0.70,
    },
    "thorough": {
        "intent_clarity": 0.85,
        "constraint_clarity": 0.80,
        "ac_testability": 0.90,
        "lifecycle_coverage": 0.85,
        "decision_boundary": 0.90,
    },
    "full": {
        "intent_clarity": 0.90,
        "constraint_clarity": 0.85,
        "ac_testability": 0.95,
        "lifecycle_coverage": 0.90,
        "decision_boundary": 0.95,
    },
    "deep": {
        "intent_clarity": 0.92,
        "constraint_clarity": 0.90,
        "ac_testability": 0.98,
        "lifecycle_coverage": 0.95,
        "decision_boundary": 0.98,
    },
}


@dataclass
class SeedReadinessScore:
    total: float
    dimensions: dict[str, float]
    floors: dict[str, float]
    below_floor: list[str]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "dimensions": self.dimensions,
            "floors": self.floors,
            "below_floor": self.below_floor,
        }


def compute_seed_readiness(
    dimensions: dict[str, float],
    *,
    samvil_tier: str = "standard",
) -> SeedReadinessScore:
    """Pure function. Caller populates each dimension in [0, 1].

    Tiers control per-dim floors, not the weighted sum — the weights
    themselves are fixed by the spec to keep score semantics constant
    across tiers.
    """
    missing = set(READINESS_WEIGHTS) - set(dimensions)
    if missing:
        # Treat missing dimensions as 0 — honest about the gap.
        dimensions = {**{k: 0.0 for k in missing}, **dimensions}
    total = sum(
        dimensions[k] * w
        for k, w in READINESS_WEIGHTS.items()
    )
    floors = READINESS_FLOORS.get(samvil_tier, READINESS_FLOORS["standard"])
    below = [k for k, v in dimensions.items() if v < floors.get(k, 0.0)]
    return SeedReadinessScore(
        total=total,
        dimensions={k: float(dimensions.get(k, 0.0)) for k in READINESS_WEIGHTS},
        floors=dict(floors),
        below_floor=below,
    )


# ── T2 — Meta Self-Probe ──────────────────────────────────────────────


_META_PROBE_PROMPT = """\
Role: interview auditor for the SAMVIL v3.2 harness.

Context: the interview just finished phase {phase!r}. Here are the answers
so far (structured):
---
{answers_summary}
---

Produce a JSON object with two keys:
  "blind_spots" : array of strings — concrete things the interview
                   MIGHT have missed. Each entry is one sentence.
  "followups"    : array of strings — targeted follow-up questions that
                   would plug those gaps. Each is a single question.

Rules:
  - Emit 0–3 items per key. 0 is acceptable if you're confident the
    phase is thorough.
  - Do not include boilerplate. Short, specific sentences only.
  - If a blind spot is about evidence (claims/gates), use the phrase
    "evidence gap".
"""


def build_meta_probe_prompt(*, phase: str, answers_summary: str) -> str:
    return _META_PROBE_PROMPT.format(phase=phase, answers_summary=answers_summary)


_BLIND_SPOT_KEYWORDS = (
    "evidence gap",
    "ac_testability",
    "lifecycle_coverage",
    "decision_boundary_clarity",
)


def parse_meta_probe_result(raw: str) -> dict[str, list[str]]:
    """Best-effort parser for the meta-probe LLM response.

    Accepts the expected JSON object. Falls back to a heuristic extractor
    if the response is free-form (common failure mode for small models).
    """
    import json as _json

    try:
        data = _json.loads(raw)
        if isinstance(data, dict):
            return {
                "blind_spots": list(data.get("blind_spots") or []),
                "followups": list(data.get("followups") or []),
            }
    except Exception:
        pass

    # Heuristic: treat lines starting with "- " as items, bucketed by
    # whether "question" or "?" is in the line.
    blind: list[str] = []
    follow: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        s = s[2:].strip()
        if "?" in s or "question" in s.lower():
            follow.append(s)
        else:
            blind.append(s)
    return {"blind_spots": blind[:3], "followups": follow[:3]}


# ── T3 — User confidence marking ──────────────────────────────────────


def confidence_follow_up(
    *,
    answer: str,
    confidence: int,
    low_threshold: int = 2,
) -> str | None:
    """When confidence ≤ threshold, emit a tacit-extraction follow-up
    question. Returns None if confidence is high enough to skip.
    """
    if confidence > low_threshold:
        return None
    # Target an example to extract tacit knowledge from low-confidence answers.
    example_ask = (
        "Can you give a concrete example of a recent time you saw this in "
        "practice (project, date, what happened)? "
        "Even a rough one helps us pin down what you actually mean."
    )
    return (
        f"You marked confidence={confidence} on: '{answer.strip()}'. "
        f"{example_ask}"
    )


# ── T4 — Scenario simulation ──────────────────────────────────────────


@dataclass
class SimulationStep:
    label: str
    detail: str = ""
    contradictions: list[str] = field(default_factory=list)


def scenario_simulate(
    *,
    features: list[dict],
    timeline: tuple[str, ...] = (
        "first-time user arrives",
        "user completes happy path",
        "user encounters edge case",
        "user returns next day",
    ),
) -> list[SimulationStep]:
    """Walk features against a fixed default timeline and flag
    contradictions.

    A contradiction is heuristic: a feature claims P1 priority but
    depends on a feature that isn't present; a feature's `independent`
    flag is True but its `depends_on` is non-empty.
    """
    steps: list[SimulationStep] = []
    feature_names = {f.get("name") for f in features}
    for label in timeline:
        step = SimulationStep(label=label)
        for f in features:
            name = f.get("name", "?")
            deps = f.get("depends_on") or []
            if f.get("independent") and deps:
                step.contradictions.append(
                    f"feature {name!r} marked independent but depends_on={deps}"
                )
            for d in deps:
                if d not in feature_names:
                    step.contradictions.append(
                        f"feature {name!r} depends on {d!r} which is not declared"
                    )
        steps.append(step)
    return steps


# ── T5 — Adversarial (prompt only) ────────────────────────────────────


_ADVERSARIAL_PROMPT = """\
You are an adversarial interviewer. The SAMVIL harness has produced
this interview summary on {samvil_tier!r} tier. Your job is to find
PLAUSIBLE failure paths: ways this project could ship and be wrong.

Interview summary:
---
{summary}
---

Return JSON:
  "plausible_failures": [ {{ "title": "...", "why": "...", "probe": "..." }} ]
  "missing_questions":  [ "string", ... ]

Rules:
  - Lean into specificity. "The login flow is brittle" is not useful;
    "if the auth token expires during the payment step, the cart silently
    clears" is useful.
  - Propose no more than 5 failures and 5 missing questions.
  - Route hits to escalation checks when possible (tag any failure
    whose root cause is one of: {escalation_checks}).
"""


def build_adversarial_prompt(*, summary: str, samvil_tier: str = "standard") -> str:
    return _ADVERSARIAL_PROMPT.format(
        summary=summary,
        samvil_tier=samvil_tier,
        escalation_checks=sorted(ESCALATION_CHECKS),
    )


# ── T6 — PAL adaptive selection ──────────────────────────────────────


_COMPLEXITY_HINTS_HIGH = re.compile(
    r"\b(multi[- ]tenant|real[- ]time|collaborative|concurrent|"
    r"payments?|auth(entication)?|compliance|billing|"
    r"streaming|websocket|offline|sync|encryption|migration)\b",
    re.IGNORECASE,
)
_COMPLEXITY_HINTS_MED = re.compile(
    r"\b(dashboard|chart|admin|workflow|pipeline|queue|integration)\b",
    re.IGNORECASE,
)


def pal_select_level(
    *,
    project_prompt: str,
    solution_type: str | None = None,
    samvil_tier: str = "standard",
) -> InterviewLevel:
    """Pick the interview level from the one-line project prompt.

    Simple ruleset (initial estimate):
      * High complexity markers → `deep` (`max` on thorough+)
      * Medium complexity → `normal`
      * Low / unclear → `quick`
      * solution_type=automation → `quick` (automation usually small)
      * solution_type=game → `normal`
    """
    text = project_prompt or ""
    if solution_type == "automation":
        return InterviewLevel.QUICK
    if solution_type == "game":
        return InterviewLevel.NORMAL
    if _COMPLEXITY_HINTS_HIGH.search(text):
        if samvil_tier in ("thorough", "full", "deep"):
            return InterviewLevel.MAX
        return InterviewLevel.DEEP
    if _COMPLEXITY_HINTS_MED.search(text):
        return InterviewLevel.NORMAL
    return InterviewLevel.QUICK


# ── Level → techniques helper ─────────────────────────────────────────


def techniques_for_level(level: InterviewLevel) -> tuple[Technique, ...]:
    return LEVEL_TO_TECHNIQUES.get(level, ())


def resolve_level(
    requested: InterviewLevel | str,
    *,
    project_prompt: str | None = None,
    solution_type: str | None = None,
    samvil_tier: str = "standard",
    provider_router_ready: bool = False,
) -> InterviewLevel:
    """Turn `auto` into a concrete level using PAL. Also downgrades `max`
    to `deep` when ④ routing isn't ready (no second-provider adversarial).
    """
    lvl = InterviewLevel(requested) if isinstance(requested, str) else requested
    if lvl == InterviewLevel.AUTO:
        lvl = pal_select_level(
            project_prompt=project_prompt or "",
            solution_type=solution_type,
            samvil_tier=samvil_tier,
        )
    if lvl == InterviewLevel.MAX and not provider_router_ready:
        # L5 adversarial needs a different-provider model. Downgrade.
        return InterviewLevel.DEEP
    return lvl
