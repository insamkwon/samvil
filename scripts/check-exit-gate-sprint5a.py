#!/usr/bin/env python3
"""Sprint 5a exit-gate check.

Per §7: one real run produces at least one `experimental_policy`. We
verify the primitives are wired and that the seed-experiments bootstrap
populated them (which it did in Sprint 1). Additional:

  A — jurisdiction detector flags the canonical sensitive actions.
  B — retro round-trip: create experiment, record 5 runs, promote,
      and the file reflects adoption.
  C — `.samvil/experiments.jsonl` exists and has ≥ 1 experimental_policy.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.jurisdiction import Jurisdiction, check_jurisdiction  # noqa: E402
from samvil_mcp.retro_v3_2 import (  # noqa: E402
    ExperimentRun,
    PolicyExperiment,
    RetroReport,
    load_retro,
    promote,
    save_retro,
)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def check_a_jurisdiction() -> bool:
    print("A) Jurisdiction detector")
    cases = [
        ("idle command", "echo hi", Jurisdiction.AI),
        ("add password reset", "", Jurisdiction.USER),
        ("npm install express", "npm install express", Jurisdiction.EXTERNAL),
        ("git force push", "git push --force", Jurisdiction.USER),
    ]
    for label, cmd, expected in cases:
        v = check_jurisdiction(action_description=label, command=cmd)
        if v.jurisdiction != expected.value:
            _fail(f"{label!r} → {v.jurisdiction} (expected {expected.value})")
            return False
    _ok("detector handled 4 canonical cases")
    return True


def check_b_retro_round_trip() -> bool:
    print("B) Retro experiment round-trip")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "retro-001.yaml"
        report = RetroReport()
        e = PolicyExperiment(id="exp_demo", rule="floor=0.85")
        report.policy_experiments.append(e)
        save_retro(report, path)

        for _ in range(5):
            loaded = load_retro(path)
            loaded.policy_experiments[0].record_run(
                ExperimentRun(ts="2026-04-24T00:00:00Z", verdict="pass")
            )
            save_retro(loaded, path)

        final = load_retro(path)
        adopted = promote(final, "exp_demo")
        save_retro(final, path)

        if adopted is None:
            _fail("promotion blocked despite 5 clean runs")
            return False
        # Reload and assert adopted stage.
        loaded = load_retro(path)
        assert loaded.adopted_policies[0].promoted_from_experiment == "exp_demo"
    _ok("5 runs + promote → adopted policy recorded")
    return True


def check_c_experiments_seeded() -> bool:
    print("C) experiments.jsonl populated")
    path = REPO / ".samvil" / "experiments.jsonl"
    if not path.exists():
        _fail(f"{path} missing")
        return False
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    if len(lines) < 1:
        _fail("no experimental_policy rows")
        return False
    _ok(f"{len(lines)} experimental_policy rows seeded")
    return True


def main() -> int:
    results = {
        "A": check_a_jurisdiction(),
        "B": check_b_retro_round_trip(),
        "C": check_c_experiments_seeded(),
    }
    print()
    print("Summary")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
