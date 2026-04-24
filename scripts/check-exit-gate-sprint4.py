#!/usr/bin/env python3
"""Sprint 4 exit-gate check.

Per HANDOFF-v3.2-DECISIONS.md §7 Sprint 4:

  * L3 dogfood beats v3.1 on lifecycle coverage and ac_testability.
  * samvil narrate produces a coherent 1-page summary on a non-trivial
    project.

The dogfood comparison requires running real interviews, which needs a
live Claude Code session. This script verifies the code paths:

  A — all 5 interview_level values are recognized and map to techniques.
  B — seed_readiness scoring is consistent with the floors.
  C — PAL adaptive picks different levels for different project prompts.
  D — narrate context assembly works on the repo's own .samvil/ dir.
  E — narrate prompt contains the expected sections and the parser
      round-trips through markdown.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.interview_v3_2 import (  # noqa: E402
    InterviewLevel,
    READINESS_FLOORS,
    compute_seed_readiness,
    pal_select_level,
    resolve_level,
    techniques_for_level,
)
from samvil_mcp.narrate import (  # noqa: E402
    build_context,
    build_narrate_prompt,
    parse_narrative,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_levels() -> bool:
    print("A) All 5 interview_level values map to techniques")
    for lvl in InterviewLevel:
        t = techniques_for_level(lvl)
        if not t:
            _fail(f"{lvl.value} has no techniques")
            return False
    _ok("all 5 levels resolve to non-empty technique tuples")

    # AUTO downgrade path
    lvl = resolve_level(
        InterviewLevel.MAX,
        provider_router_ready=False,
    )
    if lvl != InterviewLevel.DEEP:
        _fail(f"MAX without router should downgrade to DEEP, got {lvl.value}")
        return False
    _ok("MAX downgrades to DEEP without router")
    return True


def check_b_readiness_scoring() -> bool:
    print("B) seed_readiness scoring")
    score_low = compute_seed_readiness(
        {
            "intent_clarity": 0.50,
            "constraint_clarity": 0.50,
            "ac_testability": 0.50,
            "lifecycle_coverage": 0.50,
            "decision_boundary": 0.50,
        },
        samvil_tier="standard",
    )
    score_high = compute_seed_readiness(
        {k: 1.0 for k in ("intent_clarity", "constraint_clarity",
                          "ac_testability", "lifecycle_coverage",
                          "decision_boundary")},
        samvil_tier="standard",
    )
    if not (score_low.total < 0.6 < score_high.total):
        _fail(f"scoring not monotone: low={score_low.total} high={score_high.total}")
        return False
    _ok(f"low={score_low.total:.2f} below_floor={score_low.below_floor}; "
        f"high={score_high.total:.2f}")
    return True


def check_c_pal_adaptive() -> bool:
    print("C) PAL adaptive level selection")
    cases = [
        ("countdown timer", InterviewLevel.QUICK),
        ("admin dashboard", InterviewLevel.NORMAL),
        ("multi-tenant real-time sync", InterviewLevel.DEEP),
    ]
    for prompt, expected in cases:
        lvl = pal_select_level(project_prompt=prompt)
        if lvl != expected:
            _fail(f"{prompt!r} → {lvl.value}, expected {expected.value}")
            return False
    _ok("PAL picks the expected level for 3 canonical prompts")
    return True


def check_d_narrate_context() -> bool:
    print("D) Narrate context assembly")
    ctx = build_context(REPO, since=None)  # default window
    # We can't assert specific counts since the repo's .samvil/ changes,
    # but we can assert the shape is populated and the summary is
    # non-empty.
    summary = ctx.to_summary()
    if "Window:" not in summary:
        _fail("context summary missing Window:")
        return False
    if "Pending claims" not in summary:
        _fail("context summary missing Pending claims:")
        return False
    _ok(f"context summary length = {len(summary)} bytes")
    return True


def check_e_narrate_prompt_and_parse() -> bool:
    print("E) Narrate prompt + parse round-trip")
    ctx = build_context(REPO)
    prompt = build_narrate_prompt(ctx)
    required = ("what_happened", "where_stuck", "next_actions")
    for k in required:
        if k not in prompt:
            _fail(f"prompt missing key: {k}")
            return False

    # Synthetic LLM-style response
    raw = json.dumps(
        {
            "what_happened": ["Built claim ledger", "Shipped gate framework"],
            "where_stuck": [],
            "next_actions": ["Run dogfood", "Update CHANGELOG", "Bump version"],
        }
    )
    n = parse_narrative(raw)
    md = n.to_markdown()
    if "## What happened" not in md:
        _fail("markdown missing section header")
        return False
    _ok("prompt contains all sections; parser round-trips to markdown")
    return True


def main() -> int:
    results = {
        "A": check_a_levels(),
        "B": check_b_readiness_scoring(),
        "C": check_c_pal_adaptive(),
        "D": check_d_narrate_context(),
        "E": check_e_narrate_prompt_and_parse(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
