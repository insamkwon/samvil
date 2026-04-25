"""Integration tests for host capability MCP wrappers."""

from __future__ import annotations

import asyncio
import json

from samvil_mcp.server import host_chain_strategy, resolve_host_capability


def _run(coro):
    return asyncio.run(coro)


def test_resolve_host_capability_tool_returns_json() -> None:
    out = _run(resolve_host_capability("claude-code"))
    data = json.loads(out)
    assert data["name"] == "claude_code"
    assert data["chain_via"] == "skill_tool"
    assert data["mcp_tools"] is True


def test_resolve_host_capability_unknown_returns_generic() -> None:
    out = _run(resolve_host_capability("unknown-host"))
    data = json.loads(out)
    assert data["name"] == "generic"
    assert data["chain_via"] == "file_marker"


def test_host_chain_strategy_tool_returns_compact_strategy() -> None:
    out = _run(host_chain_strategy("codex_cli"))
    data = json.loads(out)
    assert data == {
        "host": "codex_cli",
        "chain_via": "file_marker",
        "file_marker": ".samvil/next-skill.json",
    }


def test_host_chain_strategy_claude_uses_skill_tool() -> None:
    out = _run(host_chain_strategy("claude_code"))
    data = json.loads(out)
    assert data["host"] == "claude_code"
    assert data["chain_via"] == "skill_tool"
