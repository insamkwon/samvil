"""Tests for evolve rebuild continuation handoff."""

from __future__ import annotations

import json

from samvil_mcp.evolve_rebuild import (
    build_evolve_rebuild_handoff,
    evolve_rebuild_summary,
    materialize_evolve_rebuild_handoff,
)


def test_build_evolve_rebuild_handoff_from_applied_plan(tmp_path):
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-apply-plan.json").write_text(json.dumps({
        "status": "applied",
        "from_version": 1,
        "to_version": 2,
    }), encoding="utf-8")

    handoff = build_evolve_rebuild_handoff(tmp_path)

    assert handoff["status"] == "ready"
    assert handoff["next_skill"] == "samvil-scaffold"
    assert handoff["marker"]["from_stage"] == "evolve"


def test_materialize_evolve_rebuild_handoff_writes_next_skill_marker(tmp_path):
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-apply-plan.json").write_text(json.dumps({
        "status": "applied",
        "from_version": 1,
        "to_version": 2,
    }), encoding="utf-8")

    result = materialize_evolve_rebuild_handoff(tmp_path)
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))
    summary = evolve_rebuild_summary(tmp_path)

    assert result["status"] == "ready"
    assert result["next_skill"] == "samvil-scaffold"
    assert marker["next_skill"] == "samvil-scaffold"
    assert summary["present"] is True
    assert summary["next_skill"] == "samvil-scaffold"


def test_materialize_evolve_rebuild_blocks_before_apply(tmp_path):
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-apply-plan.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
    }), encoding="utf-8")

    result = materialize_evolve_rebuild_handoff(tmp_path)

    assert result["status"] == "blocked"
    assert not (tmp_path / ".samvil" / "next-skill.json").exists()
