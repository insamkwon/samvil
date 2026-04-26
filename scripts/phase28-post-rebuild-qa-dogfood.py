#!/usr/bin/env python3
"""Run Phase 28 post-rebuild QA rejudge dogfood."""

from __future__ import annotations

import argparse
import hashlib
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
from samvil_mcp.evolve_rebuild import materialize_evolve_rebuild_handoff  # noqa: E402
from samvil_mcp.evolve_reentry import materialize_rebuild_reentry  # noqa: E402
from samvil_mcp.post_rebuild_qa import materialize_post_rebuild_qa  # noqa: E402
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


def _stable_hash(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
                    {
                        "id": "AC-1",
                        "description": "AI summary returns actionable feedback",
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
        "session_id": "phase28-post-rebuild-qa",
        "project_name": root.name,
        "current_stage": "qa",
        "samvil_tier": "standard",
        "qa_history": [],
    })
    materialize_qa_synthesis(root, _synthesis(1))
    materialize_qa_synthesis(root, _synthesis(2))
    materialize_qa_recovery_routing(root)
    materialize_evolve_context(root)
    materialize_evolve_proposal(root)
    materialize_evolve_apply_plan(root)
    apply_evolve_apply_plan(root)
    materialize_evolve_rebuild_handoff(root)
    materialize_rebuild_reentry(root)

    seed = json.loads((root / "project.seed.json").read_text(encoding="utf-8"))
    _write_json(root / ".samvil" / "scaffold-output.json", {
        "schema_version": "1.0",
        "status": "built",
        "seed_name": seed["name"],
        "seed_version": seed["version"],
        "seed_sha256": _stable_hash(seed),
        "artifacts": ["package.json", "src/App.tsx", "tests/qa.spec.ts"],
    })
    post_qa = materialize_post_rebuild_qa(root)
    report = build_run_report(root)
    write_run_report(report, root)
    status = _status_module()
    status_json = json.loads(status.render_json(root))
    status_human = status.render_human(root)
    post_qa_json = json.loads((root / ".samvil" / "post-rebuild-qa.json").read_text(encoding="utf-8"))
    marker = json.loads((root / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    if post_qa["status"] != "ready":
        raise AssertionError(f"post-rebuild QA not ready: {post_qa}")
    if marker["next_skill"] != "samvil-qa" or marker["from_stage"] != "scaffold":
        raise AssertionError(f"bad next-skill marker: {marker}")
    if post_qa_json["qa_request"]["seed_version"] != 2:
        raise AssertionError(f"bad QA request: {post_qa_json['qa_request']}")
    if report["post_rebuild_qa"]["status"] != "ready":
        raise AssertionError(f"run report missing post-rebuild QA: {report['post_rebuild_qa']}")
    if status_json["post_rebuild_qa"]["status"] != "ready":
        raise AssertionError(f"status JSON missing post-rebuild QA: {status_json['post_rebuild_qa']}")
    if "Post-rebuild QA: ready -> samvil-qa" not in status_human:
        raise AssertionError("human status did not expose post-rebuild QA")

    return {
        "name": root.name,
        "status": post_qa["status"],
        "next_skill": marker["next_skill"],
        "seed_version": post_qa_json["qa_request"]["seed_version"],
        "previous_issues": len(post_qa_json["previous_qa"]["issue_ids"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep generated temp project")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args()

    temp: tempfile.TemporaryDirectory[str] | None = None
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="samvil-phase28-"))
    else:
        temp = tempfile.TemporaryDirectory(prefix="samvil-phase28-")
        root = Path(temp.name)
    try:
        result = _scenario(root)
        if args.json:
            print(json.dumps({"status": "ok", "root": str(root), "result": result}, indent=2))
        else:
            print("OK: phase28 post-rebuild QA dogfood passed")
            print(
                f"{result['name']}: status={result['status']} next={result['next_skill']} "
                f"seed=v{result['seed_version']} previous_issues={result['previous_issues']}"
            )
        return 0
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
