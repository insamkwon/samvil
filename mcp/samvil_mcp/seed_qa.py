"""Seed-level QA (v4.25.0 — implementation behind v4.23.0 SKILL.md text).

Two responsibilities:

1. **Seed-vs-Interview tracing** (`evaluate_seed_against_interview`) —
   answers "is this seed faithful to what the user said in the
   interview?". For each `seed.constraints`, `seed.out_of_scope`,
   `seed.features[*].acceptance_criteria` leaf, and
   `seed.evaluation_principles[*]`, find a trace in the interview
   record (`interview-progress.json` aggregations). Untraced items are
   semantic drift candidates.

2. **Principle scoring** (`score_acs_against_principles`) — given a
   list of AC verdict records and a list of `seed.evaluation_principles`
   entries, build per-AC `principle_hits` and a weighted overall score.
   Used by samvil-qa Pass 2.5 to anchor verdicts to the seed's own
   declared quality bar.

Both functions are pure — they read inputs and return dicts. No file
writes, no MCP calls. Side-effects belong in the SKILL/server layer.

Why a separate module: keep the matching logic out of the already-fat
event_store / interview_state files, and give samvil-qa a single
import surface for the v4.23 SKILL text it described.
"""

from __future__ import annotations

import re
from typing import Iterable


# ── tracing ──────────────────────────────────────────────────


def _normalize_for_match(text: str) -> str:
    """Lowercase + strip + collapse whitespace + strip trailing punctuation.

    Trace matching is a "did the user say something like this?" check,
    not a string-equality check. We don't want minor punctuation /
    casing / whitespace differences to count as drift.
    """
    if not isinstance(text, str):
        return ""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".:;!?,")
    return text


def _find_trace(
    needle: str,
    haystack: Iterable[str],
    min_token_overlap: int = 2,
) -> dict | None:
    """Find the best trace in haystack for needle.

    Two passes:
    1. Exact (normalized) match → score 1.0
    2. Token-overlap match → score = overlap / max(needle_tokens, hay_tokens)
       (skipped when needle has < min_token_overlap tokens)

    Returns ``{"matched": str, "score": float}`` or None if no match.
    Korean tokenization is *whitespace-only* — it's a heuristic
    "shared salient term" check, not real NLP.
    """
    n_norm = _normalize_for_match(needle)
    if not n_norm:
        return None

    # Pass 1: exact
    for hay in haystack:
        h_norm = _normalize_for_match(hay)
        if h_norm and h_norm == n_norm:
            return {"matched": hay, "score": 1.0, "match_type": "exact"}

    # Pass 2: token overlap
    n_tokens = set(n_norm.split())
    if len(n_tokens) < min_token_overlap:
        return None
    best: dict | None = None
    for hay in haystack:
        h_norm = _normalize_for_match(hay)
        if not h_norm:
            continue
        h_tokens = set(h_norm.split())
        if not h_tokens:
            continue
        overlap = len(n_tokens & h_tokens)
        if overlap < min_token_overlap:
            continue
        score = overlap / max(len(n_tokens), len(h_tokens))
        if score >= 0.4 and (best is None or score > best["score"]):
            best = {"matched": hay, "score": round(score, 3), "match_type": "overlap"}
    return best


def evaluate_seed_against_interview(
    seed: dict,
    interview_progress: dict,
) -> dict:
    """Trace every user-claim in the seed back to the interview record.

    Args:
        seed: parsed project.seed.json
        interview_progress: result of interview_state.load_progress()
            (must have `constraints_aggregated`, `out_of_scope_aggregated`,
            `ac_by_phase`, `refined_answers`)

    Returns:
        {
            "ok": True,
            "verdict": "PASS" | "PARTIAL" | "FAIL",
            "coverage_score": float (0.0-1.0),
            "traced": {category: int},
            "untraced": {category: [items]},
            "details": [{category, item, trace?}, ...],
            "thresholds": {pass_min, partial_min},
            "notes": [...],
        }

    Verdict thresholds:
        PASS   coverage_score >= 0.85 AND zero untraced constraints
        PARTIAL coverage_score >= 0.60
        FAIL   below 0.60
    """
    if not isinstance(seed, dict):
        return {"ok": False, "error": "seed must be a dict"}
    if not isinstance(interview_progress, dict):
        return {"ok": False, "error": "interview_progress must be a dict"}

    constraints_pool = list(interview_progress.get("constraints_aggregated") or [])
    out_of_scope_pool = list(interview_progress.get("out_of_scope_aggregated") or [])

    # Pool of every AC the user heard during interview, flattened
    ac_pool: list[str] = []
    for phase, acs in (interview_progress.get("ac_by_phase") or {}).items():
        if isinstance(acs, list):
            ac_pool.extend(str(a) for a in acs if a)

    # Pool of every "decision" / "reasoning" text from refined answers
    decision_pool: list[str] = []
    for entry in interview_progress.get("refined_answers") or []:
        payload = entry.get("payload", {}) if isinstance(entry, dict) else {}
        for field in ("decision", "reasoning"):
            text = payload.get(field)
            if isinstance(text, str) and text.strip():
                decision_pool.append(text.strip())

    details: list[dict] = []
    traced = {"constraints": 0, "out_of_scope": 0, "ac": 0, "principles": 0}
    untraced: dict[str, list[str]] = {
        "constraints": [],
        "out_of_scope": [],
        "ac": [],
        "principles": [],
    }

    def _check(category: str, item: str, pool: list[str]) -> None:
        trace = _find_trace(item, pool)
        if trace:
            traced[category] += 1
            details.append({"category": category, "item": item, "trace": trace})
        else:
            untraced[category].append(item)
            details.append({"category": category, "item": item, "trace": None})

    for c in seed.get("constraints") or []:
        if isinstance(c, str) and c.strip():
            _check("constraints", c.strip(), constraints_pool)

    for o in seed.get("out_of_scope") or []:
        if isinstance(o, str) and o.strip():
            _check("out_of_scope", o.strip(), out_of_scope_pool)

    for feature in seed.get("features") or []:
        if not isinstance(feature, dict):
            continue
        for ac in feature.get("acceptance_criteria") or []:
            if isinstance(ac, dict):
                desc = ac.get("description", "")
                if isinstance(desc, str) and desc.strip():
                    _check("ac", desc.strip(), ac_pool + decision_pool)
            elif isinstance(ac, str) and ac.strip():
                _check("ac", ac.strip(), ac_pool + decision_pool)

    for principle in seed.get("evaluation_principles") or []:
        if not isinstance(principle, dict):
            continue
        rationale = principle.get("rationale", "")
        # principle is "traced" if its rationale (or the principle text)
        # appears in interview material — that proves it isn't fabricated
        target = (rationale or principle.get("principle", "")).strip()
        if target:
            _check(
                "principles",
                target,
                constraints_pool + ac_pool + decision_pool + out_of_scope_pool,
            )

    total = sum(traced.values()) + sum(len(v) for v in untraced.values())
    if total == 0:
        coverage = 0.0
        verdict = "FAIL"
        notes = ["Seed has no checkable items (constraints / out_of_scope / ACs / principles all empty)."]
    else:
        coverage = round(sum(traced.values()) / total, 3)
        # Constraints are stricter — drift on a hard constraint is worse than
        # drift on an aspirational principle.
        zero_constraint_drift = len(untraced["constraints"]) == 0
        if coverage >= 0.85 and zero_constraint_drift:
            verdict = "PASS"
        elif coverage >= 0.60:
            verdict = "PARTIAL"
        else:
            verdict = "FAIL"
        notes = []
        if not zero_constraint_drift and coverage >= 0.85:
            notes.append(
                f"Coverage is high but {len(untraced['constraints'])} constraint(s) untraced — downgraded to PARTIAL."
            )
            verdict = "PARTIAL"

    return {
        "ok": True,
        "verdict": verdict,
        "coverage_score": coverage,
        "traced": traced,
        "untraced": untraced,
        "details": details,
        "thresholds": {"pass_min": 0.85, "partial_min": 0.60},
        "notes": notes,
    }


# ── principle scoring ────────────────────────────────────────


def score_acs_against_principles(
    ac_verdicts: list[dict],
    evaluation_principles: list[dict],
) -> dict:
    """Match each AC verdict against the seed's evaluation_principles.

    Args:
        ac_verdicts: list of {leaf_id, criterion (str), verdict (str),
            evidence (str or list)}. `verdict` interpreted as
            satisfied when in {"PASS", "PARTIAL"}.
        evaluation_principles: list of
            {principle, weight (0-1, default 0.5), rationale?, source_phase?}

    Returns:
        {
            "ok": True,
            "per_leaf": [
                {
                    "leaf_id": str,
                    "principle_hits": [
                        {"principle": str, "weight": float, "satisfied": bool}
                    ],
                    "weighted_score": float (0-1),
                    "downgrade_recommended": bool,
                },
                ...
            ],
            "weight_violations": [...],  # principles weighted >= 0.5
                                          # that more than half of leaves violate
            "overall_weighted_score": float,
        }

    Downgrade rule (anchors v4.23 SKILL text): a leaf marked PASS or
    PARTIAL is recommended for downgrade to PARTIAL when its
    weighted_score < 0.5 AND at least one principle of weight ≥ 0.5 is
    unsatisfied.
    """
    if not isinstance(ac_verdicts, list):
        return {"ok": False, "error": "ac_verdicts must be a list"}
    if not isinstance(evaluation_principles, list):
        return {"ok": False, "error": "evaluation_principles must be a list"}

    # Normalize principles
    norm_principles: list[dict] = []
    for p in evaluation_principles:
        if not isinstance(p, dict):
            continue
        principle = str(p.get("principle", "")).strip()
        if not principle:
            continue
        weight = p.get("weight", 0.5)
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 0.5
        weight = max(0.0, min(1.0, weight))
        norm_principles.append({"principle": principle, "weight": weight})

    if not norm_principles:
        return {
            "ok": True,
            "per_leaf": [{"leaf_id": v.get("leaf_id", ""), "principle_hits": [],
                          "weighted_score": 1.0, "downgrade_recommended": False}
                         for v in ac_verdicts if isinstance(v, dict)],
            "weight_violations": [],
            "overall_weighted_score": 1.0,
            "notes": ["No evaluation_principles provided — no scoring applied."],
        }

    per_leaf: list[dict] = []
    # Track which principles each leaf failed, for violation analysis
    violations_per_principle: dict[str, int] = {p["principle"]: 0 for p in norm_principles}

    for v in ac_verdicts:
        if not isinstance(v, dict):
            continue
        leaf_id = str(v.get("leaf_id", ""))
        criterion = str(v.get("criterion", ""))
        verdict = str(v.get("verdict", "")).upper()
        ac_satisfied = verdict in {"PASS", "PARTIAL"}

        principle_hits: list[dict] = []
        weighted_satisfied = 0.0
        weighted_total = 0.0

        for p in norm_principles:
            # A principle is "satisfied" by this leaf iff:
            #   - the AC text is plausibly related to the principle, AND
            #   - the AC itself is satisfied (PASS/PARTIAL)
            # "Plausibly related" = token-overlap match (cheap heuristic).
            relevant = _find_trace(p["principle"], [criterion]) is not None
            satisfied = ac_satisfied if relevant else True  # irrelevant → neutral
            principle_hits.append({
                "principle": p["principle"],
                "weight": p["weight"],
                "satisfied": satisfied,
                "relevant": relevant,
            })
            if relevant:
                weighted_total += p["weight"]
                if satisfied:
                    weighted_satisfied += p["weight"]
                else:
                    violations_per_principle[p["principle"]] += 1

        weighted_score = (weighted_satisfied / weighted_total) if weighted_total > 0 else 1.0
        weighted_score = round(weighted_score, 3)

        # Downgrade recommendation
        high_weight_violated = any(
            h["weight"] >= 0.5 and h["relevant"] and not h["satisfied"]
            for h in principle_hits
        )
        downgrade = ac_satisfied and weighted_score < 0.5 and high_weight_violated

        per_leaf.append({
            "leaf_id": leaf_id,
            "principle_hits": principle_hits,
            "weighted_score": weighted_score,
            "downgrade_recommended": downgrade,
        })

    total_leaves = len(per_leaf) or 1
    weight_violations = [
        {"principle": p, "violations": n, "violation_rate": round(n / total_leaves, 3)}
        for p, n in violations_per_principle.items()
        if n > 0
    ]
    overall = round(
        sum(l["weighted_score"] for l in per_leaf) / total_leaves,
        3,
    ) if per_leaf else 1.0

    return {
        "ok": True,
        "per_leaf": per_leaf,
        "weight_violations": weight_violations,
        "overall_weighted_score": overall,
    }


# ── exit conditions ─────────────────────────────────────────


def evaluate_exit_conditions(
    seed: dict,
    qa_state: dict,
) -> dict:
    """Check whether all `seed.exit_conditions` are met given current
    qa_state.

    This is intentionally minimal — exit conditions are Korean prose
    that humans interpret. We provide a structural check (the seed
    *has* exit conditions; the qa_state *has* enough data to evaluate
    them) and surface them to the caller for final LLM judgment in
    samvil-qa Phase Z. We do NOT try to LLM-interpret the conditions
    here — that's a SKILL responsibility.

    Args:
        seed: parsed project.seed.json
        qa_state: dict from samvil-qa Phase Z including
            {features_passed, features_failed, leaf_counts, ...}

    Returns:
        {
            "ok": True,
            "has_exit_conditions": bool,
            "conditions": [str, ...],
            "structurally_evaluable": bool,
            "auto_check": {
                "all_features_passed": bool,
                "high_weight_principles_satisfied": bool | None,
            },
            "verdict_blocked": bool,
            "notes": [...],
        }

    The `verdict_blocked` flag is the SKILL-level signal: if True,
    samvil-qa Phase Z cannot return PASS — the conditions are not
    satisfied yet.
    """
    if not isinstance(seed, dict):
        return {"ok": False, "error": "seed must be a dict"}
    if not isinstance(qa_state, dict):
        return {"ok": False, "error": "qa_state must be a dict"}

    conditions = seed.get("exit_conditions") or []
    if not isinstance(conditions, list):
        conditions = []

    if not conditions:
        # No exit conditions → falls back to existing samvil-qa
        # convergence rules (3-condition AND). Don't block.
        return {
            "ok": True,
            "has_exit_conditions": False,
            "conditions": [],
            "structurally_evaluable": False,
            "auto_check": {},
            "verdict_blocked": False,
            "notes": ["No exit_conditions in seed — falls back to v4.22 convergence rules."],
        }

    # Structural auto-check on the most common patterns
    features_total = qa_state.get("features_total") or len(seed.get("features") or [])
    features_passed = qa_state.get("features_passed", 0)
    all_features_passed = (features_total > 0 and features_passed >= features_total)

    high_weight_satisfied: bool | None = None
    if seed.get("evaluation_principles"):
        principle_scores = qa_state.get("principle_overall_score", None)
        if isinstance(principle_scores, (int, float)):
            high_weight_satisfied = principle_scores >= 0.8

    # Heuristic blocking: if exit_conditions explicitly mention
    # features must PASS but qa_state shows failures, block.
    blocked = False
    notes: list[str] = []
    for condition in conditions:
        c_lower = condition.lower() if isinstance(condition, str) else ""
        if "acceptance" in c_lower or "ac" in c_lower or "features" in c_lower:
            if not all_features_passed:
                blocked = True
                notes.append(
                    f"Exit condition references features/ACs but {features_total - features_passed} feature(s) still failing — blocking PASS."
                )
                break
        if "evaluation_principles" in c_lower or "principle" in c_lower:
            if high_weight_satisfied is False:
                blocked = True
                notes.append(
                    f"Exit condition references evaluation_principles but high-weight principles not satisfied — blocking PASS."
                )
                break

    return {
        "ok": True,
        "has_exit_conditions": True,
        "conditions": list(conditions),
        "structurally_evaluable": True,
        "auto_check": {
            "all_features_passed": all_features_passed,
            "high_weight_principles_satisfied": high_weight_satisfied,
        },
        "verdict_blocked": blocked,
        "notes": notes,
    }
