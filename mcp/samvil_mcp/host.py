"""Host capability declarations for SAMVIL v3.3.

SAMVIL skills should not hard-code Claude Code runtime behavior. This module
declares host differences as data so a thin skill can decide how to chain,
handoff, and degrade across Claude Code, Codex CLI, OpenCode, or a generic host.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

HOST_NAMES: tuple[str, ...] = ("claude_code", "codex_cli", "opencode", "generic")


@dataclass(frozen=True)
class HostCapability:
    name: str
    skill_invocation: str
    parallel_agents: bool
    mcp_tools: bool
    file_marker_handoff: bool
    browser_preview: bool
    native_task_update: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["chain_via"] = chain_strategy(self)
        return data


_CAPABILITIES: dict[str, HostCapability] = {
    "claude_code": HostCapability(
        name="claude_code",
        skill_invocation="skill_tool",
        parallel_agents=True,
        mcp_tools=True,
        file_marker_handoff=True,
        browser_preview=False,
        native_task_update=True,
        notes=[
            "Can invoke the next SAMVIL skill directly.",
            "Can use file markers as fallback for portability.",
        ],
    ),
    "codex_cli": HostCapability(
        name="codex_cli",
        skill_invocation="manual",
        parallel_agents=False,
        mcp_tools=True,
        file_marker_handoff=True,
        browser_preview=True,
        native_task_update=False,
        notes=[
            "Prefer MCP tools plus explicit file markers.",
            "Next skill should be resumed by reading .samvil/next-skill.json.",
        ],
    ),
    "opencode": HostCapability(
        name="opencode",
        skill_invocation="manual",
        parallel_agents=False,
        mcp_tools=True,
        file_marker_handoff=True,
        browser_preview=False,
        native_task_update=False,
        notes=[
            "Do not assume Claude-style Skill tool availability.",
            "Use .samvil/next-skill.json for portable chaining.",
        ],
    ),
    "generic": HostCapability(
        name="generic",
        skill_invocation="manual",
        parallel_agents=False,
        mcp_tools=False,
        file_marker_handoff=True,
        browser_preview=False,
        native_task_update=False,
        notes=[
            "Portable fallback with no runtime-specific tool assumptions.",
            "Use files as the handoff boundary.",
        ],
    ),
}


def resolve_host_capability(host_name: str | None = None) -> HostCapability:
    """Resolve a host name to a capability declaration."""
    key = (host_name or "").strip().lower().replace("-", "_")
    return _CAPABILITIES.get(key, _CAPABILITIES["generic"])


def chain_strategy(host: HostCapability) -> str:
    """Return how a skill should chain to the next SAMVIL skill."""
    if host.skill_invocation == "skill_tool":
        return "skill_tool"
    if host.file_marker_handoff:
        return "file_marker"
    return "manual"
