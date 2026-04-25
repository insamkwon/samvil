#!/usr/bin/env python3
"""Validate and print the next action from .samvil/next-skill.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REQUIRED = ("schema_version", "chain_via", "next_skill", "reason", "from_stage")


def load_marker(project_root: Path) -> dict:
    marker = project_root / ".samvil" / "next-skill.json"
    if not marker.exists():
        raise ValueError(f"marker missing: {marker}")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"marker is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("marker must be a JSON object")
    return data


def validate_marker(data: dict) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED:
        if not data.get(key):
            errors.append(f"missing required field: {key}")
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if data.get("chain_via") != "file_marker":
        errors.append("chain_via must be file_marker")
    next_skill = data.get("next_skill")
    if next_skill:
        skill_path = REPO / "skills" / next_skill / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"next_skill not found: {skill_path.relative_to(REPO)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--expect-next", default="")
    args = parser.parse_args()

    try:
        data = load_marker(args.project_root)
        errors = validate_marker(data)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.expect_next and data.get("next_skill") != args.expect_next:
        errors.append(
            f"expected next_skill={args.expect_next}, got {data.get('next_skill')}"
        )

    if errors:
        print("FAIL: invalid continuation marker", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    skill_path = Path("skills") / data["next_skill"] / "SKILL.md"
    print("OK: continuation marker valid")
    print(f"next_skill: {data['next_skill']}")
    print(f"from_stage: {data['from_stage']}")
    print(f"reason: {data['reason']}")
    print(f"next_action: read {skill_path} and continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
