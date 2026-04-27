"""Unit tests for build_phase_z.py — post-stage finalize (T4.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import build_phase_z


def _write(path: Path, payload: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_with_passed_features() -> dict:
    return {
        "schema_version": "3.0",
        "name": "demo",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "features": [
            {
                "name": "auth",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "sign in", "children": [],
                     "status": "pass", "evidence": ["app/login/page.tsx:12"]},
                    {"id": "AC-2", "description": "sign out", "children": [],
                     "status": "pass", "evidence": ["app/login/page.tsx:25"]},
                ],
            },
            {
                "name": "todos",
                "acceptance_criteria": [
                    {"id": "AC-3", "description": "list todos", "children": [],
                     "status": "pass", "evidence": ["components/todos/list.tsx:8"]},
                    {"id": "AC-4", "description": "add todo", "children": [],
                     "status": "fail", "evidence": []},
                ],
            },
        ],
    }


# ── Implementation rate + metrics ───────────────────────────────────


def test_metrics_implementation_rate(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["metrics"]["total_leaves"] == 4
    assert out["metrics"]["passed_leaves"] == 3
    assert out["metrics"]["failed_leaves"] == 1
    assert out["metrics"]["implementation_rate"] == 0.75


def test_metrics_zero_leaves(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", {
        "schema_version": "3.0", "name": "x", "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"}, "features": [],
    })
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["metrics"]["implementation_rate"] == 0.0
    assert out["metrics"]["total_leaves"] == 0
    assert any("no AC leaves" in n for n in out["notes"])


def test_metrics_features_passed_count(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    # auth has 2/2 pass → completed; todos has 1 fail → not completed.
    assert out["metrics"]["features_passed"] == 1
    assert out["metrics"]["features_failed"] == 1


# ── AC verdict claim payloads ───────────────────────────────────────


def test_ac_verdict_claims_only_for_pass_leaves(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert len(out["ac_verdict_claims"]) == 3  # 3 pass, 1 fail
    for claim in out["ac_verdict_claims"]:
        assert claim["claim_type"] == "ac_verdict"
        assert claim["claimed_by"] == "agent:build-worker"
        assert claim["authority_file"] == "qa-results.json"


def test_ac_verdict_claim_carries_evidence(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    by_subject = {c["subject"]: c for c in out["ac_verdict_claims"]}
    assert "AC-1" in by_subject
    assert by_subject["AC-1"]["evidence"] == ["app/login/page.tsx:12"]


def test_ac_verdict_claim_includes_feature_tag(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    by_subject = {c["subject"]: c for c in out["ac_verdict_claims"]}
    assert by_subject["AC-1"]["feature"] == "auth"
    assert by_subject["AC-3"]["feature"] == "todos"


def test_build_ac_verdict_claims_helper_directly() -> None:
    leaves = [
        {"id": "AC-1", "status": "pass", "evidence": ["x.ts:1"], "feature": "f"},
        {"id": "AC-2", "status": "fail", "evidence": [], "feature": "f"},
    ]
    out = build_phase_z.build_ac_verdict_claims(leaves)
    assert len(out) == 1
    assert out[0]["subject"] == "AC-1"


# ── Stage claim ID ─────────────────────────────────────────────────


def test_stage_claim_id_pulled_from_state(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    _write(tmp_path / "project.state.json", {
        "session_id": "sess-x",
        "samvil_tier": "thorough",
        "stage_claims": {"build": "claim-build-001"},
    })
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["stage_claim_id"] == "claim-build-001"
    assert out["samvil_tier"] == "thorough"


def test_stage_claim_id_missing_emits_note(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["stage_claim_id"] == ""
    assert any("stage_claim_id missing" in n for n in out["notes"])


# ── Gate input ─────────────────────────────────────────────────────


def test_gate_input_shape(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    _write(tmp_path / "project.state.json", {"session_id": "x", "samvil_tier": "standard"})
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    gi = out["gate_input"]
    assert gi["gate_name"] == "build_to_qa"
    assert gi["samvil_tier"] == "standard"
    assert "implementation_rate" in gi["metrics"]


# ── Stagnation hint ───────────────────────────────────────────────


def test_stagnation_hint_no_prior_failures(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["stagnation_hint"]["should_evaluate"] is False
    assert out["stagnation_hint"]["prior_integration_failures"] == 0


def test_stagnation_hint_counts_integration_failures(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    events = tmp_path / ".samvil" / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(
        "\n".join([
            json.dumps({"stage": "build", "event_type": "build_fail",
                        "data": {"scope": "integration"}}),
            json.dumps({"stage": "build", "event_type": "build_fail",
                        "data": {"scope": "integration"}}),
            json.dumps({"stage": "build", "event_type": "build_pass",
                        "data": {"scope": "integration"}}),
            # Non-integration failures don't count.
            json.dumps({"stage": "build", "event_type": "build_fail",
                        "data": {"scope": "feature:auth"}}),
        ]) + "\n",
        encoding="utf-8",
    )
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["stagnation_hint"]["prior_integration_failures"] == 2
    assert out["stagnation_hint"]["should_evaluate"] is True


# ── Handoff block ─────────────────────────────────────────────────


def test_handoff_block_renders_completed_features(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    block = out["handoff_block"]
    assert "## Build Stage" in block
    assert "auth" in block  # completed
    assert "Tree progress: 4 total / 3 passed / 1 failed" in block


def test_handoff_block_renders_rate_budget_when_provided(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(
        tmp_path,
        rate_budget_stats={"peak": 3, "total_acquired": 12, "stale_recovery": 0},
    )
    assert "Rate budget: peak=3" in out["handoff_block"]


def test_handoff_block_no_rate_budget_when_omitted(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert "Rate budget" not in out["handoff_block"]


def test_handoff_block_helper_directly() -> None:
    block = build_phase_z.render_handoff_block(
        completed_features=["A", "B"],
        failed_features=[],
        retries=1,
        total_leaves=10,
        passed_leaves=10,
        failed_leaves=0,
        feature_count=2,
        rate_budget_stats=None,
    )
    assert "Completed: A, B" in block
    assert "Failed: 없음" in block
    assert "Retries: 1" in block


# ── Schema + serialization ────────────────────────────────────────


def test_schema_version_present(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert out["schema_version"] == build_phase_z.BUILD_PHASE_Z_SCHEMA_VERSION


def test_returns_serializable_json(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed_with_passed_features())
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert json.loads(json.dumps(out)) == out


def test_missing_seed_emits_error(tmp_path: Path) -> None:
    out = build_phase_z.finalize_build_phase_z(tmp_path)
    assert any("project.seed.json" in e for e in out["errors"])
