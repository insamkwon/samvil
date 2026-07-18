#!/usr/bin/env python3
"""Fail when agent files, runtime registry, and documented counts drift."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.model_role import (  # noqa: E402
    DEFAULT_ROLES,
    INLINE_IDENTITIES,
    OUT_OF_BAND,
)


COUNT_PATTERN = re.compile(r"Agent persona files: \*\*(\d+)\*\*")
COUNT_DOCS = (
    REPO / "CLAUDE.md",
    REPO / "references" / "glossary.md",
    REPO / "agents" / "ROLE-INVENTORY.md",
)


def main() -> int:
    persona_names = {
        path.stem
        for path in (REPO / "agents").glob("*.md")
        if path.name != "ROLE-INVENTORY.md"
    }
    registered = set(DEFAULT_ROLES) | set(OUT_OF_BAND)
    expected_personas = registered - set(INLINE_IDENTITIES)
    errors: list[str] = []

    if persona_names != expected_personas:
        missing = sorted(expected_personas - persona_names)
        unregistered = sorted(persona_names - expected_personas)
        if missing:
            errors.append(f"registered personas missing files: {missing}")
        if unregistered:
            errors.append(f"persona files missing registry entries: {unregistered}")

    inline_on_disk = sorted(set(INLINE_IDENTITIES) & persona_names)
    if inline_on_disk:
        errors.append(f"inline identities unexpectedly have persona files: {inline_on_disk}")

    for path in COUNT_DOCS:
        match = COUNT_PATTERN.search(path.read_text())
        if not match:
            errors.append(f"missing persona count marker: {path.relative_to(REPO)}")
        elif int(match.group(1)) != len(persona_names):
            errors.append(
                f"persona count drift in {path.relative_to(REPO)}: "
                f"declared {match.group(1)}, disk {len(persona_names)}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        f"Agent inventory consistent: {len(persona_names)} persona files, "
        f"{len(INLINE_IDENTITIES)} inline identities"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
