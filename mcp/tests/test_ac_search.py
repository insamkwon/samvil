"""Tests for ac_search.py — BM25 AC tree search via SQLite FTS5."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from samvil_mcp.ac_search import (
    _flatten_leaves,
    index_ac_tree,
    search_ac_tree,
    search_ac_tree_by_feature,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _leaf(lid, desc, status="pending", children=None):
    return {"id": lid, "description": desc, "status": status, "children": children or []}


def _branch(lid, desc, children):
    return {"id": lid, "description": desc, "children": children}


def _feature(fid, fname, ac_tree):
    return {"id": fid, "name": fname, "acceptance_criteria": ac_tree}


# ── _flatten_leaves ─────────────────────────────────────────────────────────

def test_flatten_single_leaf():
    node = _leaf("l1", "User can log in")
    result = _flatten_leaves(node, "feat_auth", "Auth")
    assert len(result) == 1
    assert result[0]["leaf_id"] == "l1"
    assert result[0]["description"] == "User can log in"
    assert result[0]["feature_id"] == "feat_auth"
    assert result[0]["feature_name"] == "Auth"
    assert result[0]["status"] == "pending"


def test_flatten_nested_tree():
    tree = _branch("b1", "Login flow", [
        _leaf("l1", "Email field visible"),
        _leaf("l2", "Password field visible"),
        _branch("b2", "Submit", [
            _leaf("l3", "Success redirect"),
        ]),
    ])
    result = _flatten_leaves(tree, "auth", "Auth")
    assert len(result) == 3
    ids = {r["leaf_id"] for r in result}
    assert ids == {"l1", "l2", "l3"}


def test_flatten_branch_not_included():
    """Branch nodes (non-empty children) must not appear in leaf output."""
    tree = _branch("b1", "Branch desc", [_leaf("l1", "Leaf desc")])
    result = _flatten_leaves(tree, "f", "F")
    leaf_ids = {r["leaf_id"] for r in result}
    assert "b1" not in leaf_ids


def test_flatten_preserves_status():
    node = _leaf("l1", "desc", status="pass")
    result = _flatten_leaves(node, "f", "F")
    assert result[0]["status"] == "pass"


def test_flatten_missing_id_becomes_empty_string():
    node = {"description": "no id", "children": []}
    result = _flatten_leaves(node, "f", "F")
    assert result[0]["leaf_id"] == ""


# ── index_ac_tree ───────────────────────────────────────────────────────────

def test_index_creates_db(tmp_path):
    features = [_feature("f1", "Auth", _leaf("l1", "User can register"))]
    result = index_ac_tree(str(tmp_path), json.dumps(features))
    assert result["indexed"] == 1
    assert result["features"] == 1
    assert (tmp_path / ".samvil" / "ac-search.db").exists()


def test_index_multiple_features(tmp_path):
    features = [
        _feature("f1", "Auth", _branch("b1", "root", [
            _leaf("l1", "Login works"),
            _leaf("l2", "Logout works"),
        ])),
        _feature("f2", "Dashboard", _leaf("l3", "Charts visible")),
    ]
    result = index_ac_tree(str(tmp_path), json.dumps(features))
    assert result["indexed"] == 3
    assert result["features"] == 2


def test_index_clears_on_reindex(tmp_path):
    features = [_feature("f1", "F", _leaf("l1", "original leaf"))]
    index_ac_tree(str(tmp_path), json.dumps(features))
    features2 = [_feature("f2", "G", _leaf("l2", "new leaf"))]
    result = index_ac_tree(str(tmp_path), json.dumps(features2))
    assert result["indexed"] == 1
    rows = search_ac_tree(str(tmp_path), "original")
    assert len(rows) == 0


def test_index_invalid_json_returns_error(tmp_path):
    result = index_ac_tree(str(tmp_path), "not json")
    assert "error" in result
    assert result["indexed"] == 0


def test_index_non_list_returns_error(tmp_path):
    result = index_ac_tree(str(tmp_path), '{"key": "value"}')
    assert "error" in result


def test_index_feature_without_ac_skipped(tmp_path):
    features = [{"id": "f1", "name": "F"}]  # no acceptance_criteria
    result = index_ac_tree(str(tmp_path), json.dumps(features))
    assert result["indexed"] == 0


# ── search_ac_tree ──────────────────────────────────────────────────────────

def test_search_finds_relevant_leaf(tmp_path):
    features = [_feature("f1", "Auth", _leaf("l1", "User can login with email"))]
    index_ac_tree(str(tmp_path), json.dumps(features))
    results = search_ac_tree(str(tmp_path), "email")
    assert len(results) == 1
    assert results[0]["leaf_id"] == "l1"


def test_search_returns_empty_when_no_db(tmp_path):
    results = search_ac_tree(str(tmp_path), "anything")
    assert results == []


def test_search_returns_empty_on_empty_query(tmp_path):
    features = [_feature("f1", "F", _leaf("l1", "something"))]
    index_ac_tree(str(tmp_path), json.dumps(features))
    assert search_ac_tree(str(tmp_path), "") == []
    assert search_ac_tree(str(tmp_path), "   ") == []


def test_search_respects_limit(tmp_path):
    leaves = [_leaf(f"l{i}", f"user action item number {i}") for i in range(10)]
    tree = _branch("root", "root", leaves)
    features = [_feature("f1", "F", tree)]
    index_ac_tree(str(tmp_path), json.dumps(features))
    results = search_ac_tree(str(tmp_path), "user action", limit=3)
    assert len(results) <= 3


def test_search_returns_feature_metadata(tmp_path):
    features = [_feature("feat_auth", "Authentication", _leaf("l1", "Register form"))]
    index_ac_tree(str(tmp_path), json.dumps(features))
    results = search_ac_tree(str(tmp_path), "register")
    assert results[0]["feature_id"] == "feat_auth"
    assert results[0]["feature_name"] == "Authentication"


# ── search_ac_tree_by_feature ───────────────────────────────────────────────

def test_search_by_feature_returns_all_leaves(tmp_path):
    features = [
        _feature("f1", "Auth", _branch("r", "root", [
            _leaf("l1", "Login"),
            _leaf("l2", "Logout"),
        ])),
        _feature("f2", "Dashboard", _leaf("l3", "Charts")),
    ]
    index_ac_tree(str(tmp_path), json.dumps(features))
    results = search_ac_tree_by_feature(str(tmp_path), "f1")
    ids = {r["leaf_id"] for r in results}
    assert ids == {"l1", "l2"}
    assert all(r["feature_id"] == "f1" for r in results)


def test_search_by_feature_empty_when_not_found(tmp_path):
    features = [_feature("f1", "F", _leaf("l1", "something"))]
    index_ac_tree(str(tmp_path), json.dumps(features))
    results = search_ac_tree_by_feature(str(tmp_path), "nonexistent")
    assert results == []


def test_search_by_feature_empty_when_no_db(tmp_path):
    results = search_ac_tree_by_feature(str(tmp_path), "f1")
    assert results == []


def test_search_by_feature_empty_string_returns_empty(tmp_path):
    results = search_ac_tree_by_feature(str(tmp_path), "")
    assert results == []
