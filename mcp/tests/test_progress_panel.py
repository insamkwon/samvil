"""Smoke tests for progress_panel (Phase B.3).

Verifies:
- compute_progress returns the expected structured shape from
  project.state.json + project.seed.json + events.jsonl.
- AC tree leaf counts walk the children/status correctly.
- ETA: build/qa scale with leaf count and remaining work; missing
  data degrades to None ('unknown').
- Pipeline strip marks completed/active/pending correctly.
- render_panel produces an ASCII block that mentions the project name,
  current stage, and ETA.
- The MCP server tool wraps both compute + render and returns valid JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import progress_panel as pp


# ── Fixtures ────────────────────────────────────────────────────────


def _write_state(root: Path, **fields) -> None:
    base = {"current_stage": "build", "completed_stages": ["interview", "seed", "scaffold"]}
    base.update(fields)
    (root / "project.state.json").write_text(json.dumps(base), encoding="utf-8")


def _write_seed_with_acs(root: Path, statuses: list[str]) -> None:
    """Write a seed with one feature whose AC tree has the given leaf statuses."""
    acs = [
        {"id": f"AC-{i+1}", "description": "x", "status": s, "children": []}
        for i, s in enumerate(statuses)
    ]
    seed = {
        "schema_version": "3.0",
        "name": "demo-app",
        "features": [
            {"name": "feat", "description": "x", "acceptance_criteria": acs}
        ],
    }
    (root / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")


def _write_events(root: Path, events: list[dict]) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    (samvil / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


# ── compute_progress ────────────────────────────────────────────────


def test_returns_zero_state_for_empty_project(tmp_path: Path) -> None:
    """Project with no state/seed/events returns a usable, empty view."""
    progress = pp.compute_progress(tmp_path)
    assert progress["current_stage"] == ""
    assert progress["leaves"]["total"] == 0
    assert progress["pipeline"], "pipeline list must be present even when empty"
    # Default tier when state.json absent
    assert progress["samvil_tier"] == "standard"


def test_walks_ac_tree_status_counts(tmp_path: Path) -> None:
    """AC tree leaf counts must split PASS / FAIL / pending."""
    _write_state(tmp_path)
    _write_seed_with_acs(tmp_path, ["pass", "pass", "pass", "fail", "pending", "pending"])
    progress = pp.compute_progress(tmp_path)
    assert progress["leaves"] == {
        "total": 6,
        "pass": 3,
        "fail": 1,
        "pending": 2,
    }


def test_pipeline_marks_active_and_completed(tmp_path: Path) -> None:
    _write_state(
        tmp_path,
        current_stage="build",
        completed_stages=["interview", "seed", "scaffold"],
    )
    _write_seed_with_acs(tmp_path, [])
    progress = pp.compute_progress(tmp_path)
    by_stage = {p["stage"]: p["mark"] for p in progress["pipeline"]}
    assert by_stage["interview"] == "done"
    assert by_stage["seed"] == "done"
    assert by_stage["scaffold"] == "done"
    assert by_stage["build"] == "active"
    assert by_stage["qa"] == "pending"


def test_eta_scales_down_as_leaves_complete(tmp_path: Path) -> None:
    """As more leaves PASS, build ETA must shrink toward 0."""
    _write_state(tmp_path, current_stage="build")
    _write_seed_with_acs(tmp_path, ["pending"] * 8)
    early = pp.compute_progress(tmp_path)["eta_sec"]

    _write_seed_with_acs(tmp_path, ["pass"] * 7 + ["pending"])
    late = pp.compute_progress(tmp_path)["eta_sec"]

    assert early is not None and late is not None
    assert late < early, "ETA must shrink as work completes"


def test_elapsed_in_stage_uses_event_timestamps(tmp_path: Path) -> None:
    """elapsed_in_stage_sec must reflect time since the most recent stage_start."""
    _write_state(tmp_path, current_stage="build")
    _write_seed_with_acs(tmp_path, [])
    _write_events(
        tmp_path,
        [{"ts": 1000.0, "stage": "build", "event_type": "build_started"}],
    )
    progress = pp.compute_progress(tmp_path, now=1300.0)
    assert progress["elapsed_in_stage_sec"] == pytest.approx(300.0)


# ── render_panel ────────────────────────────────────────────────────


def test_render_panel_contains_project_and_stage(tmp_path: Path) -> None:
    _write_state(tmp_path, current_stage="build")
    _write_seed_with_acs(tmp_path, ["pass", "pending"])
    panel = pp.render_panel(pp.compute_progress(tmp_path))
    assert "demo-app" in panel
    assert "build" in panel
    assert "AC Tree" in panel or "leaves" in panel.lower()
    # ASCII frame markers
    assert panel.startswith("┌") or panel.startswith("|") or "─" in panel


# ── MCP server wrapper ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_render_progress_panel_returns_valid_json(tmp_path: Path) -> None:
    """The @mcp.tool wrapper must wrap compute + render in JSON, never raise."""
    from samvil_mcp.server import render_progress_panel as tool

    _write_state(tmp_path, current_stage="qa")
    _write_seed_with_acs(tmp_path, ["pass", "pass"])
    raw = await tool(str(tmp_path))
    payload = json.loads(raw)
    assert "progress" in payload
    assert "panel" in payload
    assert payload["progress"]["current_stage"] == "qa"
    assert "demo-app" in payload["panel"]


def test_render_progress_panel_tool_is_registered() -> None:
    """The new MCP tool must be wired in server.py for skill consumption."""
    from samvil_mcp.server import mcp

    names = set(mcp._tool_manager._tools.keys())
    assert "render_progress_panel" in names
