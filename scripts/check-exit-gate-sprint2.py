#!/usr/bin/env python3
"""Sprint 2 exit-gate check.

Per HANDOFF-v3.2-DECISIONS.md §7 Sprint 2 exit gate:

  * "build on Opus, QA on Codex" round-trips on a toy project.
  * Escalation and downgrade fire correctly in synthetic scenarios.

This script verifies both deterministically, in-process (no network).

Usage:
  python3 scripts/check-exit-gate-sprint2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.routing import (  # noqa: E402
    CostTier,
    ModelProfile,
    route_task,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_opus_build_codex_qa() -> bool:
    """Simulate the exit-gate scenario."""
    print("A) build on Opus, QA on Codex")

    # Scenario: frontier profiles, Opus first for build, Codex first for QA.
    build_profiles = [
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
            nickname="opus-4.7",
        ),
        ModelProfile(
            provider="openai",
            model_id="gpt-5-codex",
            cost_tier=CostTier.FRONTIER,
            nickname="codex",
        ),
    ]
    qa_profiles = list(reversed(build_profiles))
    role_overrides = {
        "build-worker": CostTier.FRONTIER,
        "qa-functional": CostTier.FRONTIER,
    }

    build = route_task(
        task_role="build-worker",
        profiles=build_profiles,
        role_overrides=role_overrides,
    )
    if build.profile.model_id != "claude-opus-4-7":
        _fail(
            f"build picked {build.profile.model_id}, expected claude-opus-4-7"
        )
        return False
    _ok(f"build → {build.profile.nickname} ({build.profile.provider})")

    qa = route_task(
        task_role="qa-functional",
        profiles=qa_profiles,
        role_overrides=role_overrides,
    )
    if qa.profile.model_id != "gpt-5-codex":
        _fail(f"qa picked {qa.profile.model_id}, expected gpt-5-codex")
        return False
    _ok(f"qa    → {qa.profile.nickname} ({qa.profile.provider})")
    return True


def check_b_escalation() -> bool:
    """On 2 failures, a balanced-default role moves to frontier."""
    print("B) Escalation")
    profiles = [
        ModelProfile(
            provider="anthropic",
            model_id="claude-haiku-4-5",
            cost_tier=CostTier.FRUGAL,
        ),
        ModelProfile(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            cost_tier=CostTier.BALANCED,
        ),
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
        ),
    ]

    for attempts, expected_tier in (
        (0, CostTier.BALANCED),
        (1, CostTier.FRONTIER),
        (2, CostTier.FRONTIER),  # capped
    ):
        d = route_task(
            task_role="build-worker",
            profiles=profiles,
            escalation_depth=min(attempts, 2),
        )
        if d.chosen_cost_tier != expected_tier:
            _fail(
                f"attempts={attempts} gave {d.chosen_cost_tier.value}, "
                f"expected {expected_tier.value}"
            )
            return False
    _ok("escalation 0→1→2 → balanced→frontier→frontier (capped)")
    return True


def check_c_downgrade() -> bool:
    """High budget pressure downgrades a balanced role to frugal."""
    print("C) Downgrade")
    profiles = [
        ModelProfile(
            provider="anthropic",
            model_id="claude-haiku-4-5",
            cost_tier=CostTier.FRUGAL,
        ),
        ModelProfile(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            cost_tier=CostTier.BALANCED,
        ),
        ModelProfile(
            provider="anthropic",
            model_id="claude-opus-4-7",
            cost_tier=CostTier.FRONTIER,
        ),
    ]
    d = route_task(
        task_role="build-worker",
        profiles=profiles,
        budget_pressure=0.95,
    )
    if d.chosen_cost_tier != CostTier.FRUGAL or not d.downgraded:
        _fail(
            f"downgrade did not fire at 0.95 pressure "
            f"(chose {d.chosen_cost_tier.value}, downgraded={d.downgraded})"
        )
        return False
    _ok(f"budget 0.95 → downgrade balanced → frugal")
    return True


def check_d_escalation_beats_downgrade() -> bool:
    """Escalation dominates downgrade when both fire."""
    print("D) Escalation overrides downgrade")
    d = route_task(
        task_role="build-worker",
        escalation_depth=1,
        budget_pressure=0.99,
    )
    if d.chosen_cost_tier != CostTier.FRONTIER:
        _fail(
            "escalation did not win over downgrade "
            f"(chose {d.chosen_cost_tier.value})"
        )
        return False
    _ok("escalation 1 + pressure 0.99 → frontier (escalation wins)")
    return True


def main() -> int:
    results = {
        "A": check_a_opus_build_codex_qa(),
        "B": check_b_escalation(),
        "C": check_c_downgrade(),
        "D": check_d_escalation_beats_downgrade(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
