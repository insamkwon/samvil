#!/usr/bin/env python3
"""view-claims — render `.samvil/claims.jsonl` for a 1-dev user.

Sprint 1 observability (⑥/⑪ scope in §6.1). Reads the append-only ledger
and collapses rows into current state per `claim_id`. Output formats:

  default (human)      — summary + pending-first list
  --format json        — machine-readable
  --format count       — one-line counts (for status bars / CI)

Filters:
  --status pending|verified|rejected
  --type   <claim_type>
  --subject <substring>
  --since  ISO-8601

Examples:
  python scripts/view-claims.py
  python scripts/view-claims.py --status pending
  python scripts/view-claims.py --subject AC- --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root or sub-dir.
REPO = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = REPO / ".samvil" / "claims.jsonl"


def iter_claims(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def latest_by_id(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in iter_claims(path):
        cid = row.get("claim_id")
        if cid:
            out[cid] = row
    return out


def _age_days(ts_iso: str) -> float | None:
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(ts.tzinfo) - ts).total_seconds() / 86400.0


def fmt_human(rows: list[dict]) -> str:
    by_status = {"pending": 0, "verified": 0, "rejected": 0}
    by_type: dict[str, int] = {}
    for r in rows:
        by_status[r.get("status", "pending")] = (
            by_status.get(r.get("status", "pending"), 0) + 1
        )
        t = r.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    lines: list[str] = []
    lines.append(f"claims: {len(rows)} total")
    lines.append(
        f"  pending:  {by_status['pending']}   "
        f"verified: {by_status['verified']}   "
        f"rejected: {by_status['rejected']}"
    )
    if by_type:
        kv = "  ".join(f"{k}:{v}" for k, v in sorted(by_type.items()))
        lines.append(f"  by_type: {kv}")
    # Pending (oldest first)
    pending = sorted(
        [r for r in rows if r.get("status") == "pending"],
        key=lambda r: r.get("ts", ""),
    )
    if pending:
        lines.append("")
        lines.append("pending (oldest first):")
        for r in pending[:20]:
            age = _age_days(r.get("ts", ""))
            age_str = f"{age:.1f}d" if age is not None else "?"
            lines.append(
                f"  [{age_str:>5}] {r.get('type','?'):<18} "
                f"{r.get('subject','?'):<30} "
                f"claimed_by={r.get('claimed_by','?')}"
            )
        if len(pending) > 20:
            lines.append(f"  ... and {len(pending) - 20} more")
    return "\n".join(lines)


def fmt_count(rows: list[dict]) -> str:
    by_status = {"pending": 0, "verified": 0, "rejected": 0}
    for r in rows:
        by_status[r.get("status", "pending")] = (
            by_status.get(r.get("status", "pending"), 0) + 1
        )
    return (
        f"total={len(rows)} "
        f"pending={by_status['pending']} "
        f"verified={by_status['verified']} "
        f"rejected={by_status['rejected']}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--path", default=str(DEFAULT_LEDGER))
    p.add_argument("--format", choices=["human", "json", "count"], default="human")
    p.add_argument("--status")
    p.add_argument("--type")
    p.add_argument("--subject")
    p.add_argument("--since", help="ISO-8601 UTC; filter ts >= this")
    args = p.parse_args()

    rows = list(latest_by_id(Path(args.path)).values())
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    if args.type:
        rows = [r for r in rows if r.get("type") == args.type]
    if args.subject:
        rows = [r for r in rows if args.subject in r.get("subject", "")]
    if args.since:
        rows = [r for r in rows if r.get("ts", "") >= args.since]

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "count":
        print(fmt_count(rows))
    else:
        if not rows:
            print("claims: 0 (empty ledger)")
        else:
            print(fmt_human(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
