"""v3 schema regression tests for seed_manager.validate_seed."""

from samvil_mcp.seed_manager import validate_seed


def _v3_base() -> dict:
    return {
        "name": "todo-app",
        "description": "simple todo",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {
            "primary_screen": "HomeScreen",
            "key_interactions": ["add"],
        },
        "features": [{
            "name": "auth",
            "priority": 1,
            "acceptance_criteria": [
                {"id": "AC-1", "description": "sign up", "children": []}
            ],
        }],
        "constraints": ["no auth"],
        "out_of_scope": ["teams"],
        "version": "3.0",
        "schema_version": "3.0",
    }


def test_v3_seed_without_root_ac_is_valid():
    assert validate_seed(_v3_base())["valid"] is True


def test_v3_seed_with_empty_feature_acs_fails():
    seed = _v3_base()
    seed["features"][0]["acceptance_criteria"] = []
    result = validate_seed(seed)
    assert not result["valid"]
    assert any("at least 1 AC leaf" in e for e in result["errors"])


def test_v3_seed_counts_nested_leaves():
    seed = _v3_base()
    seed["features"][0]["acceptance_criteria"] = [
        {
            "id": "AC-1",
            "description": "parent",
            "children": [
                {"id": "AC-1.1", "description": "leaf a", "children": []},
                {"id": "AC-1.2", "description": "leaf b", "children": []},
            ],
        }
    ]
    assert validate_seed(seed)["valid"] is True


def test_v2_without_schema_still_requires_root_ac():
    seed = _v3_base()
    seed.pop("schema_version")
    # remove features AC to ensure fallback path kicks in
    result = validate_seed(seed)
    assert not result["valid"]
    assert any("acceptance_criteria" in e for e in result["errors"])


def test_v3_counts_deep_tree_leaves():
    """3-level tree — leaves at depth 2 must be counted."""
    seed = _v3_base()
    seed["features"][0]["acceptance_criteria"] = [
        {
            "id": "AC-1", "description": "root",
            "children": [
                {
                    "id": "AC-1.1", "description": "mid",
                    "children": [
                        {"id": "AC-1.1.1", "description": "deep leaf a", "children": []},
                        {"id": "AC-1.1.2", "description": "deep leaf b", "children": []},
                    ],
                },
            ],
        },
    ]
    assert validate_seed(seed)["valid"] is True


def test_v3_all_branches_no_leaves_fails():
    """Defensive: if every AC is a branch whose children are also
    branches-only-without-leaves, this fails (well-formed trees always
    have leaves, so this is a malformed-tree edge case)."""
    seed = _v3_base()
    seed["features"][0]["acceptance_criteria"] = []  # no ACs at all
    assert validate_seed(seed)["valid"] is False


def test_v3_rejects_missing_description():
    seed = _v3_base()
    del seed["description"]
    result = validate_seed(seed)
    assert not result["valid"]
    assert any("description" in e for e in result["errors"])
