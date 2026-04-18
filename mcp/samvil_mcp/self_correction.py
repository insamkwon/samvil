"""Self-Correction Circuit (v2.5.0, Ouroboros #P6/#P9).

Wires QA failures → Evolve Wonder input. Makes Evolve loop actually
learn from failed cycles instead of blind retry.

Files managed:
  - .samvil/failed_acs.json: accumulated failed ACs across cycles
  - .samvil/qa-failures.json: structured QA failure reasons (current cycle)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def record_qa_failure(
    project_path: str,
    ac_id: str,
    ac_description: str,
    cycle: int,
    reason: str,
    suggestions: list[str] | None = None,
) -> dict:
    """Record a QA failure for this cycle.

    Returns dict with path written and total_failures.
    """
    samvil_dir = Path(project_path) / ".samvil"
    samvil_dir.mkdir(parents=True, exist_ok=True)

    failures_path = samvil_dir / "qa-failures.json"
    if failures_path.exists():
        try:
            failures = json.loads(failures_path.read_text())
        except (json.JSONDecodeError, OSError):
            failures = []
    else:
        failures = []

    failures.append({
        "ac_id": ac_id,
        "ac_description": ac_description,
        "cycle": cycle,
        "reason": reason,
        "suggestions": suggestions or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    failures_path.write_text(json.dumps(failures, indent=2, ensure_ascii=False))
    return {"path": str(failures_path), "total_failures": len(failures)}


def accumulate_failed_acs(project_path: str, qa_failures: list[dict]) -> dict:
    """Move current cycle's qa-failures.json → failed_acs.json accumulator.

    Called at end of each cycle. Preserves history across cycles.
    """
    samvil_dir = Path(project_path) / ".samvil"
    samvil_dir.mkdir(parents=True, exist_ok=True)

    accumulator_path = samvil_dir / "failed_acs.json"
    if accumulator_path.exists():
        try:
            accumulator = json.loads(accumulator_path.read_text())
        except (json.JSONDecodeError, OSError):
            accumulator = []
    else:
        accumulator = []

    accumulator.extend(qa_failures)
    accumulator_path.write_text(json.dumps(accumulator, indent=2, ensure_ascii=False))
    return {"path": str(accumulator_path), "total_accumulated": len(accumulator)}


def load_failed_acs_for_wonder(project_path: str) -> list[dict]:
    """Load accumulated failures for Wonder stage input.

    Returns list of failure dicts sorted by cycle (most recent first).
    """
    accumulator_path = Path(project_path) / ".samvil" / "failed_acs.json"
    if not accumulator_path.exists():
        return []

    try:
        failures = json.loads(accumulator_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    return sorted(failures, key=lambda f: f.get("cycle", 0), reverse=True)


def summarize_for_wonder(failures: list[dict]) -> str:
    """Generate Wonder-ready prompt from failed ACs.

    Returns human-readable summary with recurrent patterns.
    """
    if not failures:
        return "(No prior failures — first cycle or clean history)"

    # Group by ac_id to find recurring failures
    by_ac: dict[str, list[dict]] = {}
    for f in failures:
        ac_id = f.get("ac_id", "unknown")
        by_ac.setdefault(ac_id, []).append(f)

    lines = [f"# Prior Failures Summary ({len(failures)} failures across {len(by_ac)} ACs)\n"]

    # Recurring failures first (these are the most important signals)
    recurring = [(ac, fs) for ac, fs in by_ac.items() if len(fs) > 1]
    if recurring:
        lines.append("## 🔁 Recurring Failures (seen in multiple cycles)")
        for ac_id, fs in recurring:
            cycles = sorted({f.get("cycle", 0) for f in fs})
            lines.append(f"- {ac_id}: failed in cycles {cycles}")
            lines.append(f"  Latest reason: {fs[-1].get('reason', 'n/a')}")
        lines.append("")

    # Single failures
    single = [(ac, fs[0]) for ac, fs in by_ac.items() if len(fs) == 1]
    if single:
        lines.append("## One-off Failures")
        for ac_id, f in single[:10]:  # limit to 10
            lines.append(f"- {ac_id} (cycle {f.get('cycle', 0)}): {f.get('reason', 'n/a')}")
        lines.append("")

    lines.append("## Wonder Questions to Consider")
    lines.append("- Why did these ACs fail specifically?")
    lines.append("- Are they too large — should they be split into sub-ACs?")
    lines.append("- Are constraints unclear — did the scope creep?")
    lines.append("- Is there a common root cause across failures?")

    return "\n".join(lines)
