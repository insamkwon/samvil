#!/usr/bin/env python3
"""Run Phase 21 QA convergence gate dogfood."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

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


def _synthesis(iteration: int, items: list[dict]) -> dict:
    return synthesize_qa_evidence({
        "iteration": iteration,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": items},
        "pass3": {"verdict": "PASS"},
    })


def _scenario(root: Path) -> dict:
    _write_json(root / "project.state.json", {
        "session_id": "phase21-qa-convergence",
        "project_name": root.name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "qa_history": [],
    })

    first = _synthesis(1, [
        {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"},
        {"id": "AC-2", "criterion": "Export", "verdict": "FAIL", "reason": "button no-op"},
    ])
    first_materialized = materialize_qa_synthesis(root, first)
    if first_materialized["convergence"]["verdict"] != "continue":
        raise AssertionError(f"first revise should continue: {first_materialized}")

    second = _synthesis(2, [
        {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"},
        {"id": "AC-2", "criterion": "Export", "verdict": "FAIL", "reason": "button no-op"},
    ])
    second_materialized = materialize_qa_synthesis(root, second)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)

    convergence = second_materialized["convergence"]
    if convergence["verdict"] != "blocked":
        raise AssertionError(f"second identical revise should block: {convergence}")
    expected_action = "manual intervention: evolve seed, skip to retro, or fix manually"
    if report["qa"]["convergence"]["verdict"] != "blocked":
        raise AssertionError(f"run report did not expose blocked convergence: {report['qa']}")
    if report["next_action"] != expected_action:
        raise AssertionError(f"run report next action mismatch: {report['next_action']!r}")
    if status_json["next_recommended_action"] != expected_action:
        raise AssertionError(f"status next action mismatch: {status_json['next_recommended_action']!r}")
    if "QA gate: blocked" not in status_human:
        raise AssertionError("human status did not expose QA convergence gate")

    state = json.loads((root / "project.state.json").read_text(encoding="utf-8"))
    if len(state.get("qa_history") or []) != 2:
        raise AssertionError(f"state did not persist both QA iterations: {state}")
    events = [
        json.loads(line)
        for line in (root / ".samvil" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if events[-1].get("event_type") != "qa_blocked":
        raise AssertionError(f"last event should be qa_blocked: {events[-1]}")

    return {
        "name": root.name,
        "verdict": second_materialized["verdict"],
        "convergence": convergence["verdict"],
        "issue_count": convergence["issue_count"],
        "next_action": status_json["next_recommended_action"],
        "events": len(events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase21-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase21-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase21 QA convergence gate dogfood passed")
            print(
                f"{result['name']}: verdict={result['verdict']} "
                f"convergence={result['convergence']} issues={result['issue_count']} "
                f"events={result['events']} next_action='{result['next_action']}'"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
