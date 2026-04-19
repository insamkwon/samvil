"""v3.0.0 EventType enum coverage — every type emitted by skills must be
accepted by save_event without raising ValueError."""

import asyncio
import json

import pytest

from samvil_mcp.models import EventType
from samvil_mcp.server import create_session, save_event


V3_EVENT_TYPES = [
    # Pre-v3 events that were also missing from the enum
    "ac_satisfied_externally",
    "build_feature_start",
    "build_feature_success",
    "build_feature_fail",
    "build_stage_complete",
    "fix_applied",
    "stage_change",
    "stall_detected",
    "stall_abandoned",
    "evolve_gen",
    "retro_complete",
    # v3 net-new
    "ac_leaf_complete",
    "ac_verdict",
    "feature_tree_start",
    "feature_tree_complete",
    "seed_migrated",
    "dependency_plan_built",
    "rate_budget_summary",
    "rate_budget_starved",
    "rate_budget_stale_recovery",
    "pm_seed_complete",
    "pm_seed_converted",
    "tier_missing",
]


@pytest.mark.parametrize("name", V3_EVENT_TYPES)
def test_event_type_enum_accepts_v3_name(name):
    assert EventType(name).value == name


def test_save_event_accepts_every_v3_type(tmp_path, monkeypatch):
    """save_event must not silently fail on any v3 event type."""
    # Use isolated DB for the test
    from samvil_mcp import server as srv
    monkeypatch.setattr(srv, "DB_PATH", tmp_path / "samvil.db")
    monkeypatch.setattr(srv, "_store", None)

    async def runner():
        sess_json = await create_session("v3-event-test", "standard")
        sess = json.loads(sess_json)
        sid = sess["session_id"]
        for name in V3_EVENT_TYPES:
            out = await save_event(sid, name, "build", json.dumps({"k": "v"}))
            res = json.loads(out)
            assert "error" not in res, f"{name}: {res.get('error')}"
            assert res.get("saved") is True or "id" in res

    asyncio.run(runner())
