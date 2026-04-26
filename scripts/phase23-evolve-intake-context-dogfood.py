#!/usr/bin/env python3
"""Run Phase 23 evolve intake context dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

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
        "tech_stack": {"framework": "nextjs"},
        "core_experience": {"description": "Generate actionable resume feedback"},
        "features": [
            {
                "name": "AI summary",
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "User receives non-stub AI summary",
                        "children": [],
                        "status": "pending",
                        "evidence": [],
                    }
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
        "session_id": "phase23-evolve-intake",
        "project_name": root.name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "qa_history": [],
    })
    materialize_qa_synthesis(root, _synthesis(1))
    materialize_qa_synthesis(root, _synthesis(2))
    materialize_qa_recovery_routing(root)
    materialized = materialize_evolve_context(root)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)

    path = root / ".samvil" / "evolve-context.json"
    if not path.exists():
        raise AssertionError("evolve-context.json was not written")
    context = json.loads(path.read_text(encoding="utf-8"))
    if context["current_seed"]["name"] != "resume-coach":
        raise AssertionError(f"context missing current seed: {context}")
    if context["routing"]["next_skill"] != "samvil-evolve":
        raise AssertionError(f"context missing evolve route: {context['routing']}")
    if context["focus"]["area"] != "functional_spec":
        raise AssertionError(f"expected functional_spec focus: {context['focus']}")
    if context["qa"]["issue_ids"] != ["pass2:AC-1:UNIMPLEMENTED"]:
        raise AssertionError(f"expected QA issue ids: {context['qa']}")
    if not context["ground_truth"]["qa_results"]["present"]:
        raise AssertionError("context did not expose QA ground truth")
    if materialized["next_skill"] != "samvil-evolve":
        raise AssertionError(f"materialization did not return route: {materialized}")
    if report["evolve_context"]["focus_area"] != "functional_spec":
        raise AssertionError(f"run report missing evolve context: {report['evolve_context']}")
    if status_json["evolve_context"]["focus_area"] != "functional_spec":
        raise AssertionError(f"status JSON missing evolve context: {status_json['evolve_context']}")
    if "Evolve:  functional_spec" not in status_human:
        raise AssertionError("human status did not expose evolve context")

    return {
        "name": root.name,
        "next_skill": context["routing"]["next_skill"],
        "focus": context["focus"]["area"],
        "issues": context["focus"]["issue_count"],
        "path": str(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase23-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase23-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase23 evolve intake context dogfood passed")
            print(
                f"{result['name']}: next_skill={result['next_skill']} "
                f"focus={result['focus']} issues={result['issues']}"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
