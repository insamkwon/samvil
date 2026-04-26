"""Tests for guarded evolve apply plans."""

from __future__ import annotations

import json

from samvil_mcp.evolve_apply import (
    apply_evolve_apply_plan,
    build_evolve_apply_plan,
    evolve_apply_summary,
    materialize_evolve_apply_plan,
    read_evolve_apply_plan,
)


def _seed() -> dict:
    return {
        "schema_version": "3.2",
        "name": "task-app",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Create tasks"},
        "features": [
            {
                "name": "tasks",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "User can create tasks", "children": [], "status": "pending", "evidence": []}
                ],
            }
        ],
    }


def _proposal() -> dict:
    return {
        "status": "ready",
        "seed_name": "task-app",
        "from_version": 1,
        "to_version": 2,
        "proposed_changes": [
            {"type": "clarify_or_split_ac", "target": "AC-1", "instruction": "split", "apply_mode": "proposal_only"}
        ],
    }


def test_build_evolve_apply_plan_previews_seed_patch(tmp_path):
    plan = build_evolve_apply_plan(tmp_path, proposal=_proposal(), seed=_seed())

    assert plan["status"] == "ready"
    assert plan["from_version"] == 1
    assert plan["to_version"] == 2
    assert plan["operations"][0]["status"] == "mutated"
    children = plan["evolved_seed"]["features"][0]["acceptance_criteria"][0]["children"]
    assert len(children) == 2
    assert plan["validation"]["valid"] is True


def test_materialize_and_apply_evolve_plan_writes_backup_and_seed(tmp_path):
    (tmp_path / "project.seed.json").write_text(json.dumps(_seed()), encoding="utf-8")
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-proposal.json").write_text(json.dumps(_proposal()), encoding="utf-8")

    materialized = materialize_evolve_apply_plan(tmp_path)
    plan = read_evolve_apply_plan(tmp_path)
    summary = evolve_apply_summary(tmp_path)
    applied = apply_evolve_apply_plan(tmp_path)
    seed = json.loads((tmp_path / "project.seed.json").read_text(encoding="utf-8"))

    assert materialized["status"] == "ready"
    assert summary["mutations"] == 1
    assert plan["status"] == "ready"
    assert applied["status"] == "applied"
    assert seed["version"] == 2
    assert (tmp_path / "seed_history" / "v1.json").exists()
    assert (tmp_path / "seed_history" / "v1_v2_diff.md").exists()


def test_apply_evolve_plan_blocks_if_seed_changed_after_plan(tmp_path):
    seed = _seed()
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-proposal.json").write_text(json.dumps(_proposal()), encoding="utf-8")
    materialize_evolve_apply_plan(tmp_path)
    seed["version"] = 99
    (tmp_path / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")

    applied = apply_evolve_apply_plan(tmp_path)

    assert applied["status"] == "blocked"
    assert applied["next_action"] == "rebuild evolve apply plan"
