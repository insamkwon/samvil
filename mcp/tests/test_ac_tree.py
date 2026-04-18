"""Tests for ac_tree.py (v2.5.0, Phase 6)."""

import pytest

from samvil_mcp.ac_tree import (
    ACNode,
    load_ac_from_schema,
    aggregate_status,
    walk,
    leaves,
    count_nodes,
    render_tree_ascii,
    simple_decompose_suggestion,
    MAX_DEPTH,
)


def test_load_flat_string_as_leaf():
    node = load_ac_from_schema("User can sign up")
    assert node.description == "User can sign up"
    assert node.is_leaf
    assert node.children == []


def test_load_dict_ac():
    data = {
        "id": "AC-1",
        "description": "parent",
        "children": [
            {"id": "AC-1.1", "description": "child 1"},
            {"id": "AC-1.2", "description": "child 2"},
        ],
    }
    node = load_ac_from_schema(data)
    assert node.id == "AC-1"
    assert len(node.children) == 2
    assert node.children[0].id == "AC-1.1"


def test_is_leaf_is_branch():
    leaf = ACNode(id="x", description="leaf")
    assert leaf.is_leaf
    assert not leaf.is_branch

    branch = ACNode(id="y", description="branch", children=[ACNode(id="y.1", description="c")])
    assert not branch.is_leaf
    assert branch.is_branch


def test_aggregate_status_all_pass():
    leaf1 = ACNode(id="1.1", description="a", status="pass")
    leaf2 = ACNode(id="1.2", description="b", status="pass")
    branch = ACNode(id="1", description="x", children=[leaf1, leaf2])
    assert aggregate_status(branch) == "pass"


def test_aggregate_status_any_fail():
    leaf1 = ACNode(id="1.1", description="a", status="pass")
    leaf2 = ACNode(id="1.2", description="b", status="fail")
    branch = ACNode(id="1", description="x", children=[leaf1, leaf2])
    assert aggregate_status(branch) == "fail"


def test_aggregate_status_in_progress():
    leaf1 = ACNode(id="1.1", description="a", status="in_progress")
    leaf2 = ACNode(id="1.2", description="b", status="pending")
    branch = ACNode(id="1", description="x", children=[leaf1, leaf2])
    assert aggregate_status(branch) == "in_progress"


def test_walk_preorder():
    root = ACNode(id="1", description="r", children=[
        ACNode(id="1.1", description="a", children=[
            ACNode(id="1.1.1", description="aa"),
        ]),
        ACNode(id="1.2", description="b"),
    ])
    ids = [n.id for n in walk(root)]
    assert ids == ["1", "1.1", "1.1.1", "1.2"]


def test_leaves_only():
    root = ACNode(id="1", description="r", children=[
        ACNode(id="1.1", description="a", children=[
            ACNode(id="1.1.1", description="aa"),
        ]),
        ACNode(id="1.2", description="b"),
    ])
    leaf_ids = [n.id for n in leaves(root)]
    assert leaf_ids == ["1.1.1", "1.2"]


def test_count_nodes():
    root = ACNode(id="1", description="r", children=[
        ACNode(id="1.1", description="a", children=[
            ACNode(id="1.1.1", description="aa"),
        ]),
        ACNode(id="1.2", description="b"),
    ])
    counts = count_nodes(root)
    assert counts["total"] == 4
    assert counts["leaves"] == 2
    assert counts["branches"] == 2


def test_render_tree_ascii():
    root = ACNode(id="1", description="root", status="pending")
    root.children = [
        ACNode(id="1.1", description="child", status="pass"),
    ]
    output = render_tree_ascii(root)
    assert "root" in output
    assert "child" in output
    assert "✓" in output


def test_simple_decompose_and_keyword():
    suggestions = simple_decompose_suggestion("Validate email and hash password")
    assert len(suggestions) == 2
    assert "Validate email" in suggestions
    assert "hash password" in suggestions


def test_simple_decompose_comma_sep():
    suggestions = simple_decompose_suggestion("Create task, edit task, delete task")
    assert len(suggestions) == 3


def test_simple_decompose_no_suggestion():
    suggestions = simple_decompose_suggestion("User signs up")
    assert suggestions == []  # Needs LLM


def test_depth_calculation():
    root = load_ac_from_schema({
        "id": "1",
        "description": "r",
        "children": [
            {"id": "1.1", "description": "a", "children": [
                {"id": "1.1.1", "description": "aa"},
            ]},
        ],
    })
    # depth 0, 1, 2
    assert root.depth == 0
    assert root.children[0].depth == 1
    assert root.children[0].children[0].depth == 2
