"""Central synthesis for independent SAMVIL QA evidence."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QA_SYNTHESIS_SCHEMA_VERSION = "1.0"
QA_RESULTS_SCHEMA_VERSION = "1.0"
QA_CONVERGENCE_SCHEMA_VERSION = "1.0"
FUNCTIONAL_VERDICTS = {"PASS", "PARTIAL", "UNIMPLEMENTED", "FAIL"}
QUALITY_VERDICTS = {"PASS", "REVISE", "FAIL"}
PROTECTED_WRITES = {
    ".samvil/qa-report.md",
    ".samvil/events.jsonl",
    "project.state.json",
    "overall_verdict",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def qa_results_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "qa-results.json"


def qa_report_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "qa-report.md"


def qa_events_path(project_root: Path | str) -> Path:
    return Path(project_root) / ".samvil" / "events.jsonl"


def synthesize_qa_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return the central QA verdict from independently collected evidence."""
    pass1 = _normalize_pass1(evidence.get("pass1") or {})
    pass2_items = [_normalize_pass2_item(item) for item in evidence.get("pass2", {}).get("items", [])]
    pass3 = _normalize_pass3(evidence.get("pass3") or {})
    iteration = int(evidence.get("iteration") or 1)
    max_iterations = int(evidence.get("max_iterations") or 3)
    ownership = _ownership_violations(evidence.get("agent_writes") or [])
    counts = Counter(item["verdict"] for item in pass2_items)
    events = _events_for(pass2_items)

    verdict, reason, next_action = _central_verdict(
        pass1=pass1,
        pass2_items=pass2_items,
        pass2_counts=counts,
        pass3=pass3,
        ownership=ownership,
    )
    if verdict == "REVISE" and iteration >= max_iterations:
        verdict = "FAIL"
        reason = f"qa did not converge after {iteration} iterations"
        next_action = "report persistent QA failure to user"

    events.append({
        "event_type": "qa_verdict",
        "stage": "qa",
        "data": {
            "verdict": verdict,
            "iteration": iteration,
            "pass1": pass1["status"],
            "pass2": _pass2_status(counts),
            "pass3": pass3["verdict"],
        },
    })

    return {
        "schema_version": QA_SYNTHESIS_SCHEMA_VERSION,
        "gate": "qa_synthesis",
        "verdict": verdict,
        "reason": reason,
        "next_action": next_action,
        "issue_ids": _issue_ids(pass1=pass1, pass2_items=pass2_items, pass3=pass3, ownership=ownership),
        "iteration": iteration,
        "max_iterations": max_iterations,
        "pass1": pass1,
        "pass2": {
            "total": len(pass2_items),
            "counts": {name: counts.get(name, 0) for name in ("PASS", "PARTIAL", "UNIMPLEMENTED", "FAIL")},
            "items": pass2_items,
        },
        "pass3": pass3,
        "ownership_violations": ownership,
        "events": events,
        "protected_writes": sorted(PROTECTED_WRITES),
    }


def render_qa_synthesis(synthesis: dict[str, Any]) -> str:
    """Render a concise markdown QA synthesis report."""
    lines = [
        "# QA Synthesis",
        "",
        f"- Verdict: {synthesis.get('verdict') or '?'}",
        f"- Reason: {synthesis.get('reason') or '?'}",
        f"- Next action: {synthesis.get('next_action') or '?'}",
        f"- Iteration: {synthesis.get('iteration')}/{synthesis.get('max_iterations')}",
        "",
        "## Pass 1",
        f"- Mechanical: {(synthesis.get('pass1') or {}).get('status') or '?'}",
        "",
        "## Pass 2",
    ]
    counts = (synthesis.get("pass2") or {}).get("counts") or {}
    lines.append(
        "- Functional: "
        + ", ".join(f"{name}={counts.get(name, 0)}" for name in ("PASS", "PARTIAL", "UNIMPLEMENTED", "FAIL"))
    )
    for item in (synthesis.get("pass2") or {}).get("items") or []:
        lines.append(f"- {item.get('id') or '?'}: {item.get('verdict')} — {item.get('reason') or item.get('criterion') or ''}")
    lines.extend([
        "",
        "## Pass 3",
        f"- Quality: {(synthesis.get('pass3') or {}).get('verdict') or '?'}",
        "",
        "## Ownership",
    ])
    violations = synthesis.get("ownership_violations") or []
    if violations:
        for violation in violations:
            lines.append(f"- {violation.get('agent')}: {violation.get('path')}")
    else:
        lines.append("- No protected write violations.")
    convergence = synthesis.get("convergence") or {}
    if convergence:
        lines.extend([
            "",
            "## Convergence",
            f"- Gate: {convergence.get('verdict') or '?'}",
            f"- Reason: {convergence.get('reason') or '?'}",
            f"- Next action: {convergence.get('next_action') or '?'}",
            f"- Issue count: {convergence.get('issue_count', 0)}",
        ])
    return "\n".join(lines) + "\n"


def materialize_qa_synthesis(project_root: Path | str, synthesis: dict[str, Any]) -> dict[str, Any]:
    """Persist QA synthesis into report, structured results, events, and state."""
    root = Path(project_root)
    samvil = root / ".samvil"
    samvil.mkdir(parents=True, exist_ok=True)

    state = _load_project_state(root)
    convergence = evaluate_qa_convergence(synthesis, state.get("qa_history") or [])
    enriched = {**synthesis, "convergence": convergence}
    normalized = _qa_results_payload(root, enriched, convergence)
    results_path = _atomic_write_json(qa_results_path(root), normalized)
    report_path = _atomic_write_text(qa_report_path(root), render_qa_synthesis(enriched))
    event_count = _append_event_drafts(root, list(synthesis.get("events") or []) + _convergence_events(convergence))
    state_path = _update_project_state(root, enriched, convergence)
    return {
        "schema_version": QA_RESULTS_SCHEMA_VERSION,
        "status": "ok",
        "project_root": str(root),
        "qa_results_path": str(results_path),
        "qa_report_path": str(report_path),
        "events_path": str(qa_events_path(root)),
        "events_appended": event_count,
        "state_path": str(state_path) if state_path else "",
        "verdict": synthesis.get("verdict"),
        "next_action": synthesis.get("next_action"),
        "convergence": convergence,
    }


def read_qa_results(project_root: Path | str) -> dict[str, Any] | None:
    data = _load_json(qa_results_path(project_root))
    return data or None


def qa_summary(project_root: Path | str) -> dict[str, Any]:
    results = read_qa_results(project_root) or {}
    synthesis = results.get("synthesis") or {}
    return {
        "present": bool(results),
        "verdict": synthesis.get("verdict"),
        "reason": synthesis.get("reason"),
        "next_action": synthesis.get("next_action"),
        "convergence": results.get("convergence") or synthesis.get("convergence") or {},
        "iteration": synthesis.get("iteration"),
        "max_iterations": synthesis.get("max_iterations"),
        "pass2_counts": ((synthesis.get("pass2") or {}).get("counts") or {}),
        "pass3_verdict": ((synthesis.get("pass3") or {}).get("verdict")),
        "qa_results_path": str(qa_results_path(project_root)) if results else "",
        "qa_report_path": str(qa_report_path(project_root)) if qa_report_path(project_root).exists() else "",
    }


def evaluate_qa_convergence(synthesis: dict[str, Any], qa_history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Evaluate whether repeated QA revise cycles are converging."""
    history = [row for row in (qa_history or []) if isinstance(row, dict)]
    issue_ids = _extract_issue_ids(synthesis)
    previous_issue_ids = _previous_issue_ids(history)
    previous_count = len(previous_issue_ids) if previous_issue_ids is not None else None
    issue_count = len(issue_ids)
    verdict = str(synthesis.get("verdict") or "").upper()
    iteration = int(synthesis.get("iteration") or len(history) + 1 or 1)
    max_iterations = int(synthesis.get("max_iterations") or 3)

    if verdict == "PASS":
        gate_verdict = "pass"
        reason = "qa passed"
        next_action = "proceed to deploy or evolve offer"
    elif iteration >= max_iterations:
        gate_verdict = "failed"
        reason = f"qa did not converge before max_iterations={max_iterations}"
        next_action = "report persistent QA failure to user"
    elif previous_issue_ids is not None and issue_ids and issue_ids == previous_issue_ids:
        gate_verdict = "blocked"
        reason = "identical QA issues persisted across two consecutive iterations"
        next_action = "manual intervention: evolve seed, skip to retro, or fix manually"
    elif previous_count is not None and issue_count >= previous_count and issue_count > 0:
        gate_verdict = "blocked"
        reason = "QA issue count did not decrease from previous iteration"
        next_action = "inspect persistent QA issues before another auto-fix"
    elif verdict == "FAIL":
        gate_verdict = "failed"
        reason = str(synthesis.get("reason") or "qa failed")
        next_action = str(synthesis.get("next_action") or "report QA failure to user")
    else:
        gate_verdict = "continue"
        reason = "qa revise cycle may continue"
        next_action = str(synthesis.get("next_action") or "fix QA findings")

    resolved = sorted(previous_issue_ids - issue_ids) if previous_issue_ids is not None else []
    introduced = sorted(issue_ids - previous_issue_ids) if previous_issue_ids is not None else []
    return {
        "schema_version": QA_CONVERGENCE_SCHEMA_VERSION,
        "gate": "qa_convergence",
        "verdict": gate_verdict,
        "reason": reason,
        "next_action": next_action,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "issue_count": issue_count,
        "previous_issue_count": previous_count,
        "issue_ids": sorted(issue_ids),
        "previous_issue_ids": sorted(previous_issue_ids) if previous_issue_ids is not None else [],
        "resolved_issue_ids": resolved,
        "introduced_issue_ids": introduced,
    }


def _normalize_pass1(data: dict[str, Any]) -> dict[str, Any]:
    status = str(data.get("status") or data.get("verdict") or "PASS").upper()
    if status not in {"PASS", "FAIL"}:
        status = "FAIL"
    return {
        "status": status,
        "method": data.get("method") or "main-session",
        "issues": list(data.get("issues") or []),
    }


def _normalize_pass2_item(data: dict[str, Any]) -> dict[str, Any]:
    verdict = str(data.get("verdict") or "FAIL").upper()
    if verdict not in FUNCTIONAL_VERDICTS:
        verdict = "FAIL"
    evidence = data.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    return {
        "id": str(data.get("id") or data.get("ac_id") or "?"),
        "criterion": str(data.get("criterion") or data.get("description") or ""),
        "verdict": verdict,
        "method": str(data.get("method") or "independent"),
        "evidence": list(evidence),
        "reason": str(data.get("reason") or data.get("notes") or ""),
        "is_core_experience": bool(data.get("is_core_experience", False)),
    }


def _normalize_pass3(data: dict[str, Any]) -> dict[str, Any]:
    verdict = str(data.get("verdict") or "PASS").upper()
    if verdict not in QUALITY_VERDICTS:
        verdict = "FAIL"
    return {
        "verdict": verdict,
        "average_score": data.get("average_score"),
        "issues": list(data.get("issues") or []),
        "dimensions": dict(data.get("dimensions") or {}),
    }


def _ownership_violations(writes: list[dict[str, Any]]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for write in writes:
        agent = str(write.get("agent") or "")
        path = str(write.get("path") or "")
        if agent == "main-session":
            continue
        if path in PROTECTED_WRITES:
            violations.append({"agent": agent or "unknown-agent", "path": path})
    return violations


def _central_verdict(
    *,
    pass1: dict[str, Any],
    pass2_items: list[dict[str, Any]],
    pass2_counts: Counter[str],
    pass3: dict[str, Any],
    ownership: list[dict[str, str]],
) -> tuple[str, str, str]:
    if ownership:
        return "REVISE", "independent QA attempted protected writes", "discard protected writes and rerun central synthesis"
    if pass1["status"] == "FAIL":
        return "REVISE", "mechanical QA failed", "fix mechanical checks before functional synthesis"
    if any(item["verdict"] == "UNIMPLEMENTED" and item["is_core_experience"] for item in pass2_items):
        return "FAIL", "core experience is unimplemented", "report core implementation failure to user"
    if pass2_counts.get("FAIL", 0):
        return "REVISE", "functional QA found failing ACs", "fix failing acceptance criteria"
    if pass2_counts.get("UNIMPLEMENTED", 0):
        return "REVISE", "functional QA found unimplemented ACs", "replace stubs or hardcoded paths with real implementation"
    if pass3["verdict"] in {"REVISE", "FAIL"}:
        return "REVISE", "quality QA requires revision", "fix quality issues without changing functional verdicts"
    return "PASS", "all central QA gates passed", "proceed to deploy or evolve offer"


def _issue_ids(
    *,
    pass1: dict[str, Any],
    pass2_items: list[dict[str, Any]],
    pass3: dict[str, Any],
    ownership: list[dict[str, str]],
) -> list[str]:
    ids: set[str] = set()
    for issue in pass1.get("issues") or []:
        ids.add("pass1:" + _slug(str(issue)))
    for item in pass2_items:
        if item.get("verdict") in {"FAIL", "UNIMPLEMENTED"}:
            ids.add(f"pass2:{item.get('id') or '?'}:{item.get('verdict')}")
    for issue in pass3.get("issues") or []:
        ids.add("pass3:" + _slug(str(issue)))
    for violation in ownership:
        ids.add(f"ownership:{violation.get('agent') or '?'}:{violation.get('path') or '?'}")
    return sorted(ids)


def _extract_issue_ids(synthesis: dict[str, Any]) -> set[str]:
    explicit = synthesis.get("issue_ids")
    if isinstance(explicit, list):
        return {str(item) for item in explicit if str(item)}
    pass1 = synthesis.get("pass1") or {}
    pass2_items = ((synthesis.get("pass2") or {}).get("items") or [])
    pass3 = synthesis.get("pass3") or {}
    ownership = synthesis.get("ownership_violations") or []
    return set(_issue_ids(
        pass1=pass1,
        pass2_items=[item for item in pass2_items if isinstance(item, dict)],
        pass3=pass3,
        ownership=[item for item in ownership if isinstance(item, dict)],
    ))


def _previous_issue_ids(history: list[dict[str, Any]]) -> set[str] | None:
    for row in reversed(history):
        issue_ids = row.get("issue_ids")
        if isinstance(issue_ids, list):
            return {str(item) for item in issue_ids if str(item)}
    return None


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in normalized.split("-") if part)[:80] or "unknown"


def _pass2_status(counts: Counter[str]) -> str:
    if counts.get("FAIL", 0):
        return "FAIL"
    if counts.get("UNIMPLEMENTED", 0):
        return "UNIMPLEMENTED"
    return "PASS"


def _events_for(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in items:
        if item["verdict"] == "PARTIAL":
            events.append({
                "event_type": "qa_partial",
                "stage": "qa",
                "data": {"criterion": item["id"], "reason": item["reason"], "source": "pass2"},
            })
        elif item["verdict"] == "UNIMPLEMENTED":
            events.append({
                "event_type": "qa_unimplemented",
                "stage": "qa",
                "data": {
                    "criterion": item["id"],
                    "reason": item["reason"],
                    "is_core_experience": item["is_core_experience"],
                },
            })
    return events


def _qa_results_payload(root: Path, synthesis: dict[str, Any], convergence: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": QA_RESULTS_SCHEMA_VERSION,
        "project_root": str(root),
        "generated_at": _now_iso(),
        "source": "qa_synthesis",
        "synthesis": synthesis,
        "convergence": convergence,
    }


def _convergence_events(convergence: dict[str, Any]) -> list[dict[str, Any]]:
    if convergence.get("verdict") not in {"blocked", "failed"}:
        return []
    return [{
        "event_type": "qa_blocked" if convergence.get("verdict") == "blocked" else "qa_failed",
        "stage": "qa",
        "data": {
            "reason": convergence.get("reason"),
            "next_action": convergence.get("next_action"),
            "iteration": convergence.get("iteration"),
            "issue_ids": convergence.get("issue_ids") or [],
        },
    }]


def _append_event_drafts(root: Path, events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    path = qa_events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_project_state(root)
    session_id = state.get("session_id")
    now = _now_iso()
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            row = {
                "ts": now,
                "session_id": session_id,
                "event_type": event.get("event_type"),
                "stage": event.get("stage") or "qa",
                "data": event.get("data") or {},
                "source": "qa_synthesis",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(events)


def _update_project_state(root: Path, synthesis: dict[str, Any], convergence: dict[str, Any]) -> Path | None:
    path = root / "project.state.json"
    if not path.exists():
        path = root / ".samvil" / "state.json"
    state = _load_json(path) if path.exists() else {}
    if not isinstance(state, dict):
        state = {}
    history = state.get("qa_history")
    if not isinstance(history, list):
        history = []
    history.append({
        "iteration": synthesis.get("iteration"),
        "verdict": synthesis.get("verdict"),
        "reason": synthesis.get("reason"),
        "next_action": synthesis.get("next_action"),
        "issue_ids": synthesis.get("issue_ids") or convergence.get("issue_ids") or [],
        "convergence_verdict": convergence.get("verdict"),
        "convergence_reason": convergence.get("reason"),
        "pass2_counts": ((synthesis.get("pass2") or {}).get("counts") or {}),
        "pass3": ((synthesis.get("pass3") or {}).get("verdict")),
    })
    state["qa_history"] = history
    state["last_qa_verdict"] = synthesis.get("verdict")
    state["last_qa_next_action"] = synthesis.get("next_action")
    state["last_qa_convergence"] = convergence
    state["last_qa_at"] = _now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    return _atomic_write_json(path, state)


def _load_project_state(root: Path) -> dict[str, Any]:
    return _load_json(root / "project.state.json") or _load_json(root / ".samvil" / "state.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    return _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path
