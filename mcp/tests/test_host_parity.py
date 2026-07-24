"""Smoke tests for scripts/check-host-parity.py (Phase A.2).

Verifies the parity script:
- Passes against the current repo state.
- Detects when a Codex command's '## Auto-Proceed Policy' heading is
  removed from a mechanical-stage file (the v4.11.0 retro regression).
- Detects when a CC SKILL.md drops a host-specific core tool reference.
- Allowlist correctly suppresses intentional gaps.

Tests use a tmp clone of the relevant files to avoid mutating the
repo state.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-host-parity.py"
GENERATOR = REPO_ROOT / "scripts" / "generate-host-commands.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_script_exists_and_executable() -> None:
    assert SCRIPT.exists(), f"missing: {SCRIPT}"


def test_current_repo_state_has_parity() -> None:
    """Structural parity passes while untested execution surfaces stay visible."""
    result = _run("--strict")
    assert result.returncode == 0, f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "✓ structural host parity" in result.stdout
    assert "UNTESTED" in result.stdout
    assert "samvil-qa" in result.stdout
    assert "Codex native stage execution" in result.stdout
    assert "Gemini native stage execution" in result.stdout
    assert "SSOT command corpus contract is checked" in result.stdout


def test_fresh_codex_boot_creates_and_persists_session_before_chaining() -> None:
    command = (
        REPO_ROOT / "references" / "codex-commands" / "samvil.md"
    ).read_text(encoding="utf-8")

    assert "create_session(" in command
    assert 'project_root="${PWD}"' in command
    assert '"session_id":"<returned session_id>"' in command
    assert command.index("create_session(") < command.index("write_chain_marker(")


def test_detects_missing_auto_proceed_heading(tmp_path: Path) -> None:
    """Removing '## Auto-Proceed Policy' from samvil-evolve.md must fail strict."""
    target = REPO_ROOT / "references" / "codex-commands" / "samvil-evolve.md"
    backup = target.read_text(encoding="utf-8")
    try:
        # Replace the heading line to simulate accidental deletion
        broken = backup.replace(
            "## Auto-Proceed Policy",
            "## Removed Section",
            1,
        )
        target.write_text(broken, encoding="utf-8")

        result = _run("--strict")
        assert result.returncode == 1, (
            "parity check should fail when Auto-Proceed heading is removed"
        )
        assert "Auto-Proceed Policy" in result.stdout
        assert "samvil-evolve" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_detects_missing_core_tool_in_codex(tmp_path: Path) -> None:
    """Removing a host-specific core tool from a Codex command must fail strict."""
    target = REPO_ROOT / "references" / "codex-commands" / "samvil-build.md"
    backup = target.read_text(encoding="utf-8")
    try:
        # next_buildable_leaves is a CORE_TOOLS_CODEX entry for samvil-build
        broken = backup.replace("next_buildable_leaves", "FOO_REMOVED_TOOL")
        target.write_text(broken, encoding="utf-8")

        result = _run("--strict")
        assert result.returncode == 1, "parity must fail when core tool is gone"
        assert "next_buildable_leaves" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_detects_wrong_chain_target_in_codex_command(tmp_path: Path) -> None:
    """Replacing a concrete next_skill target must fail strict parity."""
    target = REPO_ROOT / "references" / "codex-commands" / "samvil-seed.md"
    backup = target.read_text(encoding="utf-8")
    try:
        broken = backup.replace("samvil-design", "samvil-retro")
        target.write_text(broken, encoding="utf-8")

        result = _run("--strict")

        assert result.returncode == 1
        assert "samvil-seed" in result.stdout
        assert "chain target" in result.stdout
        assert "samvil-design" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


@pytest.mark.parametrize(
    ("legacy_path", "canonical_path"),
    [
        (".samvil/project.seed.json", "root project.seed.json"),
        (".samvil/project.config.json", "root project.config.json"),
        (".samvil/project.state.json", "root project.state.json"),
        (".samvil/interview-summary.md", "root interview-summary.md"),
    ],
)
def test_detects_legacy_host_command_ssot_paths(
    legacy_path: str,
    canonical_path: str,
) -> None:
    """Host-facing commands must not reintroduce legacy .samvil SSOT paths."""
    target = REPO_ROOT / "references" / "codex-commands" / "samvil-seed.md"
    backup = target.read_text(encoding="utf-8")
    try:
        target.write_text(f"Read `{legacy_path}`.\n", encoding="utf-8")

        result = _run("--strict")

        assert result.returncode == 1
        assert legacy_path in result.stdout
        assert canonical_path in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_non_strict_mode_returns_zero_even_with_issues() -> None:
    """Without --strict, the script reports issues but still exits 0
    (suitable for non-blocking informational use)."""
    target = REPO_ROOT / "references" / "codex-commands" / "samvil-evolve.md"
    backup = target.read_text(encoding="utf-8")
    try:
        broken = backup.replace("## Auto-Proceed Policy", "## Removed", 1)
        target.write_text(broken, encoding="utf-8")
        result = _run()  # no --strict
        assert result.returncode == 0
        assert "found issues" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_allowlist_yaml_suppresses_intentional_gap(tmp_path: Path) -> None:
    """An entry in host-parity-allowlist.yaml must suppress the matching issue."""
    target_codex = REPO_ROOT / "references" / "codex-commands" / "samvil-build.md"
    allowlist = REPO_ROOT / "references" / "host-parity-allowlist.yaml"
    backup_codex = target_codex.read_text(encoding="utf-8")
    backup_allow = allowlist.read_text(encoding="utf-8")
    try:
        broken = backup_codex.replace("next_buildable_leaves", "REMOVED_TOOL_XYZ")
        target_codex.write_text(broken, encoding="utf-8")
        # Confirm the un-allowlisted version fails first
        first = _run("--strict")
        assert first.returncode == 1

        # Now add an allowlist entry and re-run
        suppressed = backup_allow + (
            "\nsamvil-build:\n"
            "  missing_in_codex:\n"
            "    - next_buildable_leaves   # why: test-only — verifies allowlist works\n"
        )
        allowlist.write_text(suppressed, encoding="utf-8")

        result = _run("--strict")
        assert result.returncode == 0, (
            f"allowlist entry should suppress the issue\nstdout:\n{result.stdout}"
        )
    finally:
        target_codex.write_text(backup_codex, encoding="utf-8")
        allowlist.write_text(backup_allow, encoding="utf-8")


def test_detects_legacy_seed_ssot_path_in_gemini_commands() -> None:
    target = REPO_ROOT / "references" / "gemini-commands" / "samvil-seed.toml"
    backup = target.read_text(encoding="utf-8")
    try:
        target.write_text(
            backup.replace("project.seed.json", ".samvil/project.seed.json", 1),
            encoding="utf-8",
        )

        result = _run("--strict")

        assert result.returncode == 1
        assert "legacy .samvil/project.seed.json" in result.stdout
        assert "references/gemini-commands/samvil-seed.toml" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_detects_missing_gemini_qa_lifecycle_contract() -> None:
    target = REPO_ROOT / "references" / "gemini-commands" / "samvil-qa.toml"
    backup = target.read_text(encoding="utf-8")
    try:
        target.write_text(
            backup.replace("materialize_qa_synthesis", "REMOVED_QA_MATERIALIZER", 1),
            encoding="utf-8",
        )

        result = _run("--strict")

        assert result.returncode == 1
        assert "Gemini QA lifecycle contract" in result.stdout
        assert "materialize_qa_synthesis" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")


def test_gemini_qa_command_matches_generator() -> None:
    spec = importlib.util.spec_from_file_location("generate_host_commands", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generated = module._gemini_template("samvil-qa", "samvil-deploy")
    actual = (
        REPO_ROOT / "references" / "gemini-commands" / "samvil-qa.toml"
    ).read_text(encoding="utf-8")

    assert generated == actual


def test_detects_legacy_seed_ssot_path_in_agents_contract() -> None:
    target = REPO_ROOT / "AGENTS.md"
    backup = target.read_text(encoding="utf-8")
    try:
        target.write_text(
            backup.replace("root `project.seed.json`", "`.samvil/project.seed.json`", 1),
            encoding="utf-8",
        )

        result = _run("--strict")

        assert result.returncode == 1
        assert "legacy .samvil/project.seed.json" in result.stdout
        assert "AGENTS.md" in result.stdout
    finally:
        target.write_text(backup, encoding="utf-8")
