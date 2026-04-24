#!/usr/bin/env python3
"""Sprint 1 exit-gate check — automated subset.

Per HANDOFF-v3.2-DECISIONS.md §7 Sprint 1 exit gate:

  * Empty project round-trips skeleton gates.       (A)
  * Glossary CI check green.                        (B)
  * Calibration dogfood completes and at least 80 % (C)
    of `(initial estimate)` constants have ≥ 1 recorded observation.

This script verifies A, B, C deterministically:

  A — runs a synthetic skeleton round-trip (claim_post → verify →
      gate_check → view-claims). Uses a temp ledger, leaves no trace.
  B — invokes `scripts/check-glossary.sh` and parses exit code.
  C — inspects `.samvil/experiments.jsonl` directly.

Exit codes:
  0 — all three pass
  1 — any fail (details printed)
  2 — usage / environment error

Keep this script pure-Python (no PyYAML, no MCP dependency) so it runs
in minimal environments and in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_skeleton_round_trip() -> bool:
    """Spin up a throwaway ledger + one synthetic claim + one gate check."""
    print("A) Skeleton round-trip")
    # Add mcp/ to sys.path so we can import claim_ledger without installing.
    sys.path.insert(0, str(REPO / "mcp"))
    try:
        from samvil_mcp.claim_ledger import ClaimLedger
        from samvil_mcp.gates import GateName, Verdict, gate_check
    except Exception as e:  # pragma: no cover
        _fail(f"import failed: {e}")
        return False

    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        # Seed a tiny file so file:line evidence resolves.
        src = project / "src"
        src.mkdir()
        (src / "app.ts").write_text("console.log('hi')\n")

        ledger = ClaimLedger(project / ".samvil" / "claims.jsonl")

        # Post a seed field claim, verify it, assert state.
        claim = ledger.post(
            type="seed_field_set",
            subject="features[0].name",
            statement="feature name = Focus Timer",
            authority_file="seed.json",
            claimed_by="agent:seed-architect",
            evidence=["src/app.ts:1"],
        )
        verified = ledger.verify(
            claim.claim_id,
            verified_by="agent:user",
            project_root=project,
        )
        if verified.status != "verified":
            _fail(f"verify did not set status=verified (got {verified.status})")
            return False
        _ok(f"claim {verified.claim_id[:20]}… verified")

        # Run a gate check that should PASS (standard tier, above floor).
        v = gate_check(
            GateName.BUILD_TO_QA.value,
            samvil_tier="standard",
            metrics={"implementation_rate": 0.90},
        )
        if v.verdict != Verdict.PASS.value:
            _fail(f"gate_check(build_to_qa, 0.90) gave {v.verdict}, expected pass")
            return False
        _ok("gate_check build_to_qa@standard/0.90 → pass")

        # Run a gate check that should BLOCK.
        v2 = gate_check(
            GateName.BUILD_TO_QA.value,
            samvil_tier="thorough",
            metrics={"implementation_rate": 0.50},
        )
        if v2.verdict != Verdict.BLOCK.value:
            _fail(
                f"gate_check(build_to_qa@thorough/0.50) gave {v2.verdict}, expected block"
            )
            return False
        _ok("gate_check build_to_qa@thorough/0.50 → block")

    sys.path.pop(0)
    return True


def check_b_glossary() -> bool:
    print("B) Glossary check")
    script = REPO / "scripts" / "check-glossary.sh"
    if not script.exists():
        _fail(f"missing {script}")
        return False
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail("check-glossary.sh exited non-zero")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return False
    _ok("glossary check: green")
    return True


def check_c_experiments_coverage(min_pct: float = 0.80) -> bool:
    """Do ≥80 % of seeded experiments have at least one observation?"""
    print(f"C) Experiment coverage ≥ {int(min_pct*100)}%")
    path = REPO / ".samvil" / "experiments.jsonl"
    if not path.exists():
        _fail(f"{path} missing — run scripts/seed-experiments.py first")
        return False
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    total = len(rows)
    if total == 0:
        _fail("experiments.jsonl is empty")
        return False
    with_obs = sum(1 for r in rows if r.get("observations"))
    pct = with_obs / total
    msg = f"{with_obs}/{total} experiments calibrated ({pct*100:.0f}%)"
    if pct < min_pct:
        _fail(msg + f" — below {int(min_pct*100)}% exit-gate target")
        print(
            "    tip: run references/calibration-dogfood.md and append "
            "observations, or run scripts/seed-sample-observations.py "
            "for synthetic coverage during development"
        )
        return False
    _ok(msg)
    return True


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--skip-c",
        action="store_true",
        help="skip the experiment coverage check (for CI where dogfood hasn't happened)",
    )
    args = p.parse_args()

    results = {
        "A": check_a_skeleton_round_trip(),
        "B": check_b_glossary(),
    }
    if not args.skip_c:
        results["C"] = check_c_experiments_coverage()

    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
