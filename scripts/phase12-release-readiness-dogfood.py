#!/usr/bin/env python3
"""Run Phase 12 release readiness gate dogfood."""

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
from samvil_mcp.release import (  # noqa: E402
    build_release_report,
    evaluate_release_gate,
    write_release_report,
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


def _prepare_root(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "shot.png").write_text("png", encoding="utf-8")
    _write_json(root / "project.state.json", {
        "session_id": f"phase12-{name}",
        "project_name": name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })


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


def _checks(*, failed: str = "") -> list[dict[str, Any]]:
    rows = [
        ("phase30_final_e2e_bundle", "python3 scripts/phase30-final-e2e-bundle-dogfood.py"),
        ("phase29_evolve_cycle_closure", "python3 scripts/phase29-evolve-cycle-closure-dogfood.py"),
        ("phase28_post_rebuild_qa", "python3 scripts/phase28-post-rebuild-qa-dogfood.py"),
        ("phase27_rebuild_reentry", "python3 scripts/phase27-rebuild-reentry-dogfood.py"),
        ("phase26_evolve_rebuild", "python3 scripts/phase26-evolve-rebuild-dogfood.py"),
        ("phase25_evolve_apply", "python3 scripts/phase25-evolve-apply-dogfood.py"),
        ("phase24_evolve_proposal", "python3 scripts/phase24-evolve-proposal-dogfood.py"),
        ("phase23_evolve_intake_context", "python3 scripts/phase23-evolve-intake-context-dogfood.py"),
        ("phase22_qa_recovery_routing", "python3 scripts/phase22-qa-recovery-routing-dogfood.py"),
        ("phase21_qa_convergence_gate", "python3 scripts/phase21-qa-convergence-gate-dogfood.py"),
        ("phase20_qa_materialization", "python3 scripts/phase20-qa-materialization-dogfood.py"),
        ("phase19_qa_synthesis_gate", "python3 scripts/phase19-qa-synthesis-gate-dogfood.py"),
        ("phase18_independent_evidence", "python3 scripts/phase18-independent-evidence-dogfood.py"),
        ("phase12_release_readiness", "python3 scripts/phase12-release-readiness-dogfood.py"),
        ("phase11_repair_orchestration", "python3 scripts/phase11-repair-orchestration-dogfood.py"),
        ("phase10_repair_regression", "python3 scripts/phase10-inspection-repair-dogfood.py"),
        ("phase8_browser_inspection", "python3 scripts/phase8-real-app-inspection.py"),
        ("pre_commit", "bash scripts/pre-commit-check.sh"),
    ]
    return [
        {
            "name": name,
            "status": "fail" if name == failed else "pass",
            "command": command,
            "message": "simulated dogfood result",
        }
        for name, command in rows
    ]


def _write_verified_repair(root: Path) -> None:
    before = build_inspection_report(root, evidence=_evidence(root.name, fixed=False))
    after = build_inspection_report(root, evidence=_evidence(root.name, fixed=True))
    write_inspection_report(before, root)
    after_inspection_report_path(root).write_text(json.dumps(after, indent=2), encoding="utf-8")
    plan = build_repair_plan(root, inspection_report=before)
    write_repair_plan(plan, root)
    report = build_repair_report(root, plan=plan, before_report=before, after_report=after)
    write_repair_report(report, root)


def _case_repair_blocked(base: Path) -> dict[str, Any]:
    root = base / "release-repair-blocked"
    _prepare_root(root, root.name)
    before = build_inspection_report(root, evidence=_evidence(root.name, fixed=False))
    write_inspection_report(before, root)
    release = build_release_report(root, checks=_checks())
    write_release_report(release, root)
    return _assert_case(root, "blocked", "repair gate is blocked", "build repair plan")


def _case_release_failed(base: Path) -> dict[str, Any]:
    root = base / "release-check-failed"
    _prepare_root(root, root.name)
    _write_verified_repair(root)
    release = build_release_report(root, checks=_checks(failed="pre_commit"))
    write_release_report(release, root)
    return _assert_case(
        root,
        "blocked",
        "required release checks are failed or missing",
        "fix release check: pre_commit",
    )


def _case_release_passed(base: Path) -> dict[str, Any]:
    root = base / "release-ready"
    _prepare_root(root, root.name)
    _write_verified_repair(root)
    release = build_release_report(root, checks=_checks())
    write_release_report(release, root)
    return _assert_case(root, "pass", "all required release checks passed", "ready to tag release")


def _assert_case(
    root: Path,
    expected_verdict: str,
    expected_reason: str,
    expected_action: str,
) -> dict[str, Any]:
    gate = evaluate_release_gate(root)
    if gate["verdict"] != expected_verdict:
        raise AssertionError(f"{root.name}: expected {expected_verdict}, got {gate}")
    if gate["reason"] != expected_reason:
        raise AssertionError(f"{root.name}: expected reason {expected_reason!r}, got {gate}")
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    run_gate = report["release"]["gate"]
    status_gate = status_json["run_report"]["release"]["gate"]
    if run_gate["verdict"] != expected_verdict or status_gate["verdict"] != expected_verdict:
        raise AssertionError(f"{root.name}: run/status release gate mismatch")
    actions = [gate["next_action"], report["next_action"], status_json["next_recommended_action"]]
    if expected_action not in actions:
        raise AssertionError(f"{root.name}: expected action {expected_action!r}, got {actions}")
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
        base = Path(tempfile.mkdtemp(prefix="samvil-phase12-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase12-")
        base = Path(temp.name)
    try:
        results = [
            _case_repair_blocked(base),
            _case_release_failed(base),
            _case_release_passed(base),
        ]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase12 release readiness dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: gate={result['gate']} reason='{result['reason']}' "
                    f"next_action='{result['next_action']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
