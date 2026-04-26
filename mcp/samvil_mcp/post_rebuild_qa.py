"""Prepare QA rejudge input after a rebuilt evolved seed."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POST_REBUILD_QA_SCHEMA_VERSION = "1.0"


def post_rebuild_qa_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "post-rebuild-qa.json"


def scaffold_output_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "scaffold-output.json"


def next_skill_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "next-skill.json"


def build_post_rebuild_qa(project_root: Path | str) -> dict[str, Any]:
    """Build a deterministic QA rejudge request after rebuild/scaffold output."""
    root = Path(project_root)
    seed = _load_json(root / "project.seed.json")
    reentry = _load_json(root / ".samvil" / "rebuild-reentry.json")
    scaffold_input = _load_json(root / ".samvil" / "scaffold-input.json")
    scaffold_output = _load_json(scaffold_output_path(root))
    qa_results = _load_json(root / ".samvil" / "qa-results.json")
    seed_hash = _stable_hash(seed) if seed else ""
    issues = _issues(seed, seed_hash, reentry, scaffold_input, scaffold_output, qa_results)
    status = "ready" if not issues else "blocked"
    previous = _previous_qa(qa_results)
    marker = _next_skill_marker(seed, seed_hash, previous) if status == "ready" else {}
    qa_request = _qa_request(root, seed, seed_hash, scaffold_output, previous) if status == "ready" else {}
    return {
        "schema_version": POST_REBUILD_QA_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "rebuild_reentry",
        "status": status,
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "next_skill": marker.get("next_skill"),
        "from_stage": marker.get("from_stage"),
        "previous_qa": previous,
        "scaffold_output": _scaffold_summary(scaffold_output),
        "issues": issues,
        "qa_request": qa_request,
        "marker": marker,
        "next_action": "run samvil-qa against rebuilt output" if status == "ready" else "fix post-rebuild QA blockers",
    }


def materialize_post_rebuild_qa(project_root: Path | str, *, persist_next_skill: bool = True) -> dict[str, Any]:
    payload = build_post_rebuild_qa(project_root)
    path = _atomic_write_json(post_rebuild_qa_path(project_root), payload)
    marker_path = ""
    if persist_next_skill and payload.get("status") == "ready":
        marker_path = str(_atomic_write_json(next_skill_path(project_root), payload["marker"]))
    return {
        "schema_version": POST_REBUILD_QA_SCHEMA_VERSION,
        "status": payload["status"],
        "project_root": str(Path(project_root)),
        "post_rebuild_qa_path": str(path),
        "next_skill_path": marker_path,
        "next_skill": payload.get("next_skill"),
        "next_action": payload.get("next_action"),
    }


def read_post_rebuild_qa(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(post_rebuild_qa_path(project_root))
    return data or None


def post_rebuild_qa_summary(project_root: Path | str) -> dict[str, Any]:
    payload = read_post_rebuild_qa(project_root) or {}
    previous = payload.get("previous_qa") or {}
    return {
        "present": bool(payload),
        "status": payload.get("status"),
        "seed_name": payload.get("seed_name"),
        "seed_version": payload.get("seed_version"),
        "next_skill": payload.get("next_skill"),
        "from_stage": payload.get("from_stage"),
        "previous_verdict": previous.get("verdict"),
        "previous_issue_count": len(previous.get("issue_ids") or []),
        "issue_count": len(payload.get("issues") or []),
        "next_action": payload.get("next_action"),
        "path": str(post_rebuild_qa_path(project_root)) if payload else "",
        "scaffold_output_path": str(scaffold_output_path(project_root)) if scaffold_output_path(project_root).exists() else "",
    }


def _issues(
    seed: dict[str, Any],
    seed_hash: str,
    reentry: dict[str, Any],
    scaffold_input: dict[str, Any],
    scaffold_output: dict[str, Any],
    qa_results: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not seed:
        issues.append("project.seed.json missing")
    if not reentry:
        issues.append(".samvil/rebuild-reentry.json missing")
    if not scaffold_input:
        issues.append(".samvil/scaffold-input.json missing")
    if not scaffold_output:
        issues.append(".samvil/scaffold-output.json missing")
    if not qa_results:
        issues.append(".samvil/qa-results.json missing")
    if reentry and reentry.get("status") != "ready":
        issues.append("rebuild reentry is not ready")
    if scaffold_output and scaffold_output.get("status") not in {"built", "ready", "ok", "pass"}:
        issues.append("scaffold output is not built")
    if seed and scaffold_input:
        if scaffold_input.get("seed_version") != seed.get("version"):
            issues.append("scaffold input seed version does not match project seed")
        if scaffold_input.get("seed_sha256") != seed_hash:
            issues.append("scaffold input seed hash does not match project seed")
    if seed and reentry and reentry.get("seed_sha256") != seed_hash:
        issues.append("rebuild reentry seed hash does not match project seed")
    if seed and scaffold_output:
        if scaffold_output.get("seed_version") != seed.get("version"):
            issues.append("scaffold output seed version does not match project seed")
        if scaffold_output.get("seed_sha256") != seed_hash:
            issues.append("scaffold output seed hash does not match project seed")
    return issues


def _previous_qa(qa_results: dict[str, Any]) -> dict[str, Any]:
    synthesis = qa_results.get("synthesis") or {}
    convergence = qa_results.get("convergence") or synthesis.get("convergence") or {}
    return {
        "verdict": synthesis.get("verdict"),
        "reason": synthesis.get("reason"),
        "iteration": synthesis.get("iteration"),
        "max_iterations": synthesis.get("max_iterations"),
        "issue_ids": list(synthesis.get("issue_ids") or convergence.get("issue_ids") or []),
        "convergence_verdict": convergence.get("verdict"),
        "qa_results_path": qa_results.get("qa_results_path") or "",
    }


def _qa_request(
    root: Path,
    seed: dict[str, Any],
    seed_hash: str,
    scaffold_output: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "next_skill": "samvil-qa",
        "from_stage": "scaffold",
        "reason": "rejudge rebuilt evolved seed",
        "seed_path": str(root / "project.seed.json"),
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "scaffold_output_path": str(scaffold_output_path(root)),
        "scaffold_artifacts": list(scaffold_output.get("artifacts") or []),
        "previous_qa": previous,
        "required_passes": ["pass1_mechanical", "pass2_functional", "pass3_quality"],
        "write_contract": "central QA synthesis owns .samvil/qa-results.json and .samvil/qa-report.md",
    }


def _next_skill_marker(seed: dict[str, Any], seed_hash: str, previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "host": "portable",
        "next_skill": "samvil-qa",
        "reason": "rebuilt evolved seed is ready for QA rejudge",
        "from_stage": "scaffold",
        "created_by": "samvil-scaffold",
        "target_stage": "qa",
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "previous_verdict": previous.get("verdict"),
    }


def _scaffold_summary(scaffold_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(scaffold_output),
        "status": scaffold_output.get("status"),
        "seed_version": scaffold_output.get("seed_version"),
        "seed_sha256": scaffold_output.get("seed_sha256"),
        "artifact_count": len(scaffold_output.get("artifacts") or []),
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
