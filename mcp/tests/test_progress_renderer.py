"""Tests for progress_renderer.py (v2.5.0, Phase 5)."""

import json
from pathlib import Path

import pytest

from samvil_mcp.progress_renderer import (
    render_double_diamond,
    render_ac_tree_flat,
    update_progress_file,
)


def test_render_double_diamond_all_pending():
    stage_statuses = {
        "interview": "pending",
        "build": "pending",
    }
    output = render_double_diamond(stage_statuses)
    assert "Discover" in output
    assert "Define" in output
    assert "Develop" in output
    assert "Deliver" in output


def test_render_double_diamond_in_progress():
    stage_statuses = {
        "interview": "done",
        "seed": "done",
        "build": "in_progress",
    }
    output = render_double_diamond(stage_statuses)
    assert "◆" in output or "◇" in output  # has diamond symbols


def test_render_double_diamond_empty():
    output = render_double_diamond({})
    assert "Discover" in output


def test_render_ac_tree_flat():
    features = [
        {
            "name": "auth",
            "acs": [
                {"id": "AC-1", "verdict": "PASS"},
                {"id": "AC-2", "verdict": "FAIL"},
            ],
        },
    ]
    output = render_ac_tree_flat(features)
    assert "auth" in output
    assert "[1/2]" in output
    assert "AC-1" in output
    assert "AC-2" in output


def test_update_progress_file_writes(tmp_path):
    state = {
        "current_stage": "build",
        "completed_stages": ["interview", "seed"],
    }
    result = update_progress_file(str(tmp_path), state)
    assert "path" in result
    assert result["bytes"] > 0

    progress_md = Path(result["path"])
    assert progress_md.exists()
    content = progress_md.read_text()
    assert "SAMVIL Progress" in content
    assert "build" in content


def test_update_progress_file_with_features(tmp_path):
    state = {"current_stage": "qa", "completed_stages": ["interview", "seed", "build"]}
    features = [{"name": "auth", "acs": [{"id": "AC-1", "verdict": "PASS"}]}]
    result = update_progress_file(str(tmp_path), state, features)
    content = Path(result["path"]).read_text()
    assert "Feature Progress" in content
    assert "auth" in content
