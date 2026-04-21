"""v3-011: AC leaf split heuristics for evolve cycle.

Suggests when a complex AC leaf should be decomposed into children, based on
structural signals (compound verbs, multi-clause sentences, length). The
actual LLM-driven split is performed by the evolve skill; this module
provides the rule-based detector so tests can pin behavior.

This is a lightweight heuristic — not a replacement for the evolve skill's
LLM step. It's the trigger layer: "should this leaf be considered for split?"
"""
from __future__ import annotations

import re
from typing import Any

# Structural signals
_COMPOUND_CONNECTORS = (" and ", " 그리고 ", " 또는 ", "하고 ", " or ", ", ")
# chars. Below this, split adds noise. 40 is the empirical cutoff found during
# dogfood — shorter leaves are already precise enough that splitting them
# creates more review overhead than it saves.
_MIN_SPLIT_LENGTH = 40
_MAX_COMMAS = 3


def should_split(description: str) -> dict[str, Any]:
    """Return a verdict on whether this leaf description is a good split candidate.

    Output:
        {
          "should_split": bool,
          "reasons": list[str],
          "suggested_children": list[str] | None,  # heuristic split
        }
    """
    reasons: list[str] = []

    length = len(description)
    if length < _MIN_SPLIT_LENGTH:
        return {"should_split": False, "reasons": ["too_short"], "suggested_children": None}

    # Compound connectors
    connector_hits = [c.strip() for c in _COMPOUND_CONNECTORS if c in description.lower()]
    if connector_hits:
        reasons.append(f"compound_connectors:{connector_hits}")

    # Multi-comma
    comma_count = description.count(",")
    if comma_count >= _MAX_COMMAS:
        reasons.append(f"many_commas:{comma_count}")

    # Multiple verbs in the same sentence (rough English + Korean detection)
    verb_markers = [
        r"\buser can\s+\w+",
        r"\b(create|edit|delete|update|add|remove|load|save|sync)\b",
        r"(생성|편집|삭제|수정|추가|제거|동기화|저장)하고",
    ]
    verb_hits = sum(
        1 for pattern in verb_markers if re.search(pattern, description, re.IGNORECASE)
    )
    if verb_hits >= 2:
        reasons.append(f"multi_verb:{verb_hits}")

    should = len(reasons) > 0

    suggested_children = None
    if should:
        # Naive split on connectors (LLM will produce better output in evolve)
        for c in _COMPOUND_CONNECTORS:
            if c in description.lower():
                parts = [p.strip() for p in _split_case_insensitive(description, c) if p.strip()]
                if len(parts) >= 2:
                    suggested_children = parts
                    break

    return {
        "should_split": should,
        "reasons": reasons,
        "suggested_children": suggested_children,
    }


def _split_case_insensitive(text: str, sep: str) -> list[str]:
    """Split text on separator, case-insensitive."""
    pattern = re.compile(re.escape(sep), re.IGNORECASE)
    return pattern.split(text)
