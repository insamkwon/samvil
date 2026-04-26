from __future__ import annotations

import hashlib
import json
from pathlib import Path

from samvil_mcp.final_e2e import build_final_e2e_bundle, materialize_final_e2e_bundle


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _seed() -> dict:
    return {"name": "task-app", "version": 2}


def _seed_hash(seed: dict) -> str:
    payload = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project(root: Path) -> None:
    seed = _seed()
    digest = _seed_hash(seed)
    _write_json(root / "project.seed.json", seed)
    _write_json(root / ".samvil" / "qa-results.json", {
        "synthesis": {"verdict": "PASS", "iteration": 3, "issue_ids": []},
        "convergence": {"verdict": "pass"},
    })
    _write_json(root / ".samvil" / "qa-routing.json", {
        "primary_route": {"next_skill": "samvil-evolve"},
    })
    _write_json(root / ".samvil" / "evolve-context.json", {"focus": {"area": "functional_spec"}})
    _write_json(root / ".samvil" / "evolve-proposal.json", {"status": "ready"})
    _write_json(root / ".samvil" / "evolve-apply-plan.json", {"status": "applied"})
    _write_json(root / ".samvil" / "evolve-rebuild.json", {"status": "ready", "next_skill": "samvil-scaffold"})
    _write_json(root / ".samvil" / "rebuild-reentry.json", {
        "status": "ready",
        "next_skill": "samvil-scaffold",
        "seed_version": 2,
        "seed_sha256": digest,
    })
    _write_json(root / ".samvil" / "scaffold-input.json", {"seed_version": 2, "seed_sha256": digest})
    _write_json(root / ".samvil" / "scaffold-output.json", {"status": "built", "seed_version": 2, "seed_sha256": digest})
    _write_json(root / ".samvil" / "post-rebuild-qa.json", {
        "status": "ready",
        "next_skill": "samvil-qa",
        "seed_version": 2,
        "seed_sha256": digest,
    })
    _write_json(root / ".samvil" / "evolve-cycle.json", {
        "status": "ready",
        "verdict": "closed",
        "next_skill": "samvil-retro",
        "seed_version": 2,
        "seed_sha256": digest,
    })
    _write_json(root / ".samvil" / "run-report.json", {
        "evolve_cycle": {"present": True, "verdict": "closed"},
    })


def test_final_e2e_bundle_passes_complete_chain(tmp_path: Path) -> None:
    _project(tmp_path)

    bundle = build_final_e2e_bundle(tmp_path)

    assert bundle["status"] == "pass"
    assert bundle["chain"]["cycle_verdict"] == "closed"
    assert bundle["issues"] == []


def test_materialize_final_e2e_bundle_writes_artifact(tmp_path: Path) -> None:
    _project(tmp_path)

    result = materialize_final_e2e_bundle(tmp_path)

    assert result["status"] == "pass"
    assert (tmp_path / ".samvil" / "final-e2e-bundle.json").exists()


def test_final_e2e_bundle_blocks_seed_hash_mismatch(tmp_path: Path) -> None:
    _project(tmp_path)
    _write_json(tmp_path / ".samvil" / "scaffold-output.json", {
        "status": "built",
        "seed_version": 2,
        "seed_sha256": "wrong",
    })

    bundle = build_final_e2e_bundle(tmp_path)

    assert bundle["status"] == "blocked"
    assert "scaffold_output seed hash does not match project seed" in bundle["issues"]
