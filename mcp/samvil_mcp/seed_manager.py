"""Seed version management and comparison for SAMVIL evolve loop.

Compares seed versions to detect convergence:
  - similarity = 1.0 means identical seeds
  - similarity ≥ 0.95 = converged (stop evolving)
"""

from __future__ import annotations

import json


def compare_seeds(seed_a: dict, seed_b: dict) -> dict:
    """Compare two seed versions and return similarity metrics.

    Returns:
        Dict with overall similarity (0.0-1.0) and per-field changes.
    """
    fields = [
        "name", "description", "mode", "tech_stack",
        "core_experience", "features", "acceptance_criteria",
        "constraints", "out_of_scope",
    ]

    matches = 0
    total = 0
    changes = []

    for field in fields:
        a_val = seed_a.get(field)
        b_val = seed_b.get(field)
        total += 1

        if a_val == b_val:
            matches += 1
        else:
            if isinstance(a_val, list) and isinstance(b_val, list):
                # For lists, compute Jaccard similarity
                set_a = {json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x) for x in a_val}
                set_b = {json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x) for x in b_val}
                if set_a | set_b:
                    jaccard = len(set_a & set_b) / len(set_a | set_b)
                    matches += jaccard
                    if jaccard < 1.0:
                        added = set_b - set_a
                        removed = set_a - set_b
                        changes.append({
                            "field": field,
                            "similarity": round(jaccard, 3),
                            "added": list(added)[:5],
                            "removed": list(removed)[:5],
                        })
                else:
                    matches += 1  # Both empty
            elif isinstance(a_val, dict) and isinstance(b_val, dict):
                # For dicts, compare keys
                all_keys = set(a_val.keys()) | set(b_val.keys())
                if all_keys:
                    matching_keys = sum(1 for k in all_keys if a_val.get(k) == b_val.get(k))
                    dict_sim = matching_keys / len(all_keys)
                    matches += dict_sim
                    if dict_sim < 1.0:
                        changes.append({
                            "field": field,
                            "similarity": round(dict_sim, 3),
                        })
                else:
                    matches += 1
            else:
                changes.append({
                    "field": field,
                    "old": str(a_val)[:100],
                    "new": str(b_val)[:100],
                })

    similarity = matches / total if total > 0 else 1.0

    return {
        "similarity": round(similarity, 3),
        "converged": similarity >= 0.95,
        "convergence_threshold": 0.95,
        "changes": changes,
        "fields_compared": total,
        "fields_matching": round(matches, 1),
    }


def check_convergence(seed_history: list[dict]) -> dict:
    """Check if the seed evolution has converged.

    Args:
        seed_history: List of seed dicts ordered by version.

    Returns:
        Convergence status with trend analysis.
    """
    if len(seed_history) < 2:
        return {
            "converged": False,
            "reason": "Need at least 2 versions to check convergence",
            "generations": len(seed_history),
        }

    # Compare last two versions
    last = seed_history[-1]
    prev = seed_history[-2]
    comparison = compare_seeds(prev, last)

    # Check trend (are changes getting smaller?)
    trend = "unknown"
    if len(seed_history) >= 3:
        prev_prev = seed_history[-3]
        older_comparison = compare_seeds(prev_prev, prev)
        if comparison["similarity"] > older_comparison["similarity"]:
            trend = "converging"
        elif comparison["similarity"] < older_comparison["similarity"]:
            trend = "diverging"
        else:
            trend = "stable"

    return {
        "converged": comparison["converged"],
        "similarity": comparison["similarity"],
        "trend": trend,
        "generations": len(seed_history),
        "max_generations": 30,
        "changes_in_last": comparison["changes"],
    }
