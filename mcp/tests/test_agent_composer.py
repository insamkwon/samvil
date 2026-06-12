"""Tests for MCP-owned agent prompt composition (v4.30 W3.2)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from samvil_mcp.agent_composer import _AGENTS_DIR, compose_agent_prompts
from samvil_mcp.server import compose_agent_prompt


@pytest.fixture
def fake_agents(tmp_path: Path) -> Path:
    adir = tmp_path / "agents"
    adir.mkdir()
    (adir / "qa-functional.md").write_text(
        "---\nname: qa-functional\nmodel_role: judge\n---\n\n"
        "# QA Functional\nVerify each AC against actual code."
    )
    return adir


def test_compose_merges_persona_context_task(
    fake_agents: Path, tmp_path: Path
) -> None:
    (tmp_path / "project.seed.json").write_text('{"name": "todo"}')
    result = compose_agent_prompts(
        ["qa-functional"],
        project_root=str(tmp_path),
        header="You are {name} for SAMVIL QA.",
        context_files=["project.seed.json"],
        task="Return JSON verdict.",
        agents_dir=fake_agents,
    )
    prompt = result.prompts["qa-functional"]
    assert prompt.startswith("You are qa-functional for SAMVIL QA.")
    assert "model_role" not in prompt  # frontmatter stripped
    assert "Verify each AC against actual code." in prompt
    assert '### project.seed.json\n{"name": "todo"}' in prompt
    assert prompt.rstrip().endswith("Return JSON verdict.")
    assert result.missing_agents == []


def test_missing_agent_reported_not_raised(fake_agents: Path, tmp_path: Path) -> None:
    result = compose_agent_prompts(
        ["qa-functional", "no-such-agent"],
        project_root=str(tmp_path),
        agents_dir=fake_agents,
    )
    assert "qa-functional" in result.prompts
    assert result.missing_agents == ["no-such-agent"]


def test_missing_context_reported(fake_agents: Path, tmp_path: Path) -> None:
    result = compose_agent_prompts(
        ["qa-functional"],
        project_root=str(tmp_path),
        context_files=["nope.json"],
        agents_dir=fake_agents,
    )
    assert result.missing_context == ["nope.json"]
    assert "qa-functional" in result.prompts


def test_context_inline_block_included(fake_agents: Path, tmp_path: Path) -> None:
    result = compose_agent_prompts(
        ["qa-functional"],
        project_root=str(tmp_path),
        context_inline="## Round 1 Debate\n- point A",
        agents_dir=fake_agents,
    )
    assert "## Round 1 Debate" in result.prompts["qa-functional"]


def test_real_agents_dir_resolves() -> None:
    """The packaged agents/ dir must exist and contain the personas the
    skills reference."""
    assert _AGENTS_DIR.is_dir()
    for name in ("qa-functional", "qa-quality", "wonder-analyst", "product-owner"):
        assert (_AGENTS_DIR / f"{name}.md").exists(), name


def test_mcp_tool_roundtrip(tmp_path: Path) -> None:
    """Tool wrapper against the real packaged agents/ directory."""
    result = json.loads(
        asyncio.run(
            compose_agent_prompt(
                agent_names_json='["wonder-analyst"]',
                project_root=str(tmp_path),
                task="Find what surprised us.",
            )
        )
    )
    assert "wonder-analyst" in result["prompts"]
    assert result["missing_agents"] == []
    assert "Find what surprised us." in result["prompts"]["wonder-analyst"]
