"""Unit tests for mcp/samvil_mcp/resume.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samvil_mcp.resume import (
    _handoff_excerpt,
    _minutes_since,
    _stage_progress,
    resume_session,
    write_leaf_checkpoint,
    read_leaf_checkpoint,
    clear_leaf_checkpoint,
)


# ── _minutes_since ────────────────────────────────────────────────


def test_minutes_since_none_input() -> None:
    assert _minutes_since(None) is None


def test_minutes_since_invalid_string() -> None:
    assert _minutes_since("not-a-date") is None


def test_minutes_since_recent() -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=42)).isoformat()
    result = _minutes_since(ts)
    assert result is not None
    assert 41 <= result <= 43


def test_minutes_since_z_suffix() -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    result = _minutes_since(ts)
    assert result is not None
    assert 9 <= result <= 11


# ── _stage_progress ───────────────────────────────────────────────


def test_stage_progress_build_in_progress() -> None:
    state = {
        "current_stage": "build",
        "completed_features": ["a", "b"],
        "in_progress": "c",
    }
    assert _stage_progress(state) == "Phase B: 2 done, 'c' in progress"


def test_stage_progress_build_no_in_progress() -> None:
    state = {"current_stage": "build", "completed_features": ["a"], "in_progress": ""}
    assert _stage_progress(state) == "Phase B: 1 features done"


def test_stage_progress_build_starting() -> None:
    state = {"current_stage": "build", "completed_features": [], "in_progress": ""}
    assert _stage_progress(state) == "Phase B: starting"


def test_stage_progress_qa_with_history() -> None:
    state = {"current_stage": "qa", "qa_history": [1, 2]}
    assert _stage_progress(state) == "QA: 2/3 pass(es) done"


def test_stage_progress_qa_starting() -> None:
    state = {"current_stage": "qa", "qa_history": []}
    assert _stage_progress(state) == "QA: starting"


def test_stage_progress_evolve() -> None:
    state = {"current_stage": "evolve", "retro_count": 3}
    assert _stage_progress(state) == "Evolve: cycle 3"


def test_stage_progress_other_stage() -> None:
    state = {"current_stage": "design"}
    assert _stage_progress(state) == "design"


# ── _handoff_excerpt ──────────────────────────────────────────────


def test_handoff_excerpt_missing_file(tmp_path: Path) -> None:
    assert _handoff_excerpt(tmp_path) == ""


def test_handoff_excerpt_short_file(tmp_path: Path) -> None:
    (tmp_path / "handoff.md").write_text("short content")
    assert _handoff_excerpt(tmp_path) == "short content"


def test_handoff_excerpt_long_file(tmp_path: Path) -> None:
    (tmp_path / "handoff.md").write_text("x" * 1000)
    result = _handoff_excerpt(tmp_path, max_chars=500)
    assert len(result) == 500


# ── resume_session ────────────────────────────────────────────────


def test_resume_session_no_state(tmp_path: Path) -> None:
    r = resume_session(str(tmp_path))
    assert r["found"] is False
    assert r["next_skill"] == "samvil-interview"
    assert r["completed_features"] == []
    assert r["failed_acs"] == []
    assert r["samvil_tier"] == "standard"


def test_resume_session_empty_state(tmp_path: Path) -> None:
    (tmp_path / "project.state.json").write_text("{}")
    r = resume_session(str(tmp_path))
    assert r["found"] is False


def test_resume_session_primary_state_path(tmp_path: Path) -> None:
    state = {"current_stage": "design", "samvil_tier": "thorough"}
    (tmp_path / "project.state.json").write_text(json.dumps(state))
    r = resume_session(str(tmp_path))
    assert r["found"] is True
    assert r["last_stage"] == "design"
    assert r["next_skill"] == "samvil-design"
    assert r["samvil_tier"] == "thorough"


def test_resume_session_fallback_samvil_dir(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    state = {"current_stage": "scaffold"}
    (samvil / "state.json").write_text(json.dumps(state))
    r = resume_session(str(tmp_path))
    assert r["found"] is True
    assert r["next_skill"] == "samvil-scaffold"


def test_resume_session_primary_takes_precedence(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (tmp_path / "project.state.json").write_text(json.dumps({"current_stage": "build"}))
    (samvil / "state.json").write_text(json.dumps({"current_stage": "qa"}))
    r = resume_session(str(tmp_path))
    assert r["last_stage"] == "build"


def test_resume_session_all_stages_map_correctly(tmp_path: Path) -> None:
    stage_pairs = [
        ("interview", "samvil-interview"),
        ("seed", "samvil-seed"),
        ("council", "samvil-council"),
        ("design", "samvil-design"),
        ("scaffold", "samvil-scaffold"),
        ("build", "samvil-build"),
        ("qa", "samvil-qa"),
        ("deploy", "samvil-deploy"),
        ("evolve", "samvil-evolve"),
        ("retro", "samvil-retro"),
    ]
    for stage, expected_skill in stage_pairs:
        state_file = tmp_path / "project.state.json"
        state_file.write_text(json.dumps({"current_stage": stage}))
        r = resume_session(str(tmp_path))
        assert r["next_skill"] == expected_skill, f"stage={stage}"


def test_resume_session_project_name_from_seed(tmp_path: Path) -> None:
    (tmp_path / "project.state.json").write_text(json.dumps({"current_stage": "qa"}))
    (tmp_path / "project.seed.json").write_text(json.dumps({"project_name": "my-app"}))
    r = resume_session(str(tmp_path))
    assert r["project_name"] == "my-app"


def test_resume_session_failed_acs_propagated(tmp_path: Path) -> None:
    state = {
        "current_stage": "build",
        "failed_acs": ["AC-1", "AC-2"],
    }
    (tmp_path / "project.state.json").write_text(json.dumps(state))
    r = resume_session(str(tmp_path))
    assert r["failed_acs"] == ["AC-1", "AC-2"]


def test_resume_session_minutes_since_set(tmp_path: Path) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    state = {"current_stage": "build", "last_progress_at": ts}
    (tmp_path / "project.state.json").write_text(json.dumps(state))
    r = resume_session(str(tmp_path))
    assert r["minutes_since"] is not None
    assert 29 <= r["minutes_since"] <= 31


def test_resume_session_handoff_included(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "handoff.md").write_text("last note here")
    (tmp_path / "project.state.json").write_text(json.dumps({"current_stage": "evolve"}))
    r = resume_session(str(tmp_path))
    assert r["handoff_excerpt"] == "last note here"


def test_resume_session_in_progress_leaf_none_by_default(tmp_path: Path) -> None:
    (tmp_path / "project.state.json").write_text(json.dumps({"current_stage": "build"}))
    r = resume_session(str(tmp_path))
    assert r["in_progress_leaf"] is None


def test_resume_session_no_state_has_leaf_none(tmp_path: Path) -> None:
    r = resume_session(str(tmp_path))
    assert r["in_progress_leaf"] is None


# ── write/read/clear leaf checkpoint ─────────────────────────────


def test_write_leaf_checkpoint_returns_dict(tmp_path: Path) -> None:
    c = write_leaf_checkpoint(str(tmp_path), "feat_auth", "ac_2_3", "JWT validation")
    assert c["feature_id"] == "feat_auth"
    assert c["leaf_id"] == "ac_2_3"
    assert c["leaf_description"] == "JWT validation"
    assert "written_at" in c


def test_write_leaf_checkpoint_creates_file(tmp_path: Path) -> None:
    write_leaf_checkpoint(str(tmp_path), "feat_auth", "ac_2_3")
    path = tmp_path / ".samvil" / "leaf-checkpoint.json"
    assert path.exists()


def test_read_leaf_checkpoint_roundtrip(tmp_path: Path) -> None:
    write_leaf_checkpoint(str(tmp_path), "feat_auth", "ac_2_3", "JWT validation")
    r = read_leaf_checkpoint(str(tmp_path))
    assert r is not None
    assert r["feature_id"] == "feat_auth"
    assert r["leaf_id"] == "ac_2_3"


def test_read_leaf_checkpoint_none_when_missing(tmp_path: Path) -> None:
    assert read_leaf_checkpoint(str(tmp_path)) is None


def test_read_leaf_checkpoint_none_on_corrupt(tmp_path: Path) -> None:
    d = tmp_path / ".samvil"
    d.mkdir()
    (d / "leaf-checkpoint.json").write_text("not json{")
    assert read_leaf_checkpoint(str(tmp_path)) is None


def test_clear_leaf_checkpoint_returns_true(tmp_path: Path) -> None:
    write_leaf_checkpoint(str(tmp_path), "f", "l")
    assert clear_leaf_checkpoint(str(tmp_path)) is True
    assert read_leaf_checkpoint(str(tmp_path)) is None


def test_clear_leaf_checkpoint_returns_false_when_missing(tmp_path: Path) -> None:
    assert clear_leaf_checkpoint(str(tmp_path)) is False


# ── _stage_progress with leaf ─────────────────────────────────────


def test_stage_progress_build_with_leaf_no_completed(tmp_path: Path) -> None:
    state = {"current_stage": "build", "completed_features": [], "in_progress": ""}
    leaf = {"feature_id": "feat_auth", "leaf_id": "ac_2_3", "leaf_description": "JWT"}
    result = _stage_progress(state, leaf)
    assert "feat_auth" in result
    assert "ac_2_3" in result
    assert "JWT" in result


def test_stage_progress_build_with_leaf_and_completed(tmp_path: Path) -> None:
    state = {"current_stage": "build", "completed_features": ["feat_login"], "in_progress": ""}
    leaf = {"feature_id": "feat_auth", "leaf_id": "ac_2_3", "leaf_description": ""}
    result = _stage_progress(state, leaf)
    assert "1 done" in result
    assert "feat_auth" in result
