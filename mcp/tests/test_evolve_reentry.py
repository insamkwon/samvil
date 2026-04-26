"""Tests for rebuild reentry contracts."""

from __future__ import annotations

import json

from samvil_mcp.evolve_reentry import (
    build_rebuild_reentry,
    materialize_rebuild_reentry,
    rebuild_reentry_summary,
)


def _write_project(tmp_path, *, seed_version: int = 2, next_skill: str = "samvil-scaffold") -> None:
    (tmp_path / ".samvil").mkdir()
    (tmp_path / "project.seed.json").write_text(json.dumps({
        "name": "task-app",
        "version": seed_version,
        "features": [],
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "evolve-rebuild.json").write_text(json.dumps({
        "status": "ready",
        "from_version": 1,
        "to_version": 2,
        "next_skill": "samvil-scaffold",
        "reason": "evolved seed v1->v2 applied; rebuild with evolved seed",
    }), encoding="utf-8")
    (tmp_path / ".samvil" / "next-skill.json").write_text(json.dumps({
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "next_skill": next_skill,
        "reason": "evolved seed v1->v2 applied; rebuild with evolved seed",
        "from_stage": "evolve",
    }), encoding="utf-8")


def test_build_rebuild_reentry_is_ready_for_scaffold(tmp_path):
    _write_project(tmp_path)

    reentry = build_rebuild_reentry(tmp_path)

    assert reentry["status"] == "ready"
    assert reentry["next_skill"] == "samvil-scaffold"
    assert reentry["scaffold_input"]["seed_version"] == 2
    assert reentry["scaffold_input"]["seed_sha256"]


def test_materialize_rebuild_reentry_writes_scaffold_input(tmp_path):
    _write_project(tmp_path)

    result = materialize_rebuild_reentry(tmp_path)
    summary = rebuild_reentry_summary(tmp_path)

    assert result["status"] == "ready"
    assert (tmp_path / ".samvil" / "rebuild-reentry.json").exists()
    assert (tmp_path / ".samvil" / "scaffold-input.json").exists()
    assert summary["status"] == "ready"


def test_rebuild_reentry_blocks_when_seed_version_mismatches(tmp_path):
    _write_project(tmp_path, seed_version=3)

    result = materialize_rebuild_reentry(tmp_path)

    assert result["status"] == "blocked"
    assert not (tmp_path / ".samvil" / "scaffold-input.json").exists()
