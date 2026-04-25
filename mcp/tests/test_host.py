"""Unit tests for v3.3 HostCapability resolver."""

from __future__ import annotations

from samvil_mcp.host import (
    HOST_NAMES,
    HostCapability,
    chain_strategy,
    resolve_host_capability,
)


def test_host_names_are_explicit() -> None:
    assert HOST_NAMES == ("claude_code", "codex_cli", "opencode", "generic")


def test_claude_code_supports_skill_tool_chaining() -> None:
    cap = resolve_host_capability("claude_code")
    assert cap.name == "claude_code"
    assert cap.skill_invocation == "skill_tool"
    assert cap.parallel_agents is True
    assert chain_strategy(cap) == "skill_tool"


def test_codex_cli_uses_file_marker_chain() -> None:
    cap = resolve_host_capability("codex_cli")
    assert cap.name == "codex_cli"
    assert cap.skill_invocation == "manual"
    assert cap.file_marker_handoff is True
    assert chain_strategy(cap) == "file_marker"


def test_opencode_uses_file_marker_chain() -> None:
    cap = resolve_host_capability("opencode")
    assert cap.name == "opencode"
    assert cap.skill_invocation == "manual"
    assert chain_strategy(cap) == "file_marker"


def test_unknown_host_falls_back_to_generic() -> None:
    cap = resolve_host_capability("something-new")
    assert cap.name == "generic"
    assert cap.file_marker_handoff is True
    assert chain_strategy(cap) == "file_marker"


def test_empty_host_defaults_to_generic() -> None:
    assert resolve_host_capability(None).name == "generic"
    assert resolve_host_capability("").name == "generic"


def test_host_capability_serializes_without_enum_leakage() -> None:
    cap = HostCapability(
        name="test",
        skill_invocation="manual",
        parallel_agents=False,
        mcp_tools=True,
        file_marker_handoff=True,
        browser_preview=False,
        native_task_update=False,
        notes=["portable"],
    )

    assert cap.to_dict() == {
        "name": "test",
        "skill_invocation": "manual",
        "parallel_agents": False,
        "mcp_tools": True,
        "file_marker_handoff": True,
        "browser_preview": False,
        "native_task_update": False,
        "notes": ["portable"],
        "chain_via": "file_marker",
    }
