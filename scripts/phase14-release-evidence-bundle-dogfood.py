#!/usr/bin/env python3
"""Run Phase 14 release evidence bundle dogfood."""

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

from samvil_mcp.release import (  # noqa: E402
    build_release_evidence_bundle,
    run_release_checks,
    write_release_evidence_bundle,
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
    _write_json(root / "project.state.json", {
        "session_id": f"phase14-{name}",
        "project_name": name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "seed_version": 1,
    })


def _commands(mode: str) -> list[dict[str, Any]]:
    if mode == "fail":
        return [
            {"name": "bundle_ok", "command": "python3 -c 'print(\"bundle ok\")'", "timeout_seconds": 5},
            {
                "name": "bundle_fail",
                "command": "python3 -c 'import sys; print(\"bundle bad stdout\"); sys.stderr.write(\"bundle bad stderr\\n\"); sys.exit(9)'",
                "timeout_seconds": 5,
            },
        ]
    return [
        {"name": "bundle_alpha", "command": "python3 -c 'print(\"alpha\")'", "timeout_seconds": 5},
        {"name": "bundle_beta", "command": "python3 -c 'print(\"beta\")'", "timeout_seconds": 5},
    ]


def _case(base: Path, name: str, mode: str, expected_status: str) -> dict[str, Any]:
    root = base / name
    _prepare_root(root, name)
    report = run_release_checks(root, commands=_commands(mode), persist=True)
    bundle = build_release_evidence_bundle(root)
    path = write_release_evidence_bundle(bundle, root)
    run_report = build_run_report(root)
    write_run_report(run_report, root)
    status_json = json.loads(_status_module().render_json(root))
    context = path.read_text(encoding="utf-8")
    if report["summary"]["status"] != expected_status:
        raise AssertionError(f"{name}: expected report {expected_status}, got {report['summary']}")
    if bundle["release"]["status"] != expected_status:
        raise AssertionError(f"{name}: bundle status mismatch")
    if status_json["release"]["bundle_path"] != str(path):
        raise AssertionError(f"{name}: status bundle path mismatch")
    if "Release Evidence Bundle" not in context:
        raise AssertionError(f"{name}: missing bundle heading")
    if expected_status == "blocked" and "bundle bad stderr" not in context:
        raise AssertionError(f"{name}: failed stderr tail missing from bundle")
    return {
        "name": name,
        "status": bundle["release"]["status"],
        "gate": bundle["gate"]["verdict"],
        "path": str(path),
        "checks": len(bundle["checks"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp projects")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        base = Path(tempfile.mkdtemp(prefix="samvil-phase14-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase14-")
        base = Path(temp.name)
    try:
        results = [
            _case(base, "bundle-all-pass", "pass", "pass"),
            _case(base, "bundle-failed-output", "fail", "blocked"),
        ]
        if args.json:
            print(json.dumps({"status": "ok", "base": str(base), "results": results}, indent=2))
        else:
            print("OK: phase14 release evidence bundle dogfood passed")
            for result in results:
                print(
                    f"{result['name']}: status={result['status']} gate={result['gate']} "
                    f"checks={result['checks']} bundle='{result['path']}'"
                )
            print(f"base: {base}")
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
