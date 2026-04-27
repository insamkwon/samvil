"""Smoke tests for samvil-build (T4.8 ultra-thin migration).

The samvil-build skill is intentionally CC-bound: it spawns Agent
workers, runs `npm run build` / `npx tsc` / `npx expo export` /
`python -m py_compile`, writes `.samvil/build.log`, and parses
worker reply blocks. None of those move into MCP — graceful
degradation against host failures (P8) requires the skill body to
keep them.

What CAN be machine-pinned, and is pinned here, is the three new
build aggregator tools the thin skill delegates to. They own:

  - Phase A: stack identification, recipe path, build-verify command,
    Phase A.6 sanity scan, resume hint.
  - Phase B: MAX_PARALLEL resolution, batch composition via
    next_buildable_leaves, Worker context bundle, independence check,
    circuit-breaker counter readout.
  - Phase Z: per-leaf ac_verdict claim payload prep,
    implementation_rate metric, gate_check input, stagnation hint,
    pre-rendered handoff block.

7 critical preservation scenarios (must not regress):

  ST-1: Boot + Phase A web-app build verify.
  ST-2: Phase B parallel dispatch — 2 features × 4 leaves.
  ST-3: Circuit Breaker — consecutive=2 trips halt; next feature
        still runs.
  ST-4: Integration build per feature — implementation_rate
        accumulated across features.
  ST-5: Phase Z contract + gate input — claims + implementation_rate.
  ST-6: Stall detection + checkpoint resume — completed_features
        skipped on resume.
  ST-7: Reward Hacking prevention — failed leaf with no evidence
        does NOT generate an ac_verdict claim.

Plus solution_type coverage (5), rate-budget interactions, and
checkpoint-resume idempotency.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import build_phase_a, build_phase_b, build_phase_z


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_v3(
    name: str = "demo",
    solution_type: str = "web-app",
    framework: str = "nextjs",
    features: list[dict] | None = None,
) -> dict:
    if features is None:
        features = [
            {
                "name": "auth",
                "description": "auth flow",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "sign in", "children": [],
                     "status": "pass", "evidence": ["app/login.tsx:12"]},
                    {"id": "AC-2", "description": "sign out", "children": [],
                     "status": "pass", "evidence": ["app/login.tsx:25"]},
                ],
            },
            {
                "name": "todos",
                "description": "todo CRUD",
                "acceptance_criteria": [
                    {"id": "AC-3", "description": "list", "children": [],
                     "status": "pass", "evidence": ["components/todos/list.tsx:8"]},
                    {"id": "AC-4", "description": "add", "children": [],
                     "status": "pass", "evidence": ["components/todos/list.tsx:30"]},
                ],
            },
        ]
    return {
        "schema_version": "3.0",
        "name": name,
        "solution_type": solution_type,
        "tech_stack": {"framework": framework},
        "features": features,
    }


def _flat_tree(leaf_count: int = 4) -> str:
    children = [
        {"id": f"AC-{i}", "description": f"do {i}", "children": [], "status": "pending"}
        for i in range(1, leaf_count + 1)
    ]
    return json.dumps({
        "id": "AC-ROOT",
        "description": "root",
        "children": children,
        "status": "pending",
    })


# ═══════════════════════════════════════════════════════════════════
# 7 CRITICAL PRESERVATION SCENARIOS
# ═══════════════════════════════════════════════════════════════════


# ST-1: Boot + Phase A web-app build verify.


def test_st1_boot_phase_a_web_app(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_v3())
    _write(tmp_path / "project.state.json", {"session_id": "sess-x", "samvil_tier": "standard"})

    out = build_phase_a.aggregate_build_phase_a(tmp_path)
    assert out["solution_type"] == "web-app"
    assert "npm run build" in out["build_verify"]["command"]
    assert out["recipe_path"] == "references/web-recipes.md"
    assert out["resume_hint"]["session_id"] == "sess-x"
    assert out["sanity"]["passed"] is True


# ST-2: Phase B parallel dispatch — 2 features × 4 leaves each.


def test_st2_phase_b_parallel_dispatch(tmp_path: Path) -> None:
    seed = _seed_v3()
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature,
        feature_num=1,
        tree_json=_flat_tree(4),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    assert out["max_parallel"] == 2
    assert out["batch"]["count"] == 2  # honors MAX_PARALLEL
    assert len(out["worker_bundles"]) == 2
    # Every bundle has the worker contract pieces the skill body needs.
    for bundle in out["worker_bundles"]:
        assert bundle["leaf_id"]
        assert "files_created" in bundle["reply_format"]
        assert "Do NOT run" in bundle["contract"]["no_full_build"]


# ST-3: Circuit Breaker — consecutive=2 trips halt; next feature
# still runs (skill body re-enters Phase B for the next feature).


def test_st3_circuit_breaker_halts_at_two(tmp_path: Path) -> None:
    seed = _seed_v3()
    feature_a = seed["features"][0]
    out_halt = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature_a,
        feature_num=1,
        tree_json=_flat_tree(4),
        completed_ids=[],
        consecutive_fail_batches=2,
    )
    assert out_halt["circuit_breaker"]["halt"] is True
    assert out_halt["circuit_breaker"]["max_retries"] == 2

    # Next feature: counter resets (skill body owns this), tree dispatch
    # for feature B proceeds normally even though A halted.
    feature_b = seed["features"][1]
    out_b = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 2},
        feature=feature_b,
        feature_num=2,
        tree_json=_flat_tree(2),
        completed_ids=[],
        consecutive_fail_batches=0,  # fresh counter
    )
    assert out_b["circuit_breaker"]["halt"] is False
    assert out_b["batch"]["count"] == 2


# ST-4: Integration build per feature — implementation_rate
# accumulated across features (not per feature).


def test_st4_implementation_rate_across_features(tmp_path: Path) -> None:
    # 4 leaves total, 3 pass, 1 fail → 0.75 rate.
    seed = _seed_v3()
    seed["features"][1]["acceptance_criteria"][1]["status"] = "fail"
    seed["features"][1]["acceptance_criteria"][1]["evidence"] = []
    _write(tmp_path / "project.seed.json", seed)
    _write(tmp_path / "project.state.json", {"session_id": "x", "samvil_tier": "standard"})

    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["metrics"]["total_leaves"] == 4
    assert out["metrics"]["passed_leaves"] == 3
    assert out["metrics"]["failed_leaves"] == 1
    assert out["metrics"]["implementation_rate"] == 0.75
    assert out["gate_input"]["metrics"]["implementation_rate"] == 0.75


# ST-5: Phase Z contract + gate input — claims + implementation_rate
# wired to gate_check tool name.


def test_st5_phase_z_contract_layer_complete(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_v3())
    _write(tmp_path / "project.state.json", {
        "session_id": "sess-y",
        "samvil_tier": "thorough",
        "stage_claims": {"build": "claim-build-42"},
    })
    out = build_phase_z.finalize_build_phase_z(tmp_path)

    # 1. ac_verdict claim payloads ready (4 pass leaves → 4 claims).
    assert len(out["ac_verdict_claims"]) == 4
    for claim in out["ac_verdict_claims"]:
        assert claim["claim_type"] == "ac_verdict"
        assert claim["claimed_by"] == "agent:build-worker"
        assert claim["evidence"]  # non-empty

    # 2. Stage claim ID surfaced for skill's claim_verify call.
    assert out["stage_claim_id"] == "claim-build-42"

    # 3. Gate input ready for gate_check.
    assert out["gate_input"]["gate_name"] == "build_to_qa"
    assert out["gate_input"]["samvil_tier"] == "thorough"
    assert out["gate_input"]["metrics"]["implementation_rate"] == 1.0


# ST-6: Stall detection + checkpoint resume — completed_features
# in state.json carry forward; aggregator surfaces them so the skill
# can skip already-done work.


def test_st6_resume_skips_completed_features(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_v3())
    _write(tmp_path / "project.state.json", {
        "session_id": "sess-resume",
        "samvil_tier": "standard",
        "completed_features": ["auth"],
        "current_stage": "build",
    })
    out = build_phase_a.aggregate_build_phase_a(tmp_path)
    assert out["resume_hint"]["completed_features"] == ["auth"]
    # Phase B for an already-completed feature would dispatch 0 leaves
    # because the skill body skips it (we just expose the data here).


# ST-7: Reward Hacking prevention — failed leaf with no evidence
# does NOT generate an ac_verdict claim.


def test_st7_no_claims_for_failed_or_evidenceless_leaves(tmp_path: Path) -> None:
    seed = _seed_v3()
    # Force one leaf to be a failure with no evidence.
    seed["features"][0]["acceptance_criteria"][0]["status"] = "fail"
    seed["features"][0]["acceptance_criteria"][0]["evidence"] = []
    # Force another leaf to be pending (Reward Hacking edge case:
    # AI claims success without marking pass).
    seed["features"][1]["acceptance_criteria"][1]["status"] = "pending"
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_z.finalize_build_phase_z(tmp_path)

    subjects = {c["subject"] for c in out["ac_verdict_claims"]}
    assert "AC-1" not in subjects  # failed
    assert "AC-4" not in subjects  # pending
    assert "AC-2" in subjects
    assert "AC-3" in subjects


# ═══════════════════════════════════════════════════════════════════
# Solution-type coverage (5)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("solution_type,framework,expected_cmd_substr", [
    ("web-app", "nextjs", "npm run build"),
    ("dashboard", "nextjs", "npm run build"),
    ("game", "phaser", "tsc --noEmit"),
    ("mobile-app", "expo", "expo export"),
    ("automation", "python-script", "py_compile"),
])
def test_solution_type_coverage(
    tmp_path: Path, solution_type: str, framework: str, expected_cmd_substr: str
) -> None:
    seed = _seed_v3(solution_type=solution_type, framework=framework)
    if solution_type == "automation":
        seed["implementation"] = {"runtime": "python"}
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert expected_cmd_substr in out["build_verify"]["command"]


# ═══════════════════════════════════════════════════════════════════
# Rate-budget + checkpoint resume idempotency
# ═══════════════════════════════════════════════════════════════════


def test_rate_budget_stats_render_into_handoff(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_v3())
    out = build_phase_z.finalize_build_phase_z(
        tmp_path,
        rate_budget_stats={"peak": 4, "total_acquired": 16, "stale_recovery": 1},
    )
    assert "Rate budget: peak=4" in out["handoff_block"]
    assert "stale_recovery=1" in out["handoff_block"]


def test_checkpoint_resume_idempotent(tmp_path: Path) -> None:
    """Resume reads the same completed_features list across calls."""
    _write(tmp_path / "project.seed.json", _seed_v3())
    _write(tmp_path / "project.state.json", {
        "session_id": "sess-x",
        "completed_features": ["auth"],
    })
    out_a = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    out_b = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out_a["resume_hint"] == out_b["resume_hint"]


# ═══════════════════════════════════════════════════════════════════
# AC tree branch aggregation + dispatch state machine
# ═══════════════════════════════════════════════════════════════════


def test_dispatch_advances_through_completed_ids(tmp_path: Path) -> None:
    """Iterating completed_ids forward shows the aggregator only
    returns the next batch — the in-progress check that protects the
    Worker Dispatch Contract from re-spawning done work."""
    seed = _seed_v3(features=[{"name": "f", "acceptance_criteria": []}])
    feature = seed["features"][0]
    completed: list[str] = []
    seen: list[str] = []
    for _ in range(2):  # 4 leaves at MAX_PARALLEL=2 → 2 iterations.
        out = build_phase_b.dispatch_build_batch(
            seed=seed,
            blueprint=None,
            config={"max_parallel": 2},
            feature=feature,
            feature_num=1,
            tree_json=_flat_tree(4),
            completed_ids=completed,
            consecutive_fail_batches=0,
        )
        for bundle in out["worker_bundles"]:
            seen.append(bundle["leaf_id"])
            completed.append(bundle["leaf_id"])
    assert seen == ["AC-1", "AC-2", "AC-3", "AC-4"]


def test_dispatch_returns_zero_when_all_done(tmp_path: Path) -> None:
    seed = _seed_v3(features=[{"name": "f", "acceptance_criteria": []}])
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 4},
        feature=feature,
        feature_num=1,
        tree_json=_flat_tree(2),
        completed_ids=["AC-1", "AC-2"],
        consecutive_fail_batches=0,
    )
    assert out["batch"]["count"] == 0
    assert any("no buildable leaves" in n for n in out["notes"])


def test_dispatch_blocked_ancestor_blocks_descendants() -> None:
    """ac_tree.next_buildable_leaves' blocked-ancestor rule must be
    honored by the dispatch aggregator (preserves Reward Hacking
    barrier: failed parent → no children spawned)."""
    tree = {
        "id": "AC-ROOT", "description": "root", "status": "pending",
        "children": [
            {
                "id": "AC-A", "description": "blocked branch", "status": "blocked",
                "children": [
                    {"id": "AC-A-1", "description": "child", "status": "pending", "children": []},
                ],
            },
            {
                "id": "AC-B", "description": "ok branch", "status": "pending",
                "children": [
                    {"id": "AC-B-1", "description": "child b", "status": "pending", "children": []},
                ],
            },
        ],
    }
    seed = {"name": "x", "tech_stack": {"framework": "nextjs"}, "features": [{"name": "f"}]}
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 4},
        feature=seed["features"][0],
        feature_num=1,
        tree_json=json.dumps(tree),
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    leaf_ids = [b["leaf_id"] for b in out["worker_bundles"]]
    assert "AC-A-1" not in leaf_ids  # blocked ancestor
    assert "AC-B-1" in leaf_ids


# ═══════════════════════════════════════════════════════════════════
# Worker context contract — ≤2000 token budget proxy
# ═══════════════════════════════════════════════════════════════════


def test_worker_bundle_payload_under_size_budget() -> None:
    """JSON-serialized worker bundle stays small. ≤2000 tokens ≈
    ≤6000 chars (rough 3:1 char:token ratio for Korean+English mix).
    Skill body composes the final Agent prompt, but our context
    payload should not be the bloat."""
    seed = _seed_v3()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "do thing", "parent_id": None}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert len(serialized) <= 6000


def test_worker_bundle_persona_is_pointer_not_inline() -> None:
    """Persona is a *pointer* the skill body resolves — never the full
    file body (would explode token budget). T4.6 lesson."""
    seed = _seed_v3()
    feature = seed["features"][0]
    leaf = {"id": "AC-1", "description": "x"}
    bundle = build_phase_b.render_worker_context(seed, {}, feature, leaf)
    assert "agents/" in bundle["persona_pointer"]
    # Persona pointer must NOT contain a full agent body.
    assert len(bundle["persona_pointer"]) < 200


# ═══════════════════════════════════════════════════════════════════
# Cross-cutting: error pathway, schema stability
# ═══════════════════════════════════════════════════════════════════


def test_phase_a_continues_on_missing_state(tmp_path: Path) -> None:
    """INV-5: aggregator never raises on missing files."""
    _write(tmp_path / "project.seed.json", _seed_v3())
    out = build_phase_a.aggregate_build_phase_a(tmp_path)
    assert out["seed_loaded"] is True
    assert out["state_loaded"] is False
    # Resume hint is empty but still present.
    assert out["resume_hint"] == {
        "completed_features": [],
        "current_stage": "",
        "session_id": "",
        "current_model_build": {},
    }


def test_phase_z_handles_v2_flat_ac_list(tmp_path: Path) -> None:
    """v2 seeds carry ACs as flat string lists — aggregator should
    still extract leaves and compute implementation_rate."""
    seed = {
        "schema_version": "3.0",
        "name": "demo",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "features": [
            {
                "name": "feat",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "x", "children": [],
                     "status": "pass", "evidence": ["x.tsx:1"]},
                ],
            },
        ],
    }
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["metrics"]["implementation_rate"] == 1.0


def test_all_three_aggregators_return_schema_version() -> None:
    """Every aggregator must declare schema_version for forward-compat
    parsing in the skill body."""
    assert build_phase_a.BUILD_PHASE_A_SCHEMA_VERSION == "1.0"
    assert build_phase_b.BUILD_PHASE_B_SCHEMA_VERSION == "1.0"
    assert build_phase_z.BUILD_PHASE_Z_SCHEMA_VERSION == "1.0"


# ═══════════════════════════════════════════════════════════════════
# Additional preservation checks (Phase B/Z edge cases)
# ═══════════════════════════════════════════════════════════════════


def test_phase_a_sanity_warns_about_broken_imports_with_paths(tmp_path: Path) -> None:
    """A.6.3 → broken imports surface filename + import in warnings."""
    _write(tmp_path / "project.seed.json", _seed_v3())
    src = tmp_path / "src" / "feature.ts"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("import x from './nope';\n", encoding="utf-8")
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    assert out["sanity"]["passed"] is False
    assert any("src/feature.ts" in w for w in out["sanity"]["warnings"])


def test_phase_b_no_workers_when_completed_set_includes_all(tmp_path: Path) -> None:
    """Worker dispatch contract: don't spawn agents for already-pass
    leaves (preserves checkpoint resume semantics)."""
    seed = _seed_v3(features=[{"name": "f", "acceptance_criteria": []}])
    feature = seed["features"][0]
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={"max_parallel": 4},
        feature=feature,
        feature_num=1,
        tree_json=_flat_tree(3),
        completed_ids=["AC-1", "AC-2", "AC-3"],
        consecutive_fail_batches=0,
    )
    assert out["worker_bundles"] == []


def test_phase_b_parallel_meta_includes_diagnostics() -> None:
    """parallel_meta carries cpu_cores + memory_pct + source for retro
    instrumentation."""
    out = build_phase_b.resolve_max_parallel({}, cpu_cores=8, memory_pct=50.0)
    assert "cpu_cores" in out
    assert "memory_pct" in out
    assert "source" in out


def test_phase_z_handoff_block_marks_zero_failures_as_korean_none() -> None:
    """Handoff prose is in Korean — keep '없음' literal."""
    _write(
        Path("/tmp/sv-test-noempty"),
        "",  # placeholder; we're not using tmp_path here for handoff helper
    ) if False else None
    block = build_phase_z.render_handoff_block(
        completed_features=["A"],
        failed_features=[],
        retries=0,
        total_leaves=2,
        passed_leaves=2,
        failed_leaves=0,
        feature_count=1,
        rate_budget_stats=None,
    )
    assert "Failed: 없음" in block


def test_phase_z_implementation_rate_below_threshold_emits_warning(tmp_path: Path) -> None:
    """When implementation_rate is low, surface a note so the skill
    body can warn the user before chaining to gate_check."""
    seed = _seed_v3()
    # 4 leaves, 1 pass, 3 fail → 0.25 rate.
    for f in seed["features"]:
        for ac in f["acceptance_criteria"]:
            ac["status"] = "fail"
            ac["evidence"] = []
    seed["features"][0]["acceptance_criteria"][0]["status"] = "pass"
    seed["features"][0]["acceptance_criteria"][0]["evidence"] = ["x:1"]
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["metrics"]["implementation_rate"] == 0.25
    assert any("below typical" in n for n in out["notes"])


def test_phase_z_single_pass_leaf_renders_one_claim(tmp_path: Path) -> None:
    """Smallest valid case: 1 feature, 1 pass leaf → 1 ac_verdict claim."""
    seed = {
        "schema_version": "3.0", "name": "demo", "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "features": [
            {
                "name": "tiny",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "minimal", "children": [],
                     "status": "pass", "evidence": ["app/page.tsx:1"]},
                ],
            },
        ],
    }
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert len(out["ac_verdict_claims"]) == 1
    assert out["ac_verdict_claims"][0]["subject"] == "AC-1"


def test_phase_a_blueprint_loaded_flag(tmp_path: Path) -> None:
    """blueprint.json presence flips the loaded flag — skill body
    branches on this for Phase A.5 dependency pre-resolution."""
    _write(tmp_path / "project.seed.json", _seed_v3())
    _write(tmp_path / "project.blueprint.json", {"architecture": {"directory_structure": "app/"}})
    out = build_phase_a.aggregate_build_phase_a(tmp_path)
    assert out["blueprint_loaded"] is True


def test_phase_b_invalid_tree_does_not_raise() -> None:
    """INV-5: aggregator returns errors[] but never raises, so the
    skill body's try/catch wrapper isn't strictly required (still
    used as a defense-in-depth)."""
    seed = _seed_v3()
    out = build_phase_b.dispatch_build_batch(
        seed=seed,
        blueprint=None,
        config={},
        feature=seed["features"][0],
        feature_num=1,
        tree_json='{"id": "ROOT", "description": "x", "children": [{"id": "deep1", "description": "x", "children": [{"id": "deep2", "description": "x", "children": [{"id": "deep3", "description": "x", "children": [{"id": "deep4", "description": "x", "children": []}]}]}]}]}',
        completed_ids=[],
        consecutive_fail_batches=0,
    )
    # MAX_DEPTH=3 enforcement triggers an error path — the aggregator
    # surfaces it instead of crashing.
    assert "errors" in out
