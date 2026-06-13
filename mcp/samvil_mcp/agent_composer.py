"""Agent prompt composition — MCP-owned single source of truth (W3.2).

Before this module, skills told the LLM to "<paste agents/<name>.md>" into
Agent tool prompts. That made agent behavior a dual-source problem: the
agent file AND the skill's inline framing both defined it, kept in sync by
hand (CLAUDE.md §Agent 사용 규칙 admitted this hazard).

compose_agent_prompt() makes the MCP layer the assembler:
  agents/<name>.md (persona)  +  context files (seed/interview/...)  +
  task block  →  final prompt string per agent.

Skills pass file *paths*; this module reads them deterministically. If an
agent file is missing the result carries it in `missing_agents` and the
skill falls back to the legacy paste path (P8, INV-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

def _resolve_agents_dir() -> Path:
    """Locate the packaged agents/ directory.

    Source-tree layout: <root>/mcp/samvil_mcp/agent_composer.py →
    parents[2] == <root>. But production runs install samvil_mcp into a
    uvx venv (site-packages), where parents[2] is lib/pythonX.Y — so
    prefer CLAUDE_PLUGIN_ROOT (set by the Claude Code plugin runtime)
    and fall back to the source-tree guess (v4.30.4 review finding).
    """
    import os as _os

    env_root = _os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if env_root:
        cand = Path(env_root) / "agents"
        if cand.is_dir():
            return cand
    return Path(__file__).resolve().parents[2] / "agents"


_AGENTS_DIR = _resolve_agents_dir()

_MAX_CONTEXT_CHARS = 24_000  # per context file, defensive cap


@dataclass
class ComposedPrompts:
    prompts: dict[str, str] = field(default_factory=dict)
    missing_agents: list[str] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    agents_dir: str = str(_AGENTS_DIR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompts": self.prompts,
            "missing_agents": self.missing_agents,
            "missing_context": self.missing_context,
            "agents_dir": self.agents_dir,
        }


def _strip_frontmatter(text: str) -> str:
    """Drop YAML frontmatter — Agent tool prompts need the body only."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def _read_capped(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if len(text) > _MAX_CONTEXT_CHARS:
        return text[:_MAX_CONTEXT_CHARS] + "\n…(truncated)"
    return text


def compose_agent_prompts(
    agent_names: list[str],
    *,
    project_root: str = ".",
    header: str = "You are {name} for SAMVIL.",
    context_files: list[str] | None = None,
    context_inline: str = "",
    task: str = "",
    agents_dir: str | Path | None = None,
) -> ComposedPrompts:
    """Compose one prompt per agent persona.

    Layout per prompt:
        <header(name)>          — skill-provided framing line
        <agents/<name>.md body> — persona, frontmatter stripped
        ## Context              — each context file under its filename
        <context_inline>        — e.g. council round-2 injection
        ## Task                 — skill-provided task + output format
    """
    result = ComposedPrompts()
    root = Path(project_root)
    # Resolve at call time, not import time — CLAUDE_PLUGIN_ROOT may be
    # set after module import in some host startup orders.
    adir = Path(agents_dir) if agents_dir else _resolve_agents_dir()
    result.agents_dir = str(adir)

    context_blocks: list[str] = []
    for rel in context_files or []:
        text = _read_capped(root / rel)
        if text is None:
            result.missing_context.append(rel)
            continue
        context_blocks.append(f"### {rel}\n{text.strip()}")

    for name in agent_names:
        body = _read_capped(adir / f"{name}.md")
        if body is None:
            result.missing_agents.append(name)
            continue
        parts = [header.format(name=name), _strip_frontmatter(body).strip()]
        if context_blocks:
            parts.append("## Context\n" + "\n\n".join(context_blocks))
        if context_inline.strip():
            parts.append(context_inline.strip())
        if task.strip():
            parts.append("## Task\n" + task.strip())
        result.prompts[name] = "\n\n".join(parts)

    return result
