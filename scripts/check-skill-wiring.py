#!/usr/bin/env python3
"""Skill wiring smoke test (v3.2 β plan, post-Sprint 6).

Verifies each stage SKILL.md mentions the Contract Layer Protocol and
contains the minimal MCP tool references it should. Grep-based — no
runtime execution. The point is to catch "someone edited a skill and
forgot to call the post_stage gate" before it regresses silently.

Rules:
  * Every stage skill that changed in the β wiring must mention
    `contract-layer-protocol.md`.
  * Each skill must reference the specific MCP tools it was supposed
    to wire up.

Not checked here (runtime):
  * Do the tools actually get called when the skill runs?
    → requires real `/samvil` invocation (dogfood).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CHECKS: list[tuple[str, str, tuple[str, ...]]] = [
    # (skill_name, skill_path, required substrings)
    (
        "samvil",
        "skills/samvil/SKILL.md",
        ("contract-layer-protocol", "check_jurisdiction",),
    ),
    (
        "samvil-interview",
        "skills/samvil-interview/SKILL.md",
        (
            "contract-layer-protocol",
            "compute_seed_readiness",
            "gate_check",
            "interview_to_seed",
        ),
    ),
    (
        "samvil-build",
        "skills/samvil-build/SKILL.md",
        (
            "contract-layer-protocol",
            "route_task",
            "claim_post",
            "gate_check",
            "build_to_qa",
        ),
    ),
    (
        "samvil-qa",
        "skills/samvil-qa/SKILL.md",
        (
            "contract-layer-protocol",
            "route_task",
            "validate_role_separation",
            "claim_verify",
            "consensus_trigger",
            "qa_to_deploy",
        ),
    ),
    (
        "samvil-council",
        "skills/samvil-council/SKILL.md",
        (
            "council_deprecation_warning",
            "council-retirement-migration",
            "--council",
        ),
    ),
    (
        "samvil-update",
        "skills/samvil-update/SKILL.md",
        (
            "migrate_plan",
            "migrate_apply",
            "--migrate v3.2",
            "v3.1 → v3.2",
        ),
    ),
    (
        "samvil-retro",
        "skills/samvil-retro/SKILL.md",
        (
            "narrate_build_prompt",
            "narrate_parse",
        ),
    ),
]


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def main() -> int:
    all_green = True
    for skill_name, rel_path, required in CHECKS:
        path = REPO / rel_path
        if not path.exists():
            _fail(f"{skill_name}: file missing ({rel_path})")
            all_green = False
            continue
        text = path.read_text()
        missing = [token for token in required if token not in text]
        if missing:
            _fail(f"{skill_name}: missing tokens {missing}")
            all_green = False
        else:
            _ok(f"{skill_name}: all {len(required)} tokens present")
    print()
    print("Summary:", "PASS" if all_green else "FAIL")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
