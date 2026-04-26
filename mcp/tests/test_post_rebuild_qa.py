from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.post_rebuild_qa import (
    build_post_rebuild_qa,
    materialize_post_rebuild_qa,
    post_rebuild_qa_summary,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _seed() -> dict:
    return {"name": "task-app", "version": 2, "features": [{"name": "tasks"}]}


def _seed_hash(seed: dict) -> str:
    import hashlib

    payload = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ready_project(root: Path) -> str:
    seed = _seed()
    digest = _seed_hash(seed)
    _write_json(root / "project.seed.json", seed)
    _write_json(root / ".samvil" / "rebuild-reentry.json", {
        "status": "ready",
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    })
    _write_json(root / ".samvil" / "scaffold-input.json", {
        "seed_name": "task-app",
        "seed_version": 2,
        "seed_sha256": digest,
        "next_skill": "samvil-scaffold",
    })
    _write_json(root / ".samvil" / "scaffold-output.json", {
        "status": "built",
        "seed_version": 2,
        "seed_sha256": digest,
        "artifacts": ["package.json", "src/App.tsx"],
    })
    _write_json(root / ".samvil" / "qa-results.json", {
        "synthesis": {
            "verdict": "REVISE",
            "reason": "stub response",
            "iteration": 2,
            "max_iterations": 3,
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
        "convergence": {
            "verdict": "blocked",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
        },
    })
    return digest


def test_build_post_rebuild_qa_ready(tmp_path: Path) -> None:
    digest = _ready_project(tmp_path)

    payload = build_post_rebuild_qa(tmp_path)

    assert payload["status"] == "ready"
    assert payload["next_skill"] == "samvil-qa"
    assert payload["seed_sha256"] == digest
    assert payload["previous_qa"]["issue_ids"] == ["pass2:AC-1:UNIMPLEMENTED"]
    assert payload["qa_request"]["required_passes"] == [
        "pass1_mechanical",
        "pass2_functional",
        "pass3_quality",
    ]


def test_materialize_post_rebuild_qa_writes_next_skill_marker(tmp_path: Path) -> None:
    _ready_project(tmp_path)

    result = materialize_post_rebuild_qa(tmp_path)
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))
    summary = post_rebuild_qa_summary(tmp_path)

    assert result["status"] == "ready"
    assert result["next_skill"] == "samvil-qa"
    assert marker["next_skill"] == "samvil-qa"
    assert marker["from_stage"] == "scaffold"
    assert summary["previous_issue_count"] == 1


def test_post_rebuild_qa_blocks_hash_mismatch(tmp_path: Path) -> None:
    _ready_project(tmp_path)
    _write_json(tmp_path / ".samvil" / "scaffold-output.json", {
        "status": "built",
        "seed_version": 2,
        "seed_sha256": "wrong",
        "artifacts": ["package.json"],
    })

    payload = build_post_rebuild_qa(tmp_path)

    assert payload["status"] == "blocked"
    assert "scaffold output seed hash does not match project seed" in payload["issues"]
    assert payload["qa_request"] == {}


def test_post_rebuild_qa_flags_missing_scaffold_input(tmp_path: Path) -> None:
    """When scaffold-input.json is absent, _issues must report it (T1.1 regression guard)."""
    _ready_project(tmp_path)
    # Remove scaffold-input.json — simulate scaffold not being invoked
    (tmp_path / ".samvil" / "scaffold-input.json").unlink()

    payload = build_post_rebuild_qa(tmp_path)

    assert payload["status"] == "blocked"
    assert any("scaffold-input.json" in issue for issue in payload["issues"])
