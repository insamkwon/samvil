#!/usr/bin/env python3
"""Run Phase 25 evolve apply plan dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.evolve_execution import (  # noqa: E402
    apply_evolve_apply_plan,
    materialize_evolve_apply_plan,
    materialize_evolve_proposal,
)
from samvil_mcp.evolve_loop import materialize_evolve_context  # noqa: E402
from samvil_mcp.qa_routing import materialize_qa_recovery_routing  # noqa: E402
from samvil_mcp.qa_synthesis import materialize_qa_synthesis, synthesize_qa_evidence  # noqa: E402
from samvil_mcp.telemetry import build_run_report, write_run_report  # noqa: E402


def _status_module():
    script = REPO / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load samvil-status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _seed() -> dict:
    return {
        "schema_version": "3.2",
        "name": "resume-coach",
        "description": "AI resume coach",
        "mode": "web",
        "version": 1,
        "core_experience": {"description": "Generate actionable resume feedback"},
        "features": [
            {
                "name": "AI summary",
                "acceptance_criteria": [
                    {"id": "AC-1", "description": "AI summary returns actionable feedback", "children": [], "status": "pending", "evidence": []}
                ],
            }
        ],
    }


def _synthesis(iteration: int) -> dict:
    return synthesize_qa_evidence({
        "iteration": iteration,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub response"}
        ]},
        "pass3": {"verdict": "PASS"},
    })


def _scenario(root: Path) -> dict:
    _write_json(root / "project.seed.json", _seed())
    _write_json(root / "project.state.json", {
        "session_id": "phase25-evolve-apply",
        "project_name": root.name,
        "current_stage": "evolve",
        "samvil_tier": "standard",
        "qa_history": [],
    })
    materialize_qa_synthesis(root, _synthesis(1))
    materialize_qa_synthesis(root, _synthesis(2))
    materialize_qa_recovery_routing(root)
    materialize_evolve_context(root)
    materialize_evolve_proposal(root)
    materialized = materialize_evolve_apply_plan(root)
    report_before = build_run_report(root)
    applied = apply_evolve_apply_plan(root)
    report_after = build_run_report(root)
    write_run_report(report_after, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)

    seed = json.loads((root / "project.seed.json").read_text(encoding="utf-8"))
    if materialized["status"] != "ready":
        raise AssertionError(f"apply plan not ready: {materialized}")
    if report_before["evolve_apply"]["status"] != "ready":
        raise AssertionError(f"run report missing ready apply plan: {report_before['evolve_apply']}")
    if applied["status"] != "applied":
        raise AssertionError(f"apply failed: {applied}")
    if seed["version"] != 2:
        raise AssertionError(f"seed version not advanced: {seed}")
    children = seed["features"][0]["acceptance_criteria"][0]["children"]
    if len(children) != 2:
        raise AssertionError(f"AC was not split: {children}")
    if not (root / "seed_history" / "v1.json").exists():
        raise AssertionError("seed backup missing")
    if status_json["evolve_apply"]["status"] != "applied":
        raise AssertionError(f"status JSON missing applied plan: {status_json['evolve_apply']}")
    if "Apply:   applied" not in status_human:
        raise AssertionError("human status did not expose applied plan")

    return {
        "name": root.name,
        "status": applied["status"],
        "from_version": applied["from_version"],
        "to_version": applied["to_version"],
        "mutations": materialized["mutations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase25-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase25-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase25 evolve apply dogfood passed")
            print(
                f"{result['name']}: status={result['status']} "
                f"v{result['from_version']}->v{result['to_version']} mutations={result['mutations']}"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
