#!/usr/bin/env python3
"""Forward integrity check (v4.29.0).

Asks: do all ``mcp__samvil_mcp__<name>`` references in SKILL.md and
Codex command files resolve to actually-registered ``@mcp.tool()``
functions in ``mcp/samvil_mcp/server.py``?

The existing ``check-skill-wiring.py`` does the *reverse* — every
registered tool must be referenced in some skill (so dead tools get
caught). This script does the *forward* — every cited tool must
actually exist (so aspirational SKILL text gets caught).

Together the two scripts close the SKILL ↔ MCP synchronization loop,
applying SAMVIL's P1 (Evidence-based Assertions) to its own
documentation.

Exit codes:
    0  every reference resolves OR is in INTENTIONAL_FUTURE_REFS
    1  one or more references are unresolved

Run from repo root:
    python3 scripts/check-skill-forward-integrity.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"
CODEX_DIR = REPO / "references" / "codex-commands"
SERVER_PY = REPO / "mcp" / "samvil_mcp" / "server.py"

# Pattern for tool references in SKILL text. We match both
# ``mcp__samvil_mcp__<name>`` (Claude Code / Skill convention) and
# bare references inside backticks. We deliberately do NOT match
# ``samvil_mcp.<module>`` Python imports because those are not the
# same surface — they're internal module paths, not external MCP
# tool names.
TOOL_REF_PATTERN = re.compile(r"mcp__samvil_mcp__([a-z_][a-z0-9_]*)")

# Tools we know exist but reference deliberately *before* implementing
# them. Each entry must include a one-line rationale and a target
# release. Used sparingly — every entry here is a P1 deferral and
# needs to be cleared before the target release ships.
INTENTIONAL_FUTURE_REFS: dict[str, str] = {
    # Example shape (no actual entries right now):
    # "future_tool": "v4.30 plan — see docs/samvil-v2-roadmap.md §X",
}


def collect_registered_tools() -> set[str]:
    """Return the set of @mcp.tool() function names.

    W5.3: tools live in server.py plus extracted ``tools_*.py`` modules
    (register-pattern). Matches both ``async def`` and bare ``def``,
    indented or top-level.
    """
    sources = [SERVER_PY] + sorted(SERVER_PY.parent.glob("tools_*.py"))
    names: set[str] = set()
    for src in sources:
        content = src.read_text(encoding="utf-8")
        names.update(
            re.findall(r"@mcp\.tool\(\)\s*\n\s*(?:async\s+)?def (\w+)", content)
        )
    return names


def collect_skill_references() -> dict[str, list[tuple[Path, int, str]]]:
    """For every Skill / Codex command file, extract tool refs.

    Returns: { tool_name: [(file_path, line_no, line_text), ...] }
    """
    refs: dict[str, list[tuple[Path, int, str]]] = {}
    sources: list[Path] = []
    if SKILLS_DIR.exists():
        sources.extend(SKILLS_DIR.glob("**/SKILL.md"))
        sources.extend(SKILLS_DIR.glob("**/SKILL.legacy.md"))
    if CODEX_DIR.exists():
        sources.extend(CODEX_DIR.glob("*.md"))
    for src in sources:
        try:
            for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
                for tool in TOOL_REF_PATTERN.findall(line):
                    refs.setdefault(tool, []).append((src, lineno, line.strip()))
        except (OSError, UnicodeDecodeError):
            continue
    return refs


def main() -> int:
    registered = collect_registered_tools()
    refs = collect_skill_references()

    if not registered:
        print("✗ Could not parse @mcp.tool() registry from server.py")
        return 1

    unresolved: dict[str, list[tuple[Path, int, str]]] = {}
    for tool, hits in refs.items():
        if tool in registered:
            continue
        if tool in INTENTIONAL_FUTURE_REFS:
            continue
        unresolved[tool] = hits

    print("Forward integrity check (SKILL → MCP)")
    print(f"  Registered @mcp.tool() functions: {len(registered)}")
    print(f"  Distinct tool refs in skill files: {len(refs)}")
    print(f"  Intentional future deferrals: {len(INTENTIONAL_FUTURE_REFS)}")

    if not unresolved:
        print("✓ all mcp__samvil_mcp__ references resolve to registered tools")
        return 0

    print(f"✗ {len(unresolved)} unresolved reference(s):")
    for tool, hits in sorted(unresolved.items()):
        print(f"\n  • mcp__samvil_mcp__{tool}")
        for path, lineno, line in hits[:3]:  # cap to 3 hits per tool
            rel = path.relative_to(REPO)
            print(f"      {rel}:{lineno}  {line[:120]}")
        if len(hits) > 3:
            print(f"      ... +{len(hits) - 3} more references")

    print("\nFix options:")
    print("  - Implement the tool in mcp/samvil_mcp/server.py with @mcp.tool()")
    print("  - Or remove the reference from the SKILL/Codex command")
    print("  - Or (last resort, with rationale) add to INTENTIONAL_FUTURE_REFS in this script")
    return 1


if __name__ == "__main__":
    sys.exit(main())
