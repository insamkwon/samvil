"""Smoke tests for samvil-deploy (T3.4 ultra-thin migration).

The samvil-deploy skill is intentionally host-bound: it shells out to
`vercel`, `railway`, `coolify`, `eas`, `npx gh-pages`, `crontab`, etc.
None of those move into MCP — graceful degradation against host failures
(P8) requires the skill body to keep them.

What CAN be machine-pinned, and is pinned here, is the new
`evaluate_deploy_target` MCP tool the thin skill delegates to. It owns:

- QA gate decision (qa_status must be PASS).
- Per-`solution_type` deploy-target catalog (web-app, dashboard, game,
  mobile-app, automation).
- Platform precedence: caller-pinned → seed-pinned → catalog.recommended.
- Env-var parsing from `.env.example`, including placeholder detection.
- Build-artifact existence check (`.next/` for web, `dist/` for game).
- Aggregated `ready` / `blockers` payload the skill renders.

Skill-body behaviors that stay in CC and aren't covered here:
- AskUserQuestion prompts for missing env vars and platform choice.
- Actually executing the platform deploy command.
- Writing `.samvil/deploy-info.json` and updating `project.state.json`.
- Chain into `samvil-retro`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import deploy_targets


# ── Fixtures ───────────────────────────────────────────────────


def _write_state(root: Path, qa_status: str) -> None:
    (root / "project.state.json").write_text(
        json.dumps({"qa_status": qa_status}),
        encoding="utf-8",
    )


def _write_seed(root: Path, **overrides) -> None:
    seed = {
        "schema_version": "3.0",
        "name": "demo",
        "vision": "demo vision",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {"primary_screen": "/"},
        "features": [
            {
                "name": "auth",
                "description": "auth feature",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "sign in works", "children": []},
                ],
            }
        ],
    }
    seed.update(overrides)
    (root / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")


# ── QA gate ────────────────────────────────────────────────────


def test_qa_gate_blocks_when_qa_status_missing(tmp_path: Path) -> None:
    """No qa_status in state must block deploy with a clear reason."""
    gate = deploy_targets.evaluate_qa_gate({})
    assert gate["verdict"] == "blocked"
    assert "PASS" in gate["reason"]
    assert "qa" in gate["next_action"].lower()


def test_qa_gate_passes_only_on_pass_verbatim() -> None:
    """Only `PASS` (case-insensitive) unlocks deploy."""
    assert deploy_targets.evaluate_qa_gate({"qa_status": "PASS"})["verdict"] == "pass"
    assert deploy_targets.evaluate_qa_gate({"qa_status": "pass"})["verdict"] == "pass"
    assert deploy_targets.evaluate_qa_gate({"qa_status": "REVISE"})["verdict"] == "blocked"
    assert deploy_targets.evaluate_qa_gate({"qa_status": "FAIL"})["verdict"] == "blocked"


def test_qa_gate_reads_nested_qa_dict() -> None:
    """Some pipelines write `state.qa.status` instead of `qa_status`."""
    assert (
        deploy_targets.evaluate_qa_gate({"qa": {"status": "PASS"}})["verdict"]
        == "pass"
    )
    assert (
        deploy_targets.evaluate_qa_gate({"qa": {"verdict": "PASS"}})["verdict"]
        == "pass"
    )


# ── Catalog shape (per solution_type × platforms) ─────────────


def test_catalog_covers_all_five_solution_types() -> None:
    """Every documented solution_type must have at least one platform."""
    expected = {"web-app", "dashboard", "game", "mobile-app", "automation"}
    assert set(deploy_targets.DEPLOY_CATALOG.keys()) == expected
    for stype, entries in deploy_targets.DEPLOY_CATALOG.items():
        assert entries, f"{stype} has no platforms"
        # Every entry must carry the four columns the skill renders
        for entry in entries:
            assert {"id", "label", "command", "notes"}.issubset(entry)


def test_catalog_each_solution_type_has_one_recommended() -> None:
    """The skill picks `recommended` when the seed and caller don't pin one."""
    for stype, entries in deploy_targets.DEPLOY_CATALOG.items():
        recommended = [e for e in entries if e.get("recommended")]
        assert len(recommended) == 1, (
            f"{stype} must have exactly one recommended platform "
            f"(found {len(recommended)})"
        )


# ── parse_env_example ─────────────────────────────────────────


def test_parse_env_example_missing_file_is_zero_state(tmp_path: Path) -> None:
    """A project with no .env.example must not block deploy."""
    info = deploy_targets.parse_env_example(tmp_path / ".env.example")
    assert info["exists"] is False
    assert info["required_keys"] == []
    assert info["placeholder_keys"] == []


def test_parse_env_example_detects_placeholders(tmp_path: Path) -> None:
    """Empty values and known placeholder tokens must be reported."""
    env = tmp_path / ".env.example"
    env.write_text(
        "# comment line\n"
        "API_KEY=\n"
        "SECRET=YOUR_KEY_HERE\n"
        'DATABASE_URL="postgres://user:pass@host/db"\n'
        "FILLED=real-value\n",
        encoding="utf-8",
    )
    info = deploy_targets.parse_env_example(env)
    assert info["exists"] is True
    assert set(info["required_keys"]) == {
        "API_KEY",
        "SECRET",
        "DATABASE_URL",
        "FILLED",
    }
    assert set(info["placeholder_keys"]) == {"API_KEY", "SECRET"}


# ── evaluate_deploy_target aggregator ─────────────────────────


def test_evaluate_blocks_when_qa_not_pass(tmp_path: Path) -> None:
    """End-to-end: a project with QA=FAIL must surface the gate as a blocker."""
    _write_state(tmp_path, "FAIL")
    _write_seed(tmp_path)

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["ready"] is False
    assert any("PASS" in b for b in result["blockers"])
    assert result["qa_gate"]["verdict"] == "blocked"


def test_evaluate_picks_recommended_platform_when_unpinned(tmp_path: Path) -> None:
    """Without seed.tech_stack.deploy or caller arg, the recommended wins."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="web-app")

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["selected_platform"]["id"] == "vercel"
    assert result["selected_platform"]["recommended"] is True


def test_evaluate_caller_platform_overrides_seed_pin(tmp_path: Path) -> None:
    """Caller-supplied `platform` argument beats seed.tech_stack.deploy."""
    _write_state(tmp_path, "PASS")
    _write_seed(
        tmp_path,
        solution_type="web-app",
        tech_stack={"framework": "nextjs", "deploy": "railway"},
    )

    result = deploy_targets.evaluate_deploy_target(
        str(tmp_path),
        platform="coolify",
    )
    assert result["selected_platform"]["id"] == "coolify"


def test_evaluate_seed_pin_overrides_catalog_recommended(tmp_path: Path) -> None:
    """When the seed pins a platform, that wins over `recommended`."""
    _write_state(tmp_path, "PASS")
    _write_seed(
        tmp_path,
        solution_type="web-app",
        tech_stack={"framework": "nextjs", "deploy": "railway"},
    )

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["selected_platform"]["id"] == "railway"


def test_evaluate_game_uses_dist_artifact_check(tmp_path: Path) -> None:
    """game solution_type must check `dist/`, not `.next/`."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="game")

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["build_artifact"]["checked_paths"] == ["dist"]
    # No dist/ exists yet → must surface as a blocker for non-manual platforms
    assert any("build artifact missing" in b for b in result["blockers"])


def test_evaluate_ready_when_all_gates_pass(tmp_path: Path) -> None:
    """The happy path: QA=PASS, no env placeholders, build artifact present."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="web-app")
    (tmp_path / ".next").mkdir()  # build artifact exists
    # No .env.example → zero-state, not a blocker

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["ready"] is True, result["blockers"]
    assert result["blockers"] == []


def test_evaluate_missing_seed_does_not_crash(tmp_path: Path) -> None:
    """INV-5 / P8: a project with no seed must still return a usable payload."""
    # No state, no seed
    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert "error" not in result, result
    # Falls through to web-app catalog so the skill can still render
    assert result["solution_type"] == "web-app"
    # And the QA gate naturally blocks (no qa_status anywhere)
    assert result["qa_gate"]["verdict"] == "blocked"


# ── _artifact_paths_for_framework (v3-001) ────────────────────


def test_artifact_paths_vite_react_returns_dist() -> None:
    """vite-react framework must resolve to dist/, not .next/."""
    paths = deploy_targets._artifact_paths_for_framework(
        "web-app", {"framework": "vite-react"}
    )
    assert paths == ["dist"]


def test_artifact_paths_nextjs_returns_next() -> None:
    """nextjs framework must continue to resolve to .next/."""
    paths = deploy_targets._artifact_paths_for_framework(
        "web-app", {"framework": "nextjs"}
    )
    assert paths == [".next"]


def test_artifact_paths_vite_variants_all_return_dist() -> None:
    """All Vite-family frameworks (vite, astro, sveltekit, remix) → dist/."""
    vite_like = ["vite", "vite-react", "vite-vue", "vite-svelte", "astro", "sveltekit", "remix"]
    for fw in vite_like:
        paths = deploy_targets._artifact_paths_for_framework("web-app", {"framework": fw})
        assert paths == ["dist"], f"Expected dist for framework={fw}, got {paths}"


def test_artifact_paths_version_suffix_stripped() -> None:
    """Framework pins like 'vite-react@5' must still match as vite-react."""
    paths = deploy_targets._artifact_paths_for_framework(
        "web-app", {"framework": "vite-react@5"}
    )
    assert paths == ["dist"]


def test_artifact_paths_no_tech_stack_falls_back_to_solution_type() -> None:
    """Missing tech_stack must fall back to ARTIFACT_PATHS per solution_type."""
    assert deploy_targets._artifact_paths_for_framework("web-app", None) == [".next"]
    assert deploy_targets._artifact_paths_for_framework("game", None) == ["dist"]
    assert deploy_targets._artifact_paths_for_framework("mobile-app", None) == []


def test_evaluate_vite_react_happy_path(tmp_path: Path) -> None:
    """vite-react project with dist/ present and QA PASS must be ready=True."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="web-app", tech_stack={"framework": "vite-react"})
    (tmp_path / "dist").mkdir()

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["build_artifact"]["checked_paths"] == ["dist"]
    assert result["ready"] is True, result["blockers"]


def test_evaluate_vite_react_missing_dist_is_blocker(tmp_path: Path) -> None:
    """vite-react project without dist/ must surface a build-artifact blocker."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="web-app", tech_stack={"framework": "vite-react"})
    # dist/ does NOT exist

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["build_artifact"]["checked_paths"] == ["dist"]
    assert any("build artifact missing" in b for b in result["blockers"])


def test_evaluate_nextjs_no_false_positive_with_vite_seed(tmp_path: Path) -> None:
    """A Next.js project with .next/ present must NOT be blocked as if Vite."""
    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path, solution_type="web-app", tech_stack={"framework": "nextjs"})
    (tmp_path / ".next").mkdir()

    result = deploy_targets.evaluate_deploy_target(str(tmp_path))
    assert result["build_artifact"]["checked_paths"] == [".next"]
    assert result["ready"] is True, result["blockers"]


# ── Wiring on live MCP server ─────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_deploy_target_mcp_tool_returns_valid_json(
    tmp_path: Path,
) -> None:
    """The @mcp.tool wrapper must return JSON, never raise."""
    from samvil_mcp.server import evaluate_deploy_target as tool

    _write_state(tmp_path, "PASS")
    _write_seed(tmp_path)

    raw = await tool(str(tmp_path))
    payload = json.loads(raw)
    assert "error" not in payload, payload
    assert payload["solution_type"] == "web-app"
    assert payload["qa_gate"]["verdict"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_deploy_target_handles_bad_path() -> None:
    """A bogus project_root must come back as a structured payload, never raise."""
    from samvil_mcp.server import evaluate_deploy_target as tool

    raw = await tool("/nonexistent/project/root")
    payload = json.loads(raw)
    # Either a clean fall-through (no seed, no state) or a structured error
    assert isinstance(payload, dict)
    assert "qa_gate" in payload or "error" in payload


def test_deploy_skill_tool_is_registered_on_server() -> None:
    """The new T3.4 tool must be wired in server.py."""
    from samvil_mcp.server import mcp

    tool_map = mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tool_map.keys())
    assert "evaluate_deploy_target" in names
    # save_event is used by the skill's best-effort observability lines
    assert "save_event" in names
