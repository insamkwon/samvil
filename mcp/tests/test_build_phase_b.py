"""Unit tests for build_phase_b.py — per-batch dispatch (T4.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import build_phase_b


# ── MAX_PARALLEL resolution ────────────────────────────────────────


def test_user_override_wins() -> None:
    out = build_phase_b.resolve_max_parallel(
        {"max_parallel": 5}, cpu_cores=2, memory_pct=10.0
    )
    assert out["max_parallel"] == 5
    assert out["source"] == "config"


def test_low_cpu_returns_one() -> None:
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=2, memory_pct=10.0)
    assert out["max_parallel"] == 1
    assert out["source"] == "cpu"


def test_high_cpu_returns_three() -> None:
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=12, memory_pct=20.0)
    assert out["max_parallel"] == 3


def test_mid_cpu_returns_two() -> None:
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=6, memory_pct=20.0)
    assert out["max_parallel"] == 2


def test_memory_pressure_clamps_down() -> None:
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=8, memory_pct=85.0)
    assert out["max_parallel"] == 2  # 3 - 1 due to mem clamp
    assert "memory_clamp" in out["source"]


def test_memory_clamp_floor_one() -> None:
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=2, memory_pct=95.0)
    # Already at 1; clamp must not go below 1.
    assert out["max_parallel"] == 1


def test_invalid_user_override_falls_back_to_cpu() -> None:
    out = build_phase_b.resolve_max_parallel(
        {"max_parallel": "garbage"}, cpu_cores=8, memory_pct=10.0
    )
    assert out["max_parallel"] == 3
    assert out["source"] == "cpu"


# ── Worker context bundle ──────────────────────────────────────────


def _seed_with_features() -> dict:
    return {
        "name": "demo",
        "tech_stack": {
            "framework": "nextjs",
            "ui_library": "shadcn",
            "state": "zustand",
            "language": "typescript",
        },
        "features": [
            {"name": "auth", "description": "auth flow"},
            {"name": "todo-crud", "description": "todo CRUD"},
            {"name": "calendar", "description": "calendar"},
        ],
    }


def test_worker_bundle_includes_all_required_blocks() -> None:
    seed = _seed_with_features()
    blueprint = {"architecture": {"directory_structure": "app/, components/, lib/"}}
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "user can sign in", "parent_id": None}
    bundle = build_phase_b.render_worker_context(seed, blueprint, feature, leaf)
    assert "persona_pointer" in bundle
    assert "context" in bundle
    assert "your_leaf" in bundle
    assert "contract" in bundle
    assert "reply_format" in bundle


def test_worker_bundle_peers_excludes_self() -> None:
    seed = _seed_with_features()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    peers = bundle["context"]["peers"]
    assert "auth" not in peers
    assert "todo-crud" in peers
    assert "calendar" in peers


def test_worker_bundle_stack_summary_compact() -> None:
    seed = _seed_with_features()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    stack = bundle["context"]["stack"]
    assert "nextjs" in stack
    assert len(stack) <= 80


def test_worker_bundle_reply_format_parseable() -> None:
    seed = _seed_with_features()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    fmt = bundle["reply_format"]
    # The skill body parses these lines, so they must be present verbatim.
    assert "Leaf:" in fmt
    assert "files_created" in fmt
    assert "typecheck_ok" in fmt


def test_worker_bundle_contract_no_full_build() -> None:
    seed = _seed_with_features()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    assert "Do NOT run" in bundle["contract"]["no_full_build"]


def test_worker_bundle_handles_missing_blueprint() -> None:
    seed = _seed_with_features()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    assert "blueprint" in bundle["context"]["architecture"].lower() or bundle["context"]["architecture"]


# ── Independence check ────────────────────────────────────────────


def test_independence_no_overlap_returns_independent() -> None:
    features = [
        {"name": "A", "touched_files": ["components/A/x.tsx"]},
        {"name": "B", "touched_files": ["components/B/y.tsx"]},
    ]
    out = build_phase_b.check_feature_independence(features)
    assert out["independent_pairs"] == [["A", "B"]]
    assert out["sequential_pairs"] == []


def test_independence_shared_file_downgrades_to_sequential() -> None:
    features = [
        {"name": "A", "touched_files": ["app/layout.tsx"]},
        {"name": "B", "touched_files": ["app/layout.tsx"]},
    ]
    out = build_phase_b.check_feature_independence(features)
    assert out["independent_pairs"] == []
    assert any(p[:2] == ["A", "B"] for p in out["sequential_pairs"])


def test_independence_dependency_link_downgrades() -> None:
    features = [
        {"name": "A"},
        {"name": "B", "depends_on": ["A"]},
    ]
    out = build_phase_b.check_feature_independence(features)
    assert any("dependency link" in p[2] for p in out["sequential_pairs"])


def test_independence_shared_route_downgrades() -> None:
    features = [
        {"name": "A", "routes": ["/dashboard"]},
        {"name": "B", "routes": ["/dashboard"]},
    ]
    out = build_phase_b.check_feature_independence(features)
    assert out["sequential_pairs"]


def test_independence_shared_store_slice_downgrades() -> None:
    features = [
        {"name": "A", "store_slice": "userSlice"},
        {"name": "B", "store_slice": "userSlice"},
    ]
    out = build_phase_b.check_feature_independence(features)
    assert out["sequential_pairs"]


# ── dispatch_build_batch (the aggregator entry point) ─────────────


def _tree_json(leaf_count: int = 4) -> str:
    children = [
        {"id": f"AC-{i}", "description": f"do thing {i}", "children": [], "status": "pending"}
        for i in range(1, leaf_count + 1)
    ]
    root = {"id": "AC-ROOT", "description": "root", "children": children, "status": "pending"}
    return json.dumps(root)


def test_dispatch_returns_correct_batch_size() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature,
        feature_num=1,
        tree_json=_tree_json(4),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out["batch"]["count"] == 2  # max_parallel=2
    assert len(out["worker_bundles"]) == 2


def test_dispatch_skips_completed_leaves() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 4},
        feature=feature,
        feature_num=1,
        tree_json=_tree_json(4),
        completed_ids=["AC-1", "AC-2"],
        consecutive_fail_batches=0,
    )
    leaf_ids = [b["leaf_id"] for b in out["worker_bundles"]]
    assert "AC-1" not in leaf_ids
    assert "AC-2" not in leaf_ids
    assert "AC-3" in leaf_ids


def test_dispatch_circuit_breaker_halt() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature,
        feature_num=1,
        tree_json=_tree_json(4),
        completed_ids=[],
        consecutive_fail_batches=2,
    )
    assert out["circuit_breaker"]["halt"] is True
    assert out["circuit_breaker"]["max_retries"] == 2


def test_dispatch_circuit_breaker_no_halt() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature,
        feature_num=1,
        tree_json=_tree_json(4),
        completed_ids=[],
        consecutive_fail_batches=1,
    )
    assert out["circuit_breaker"]["halt"] is False


def test_dispatch_invalid_tree_returns_empty_batch_with_error() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={},
        feature=feature,
        feature_num=1,
        tree_json="{not valid json",
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out["batch"]["count"] == 0
    assert out["errors"]


def test_dispatch_independence_only_when_multiple_features() -> None:
    # Multiple features → independence runs.
    seed_multi = {
        "name": "demo",
        "tech_stack": {"framework": "nextjs"},
        "features": [{"name": "A"}, {"name": "B"}],
    }
    out_multi = build_phase_b.dispatch_build_batch(
        seed=seed_multi,
        blueprint=None,
        config={},
        feature=seed_multi["features"][0],
        feature_num=1,
        tree_json=_tree_json(2),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out_multi["independence"] is not None

    # Single feature → independence skipped.
    seed_single = {
        "name": "demo",
        "tech_stack": {"framework": "nextjs"},
        "features": [{"name": "A"}],
    }
    out_single = build_phase_b.dispatch_build_batch(
        seed=seed_single,
        blueprint=None,
        config={},
        feature=seed_single["features"][0],
        feature_num=1,
        tree_json=_tree_json(2),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out_single["independence"] is None


# ── FTS enrichment (Items 2 + 3) ─────────────────────────────────────


def _make_seed_feature(feature_name: str = "Auth") -> tuple[dict, dict]:
    seed = {
        "name": "demo",
        "tech_stack": {"framework": "nextjs"},
        "features": [{"name": feature_name, "id": feature_name.lower()}],
    }
    feature = {"name": feature_name, "id": feature_name.lower(), "description": "Feature desc"}
    return seed, feature


def _make_leaf(lid: str = "l1", desc: str = "User can login") -> dict:
    return {"id": lid, "description": desc, "children": [], "status": "pending"}


def test_render_worker_context_accepts_fts_sibling_leaves() -> None:
    seed, feature = _make_seed_feature()
    leaf = _make_leaf("l1", "Login form")
    fts_siblings = [
        {"leaf_id": "l2", "feature_id": "auth", "feature_name": "Auth",
         "description": "Logout flow", "status": "pending"},
    ]
    bundle = build_phase_b.render_worker_context(
        seed, {}, feature, leaf,
        fts_sibling_leaves=fts_siblings,
    )
    sibling_ctx = bundle["your_leaf"]["sibling_leaf_context"]
    assert len(sibling_ctx) == 1
    assert sibling_ctx[0]["id"] == "l2"
    assert sibling_ctx[0]["description"] == "Logout flow"


def test_render_worker_context_excludes_self_from_siblings() -> None:
    seed, feature = _make_seed_feature()
    leaf = _make_leaf("l1", "Login form")
    fts_siblings = [
        {"leaf_id": "l1", "feature_id": "auth", "feature_name": "Auth",
         "description": "Login form", "status": "pending"},
        {"leaf_id": "l2", "feature_id": "auth", "feature_name": "Auth",
         "description": "Logout flow", "status": "pending"},
    ]
    bundle = build_phase_b.render_worker_context(
        seed, {}, feature, leaf,
        fts_sibling_leaves=fts_siblings,
    )
    ids = [s["id"] for s in bundle["your_leaf"]["sibling_leaf_context"]]
    assert "l1" not in ids
    assert "l2" in ids


def test_render_worker_context_cross_feature_related() -> None:
    seed, feature = _make_seed_feature()
    leaf = _make_leaf("l1", "User authentication")
    cross = [
        {"leaf_id": "xl1", "feature_id": "dashboard", "feature_name": "Dashboard",
         "description": "Redirect after login", "status": "pending"},
    ]
    bundle = build_phase_b.render_worker_context(
        seed, {}, feature, leaf,
        cross_feature_related=cross,
    )
    cfr = bundle["your_leaf"]["cross_feature_related"]
    assert len(cfr) == 1
    assert cfr[0]["feature"] == "Dashboard"
    assert "Redirect" in cfr[0]["description"]


def test_render_worker_context_empty_fts_returns_empty_lists() -> None:
    seed, feature = _make_seed_feature()
    leaf = _make_leaf("l1", "Login")
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    assert bundle["your_leaf"]["sibling_leaf_context"] == []
    assert bundle["your_leaf"]["cross_feature_related"] == []


def test_dispatch_accepts_project_root_gracefully(tmp_path) -> None:
    """dispatch_build_batch with project_root pointing to empty dir is non-fatal."""
    seed, feature = _make_seed_feature()
    tree = json.dumps({
        "id": "root", "description": "root", "children": [
            {"id": "l1", "description": "Login", "children": [], "status": "pending"},
        ], "status": "pending",
    })
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={},
        feature=feature,
        feature_num=1,
        tree_json=tree,
        completed_ids=[],
        consecutive_fail_batches=0,
        project_root=str(tmp_path),  # no FTS index — graceful degradation
    )
    assert out["batch"]["count"] == 1
    assert not out["errors"]
    # sibling_leaf_context and cross_feature_related should be empty (no DB)
    bundle = out["worker_bundles"][0]
    assert bundle["your_leaf"]["sibling_leaf_context"] == []
    assert bundle["your_leaf"]["cross_feature_related"] == []


def test_dispatch_fts_enrichment_when_db_exists(tmp_path) -> None:
    """When FTS DB exists, sibling_leaf_context is populated."""
    import json as _json
    from samvil_mcp.ac_search import index_ac_tree

    seed, feature = _make_seed_feature("Auth")
    ac_tree = {
        "id": "root", "description": "Auth root", "children": [
            {"id": "l1", "description": "Login form", "children": [], "status": "pending"},
            {"id": "l2", "description": "Logout button", "children": [], "status": "pending"},
        ], "status": "pending",
    }
    features_json = _json.dumps([{
        "id": "auth", "name": "Auth", "acceptance_criteria": ac_tree,
    }])
    index_ac_tree(str(tmp_path), features_json)

    tree_json = _json.dumps(ac_tree)
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature,
        feature_num=1,
        tree_json=tree_json,
        completed_ids=[],
        consecutive_fail_batches=0,
        project_root=str(tmp_path),
    )
    assert out["batch"]["count"] == 2
    # Each worker bundle should have sibling_leaf_context populated
    for bundle in out["worker_bundles"]:
        ctx = bundle["your_leaf"]["sibling_leaf_context"]
        assert isinstance(ctx, list)
        # Should not include self
        self_id = bundle["your_leaf"]["leaf_id"]
        assert all(s["id"] != self_id for s in ctx)


def test_dispatch_schema_version_present() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={},
        feature=seed["features"][0],
        feature_num=1,
        tree_json=_tree_json(2),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out["schema_version"] == build_phase_b.BUILD_PHASE_B_SCHEMA_VERSION


def test_dispatch_returns_serializable_json() -> None:
    seed = {"name": "demo", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={},
        feature=seed["features"][0],
        feature_num=1,
        tree_json=_tree_json(3),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert json.loads(json.dumps(out)) == out
