#!/usr/bin/env python3
"""View harness-feedback.log in human-readable format.

Prints:
  1. Summary table (entries, total suggestions_v2)
  2. Priority breakdown
  3. Sprint breakdown with IDs
  4. Latest entry detailed dump (all suggestions_v2)

Usage:
  python3 scripts/view-retro.py              # all entries summary
  python3 scripts/view-retro.py --latest     # latest entry full
  python3 scripts/view-retro.py --id v3-022  # single suggestion detail
  python3 scripts/view-retro.py --sprint 1   # all in Sprint 1
  python3 scripts/view-retro.py --priority CRITICAL
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_PATHS = [
    Path.cwd() / "harness-feedback.log",
    Path.home() / "dev" / "samvil" / "harness-feedback.log",
]


def find_log() -> Path | None:
    for p in DEFAULT_PATHS:
        if p.exists():
            return p
    # Try plugin cache
    cache = Path.home() / ".claude" / "plugins" / "cache" / "samvil" / "samvil"
    if cache.exists():
        for sub in cache.iterdir():
            candidate = sub / "harness-feedback.log"
            if candidate.exists():
                return candidate
    return None


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def all_v2_items(data: list[dict]) -> list[dict]:
    """Flatten all suggestions_v2 across entries, annotating with run_id."""
    out = []
    for e in data:
        for it in e.get("suggestions_v2", []) or []:
            it = dict(it)
            it["_run_id"] = e.get("run_id", "?")
            out.append(it)
    return out


def cmd_summary(data: list[dict]) -> None:
    print(f"Entries: {len(data)}")
    all_items = all_v2_items(data)
    print(f"suggestions_v2 total: {len(all_items)}\n")

    # Per-entry table
    print(f"{'#':<3} {'run_id':<42} {'v2 count':>9}  {'legacy':>6}")
    print("-" * 70)
    for i, e in enumerate(data, 1):
        rid = e.get("run_id", "?")
        v2 = len(e.get("suggestions_v2", []) or [])
        legacy = len(e.get("suggestions", []) or [])
        print(f"{i:<3} {rid[:40]:<42} {v2:>9}  {legacy:>6}")

    # Priority breakdown
    prio_count = Counter(it.get("priority", "?") for it in all_items)
    prio_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "BENEFIT"]
    print("\nPriority breakdown:")
    for p in prio_order:
        if p in prio_count:
            print(f"  {p:<10} {prio_count[p]}")

    # Sprint breakdown
    sprints: dict[str, list[str]] = defaultdict(list)
    for it in all_items:
        sprints[it.get("sprint", "(unassigned)")].append(it.get("id", "?"))

    print("\nSprint breakdown:")
    for sp in sorted(sprints):
        ids = sprints[sp]
        print(f"  {sp}: {len(ids)} — {', '.join(sorted(ids))}")


def cmd_latest(data: list[dict]) -> None:
    if not data:
        print("(empty log)")
        return
    e = data[-1]
    print(f"Latest entry: {e.get('run_id', '?')}")
    print(f"Timestamp:    {e.get('timestamp', '?')}")
    items = e.get("suggestions_v2", []) or []
    print(f"\n{len(items)} suggestions_v2:\n")
    for it in items:
        _print_item(it)


def cmd_by_id(data: list[dict], query: str) -> None:
    for it in all_v2_items(data):
        if it.get("id", "") == query:
            _print_item(it, detailed=True)
            return
    print(f"No suggestion with id={query}")


def cmd_by_sprint(data: list[dict], n: str) -> None:
    key = f"Sprint {n}"
    matched = [it for it in all_v2_items(data) if key in it.get("sprint", "")]
    print(f"Sprint {n} — {len(matched)} items\n")
    for it in matched:
        _print_item(it)


def cmd_by_priority(data: list[dict], p: str) -> None:
    p = p.upper()
    matched = [it for it in all_v2_items(data) if it.get("priority", "") == p]
    print(f"Priority {p} — {len(matched)} items\n")
    for it in matched:
        _print_item(it)


def _print_item(it: dict, detailed: bool = False) -> None:
    iid = it.get("id", "?")
    prio = it.get("priority", "?")
    name = it.get("name", "")
    sprint = it.get("sprint", "")
    print(f"  {iid} [{prio}] {name}")
    if sprint:
        print(f"    sprint:  {sprint}")
    if detailed or True:  # always show component/problem for readability
        print(f"    component: {it.get('component', '')}")
        problem = it.get("problem", "")
        if problem:
            print(f"    problem:   {problem[:200]}{'...' if len(problem) > 200 else ''}")
    if detailed:
        fix = it.get("fix", "")
        impact = it.get("expected_impact", "")
        source = it.get("source", "")
        if fix:
            print(f"    fix:       {fix}")
        if impact:
            print(f"    impact:    {impact}")
        if source:
            print(f"    source:    {source}")
    print()


def main() -> int:
    path = find_log()
    if not path:
        print("ERROR: harness-feedback.log not found", file=sys.stderr)
        return 1

    data = load(path)
    args = sys.argv[1:]
    if not args:
        cmd_summary(data)
        return 0
    if args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--latest":
        cmd_latest(data)
        return 0
    if args[0] == "--id" and len(args) > 1:
        cmd_by_id(data, args[1])
        return 0
    if args[0] == "--sprint" and len(args) > 1:
        cmd_by_sprint(data, args[1])
        return 0
    if args[0] == "--priority" and len(args) > 1:
        cmd_by_priority(data, args[1])
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
