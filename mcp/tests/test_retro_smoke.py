"""Smoke tests for samvil-retro (T4.1 ultra-thin migration).

The samvil-retro skill is post-processing only — it reads finished-run
artifacts and writes a structured suggestion log. The skill body keeps
the bits that need a real shell / LLM call:

- Picking the 3 final suggestions (LLM judgement).
- AskUserQuestion for the new-app-preset accumulation prompt.
- Mutating `harness-feedback.log` (the skill decides what to write).
- Pipeline-end Compressor narrate (separate `narrate_*` tools).

What CAN be machine-pinned, and is pinned here, is the new
`aggregate_retro_metrics` MCP tool the thin skill delegates to. It owns:

- Per-run metric extraction from state.json + metrics.json + events.jsonl.
- Recurring-pattern detection across harness-feedback.log history.
- Bottleneck-stage identification (top 2 by duration_ms ≥ 20%).
- Flow compliance (planned vs. actual stage sequence).
- Agent utilization (configured tier vs. spawned agents).
- v3 AC tree leaf stats (counts grouped by status).
- Next suggestion ID computation (max v<major>-NNN + 1).
- MCP health summary (.samvil/mcp-health.jsonl).

Idempotency: re-aggregating the same project_root yields the same dict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import retro_aggregate


# ── Fixtures ───────────────────────────────────────────────────


def _write_seed(root: Path, **overrides) -> None:
    seed = {
        "schema_version": "3.0",
        "name": "demo-app",
        "vision": "test vision",
    }
    seed.update(overrides)
    (root / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")


def _write_state(
    root: Path,
    *,
    completed: list[str] | None = None,
    failed: list[str] | None = None,
    qa_history: list[dict] | None = None,
    build_retries: int = 0,
    selected_tier: str = "standard",
) -> None:
    state = {
        "completed_features": completed or ["feat_a", "feat_b"],
        "failed": failed or [],
        "qa_history": qa_history or [{"verdict": "PASS", "iteration": 1}],
        "build_retries": build_retries,
        "config": {"selected_tier": selected_tier},
    }
    (root / "project.state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )


def _write_metrics(root: Path, durations: dict[str, int]) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    metrics = {
        "stages": {
            name: {"duration_ms": d} for name, d in durations.items()
        },
        "total_duration_ms": sum(durations.values()),
    }
    (samvil / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")


def _write_events(root: Path, events: list[dict]) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    (samvil / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _write_health(root: Path, rows: list[dict]) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    (samvil / "mcp-health.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _write_interview(root: Path, n_questions: int) -> None:
    qs = "\n".join(f"Q{i}: question?" for i in range(1, n_questions + 1))
    (root / "interview-summary.md").write_text(qs, encoding="utf-8")


def _write_feedback_log(plugin_root: Path, entries: list[dict]) -> Path:
    plugin_root.mkdir(parents=True, exist_ok=True)
    log = plugin_root / "harness-feedback.log"
    log.write_text(json.dumps(entries), encoding="utf-8")
    return log


# ── Behavior 1: per-run metric extraction ──────────────────────


def test_extract_metrics_basic(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(
        tmp_path,
        completed=["a", "b", "c"],
        failed=["d"],
        build_retries=2,
        qa_history=[
            {"verdict": "FAIL", "iteration": 1},
            {"verdict": "PASS", "iteration": 2},
        ],
    )
    _write_metrics(
        tmp_path,
        {"interview": 1000, "build": 8000, "qa": 6000, "retro": 500},
    )
    _write_interview(tmp_path, 7)

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    m = out["metrics"]

    assert m["seed_name"] == "demo-app"
    assert m["features_passed"] == 3
    assert m["features_failed"] == 1
    assert m["features_attempted"] == 4
    assert m["build_retries"] == 2
    assert m["qa_iterations"] == 2
    assert m["qa_verdict"] == "PASS"
    assert m["interview_questions"] == 7
    assert m["total_duration_ms"] == 15500
    assert m["build_pass_rate"] == 0.75


# ── Behavior 2: bottleneck-stage identification ────────────────


def test_bottleneck_stages_top2_over_20pct(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_metrics(
        tmp_path,
        {
            "interview": 1000,
            "seed": 500,
            "design": 300,
            "build": 6000,  # 60%
            "qa": 2200,     # 22%
        },
    )
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    bn = out["metrics"]["bottleneck_stages"]
    assert "build" in bn
    assert "qa" in bn
    # interview at ~10% is below 20% threshold → excluded
    assert "interview" not in bn


# ── Behavior 3: recurring-pattern detection ────────────────────


def test_recurring_pattern_detected_across_runs(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(
        plugin_root,
        [
            {
                "run_id": "run-001",
                "suggestions_v2": [
                    {
                        "id": "v3-100",
                        "name": "drag-drop build failure",
                        "problem": "drag handler missing",
                        "fix": "add @hello-pangea/dnd setup",
                    }
                ],
            },
            {
                "run_id": "run-002",
                "suggestions_v2": [
                    {
                        "id": "v3-101",
                        "name": "drag-drop regression",
                        "problem": "drag again broken",
                        "fix": "drag library config",
                    }
                ],
            },
            {
                "run_id": "run-003",
                "suggestions_v2": [
                    {
                        "id": "v3-102",
                        "name": "drag-drop init failure",
                        "problem": "drag context provider missing",
                        "fix": "wrap with drag provider",
                    }
                ],
            },
        ],
    )
    _write_seed(tmp_path)
    _write_state(tmp_path)

    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
    )
    keywords = {p["keyword"] for p in out["recurring_patterns"]}
    assert "drag" in keywords
    drag = next(p for p in out["recurring_patterns"] if p["keyword"] == "drag")
    assert drag["count"] >= 3
    assert set(drag["runs"]) == {"run-001", "run-002", "run-003"}


def test_recurring_pattern_below_threshold_not_reported(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(
        plugin_root,
        [
            {
                "run_id": "run-001",
                "suggestions_v2": [
                    {
                        "id": "v3-100",
                        "name": "uniqueness",
                        "problem": "rare keyword",
                        "fix": "fix it",
                    }
                ],
            },
        ],
    )
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
    )
    # Only 1 occurrence — below default min_occurrences=3
    assert out["recurring_patterns"] == []


# ── Behavior 4: flow compliance ────────────────────────────────


def test_flow_compliance_detects_excessive_build(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_events(
        tmp_path,
        [
            {"event_type": "interview_started", "stage": "interview"},
            {"event_type": "seed_complete", "stage": "seed"},
            {"event_type": "build_started", "stage": "build"},
            {"event_type": "build_started", "stage": "build"},
            {"event_type": "build_started", "stage": "build"},
            {"event_type": "build_started", "stage": "build"},  # 4x build
            {"event_type": "qa_started", "stage": "qa"},
        ],
    )
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    fc = out["flow_compliance"]
    assert any("build executed" in d for d in fc["deviations"])
    assert "build" in fc["actual_sequence"]
    assert fc["matched"] is False


# ── Behavior 5: agent utilization ──────────────────────────────


def test_agent_utilization_underutilized_flag(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path, selected_tier="standard")  # tier_total=20
    _write_events(
        tmp_path,
        [
            {"event_type": "agent_spawn", "stage": "build",
             "data": {"agent": "frontend-dev"}},
            {"event_type": "agent_spawn", "stage": "qa",
             "data": {"agent": "qa-mechanical"}},
        ],
    )
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    au = out["agent_utilization"]
    assert au["tier"] == "standard"
    assert au["tier_total"] == 20
    assert au["used"] == 2
    assert au["utilization"] == 0.1
    assert au["underutilized"] is True


# ── Behavior 6: v3 AC leaf stats ───────────────────────────────


def test_v3_leaf_stats_grouped_by_status(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_events(
        tmp_path,
        [
            {"event_type": "ac_leaf_complete", "stage": "build",
             "data": {"status": "passed"}},
            {"event_type": "ac_leaf_complete", "stage": "build",
             "data": {"status": "passed"}},
            {"event_type": "ac_leaf_complete", "stage": "build",
             "data": {"status": "failed"}},
            {"event_type": "feature_tree_complete", "stage": "qa",
             "data": {"feature": "F1", "passed": 5, "failed": 1,
                      "total_leaves": 6}},
        ],
    )
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    leaf = out["v3_leaf_stats"]
    assert leaf["total_leaf_events"] == 3
    assert leaf["by_status"] == {"passed": 2, "failed": 1}
    assert len(leaf["feature_tree_complete"]) == 1
    assert leaf["feature_tree_complete"][0]["feature"] == "F1"


# ── Behavior 7: next suggestion ID assignment ──────────────────


def test_next_suggestion_id_increments_max(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(
        plugin_root,
        [
            {
                "run_id": "old",
                "suggestions_v2": [
                    {"id": "v3-005", "name": "x"},
                    {"id": "v3-027", "name": "y"},
                    {"id": "v3-012", "name": "z"},
                ],
            },
            {
                "run_id": "newer",
                "suggestions_v2": [
                    {"id": "v3-030", "name": "later"},
                ],
            },
        ],
    )
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
    )
    assert out["next_suggestion_id"] == "v3-031"


def test_next_suggestion_id_first_run(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(plugin_root, [])
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
    )
    assert out["next_suggestion_id"] == "v3-001"


def test_next_suggestion_id_respects_major(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(
        plugin_root,
        [
            {
                "run_id": "old",
                "suggestions_v2": [
                    {"id": "v3-099", "name": "v3 entry"},
                ],
            },
        ],
    )
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
        suggestion_major=4,
    )
    # v3-099 belongs to a different major; v4 starts at 001
    assert out["next_suggestion_id"] == "v4-001"


# ── Behavior 8: MCP health summary ─────────────────────────────


def test_mcp_health_summary(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_health(
        tmp_path,
        [
            {"status": "ok", "tool": "save_event"},
            {"status": "ok", "tool": "save_event"},
            {"status": "fail", "tool": "narrate_build_prompt",
             "error": "boom"},
            {"status": "fail", "tool": "narrate_build_prompt",
             "error": "boom"},
        ],
    )
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    h = out["mcp_health"]
    assert h["total"] == 4
    assert h["ok"] == 2
    assert h["fail"] == 2
    assert h["fail_rate"] == 0.5
    assert h["warning"] is True
    failed_names = {f["tool"] for f in h["failed_tools"]}
    assert "narrate_build_prompt" in failed_names


def test_mcp_health_missing_log(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    h = out["mcp_health"]
    assert h["exists"] is False
    assert h["total"] == 0
    assert h["fail_rate"] == 0.0


# ── Behavior 9: idempotency ────────────────────────────────────


def test_aggregate_idempotent(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path, completed=["a"], failed=["b"], build_retries=1)
    _write_metrics(tmp_path, {"build": 5000, "qa": 2000})
    _write_events(
        tmp_path,
        [
            {"event_type": "ac_leaf_complete", "stage": "build",
             "data": {"status": "passed"}},
        ],
    )
    _write_interview(tmp_path, 4)

    a = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    b = retro_aggregate.aggregate_retro_metrics(str(tmp_path))

    # Drop the keys that contain absolute paths (deterministic but uninteresting).
    for d in (a, b):
        d.pop("project_root", None)
    assert a == b


# ── Behavior 10: missing files = graceful zero-state ───────────


def test_missing_inputs_yield_zero_state(tmp_path: Path) -> None:
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    assert out["schema_version"] == "1.0"
    assert out["metrics"]["features_attempted"] == 0
    assert out["metrics"]["interview_questions"] == 0
    assert out["recurring_patterns"] == []
    assert out["flow_compliance"]["actual_sequence"] == []
    assert out["mcp_health"]["exists"] is False
    assert out["next_suggestion_id"] == "v3-001"


# ── Behavior 11: schema shape (renderable by skill) ────────────


def test_aggregate_returns_expected_top_level_keys(tmp_path: Path) -> None:
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    expected_keys = {
        "schema_version",
        "project_root",
        "feedback_log_path",
        "metrics",
        "recurring_patterns",
        "flow_compliance",
        "agent_utilization",
        "v3_leaf_stats",
        "mcp_health",
        "next_suggestion_id",
        "feedback_entries_count",
        "errors",
    }
    assert expected_keys.issubset(out.keys())


# ── Behavior 12: legacy `suggestions` (string array) recurring ─


def test_recurring_pattern_walks_legacy_suggestions(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write_feedback_log(
        plugin_root,
        [
            {
                "run_id": "run-001",
                "suggestions": [
                    "tailwind config breaks on fresh scaffold",
                    "interview questions too long",
                ],
            },
            {
                "run_id": "run-002",
                "suggestions": [
                    "tailwind purge regression detected",
                    "tailwind v4 migration trips users",
                ],
            },
            {
                "run_id": "run-003",
                "suggestions_v2": [
                    {
                        "id": "v3-100",
                        "name": "tailwind v4 default",
                        "problem": "tailwind config still bad",
                        "fix": "ship tailwind v4 baseline",
                    }
                ],
            },
        ],
    )
    _write_seed(tmp_path)
    _write_state(tmp_path)
    out = retro_aggregate.aggregate_retro_metrics(
        str(tmp_path),
        plugin_root=str(plugin_root),
    )
    keywords = {p["keyword"] for p in out["recurring_patterns"]}
    assert "tailwind" in keywords


# ── Behavior 13: v3-003 file-based fallback (sparse events) ────


def _write_qa_results(root: Path, verdict: str, ac_statuses: list[str]) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    ac_results = [{"id": f"AC-{i+1}", "status": s} for i, s in enumerate(ac_statuses)]
    (samvil / "qa-results.json").write_text(
        json.dumps({"verdict": verdict, "ac_results": ac_results}),
        encoding="utf-8",
    )


def test_qa_verdict_from_qa_results_when_events_sparse(tmp_path: Path) -> None:
    """When events.jsonl has no qa_history, derive verdict from qa-results.json."""
    # State has no qa_history; events.jsonl is empty
    state = {"completed_features": ["feat_a"], "config": {"selected_tier": "standard"}}
    (tmp_path / "project.state.json").write_text(json.dumps(state), encoding="utf-8")
    _write_seed(tmp_path)
    _write_qa_results(tmp_path, "PASS", ["PASS", "PASS", "PASS"])
    # Deliberately sparse events (no ac_leaf_complete entries)
    _write_events(tmp_path, [{"stage": "qa", "event_type": "stage_start"}])

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    assert out["metrics"]["qa_verdict"] == "PASS"


def test_leaf_stats_from_qa_results_when_events_empty(tmp_path: Path) -> None:
    """v3_leaf_stats should read ac_results from qa-results.json when no leaf events."""
    state = {"config": {"selected_tier": "standard"}}
    (tmp_path / "project.state.json").write_text(json.dumps(state), encoding="utf-8")
    _write_seed(tmp_path)
    _write_qa_results(tmp_path, "PASS", ["PASS", "PASS", "FAIL"])
    # No ac_leaf_complete events
    _write_events(tmp_path, [])

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    leaf_stats = out["v3_leaf_stats"]
    assert leaf_stats["total_leaf_events"] == 3
    assert leaf_stats["by_status"]["PASS"] == 2
    assert leaf_stats["by_status"]["FAIL"] == 1
    assert leaf_stats["source"] == "qa_results"


def test_leaf_stats_from_seed_when_qa_results_absent(tmp_path: Path) -> None:
    """v3_leaf_stats should fall back to seed.features AC tree as last resort."""
    features = [
        {
            "name": "f1",
            "description": "x",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "x", "status": "PASS", "children": []},
                {"id": "AC-2", "description": "y", "status": "FAIL", "children": []},
            ],
        }
    ]
    seed = {"schema_version": "3.0", "name": "demo", "features": features}
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    state = {"config": {"selected_tier": "standard"}}
    (tmp_path / "project.state.json").write_text(json.dumps(state), encoding="utf-8")
    # No qa-results.json, no events
    _write_events(tmp_path, [])

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    leaf_stats = out["v3_leaf_stats"]
    assert leaf_stats["total_leaf_events"] == 2
    assert leaf_stats["by_status"]["PASS"] == 1
    assert leaf_stats["by_status"]["FAIL"] == 1
    assert leaf_stats["source"] == "seed"


def test_flow_compliance_from_completed_stages_when_events_empty(tmp_path: Path) -> None:
    """compute_flow_compliance falls back to state.completed_stages when events are empty."""
    state = {
        "completed_stages": ["interview", "seed", "scaffold", "build", "qa"],
        "config": {"selected_tier": "standard"},
    }
    (tmp_path / "project.state.json").write_text(json.dumps(state), encoding="utf-8")
    _write_seed(tmp_path)
    _write_events(tmp_path, [])  # no stage events

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    fc = out["flow_compliance"]
    assert fc["source"] == "state_file"
    assert "interview" in fc["actual_sequence"]
    assert "qa" in fc["actual_sequence"]


def test_features_from_seed_when_state_has_no_completed_features(tmp_path: Path) -> None:
    """extract_metrics derives feature counts from seed AC tree when state is silent."""
    features = [
        {
            "name": "timer",
            "description": "countdown timer",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "starts", "status": "PASS", "children": []},
                {"id": "AC-2", "description": "stops", "status": "PASS", "children": []},
            ],
        }
    ]
    seed = {"schema_version": "3.0", "name": "demo", "features": features}
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    # State has no completed_features
    state: dict = {"config": {"selected_tier": "standard"}}
    (tmp_path / "project.state.json").write_text(json.dumps(state), encoding="utf-8")

    out = retro_aggregate.aggregate_retro_metrics(str(tmp_path))
    m = out["metrics"]
    assert m["features_passed"] == 2
    assert m["features_attempted"] == 2
