"""Tests for tests-as-deliverable spec generation (B1)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from samvil_mcp.test_deliverable import (
    feature_spec_filename,
    package_json_test_patch,
    playwright_config,
    smoke_spec,
    spec_from_acs,
)
from samvil_mcp.server import emit_ac_spec, scaffold_test_harness


def test_spec_one_test_per_ac() -> None:
    spec = spec_from_acs(
        "counter",
        [
            {
                "ac_id": "AC-1.1",
                "description": "increment increases count",
                "steps": [
                    {"action": "goto", "url": "/"},
                    {"action": "click", "role": "button", "name": "증가"},
                    {"action": "expect_text", "selector": "main", "contains": "1"},
                ],
            },
            {
                "ac_id": "AC-2.1",
                "description": "persists across reload",
                "steps": [
                    {"action": "reload"},
                    {"action": "expect_text", "selector": "main", "contains": "1"},
                ],
            },
        ],
    )
    assert spec.count("test(") == 2  # two real tests
    assert 'getByRole("button", { name: "증가" })' in spec
    assert 'toContainText("1")' in spec
    assert "import { test, expect } from '@playwright/test';" in spec


def test_korean_and_quotes_are_escaped() -> None:
    spec = spec_from_acs(
        "f",
        [
            {
                "ac_id": "AC-1",
                "description": 'has "quotes" and 한글',
                "steps": [{"action": "expect_visible", "role": "heading", "name": "제목"}],
            }
        ],
    )
    # Must be valid JS string literals — no raw unescaped quote breaking out.
    assert '\\"quotes\\"' in spec
    assert "한글" in spec


def test_empty_ac_becomes_skip_with_todo() -> None:
    spec = spec_from_acs("f", [{"ac_id": "AC-1", "description": "x", "steps": []}])
    assert "test.skip(" in spec
    assert "TODO" in spec


def test_auto_goto_injected_when_missing() -> None:
    spec = spec_from_acs(
        "f",
        [{"ac_id": "AC-1", "description": "x", "steps": [{"action": "reload"}]}],
        base_path="/app",
    )
    assert 'await page.goto("/app");' in spec


def test_console_error_helper_wired_only_when_used() -> None:
    with_console = spec_from_acs(
        "f",
        [{"ac_id": "AC-1", "description": "x", "steps": [{"action": "expect_no_console_errors"}]}],
    )
    assert "consoleErrors" in with_console
    assert "page.on('console'" in with_console
    without = spec_from_acs(
        "f",
        [{"ac_id": "AC-1", "description": "x", "steps": [{"action": "reload"}]}],
    )
    assert "consoleErrors" not in without


def test_unsupported_action_does_not_crash() -> None:
    spec = spec_from_acs(
        "f",
        [{"ac_id": "AC-1", "description": "x", "steps": [{"action": "teleport"}]}],
    )
    assert "skipped unsupported step" in spec


def test_package_json_patch_adds_test_script() -> None:
    patched = package_json_test_patch({"scripts": {"build": "vite build"}})
    assert patched["scripts"]["test"] == "playwright test"
    assert "@playwright/test" in patched["devDependencies"]


def test_package_json_patch_preserves_real_test_script() -> None:
    patched = package_json_test_patch({"scripts": {"test": "vitest run"}})
    assert patched["scripts"]["test"] == "vitest run"  # not clobbered


def test_package_json_patch_overrides_default_placeholder() -> None:
    patched = package_json_test_patch(
        {"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}
    )
    assert patched["scripts"]["test"] == "playwright test"


def test_config_and_filename() -> None:
    cfg = playwright_config("http://localhost:4173")
    assert "testDir: './tests/e2e'" in cfg
    assert "npm run build && npm run preview" in cfg
    assert "['json', { outputFile: '.samvil/test-results.json' }]" in cfg
    assert feature_spec_filename("Todo List!") == "tests/e2e/todo-list.spec.ts"


def test_smoke_spec_is_valid() -> None:
    s = smoke_spec("/")
    assert "expect_no_console_errors" not in s  # rendered, not literal
    assert "consoleErrors" in s


def test_scaffold_test_harness_writes_files(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "app", "scripts": {"build": "vite build", "preview": "vite preview"}})
    )
    result = json.loads(
        asyncio.run(scaffold_test_harness(str(tmp_path)))
    )
    assert result["status"] == "ok"
    assert (tmp_path / "playwright.config.ts").exists()
    assert (tmp_path / "tests" / "e2e" / "smoke.spec.ts").exists()
    pkg = json.loads((tmp_path / "package.json").read_text())
    assert pkg["scripts"]["test"] == "playwright test"


def test_scaffold_test_harness_wires_expo_web_server(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "mobile-app",
                "dependencies": {"expo": "~52.0.0"},
                "scripts": {"web": "expo start --web"},
            }
        )
    )

    result = json.loads(asyncio.run(scaffold_test_harness(str(tmp_path))))

    assert result["status"] == "ok"
    config = (tmp_path / "playwright.config.ts").read_text()
    assert "npx expo start --web" in config
    assert "localhost:8081" in config


def test_emit_ac_spec_writes_feature_file(tmp_path: Path) -> None:
    acs = json.dumps(
        [
            {
                "ac_id": "AC-1.1",
                "description": "click increments",
                "steps": [
                    {"action": "goto", "url": "/"},
                    {"action": "click", "role": "button", "name": "증가"},
                    {"action": "expect_text", "selector": "main", "contains": "1"},
                ],
            }
        ]
    )
    result = json.loads(asyncio.run(emit_ac_spec(str(tmp_path), "counter", acs)))
    assert result["status"] == "ok"
    assert result["spec_path"] == "tests/e2e/counter.spec.ts"
    assert result["ac_count"] == 1
    assert result["empty_acs"] == []
    assert (tmp_path / "tests" / "e2e" / "counter.spec.ts").exists()


def test_emit_ac_spec_flags_empty_acs(tmp_path: Path) -> None:
    acs = json.dumps([{"ac_id": "AC-9", "description": "untested", "steps": []}])
    result = json.loads(asyncio.run(emit_ac_spec(str(tmp_path), "f", acs)))
    assert result["empty_acs"] == ["AC-9"]


# ── A3 adversarial spec ───────────────────────────────────────────


def test_adversarial_spec_probes_buttons_and_inputs() -> None:
    from samvil_mcp.test_deliverable import adversarial_spec

    spec = adversarial_spec(["증가", "리셋"], ["#title"], base_path="/")
    assert 'getByRole("button", { name: "증가" })' in spec
    assert 'getByRole("button", { name: "리셋" })' in spec
    assert 'page.locator("#title")' in spec
    assert "'x'.repeat(2000)" in spec
    assert "await page.reload()" in spec
    assert "pageerror" in spec
    # rapid-click loop present
    assert "for (let i = 0; i < 8" in spec


def test_adversarial_spec_empty_lists_still_has_reload() -> None:
    from samvil_mcp.test_deliverable import adversarial_spec

    spec = adversarial_spec([], [], base_path="/")
    assert "reload mid-session stays stable" in spec


def test_emit_adversarial_spec_tool(tmp_path) -> None:
    import asyncio
    from samvil_mcp.server import emit_adversarial_spec

    result = json.loads(
        asyncio.run(
            emit_adversarial_spec(
                str(tmp_path), json.dumps(["증가"]), json.dumps(["#title"])
            )
        )
    )
    assert result["status"] == "ok"
    assert result["button_probes"] == 1
    assert result["input_probes"] == 1
    assert (tmp_path / "tests" / "e2e" / "adversarial.spec.ts").exists()
