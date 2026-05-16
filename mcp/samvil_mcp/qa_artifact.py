"""Standalone artifact QA module (v4.29.0 — backs samvil-qa --target=artifact).

samvil-qa SKILL (v4.27) described 5-dim weighted rubric scoring for
arbitrary artifacts (code / doc / API response / screenshot). v4.29
ships the real implementation so the SKILL is no longer aspirational.

Pure functions: take an artifact + a quality bar, produce a structured
verdict with per-dimension scores and actionable suggestions.

The scoring is *heuristic*, not LLM-aided. The 5-dim rubric is a
deterministic structural analysis. samvil-qa SKILL invokes this to
get a baseline; the SKILL/LLM can then *augment* the verdict with
LLM judgment if it has context the heuristic can't see (e.g. domain
semantics). This split keeps the contract clear: machine gives the
structural floor, LLM adds semantic depth on top.

Returns shape mirrors what samvil-qa SKILL v4.27 promised, so swapping
the aspirational text for the real call is a 1:1 substitution.
"""

from __future__ import annotations

import re
from typing import Literal

ArtifactType = Literal["code", "test_output", "document", "api_response", "screenshot", "custom"]

# Verdict thresholds match Ouroboros qa-judge for cross-system consistency.
PASS_THRESHOLD = 0.80
REVISE_THRESHOLD = 0.40


# Dimension weights default to equal. Caller can override via
# `dimension_weights` to emphasize e.g. correctness over polish.
DEFAULT_WEIGHTS = {
    "correctness": 0.30,
    "completeness": 0.20,
    "quality": 0.20,
    "intent_alignment": 0.20,
    "domain_specific": 0.10,
}


# ── per-dimension heuristic scorers ─────────────────────────


def _score_correctness(text: str, artifact_type: str) -> tuple[float, list[str]]:
    """Heuristic correctness signal.

    For code: no syntax-error-pattern strings, balanced braces/brackets,
    no `TODO`/`FIXME`/`XXX` markers (those signal known incorrectness).
    For document: no `???` / `TBD` / `[placeholder]`.
    For api_response: parseable as JSON if it starts with `{`/`[`.
    For test_output: no `FAIL`/`ERROR` lines.
    """
    suggestions: list[str] = []
    score = 1.0

    if artifact_type in ("code", "custom"):
        for pattern, weight, msg in [
            (r"\bTODO\b", 0.1, "Resolve TODO markers — they indicate known incompleteness."),
            (r"\bFIXME\b", 0.15, "Resolve FIXME markers — known bugs."),
            (r"\bXXX\b", 0.05, "Resolve XXX markers."),
        ]:
            hits = len(re.findall(pattern, text))
            if hits > 0:
                score -= weight * min(hits, 3) / 3
                suggestions.append(f"{msg} ({hits} occurrence(s))")
        # crude balance check
        for open_c, close_c in [("{", "}"), ("(", ")"), ("[", "]")]:
            o = text.count(open_c)
            c = text.count(close_c)
            if o != c:
                score -= 0.15
                suggestions.append(f"Unbalanced {open_c}{close_c}: {o} open vs {c} close.")

    elif artifact_type == "document":
        for marker in ("???", "TBD", "[placeholder]"):
            if marker in text:
                score -= 0.1
                suggestions.append(f"Resolve placeholder marker: {marker!r}")

    elif artifact_type == "api_response":
        stripped = text.strip()
        if stripped.startswith(("{", "[")):
            try:
                import json as _json
                _json.loads(stripped)
            except _json.JSONDecodeError as exc:
                score -= 0.4
                suggestions.append(f"Response looks like JSON but failed to parse: {exc.msg}.")

    elif artifact_type == "test_output":
        for line in text.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            # FAIL/ERROR/FAILED can appear anywhere on the line (e.g.
            # "test_two ... FAIL"), not only as line prefix.
            if any(marker in upper for marker in ("FAIL", "ERROR")):
                score -= 0.2
                suggestions.append(f"Test failure detected: {stripped[:80]}")
                break

    return max(0.0, min(1.0, score)), suggestions


def _score_completeness(text: str, artifact_type: str) -> tuple[float, list[str]]:
    """Heuristic completeness — empty / suspiciously short content."""
    suggestions: list[str] = []
    length = len(text.strip())
    if length == 0:
        return 0.0, ["Artifact is empty."]
    if length < 50:
        return 0.3, ["Artifact is very short (<50 chars) — likely incomplete."]
    if length < 200:
        return 0.6, ["Artifact is short — verify it captures the full scope."]
    if artifact_type == "document" and length < 500:
        return 0.7, ["Document is short for a document artifact — section coverage may be thin."]
    return 1.0, []


def _score_quality(text: str, artifact_type: str) -> tuple[float, list[str]]:
    """Heuristic quality — style / readability cues."""
    suggestions: list[str] = []
    score = 1.0

    if artifact_type in ("code", "custom"):
        # very long lines reduce readability
        long_lines = [ln for ln in text.splitlines() if len(ln) > 120]
        if long_lines:
            ratio = len(long_lines) / max(1, len(text.splitlines()))
            score -= min(0.3, ratio)
            suggestions.append(f"{len(long_lines)} line(s) exceed 120 chars — consider wrapping.")

        # bare `print(` and similar debugging artifacts
        for pattern, msg in [
            (r"\bprint\(", "Bare print() — consider proper logging."),
            (r"console\.log\(", "console.log() left in code — consider proper logging."),
        ]:
            if re.search(pattern, text):
                score -= 0.1
                suggestions.append(msg)

    elif artifact_type == "document":
        # No headings at all → flat doc, harder to navigate
        if not re.search(r"^#+\s", text, re.MULTILINE):
            score -= 0.2
            suggestions.append("Document has no markdown headings — structure is implicit.")

    return max(0.0, min(1.0, score)), suggestions


def _score_intent_alignment(text: str, quality_bar: str) -> tuple[float, list[str]]:
    """Heuristic alignment with the stated quality_bar via token overlap.

    quality_bar tokens that don't appear in the artifact suggest the
    artifact may have drifted from the user's stated goal.
    """
    suggestions: list[str] = []
    if not quality_bar.strip():
        return 1.0, []
    bar_tokens = {t.lower() for t in re.findall(r"[a-zA-Z가-힣]{3,}", quality_bar)}
    text_tokens = {t.lower() for t in re.findall(r"[a-zA-Z가-힣]{3,}", text)}
    if not bar_tokens:
        return 1.0, []
    overlap = bar_tokens & text_tokens
    coverage = len(overlap) / len(bar_tokens)
    if coverage < 0.3:
        suggestions.append(
            f"Only {len(overlap)}/{len(bar_tokens)} quality-bar token(s) appear in artifact — "
            "may not address the stated goal."
        )
    return round(coverage, 3) if coverage > 0 else 0.0, suggestions


def _score_domain_specific(text: str, artifact_type: str) -> tuple[float, list[str]]:
    """Per-type domain checks. Lightweight."""
    suggestions: list[str] = []
    if artifact_type == "code":
        if not re.search(r"\bdef |\bclass |\bfunction |\bconst |\blet ", text):
            return 0.7, ["No function/class definitions detected — verify this is the right artifact."]
    elif artifact_type == "api_response":
        if not text.strip().startswith(("{", "[", "<")):
            return 0.5, ["API response doesn't look structured (not JSON/XML)."]
    elif artifact_type == "test_output":
        if not re.search(r"\b(passed|PASSED|ok|OK|test|FAIL|ERROR)\b", text):
            return 0.5, ["Test output has no recognizable test result markers."]
    return 1.0, []


# ── orchestrator ────────────────────────────────────────────


def score_artifact(
    artifact: str,
    quality_bar: str = "",
    artifact_type: str = "custom",
    dimension_weights: dict | None = None,
    pass_threshold: float = PASS_THRESHOLD,
    revise_threshold: float = REVISE_THRESHOLD,
) -> dict:
    """Score an artifact across 5 dimensions, return verdict.

    Returns:
        {
            "ok": True,
            "score": float (weighted average, 0.0-1.0),
            "verdict": "PASS" | "REVISE" | "FAIL",
            "loop_action": "done" | "continue" | "escalate",
            "dimensions": {dim_name: float, ...},
            "suggestions": [str, ...],
            "weights_applied": {dim_name: weight},
            "thresholds": {pass, revise},
            "artifact_type": str,
        }

    Verdict mapping:
        score >= pass_threshold → PASS / done
        revise_threshold <= score < pass_threshold → REVISE / continue
        score < revise_threshold → FAIL / escalate
    """
    if not isinstance(artifact, str):
        return {"ok": False, "error": "artifact must be a string (use Read tool for files)"}
    if artifact_type not in ("code", "test_output", "document", "api_response", "screenshot", "custom"):
        return {"ok": False, "error": f"unknown artifact_type: {artifact_type}"}

    # Empty artifact short-circuits to FAIL — no point running heuristics on
    # nothing. Without this guard, the other dimensions default to 1.0 and
    # the weighted score lands at ~0.6 (REVISE), which would be misleading.
    if not artifact.strip():
        return {
            "ok": True,
            "score": 0.0,
            "verdict": "FAIL",
            "loop_action": "escalate",
            "dimensions": {k: 0.0 for k in DEFAULT_WEIGHTS},
            "suggestions": ["Artifact is empty — nothing to evaluate."],
            "weights_applied": {k: round(v, 3) for k, v in DEFAULT_WEIGHTS.items()},
            "thresholds": {"pass": pass_threshold, "revise": revise_threshold},
            "artifact_type": artifact_type,
        }

    weights = dict(DEFAULT_WEIGHTS)
    if isinstance(dimension_weights, dict):
        for k, v in dimension_weights.items():
            if k in weights and isinstance(v, (int, float)) and 0.0 <= v <= 1.0:
                weights[k] = float(v)
    # Normalize weights so they sum to 1
    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}

    dimensions: dict[str, float] = {}
    all_suggestions: list[str] = []

    score, s = _score_correctness(artifact, artifact_type)
    dimensions["correctness"] = round(score, 3)
    all_suggestions.extend(s)

    score, s = _score_completeness(artifact, artifact_type)
    dimensions["completeness"] = round(score, 3)
    all_suggestions.extend(s)

    score, s = _score_quality(artifact, artifact_type)
    dimensions["quality"] = round(score, 3)
    all_suggestions.extend(s)

    score, s = _score_intent_alignment(artifact, quality_bar)
    dimensions["intent_alignment"] = round(score, 3)
    all_suggestions.extend(s)

    score, s = _score_domain_specific(artifact, artifact_type)
    dimensions["domain_specific"] = round(score, 3)
    all_suggestions.extend(s)

    overall = sum(dimensions[d] * weights[d] for d in dimensions)
    overall = round(overall, 3)

    if overall >= pass_threshold:
        verdict, loop_action = "PASS", "done"
    elif overall >= revise_threshold:
        verdict, loop_action = "REVISE", "continue"
    else:
        verdict, loop_action = "FAIL", "escalate"

    return {
        "ok": True,
        "score": overall,
        "verdict": verdict,
        "loop_action": loop_action,
        "dimensions": dimensions,
        "suggestions": all_suggestions,
        "weights_applied": {k: round(v, 3) for k, v in weights.items()},
        "thresholds": {"pass": pass_threshold, "revise": revise_threshold},
        "artifact_type": artifact_type,
    }
