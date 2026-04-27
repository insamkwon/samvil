#!/usr/bin/env python3
"""Validate all host command reference files for completeness and consistency."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EXPECTED_SKILLS = [
    "samvil", "samvil-interview", "samvil-pm-interview", "samvil-seed",
    "samvil-council", "samvil-design", "samvil-scaffold", "samvil-build",
    "samvil-qa", "samvil-deploy", "samvil-evolve", "samvil-retro",
    "samvil-analyze", "samvil-doctor", "samvil-update",
]

CODEX_DIR = REPO / "references" / "codex-commands"
GEMINI_DIR = REPO / "references" / "gemini-commands"

errors: list[str] = []
ok_count = 0


def check_dir(d: Path, ext: str, mcp_required: list[str]) -> None:
    global ok_count
    for skill in EXPECTED_SKILLS:
        f = d / f"{skill}{ext}"
        if not f.exists():
            errors.append(f"MISSING: {f.relative_to(REPO)}")
            continue
        content = f.read_text(encoding="utf-8")
        for tool in mcp_required:
            if tool not in content:
                errors.append(f"MISSING_TOOL {tool}: {f.relative_to(REPO)}")
            else:
                ok_count += 1


check_dir(CODEX_DIR, ".md", ["read_chain_marker", "write_chain_marker"])
check_dir(GEMINI_DIR, ".toml", ["read_chain_marker"])

if errors:
    print("FAIL: host command file validation", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {ok_count} tool references validated across codex+gemini command files")
