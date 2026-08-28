#!/usr/bin/env python3
"""Clean-commit Codex runtime harness and readiness checker."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def localhost_probe() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
    return True


def readiness() -> dict[str, object]:
    sys.path.insert(0, str(ROOT / "mcp"))
    from samvil_mcp.codex_installer import validate_activation_readiness

    result = validate_activation_readiness(ROOT)
    try:
        localhost_bind = localhost_probe()
    except OSError as error:
        localhost_bind = False
        result["blockers"] = [
            *result["blockers"],
            f"localhost bind probe is unavailable: {error}",
        ]
        result["ready"] = False
    result.update({
        "host_binary": shutil.which("codex") or "",
        "localhost_bind": localhost_bind,
        "tested_commit": _git("rev-parse", "HEAD"),
        "tested_tree": _git("rev-parse", "HEAD^{tree}"),
    })
    if not result["host_binary"]:
        result["blockers"] = [*result["blockers"], "codex binary is unavailable"]
        result["ready"] = False
    return result


def evaluate_mode(
    readiness_result: dict[str, object],
    *,
    check: bool,
    scenario: str,
    repeat: int,
) -> dict[str, object]:
    result = dict(readiness_result)
    blockers = list(result.get("blockers", []))
    result.update({
        "mode": "check" if check else "scenario",
        "scenario": "" if check else scenario,
        "repeat": repeat,
        "scenario_executed": False,
    })
    if repeat < 1:
        blockers.append("repeat must be at least 1")
    if not check:
        blockers.append("Codex runtime scenario execution is not implemented")
    if blockers:
        result["ready"] = False
    result["blockers"] = blockers
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--scenario")
    mode.add_argument("--all", action="store_true")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = evaluate_mode(
        readiness(),
        check=args.check,
        scenario=args.scenario or ("all" if args.all else ""),
        repeat=args.repeat,
    )
    if not args.check:
        status = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
        unexpected = [line for line in status if not line.endswith(" $CODEX_HOME/")]
        if unexpected:
            result["ready"] = False
            result["blockers"] = [*result["blockers"], "worktree is not clean for runtime evidence"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.receipt:
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
