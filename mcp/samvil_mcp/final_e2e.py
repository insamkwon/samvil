"""Final end-to-end bundle for the evolve/rebuild/QA closure chain."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINAL_E2E_SCHEMA_VERSION = "1.0"


def final_e2e_bundle_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "final-e2e-bundle.json"


def build_final_e2e_bundle(project_root: Path | str) -> dict[str, Any]:
    """Build a deterministic final E2E verdict from project-local artifacts."""
    root = Path(project_root)
    seed = _load_json(root / "project.seed.json")
    artifacts = {
        "qa_results": _load_json(root / ".samvil" / "qa-results.json"),
        "qa_routing": _load_json(root / ".samvil" / "qa-routing.json"),
        "evolve_context": _load_json(root / ".samvil" / "evolve-context.json"),
        "evolve_proposal": _load_json(root / ".samvil" / "evolve-proposal.json"),
        "evolve_apply": _load_json(root / ".samvil" / "evolve-apply-plan.json"),
        "evolve_rebuild": _load_json(root / ".samvil" / "evolve-rebuild.json"),
        "rebuild_reentry": _load_json(root / ".samvil" / "rebuild-reentry.json"),
        "scaffold_input": _load_json(root / ".samvil" / "scaffold-input.json"),
        "scaffold_output": _load_json(root / ".samvil" / "scaffold-output.json"),
        "post_rebuild_qa": _load_json(root / ".samvil" / "post-rebuild-qa.json"),
        "evolve_cycle": _load_json(root / ".samvil" / "evolve-cycle.json"),
        "run_report": _load_json(root / ".samvil" / "run-report.json"),
    }
    seed_hash = _stable_hash(seed) if seed else ""
    issues = _issues(seed, seed_hash, artifacts)
    status = "pass" if not issues else "blocked"
    return {
        "schema_version": FINAL_E2E_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "status": status,
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "artifact_presence": {name: bool(value) for name, value in artifacts.items()},
        "chain": _chain_summary(artifacts),
        "issues": issues,
        "next_action": "final E2E bundle passed" if status == "pass" else "fix final E2E bundle blockers",
    }


def materialize_final_e2e_bundle(project_root: Path | str) -> dict[str, Any]:
    bundle = build_final_e2e_bundle(project_root)
    path = _atomic_write_json(final_e2e_bundle_path(project_root), bundle)
    return {
        "schema_version": FINAL_E2E_SCHEMA_VERSION,
        "status": bundle["status"],
        "project_root": str(Path(project_root)),
        "final_e2e_bundle_path": str(path),
        "issue_count": len(bundle.get("issues") or []),
        "next_action": bundle.get("next_action"),
    }


def read_final_e2e_bundle(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(final_e2e_bundle_path(project_root))
    return data or None


def final_e2e_summary(project_root: Path | str) -> dict[str, Any]:
    bundle = read_final_e2e_bundle(project_root) or {}
    return {
        "present": bool(bundle),
        "status": bundle.get("status"),
        "seed_name": bundle.get("seed_name"),
        "seed_version": bundle.get("seed_version"),
        "issue_count": len(bundle.get("issues") or []),
        "next_action": bundle.get("next_action"),
        "path": str(final_e2e_bundle_path(project_root)) if bundle else "",
        "chain": bundle.get("chain") or {},
    }


def _issues(seed: dict[str, Any], seed_hash: str, artifacts: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    if not seed:
        issues.append("project.seed.json missing")
    for name, payload in artifacts.items():
        if not payload:
            issues.append(f"{name} artifact missing")
    qa_routing = artifacts["qa_routing"]
    evolve_apply = artifacts["evolve_apply"]
    evolve_rebuild = artifacts["evolve_rebuild"]
    rebuild_reentry = artifacts["rebuild_reentry"]
    scaffold_input = artifacts["scaffold_input"]
    scaffold_output = artifacts["scaffold_output"]
    post_rebuild_qa = artifacts["post_rebuild_qa"]
    evolve_cycle = artifacts["evolve_cycle"]
    run_report = artifacts["run_report"]

    primary_route = qa_routing.get("primary_route") or {}
    if qa_routing and primary_route.get("next_skill") != "samvil-evolve":
        issues.append("QA routing did not target samvil-evolve")
    if evolve_apply and evolve_apply.get("status") != "applied":
        issues.append("evolve apply plan is not applied")
    if evolve_rebuild and evolve_rebuild.get("status") != "ready":
        issues.append("evolve rebuild handoff is not ready")
    if evolve_rebuild and evolve_rebuild.get("next_skill") != "samvil-scaffold":
        issues.append("evolve rebuild handoff does not target samvil-scaffold")
    if rebuild_reentry and rebuild_reentry.get("status") != "ready":
        issues.append("rebuild reentry is not ready")
    if post_rebuild_qa and post_rebuild_qa.get("status") != "ready":
        issues.append("post-rebuild QA is not ready")
    if post_rebuild_qa and post_rebuild_qa.get("next_skill") != "samvil-qa":
        issues.append("post-rebuild QA does not target samvil-qa")
    if evolve_cycle and evolve_cycle.get("status") != "ready":
        issues.append("evolve cycle closure is not ready")
    if evolve_cycle and evolve_cycle.get("verdict") != "closed":
        issues.append("evolve cycle did not close")
    if evolve_cycle and evolve_cycle.get("next_skill") != "samvil-retro":
        issues.append("closed evolve cycle does not target samvil-retro")
    for name in ("scaffold_input", "scaffold_output", "post_rebuild_qa", "evolve_cycle"):
        payload = artifacts[name]
        if seed and payload and payload.get("seed_sha256") != seed_hash:
            issues.append(f"{name} seed hash does not match project seed")
        if seed and payload and payload.get("seed_version") != seed.get("version"):
            issues.append(f"{name} seed version does not match project seed")
    if run_report:
        report_cycle = run_report.get("evolve_cycle") or {}
        if report_cycle.get("verdict") != "closed":
            issues.append("run report does not expose closed evolve cycle")
    return issues


def _chain_summary(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "qa_route": ((artifacts["qa_routing"].get("primary_route") or {}).get("next_skill")),
        "evolve_apply": artifacts["evolve_apply"].get("status"),
        "rebuild": artifacts["evolve_rebuild"].get("next_skill"),
        "reentry": artifacts["rebuild_reentry"].get("next_skill"),
        "post_rebuild_qa": artifacts["post_rebuild_qa"].get("next_skill"),
        "cycle_verdict": artifacts["evolve_cycle"].get("verdict"),
        "cycle_next": artifacts["evolve_cycle"].get("next_skill"),
    }


def _stable_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
