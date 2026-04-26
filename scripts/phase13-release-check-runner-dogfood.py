#!/usr/bin/env python3
"""Run Phase 13 release check runner dogfood."""

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
from samvil_mcp.release import evaluate_release_gate, run_release_checks  # noqa: E402
from samvil_mcp.telemetry import build_run_report, write_run_report  # noqa: E402


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


def _prepare_root(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "shot.png").write_text("png", encoding="utf-8")
    _write_json(root / "project.state.json", {
        "session_id": f"phase13-{name}",
        "project_name": name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })
    _write_verified_repair(root)


def _evidence(scenario: str, *, fixed: bool) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": scenario,
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": [] if fixed else ["ReferenceError: broken"],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
        "interactions": [
            {"id": "primary-flow", "status": "pass", "message": "primary flow worked"}
        ],
    }


def _write_verified_repair(root: Path) -> None:
    before = build_inspection_report(root, evidence=_evidence(root.name, fixed=False))
    after = build_inspection_report(root, evidence=_evidence(root.name, fixed=True))
    write_inspection_report(before, root)
    after_inspection_report_path(root).write_text(json.dumps(after, indent=2), encoding="utf-8")
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_report(report, root)


def _commands(mode: str) -> list[dict[str, Any]]:
    rows = [
        {"name": "runner_alpha", "command": "python3 -c 'print(\"alpha ok\")'", "timeout_seconds": 5},
        {"name": "runner_beta", "command": "python3 -c 'print(\"beta ok\")'", "timeout_seconds": 5},
    ]
    if mode == "fail":
        rows.append({
            "name": "runner_fail",
            "command": "python3 -c 'import sys; print(\"runner failed\"); sys.exit(7)'",
            "timeout_seconds": 5,
        })
    elif mode == "timeout":
        rows.append({
            "name": "runner_timeout",
            "command": "python3 -c 'import time; time.sleep(2)'",
            "timeout_seconds": 0.1,
        })
    else:
        rows.append({"name": "runner_gamma", "command": "python3 -c 'print(\"gamma ok\")'", "timeout_seconds": 5})
    return rows


def _case(base: Path, name: str, mode: str, expected_verdict: str, expected_action: str) -> dict[str, Any]:
    root = base / name
    _prepare_root(root, name)
    report = run_release_checks(root, commands=_commands(mode), persist=True)
    gate = evaluate_release_gate(root, release_report=report)
    if gate["verdict"] != expected_verdict:
        raise AssertionError(f"{name}: expected {expected_verdict}, got {gate}")
    if gate["next_action"] != expected_action:
        raise AssertionError(f"{name}: expected action {expected_action!r}, got {gate}")
    run_report = build_run_report(root)
    write_run_report(run_report, root)
    status_json = json.loads(_status_module().render_json(root))
    status_gate = status_json["run_report"]["release"]["gate"]
    if status_gate["verdict"] != expected_verdict:
        raise AssertionError(f"{name}: status release gate mismatch")
    if status_json["release"]["source"] != "runner":
        raise AssertionError(f"{name}: status did not expose runner source")
    return {
        "name": name,
        "gate": gate["verdict"],
        "next_action": gate["next_action"],
        "report_status": report["summary"]["status"],
        "failed_checks": report["summary"]["failed_checks"],
        "source": report["source"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase13-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase13-")
        base = Path(temp.name)
    try:
        results = [
            _case(base, "runner-all-pass", "pass", "pass", "ready to tag release"),
            _case(base, "runner-command-failed", "fail", "blocked", "fix release check: runner_fail"),
            _case(base, "runner-command-timeout", "timeout", "blocked", "fix release check: runner_timeout"),
        ]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase13 release check runner dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: gate={result['gate']} report={result['report_status']} "
                    f"failed={result['failed_checks']} next_action='{result['next_action']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
