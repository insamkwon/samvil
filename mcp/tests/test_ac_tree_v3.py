"""Tests for v3.0.0 T1.1 AC tree traversal helpers."""

from samvil_mcp.ac_tree import (
    ACNode,
    all_done,
    is_branch_complete,
    leaves,
    load_ac_from_schema,
    next_buildable_leaves,
    tree_progress,
)


def _sample_tree() -> ACNode:
    """AC-1 with two leaf children AC-1.1, AC-1.2."""
    return load_ac_from_schema({
        "id": "AC-1",
        "description": "auth",
        "children": [
            {"id": "AC-1.1", "description": "sign up"},
            {"id": "AC-1.2", "description": "log in"},
        ],
    })


def test_next_buildable_leaves_simple():
    tree = _sample_tree()
    batch = next_buildable_leaves(tree, completed=set(), max_parallel=2)
    assert len(batch) == 2
    assert {l.id for l in batch} == {"AC-1.1", "AC-1.2"}


def test_next_buildable_leaves_respects_max_parallel():
    tree = load_ac_from_schema({
        "id": "AC-1",
        "description": "root",
        "children": [
            {"id": f"AC-1.{i}", "description": f"leaf {i}"} for i in range(1, 6)
        ],
    })
    batch = next_buildable_leaves(tree, completed=set(), max_parallel=2)
    assert len(batch) == 2


def test_next_buildable_leaves_skips_completed_ids():
    tree = _sample_tree()
    batch = next_buildable_leaves(tree, completed={"AC-1.1"}, max_parallel=2)
    assert [l.id for l in batch] == ["AC-1.2"]


def test_next_buildable_leaves_skips_terminal_status():
    tree = _sample_tree()
    # mark first leaf as already passed
    tree.children[0].status = "pass"
    tree.children[1].status = "skipped"
    batch = next_buildable_leaves(tree, completed=set(), max_parallel=2)
    assert batch == []


def test_next_buildable_leaves_skips_blocked_parent():
    tree = load_ac_from_schema({
        "id": "AC-1",
        "description": "parent",
        "status": "blocked",
        "children": [
            {"id": "AC-1.1", "description": "child 1"},
            {"id": "AC-1.2", "description": "child 2"},
        ],
    })
    # parent is blocked → children should not be buildable
    batch = next_buildable_leaves(tree, completed=set(), max_parallel=2)
    assert batch == []


def test_is_branch_complete_all_pass():
    tree = _sample_tree()
    for leaf in leaves(tree):
        leaf.status = "pass"
    assert is_branch_complete(tree) is True


def test_is_branch_complete_partial_fail_not_complete():
    tree = _sample_tree()
    tree.children[0].status = "pass"
    tree.children[1].status = "fail"
    # fail is terminal for all_done but not a "completion" for branch
    assert is_branch_complete(tree) is False


def test_is_branch_complete_skipped_counts():
    tree = _sample_tree()
    tree.children[0].status = "pass"
    tree.children[1].status = "skipped"
    assert is_branch_complete(tree) is True


def test_all_done_terminal_states():
    tree = _sample_tree()
    tree.children[0].status = "pass"
    tree.children[1].status = "fail"
    assert all_done(tree) is True


def test_all_done_with_pending_false():
    tree = _sample_tree()
    tree.children[0].status = "pass"
    tree.children[1].status = "pending"
    assert all_done(tree) is False


def test_tree_progress_empty_pending():
    tree = _sample_tree()
    stats = tree_progress(tree)
    assert stats["total_leaves"] == 2
    assert stats["completed"] == 0
    assert stats["passed"] == 0
    assert stats["failed"] == 0
    assert stats["pending"] == 2
    assert stats["progress_pct"] == 0


def test_tree_progress_mixed():
    tree = _sample_tree()
    tree.children[0].status = "pass"
    tree.children[1].status = "fail"
    stats = tree_progress(tree)
    assert stats["total_leaves"] == 2
    assert stats["completed"] == 2
    assert stats["passed"] == 1
    assert stats["failed"] == 1
    assert stats["pending"] == 0
    assert stats["progress_pct"] == 100.0


def test_tree_progress_single_leaf_only_counts_leaf():
    # Root is itself a leaf when no children
    tree = load_ac_from_schema({"id": "AC-1", "description": "solo"})
    stats = tree_progress(tree)
    assert stats["total_leaves"] == 1
    assert stats["pending"] == 1


def test_tree_progress_branch_not_counted_as_leaf():
    tree = _sample_tree()
    # status on branch shouldn't be counted
    tree.status = "pass"
    stats = tree_progress(tree)
    assert stats["total_leaves"] == 2
    assert stats["passed"] == 0


def test_next_buildable_leaves_deep_tree():
    tree = load_ac_from_schema({
        "id": "AC-1",
        "description": "root",
        "children": [
            {
                "id": "AC-1.1",
                "description": "group 1",
                "children": [
                    {"id": "AC-1.1.1", "description": "leaf a"},
                    {"id": "AC-1.1.2", "description": "leaf b"},
                ],
            },
            {"id": "AC-1.2", "description": "leaf c"},
        ],
    })
    batch = next_buildable_leaves(tree, completed=set(), max_parallel=3)
    ids = {l.id for l in batch}
    assert ids == {"AC-1.1.1", "AC-1.1.2", "AC-1.2"}
