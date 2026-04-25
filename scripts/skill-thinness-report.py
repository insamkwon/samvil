#!/usr/bin/env python3
"""Report active SAMVIL skill size versus preserved legacy bodies.

Phase 2 uses this as a guardrail while migrating long stage skills into
ultra-thin MCP-driven entries.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"


@dataclass(frozen=True)
class SkillSize:
    name: str
    active_lines: int
    legacy_lines: int | None
    active_path: Path

    @property
    def has_legacy(self) -> bool:
        return self.legacy_lines is not None


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def collect() -> list[SkillSize]:
    rows: list[SkillSize] = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        legacy = skill_md.with_name("SKILL.legacy.md")
        rows.append(
            SkillSize(
                name=skill_md.parent.name,
                active_lines=_line_count(skill_md),
                legacy_lines=_line_count(legacy) if legacy.exists() else None,
                active_path=skill_md.relative_to(REPO),
            )
        )
    return rows


def render(rows: list[SkillSize], *, threshold: int) -> str:
    lines = [
        "# Skill Thinness Report",
        "",
        f"Threshold: {threshold} active lines",
        "",
        "| Skill | Active | Legacy | Status |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        legacy = str(row.legacy_lines) if row.legacy_lines is not None else "-"
        if row.active_lines <= threshold:
            status = "thin"
        elif row.has_legacy:
            status = "legacy-preserved"
        else:
            status = "needs-migration"
        lines.append(f"| `{row.name}` | {row.active_lines} | {legacy} | {status} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-over", type=int, default=0)
    parser.add_argument("--threshold", type=int, default=120)
    parser.add_argument(
        "--migrated-only",
        action="store_true",
        help="Only show skills that already have SKILL.legacy.md.",
    )
    args = parser.parse_args()

    rows = collect()
    if args.migrated_only:
        rows = [row for row in rows if row.has_legacy]

    print(render(rows, threshold=args.threshold))

    if args.fail_over:
        offenders = [
            row for row in rows
            if row.has_legacy and row.active_lines > args.fail_over
        ]
        if offenders:
            names = ", ".join(f"{row.name}={row.active_lines}" for row in offenders)
            print(f"\nFAIL: migrated skills over {args.fail_over} lines: {names}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
