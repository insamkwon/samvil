"""Host Adapters — per-host skill/chaining configuration (M2).

Extends `host.py` HostCapability with concrete adapter definitions
that map SAMVIL pipeline stages to host-specific invocation patterns.

Each adapter produces the minimal configuration a host needs:
  - Command/section templates for each skill stage
  - Tool alias mappings (Read ↔ apply_patch, etc.)
  - Chain continuation format (Skill tool vs file marker)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .host import HostCapability, chain_strategy, resolve_host_capability


# ── Adapter data classes ─────────────────────────────────────────


@dataclass
class SkillMapping:
    """How a single SAMVIL skill maps to a host-specific invocation."""

    skill_name: str
    host_command: str  # e.g. "/samvil-build" or "ooo build" or section header
    description: str
    next_skill: str  # skill to chain to after this one
    required_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "host_command": self.host_command,
            "description": self.description,
            "next_skill": self.next_skill,
            "required_tools": self.required_tools,
        }


@dataclass
class HostAdapter:
    """Full adapter for a specific host environment."""

    host_name: str
    capability: HostCapability
    skill_mappings: list[SkillMapping] = field(default_factory=list)
    tool_aliases: dict[str, str] = field(default_factory=dict)
    chain_format: str = ""  # "skill_tool" | "file_marker" | "manual"
    setup_instructions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_name": self.host_name,
            "capability": self.capability.to_dict(),
            "skill_mappings": [m.to_dict() for m in self.skill_mappings],
            "tool_aliases": self.tool_aliases,
            "chain_format": self.chain_format,
            "setup_instructions": self.setup_instructions,
        }


# ── Tool alias maps ─────────────────────────────────────────────


_CLAUDE_CODE_ALIASES: dict[str, str] = {
    "Read": "Read",
    "Edit": "Edit",
    "Write": "Write",
    "Bash": "Bash",
    "Agent": "Agent",
    "Skill": "Skill",
}

_CODEX_ALIASES: dict[str, str] = {
    "Read": "apply_patch (read mode)",
    "Edit": "apply_patch",
    "Write": "apply_patch (create)",
    "Bash": "shell",
    "Agent": "N/A (serial only)",
    "Skill": "N/A (use commands/*.md)",
}

_OPENCODE_ALIASES: dict[str, str] = {
    "Read": "Read",
    "Edit": "Edit",
    "Write": "Write",
    "Bash": "Bash",
    "Agent": "subagent (if supported)",
    "Skill": "N/A (use AGENTS.md sections)",
}

_GEMINI_ALIASES: dict[str, str] = {
    "Read": "read_file / read_many_files",
    "Edit": "replace_in_file",
    "Write": "write_file",
    "Bash": "run_shell_command",
    "Agent": "subagent (via @google/gemini-cli-sdk)",
    "Skill": "N/A (use .gemini/commands/*.toml)",
}

_GENERIC_ALIASES: dict[str, str] = {
    "Read": "file read",
    "Edit": "file edit",
    "Write": "file write",
    "Bash": "shell",
    "Agent": "N/A",
    "Skill": "N/A",
}


# ── Skill chain definition (SAMVIL pipeline order) ─────────────


_SKILL_CHAIN: list[dict[str, str]] = [
    {"name": "samvil", "next": "samvil-interview"},
    {"name": "samvil-interview", "next": "samvil-seed"},
    {"name": "samvil-pm-interview", "next": "samvil-seed"},
    {"name": "samvil-seed", "next": "samvil-council"},
    {"name": "samvil-council", "next": "samvil-design"},
    {"name": "samvil-design", "next": "samvil-scaffold"},
    {"name": "samvil-scaffold", "next": "samvil-build"},
    {"name": "samvil-build", "next": "samvil-qa"},
    {"name": "samvil-qa", "next": "samvil-deploy"},
    {"name": "samvil-deploy", "next": "samvil-evolve"},
    {"name": "samvil-evolve", "next": "samvil-retro"},
    {"name": "samvil-retro", "next": ""},
    {"name": "samvil-analyze", "next": ""},
    {"name": "samvil-doctor", "next": ""},
    {"name": "samvil-update", "next": ""},
    {"name": "samvil-resume", "next": ""},
]


def _build_skill_mappings(
    host_name: str,
    command_prefix: str,
) -> list[SkillMapping]:
    """Build skill mappings for a host with a given command prefix."""
    descriptions = {
        "samvil": "Orchestrate full pipeline",
        "samvil-interview": "Engineering interview",
        "samvil-pm-interview": "PM interview",
        "samvil-seed": "Generate seed.json",
        "samvil-council": "Council review",
        "samvil-design": "Generate blueprint",
        "samvil-scaffold": "Create project skeleton",
        "samvil-build": "Build features",
        "samvil-qa": "QA verification",
        "samvil-deploy": "Deploy application",
        "samvil-evolve": "Evolve seed",
        "samvil-retro": "Retrospective",
        "samvil-analyze": "Analyze existing project",
        "samvil-doctor": "Environment diagnostic",
        "samvil-update": "Update SAMVIL",
        "samvil-resume": "Resume interrupted session",
    }
    mappings = []
    for entry in _SKILL_CHAIN:
        name = entry["name"]
        mappings.append(SkillMapping(
            skill_name=name,
            host_command=f"{command_prefix}{name}",
            description=descriptions.get(name, ""),
            next_skill=entry["next"],
        ))
    return mappings


# ── Adapter instances ─────────────────────────────────────────────


_CLAUDE_CODE_ADAPTER = HostAdapter(
    host_name="claude_code",
    capability=resolve_host_capability("claude_code"),
    skill_mappings=_build_skill_mappings("claude_code", "/samvil:"),
    tool_aliases=_CLAUDE_CODE_ALIASES,
    chain_format="skill_tool",
    setup_instructions=[
        "Install SAMVIL as a Claude Code plugin.",
        "Skills auto-register via plugin.json.",
        "Chain uses Skill tool invocation.",
    ],
)

_CODEX_ADAPTER = HostAdapter(
    host_name="codex_cli",
    capability=resolve_host_capability("codex_cli"),
    skill_mappings=_build_skill_mappings("codex_cli", "samvil "),
    tool_aliases=_CODEX_ALIASES,
    chain_format="file_marker",
    setup_instructions=[
        "Copy commands/*.md to .codex/commands/ in project root.",
        "SAMVIL MCP server must be running (stdio).",
        "Chain uses .samvil/next-skill.json file markers.",
        "Each command reads the marker and continues the pipeline.",
    ],
)

_OPENCODE_ADAPTER = HostAdapter(
    host_name="opencode",
    capability=resolve_host_capability("opencode"),
    skill_mappings=_build_skill_mappings("opencode", "samvil "),
    tool_aliases=_OPENCODE_ALIASES,
    chain_format="file_marker",
    setup_instructions=[
        "Add SAMVIL sections to AGENTS.md.",
        "SAMVIL MCP server must be running (stdio).",
        "Chain uses .samvil/next-skill.json file markers.",
        "Each section reads the marker and continues the pipeline.",
    ],
)

_GEMINI_ADAPTER = HostAdapter(
    host_name="gemini_cli",
    capability=resolve_host_capability("gemini_cli"),
    skill_mappings=_build_skill_mappings("gemini_cli", "/samvil "),
    tool_aliases=_GEMINI_ALIASES,
    chain_format="file_marker",
    setup_instructions=[
        "Copy .gemini/commands/*.toml to project .gemini/commands/.",
        "Add MCP server to settings.json mcpServers section.",
        "Context loaded from GEMINI.md or AGENTS.md.",
        "Chain uses .samvil/next-skill.json file markers.",
        "Each command reads the marker and continues the pipeline.",
    ],
)

_GENERIC_ADAPTER = HostAdapter(
    host_name="generic",
    capability=resolve_host_capability("generic"),
    skill_mappings=_build_skill_mappings("generic", "samvil "),
    tool_aliases=_GENERIC_ALIASES,
    chain_format="file_marker",
    setup_instructions=[
        "No host-specific integration available.",
        "Use MCP tools directly via stdio.",
        "Chain uses .samvil/next-skill.json file markers.",
        "Read SKILL.md files manually for stage instructions.",
    ],
)


_ADAPTERS: dict[str, HostAdapter] = {
    "claude_code": _CLAUDE_CODE_ADAPTER,
    "codex_cli": _CODEX_ADAPTER,
    "opencode": _OPENCODE_ADAPTER,
    "gemini_cli": _GEMINI_ADAPTER,
    "generic": _GENERIC_ADAPTER,
}


# ── Public API ─────────────────────────────────────────────────────


def get_adapter(host_name: str | None = None) -> dict[str, Any]:
    """Get the full adapter for a host.

    Returns HostAdapter as dict with capability, skill mappings,
    tool aliases, chain format, and setup instructions.
    """
    key = (host_name or "").strip().lower().replace("-", "_")
    adapter = _ADAPTERS.get(key, _GENERIC_ADAPTER)
    return adapter.to_dict()


def get_chain_continuation(
    host_name: str | None,
    current_skill: str,
) -> dict[str, Any]:
    """Determine how to continue after the current skill.

    Returns dict with:
      - next_skill: name of the next skill in the pipeline
      - chain_via: "skill_tool" | "file_marker" | "manual"
      - marker_path: .samvil/next-skill.json (for file_marker hosts)
      - command: host-specific command to invoke next skill
    """
    adapter = _ADAPTERS.get(
        (host_name or "").strip().lower().replace("-", "_"),
        _GENERIC_ADAPTER,
    )

    next_skill = ""
    host_command = ""
    for m in adapter.skill_mappings:
        if m.skill_name == current_skill:
            next_skill = m.next_skill
            host_command = m.host_command
            break

    return {
        "next_skill": next_skill,
        "chain_via": adapter.chain_format,
        "marker_path": ".samvil/next-skill.json",
        "command": host_command,
        "host_name": adapter.host_name,
    }


def list_adapters() -> list[dict[str, Any]]:
    """List all available host adapters (summary only)."""
    return [
        {
            "host_name": a.host_name,
            "chain_format": a.chain_format,
            "skill_count": len(a.skill_mappings),
            "mcp_tools": a.capability.mcp_tools,
            "parallel_agents": a.capability.parallel_agents,
        }
        for a in _ADAPTERS.values()
    ]
