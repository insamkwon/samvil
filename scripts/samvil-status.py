#!/usr/bin/env python3
"""samvil status — one-screen TUI for the current project.

Sprint 1 MVP per HANDOFF-v3.2-DECISIONS.md §6.1. Zero LLM calls. Runs
against local files only:

  .samvil/state.json          (sprint, stage, samvil_tier)
  .samvil/claims.jsonl        (ledger)
  .samvil/experiments.jsonl   (performance budget + initial-estimate tracking)
  .samvil/events.jsonl        (last activity)

Panes in MVP (other panes deferred to later sprints per §6.1):
  - Sprint + stage
  - Gate latest verdicts
  - Performance budget consumption
  - Next recommended action (from the latest non-PASS gate)

Usage:
  python scripts/samvil-status.py
  python scripts/samvil-status.py --root /path/to/project
  python scripts/samvil-status.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SELF = Path(__file__).resolve().parent
REPO = SELF.parent


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_gate_verdicts(claims: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for r in claims:
        if r.get("type") != "gate_verdict":
            continue
        subject = r.get("subject", "")
        ts = r.get("ts", "")
        if subject not in latest or latest[subject].get("ts", "") < ts:
            latest[subject] = r
    return latest


def next_recommended_action(gate_verdicts: dict[str, dict]) -> str:
    """Pick the most recent non-pass verdict and render its required_action."""
    non_pass = [
        v
        for v in gate_verdicts.values()
        if (v.get("meta", {}) or {}).get("verdict")
        not in (None, "pass", "skip")
    ]
    if not non_pass:
        return "(nothing urgent — latest gates all pass)"
    latest = sorted(non_pass, key=lambda r: r.get("ts", ""))[-1]
    meta = latest.get("meta", {}) or {}
    action = (meta.get("required_action") or {}).get("type", "ask_user")
    subject = latest.get("subject", "?")
    return f"{subject}: {meta.get('verdict','?')} → {action}"


def experiment_coverage(experiments: list[dict]) -> tuple[int, int]:
    """Return (with_observations, total) — the 80% target is the §7 exit gate."""
    with_obs = sum(1 for e in experiments if e.get("observations"))
    return with_obs, len(experiments)


def budget_summary(state: dict) -> str:
    """Budget enforcement ships in Sprint 6 (⑬). For now show placeholder
    counts if the file hasn't been populated yet."""
    budget = state.get("performance_budget") or {}
    if not budget:
        return "(not yet initialized — Sprint 6 ships budget enforcement)"
    consumed = budget.get("consumed", {})
    ceiling = budget.get("ceiling", {})
    parts = []
    for key in ("wall_time_minutes", "llm_calls", "estimated_cost_usd"):
        c = consumed.get(key)
        max_ = ceiling.get(key)
        if c is None or max_ is None:
            continue
        pct = (c / max_ * 100.0) if max_ else 0.0
        parts.append(f"{key}={c:.1f}/{max_} ({pct:.0f}%)")
    return "  ".join(parts) or "(empty)"


def render_human(root: Path) -> str:
    state = _load_json(root / ".samvil" / "state.json")
    claims = _load_jsonl(root / ".samvil" / "claims.jsonl")
    experiments = _load_jsonl(root / ".samvil" / "experiments.jsonl")

    # v3.1 stored the field under the legacy name. Read both, preferring
    # the new one. After v3.3 the legacy branch is removed.
    samvil_tier = (
        state.get("samvil_tier")
        or state.get("agent_tier")  # glossary-allow: legacy state.json fallback
        or "standard"
    )
    sprint = state.get("sprint") or state.get("current_sprint") or "?"
    stage = state.get("current_stage") or state.get("stage") or "?"

    gate_verdicts = latest_gate_verdicts(claims)
    pending_claims = [c for c in claims if c.get("status") == "pending"]
    obs_with, obs_total = experiment_coverage(experiments)

    lines: list[str] = []
    lines.append(f"samvil status — root={root}")
    lines.append("=" * 60)
    lines.append(f"Sprint:  {sprint}")
    lines.append(f"Stage:   {stage}")
    lines.append(f"Tier:    {samvil_tier}")
    lines.append("")
    lines.append("Gate verdicts (latest):")
    if not gate_verdicts:
        lines.append("  (no gate_verdict claims recorded yet)")
    else:
        for g, v in sorted(gate_verdicts.items()):
            meta = v.get("meta", {}) or {}
            lines.append(
                f"  {g:<22} {meta.get('verdict','?'):<9} "
                f"{meta.get('reason','')[:60]}"
            )
    lines.append("")
    lines.append(f"Pending claims:    {len(pending_claims)}")
    if obs_total > 0:
        pct = obs_with / obs_total * 100.0
        lines.append(
            f"Experiments:       {obs_with}/{obs_total} calibrated "
            f"({pct:.0f}% — Sprint 1 exit target: 80%)"
        )
    else:
        lines.append(
            "Experiments:       0 (run scripts/seed-experiments.py to bootstrap)"
        )
    lines.append("")
    lines.append(f"Budget:            {budget_summary(state)}")
    lines.append("")
    lines.append(f"Next action:       {next_recommended_action(gate_verdicts)}")
    return "\n".join(lines)


def render_json(root: Path) -> str:
    state = _load_json(root / ".samvil" / "state.json")
    claims = _load_jsonl(root / ".samvil" / "claims.jsonl")
    experiments = _load_jsonl(root / ".samvil" / "experiments.jsonl")
    samvil_tier = state.get("samvil_tier") or "standard"
    gate_verdicts = latest_gate_verdicts(claims)
    pending = [c for c in claims if c.get("status") == "pending"]
    obs_with, obs_total = experiment_coverage(experiments)
    return json.dumps(
        {
            "root": str(root),
            "sprint": state.get("sprint"),
            "stage": state.get("current_stage"),
            "samvil_tier": samvil_tier,
            "gate_verdicts_latest": gate_verdicts,
            "pending_claims_count": len(pending),
            "experiments": {
                "total": obs_total,
                "with_observations": obs_with,
                "coverage_pct": (obs_with / obs_total * 100.0) if obs_total else 0.0,
            },
            "next_recommended_action": next_recommended_action(gate_verdicts),
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default=str(REPO))
    p.add_argument("--format", choices=["human", "json"], default="human")
    args = p.parse_args()
    root = Path(args.root)
    if args.format == "json":
        print(render_json(root))
    else:
        print(render_human(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
