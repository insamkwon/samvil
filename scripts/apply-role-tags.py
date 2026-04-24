#!/usr/bin/env python3
"""Inject `model_role:` frontmatter into every agents/*.md file.

Sprint 3 (⑤) — the canonical role mapping lives in
`mcp/samvil_mcp/model_role.DEFAULT_ROLES`. This script reads that
mapping and updates each agent's YAML frontmatter so humans can see the
role at a glance.

Behaviour:
  * If the frontmatter already has a `model_role:` line, replace it.
  * Otherwise insert `model_role:` after the `description:` line (or the
    first line of frontmatter if there's no description).
  * Leave everything else untouched — whitespace, ordering, body.
  * For out-of-band agents, set `model_role: out_of_band` so the file
    remains honest about why it isn't one of the six.

Idempotent. `--dry-run` prints the diff without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.model_role import (  # noqa: E402
    DEFAULT_ROLES,
    OUT_OF_BAND,
)


MODEL_ROLE_LINE = re.compile(r"^model_role:\s*\S+\s*$", re.MULTILINE)
DESCRIPTION_LINE = re.compile(r"^description:\s*.+$", re.MULTILINE)


def upsert_model_role(text: str, role_value: str) -> tuple[str, bool]:
    """Return (new_text, changed)."""
    # Only touch content inside the first frontmatter block.
    if not text.startswith("---\n"):
        return text, False
    end = text.find("\n---", 4)
    if end == -1:
        return text, False
    front = text[4:end]  # between the two --- markers
    rest = text[end:]

    if MODEL_ROLE_LINE.search(front):
        new_front = MODEL_ROLE_LINE.sub(f"model_role: {role_value}", front)
    else:
        # Insert after description if present, else at end of frontmatter.
        desc = DESCRIPTION_LINE.search(front)
        if desc:
            insert_at = desc.end()
            new_front = (
                front[:insert_at]
                + f"\nmodel_role: {role_value}"
                + front[insert_at:]
            )
        else:
            new_front = front.rstrip("\n") + f"\nmodel_role: {role_value}\n"

    new_text = "---\n" + new_front + rest
    return new_text, new_text != text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agents-dir", default=str(REPO / "agents"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    agents_dir = Path(args.agents_dir)
    if not agents_dir.is_dir():
        print(f"agents dir not found: {agents_dir}", file=sys.stderr)
        return 1

    changed = 0
    skipped_unknown: list[str] = []
    for path in sorted(agents_dir.glob("*.md")):
        name = path.stem
        if name in DEFAULT_ROLES:
            role_value = DEFAULT_ROLES[name].value
        elif name in OUT_OF_BAND:
            role_value = "out_of_band"
        elif name == "ROLE-INVENTORY":
            continue
        else:
            skipped_unknown.append(name)
            continue

        text = path.read_text()
        new_text, did_change = upsert_model_role(text, role_value)
        if did_change:
            if args.dry_run:
                print(f"DRY: would update {path.name} → model_role: {role_value}")
            else:
                path.write_text(new_text)
                print(f"updated {path.name} → model_role: {role_value}")
            changed += 1

    if skipped_unknown:
        print(
            f"\n⚠ skipped {len(skipped_unknown)} agents with no role in DEFAULT_ROLES:",
            file=sys.stderr,
        )
        for n in skipped_unknown:
            print(f"    - {n}", file=sys.stderr)
        print(
            "   Register them in mcp/samvil_mcp/model_role.DEFAULT_ROLES "
            "or add to OUT_OF_BAND.",
            file=sys.stderr,
        )

    print(f"\n{changed} file(s) updated ({'dry-run' if args.dry_run else 'written'})")
    return 1 if skipped_unknown else 0


if __name__ == "__main__":
    sys.exit(main())
