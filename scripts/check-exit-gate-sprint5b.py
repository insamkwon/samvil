#!/usr/bin/env python3
"""Sprint 5b exit-gate check.

Per §7 Sprint 5b:
  * Synthetic test forces a `high`-severity stagnation and lateral
    diagnosis kicks in correctly.
  * Synthetic Generator-Judge dispute invokes consensus resolver.
  * `/samvil` without `--council` runs the full pipeline without
    Council Gate A.  (documented; verified by opt-in flag presence in
    `references/council-retirement-migration.md`.)

Code-level checks we can run here:

  A — stagnation: with 2 signals we get severity=HIGH + lateral prompt.
  B — consensus: Generator/Judge mismatch detector fires and resolver
      prompts are well-formed.
  C — retirement doc: the migration path exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.consensus_v3_2 import (  # noqa: E402
    DisputeInput,
    build_judge_prompt,
    build_reviewer_prompt,
    detect_dispute,
)
from samvil_mcp.stagnation_v3_2 import (  # noqa: E402
    Severity,
    StagnationInput,
    build_lateral_prompt,
    evaluate,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_stagnation_high() -> bool:
    print("A) Stagnation HIGH with 2 signals → lateral prompt")
    v = evaluate(
        StagnationInput(
            error_history=["build_fail", "build_fail"],
            current_error="build_fail",
            seed_version_changed=True,
            build_output_changed=False,
        )
    )
    if v.severity != Severity.HIGH.value:
        _fail(f"severity={v.severity}, expected high")
        return False
    if not v.should_halt:
        _fail("should_halt not set")
        return False
    prompt = build_lateral_prompt(subject="AC-demo", verdict=v)
    if "AC-demo" not in prompt or "alternative" not in prompt.lower():
        _fail("lateral prompt malformed")
        return False
    _ok("two signals → HIGH → lateral prompt built")
    return True


def check_b_consensus() -> bool:
    print("B) Consensus mismatch triggers + resolver prompts")
    d = detect_dispute(
        DisputeInput(
            subject="AC-1", generator_verdict="pass", judge_verdict="fail"
        )
    )
    if not d.should_invoke:
        _fail("dispute not detected")
        return False
    rev = build_reviewer_prompt(
        subject="AC-1", triggers=d.triggers, context="evidence is thin"
    )
    jud = build_judge_prompt(
        subject="AC-1", triggers=d.triggers, reviewer_position="escalate"
    )
    if "AC-1" not in rev or "AC-1" not in jud:
        _fail("resolver prompts missing subject")
        return False
    _ok("mismatch detected; Reviewer + Judge prompts built")
    return True


def check_c_retirement_doc() -> bool:
    print("C) Council retirement migration doc")
    doc = REPO / "references" / "council-retirement-migration.md"
    if not doc.exists():
        _fail(f"{doc} missing")
        return False
    text = doc.read_text()
    for marker in ("v3.2.0", "v3.3.0", "--council", "dispute resolver"):
        if marker not in text:
            _fail(f"doc missing marker: {marker}")
            return False
    _ok(f"{doc.name} present and complete")
    return True


def main() -> int:
    results = {
        "A": check_a_stagnation_high(),
        "B": check_b_consensus(),
        "C": check_c_retirement_doc(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
