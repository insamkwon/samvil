"""Evolve loop engine for SAMVIL — seed improvement through evaluation feedback.

Pipeline:
  1. Wonder: "What was lacking?" (analyze QA results)
  2. Reflect: "How to improve?" (propose seed changes)
  3. New seed version with improvements
  4. Check convergence → stop or continue
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .seed_manager import check_convergence, compare_seeds


def generate_evolve_context(
    current_seed: dict,
    qa_result: dict,
    seed_history: list[dict] | None = None,
) -> dict:
    """Generate context for wonder/reflect agents.

    Args:
        current_seed: Current seed JSON
        qa_result: QA report with verdicts per AC
        seed_history: Previous seed versions for convergence context

    Returns:
        Context dict for agent prompts.
    """
    context = {
        "current_seed": current_seed,
        "qa_result": qa_result,
        "version": current_seed.get("version", 1),
    }

    if seed_history and len(seed_history) >= 2:
        convergence = check_convergence(seed_history)
        context["convergence"] = convergence
        context["previous_changes"] = compare_seeds(
            seed_history[-2], seed_history[-1]
        )["changes"]

    return context


def validate_evolved_seed(original: dict, evolved: dict) -> dict:
    """Validate that an evolved seed is a valid improvement.

    Rules:
    - Must keep same name and mode
    - Must not add more than 2 new features per evolution
    - Must not remove core_experience
    - Version must increment by 1

    Returns:
        Validation result with issues list.
    """
    issues = []

    # Name and mode must be preserved
    if evolved.get("name") != original.get("name"):
        issues.append("name changed — must be preserved")
    if evolved.get("mode") != original.get("mode"):
        issues.append("mode changed — must be preserved")

    # Core experience must exist
    if not evolved.get("core_experience"):
        issues.append("core_experience removed — must be preserved")

    # Version must increment
    orig_version = original.get("version", 1)
    new_version = evolved.get("version", 1)
    if new_version != orig_version + 1:
        issues.append(f"version should be {orig_version + 1}, got {new_version}")

    # Feature count check (max 2 new features per evolution)
    orig_features = {f["name"] if isinstance(f, dict) else f for f in original.get("features", [])}
    new_features = {f["name"] if isinstance(f, dict) else f for f in evolved.get("features", [])}
    added = new_features - orig_features
    if len(added) > 2:
        issues.append(f"Too many new features ({len(added)}). Max 2 per evolution.")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "features_added": list(added),
        "features_removed": list(orig_features - new_features),
    }
