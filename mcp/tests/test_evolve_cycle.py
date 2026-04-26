from __future__ import annotations

import hashlib
import json
from pathlib import Path

from samvil_mcp.evolve_cycle import build_evolve_cycle_closure, materialize_evolve_cycle_closure


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _seed() -> dict:
    return {"name": "task-app", "version": 2}


def _seed_hash(seed: dict) -> str:
    payload = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project(root: Path, *, current_verdict: str = "PASS", current_iteration: int = 3) -> None:
    seed = _seed()
    digest = _seed_hash(seed)
    _write_json(root / "project.seed.json", seed)
    _write_json(root / ".samvil" / "post-rebuild-qa.json", {
        "status": "ready",
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "previous_qa": {
            "verdict": "REVISE",
            "iteration": 2,
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
        "next_skill": "samvil-qa",
    })
    _write_json(root / ".samvil" / "qa-results.json", {
        "synthesis": {
            "verdict": current_verdict,
            "reason": "qa result",
            "iteration": current_iteration,
            "max_iterations": 3,
            "issue_ids": [] if current_verdict == "PASS" else ["pass2:AC-1:UNIMPLEMENTED"],
        },
        "convergence": {
            "verdict": "pass" if current_verdict == "PASS" else "continue",
        },
    })


def test_evolve_cycle_closes_on_new_pass(tmp_path: Path) -> None:
    _project(tmp_path)

    closure = build_evolve_cycle_closure(tmp_path)

    assert closure["status"] == "ready"
    assert closure["verdict"] == "closed"
    assert closure["next_skill"] == "samvil-retro"
    assert closure["current_qa"]["iteration"] == 3


def test_materialize_evolve_cycle_writes_marker(tmp_path: Path) -> None:
    _project(tmp_path, current_verdict="REVISE")

    result = materialize_evolve_cycle_closure(tmp_path)
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert result["verdict"] == "continue_evolve"
    assert result["next_skill"] == "samvil-evolve"
    assert marker["cycle_verdict"] == "continue_evolve"


def test_evolve_cycle_blocks_when_qa_is_not_newer(tmp_path: Path) -> None:
    _project(tmp_path, current_verdict="PASS", current_iteration=2)

    closure = build_evolve_cycle_closure(tmp_path)

    assert closure["status"] == "blocked"
    assert "current QA result is not newer than post-rebuild QA request" in closure["issues"]
