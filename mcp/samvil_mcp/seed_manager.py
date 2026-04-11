"""Seed version management and comparison for SAMVIL evolve loop.

Compares seed versions to detect convergence:
  - similarity = 1.0 means identical seeds
  - similarity ≥ 0.95 = converged (stop evolving)

Also provides JSON Schema validation for inter-stage contracts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


# ── Schema Validation ──────────────────────────────────────────────

SCHEMAS_DIR = Path(__file__).parent.parent.parent / "references"


def _load_schema(schema_name: str) -> dict:
    """Load a JSON Schema from references/ directory."""
    schema_path = SCHEMAS_DIR / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path) as f:
        return json.load(f)


def validate_seed(seed: dict) -> dict:
    """Validate a seed against seed-schema.json.

    Returns dict with 'valid' bool and 'errors' list.
    Uses jsonschema if available, falls back to manual checks.
    """
    errors = []

    # Required fields
    required = ["name", "description", "tech_stack", "core_experience",
                "features", "acceptance_criteria", "constraints",
                "out_of_scope", "version"]
    for field in required:
        if field not in seed:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    # Name validation
    import re
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", seed.get("name", "")):
        errors.append("name must be kebab-case (lowercase, hyphens, no spaces)")

    # tech_stack.framework
    if seed.get("tech_stack", {}).get("framework") not in ("nextjs", "vite-react", "astro"):
        errors.append("tech_stack.framework must be nextjs, vite-react, or astro")

    # features
    features = seed.get("features", [])
    if not features:
        errors.append("features must have at least 1 item")
    for i, feat in enumerate(features):
        if not feat.get("name"):
            errors.append(f"features[{i}].name is required")
        if feat.get("priority", 0) < 1:
            errors.append(f"features[{i}].priority must be >= 1")

    # acceptance_criteria
    ac = seed.get("acceptance_criteria", [])
    if not ac:
        errors.append("acceptance_criteria must have at least 1 item")

    # core_experience
    ce = seed.get("core_experience", {})
    if not ce.get("primary_screen") or not re.match(r"^[A-Z]", ce.get("primary_screen", "")):
        errors.append("core_experience.primary_screen must be PascalCase")
    if not ce.get("key_interactions"):
        errors.append("core_experience.key_interactions must have at least 1 item")

    # constraints and out_of_scope
    if not seed.get("constraints"):
        errors.append("constraints is empty — may indicate missing requirements")
    if not seed.get("out_of_scope"):
        errors.append("out_of_scope is empty — scope creep risk")

    # depends_on reference check
    feature_names = {f["name"] for f in features if "name" in f}
    for feat in features:
        if not feat.get("independent", True) and feat.get("depends_on"):
            if feat["depends_on"] not in feature_names:
                errors.append(f"features[{feat['name']}].depends_on references non-existent feature: {feat['depends_on']}")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_state(state: dict) -> dict:
    """Validate a state dict against state-schema.json."""
    errors = []

    if "seed_version" not in state:
        errors.append("Missing required field: seed_version")
    if "current_stage" not in state:
        errors.append("Missing required field: current_stage")
    elif state["current_stage"] not in ("interview", "seed", "scaffold", "build", "qa", "retro", "evolve", "complete"):
        errors.append(f"Invalid current_stage: {state['current_stage']}")

    return {"valid": len(errors) == 0, "errors": errors}


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
