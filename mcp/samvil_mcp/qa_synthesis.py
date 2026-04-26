"""Central synthesis for independent SAMVIL QA evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any

QA_SYNTHESIS_SCHEMA_VERSION = "1.0"
FUNCTIONAL_VERDICTS = {"PASS", "PARTIAL", "UNIMPLEMENTED", "FAIL"}
QUALITY_VERDICTS = {"PASS", "REVISE", "FAIL"}
PROTECTED_WRITES = {
    ".samvil/qa-report.md",
    ".samvil/events.jsonl",
    "project.state.json",
    "overall_verdict",
}


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
    return "\n".join(lines) + "\n"


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
