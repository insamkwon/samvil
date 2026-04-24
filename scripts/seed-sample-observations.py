#!/usr/bin/env python3
"""Seed synthetic bootstrap observations onto experiments.jsonl.

**Use this only** for Sprint 1 development-time calibration coverage,
before real dogfood runs produce real observations. Each synthetic row
is flagged `stage="bootstrap"` and `source="synthetic"` so later retro
passes can distinguish them from measured data.

The Sprint 1 exit gate (§7) requires ≥80% of `(initial estimate)`
constants to carry at least one observation. Real dogfood is the
authoritative path — this script exists so repo maintainers can verify
the end-to-end pipeline works before running full dogfood.

Usage:
  python3 scripts/seed-sample-observations.py --dry-run
  python3 scripts/seed-sample-observations.py           # writes
  python3 scripts/seed-sample-observations.py --purge-synthetic
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXP_PATH = REPO / ".samvil" / "experiments.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    )


def seed(rows: list[dict]) -> tuple[int, int]:
    """Add one bootstrap observation to each row that has none."""
    added = 0
    skipped = 0
    ts = _now()
    for r in rows:
        existing = r.get("observations") or []
        if existing:
            skipped += 1
            continue
        # Synthesize a trivially-passing observation anchored to the
        # initial value (when one exists). This says: "the default value
        # ran through the pipeline and didn't crash". It does not say
        # "the floor is correctly calibrated".
        obs = {
            "ts": ts,
            "value_seen": r.get("initial_value"),
            "verdict": "bootstrap_pass",
            "source": "synthetic",
            "stage": "bootstrap",
            "note": (
                "Synthetic bootstrap observation (scripts/seed-sample-observations.py). "
                "Replace with real dogfood data as soon as possible; "
                "see references/calibration-dogfood.md."
            ),
        }
        r["observations"] = existing + [obs]
        added += 1
    return added, skipped


def purge_synthetic(rows: list[dict]) -> int:
    removed = 0
    for r in rows:
        obs = r.get("observations") or []
        keep = [o for o in obs if o.get("source") != "synthetic"]
        if len(keep) != len(obs):
            r["observations"] = keep
            removed += 1
    return removed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--path", default=str(EXP_PATH))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--purge-synthetic",
        action="store_true",
        help="remove previously-seeded synthetic observations",
    )
    args = p.parse_args()

    path = Path(args.path)
    rows = _load(path)
    if not rows:
        print(f"no experiments at {path}; run scripts/seed-experiments.py first")
        return 1

    if args.purge_synthetic:
        removed = purge_synthetic(rows)
        print(f"purge: removed synthetic observations from {removed} experiments")
        if not args.dry_run:
            _write(path, rows)
            print(f"wrote {path}")
        return 0

    added, skipped = seed(rows)
    print(f"added bootstrap observation to {added} experiments (skipped {skipped})")
    if args.dry_run:
        print("(dry-run) no file written")
        return 0
    _write(path, rows)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
