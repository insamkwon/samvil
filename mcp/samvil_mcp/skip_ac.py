"""Skip Externally Satisfied ACs (v2.6.0, #08).

When samvil-analyze detects existing features that match ACs in the seed,
mark those ACs as externally_satisfied so the build can skip them.

Flow:
  1. samvil-analyze → .samvil/analysis.json (existing_features[])
  2. skip_ac.load_analysis() → list[ExternalSatisfaction]
  3. skip_ac.match_ac_to_existing() → fuzzy keyword match
  4. skip_ac.mark_seed_with_external() → annotate seed ACs
  5. samvil-build → skip ACs with external_satisfied=true
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ExternalSatisfaction:
    ac_description: str
    evidence: str
    commit: str = ""
    reason: str = "Existing implementation"
    detected_at: str = ""


def load_analysis(project_path: str) -> list[ExternalSatisfaction]:
    """Load .samvil/analysis.json from samvil-analyze."""
    p = Path(project_path) / ".samvil" / "analysis.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [
        ExternalSatisfaction(
            ac_description=ef.get("ac_match", ""),
            evidence=ef.get("evidence", ""),
            commit=ef.get("commit", ""),
            reason=ef.get("reason", "Existing implementation"),
            detected_at=ef.get("detected_at", ""),
        )
        for ef in data.get("existing_features", [])
    ]


def match_ac_to_existing(
    ac_description: str,
    existing: list[ExternalSatisfaction],
    similarity_threshold: float = 0.5,
) -> ExternalSatisfaction | None:
    """Fuzzy match AC to existing feature via keyword overlap (Jaccard)."""
    ac_words = set(ac_description.lower().split())
    if not ac_words:
        return None
    best_match = None
    best_score = 0.0
    for ex in existing:
        ex_words = set(ex.ac_description.lower().split())
        if not ex_words:
            continue
        overlap = len(ac_words & ex_words) / len(ac_words | ex_words)
        if overlap > best_score and overlap >= similarity_threshold:
            best_score = overlap
            best_match = ex
    return best_match


def mark_seed_with_external(seed: dict, project_path: str) -> dict:
    """Modify seed in-place to mark externally satisfied ACs."""
    existing = load_analysis(project_path)
    if not existing:
        return seed
    for feature in seed.get("features", []):
        for ac in feature.get("acceptance_criteria", []):
            if isinstance(ac, str):
                continue
            desc = ac.get("description") or ac.get("criterion", "")
            match = match_ac_to_existing(desc, existing)
            if match:
                ac["external_satisfied"] = True
                ac["external_evidence"] = match.evidence
                ac["external_reason"] = match.reason
                ac["external_detected_at"] = match.detected_at
    return seed
