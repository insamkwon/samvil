#!/usr/bin/env python3
"""Run Phase 29 evolve cycle closure dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.evolve_cycle import materialize_evolve_cycle_closure  # noqa: E402
from samvil_mcp.qa_synthesis import materialize_qa_synthesis, synthesize_qa_evidence  # noqa: E402
from samvil_mcp.telemetry import build_run_report, write_run_report  # noqa: E402


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _status_module():
    return _load_module(REPO / "scripts" / "samvil-status.py", "samvil_status_script")


def _phase28_module():
    return _load_module(REPO / "scripts" / "phase28-post-rebuild-qa-dogfood.py", "phase28_dogfood")


def _pass_synthesis() -> dict:
    return synthesize_qa_evidence({
        "iteration": 3,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {
                "id": "AC-1",
                "criterion": "AI summary",
                "verdict": "PASS",
                "reason": "rebuilt output returns actionable feedback",
                "evidence": ["src/App.tsx:10"],
            }
        ]},
        "pass3": {"verdict": "PASS"},
    })


def _scenario(root: Path) -> dict:
    _phase28_module()._scenario(root)
    materialize_qa_synthesis(root, _pass_synthesis())
    closure = materialize_evolve_cycle_closure(root)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)
    cycle_json = json.loads((root / ".samvil" / "evolve-cycle.json").read_text(encoding="utf-8"))
    marker = json.loads((root / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    if closure["status"] != "ready" or closure["verdict"] != "closed":
        raise AssertionError(f"cycle did not close: {closure}")
    if marker["next_skill"] != "samvil-retro" or marker["cycle_verdict"] != "closed":
        raise AssertionError(f"bad next-skill marker: {marker}")
    if cycle_json["current_qa"]["verdict"] != "PASS" or cycle_json["current_qa"]["iteration"] != 3:
        raise AssertionError(f"bad cycle QA context: {cycle_json['current_qa']}")
    if report["evolve_cycle"]["verdict"] != "closed":
        raise AssertionError(f"run report missing evolve cycle: {report['evolve_cycle']}")
    if status_json["evolve_cycle"]["verdict"] != "closed":
        raise AssertionError(f"status JSON missing evolve cycle: {status_json['evolve_cycle']}")
    if "Evolve cycle: closed -> samvil-retro" not in status_human:
        raise AssertionError("human status did not expose evolve cycle closure")

    return {
        "name": root.name,
        "status": closure["status"],
        "verdict": closure["verdict"],
        "next_skill": marker["next_skill"],
        "qa_iteration": cycle_json["current_qa"]["iteration"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase29-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase29-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase29 evolve cycle closure dogfood passed")
            print(
                f"{result['name']}: verdict={result['verdict']} next={result['next_skill']} "
                f"qa_iteration={result['qa_iteration']}"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
