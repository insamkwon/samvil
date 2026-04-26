#!/usr/bin/env python3
"""Run Phase 30 final E2E bundle dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.final_e2e import materialize_final_e2e_bundle  # noqa: E402
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


def _phase29_module():
    return _load_module(REPO / "scripts" / "phase29-evolve-cycle-closure-dogfood.py", "phase29_dogfood")


def _scenario(root: Path) -> dict:
    _phase29_module()._scenario(root)
    report = build_run_report(root)
    write_run_report(report, root)
    bundle = materialize_final_e2e_bundle(root)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)
    bundle_json = json.loads((root / ".samvil" / "final-e2e-bundle.json").read_text(encoding="utf-8"))

    if bundle["status"] != "pass":
        raise AssertionError(f"final E2E bundle did not pass: {bundle}")
    if bundle_json["chain"]["cycle_verdict"] != "closed":
        raise AssertionError(f"bad final chain: {bundle_json['chain']}")
    if report["final_e2e"]["status"] != "pass":
        raise AssertionError(f"run report missing final E2E: {report['final_e2e']}")
    if status_json["final_e2e"]["status"] != "pass":
        raise AssertionError(f"status JSON missing final E2E: {status_json['final_e2e']}")
    if "Final E2E: pass" not in status_human:
        raise AssertionError("human status did not expose final E2E bundle")

    return {
        "name": root.name,
        "status": bundle["status"],
        "cycle_verdict": bundle_json["chain"]["cycle_verdict"],
        "issue_count": bundle["issue_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase30-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase30-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase30 final E2E bundle dogfood passed")
            print(
                f"{result['name']}: status={result['status']} "
                f"cycle={result['cycle_verdict']} issues={result['issue_count']}"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
