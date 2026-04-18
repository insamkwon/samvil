"""JSON in/out tests for v3.0.0 MCP tool wrappers in server.py.

These don't exercise FastMCP transport; they call the async functions
directly to verify marshalling, error paths, and health logging.
"""

import asyncio
import json
from pathlib import Path

import pytest

from samvil_mcp.server import (
    analyze_ac_dependencies,
    migrate_seed,
    migrate_seed_file,
    next_buildable_leaves,
    pm_seed_to_eng_seed,
    rate_budget_acquire,
    rate_budget_release,
    rate_budget_reset,
    rate_budget_stats,
    tree_progress,
    update_leaf_status,
    validate_pm_seed,
)


def _run(coro):
    return asyncio.run(coro)


# ── Tree helpers ──────────────────────────────────────────────


def _sample_tree_json() -> str:
    return json.dumps({
        "id": "AC-1",
        "description": "auth",
        "children": [
            {"id": "AC-1.1", "description": "sign up"},
            {"id": "AC-1.2", "description": "log in"},
        ],
    })


def test_next_buildable_leaves_returns_leaves_and_count():
    out = _run(next_buildable_leaves(_sample_tree_json(), "[]", 2))
    d = json.loads(out)
    assert d["count"] == 2
    assert {l["id"] for l in d["leaves"]} == {"AC-1.1", "AC-1.2"}
    assert d["max_parallel"] == 2


def test_next_buildable_leaves_error_on_bad_json():
    out = _run(next_buildable_leaves("{not json", "[]", 2))
    d = json.loads(out)
    assert "error" in d
    assert d["count"] == 0


def test_tree_progress_reports_all_done_flag():
    out = _run(tree_progress(_sample_tree_json()))
    d = json.loads(out)
    assert d["total_leaves"] == 2
    assert d["all_done"] is False


def test_update_leaf_status_returns_tree_field_and_found_true():
    out = _run(update_leaf_status(_sample_tree_json(), "AC-1.1", "pass", "[\"components/auth/signup.tsx\"]"))
    d = json.loads(out)
    assert d["found"] is True
    assert d["status"] == "pass"
    assert d["leaf_id"] == "AC-1.1"
    # tree field is round-trip ready
    assert "tree" in d and isinstance(d["tree"], dict)
    assert "found" not in d["tree"]


def test_update_leaf_status_rejects_invalid_status():
    out = _run(update_leaf_status(_sample_tree_json(), "AC-1.1", "bogus", "[]"))
    d = json.loads(out)
    assert d["found"] is False
    assert "error" in d


def test_update_leaf_status_not_found():
    out = _run(update_leaf_status(_sample_tree_json(), "AC-9.9", "pass", "[]"))
    d = json.loads(out)
    assert d["found"] is False
    assert d["tree"] is not None  # tree still returned (unchanged)


# ── Migration ─────────────────────────────────────────────────


def test_migrate_seed_tool_emits_v3(tmp_path: Path):
    v2 = {"features": [{"name": "f", "acceptance_criteria": ["a"]}]}
    out = _run(migrate_seed(json.dumps(v2), "2", "3"))
    d = json.loads(out)
    assert d["migrated_version"] == "3.0"
    assert d["migrated"]["schema_version"] == "3.0"


def test_migrate_seed_rejects_unsupported_path():
    out = _run(migrate_seed("{}", "4", "5"))
    d = json.loads(out)
    assert "error" in d


def test_migrate_seed_file_round_trip(tmp_path: Path):
    seed_path = tmp_path / "project.seed.json"
    seed_path.write_text(json.dumps({
        "features": [{"name": "f", "acceptance_criteria": ["a"]}]
    }))
    out = _run(migrate_seed_file(str(seed_path)))
    d = json.loads(out)
    assert d["status"] == "ok"
    assert d["already_v3"] is False
    assert d["schema_version"] == "3.0"
    assert Path(d["backup_path"]).exists()


def test_migrate_seed_file_reports_missing(tmp_path: Path):
    out = _run(migrate_seed_file(str(tmp_path / "missing.json")))
    d = json.loads(out)
    assert "error" in d


# ── Dependency planning ───────────────────────────────────────


def test_analyze_ac_dependencies_returns_plan():
    acs = json.dumps([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b", "depends_on": ["A"]},
    ])
    out = _run(analyze_ac_dependencies(acs, "[]", "augment"))
    d = json.loads(out)
    assert d["total_acs"] == 2
    assert d["is_parallelizable"] is False
    assert d["execution_levels"] == [["A"], ["B"]]


def test_analyze_ac_dependencies_surfaces_cycle_error():
    acs = json.dumps([
        {"id": "A", "description": "a", "depends_on": ["B"]},
        {"id": "B", "description": "b", "depends_on": ["A"]},
    ])
    out = _run(analyze_ac_dependencies(acs, "[]", "augment"))
    d = json.loads(out)
    assert "error" in d
    assert "Cycle" in d["error"]


# ── Rate budget ───────────────────────────────────────────────


def test_rate_budget_lifecycle(tmp_path: Path):
    p = str(tmp_path / "rb.jsonl")
    a = json.loads(_run(rate_budget_acquire(p, "w1", 2)))
    assert a["acquired"] is True
    s = json.loads(_run(rate_budget_stats(p)))
    assert s["active"] == 1
    r = json.loads(_run(rate_budget_release(p, "w1")))
    assert r["released"] is True
    reset_out = json.loads(_run(rate_budget_reset(p)))
    assert reset_out["reset"] is True


def test_rate_budget_exhausts(tmp_path: Path):
    p = str(tmp_path / "rb.jsonl")
    _run(rate_budget_acquire(p, "w1", 1))
    second = json.loads(_run(rate_budget_acquire(p, "w2", 1)))
    assert second["acquired"] is False


# ── PM seed ───────────────────────────────────────────────────


def _valid_pm_json() -> str:
    return json.dumps({
        "name": "app",
        "vision": "vision",
        "epics": [{
            "id": "E1", "title": "t",
            "tasks": [{
                "id": "T1.1", "description": "d",
                "acceptance_criteria": [{"id": "AC-1.1.1", "description": "x"}]
            }]
        }],
    })


def test_validate_pm_seed_tool_ok():
    out = _run(validate_pm_seed(_valid_pm_json()))
    d = json.loads(out)
    assert d["valid"] is True
    assert d["errors"] == []


def test_validate_pm_seed_tool_reports_errors():
    out = _run(validate_pm_seed(json.dumps({"epics": []})))
    d = json.loads(out)
    assert d["valid"] is False
    assert d["errors"]


def test_pm_seed_to_eng_seed_tool_roundtrips_to_validate_seed():
    out = _run(pm_seed_to_eng_seed(_valid_pm_json(), "{}"))
    eng = json.loads(out)
    assert eng["schema_version"] == "3.0"
    # Downstream validation must accept the default-filled seed
    from samvil_mcp.seed_manager import validate_seed
    v = validate_seed(eng)
    assert v["valid"] is True, v["errors"]


def test_pm_seed_to_eng_seed_tool_accepts_defaults_override():
    defaults = json.dumps({"solution_type": "dashboard", "tech_stack": {"framework": "vite-react"}})
    out = _run(pm_seed_to_eng_seed(_valid_pm_json(), defaults))
    eng = json.loads(out)
    assert eng["solution_type"] == "dashboard"
    assert eng["tech_stack"]["framework"] == "vite-react"
