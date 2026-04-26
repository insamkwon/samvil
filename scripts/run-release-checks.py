#!/usr/bin/env python3
"""Run SAMVIL release checks and write .samvil/release-report.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.release import evaluate_release_gate, render_release_report, run_release_checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO), help="project root")
    parser.add_argument("--commands-json", default="", help="optional JSON list of command specs")
    parser.add_argument("--no-persist", action="store_true", help="do not write .samvil/release-report.json")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    commands = None
    if args.commands_json:
        data = json.loads(args.commands_json)
        commands = data if isinstance(data, list) else data.get("commands", [])
        if not isinstance(commands, list):
            raise SystemExit("--commands-json must contain a list")

    root = Path(args.root)
    report = run_release_checks(root, commands=commands, persist=not args.no_persist)
    gate = evaluate_release_gate(root, release_report=report)

    if args.format == "json":
        print(json.dumps({"status": "ok", "report": report, "gate": gate}, indent=2, ensure_ascii=False))
    else:
        print(render_release_report(report))
        print("")
        print(f"Release gate: {gate['verdict']} - {gate['reason']}")
        print(f"Next action: {gate['next_action']}")

    return 0 if gate["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
