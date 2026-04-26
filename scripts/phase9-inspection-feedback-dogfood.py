#!/usr/bin/env python3
"""Run Phase 9 inspection feedback loop dogfood over broken fixtures."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.inspection import (  # noqa: E402
    build_inspection_report,
    derive_inspection_observations,
    write_inspection_report,
)
from samvil_mcp.telemetry import append_retro_observations  # noqa: E402


def _status_module():
    script = REPO / "scripts" / "samvil-status.py"
    spec = importlib.util.spec_from_file_location("samvil_status_script", script)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load samvil-status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_broken_project(root: Path, scenario: str, evidence: dict[str, Any]) -> None:
    (root / ".samvil").mkdir(parents=True, exist_ok=True)
    _write_json(root / "project.state.json", {
        "session_id": f"phase9-{scenario}",
        "project_name": scenario,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })
    _write_json(root / ".samvil" / "run-report.json", {
        "state": {
            "session_id": f"phase9-{scenario}",
            "project_name": scenario,
            "current_stage": "qa",
            "samvil_tier": "standard",
        },
        "events": {"total": 0},
        "timeline": {"failure_count": 0, "retry_count": 0, "stages": []},
        "claims": {"pending_subjects": []},
        "mcp_health": {"failures": 0, "total": 0},
        "continuation": {"present": False},
        "next_action": "continue with samvil-qa",
    })
    _write_json(root / ".samvil" / "inspection-evidence.json", evidence)


def _dashboard_evidence() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": "broken-dashboard-feedback",
        "url": "http://127.0.0.1:5173/",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": ["ReferenceError: revenue is not defined"],
                "overflow_count": 1,
                "overflow": [{"tag": "button", "text": "Date range filter label overflows"}],
                "screenshot": "missing-dashboard.png",
            }
        ],
        "interactions": [
            {
                "id": "dashboard-filter",
                "status": "fail",
                "message": "filter button did not update chart text",
            }
        ],
    }


def _game_evidence() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": "broken-game-feedback",
        "url": "http://127.0.0.1:5174/",
        "viewports": [
            {
                "name": "mobile",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "overflow": [],
                "screenshot": "missing-game.png",
                "canvas_nonblank": False,
            }
        ],
        "interactions": [
            {
                "id": "game-keyboard-score-restart",
                "status": "fail",
                "message": "ArrowRight did not move player and restart did not reset score",
            }
        ],
    }


def _run_broken_case(base: Path, name: str, evidence: dict[str, Any], expected_types: set[str]) -> dict[str, Any]:
    root = base / name
    _write_broken_project(root, name, evidence)
    report = build_inspection_report(root)
    write_inspection_report(report, root)
    observations = derive_inspection_observations(report)
    append_retro_observations(root, observations)

    failure_types = set(report["summary"]["failure_types"])
    missing = expected_types - failure_types
    if missing:
        raise AssertionError(f"{name}: missing failure types {sorted(missing)} from {sorted(failure_types)}")
    if report["summary"]["status"] != "fail":
        raise AssertionError(f"{name}: expected failing report")
    if len(observations) != len(report["failures"]):
        raise AssertionError(f"{name}: observation count did not match failures")

    status = _status_module()
    status_json = json.loads(status.render_json(root))
    next_action = status_json["next_recommended_action"]
    if not next_action.startswith("repair inspection failure:"):
        raise AssertionError(f"{name}: status next action did not prioritize inspection: {next_action}")
    retro_path = root / ".samvil" / "retro-observations.jsonl"
    retro_rows = retro_path.read_text(encoding="utf-8").splitlines()
    if len(retro_rows) != len(observations):
        raise AssertionError(f"{name}: retro observations were not persisted")
    return {
        "name": name,
        "status": report["summary"]["status"],
        "failure_types": sorted(failure_types),
        "failures": len(report["failures"]),
        "observations": len(observations),
        "next_action": next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase9-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase9-")
        base = Path(temp.name)
    try:
        results = [
            _run_broken_case(
                base,
                "broken-dashboard-feedback",
                _dashboard_evidence(),
                {"console-error", "layout-overflow", "screenshot-missing", "interaction-failed"},
            ),
            _run_broken_case(
                base,
                "broken-game-feedback",
                _game_evidence(),
                {"screenshot-missing", "canvas-blank", "interaction-failed"},
            ),
        ]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase9 inspection feedback dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: status={result['status']} failures={result['failures']} "
                    f"observations={result['observations']} types={','.join(result['failure_types'])} "
                    f"next_action='{result['next_action']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
