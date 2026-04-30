"""Smoke tests for auto_recovery (Phase C.4).

Verifies the four-action verdict matrix:
- none      → pipeline healthy / within threshold
- reentry   → stalled but under retry budget
- escalate  → retry budget exhausted (P10 user-decision)
- block     → state corruption

And the apply flag behavior: only reentry mutates state, and only
when apply=True. Dry-run callers (the default) get a verdict without
side effects.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samvil_mcp import auto_recovery


def _write_state(root: Path, **fields) -> None:
    base = {
        "current_stage": "build",
        "completed_stages": ["interview", "seed", "scaffold"],
        "stall_recovery_count": 0,
    }
    base.update(fields)
    (root / "project.state.json").write_text(
        json.dumps(base, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _iso(seconds_ago: int, *, now: datetime | None = None) -> str:
    """Return ISO timestamp at `seconds_ago` seconds before `now` (default UTC now)."""
    base = now or datetime.now(timezone.utc)
    return (base - timedelta(seconds=seconds_ago)).isoformat()


# ── action: none ─────────────────────────────────────────────────────


def test_action_none_when_within_threshold(tmp_path: Path) -> None:
    """Recent heartbeat must yield action='none'."""
    _write_state(tmp_path, last_progress_at=_iso(60))  # 1 min ago
    verdict = auto_recovery.evaluate_stuck_recovery(tmp_path, threshold_seconds=300)
    assert verdict["action"] == "none"
    assert verdict["state_dirty"] is False
    assert "continue" in verdict["next_step"].lower()


# ── action: block ────────────────────────────────────────────────────


def test_action_block_when_state_missing(tmp_path: Path) -> None:
    """Missing state.json must yield action='block', not crash."""
    verdict = auto_recovery.evaluate_stuck_recovery(tmp_path)
    assert verdict["action"] == "block"
    assert "state_missing" in verdict["reason"]


# ── action: reentry ──────────────────────────────────────────────────


def test_action_reentry_when_first_stall(tmp_path: Path) -> None:
    """5+ min stall + count=0 must recommend reentry."""
    _write_state(tmp_path, last_progress_at=_iso(400), stall_recovery_count=0)
    verdict = auto_recovery.evaluate_stuck_recovery(tmp_path, threshold_seconds=300)
    assert verdict["action"] == "reentry"
    assert verdict["stage"] == "build"
    assert verdict["recovery_count"] == 0  # not bumped (apply=False)
    assert verdict["state_dirty"] is False
    assert "samvil-build" in verdict["next_step"]


def test_apply_true_bumps_recovery_count(tmp_path: Path) -> None:
    """apply=True on reentry must persist stall_recovery_count to state.json."""
    _write_state(tmp_path, last_progress_at=_iso(400), stall_recovery_count=0)
    verdict = auto_recovery.evaluate_stuck_recovery(
        tmp_path, apply=True, threshold_seconds=300
    )
    assert verdict["action"] == "reentry"
    assert verdict["recovery_count"] == 1
    assert verdict["state_dirty"] is True

    saved = json.loads((tmp_path / "project.state.json").read_text(encoding="utf-8"))
    assert saved["stall_recovery_count"] == 1


# ── action: escalate ─────────────────────────────────────────────────


def test_action_escalate_when_retry_budget_exhausted(tmp_path: Path) -> None:
    """Once stall_recovery_count >= MAX_STALL_RETRIES, escalate to user."""
    threshold = auto_recovery.ESCALATION_THRESHOLD
    _write_state(
        tmp_path,
        last_progress_at=_iso(400),
        stall_recovery_count=threshold,
    )
    verdict = auto_recovery.evaluate_stuck_recovery(tmp_path, threshold_seconds=300)
    assert verdict["action"] == "escalate"
    assert "AskUserQuestion" in verdict["next_step"]
    assert verdict["user_message"], "must include user-facing reawake message"


def test_escalate_does_not_mutate_even_with_apply(tmp_path: Path) -> None:
    """apply=True on escalate must NOT bump count further (already exhausted)."""
    threshold = auto_recovery.ESCALATION_THRESHOLD
    _write_state(
        tmp_path,
        last_progress_at=_iso(400),
        stall_recovery_count=threshold,
    )
    verdict = auto_recovery.evaluate_stuck_recovery(
        tmp_path, apply=True, threshold_seconds=300
    )
    assert verdict["action"] == "escalate"
    assert verdict["state_dirty"] is False
    saved = json.loads((tmp_path / "project.state.json").read_text(encoding="utf-8"))
    assert saved["stall_recovery_count"] == threshold


# ── MCP server wrapper ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_evaluate_stuck_recovery_returns_json(tmp_path: Path) -> None:
    from samvil_mcp.server import evaluate_stuck_recovery as tool

    _write_state(tmp_path, last_progress_at=_iso(60))
    raw = await tool(str(tmp_path))
    payload = json.loads(raw)
    assert payload["action"] in {"none", "reentry", "escalate", "block"}


def test_evaluate_stuck_recovery_tool_is_registered() -> None:
    from samvil_mcp.server import mcp

    names = set(mcp._tool_manager._tools.keys())
    assert "evaluate_stuck_recovery" in names
