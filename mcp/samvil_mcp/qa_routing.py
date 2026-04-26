"""Recovery routing for blocked QA convergence."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .qa_synthesis import read_qa_results

QA_ROUTING_SCHEMA_VERSION = "1.0"
NEXT_SKILL_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def qa_routing_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "qa-routing.json"


def next_skill_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "next-skill.json"


def build_qa_recovery_routing(
    project_root: Path | str,
    qa_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic next-step route from blocked QA results."""
    root = Path(project_root)
    results = qa_results if qa_results is not None else read_qa_results(root) or {}
    synthesis = results.get("synthesis") or {}
    convergence = results.get("convergence") or synthesis.get("convergence") or {}
    issue_ids = [str(item) for item in (convergence.get("issue_ids") or synthesis.get("issue_ids") or [])]
    issue_families = _issue_families(issue_ids)
    primary = _primary_route(synthesis, convergence, issue_families)
    alternatives = _alternatives(primary, synthesis, convergence, issue_families)
    routing = {
        "schema_version": QA_ROUTING_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "qa_recovery_routing",
        "status": "ready" if results else "missing_qa_results",
        "from_stage": "qa",
        "qa_verdict": synthesis.get("verdict"),
        "convergence_verdict": convergence.get("verdict"),
        "convergence_reason": convergence.get("reason"),
        "issue_ids": issue_ids,
        "issue_families": issue_families,
        "primary_route": primary,
        "alternative_routes": alternatives,
        "next_action": primary.get("next_action") or "run QA synthesis",
    }
    routing["next_skill_marker"] = _next_skill_marker(routing)
    return routing


def materialize_qa_recovery_routing(
    project_root: Path | str,
    qa_results: dict[str, Any] | None = None,
    *,
    persist_next_skill: bool = True,
) -> dict[str, Any]:
    """Persist QA recovery route and portable continuation marker."""
    root = Path(project_root)
    routing = build_qa_recovery_routing(root, qa_results=qa_results)
    route_path = _atomic_write_json(qa_routing_path(root), routing)
    marker_path = ""
    if persist_next_skill and routing["primary_route"].get("next_skill"):
        marker_path = str(_atomic_write_json(next_skill_path(root), routing["next_skill_marker"]))
    return {
        "schema_version": QA_ROUTING_SCHEMA_VERSION,
        "status": routing["status"],
        "project_root": str(root),
        "qa_routing_path": str(route_path),
        "next_skill_path": marker_path,
        "primary_route": routing["primary_route"],
        "next_action": routing["next_action"],
    }


def read_qa_recovery_routing(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(qa_routing_path(project_root))
    return data or None


def qa_routing_summary(project_root: Path | str) -> dict[str, Any]:
    routing = read_qa_recovery_routing(project_root) or {}
    primary = routing.get("primary_route") or {}
    marker_path = next_skill_path(project_root)
    return {
        "present": bool(routing),
        "status": routing.get("status"),
        "next_skill": primary.get("next_skill"),
        "route_type": primary.get("route_type"),
        "reason": primary.get("reason"),
        "next_action": routing.get("next_action") or primary.get("next_action"),
        "alternatives": routing.get("alternative_routes") or [],
        "qa_routing_path": str(qa_routing_path(project_root)) if routing else "",
        "next_skill_path": str(marker_path) if marker_path.exists() else "",
    }


def render_qa_recovery_routing(routing: dict[str, Any]) -> str:
    primary = routing.get("primary_route") or {}
    lines = [
        "# QA Recovery Routing",
        "",
        f"- Status: {routing.get('status') or '?'}",
        f"- QA verdict: {routing.get('qa_verdict') or '?'}",
        f"- Convergence: {routing.get('convergence_verdict') or '?'}",
        f"- Primary: {primary.get('next_skill') or '?'} ({primary.get('route_type') or '?'})",
        f"- Reason: {primary.get('reason') or '?'}",
        f"- Next action: {routing.get('next_action') or primary.get('next_action') or '?'}",
        "",
        "## Alternatives",
    ]
    alternatives = routing.get("alternative_routes") or []
    if not alternatives:
        lines.append("- (none)")
    for route in alternatives:
        lines.append(f"- {route.get('next_skill')}: {route.get('reason')}")
    return "\n".join(lines) + "\n"


def _primary_route(
    synthesis: dict[str, Any],
    convergence: dict[str, Any],
    issue_families: dict[str, int],
) -> dict[str, Any]:
    conv = str(convergence.get("verdict") or "")
    verdict = str(synthesis.get("verdict") or "")
    reason = str(convergence.get("reason") or synthesis.get("reason") or "")
    if conv not in {"blocked", "failed"}:
        return _route(
            "samvil-qa",
            "qa_rerun",
            "QA convergence is not blocked",
            "continue QA revise loop",
            confidence="medium",
        )
    if issue_families.get("ownership"):
        return _route(
            "samvil-retro",
            "retro",
            "independent QA ownership violation needs process correction",
            "record ownership violation and tighten QA contract",
            confidence="high",
        )
    if issue_families.get("pass1"):
        return _route(
            "samvil-build",
            "manual_repair",
            "mechanical QA is still failing",
            "fix mechanical build or smoke failures before rerunning QA",
            confidence="high",
        )
    if issue_families.get("pass2"):
        return _route(
            "samvil-evolve",
            "seed_evolve",
            "functional acceptance criteria did not converge",
            "evolve the seed or acceptance criteria before another build loop",
            confidence="high",
        )
    if issue_families.get("pass3"):
        return _route(
            "samvil-build",
            "manual_repair",
            "quality findings persisted without functional failures",
            "apply targeted UX/accessibility/code-quality repair before rerunning QA",
            confidence="medium",
        )
    if conv == "failed" or verdict == "FAIL":
        return _route(
            "samvil-retro",
            "retro",
            reason or "QA failed after max iterations",
            "stop the run and capture retro findings",
            confidence="medium",
        )
    return _route(
        "samvil-evolve",
        "seed_evolve",
        reason or "QA convergence blocked",
        "evolve seed or request manual decision",
        confidence="medium",
    )


def _alternatives(
    primary: dict[str, Any],
    synthesis: dict[str, Any],
    convergence: dict[str, Any],
    issue_families: dict[str, int],
) -> list[dict[str, Any]]:
    routes = [
        _route("samvil-evolve", "seed_evolve", "change ambiguous or impossible acceptance criteria", "run samvil-evolve"),
        _route("samvil-build", "manual_repair", "make a targeted implementation repair", "run samvil-build with QA issue context"),
        _route("samvil-retro", "retro", "stop and capture harness/process learning", "run samvil-retro"),
    ]
    primary_skill = primary.get("next_skill")
    out = [route for route in routes if route.get("next_skill") != primary_skill]
    if issue_families.get("pass3") and primary_skill != "samvil-evolve":
        out.insert(0, _route("samvil-evolve", "seed_evolve", "quality failures may reflect underspecified UX criteria", "evolve UX acceptance criteria"))
    return _dedupe_routes(out)


def _route(
    next_skill: str,
    route_type: str,
    reason: str,
    next_action: str,
    *,
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "next_skill": next_skill,
        "route_type": route_type,
        "reason": reason,
        "next_action": next_action,
        "confidence": confidence,
    }


def _issue_families(issue_ids: list[str]) -> dict[str, int]:
    counts = {"pass1": 0, "pass2": 0, "pass3": 0, "ownership": 0, "other": 0}
    for issue_id in issue_ids:
        family = issue_id.split(":", 1)[0]
        if family in counts:
            counts[family] += 1
        else:
            counts["other"] += 1
    return counts


def _next_skill_marker(routing: dict[str, Any]) -> dict[str, Any]:
    primary = routing.get("primary_route") or {}
    return {
        "schema_version": NEXT_SKILL_SCHEMA_VERSION,
        "chain_via": "file_marker",
        "next_skill": primary.get("next_skill"),
        "reason": primary.get("reason") or routing.get("convergence_reason") or "QA recovery routing",
        "from_stage": "qa",
        "source": "qa_recovery_routing",
        "route_type": primary.get("route_type"),
        "next_action": primary.get("next_action") or routing.get("next_action"),
    }


def _dedupe_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for route in routes:
        key = str(route.get("next_skill"))
        if key in seen:
            continue
        seen.add(key)
        out.append(route)
    return out


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
