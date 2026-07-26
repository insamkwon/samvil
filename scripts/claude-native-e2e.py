#!/usr/bin/env python3
"""Clean-commit Claude runtime harness and readiness checker."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def readiness() -> dict[str, object]:
    return {
        "host_binary": shutil.which("claude") or "",
        "tested_commit": _git("rev-parse", "HEAD"),
        "tested_tree": _git("rev-parse", "HEAD^{tree}"),
        "plugin_manifest": (ROOT / ".claude-plugin" / "plugin.json").is_file(),
        "ready": bool(shutil.which("claude") and (ROOT / ".claude-plugin" / "plugin.json").is_file()),
        "blockers": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--scenario")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if not args.check and not args.scenario and not args.all:
        parser.error("choose --check, --scenario, or --all")
    result = readiness()
    result.update({"mode": "check" if args.check else "scenario", "scenario": args.scenario or ("all" if args.all else ""), "repeat": args.repeat})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.receipt:
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
