"""Smoke tests for samvil-pm-interview (T3.2 ultra-thin migration).

These tests pin the behaviors that the now-ultra-thin SKILL.md delegates
to MCP. The skill body itself is mostly the user-facing Korean phase
prompts — those cannot move to MCP without losing the skill's purpose —
but every machine-checkable contract the skill relies on lives below:

- `validate_pm_seed` MCP wrapper accepts a PM seed dict, returns
  `{valid, errors}` and uses the same rules as `pm_seed.validate_pm_seed`.
- `pm_seed_to_eng_seed` MCP wrapper round-trips a complete PM interview
  (vision → users → metrics → epics → tasks → ACs) into an engineering
  seed with `schema_version: "3.0"`, `features[]` flattened from
  epics/tasks, and vision/users/metrics preserved at root.
- Conservative engineering placeholders fill missing tech_stack /
  solution_type / core_experience so `validate_seed` accepts the result
  without the PM having made engineering decisions.
- Caller-supplied `defaults_json` overrides those placeholders.
- Both MCP wrappers are registered on the live `samvil_mcp.server.mcp`.
- The wrappers degrade gracefully on bad input (return JSON error,
  don't raise — INV-5 / P8).

The Korean phase prompts and tier-routing prose stay in SKILL.md and are
validated by interactive `/samvil:samvil-pm-interview` runs.
"""

from __future__ import annotations

import json

import pytest

from samvil_mcp.pm_seed import pm_seed_to_eng_seed, validate_pm_seed


# ── Fixtures ───────────────────────────────────────────────────


def _full_pm_seed() -> dict:
    """A complete PM seed covering every interview phase."""
    return {
        "name": "habit-tracker",
        "vision": "accountability for remote workers",
        "users": [
            {"segment": "remote workers", "pain_points": ["no peers", "no streak"]},
        ],
        "metrics": [
            {"name": "D7 retention", "target": ">=40%"},
            {"name": "NPS", "target": ">=30"},
        ],
        "epics": [
            {
                "id": "E1",
                "title": "Habit CRUD",
                "tasks": [
                    {
                        "id": "T1.1",
                        "description": "Add habit",
                        "acceptance_criteria": [
                            {"id": "AC-1.1.1", "description": "user can submit name", "children": []},
                            {"id": "AC-1.1.2", "description": "duplicate name rejected", "children": []},
                        ],
                    },
                    {
                        "id": "T1.2",
                        "description": "List habits",
                        "acceptance_criteria": [
                            {"id": "AC-1.2.1", "description": "shows current week", "children": []},
                        ],
                    },
                ],
            },
            {
                "id": "E2",
                "title": "Auth",
                "tasks": [
                    {
                        "id": "T2.1",
                        "description": "Email sign in",
                        "acceptance_criteria": [
                            {"id": "AC-2.1.1", "description": "magic link works", "children": []},
                        ],
                    },
                ],
            },
        ],
    }


# ── MCP wrapper: validate_pm_seed ─────────────────────────────


@pytest.mark.asyncio
async def test_validate_pm_seed_wrapper_accepts_full_seed() -> None:
    """The @mcp.tool() wrapper must mirror pm_seed.validate_pm_seed."""
    from samvil_mcp.server import validate_pm_seed as tool

    raw = await tool(json.dumps(_full_pm_seed()))
    payload = json.loads(raw)
    assert payload["valid"] is True
    assert payload["errors"] == []


@pytest.mark.asyncio
async def test_validate_pm_seed_wrapper_returns_errors_for_missing_vision() -> None:
    from samvil_mcp.server import validate_pm_seed as tool

    bad = _full_pm_seed()
    del bad["vision"]
    payload = json.loads(await tool(json.dumps(bad)))
    assert payload["valid"] is False
    assert any("vision" in e for e in payload["errors"])


@pytest.mark.asyncio
async def test_validate_pm_seed_wrapper_handles_garbage_json() -> None:
    """INV-5 / P8: bad input returns a structured error, never crashes."""
    from samvil_mcp.server import validate_pm_seed as tool

    payload = json.loads(await tool("{not-json"))
    assert payload["valid"] is False
    assert payload["errors"], "garbage input should produce an error message"


# ── MCP wrapper: pm_seed_to_eng_seed ──────────────────────────


@pytest.mark.asyncio
async def test_pm_seed_to_eng_seed_wrapper_full_interview_roundtrip() -> None:
    """End-to-end: a finished PM interview → valid engineering seed."""
    from samvil_mcp.server import pm_seed_to_eng_seed as tool

    raw = await tool(json.dumps(_full_pm_seed()))
    eng = json.loads(raw)

    # schema + provenance preserved
    assert eng["schema_version"] == "3.0"
    assert eng["vision"].startswith("accountability")
    assert eng["users"][0]["segment"] == "remote workers"
    assert eng["metrics"][0]["name"] == "D7 retention"

    # epics × tasks flattened into features[]
    feature_names = [f["name"] for f in eng["features"]]
    assert feature_names == ["T1.1", "T1.2", "T2.1"]
    # epic title stitched into description so Build/QA can route
    assert all("/" in f["description"] for f in eng["features"])
    # AC tree leaves carried over verbatim
    assert eng["features"][0]["acceptance_criteria"][0]["id"] == "AC-1.1.1"


@pytest.mark.asyncio
async def test_pm_seed_to_eng_seed_wrapper_fills_conservative_defaults() -> None:
    """When PM hasn't decided engineering fields, placeholders unblock the chain."""
    from samvil_mcp.server import pm_seed_to_eng_seed as tool

    eng = json.loads(await tool(json.dumps(_full_pm_seed())))
    # Defaults documented in the SKILL body must hold
    assert eng["solution_type"] == "web-app"
    assert eng["tech_stack"]["framework"] == "nextjs"
    assert eng["core_experience"]["primary_screen"]  # non-empty placeholder
    # Constraints / out_of_scope deferred to Council, not left empty
    assert eng["constraints"]
    assert eng["out_of_scope"]


@pytest.mark.asyncio
async def test_pm_seed_to_eng_seed_wrapper_honors_defaults_json() -> None:
    """Caller may pre-decide engineering choices via defaults_json."""
    from samvil_mcp.server import pm_seed_to_eng_seed as tool

    overrides = {
        "solution_type": "dashboard",
        "tech_stack": {"framework": "vite-react"},
        "constraints": ["mobile breakpoint required"],
    }
    eng = json.loads(
        await tool(json.dumps(_full_pm_seed()), json.dumps(overrides))
    )
    assert eng["solution_type"] == "dashboard"
    assert eng["tech_stack"]["framework"] == "vite-react"
    assert "mobile breakpoint required" in eng["constraints"]


@pytest.mark.asyncio
async def test_pm_seed_to_eng_seed_wrapper_rejects_invalid_seed() -> None:
    """A PM seed with no ACs must not silently produce a broken eng seed.

    The wrapper is allowed to either return an error payload or surface
    the underlying ValueError; both are non-success contracts the skill
    must observe before writing project.seed.json.
    """
    from samvil_mcp.server import pm_seed_to_eng_seed as tool

    bad = _full_pm_seed()
    bad["epics"][0]["tasks"][0]["acceptance_criteria"] = []
    raw = await tool(json.dumps(bad))
    payload = json.loads(raw)
    # Either a documented error envelope or an obviously-not-a-seed payload
    assert (
        payload.get("error")
        or payload.get("valid") is False
        or "schema_version" not in payload
    ), payload


# ── Wiring on live MCP server ─────────────────────────────────


def test_pm_interview_tools_registered_on_server() -> None:
    """Both tools the thin skill calls must be wired into server.mcp."""
    from samvil_mcp.server import mcp

    tool_map = mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tool_map.keys())
    assert "validate_pm_seed" in names
    assert "pm_seed_to_eng_seed" in names
    # Sanity: the chain target events are emitted via save_event,
    # so that wrapper must exist too.
    assert "save_event" in names
