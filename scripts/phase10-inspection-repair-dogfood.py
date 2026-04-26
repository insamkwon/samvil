#!/usr/bin/env python3
"""Run Phase 10 inspection repair execution dogfood."""

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

from samvil_mcp.inspection import build_inspection_report, write_inspection_report  # noqa: E402
from samvil_mcp.repair import (  # noqa: E402
    after_inspection_report_path,
    build_repair_plan,
    build_repair_report,
    write_repair_plan,
    write_repair_report,
)


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


def _state(root: Path, name: str) -> None:
    _write_json(root / "project.state.json", {
        "session_id": f"phase10-{name}",
        "project_name": name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })


def _broken_dashboard() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": "repair-dashboard",
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
            {"id": "dashboard-filter", "status": "fail", "message": "filter did not update chart"}
        ],
    }


def _fixed_dashboard(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "dashboard-fixed.png").write_text("png", encoding="utf-8")
    return {
        "schema_version": "1.0",
        "scenario": "repair-dashboard",
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "overflow": [],
                "screenshot": "dashboard-fixed.png",
            }
        ],
        "interactions": [
            {"id": "dashboard-filter", "status": "pass", "message": "filter updated chart"}
        ],
    }


def _broken_game() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": "repair-game",
        "viewports": [
            {
                "name": "mobile",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "screenshot": "missing-game.png",
                "canvas_nonblank": False,
            }
        ],
        "interactions": [
            {"id": "game-keyboard-score-restart", "status": "fail", "message": "restart did not reset score"}
        ],
    }


def _fixed_game(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "game-fixed.png").write_text("png", encoding="utf-8")
    return {
        "schema_version": "1.0",
        "scenario": "repair-game",
        "viewports": [
            {
                "name": "mobile",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "overflow": [],
                "screenshot": "game-fixed.png",
                "canvas_nonblank": True,
            }
        ],
        "interactions": [
            {"id": "game-keyboard-score-restart", "status": "pass", "message": "restart reset score"}
        ],
    }


def _run_case(base: Path, name: str, before_evidence: dict[str, Any], after_evidence: dict[str, Any]) -> dict[str, Any]:
    root = base / name
    root.mkdir(parents=True, exist_ok=True)
    (root / ".samvil").mkdir(exist_ok=True)
    _state(root, name)

    before = build_inspection_report(root, evidence=before_evidence)
    write_inspection_report(before, root)
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    after = build_inspection_report(root, evidence=after_evidence)
    after_inspection_report_path(root).write_text(json.dumps(after, indent=2), encoding="utf-8")
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_report(report, root)

    if before["summary"]["status"] != "fail":
        raise AssertionError(f"{name}: before inspection should fail")
    if after["summary"]["status"] != "pass":
        raise AssertionError(f"{name}: after inspection should pass")
    if report["summary"]["status"] != "verified":
        raise AssertionError(f"{name}: repair report should be verified")
    if report["summary"]["resolved_failures"] != before["summary"]["failed_checks"]:
        raise AssertionError(f"{name}: resolved count mismatch")

    status = _status_module()
    status_json = json.loads(status.render_json(root))
    if status_json["repair"]["report_status"] != "verified":
        raise AssertionError(f"{name}: status did not expose verified repair")
    if status_json["next_recommended_action"] != "repair verified: re-run release checks":
        raise AssertionError(f"{name}: status next action did not reflect verified repair")

    return {
        "name": name,
        "before_failed": before["summary"]["failed_checks"],
        "after_failed": after["summary"]["failed_checks"],
        "actions": plan["summary"]["total_actions"],
        "resolved": report["summary"]["resolved_failures"],
        "status": report["summary"]["status"],
        "next_action": status_json["next_recommended_action"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase10-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase10-")
        base = Path(temp.name)
    try:
        dashboard_root = base / "repair-dashboard"
        game_root = base / "repair-game"
        results = [
            _run_case(base, "repair-dashboard", _broken_dashboard(), _fixed_dashboard(dashboard_root)),
            _run_case(base, "repair-game", _broken_game(), _fixed_game(game_root)),
        ]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase10 inspection repair dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: before_failed={result['before_failed']} "
                    f"after_failed={result['after_failed']} actions={result['actions']} "
                    f"resolved={result['resolved']} status={result['status']} "
                    f"next_action='{result['next_action']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
