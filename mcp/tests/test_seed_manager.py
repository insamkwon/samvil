"""Tests for seed_manager: schema validation and comparison."""

import pytest
from samvil_mcp.seed_manager import validate_seed, validate_state, compare_seeds, check_convergence


# ── validate_seed ──────────────────────────────────────────────


def test_valid_seed():
    seed = {
        "name": "my-app",
        "description": "A simple task management application",
        "solution_type": "web-app",
        "mode": "web",
        "tech_stack": {"framework": "nextjs", "ui": "tailwind"},
        "core_experience": {
            "description": "User creates and completes a task within 30 seconds",
            "primary_screen": "TaskList",
            "key_interactions": ["create-task", "complete-task"],
        },
        "features": [
            {"name": "task-crud", "priority": 1, "independent": True, "depends_on": None},
        ],
        "acceptance_criteria": ["User can create a task and see it in the list"],
        "constraints": ["Must work offline"],
        "out_of_scope": ["User authentication"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is True
    assert result["errors"] == []


def test_missing_required_fields():
    seed = {"name": "my-app"}
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("description" in e for e in result["errors"])


def test_invalid_name_format():
    seed = {
        "name": "My App!",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [{"name": "feat1", "priority": 1}],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("kebab-case" in e for e in result["errors"])


def test_invalid_framework():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "django"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [{"name": "feat1", "priority": 1}],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("framework" in e for e in result["errors"])


def test_empty_features():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("features" in e for e in result["errors"])


def test_depends_on_nonexistent_feature():
    seed = {
        "name": "my-app",
        "description": "x" * 20,
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "x" * 20,
            "primary_screen": "Home",
            "key_interactions": ["do-thing"],
        },
        "features": [
            {"name": "feat1", "priority": 1, "independent": False, "depends_on": "nonexistent"},
        ],
        "acceptance_criteria": ["Must work"],
        "constraints": ["None"],
        "out_of_scope": ["Nothing"],
        "version": 1,
    }
    result = validate_seed(seed)
    assert result["valid"] is False
    assert any("non-existent" in e for e in result["errors"])


def test_v3_3_seed_accepts_verify_contract() -> None:
    seed = {
        "schema_version": "3.3",
        "name": "my-app",
        "description": "A mechanically verifiable task application",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "User creates a task and sees it immediately",
            "primary_screen": "TaskList",
            "key_interactions": ["create-task"],
        },
        "features": [{
            "name": "task-list",
            "priority": 1,
            "acceptance_criteria": [{
                "id": "F1.AC1",
                "description": "task appears after creation",
                "verify": {
                    "command": "npx playwright test tests/e2e/task-list.spec.ts",
                    "artifacts": ["playwright-report/index.html"],
                    "assertion": "1 passed",
                },
            }],
        }],
        "constraints": ["Must work offline"],
        "out_of_scope": ["Authentication"],
        "version": 1,
    }

    assert validate_seed(seed) == {"valid": True, "errors": []}

    import jsonschema
    from samvil_mcp.seed_manager import _load_schema

    jsonschema.validate(seed, _load_schema("seed-schema.json"))


def test_verify_contract_rejects_unknown_fields() -> None:
    seed = {
        "schema_version": "3.3",
        "name": "my-app",
        "description": "A mechanically verifiable task application",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "User creates a task and sees it immediately",
            "primary_screen": "TaskList",
            "key_interactions": ["create-task"],
        },
        "features": [{
            "name": "task-list",
            "priority": 1,
            "acceptance_criteria": [{
                "id": "F1.AC1",
                "description": "task appears after creation",
                "verify": {"magic_pass": True},
            }],
        }],
        "constraints": ["Must work offline"],
        "out_of_scope": ["Authentication"],
        "version": 1,
    }

    result = validate_seed(seed)

    assert result["valid"] is False
    assert any("verify" in error for error in result["errors"])


# ── validate_state ──────────────────────────────────────────────


def test_valid_state():
    state = {"seed_version": 1, "current_stage": "build"}
    result = validate_state(state)
    assert result["valid"] is True


def test_missing_stage():
    state = {"seed_version": 1}
    result = validate_state(state)
    assert result["valid"] is False


def test_invalid_stage():
    state = {"seed_version": 1, "current_stage": "unknown"}
    result = validate_state(state)
    assert result["valid"] is False


# ── compare_seeds (existing, sanity check) ──────────────────────


def test_identical_seeds():
    seed = {"name": "a", "version": 1}
    result = compare_seeds(seed, seed)
    assert result["similarity"] == 1.0
    assert result["converged"] is True


# ── merge_brownfield_seed (v2.6.0) ─────────────────────────────

from samvil_mcp.seed_manager import merge_brownfield_seed


def _existing_brownfield_seed():
    return {
        "name": "todo-app",
        "description": "A basic todo app",
        "solution_type": "web-app",
        "schema_version": "3.0",
        "version": 1,
        "tech_stack": {"framework": "nextjs", "ui": "tailwind"},
        "core_experience": {"description": "Manage tasks"},
        "target_user": "Users",
        "core_problem": "Need to track tasks",
        "features": [
            {"name": "task-create", "description": "Create tasks", "status": "existing",
             "acceptance_criteria": []},
            {"name": "task-list", "description": "List tasks", "status": "existing",
             "acceptance_criteria": []},
        ],
        "constraints": ["localStorage only"],
        "out_of_scope": [],
        "acceptance_criteria": [],
    }


def _interview_state():
    return {
        "target_user": "Freelance developers managing 5+ client projects simultaneously",
        "core_problem": "They lose track of deadlines and project context when switching clients",
        "core_experience": "Dashboard showing all projects with upcoming deadlines",
        "features": ["deadline-alerts", "project-grouping"],
        "exclusions": ["real-time collaboration", "file attachments", "invoicing"],
        "constraints": ["Mobile responsive", "No PII stored"],
        "acceptance_criteria": [
            "User sees all deadlines on one screen within 1 second",
            "Overdue tasks show red indicator",
        ],
    }


def test_merge_preserves_existing_features():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    names = [f["name"] for f in merged["features"]]
    assert "task-create" in names
    assert "task-list" in names


def test_merge_adds_new_features():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    names = [f["name"] for f in merged["features"]]
    assert "deadline-alerts" in names
    assert "project-grouping" in names


def test_merge_existing_features_keep_status():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    existing = [f for f in merged["features"] if f["name"] in ("task-create", "task-list")]
    for f in existing:
        assert f["status"] == "existing"


def test_merge_new_features_have_new_status():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    new_feats = [f for f in merged["features"] if f["name"] in ("deadline-alerts", "project-grouping")]
    for f in new_feats:
        assert f["status"] == "new"


def test_merge_no_duplicate_features():
    """If a feature from interview already exists, it should not be duplicated."""
    existing = _existing_brownfield_seed()
    iv = _interview_state()
    iv["features"] = ["task-create", "deadline-alerts"]  # task-create already exists
    merged = merge_brownfield_seed(existing, iv)
    names = [f["name"] for f in merged["features"]]
    assert names.count("task-create") == 1


def test_merge_updates_metadata_when_interview_more_specific():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "Freelance developers" in merged["target_user"]
    assert "deadlines" in merged["core_problem"]


def test_merge_keeps_existing_tech_stack():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert merged["tech_stack"]["framework"] == "nextjs"


def test_merge_unions_constraints():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "localStorage only" in merged["constraints"]
    assert "Mobile responsive" in merged["constraints"]


def test_merge_uses_interview_exclusions():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert "real-time collaboration" in merged["out_of_scope"]


def test_merge_sets_analysis_source():
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state())
    assert merged["_analysis_source"] == "brownfield"


def test_merge_explicit_new_features_override_interview():
    explicit = [{"name": "gantt-chart", "description": "Gantt chart view"}]
    merged = merge_brownfield_seed(_existing_brownfield_seed(), _interview_state(),
                                   new_features=explicit)
    names = [f["name"] for f in merged["features"]]
    assert "gantt-chart" in names
    # interview features should NOT be added when explicit list given
    assert "deadline-alerts" not in names


# ── v4.23 evaluation_principles + exit_conditions ─────────────────


def _v423_seed_base():
    return {
        "name": "my-app",
        "description": "A simple task management application",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "description": "User creates and completes a task within 30 seconds",
            "primary_screen": "TaskList",
            "key_interactions": ["create-task"],
        },
        "features": [{"name": "task-crud", "priority": 1, "independent": True}],
        "acceptance_criteria": ["User can create a task"],
        "constraints": ["Must work offline"],
        "out_of_scope": ["User authentication"],
        "version": 1,
    }


def test_seed_with_evaluation_principles_valid():
    """v4.23 schema addition: evaluation_principles optional but must be well-formed when present."""
    seed = _v423_seed_base()
    seed["evaluation_principles"] = [
        {"principle": "응답은 1초 이내", "weight": 0.7, "rationale": "사용자가 빠른 응답을 명시", "source_phase": "scope"},
        {"principle": "오프라인 우선", "weight": 0.5},
    ]
    result = validate_seed(seed)
    assert result["valid"] is True, f"errors: {result.get('errors')}"


def test_seed_with_exit_conditions_valid():
    """v4.23 schema addition: exit_conditions optional list of strings."""
    seed = _v423_seed_base()
    seed["exit_conditions"] = [
        "모든 features의 acceptance_criteria가 PASS이고 evaluation_principles 중 weight ≥ 0.5인 항목이 모두 PASS",
    ]
    result = validate_seed(seed)
    assert result["valid"] is True, f"errors: {result.get('errors')}"


def test_seed_with_both_v423_fields_valid():
    seed = _v423_seed_base()
    seed["evaluation_principles"] = [{"principle": "응답 1초"}]
    seed["exit_conditions"] = ["features 모두 PASS"]
    result = validate_seed(seed)
    assert result["valid"] is True


def test_seed_without_v423_fields_still_valid():
    """Backward compat — pre-v4.23 seeds without these fields remain valid."""
    seed = _v423_seed_base()
    assert "evaluation_principles" not in seed
    assert "exit_conditions" not in seed
    result = validate_seed(seed)
    assert result["valid"] is True


def test_v423_fields_documented_in_schema_json():
    """Schema-side fields exist in seed-schema.json (canonical spec).

    Note: validate_seed uses *manual* checks not jsonschema, so it
    does not enforce evaluation_principles internal structure. The
    schema file is the spec for jsonschema-using consumers (and for
    documentation). validate_seed treats the v4.23 fields as opaque —
    presence/absence doesn't affect validation result.
    """
    import json
    from pathlib import Path
    schema_path = Path(__file__).resolve().parents[2] / "references" / "seed-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "evaluation_principles" in schema["properties"]
    assert "exit_conditions" in schema["properties"]
    ep_item = schema["properties"]["evaluation_principles"]["items"]
    assert ep_item["properties"]["weight"]["maximum"] == 1.0
    assert "principle" in ep_item["required"]


def test_v423_fields_dont_break_validate_seed_with_garbage():
    """Even malformed evaluation_principles don't break validate_seed —
    it's manual and ignores fields it doesn't know.

    This documents current behavior; switching to jsonschema-based
    validation would change this. The previous test
    (test_v423_fields_documented_in_schema_json) ensures the schema
    file itself enforces constraints for downstream consumers.
    """
    seed = _v423_seed_base()
    seed["evaluation_principles"] = [{"weight": 99, "garbage": "x"}]
    result = validate_seed(seed)
    assert result["valid"] is True  # validate_seed is lenient by design
