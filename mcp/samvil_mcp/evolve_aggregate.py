"""Boot-time aggregator for samvil-evolve (T4.2 ultra-thin migration).

Single best-effort call that collects everything the (now ~150-LOC) skill body
needs but that is not already covered by `materialize_evolve_context`,
`check_convergence_gates`, `record_qa_failure`, `validate_evolved_seed`, etc.

In particular:

  1. **auto_trigger** — reads `project.state.json` and decides whether the
     pipeline should *automatically* offer Evolve (build_retries ≥ 5,
     qa_history ≥ 2, partial_count ≥ 5).
  2. **mode_resolution** — reads `project.config.json`, resolves
     `evolve_mode` (`spec-only` default), `evolve_max_cycles` (default 5),
     and `max_total_builds` quota state vs `state.build_retries`.
  3. **four_dim_baseline** — pulls the inputs the skill needs to score the
     Quality / Intent / Purpose / Beyond pre-Wonder evaluation
     (interview core problem excerpt, seed.description, qa verdict roll-up).
  4. **cycle_state** — current evolve cycle index + max + reached-cap flag.

The five existing concerns (evolve-context.json materialization, proposal,
apply plan, rebuild handoff, convergence gates) are deliberately *not*
duplicated here — the skill calls those tools directly. This module is the
"are we even allowed/auto-triggered to evolve, and what's our 4-dim
baseline?" pre-flight.

All reads are best-effort: missing files yield empty dicts and a non-fatal
entry in `errors[]`. Never raises for a missing file. Honors INV-1 (file is
SSOT) and INV-5 (graceful degradation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVOLVE_AGGREGATE_SCHEMA_VERSION = "1.0"

# Auto-trigger thresholds (mirrors SKILL.legacy.md "When to Run" section).
AUTO_TRIGGER_BUILD_RETRIES = 5
AUTO_TRIGGER_QA_HISTORY = 2
AUTO_TRIGGER_PARTIAL_COUNT = 5

# Defaults if config.json is missing or partial.
DEFAULT_EVOLVE_MODE = "spec-only"
DEFAULT_EVOLVE_MAX_CYCLES = 5
DEFAULT_MAX_TOTAL_BUILDS = 0  # 0 = unlimited


def _read_json(path: Path) -> dict[str, Any]:
    """Best-effort JSON read. Returns {} on any failure."""
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_text(path: Path, *, max_bytes: int = 4000) -> str:
    """Best-effort text read with byte cap (interview-summary.md can be long)."""
    try:
        if not path.exists():
            return ""
        with path.open("r", encoding="utf-8") as fh:
            return fh.read(max_bytes)
    except OSError:
        return ""


def _extract_core_problem(interview_md: str) -> str:
    """Pull the '핵심 문제' / 'Core problem' line(s) from interview summary.

    The interview-summary.md format places this near the top under a section
    header. We grab the first non-empty paragraph after the header. If no
    header is found, return the first non-empty 200 chars as a fallback.
    """
    if not interview_md:
        return ""
    lines = interview_md.splitlines()
    headers = ("핵심 문제", "Core problem", "Core Problem", "## Problem")
    for idx, line in enumerate(lines):
        if any(h in line for h in headers):
            # Collect following lines until next blank line or header.
            collected: list[str] = []
            for nxt in lines[idx + 1 : idx + 12]:
                stripped = nxt.strip()
                if not stripped:
                    if collected:
                        break
                    continue
                if stripped.startswith("#"):
                    break
                collected.append(stripped)
                if sum(len(c) for c in collected) > 320:
                    break
            return " ".join(collected)[:320]
    # Fallback — first ~200 chars of non-blank content.
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:200]
    return ""


def _resolve_auto_trigger(state: dict[str, Any]) -> dict[str, Any]:
    """Decide whether Evolve should be auto-suggested based on state metrics."""
    build_retries = int(state.get("build_retries") or 0)
    qa_history = state.get("qa_history") or []
    qa_history_count = len(qa_history) if isinstance(qa_history, list) else 0

    # partial_count: count PARTIAL verdicts across qa_history.
    partial_count = 0
    if isinstance(qa_history, list):
        for entry in qa_history:
            if isinstance(entry, dict):
                verdict = (entry.get("verdict") or "").upper()
                if verdict == "PARTIAL":
                    partial_count += 1

    triggers: list[str] = []
    if build_retries >= AUTO_TRIGGER_BUILD_RETRIES:
        triggers.append(f"build_retries={build_retries} ≥ {AUTO_TRIGGER_BUILD_RETRIES}")
    if qa_history_count >= AUTO_TRIGGER_QA_HISTORY:
        triggers.append(f"qa_history={qa_history_count} ≥ {AUTO_TRIGGER_QA_HISTORY}")
    if partial_count >= AUTO_TRIGGER_PARTIAL_COUNT:
        triggers.append(f"partial_count={partial_count} ≥ {AUTO_TRIGGER_PARTIAL_COUNT}")

    return {
        "should_offer": len(triggers) > 0,
        "triggers": triggers,
        "build_retries": build_retries,
        "qa_history_count": qa_history_count,
        "partial_count": partial_count,
    }


def _resolve_mode(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Resolve evolve_mode + cycle/build quota state."""
    mode = config.get("evolve_mode") or DEFAULT_EVOLVE_MODE
    if mode not in ("spec-only", "full"):
        mode = DEFAULT_EVOLVE_MODE

    max_cycles = int(config.get("evolve_max_cycles") or DEFAULT_EVOLVE_MAX_CYCLES)
    max_total_builds = int(config.get("max_total_builds") or DEFAULT_MAX_TOTAL_BUILDS)
    build_retries = int(state.get("build_retries") or 0)

    # Quota: 0 means unlimited; otherwise compare.
    build_quota_reached = bool(
        max_total_builds > 0 and build_retries >= max_total_builds
    )

    return {
        "evolve_mode": mode,
        "evolve_max_cycles": max_cycles,
        "max_total_builds": max_total_builds,
        "build_retries": build_retries,
        "build_quota_reached": build_quota_reached,
    }


def _resolve_cycle_state(state: dict[str, Any], max_cycles: int) -> dict[str, Any]:
    """Determine current evolve cycle index + cap status."""
    # state.evolve_cycle (set by skill on each pass) or fall back to
    # length of state.evolve_history.
    cycle = state.get("evolve_cycle")
    if cycle is None:
        history = state.get("evolve_history") or []
        cycle = len(history) if isinstance(history, list) else 0
    cycle = int(cycle or 0)
    return {
        "current_cycle": cycle,
        "max_cycles": max_cycles,
        "cap_reached": cycle >= max_cycles,
        "cycles_remaining": max(0, max_cycles - cycle),
    }


def _four_dim_baseline(
    seed: dict[str, Any],
    qa_results: dict[str, Any],
    interview_text: str,
) -> dict[str, Any]:
    """Surface inputs for the 4-dim Quality/Intent/Purpose/Beyond eval.

    The skill body assigns the 1-5 scores (LLM judgement). Here we just
    collect the raw evidence so the skill body can render them in a
    single pass without re-reading files.
    """
    synthesis = qa_results.get("synthesis") or {}
    pass2 = synthesis.get("pass2") or {}
    counts = pass2.get("counts") or {}
    return {
        "core_problem_excerpt": _extract_core_problem(interview_text),
        "seed_description": (seed.get("description") or "")[:320],
        "seed_name": seed.get("name") or "",
        "seed_version": seed.get("version") or 1,
        "qa_verdict": synthesis.get("verdict") or "",
        "qa_reason": synthesis.get("reason") or "",
        "ac_pass_count": int(counts.get("pass") or 0),
        "ac_fail_count": int(counts.get("fail") or 0),
        "ac_partial_count": int(counts.get("partial") or 0),
    }


def aggregate_evolve_context(project_root: str | Path) -> dict[str, Any]:
    """Boot-time aggregator for the samvil-evolve skill body.

    Reads (best-effort) from `project_root`:
      - `project.seed.json`, `project.state.json`, `project.config.json`
      - `.samvil/qa-results.json`
      - `interview-summary.md`

    Returns a dict shaped for direct use by the skill:

    {
      "schema_version": "1.0",
      "project_root": "...",
      "auto_trigger": {
        "should_offer": bool,
        "triggers": [str],     # human-readable reasons
        "build_retries": int,
        "qa_history_count": int,
        "partial_count": int,
      },
      "mode": {
        "evolve_mode": "spec-only" | "full",
        "evolve_max_cycles": int,
        "max_total_builds": int,    # 0 = unlimited
        "build_retries": int,
        "build_quota_reached": bool,  # if true → force stop regardless of mode
      },
      "cycle": {
        "current_cycle": int,
        "max_cycles": int,
        "cap_reached": bool,
        "cycles_remaining": int,
      },
      "four_dim_baseline": {
        "core_problem_excerpt": "...",
        "seed_description": "...",
        "seed_name": "...",
        "seed_version": int,
        "qa_verdict": "PASS|PARTIAL|FAIL",
        "qa_reason": "...",
        "ac_pass_count": int,
        "ac_fail_count": int,
        "ac_partial_count": int,
      },
      "errors": [str],   # non-fatal warnings (missing files, etc.)
    }

    Never raises. On any unexpected exception, the offending section is
    left as its empty default and a string is appended to `errors`.
    """
    errors: list[str] = []
    root = Path(project_root)

    seed = _read_json(root / "project.seed.json")
    if not seed:
        errors.append("project.seed.json missing or empty")

    state = _read_json(root / "project.state.json") or _read_json(
        root / ".samvil" / "state.json"
    )
    if not state:
        errors.append("project.state.json missing or empty")

    config = _read_json(root / "project.config.json")
    qa_results = _read_json(root / ".samvil" / "qa-results.json")
    if not qa_results:
        errors.append(".samvil/qa-results.json missing or empty")

    interview_text = _read_text(root / "interview-summary.md")

    try:
        auto_trigger = _resolve_auto_trigger(state)
    except Exception as exc:  # pragma: no cover — defensive
        auto_trigger = {
            "should_offer": False,
            "triggers": [],
            "build_retries": 0,
            "qa_history_count": 0,
            "partial_count": 0,
        }
        errors.append(f"auto_trigger: {exc}")

    try:
        mode = _resolve_mode(config, state)
    except Exception as exc:  # pragma: no cover — defensive
        mode = {
            "evolve_mode": DEFAULT_EVOLVE_MODE,
            "evolve_max_cycles": DEFAULT_EVOLVE_MAX_CYCLES,
            "max_total_builds": DEFAULT_MAX_TOTAL_BUILDS,
            "build_retries": 0,
            "build_quota_reached": False,
        }
        errors.append(f"mode: {exc}")

    try:
        cycle_state = _resolve_cycle_state(state, mode["evolve_max_cycles"])
    except Exception as exc:  # pragma: no cover — defensive
        cycle_state = {
            "current_cycle": 0,
            "max_cycles": mode["evolve_max_cycles"],
            "cap_reached": False,
            "cycles_remaining": mode["evolve_max_cycles"],
        }
        errors.append(f"cycle: {exc}")

    try:
        baseline = _four_dim_baseline(seed, qa_results, interview_text)
    except Exception as exc:  # pragma: no cover — defensive
        baseline = {
            "core_problem_excerpt": "",
            "seed_description": "",
            "seed_name": "",
            "seed_version": 1,
            "qa_verdict": "",
            "qa_reason": "",
            "ac_pass_count": 0,
            "ac_fail_count": 0,
            "ac_partial_count": 0,
        }
        errors.append(f"four_dim_baseline: {exc}")

    return {
        "schema_version": EVOLVE_AGGREGATE_SCHEMA_VERSION,
        "project_root": str(root),
        "auto_trigger": auto_trigger,
        "mode": mode,
        "cycle": cycle_state,
        "four_dim_baseline": baseline,
        "errors": errors,
    }
