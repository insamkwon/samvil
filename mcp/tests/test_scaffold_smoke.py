"""Smoke tests for samvil-scaffold (T4.7 ultra-thin migration).

The samvil-scaffold skill is intentionally host-bound: it shells out to
`npx create-next-app`, `npm create vite`, `npm create astro`,
`npx create-expo-app`, `python3 -m venv`, `npm init`, `npx shadcn init`,
`npx playwright install`, etc. None of those move into MCP — graceful
degradation against host failures (P8) requires the skill body to keep
them.

What CAN be machine-pinned, and is pinned here, is the new
`evaluate_scaffold_target` MCP tool the thin skill delegates to. It owns:

- Stack identification (seed.tech_stack.framework → catalog key).
- Per-framework CLI command catalog with `<seed.name>` substitution.
- Pinned-version inventory pulled from `references/dependency-matrix.json`.
- Post-install steps the skill renders as a checklist.
- Sanity-check rules for Phase A.6 (file existence + Tailwind v3/v4
  overwrite verification).
- Build-verification command + log-path per stack (INV-2).
- Existing-project detection (incremental scaffold path).

Skill-body behaviors that stay in CC and aren't covered here:
- Actually running the CLI commands.
- Rewriting `app/layout.tsx`, `tailwind.config.ts`, `app/globals.css`
  to HSL v3 form after `shadcn init` overwrites with v4 oklch.
- AskUserQuestion when sanity checks fail.
- Writing `.samvil/build.log`, `.samvil/handoff.md`, updating state.
- Chain into samvil-build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import scaffold_targets


# ── Fixtures ───────────────────────────────────────────────────


def _write_seed(root: Path, **overrides) -> None:
    seed = {
        "schema_version": "3.0",
        "name": "demo-app",
        "vision": "demo vision",
        "solution_type": "web-app",
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {"primary_screen": "/"},
        "features": [
            {
                "name": "auth",
                "description": "auth feature",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "sign in", "children": []},
                ],
            }
        ],
    }
    seed.update(overrides)
    (root / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")


# ── Catalog completeness (1) ──────────────────────────────────


def test_catalog_covers_all_seven_supported_frameworks() -> None:
    """Every documented framework (stable + planned) must be in the catalog."""
    expected_stable = {
        "nextjs",
        "vite-react",
        "astro",
        "phaser",
        "expo",
        "python-script",
        "node-script",
        "cc-skill",
    }
    expected_planned = {"nuxt", "sveltekit"}
    keys = set(scaffold_targets.SCAFFOLD_CATALOG.keys())
    assert expected_stable <= keys, (
        f"missing stable: {expected_stable - keys}"
    )
    assert expected_planned <= keys, (
        f"missing planned: {expected_planned - keys}"
    )


def test_catalog_entry_shape_per_framework() -> None:
    """Every entry must carry the columns the skill renders."""
    required_fields = {
        "label",
        "category",
        "matrix_key",
        "cli_command_template",
        "post_install_steps",
        "sanity_checks",
        "build_command",
        "build_log_path",
        "version_check_keys",
        "env_vars_needed",
        "status",
    }
    for fw, entry in scaffold_targets.SCAFFOLD_CATALOG.items():
        missing = required_fields - set(entry)
        assert not missing, f"{fw} missing fields: {missing}"


def test_catalog_status_is_stable_or_planned() -> None:
    """status must be one of the two known values."""
    for fw, entry in scaffold_targets.SCAFFOLD_CATALOG.items():
        assert entry["status"] in {"stable", "planned"}, (
            f"{fw} has invalid status: {entry['status']!r}"
        )


def test_planned_entries_carry_fallback_framework() -> None:
    """Planned frameworks must declare which stack to fall back to."""
    for fw, entry in scaffold_targets.SCAFFOLD_CATALOG.items():
        if entry["status"] == "planned":
            assert "fallback_framework" in entry, (
                f"{fw} missing fallback_framework"
            )
            assert entry["fallback_framework"] in scaffold_targets.SCAFFOLD_CATALOG, (
                f"{fw} fallback {entry['fallback_framework']!r} not in catalog"
            )


def test_catalog_categories_are_valid() -> None:
    """category drives the skill's per-`solution_type` Output Format §."""
    valid = {"web", "game", "mobile", "automation"}
    for fw, entry in scaffold_targets.SCAFFOLD_CATALOG.items():
        assert entry["category"] in valid, (
            f"{fw} has invalid category: {entry['category']!r}"
        )


# ── CLI command shape (2) ─────────────────────────────────────


def test_stable_cli_commands_substitute_seed_name() -> None:
    """Templates with <seed.name> must substitute correctly."""
    for fw, entry in scaffold_targets.SCAFFOLD_CATALOG.items():
        if entry["status"] != "stable":
            continue
        if "<seed.name>" in entry["cli_command_template"]:
            substituted = scaffold_targets._substitute_seed_name(
                entry["cli_command_template"], "demo-app"
            )
            assert "<seed.name>" not in substituted, (
                f"{fw}: substitution failed: {substituted}"
            )
            assert "demo-app" in substituted, (
                f"{fw}: seed name not present after sub"
            )


def test_web_clis_use_pinned_npm_or_npx() -> None:
    """Web stacks (Next/Vite/Astro) must invoke npm or npx with a version pin."""
    for fw in ("nextjs", "vite-react", "astro"):
        cli = scaffold_targets.SCAFFOLD_CATALOG[fw]["cli_command_template"]
        assert cli.split()[0] in {"npx", "npm"}, (
            f"{fw} CLI must start with npx or npm: {cli}"
        )
        assert "@" in cli and any(c.isdigit() for c in cli), (
            f"{fw} CLI must include a pinned version: {cli}"
        )


def test_automation_cli_creates_directory_skeleton() -> None:
    """python-script and node-script must create src/fixtures/tests dirs."""
    for fw in ("python-script", "node-script"):
        cli = scaffold_targets.SCAFFOLD_CATALOG[fw]["cli_command_template"]
        assert "mkdir -p" in cli, f"{fw} must mkdir its skeleton"
        assert "src" in cli and "fixtures" in cli and "tests" in cli, (
            f"{fw} skeleton incomplete: {cli}"
        )


# ── Version pins (3) ──────────────────────────────────────────


def test_dependency_matrix_loads() -> None:
    """references/dependency-matrix.json must be a non-empty dict."""
    matrix = scaffold_targets._load_dependency_matrix()
    assert isinstance(matrix, dict)
    assert "nextjs14" in matrix, "matrix is empty or missing nextjs14"


def test_version_pins_extracted_for_nextjs(tmp_path: Path) -> None:
    """The pinned next/react/tailwind versions must surface in the report."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    pins = result["version_pins"]
    # Matrix pins next@14.2.35 etc. The exact values may evolve, but presence
    # is non-negotiable: scaffold without pins is the regression we're guarding.
    assert pins, "expected at least some version pins for nextjs"
    assert "next" in pins, f"expected 'next' pin, got {sorted(pins.keys())}"


def test_version_pins_handle_scoped_tailwindcss_vite(tmp_path: Path) -> None:
    """vite-react must surface the @tailwindcss/vite scoped pin."""
    _write_seed(tmp_path, tech_stack={"framework": "vite-react"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    pins = result["version_pins"]
    # tailwindcss_vite is the matrix key for the @tailwindcss/vite scoped package.
    # We accept either form; the skill consumes the value, not the key.
    has_vite_tailwind = any(
        "tailwindcss" in k and "vite" in k.replace("-", "_")
        for k in pins
    )
    assert has_vite_tailwind, (
        f"expected @tailwindcss/vite pin in {sorted(pins.keys())}"
    )


# ── Sanity check rules (4) ────────────────────────────────────


def test_sanity_checks_for_nextjs_include_tailwind_overwrite_guard() -> None:
    """The Tailwind v3 vs v4 overwrite check must be in nextjs sanity rules.

    This is the regression class the legacy skill calls out repeatedly:
    `shadcn init` rewrites globals.css and tailwind.config to oklch v4
    syntax, which breaks the HSL v3 build. The sanity check must enforce
    the v3 form remains.
    """
    checks = scaffold_targets.SCAFFOLD_CATALOG["nextjs"]["sanity_checks"]
    has_globals_check = any(
        c.get("path") == "app/globals.css"
        and c.get("must_contain") == "@tailwind base"
        for c in checks
    )
    has_hsl_check = any(
        c.get("path") == "tailwind.config.ts"
        and c.get("must_contain") == "hsl(var(--"
        for c in checks
    )
    assert has_globals_check, "missing @tailwind base check on globals.css"
    assert has_hsl_check, "missing hsl(var(-- check on tailwind.config.ts"


def test_sanity_checks_evaluate_passes_when_files_present(tmp_path: Path) -> None:
    """evaluate_sanity_checks should report all_passed=True when files exist."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("export default function P() { return null }", encoding="utf-8")
    (tmp_path / "app" / "globals.css").write_text(
        "@tailwind base;\n@tailwind components;\n", encoding="utf-8"
    )

    result = scaffold_targets.evaluate_sanity_checks(
        tmp_path,
        [
            {"path": "package.json", "required": True},
            {"path": "app/page.tsx", "required": True},
            {"path": "app/globals.css", "must_contain": "@tailwind base"},
        ],
    )
    assert result["all_passed"] is True, result
    assert result["failures"] == []


def test_sanity_checks_detect_oklch_overwrite(tmp_path: Path) -> None:
    """If shadcn rewrites globals.css to v4 oklch, the check must fail."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "globals.css").write_text(
        '@import "tailwindcss";\n@layer base { :root { --foo: oklch(...) } }\n',
        encoding="utf-8",
    )
    result = scaffold_targets.evaluate_sanity_checks(
        tmp_path,
        [{"path": "app/globals.css", "must_contain": "@tailwind base"}],
    )
    assert result["all_passed"] is False
    assert len(result["failures"]) == 1
    assert "missing" in result["failures"][0]["reason"]


def test_sanity_checks_report_missing_file(tmp_path: Path) -> None:
    """A required file that does not exist must surface as a failure."""
    result = scaffold_targets.evaluate_sanity_checks(
        tmp_path,
        [{"path": "package.json", "required": True}],
    )
    assert result["all_passed"] is False
    assert result["failures"][0]["reason"] == "missing"


# ── Existing-project detection (5) ────────────────────────────


def test_detect_existing_project_via_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    info = scaffold_targets.detect_existing_project(tmp_path)
    assert info["exists"] is True
    assert info["signal"] == "package.json"
    assert "skip full scaffold" in info["next_action"]


def test_detect_existing_project_via_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    info = scaffold_targets.detect_existing_project(tmp_path)
    assert info["exists"] is True
    assert info["signal"] == "requirements.txt"


def test_detect_existing_project_returns_zero_state_for_empty_dir(
    tmp_path: Path,
) -> None:
    info = scaffold_targets.detect_existing_project(tmp_path)
    assert info["exists"] is False
    assert info["signal"] is None
    assert "full scaffold" in info["next_action"]


# ── evaluate_scaffold_target aggregator (6) ───────────────────


def test_evaluate_picks_seed_framework_when_unpinned(tmp_path: Path) -> None:
    """seed.tech_stack.framework must be source-tagged 'seed'."""
    _write_seed(tmp_path, tech_stack={"framework": "vite-react"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["framework"] == "vite-react"
    assert result["framework_source"] == "seed"
    assert result["status"] == "stable"


def test_evaluate_argument_overrides_seed(tmp_path: Path) -> None:
    """Caller-supplied framework beats seed.tech_stack.framework."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    result = scaffold_targets.evaluate_scaffold_target(
        str(tmp_path), framework="phaser"
    )
    assert result["framework"] == "phaser"
    assert result["framework_source"] == "argument"


def test_evaluate_solution_type_default_when_seed_silent(tmp_path: Path) -> None:
    """Without tech_stack.framework, fall back to solution_type default."""
    _write_seed(tmp_path, solution_type="game", tech_stack={})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["framework"] == "phaser"
    assert result["framework_source"] == "solution_type_default"


def test_evaluate_hard_default_when_nothing_pinned(tmp_path: Path) -> None:
    """No seed at all → nextjs, source='default'."""
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["framework"] == "nextjs"
    assert result["framework_source"] == "default"


def test_evaluate_substitutes_seed_name_in_cli(tmp_path: Path) -> None:
    """The cli_command field must have <seed.name> substituted."""
    _write_seed(tmp_path, name="my-todo-app", tech_stack={"framework": "nextjs"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert "<seed.name>" not in result["cli_command"]
    assert "my-todo-app" in result["cli_command"]


def test_evaluate_planned_framework_blocks_with_fallback(tmp_path: Path) -> None:
    """nuxt/sveltekit must surface a planned-status blocker + fallback hint."""
    _write_seed(tmp_path, tech_stack={"framework": "nuxt"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["status"] == "planned"
    assert result["fallback_framework"] == "nextjs"
    assert any("planned" in b for b in result["blockers"])


def test_evaluate_unknown_framework_falls_back_with_note(tmp_path: Path) -> None:
    """An unknown framework must fall back to nextjs with a note."""
    result = scaffold_targets.evaluate_scaffold_target(
        str(tmp_path), framework="invented-framework-xyz"
    )
    assert result["framework"] == "nextjs"
    assert any("unknown framework" in n for n in result["notes"])


def test_evaluate_runs_sanity_checks_when_requested(tmp_path: Path) -> None:
    """run_sanity_checks=True must populate sanity_result."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    # Without scaffold output, sanity will fail
    result = scaffold_targets.evaluate_scaffold_target(
        str(tmp_path), run_sanity_checks=True
    )
    assert result["sanity_result"] is not None
    assert result["sanity_result"]["all_passed"] is False
    assert any("sanity-check failures" in b for b in result["blockers"])


def test_evaluate_skips_sanity_checks_by_default(tmp_path: Path) -> None:
    """Default behavior: don't run sanity (it's the skill's Phase A.6 step)."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["sanity_result"] is None


def test_evaluate_existing_project_signals_incremental(tmp_path: Path) -> None:
    """When package.json exists, existing_project.exists is True."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert result["existing_project"]["exists"] is True
    assert result["existing_project"]["signal"] == "package.json"


def test_evaluate_missing_seed_does_not_crash(tmp_path: Path) -> None:
    """INV-5 / P8: a project with no seed must still return a usable payload."""
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert "error" not in result, result
    assert result["framework"] == "nextjs"
    assert any("placeholder" in n for n in result["notes"])


def test_evaluate_accepts_inline_seed_dict(tmp_path: Path) -> None:
    """Caller may pass a pre-loaded seed dict (avoids re-reading from disk)."""
    seed = {
        "schema_version": "3.0",
        "name": "from-arg",
        "tech_stack": {"framework": "vite-react"},
        "solution_type": "web-app",
    }
    result = scaffold_targets.evaluate_scaffold_target(str(tmp_path), seed=seed)
    assert result["framework"] == "vite-react"
    assert "from-arg" in result["cli_command"]


# ── Idempotency (7) ──────────────────────────────────────────


def test_evaluate_is_idempotent(tmp_path: Path) -> None:
    """Repeated calls with the same inputs must produce identical output."""
    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})
    a = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    b = scaffold_targets.evaluate_scaffold_target(str(tmp_path))
    assert a == b


# ── Wiring on live MCP server (8) ─────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_scaffold_target_mcp_tool_returns_valid_json(
    tmp_path: Path,
) -> None:
    """The @mcp.tool wrapper must return JSON, never raise."""
    from samvil_mcp.server import evaluate_scaffold_target as tool

    _write_seed(tmp_path, tech_stack={"framework": "nextjs"})

    raw = await tool(str(tmp_path))
    payload = json.loads(raw)
    assert "error" not in payload, payload
    assert payload["framework"] == "nextjs"
    assert payload["category"] == "web"


@pytest.mark.asyncio
async def test_evaluate_scaffold_target_handles_bad_path() -> None:
    """A bogus project_path must come back as a structured payload, never raise."""
    from samvil_mcp.server import evaluate_scaffold_target as tool

    raw = await tool("/nonexistent/scaffold/path")
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    assert "framework" in payload or "error" in payload


@pytest.mark.asyncio
async def test_evaluate_scaffold_target_accepts_seed_json_string(
    tmp_path: Path,
) -> None:
    """The MCP wrapper accepts seed as a JSON string parameter."""
    from samvil_mcp.server import evaluate_scaffold_target as tool

    seed = {
        "schema_version": "3.0",
        "name": "json-arg-app",
        "tech_stack": {"framework": "astro"},
        "solution_type": "web-app",
    }
    raw = await tool(str(tmp_path), seed_json=json.dumps(seed))
    payload = json.loads(raw)
    assert payload["framework"] == "astro"
    assert "json-arg-app" in payload["cli_command"]


@pytest.mark.asyncio
async def test_evaluate_scaffold_target_rejects_invalid_seed_json(
    tmp_path: Path,
) -> None:
    """Malformed seed_json must surface a clean error string, not crash."""
    from samvil_mcp.server import evaluate_scaffold_target as tool

    raw = await tool(str(tmp_path), seed_json="not valid json {{{")
    payload = json.loads(raw)
    assert "error" in payload
    assert "invalid seed_json" in payload["error"]


def test_scaffold_skill_tool_is_registered_on_server() -> None:
    """The new T4.7 tool must be wired in server.py."""
    from samvil_mcp.server import mcp

    tool_map = mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tool_map.keys())
    assert "evaluate_scaffold_target" in names
    # save_event remains the best-effort observability sink
    assert "save_event" in names
