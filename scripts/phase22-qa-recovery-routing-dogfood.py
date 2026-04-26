#!/usr/bin/env python3
"""Run Phase 22 QA recovery routing dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

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


def _synthesis(iteration: int) -> dict:
    return synthesize_qa_evidence({
        "iteration": iteration,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": [
            {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"}
        ]},
        "pass3": {"verdict": "PASS"},
    })


def _scenario(root: Path) -> dict:
    _write_json(root / "project.state.json", {
        "session_id": "phase22-qa-recovery-routing",
        "project_name": root.name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "qa_history": [],
    })
    materialize_qa_synthesis(root, _synthesis(1))
    materialize_qa_synthesis(root, _synthesis(2))
    routed = materialize_qa_recovery_routing(root)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)

    if routed["primary_route"]["next_skill"] != "samvil-evolve":
        raise AssertionError(f"expected samvil-evolve route, got {routed}")
    if routed["next_skill_path"] == "":
        raise AssertionError("expected next-skill marker to be written")
    marker = json.loads((root / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))
    if marker["next_skill"] != "samvil-evolve" or marker["from_stage"] != "qa":
        raise AssertionError(f"invalid marker: {marker}")
    if report["qa_routing"]["next_skill"] != "samvil-evolve":
        raise AssertionError(f"run report did not expose route: {report['qa_routing']}")
    expected_action = "evolve the seed or acceptance criteria before another build loop"
    if report["next_action"] != expected_action:
        raise AssertionError(f"run report next action mismatch: {report['next_action']!r}")
    if status_json["next_recommended_action"] != expected_action:
        raise AssertionError(f"status next action mismatch: {status_json['next_recommended_action']!r}")
    if status_json["qa_routing"]["next_skill"] != "samvil-evolve":
        raise AssertionError(f"status JSON did not expose route: {status_json['qa_routing']}")
    if "QA route: samvil-evolve" not in status_human:
        raise AssertionError("human status did not expose QA route")

    smoke = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "host-continuation-smoke.py"), str(root), "--expect-next", "samvil-evolve"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    if smoke.returncode != 0:
        raise AssertionError(smoke.stdout + smoke.stderr)

    return {
        "name": root.name,
        "next_skill": routed["primary_route"]["next_skill"],
        "route_type": routed["primary_route"]["route_type"],
        "next_action": status_json["next_recommended_action"],
        "marker": marker["next_skill"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase22-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase22-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase22 QA recovery routing dogfood passed")
            print(
                f"{result['name']}: next_skill={result['next_skill']} "
                f"route_type={result['route_type']} next_action='{result['next_action']}'"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
