#!/usr/bin/env python3
"""Run Phase 11 repair orchestration gate dogfood."""

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
    derive_repair_policy_signals,
    evaluate_repair_gate,
    write_repair_plan,
    write_repair_report,
)
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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _broken_evidence(scenario: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": scenario,
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": ["ReferenceError: broken"],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
        "interactions": [
            {"id": "primary-flow", "status": "pass", "message": "primary flow worked"}
        ],
    }


def _fixed_evidence(scenario: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scenario": scenario,
        "viewports": [
            {
                "name": "desktop",
                "loaded": True,
                "console_errors": [],
                "overflow_count": 0,
                "screenshot": "shot.png",
            }
        ],
        "interactions": [
            {"id": "primary-flow", "status": "pass", "message": "primary flow worked"}
        ],
    }


def _prepare_root(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "shot.png").write_text("png", encoding="utf-8")
    _write_json(root / "project.state.json", {
        "session_id": f"phase11-{name}",
        "project_name": name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })
    _write_jsonl(root / ".samvil" / "events.jsonl", [
        {"event_type": "repair_started", "stage": "repair", "timestamp": "2026-04-26T06:00:00Z"},
        {"event_type": "repair_plan_generated", "stage": "repair", "timestamp": "2026-04-26T06:01:00Z"},
        {"event_type": "repair_applied", "stage": "repair", "timestamp": "2026-04-26T06:02:00Z"},
        {"event_type": "repair_verified", "stage": "repair", "timestamp": "2026-04-26T06:03:00Z"},
    ])


def _case_missing_plan(base: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    root = base / "repair-gate-missing-plan"
    _prepare_root(root, root.name)
    before = build_inspection_report(root, evidence=_broken_evidence(root.name))
    write_inspection_report(before, root)
    return _assert_case(root, "blocked", "build repair plan"), None


def _case_plan_only(base: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    root = base / "repair-gate-plan-only"
    _prepare_root(root, root.name)
    before = build_inspection_report(root, evidence=_broken_evidence(root.name))
    write_inspection_report(before, root)
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    return _assert_case(root, "blocked", plan["next_action"]), None


def _case_verified(base: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = base / "repair-gate-verified"
    _prepare_root(root, root.name)
    before = build_inspection_report(root, evidence=_broken_evidence(root.name))
    after = build_inspection_report(root, evidence=_fixed_evidence(root.name))
    write_inspection_report(before, root)
    after_inspection_report_path(root).write_text(json.dumps(after, indent=2), encoding="utf-8")
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    repair_report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_report(repair_report, root)
    return _assert_case(root, "pass", "continue to release checks"), repair_report


def _assert_case(root: Path, expected_verdict: str, expected_action: str) -> dict[str, Any]:
    gate = evaluate_repair_gate(root)
    if gate["verdict"] != expected_verdict:
        raise AssertionError(f"{root.name}: expected {expected_verdict}, got {gate}")
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    run_gate = report["repair"]["gate"]
    status_gate = status_json["run_report"]["repair"]["gate"]
    if run_gate["verdict"] != expected_verdict or status_gate["verdict"] != expected_verdict:
        raise AssertionError(f"{root.name}: run/status gate mismatch")
    actions = [gate["next_action"], report["next_action"], status_json["next_recommended_action"]]
    if expected_action not in actions:
        raise AssertionError(f"{root.name}: next action mismatch")
    return {
        "name": root.name,
        "gate": gate["verdict"],
        "reason": gate["reason"],
        "next_action": gate["next_action"],
        "run_next_action": report["next_action"],
        "status_next_action": status_json["next_recommended_action"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase11-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase11-")
        base = Path(temp.name)
    try:
        missing, _ = _case_missing_plan(base)
        plan_only, _ = _case_plan_only(base)
        verified, repair_report = _case_verified(base)
        signals = derive_repair_policy_signals([repair_report, {**repair_report, "scenario": "repair-gate-verified-2"}])
        if not signals or signals[0]["dedupe_key"] != "repair-policy:console-error":
            raise AssertionError(f"expected repair policy signal, got {signals}")
        results = [missing, plan_only, verified]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results, "signals": signals}, indent=2))
        else:
            print("OK: phase11 repair orchestration dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: gate={result['gate']} reason='{result['reason']}' "
                    f"next_action='{result['next_action']}'"
                )
            print(f"policy_signals={len(signals)} first={signals[0]['dedupe_key']}")
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
