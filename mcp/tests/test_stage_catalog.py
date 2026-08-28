"""Canonical stage catalog characterization and safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.stage_catalog import (
    instruction_path_for,
    get_stage_spec,
    iter_stage_specs,
    skill_for_state_stage,
    state_stage_for,
    validate_stage_transition,
)


def test_catalog_preserves_pipeline_order_and_static_routes() -> None:
    names = [spec.skill_name for spec in iter_stage_specs()]
    assert names[:8] == [
        "samvil-interview",
        "samvil-seed",
        "samvil-council",
        "samvil-design",
        "samvil-scaffold",
        "samvil-build",
        "samvil-qa",
        "samvil-deploy",
    ]
    assert validate_stage_transition("samvil-interview", "samvil-seed") is True
    assert validate_stage_transition("samvil-build", "samvil-qa") is True
    assert validate_stage_transition("samvil-qa", "samvil-deploy") is True
    assert validate_stage_transition("samvil-design", "samvil-interview") is False


def test_catalog_preserves_dynamic_routes_and_terminal_behavior() -> None:
    assert set(get_stage_spec("samvil-qa").valid_next) == {
        "samvil-qa",
        "samvil-deploy",
        "samvil-evolve",
        "samvil-retro",
    }
    assert set(get_stage_spec("samvil-analyze").valid_next) == {
        "samvil-interview",
        "samvil-seed",
        "samvil-design",
        "samvil-qa",
    }
    assert set(get_stage_spec("samvil-evolve").valid_next) == {"samvil-build", "samvil-retro"}
    assert get_stage_spec("samvil-retro").terminal is True
    assert get_stage_spec("samvil-retro").valid_next == ()


def test_state_stage_views_remain_compatible() -> None:
    assert state_stage_for("samvil-build") == "build"
    assert state_stage_for("build") == "build"
    assert skill_for_state_stage("build") == "samvil-build"
    assert skill_for_state_stage("qa") == "samvil-qa"
    with pytest.raises(ValueError):
        state_stage_for("unknown-stage")


def test_instruction_paths_are_repo_contained_and_exist() -> None:
    repo = Path(__file__).resolve().parents[2]
    path = instruction_path_for("samvil-build", repo)
    assert path == (repo / "references/codex-commands/samvil-build.md").resolve()
    assert path.is_file()

    with pytest.raises(ValueError):
        instruction_path_for("../samvil-build", repo)
    with pytest.raises(ValueError):
        instruction_path_for("/tmp/escape", repo)
    with pytest.raises(ValueError):
        instruction_path_for("not-a-stage", repo)
