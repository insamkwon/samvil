"""Tests for host_adapters module (M2 Multi-host)."""

import json
import pytest

from samvil_mcp.host_adapters import (
    HostAdapter,
    SkillMapping,
    get_adapter,
    get_chain_continuation,
    list_adapters,
    _SKILL_CHAIN,
    _CLAUDE_CODE_ADAPTER,
    _CODEX_ADAPTER,
    _OPENCODE_ADAPTER,
    _GENERIC_ADAPTER,
    _CLAUDE_CODE_ALIASES,
    _CODEX_ALIASES,
    _OPENCODE_ALIASES,
    _GEMINI_ALIASES,
    _GEMINI_ADAPTER,
    _GENERIC_ALIASES,
)


class TestSkillMapping:
    def test_to_dict(self):
        m = SkillMapping(
            skill_name="samvil-build",
            host_command="/samvil:samvil-build",
            description="Build features",
            next_skill="samvil-qa",
            required_tools=["Read", "Edit", "Bash"],
        )
        d = m.to_dict()
        assert d["skill_name"] == "samvil-build"
        assert d["next_skill"] == "samvil-qa"
        assert len(d["required_tools"]) == 3

    def test_default_required_tools(self):
        m = SkillMapping("s", "c", "d", "n")
        assert m.required_tools == []


class TestHostAdapter:
    def test_to_dict(self):
        a = HostAdapter(
            host_name="test",
            capability=_CLAUDE_CODE_ADAPTER.capability,
            skill_mappings=[],
            tool_aliases={"Read": "Read"},
            chain_format="skill_tool",
        )
        d = a.to_dict()
        assert d["host_name"] == "test"
        assert d["chain_format"] == "skill_tool"
        assert "capability" in d

    def test_default_fields(self):
        a = HostAdapter(host_name="x", capability=_GENERIC_ADAPTER.capability)
        assert a.skill_mappings == []
        assert a.tool_aliases == {}
        assert a.setup_instructions == []


class TestGetAdapter:
    def test_claude_code(self):
        result = get_adapter("claude_code")
        assert result["host_name"] == "claude_code"
        assert result["chain_format"] == "skill_tool"
        assert len(result["skill_mappings"]) == 16

    def test_codex_cli(self):
        result = get_adapter("codex_cli")
        assert result["host_name"] == "codex_cli"
        assert result["chain_format"] == "file_marker"

    def test_opencode(self):
        result = get_adapter("opencode")
        assert result["host_name"] == "opencode"
        assert result["chain_format"] == "file_marker"

    def test_generic_fallback(self):
        result = get_adapter("unknown_host")
        assert result["host_name"] == "generic"

    def test_none_returns_generic(self):
        result = get_adapter(None)
        assert result["host_name"] == "generic"

    def test_empty_string_returns_generic(self):
        result = get_adapter("")
        assert result["host_name"] == "generic"

    def test_hyphen_to_underscore(self):
        result = get_adapter("claude-code")
        assert result["host_name"] == "claude_code"

    def test_case_insensitive(self):
        result = get_adapter("CLAUDE_CODE")
        assert result["host_name"] == "claude_code"


class TestGetChainContinuation:
    def test_build_to_qa(self):
        result = get_chain_continuation("claude_code", "samvil-build")
        assert result["next_skill"] == "samvil-qa"
        assert result["chain_via"] == "skill_tool"

    def test_last_skill_empty_next(self):
        result = get_chain_continuation("claude_code", "samvil-retro")
        assert result["next_skill"] == ""

    def test_terminal_skills(self):
        for skill in ["samvil-analyze", "samvil-doctor", "samvil-update"]:
            result = get_chain_continuation("claude_code", skill)
            assert result["next_skill"] == ""

    def test_codex_file_marker(self):
        result = get_chain_continuation("codex_cli", "samvil-build")
        assert result["chain_via"] == "file_marker"
        assert result["marker_path"] == ".samvil/next-skill.json"

    def test_unknown_skill_empty(self):
        result = get_chain_continuation("claude_code", "nonexistent")
        assert result["next_skill"] == ""

    def test_generic_host(self):
        result = get_chain_continuation("generic", "samvil-seed")
        assert result["next_skill"] == "samvil-council"
        assert result["chain_via"] == "file_marker"

    def test_host_name_in_result(self):
        result = get_chain_continuation("claude_code", "samvil-build")
        assert result["host_name"] == "claude_code"


class TestListAdapters:
    def test_returns_five(self):
        result = list_adapters()
        assert len(result) == 5

    def test_adapter_summaries(self):
        result = list_adapters()
        names = {a["host_name"] for a in result}
        assert names == {"claude_code", "codex_cli", "opencode", "gemini_cli", "generic"}

    def test_each_has_required_fields(self):
        for a in list_adapters():
            assert "host_name" in a
            assert "chain_format" in a
            assert "skill_count" in a
            assert "mcp_tools" in a
            assert "parallel_agents" in a
            assert a["skill_count"] == 16


class TestSkillChain:
    def test_chain_has_16_entries(self):
        assert len(_SKILL_CHAIN) == 16

    def test_chain_starts_with_samvil(self):
        assert _SKILL_CHAIN[0]["name"] == "samvil"

    def test_chain_ends_with_update(self):
        last_names = {_SKILL_CHAIN[i]["name"] for i in range(11, 16)}
        assert "samvil-retro" in last_names
        assert "samvil-update" in last_names

    def test_pipeline_sequence(self):
        pipeline = ["samvil", "samvil-interview", "samvil-pm-interview",
                     "samvil-seed", "samvil-council", "samvil-design",
                     "samvil-scaffold", "samvil-build", "samvil-qa",
                     "samvil-deploy", "samvil-evolve", "samvil-retro"]
        for i, expected in enumerate(pipeline):
            assert _SKILL_CHAIN[i]["name"] == expected

    def test_next_links_consistent(self):
        names = {e["name"] for e in _SKILL_CHAIN}
        for entry in _SKILL_CHAIN:
            nxt = entry["next"]
            if nxt:
                assert nxt in names, f"{entry['name']} → {nxt} not in chain"


class TestToolAliases:
    def test_claude_code_has_all_core_tools(self):
        for tool in ["Read", "Edit", "Write", "Bash", "Agent", "Skill"]:
            assert tool in _CLAUDE_CODE_ALIASES

    def test_codex_marks_agent_na(self):
        assert "N/A" in _CODEX_ALIASES["Agent"]

    def test_opencode_agent_conditional(self):
        assert "subagent" in _OPENCODE_ALIASES["Agent"]

    def test_gemini_has_core_tools(self):
        for tool in ["Read", "Edit", "Write", "Bash"]:
            assert tool in _GEMINI_ALIASES

    def test_gemini_read_alias(self):
        assert "read_file" in _GEMINI_ALIASES["Read"]


class TestAdapterInstances:
    def test_claude_code_skill_command_prefix(self):
        for m in _CLAUDE_CODE_ADAPTER.skill_mappings:
            assert m.host_command.startswith("/samvil:")

    def test_codex_skill_command_prefix(self):
        for m in _CODEX_ADAPTER.skill_mappings:
            assert m.host_command.startswith("samvil ")

    def test_claude_code_setup_instructions(self):
        assert len(_CLAUDE_CODE_ADAPTER.setup_instructions) > 0

    def test_codex_setup_mentions_mcp(self):
        instructions = " ".join(_CODEX_ADAPTER.setup_instructions)
        assert "MCP" in instructions

    def test_all_adapters_have_capability(self):
        for adapter in [_CLAUDE_CODE_ADAPTER, _CODEX_ADAPTER,
                        _OPENCODE_ADAPTER, _GEMINI_ADAPTER, _GENERIC_ADAPTER]:
            assert adapter.capability is not None
            assert adapter.capability.name == adapter.host_name

    def test_gemini_adapter_chain_format(self):
        assert _GEMINI_ADAPTER.chain_format == "file_marker"

    def test_gemini_adapter_parallel_agents(self):
        assert _GEMINI_ADAPTER.capability.parallel_agents is True

    def test_gemini_adapter_mcp_tools(self):
        assert _GEMINI_ADAPTER.capability.mcp_tools is True
