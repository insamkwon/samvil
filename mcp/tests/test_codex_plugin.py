"""Contract tests for the Codex-native SAMVIL plugin boundary."""

from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CODEX_MANIFEST = REPO / ".codex-plugin" / "plugin.json"
CODEX_MCP = REPO / ".codex-mcp.json"
CODEX_SKILLS = REPO / "codex" / "skills"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_codex_manifest_exposes_only_verified_relative_surfaces() -> None:
    manifest = _read_json(CODEX_MANIFEST)

    assert manifest["name"] == "samvil"
    assert manifest["skills"] == "./codex/skills/"
    assert manifest["mcpServers"] == "./.codex-mcp.json"
    assert "hooks" not in manifest
    assert "${CLAUDE_PLUGIN_ROOT}" not in CODEX_MANIFEST.read_text(encoding="utf-8")
    assert set(manifest["interface"]) == {
        "displayName",
        "shortDescription",
        "developerName",
        "category",
        "capabilities",
    }
    assert manifest["interface"]["capabilities"] == ["Interactive", "Read", "Write"]


def test_codex_mcp_launcher_is_plugin_relative() -> None:
    launcher = _read_json(CODEX_MCP)
    server = launcher["mcpServers"]["samvil-mcp"]

    assert server["cwd"] == "."
    assert server["command"] == "uvx"
    assert server["args"] == ["--from", "./mcp", "samvil-mcp"]
    serialized = CODEX_MCP.read_text(encoding="utf-8")
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


def test_codex_manifest_and_launcher_have_no_author_machine_paths() -> None:
    for path in (CODEX_MANIFEST, CODEX_MCP):
        serialized = path.read_text(encoding="utf-8")
        assert "/Users/" not in serialized
        assert "/home/" not in serialized


def test_manifest_version_matches_claude_manifest_and_mcp_package() -> None:
    codex_version = _read_json(CODEX_MANIFEST)["version"]
    claude_version = _read_json(REPO / ".claude-plugin" / "plugin.json")["version"]
    init_text = (REPO / "mcp" / "samvil_mcp" / "__init__.py").read_text(encoding="utf-8")

    assert codex_version == claude_version
    assert f'__version__ = "{codex_version}"' in init_text


def test_codex_skill_root_exposes_exactly_three_public_skills() -> None:
    assert CODEX_SKILLS.is_dir()
    assert (CODEX_SKILLS / "README.md").is_file()
    assert sorted(path.name for path in CODEX_SKILLS.iterdir() if path.is_dir()) == ["resume", "run", "status"]


def test_public_codex_skills_have_bare_names_and_shared_tools() -> None:
    for name in ("run", "resume", "status"):
        text = (CODEX_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"name: {name}" in text
    run = (CODEX_SKILLS / "run" / "SKILL.md").read_text(encoding="utf-8")
    resume = (CODEX_SKILLS / "resume" / "SKILL.md").read_text(encoding="utf-8")
    status = (CODEX_SKILLS / "status" / "SKILL.md").read_text(encoding="utf-8")
    for tool in ("get_stage_envelope", "begin_stage", "commit_stage_transition"):
        assert f"mcp__samvil_mcp__{tool}" in run
        assert f"mcp__samvil_mcp__{tool}" in resume
    assert "mcp__samvil_mcp__get_stage_envelope" in status
    assert "mcp__samvil_mcp__begin_stage" not in status
    assert "mcp__samvil_mcp__commit_stage_transition" not in status
