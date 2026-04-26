"""Close or continue an evolve cycle after post-rebuild QA."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVOLVE_CYCLE_SCHEMA_VERSION = "1.0"


def evolve_cycle_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "evolve-cycle.json"


def next_skill_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "next-skill.json"


def build_evolve_cycle_closure(project_root: Path | str) -> dict[str, Any]:
    """Build the closure verdict for an evolve -> rebuild -> QA cycle."""
    root = Path(project_root)
    seed = _load_json(root / "project.seed.json")
    post_qa = _load_json(root / ".samvil" / "post-rebuild-qa.json")
    qa_results = _load_json(root / ".samvil" / "qa-results.json")
    seed_hash = _stable_hash(seed) if seed else ""
    previous = post_qa.get("previous_qa") or {}
    current = _current_qa(qa_results)
    issues = _issues(seed, seed_hash, post_qa, qa_results, previous, current)
    status = "ready" if not issues else "blocked"
    verdict = _cycle_verdict(current) if status == "ready" else "blocked"
    next_skill = _next_skill(verdict)
    marker = _next_skill_marker(verdict, next_skill, seed, seed_hash, current) if next_skill and status == "ready" else {}
    return {
        "schema_version": EVOLVE_CYCLE_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "post_rebuild_qa",
        "status": status,
        "verdict": verdict,
        "seed_name": seed.get("name"),
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "previous_qa": previous,
        "current_qa": current,
        "issues": issues,
        "next_skill": next_skill if status == "ready" else None,
        "marker": marker,
        "next_action": _next_action(verdict) if status == "ready" else "fix evolve cycle blockers",
    }


def materialize_evolve_cycle_closure(project_root: Path | str, *, persist_next_skill: bool = True) -> dict[str, Any]:
    closure = build_evolve_cycle_closure(project_root)
    path = _atomic_write_json(evolve_cycle_path(project_root), closure)
    marker_path = ""
    if persist_next_skill and closure.get("status") == "ready" and closure.get("marker"):
        marker_path = str(_atomic_write_json(next_skill_path(project_root), closure["marker"]))
    return {
        "schema_version": EVOLVE_CYCLE_SCHEMA_VERSION,
        "status": closure["status"],
        "verdict": closure["verdict"],
        "project_root": str(Path(project_root)),
        "evolve_cycle_path": str(path),
        "next_skill_path": marker_path,
        "next_skill": closure.get("next_skill"),
        "next_action": closure.get("next_action"),
    }


def read_evolve_cycle_closure(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(evolve_cycle_path(project_root))
    return data or None


def evolve_cycle_summary(project_root: Path | str) -> dict[str, Any]:
    closure = read_evolve_cycle_closure(project_root) or {}
    current = closure.get("current_qa") or {}
    return {
        "present": bool(closure),
        "status": closure.get("status"),
        "verdict": closure.get("verdict"),
        "seed_name": closure.get("seed_name"),
        "seed_version": closure.get("seed_version"),
        "current_verdict": current.get("verdict"),
        "current_iteration": current.get("iteration"),
        "next_skill": closure.get("next_skill"),
        "issue_count": len(closure.get("issues") or []),
        "next_action": closure.get("next_action"),
        "path": str(evolve_cycle_path(project_root)) if closure else "",
    }


def _issues(
    seed: dict[str, Any],
    seed_hash: str,
    post_qa: dict[str, Any],
    qa_results: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not seed:
        issues.append("project.seed.json missing")
    if not post_qa:
        issues.append(".samvil/post-rebuild-qa.json missing")
    if not qa_results:
        issues.append(".samvil/qa-results.json missing")
    if post_qa and post_qa.get("status") != "ready":
        issues.append("post-rebuild QA request is not ready")
    if seed and post_qa and post_qa.get("seed_sha256") != seed_hash:
        issues.append("post-rebuild QA seed hash does not match project seed")
    if seed and post_qa and post_qa.get("seed_version") != seed.get("version"):
        issues.append("post-rebuild QA seed version does not match project seed")
    previous_iteration = _as_int(previous.get("iteration"))
    current_iteration = _as_int(current.get("iteration"))
    if qa_results and not current.get("verdict"):
        issues.append("current QA verdict missing")
    if previous_iteration is not None and current_iteration is not None and current_iteration <= previous_iteration:
        issues.append("current QA result is not newer than post-rebuild QA request")
    return issues


def _current_qa(qa_results: dict[str, Any]) -> dict[str, Any]:
    synthesis = qa_results.get("synthesis") or {}
    convergence = qa_results.get("convergence") or synthesis.get("convergence") or {}
    return {
        "verdict": synthesis.get("verdict"),
        "reason": synthesis.get("reason"),
        "iteration": synthesis.get("iteration"),
        "max_iterations": synthesis.get("max_iterations"),
        "issue_ids": list(synthesis.get("issue_ids") or convergence.get("issue_ids") or []),
        "convergence_verdict": convergence.get("verdict"),
        "convergence_reason": convergence.get("reason"),
    }


def _cycle_verdict(current: dict[str, Any]) -> str:
    verdict = str(current.get("verdict") or "").upper()
    convergence = str(current.get("convergence_verdict") or "").lower()
    if verdict == "PASS":
        return "closed"
    if verdict == "FAIL" or convergence == "failed":
        return "failed"
    if verdict == "REVISE":
        return "continue_evolve"
    return "blocked"


def _next_skill(verdict: str) -> str | None:
    if verdict == "continue_evolve":
        return "samvil-evolve"
    if verdict in {"closed", "failed"}:
        return "samvil-retro"
    return None


def _next_action(verdict: str) -> str:
    if verdict == "closed":
        return "evolve cycle closed; capture retro or proceed to release"
    if verdict == "continue_evolve":
        return "continue with samvil-evolve using current QA findings"
    if verdict == "failed":
        return "stop evolve cycle and capture failure in samvil-retro"
    return "fix evolve cycle blockers"


def _next_skill_marker(
    verdict: str,
    next_skill: str,
    seed: dict[str, Any],
    seed_hash: str,
    current: dict[str, Any],
) -> dict[str, Any]:
    target_stage = "evolve" if next_skill == "samvil-evolve" else "retro"
    return {
        "schema_version": "1.0",
        "chain_via": "file_marker",
        "host": "portable",
        "next_skill": next_skill,
        "reason": _next_action(verdict),
        "from_stage": "qa",
        "created_by": "samvil-qa",
        "target_stage": target_stage,
        "cycle_verdict": verdict,
        "seed_version": seed.get("version"),
        "seed_sha256": seed_hash,
        "qa_verdict": current.get("verdict"),
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
