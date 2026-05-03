#!/usr/bin/env python3
"""Generate host-specific command reference files from _SKILL_CHAIN.

Usage:
  python3 scripts/generate-host-commands.py --host codex [--force] [--dry-run]
  python3 scripts/generate-host-commands.py --host gemini [--force] [--dry-run]
  python3 scripts/generate-host-commands.py --host all [--force] [--dry-run]

Rules:
  - Existing files are skipped unless --force is given.
  - --dry-run prints what would be created without writing anything.
  - Both codex (.md) and gemini (.toml) templates include read_chain_marker
    and write_chain_marker references (required by test_chain_marker_e2e.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.host_adapters import _SKILL_CHAIN  # type: ignore[import]

CODEX_DIR = REPO / "references" / "codex-commands"
GEMINI_DIR = REPO / "references" / "gemini-commands"

_SKILL_DESCRIPTIONS: dict[str, str] = {
    "samvil": "Orchestrator — health check, tier selection, chain start",
    "samvil-interview": "Engineering-focused Socratic interview",
    "samvil-pm-interview": "PM-focused interview (vision → epics → tasks → ACs)",
    "samvil-seed": "Interview results → seed.json conversion",
    "samvil-council": "Council Gate A (2-round: Research → Review)",
    "samvil-design": "blueprint.json generation + Gate B",
    "samvil-scaffold": "Next.js 14 + shadcn/ui project scaffold",
    "samvil-build": "AC Tree leaf-level feature implementation",
    "samvil-qa": "Tree aggregation 3-pass verification",
    "samvil-deploy": "Post-QA deployment (Vercel/Railway/Coolify)",
    "samvil-evolve": "Seed evolution (Wonder → Reflect → converge)",
    "samvil-retro": "Harness self-improvement proposals",
    "samvil-analyze": "Brownfield project analysis",
    "samvil-doctor": "Environment/plugin diagnostics",
    "samvil-update": "GitHub update + --migrate support",
    "samvil-resume": "Resume interrupted session without re-running interview",
}


def _codex_template(skill_name: str, next_skill: str) -> str:
    desc = _SKILL_DESCRIPTIONS.get(skill_name, skill_name)
    next_line = f"After completing: read `.samvil/next-skill.json` for the next stage ({next_skill})." if next_skill else "This is a terminal skill — no automatic chain continuation."
    chain_note = f"\nTell the user the next command to run." if next_skill else ""
    return f"""# SAMVIL {skill_name} (Codex CLI)

{desc}.

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `{skill_name}`, skip this stage.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${{PWD}}")`.
2. Read `project.seed.json` for seed context and current state.
3. Execute the {skill_name} stage logic according to the SKILL.md instructions
   in `skills/{skill_name}/SKILL.md`.
4. On completion, run MCP tool `write_chain_marker(project_root="${{PWD}}",
   host_name="codex_cli", current_skill="{skill_name}")`.

## Chain

{next_line}{chain_note}
"""


def _gemini_template(skill_name: str, next_skill: str) -> str:
    desc = _SKILL_DESCRIPTIONS.get(skill_name, skill_name)
    chain_note = f'Read `.samvil/next-skill.json` for the next stage ({next_skill}) and report to the user.' if next_skill else "This is a terminal skill — no automatic chain continuation."
    return f"""prompt = \"\"\"
SAMVIL pipeline stage: {skill_name}.

{desc}.

## Prerequisites

Use MCP tool `read_chain_marker` with project_root="${{PWD}}" to check pipeline position.
If `next_skill` is not `{skill_name}`, skip and report the expected stage.

## Execution

1. Use MCP tool `read_chain_marker` with project_root to confirm stage.
2. Read `.samvil/project.seed.json` for seed context.
3. Execute the {skill_name} stage logic (see `skills/{skill_name}/SKILL.md`).
4. On completion, use MCP tool `write_chain_marker` with project_root="${{PWD}}",
   host_name="gemini_cli", current_skill="{skill_name}".

## Chain

{chain_note}
\"\"\"
"""


def generate_codex(force: bool, dry_run: bool) -> list[str]:
    CODEX_DIR.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for entry in _SKILL_CHAIN:
        name = entry["name"]
        next_s = entry["next"]
        dest = CODEX_DIR / f"{name}.md"
        if dest.exists() and not force:
            print(f"  SKIP  {dest.name} (exists, use --force to overwrite)")
            continue
        content = _codex_template(name, next_s)
        if dry_run:
            print(f"  DRY   {dest.name}")
        else:
            dest.write_text(content, encoding="utf-8")
            print(f"  WRITE {dest.name}")
        created.append(str(dest))
    return created


def generate_gemini(force: bool, dry_run: bool) -> list[str]:
    GEMINI_DIR.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for entry in _SKILL_CHAIN:
        name = entry["name"]
        next_s = entry["next"]
        dest = GEMINI_DIR / f"{name}.toml"
        if dest.exists() and not force:
            print(f"  SKIP  {dest.name} (exists, use --force to overwrite)")
            continue
        content = _gemini_template(name, next_s)
        if dry_run:
            print(f"  DRY   {dest.name}")
        else:
            dest.write_text(content, encoding="utf-8")
            print(f"  WRITE {dest.name}")
        created.append(str(dest))
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate host command reference files.")
    parser.add_argument("--host", choices=["codex", "gemini", "all"], default="all")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if args.dry_run:
        print("[dry-run] No files will be written.\n")

    total = 0
    if args.host in ("codex", "all"):
        print(f"=== codex ({CODEX_DIR}) ===")
        total += len(generate_codex(args.force, args.dry_run))

    if args.host in ("gemini", "all"):
        print(f"\n=== gemini ({GEMINI_DIR}) ===")
        total += len(generate_gemini(args.force, args.dry_run))

    action = "would create" if args.dry_run else "created/updated"
    print(f"\nDone. {total} file(s) {action}.")


if __name__ == "__main__":
    main()
