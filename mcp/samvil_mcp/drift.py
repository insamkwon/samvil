"""Seed drift measurement — goal alignment across evolution (v4.30 W5.2).

Pattern from ouroboros's 3-component drift measurement: evolution can
produce a seed that converges beautifully on the *wrong* target. The 5
evolve_checks watch quality/regression; this watches **direction**.

Three weighted dimensions, all lexical (deterministic, no LLM):
  goal_drift (0.5)       — description / core_problem token divergence
  constraint_drift (0.3) — constraints set divergence
  ontology_drift (0.2)   — feature-name + AC vocabulary divergence

Pure function over two seed dicts — storage-agnostic by design (callers
already hold the original via get_seed_history / seed v1 file).
"""

from __future__ import annotations

import re
from typing import Any

GOAL_WEIGHT = 0.5
CONSTRAINT_WEIGHT = 0.3
ONTOLOGY_WEIGHT = 0.2

WARNING_THRESHOLD = 0.3
EXCESSIVE_THRESHOLD = 0.6

_TOKEN = re.compile(r"[A-Za-z가-힣0-9]{2,}")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _jaccard_drift(a: set[str], b: set[str]) -> float:
    """1 - Jaccard similarity. Both empty → no drift (nothing to diverge)."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    return round(1.0 - len(a & b) / len(a | b), 4)


def _goal_text(seed: dict[str, Any]) -> str:
    parts = [
        str(seed.get("description") or ""),
        str(seed.get("core_problem") or ""),
        str((seed.get("core_experience") or {}).get("description") or "")
        if isinstance(seed.get("core_experience"), dict)
        else str(seed.get("core_experience") or ""),
    ]
    return " ".join(parts)


def _constraints(seed: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    raw = seed.get("constraints") or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    for item in raw if isinstance(raw, list) else []:
        out |= _tokens(str(item))
    return out


def _ac_tokens(ac: Any) -> set[str]:
    """Tokens from one AC node — handles string ACs, dict ACs in their
    schema variants (description / text / criterion), and AC-tree nodes
    with nested children (v4.30.4 review finding: criterion + children
    were silently skipped, zeroing ontology_drift for tree rewrites)."""
    out: set[str] = set()
    if isinstance(ac, str):
        return _tokens(ac)
    if not isinstance(ac, dict):
        return out
    out |= _tokens(
        str(ac.get("description") or ac.get("text") or ac.get("criterion") or "")
    )
    for child in ac.get("children") or []:
        out |= _ac_tokens(child)
    return out


def _ontology(seed: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for feature in seed.get("features") or []:
        if not isinstance(feature, dict):
            continue
        out |= _tokens(str(feature.get("name") or ""))
        acs = feature.get("acceptance_criteria") or []
        for ac in acs if isinstance(acs, list) else []:
            out |= _ac_tokens(ac)
    return out


def measure_drift(
    original: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    goal = _jaccard_drift(_tokens(_goal_text(original)), _tokens(_goal_text(current)))
    constraint = _jaccard_drift(_constraints(original), _constraints(current))
    ontology = _jaccard_drift(_ontology(original), _ontology(current))

    total = round(
        GOAL_WEIGHT * goal + CONSTRAINT_WEIGHT * constraint + ONTOLOGY_WEIGHT * ontology,
        4,
    )
    if total >= EXCESSIVE_THRESHOLD:
        verdict, action = "excessive", (
            "evolution has drifted from the original goal — pause and ask "
            "the user whether the new direction is intentional (P2)"
        )
    elif total >= WARNING_THRESHOLD:
        verdict, action = "warning", (
            "notable drift — surface the drift summary alongside the "
            "evolve checkpoint so the user sees the direction change"
        )
    else:
        verdict, action = "ok", "direction holds — continue"

    return {
        "goal_drift": goal,
        "constraint_drift": constraint,
        "ontology_drift": ontology,
        "total_drift": total,
        "weights": {
            "goal": GOAL_WEIGHT,
            "constraint": CONSTRAINT_WEIGHT,
            "ontology": ONTOLOGY_WEIGHT,
        },
        "verdict": verdict,
        "next_action": action,
    }
