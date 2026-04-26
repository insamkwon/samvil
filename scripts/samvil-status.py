#!/usr/bin/env python3
"""samvil status — one-screen TUI for the current project.

Sprint 1 MVP per HANDOFF-v3.2-DECISIONS.md §6.1. Zero LLM calls. Runs
against local files only:

  .samvil/state.json          (sprint, stage, samvil_tier)
  .samvil/claims.jsonl        (ledger)
  .samvil/experiments.jsonl   (performance budget + initial-estimate tracking)
  .samvil/events.jsonl        (last activity)
  .samvil/run-report.json     (v3.5 telemetry rollup, if present)
  .samvil/inspection-report.json (v3.10 browser inspection rollup, if present)
  .samvil/repair-plan.json    (v3.12 repair plan, if present)
  .samvil/repair-report.json  (v3.12 repair report, if present)
  .samvil/qa-results.json     (v3.22 QA synthesis materialization, if present)
  .samvil/qa-report.md        (v3.22 QA synthesis markdown, if present)
  .samvil/release-report.json (v3.14 release readiness report, if present)
  .samvil/release-summary.md  (v3.16 release evidence bundle, if present)

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


def _load_state(root: Path) -> dict:
    return _load_json(root / ".samvil" / "state.json") or _load_json(root / "project.state.json")


def _load_run_report(root: Path) -> dict:
    return _load_json(root / ".samvil" / "run-report.json")


def _load_inspection_report(root: Path) -> dict:
    return _load_json(root / ".samvil" / "inspection-report.json")


def _load_repair_plan(root: Path) -> dict:
    return _load_json(root / ".samvil" / "repair-plan.json")


def _load_repair_report(root: Path) -> dict:
    return _load_json(root / ".samvil" / "repair-report.json")


def _load_qa_results(root: Path) -> dict:
    return _load_json(root / ".samvil" / "qa-results.json")


def _load_qa_routing(root: Path) -> dict:
    return _load_json(root / ".samvil" / "qa-routing.json")


def _load_evolve_context(root: Path) -> dict:
    return _load_json(root / ".samvil" / "evolve-context.json")


def _load_evolve_proposal(root: Path) -> dict:
    return _load_json(root / ".samvil" / "evolve-proposal.json")


def _load_evolve_apply(root: Path) -> dict:
    return _load_json(root / ".samvil" / "evolve-apply-plan.json")


def _load_evolve_rebuild(root: Path) -> dict:
    return _load_json(root / ".samvil" / "evolve-rebuild.json")


def _load_rebuild_reentry(root: Path) -> dict:
    return _load_json(root / ".samvil" / "rebuild-reentry.json")


def _load_post_rebuild_qa(root: Path) -> dict:
    return _load_json(root / ".samvil" / "post-rebuild-qa.json")


def _load_evolve_cycle(root: Path) -> dict:
    return _load_json(root / ".samvil" / "evolve-cycle.json")


def _load_release_report(root: Path) -> dict:
    return _load_json(root / ".samvil" / "release-report.json")


def _release_bundle_path(root: Path) -> Path:
    return root / ".samvil" / "release-summary.md"


def _qa_report_path(root: Path) -> Path:
    return root / ".samvil" / "qa-report.md"


def _mutation_count(operations: list[dict]) -> int:
    return sum(1 for item in operations if item.get("status") == "mutated")


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


def inspection_recommended_action(inspection: dict) -> str | None:
    summary = inspection.get("summary", {}) or {}
    if summary.get("status") != "fail":
        return None
    return inspection.get("next_action") or "repair inspection failure"


def repair_recommended_action(repair_plan: dict, repair_report: dict) -> str | None:
    if repair_report:
        if (repair_report.get("summary", {}) or {}).get("status") == "verified":
            return None
        return repair_report.get("next_action") or "review repair report"
    actions = repair_plan.get("actions") or []
    if actions:
        return f"execute repair plan: {actions[0].get('instruction')}"
    return None


def release_recommended_action(report: dict, release_report: dict) -> str | None:
    release_gate = ((report.get("release", {}) or {}).get("gate", {}) or {})
    if release_gate.get("verdict") == "blocked":
        return release_gate.get("next_action") or "clear release gate"
    if release_report and (release_report.get("summary", {}) or {}).get("status") != "pass":
        return release_report.get("next_action") or "fix release checks"
    return None


def qa_recommended_action(report: dict, qa_results: dict, qa_routing: dict | None = None) -> str | None:
    report_qa = (report.get("qa", {}) or {})
    report_routing = (report.get("qa_routing", {}) or {})
    synthesis = qa_results.get("synthesis", {}) or {}
    convergence = report_qa.get("convergence") or qa_results.get("convergence") or synthesis.get("convergence") or {}
    if convergence.get("verdict") in {"blocked", "failed"}:
        routing_action = (
            report_routing.get("next_action")
            or (qa_routing or {}).get("next_action")
            or ((qa_routing or {}).get("primary_route") or {}).get("next_action")
        )
        if routing_action:
            return routing_action
        return convergence.get("next_action") or "resolve QA convergence gate"
    verdict = report_qa.get("verdict") or synthesis.get("verdict")
    if verdict in {"REVISE", "FAIL"}:
        return report_qa.get("next_action") or synthesis.get("next_action") or "fix QA findings"
    return None


def status_next_action(
    report: dict,
    gate_verdicts: dict[str, dict],
    inspection: dict,
    repair_plan: dict,
    repair_report: dict,
    release_report: dict | None = None,
    qa_results: dict | None = None,
    qa_routing: dict | None = None,
) -> str:
    repair_action = repair_recommended_action(repair_plan, repair_report)
    if repair_action:
        return repair_action
    repair_verified = (repair_report.get("summary", {}) or {}).get("status") == "verified"
    release_action = release_recommended_action(report, release_report or {})
    if release_action:
        return release_action
    qa_action = qa_recommended_action(report, qa_results or {}, qa_routing or {})
    if qa_action:
        return qa_action
    if repair_verified and not report and not release_report:
        return repair_report.get("next_action") or "repair verified: re-run release checks"
    if not repair_verified:
        inspection_action = inspection_recommended_action(inspection)
        if inspection_action:
            return inspection_action
    if report:
        return report.get("next_action") or next_recommended_action(gate_verdicts)
    return next_recommended_action(gate_verdicts)


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
    state = _load_state(root)
    report = _load_run_report(root)
    inspection = _load_inspection_report(root)
    repair_plan = _load_repair_plan(root)
    repair_report = _load_repair_report(root)
    qa_results = _load_qa_results(root)
    qa_routing = _load_qa_routing(root)
    evolve_context = _load_evolve_context(root)
    evolve_proposal = _load_evolve_proposal(root)
    evolve_apply = _load_evolve_apply(root)
    evolve_rebuild = _load_evolve_rebuild(root)
    rebuild_reentry = _load_rebuild_reentry(root)
    post_rebuild_qa = _load_post_rebuild_qa(root)
    evolve_cycle = _load_evolve_cycle(root)
    release_report = _load_release_report(root)
    release_bundle = _release_bundle_path(root)
    qa_report = _qa_report_path(root)
    claims = _load_jsonl(root / ".samvil" / "claims.jsonl")
    experiments = _load_jsonl(root / ".samvil" / "experiments.jsonl")
    report_state = report.get("state", {}) or {}
    report_claims = report.get("claims", {}) or {}
    timeline = report.get("timeline", {}) or {}
    health = report.get("mcp_health", {}) or {}
    continuation = report.get("continuation", {}) or {}
    report_repair = report.get("repair", {}) or {}
    repair_gate = report_repair.get("gate", {}) or {}
    report_qa = report.get("qa", {}) or {}
    report_qa_routing = report.get("qa_routing", {}) or {}
    report_evolve_context = report.get("evolve_context", {}) or {}
    report_evolve_proposal = report.get("evolve_proposal", {}) or {}
    report_evolve_apply = report.get("evolve_apply", {}) or {}
    report_evolve_rebuild = report.get("evolve_rebuild", {}) or {}
    report_rebuild_reentry = report.get("rebuild_reentry", {}) or {}
    report_post_rebuild_qa = report.get("post_rebuild_qa", {}) or {}
    report_evolve_cycle = report.get("evolve_cycle", {}) or {}
    report_release = report.get("release", {}) or {}
    release_gate = report_release.get("gate", {}) or {}
    inspection_summary = inspection.get("summary", {}) or {}
    repair_plan_summary = repair_plan.get("summary", {}) or {}
    repair_report_summary = repair_report.get("summary", {}) or {}
    qa_synthesis = qa_results.get("synthesis", {}) or {}
    qa_primary_route = report_qa_routing.get("primary_route") or qa_routing.get("primary_route") or {}
    evolve_focus = evolve_context.get("focus") or {}
    qa_convergence = report_qa.get("convergence") or qa_results.get("convergence") or qa_synthesis.get("convergence") or {}
    qa_counts = ((report_qa.get("pass2_counts") or qa_synthesis.get("pass2", {}).get("counts")) or {})
    release_report_summary = release_report.get("summary", {}) or {}

    # v3.1 stored the field under the legacy name. Read both, preferring
    # the new one. After v3.3 the legacy branch is removed.
    samvil_tier = (
        report_state.get("samvil_tier")
        or state.get("samvil_tier")
        or state.get("agent_tier")  # glossary-allow: legacy state.json fallback
        or "standard"
    )
    sprint = state.get("sprint") or state.get("current_sprint") or "?"
    stage = report_state.get("current_stage") or state.get("current_stage") or state.get("stage") or "?"

    gate_verdicts = latest_gate_verdicts(claims)
    pending_claims = [c for c in claims if c.get("status") == "pending"]
    pending_subjects = report_claims.get("pending_subjects")
    pending_count = len(pending_subjects) if isinstance(pending_subjects, list) else len(pending_claims)
    obs_with, obs_total = experiment_coverage(experiments)

    lines: list[str] = []
    lines.append(f"samvil status — root={root}")
    lines.append("=" * 60)
    lines.append(f"Sprint:  {sprint}")
    lines.append(f"Stage:   {stage}")
    lines.append(f"Tier:    {samvil_tier}")
    if report:
        lines.append(f"Report:  {report.get('generated_at') or '?'}")
    if repair_gate:
        lines.append(
            "Gate:    "
            f"repair={repair_gate.get('verdict', '?')}"
        )
    if release_gate:
        lines.append(
            "Gate:    "
            f"release={release_gate.get('verdict', '?')}"
        )
    if inspection:
        lines.append(
            "Inspect: "
            f"{inspection_summary.get('status', '?')} "
            f"({inspection_summary.get('passed_checks', 0)} pass / "
            f"{inspection_summary.get('failed_checks', 0)} fail)"
        )
    if repair_report:
        lines.append(
            "Repair:  "
            f"{repair_report_summary.get('status', '?')} "
            f"({repair_report_summary.get('resolved_failures', 0)} resolved / "
            f"{repair_report_summary.get('remaining_failures', 0)} remaining)"
        )
    elif repair_plan:
        lines.append(
            "Repair:  "
            f"{repair_plan_summary.get('status', '?')} "
            f"({repair_plan_summary.get('total_actions', 0)} actions)"
        )
    if qa_results:
        lines.append(
            "QA:      "
            f"{qa_synthesis.get('verdict', '?')} "
            f"(P={qa_counts.get('PASS', 0)} / "
            f"Pa={qa_counts.get('PARTIAL', 0)} / "
            f"U={qa_counts.get('UNIMPLEMENTED', 0)} / "
            f"F={qa_counts.get('FAIL', 0)})"
        )
        if qa_convergence:
            lines.append(
                "QA gate: "
                f"{qa_convergence.get('verdict', '?')} "
                f"({qa_convergence.get('issue_count', 0)} issues)"
            )
    if qa_report.exists():
        lines.append(f"QA report: {qa_report}")
    if qa_routing:
        lines.append(
            "QA route: "
            f"{qa_primary_route.get('next_skill', '?')} "
            f"({qa_primary_route.get('route_type', '?')})"
        )
    if evolve_context:
        lines.append(
            "Evolve:  "
            f"{evolve_focus.get('area', '?')} "
            f"({evolve_focus.get('issue_count', 0)} issues)"
        )
    if evolve_proposal:
        lines.append(
            "Proposal:"
            f" {evolve_proposal.get('status', '?')} "
            f"({len(evolve_proposal.get('proposed_changes') or [])} changes)"
        )
    if evolve_apply:
        lines.append(
            "Apply:   "
            f"{evolve_apply.get('status', '?')} "
            f"({_mutation_count(evolve_apply.get('operations') or [])} mutations)"
        )
    if evolve_rebuild:
        lines.append(
            "Rebuild: "
            f"{evolve_rebuild.get('status', '?')} -> "
            f"{evolve_rebuild.get('next_skill') or '?'}"
        )
    if rebuild_reentry:
        lines.append(
            "Reentry: "
            f"{rebuild_reentry.get('status', '?')} -> "
            f"{rebuild_reentry.get('next_skill') or '?'}"
        )
    if post_rebuild_qa:
        lines.append(
            "Post-rebuild QA: "
            f"{post_rebuild_qa.get('status', '?')} -> "
            f"{post_rebuild_qa.get('next_skill') or '?'}"
        )
    if evolve_cycle:
        lines.append(
            "Evolve cycle: "
            f"{evolve_cycle.get('verdict', '?')} -> "
            f"{evolve_cycle.get('next_skill') or '?'}"
        )
    if release_report:
        lines.append(
            "Release: "
            f"{release_report_summary.get('status', '?')} "
            f"({release_report_summary.get('passed_checks', 0)} pass / "
            f"{release_report_summary.get('failed_checks', 0)} fail / "
            f"{release_report_summary.get('missing_checks', 0)} missing)"
        )
        if release_report.get("source"):
            lines.append(f"Release source: {release_report.get('source')}")
    if release_bundle.exists():
        lines.append(f"Release bundle: {release_bundle}")
    lines.append("")
    lines.append("Gate verdicts (latest):")
    report_gates = report_claims.get("latest_gate_verdicts") or []
    if report_gates:
        for gate in report_gates:
            lines.append(
                f"  {str(gate.get('subject','?')):<22} "
                f"{str(gate.get('verdict','?')):<9} "
                f"{str(gate.get('reason',''))[:60]}"
            )
    elif not gate_verdicts:
        lines.append("  (no gate_verdict claims recorded yet)")
    else:
        for g, v in sorted(gate_verdicts.items()):
            meta = v.get("meta", {}) or {}
            lines.append(
                f"  {g:<22} {meta.get('verdict','?'):<9} "
                f"{meta.get('reason','')[:60]}"
            )
    lines.append("")
    lines.append(f"Pending claims:    {pending_count}")
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
    if report:
        lines.append("")
        lines.append("Run report:")
        lines.append(
            f"  Events:          {(report.get('events', {}) or {}).get('total', 0)} total"
        )
        lines.append(
            "  Failures/retry:  "
            f"{timeline.get('failure_count', 0)} failures, "
            f"{timeline.get('retry_count', 0)} retries"
        )
        lines.append(
            "  MCP health:      "
            f"{health.get('failures', 0)} failures / "
            f"{health.get('total', 0)} events"
        )
        if continuation.get("present"):
            lines.append(
                "  Continuation:    "
                f"{continuation.get('from_stage')} -> {continuation.get('next_skill')}"
            )
        else:
            lines.append("  Continuation:    (none)")
        if repair_gate:
            lines.append(
                "  Repair gate:     "
                f"{repair_gate.get('verdict', '?')} - {repair_gate.get('reason', '')}"
            )
        if release_gate:
            lines.append(
                "  Release gate:    "
                f"{release_gate.get('verdict', '?')} - {release_gate.get('reason', '')}"
            )
        if report_qa.get("present"):
            lines.append(
                "  QA:              "
                f"{report_qa.get('verdict', '?')} - {report_qa.get('reason', '')}"
            )
            convergence = report_qa.get("convergence") or {}
            if convergence:
                lines.append(
                    "  QA convergence: "
                    f"{convergence.get('verdict', '?')} - {convergence.get('reason', '')}"
                )
        if report_qa_routing.get("present"):
            lines.append(
                "  QA route:       "
                f"{report_qa_routing.get('next_skill', '?')} - {report_qa_routing.get('reason', '')}"
            )
        if report_evolve_context.get("present"):
            lines.append(
                "  Evolve context: "
                f"{report_evolve_context.get('focus_area', '?')} / "
                f"{report_evolve_context.get('issue_count', 0)} issues"
            )
        if report_evolve_proposal.get("present"):
            lines.append(
                "  Evolve proposal:"
                f" {report_evolve_proposal.get('status', '?')} / "
                f"{report_evolve_proposal.get('changes', 0)} changes"
            )
        if report_evolve_apply.get("present"):
            lines.append(
                "  Evolve apply:   "
                f"{report_evolve_apply.get('status', '?')} / "
                f"{report_evolve_apply.get('mutations', 0)} mutations"
            )
        if report_evolve_rebuild.get("present"):
            lines.append(
                "  Evolve rebuild: "
                f"{report_evolve_rebuild.get('status', '?')} -> "
                f"{report_evolve_rebuild.get('next_skill') or '?'}"
            )
        if report_rebuild_reentry.get("present"):
            lines.append(
                "  Rebuild reentry:"
                f" {report_rebuild_reentry.get('status', '?')} -> "
                f"{report_rebuild_reentry.get('next_skill') or '?'}"
            )
        if report_post_rebuild_qa.get("present"):
            lines.append(
                "  Post-rebuild QA:"
                f" {report_post_rebuild_qa.get('status', '?')} -> "
                f"{report_post_rebuild_qa.get('next_skill') or '?'}"
            )
        if report_evolve_cycle.get("present"):
            lines.append(
                "  Evolve cycle:"
                f" {report_evolve_cycle.get('verdict', '?')} -> "
                f"{report_evolve_cycle.get('next_skill') or '?'}"
            )
        stages = timeline.get("stages") or []
        if stages:
            lines.append("  Stage timeline:")
            for row in stages[:6]:
                duration = row.get("duration_seconds")
                duration_text = f"{duration:.1f}s" if isinstance(duration, (int, float)) else "?"
                lines.append(
                    f"    {str(row.get('stage','?')):<14} "
                    f"{str(row.get('status','?')):<11} "
                    f"{duration_text}"
                )
    if inspection:
        lines.append("")
        lines.append("Inspection:")
        lines.append(
            f"  Status:          {inspection_summary.get('status', '?')}"
        )
        lines.append(
            "  Checks:          "
            f"{inspection_summary.get('passed_checks', 0)} passed, "
            f"{inspection_summary.get('failed_checks', 0)} failed, "
            f"{inspection_summary.get('warning_checks', 0)} warnings"
        )
        lines.append(
            "  Browser:         "
            f"{inspection_summary.get('viewports', 0)} viewports, "
            f"{inspection_summary.get('console_errors', 0)} console errors, "
            f"{inspection_summary.get('screenshots', 0)} screenshots"
        )
        failures = inspection.get("failures") or []
        if failures:
            lines.append("  Failures:")
            for failure in failures[:5]:
                lines.append(
                    f"    {failure.get('type')}: {failure.get('repair_hint')}"
                )
    if repair_plan or repair_report:
        lines.append("")
        lines.append("Repair:")
        if repair_plan:
            lines.append(
                "  Plan:            "
                f"{repair_plan_summary.get('status', '?')} / "
                f"{repair_plan_summary.get('total_actions', 0)} actions"
            )
        if repair_report:
            lines.append(
                "  Report:          "
                f"{repair_report_summary.get('status', '?')} / "
                f"{repair_report_summary.get('resolved_failures', 0)} resolved / "
                f"{repair_report_summary.get('remaining_failures', 0)} remaining"
            )
    if qa_results:
        lines.append("")
        lines.append("QA:")
        lines.append(
            "  Synthesis:       "
            f"{qa_synthesis.get('verdict', '?')} - {qa_synthesis.get('reason', '')}"
        )
        lines.append(
            "  Pass 2:          "
            f"{qa_counts.get('PASS', 0)} pass / "
            f"{qa_counts.get('PARTIAL', 0)} partial / "
            f"{qa_counts.get('UNIMPLEMENTED', 0)} unimplemented / "
            f"{qa_counts.get('FAIL', 0)} fail"
        )
        lines.append(
            "  Pass 3:          "
            f"{((qa_synthesis.get('pass3') or {}).get('verdict') or '?')}"
        )
        if qa_convergence:
            lines.append(
                "  Convergence:     "
                f"{qa_convergence.get('verdict', '?')} - {qa_convergence.get('reason', '')}"
            )
        if qa_report.exists():
            lines.append(f"  Report:          {qa_report}")
        if qa_routing:
            lines.append(
                "  Route:           "
                f"{qa_primary_route.get('next_skill', '?')} - {qa_primary_route.get('reason', '')}"
            )
    if evolve_context:
        lines.append("")
        lines.append("Evolve context:")
        lines.append(
            "  Focus:           "
            f"{evolve_focus.get('area', '?')} / {evolve_focus.get('issue_count', 0)} issues"
        )
        lines.append(
            "  Route:           "
            f"{((evolve_context.get('routing') or {}).get('next_skill')) or '?'}"
        )
    if evolve_proposal:
        lines.append("")
        lines.append("Evolve proposal:")
        lines.append(
            "  Status:          "
            f"{evolve_proposal.get('status', '?')} / {len(evolve_proposal.get('proposed_changes') or [])} changes"
        )
        lines.append(
            "  Next action:     "
            f"{evolve_proposal.get('next_action') or '?'}"
        )
    if evolve_apply:
        lines.append("")
        lines.append("Evolve apply:")
        lines.append(
            "  Status:          "
            f"{evolve_apply.get('status', '?')} / {_mutation_count(evolve_apply.get('operations') or [])} mutations"
        )
        lines.append(
            "  Version:         "
            f"v{evolve_apply.get('from_version') or '?'} -> v{evolve_apply.get('to_version') or '?'}"
        )
        lines.append(
            "  Next action:     "
            f"{evolve_apply.get('next_action') or '?'}"
        )
    if evolve_rebuild:
        lines.append("")
        lines.append("Evolve rebuild:")
        lines.append(
            "  Status:          "
            f"{evolve_rebuild.get('status', '?')}"
        )
        lines.append(
            "  Next skill:      "
            f"{evolve_rebuild.get('next_skill') or '?'}"
        )
        lines.append(
            "  Next action:     "
            f"{evolve_rebuild.get('next_action') or '?'}"
        )
    if rebuild_reentry:
        lines.append("")
        lines.append("Rebuild reentry:")
        lines.append(
            "  Status:          "
            f"{rebuild_reentry.get('status', '?')} / {len(rebuild_reentry.get('issues') or [])} issues"
        )
        lines.append(
            "  Seed:            "
            f"{rebuild_reentry.get('seed_name') or '?'} v{rebuild_reentry.get('seed_version') or '?'}"
        )
        lines.append(
            "  Next skill:      "
            f"{rebuild_reentry.get('next_skill') or '?'}"
        )
    if post_rebuild_qa:
        previous = post_rebuild_qa.get("previous_qa") or {}
        lines.append("")
        lines.append("Post-rebuild QA:")
        lines.append(
            "  Status:          "
            f"{post_rebuild_qa.get('status', '?')} / {len(post_rebuild_qa.get('issues') or [])} issues"
        )
        lines.append(
            "  Seed:            "
            f"{post_rebuild_qa.get('seed_name') or '?'} v{post_rebuild_qa.get('seed_version') or '?'}"
        )
        lines.append(
            "  Previous QA:     "
            f"{previous.get('verdict') or '?'} / {len(previous.get('issue_ids') or [])} issues"
        )
        lines.append(
            "  Next skill:      "
            f"{post_rebuild_qa.get('next_skill') or '?'}"
        )
    if evolve_cycle:
        current = evolve_cycle.get("current_qa") or {}
        lines.append("")
        lines.append("Evolve cycle:")
        lines.append(
            "  Status:          "
            f"{evolve_cycle.get('status', '?')} / {len(evolve_cycle.get('issues') or [])} issues"
        )
        lines.append(
            "  Verdict:         "
            f"{evolve_cycle.get('verdict') or '?'}"
        )
        lines.append(
            "  Current QA:      "
            f"{current.get('verdict') or '?'} / iteration {current.get('iteration') or '?'}"
        )
        lines.append(
            "  Next skill:      "
            f"{evolve_cycle.get('next_skill') or '?'}"
        )
    if release_report:
        lines.append("")
        lines.append("Release:")
        lines.append(
            "  Report:          "
            f"{release_report_summary.get('status', '?')} / "
            f"{release_report_summary.get('passed_checks', 0)} passed / "
            f"{release_report_summary.get('failed_checks', 0)} failed / "
            f"{release_report_summary.get('missing_checks', 0)} missing"
        )
        if release_report.get("source"):
            lines.append(f"  Source:          {release_report.get('source')}")
        if release_bundle.exists():
            lines.append(f"  Bundle:          {release_bundle}")
    lines.append("")
    lines.append(
        "Next action:       "
        f"{status_next_action(report, gate_verdicts, inspection, repair_plan, repair_report, release_report, qa_results, qa_routing)}"
    )
    return "\n".join(lines)


def render_json(root: Path) -> str:
    state = _load_state(root)
    report = _load_run_report(root)
    inspection = _load_inspection_report(root)
    repair_plan = _load_repair_plan(root)
    repair_report = _load_repair_report(root)
    qa_results = _load_qa_results(root)
    qa_routing = _load_qa_routing(root)
    evolve_context = _load_evolve_context(root)
    evolve_proposal = _load_evolve_proposal(root)
    evolve_apply = _load_evolve_apply(root)
    evolve_rebuild = _load_evolve_rebuild(root)
    rebuild_reentry = _load_rebuild_reentry(root)
    post_rebuild_qa = _load_post_rebuild_qa(root)
    evolve_cycle = _load_evolve_cycle(root)
    release_report = _load_release_report(root)
    release_bundle = _release_bundle_path(root)
    qa_report = _qa_report_path(root)
    claims = _load_jsonl(root / ".samvil" / "claims.jsonl")
    experiments = _load_jsonl(root / ".samvil" / "experiments.jsonl")
    report_state = report.get("state", {}) or {}
    report_claims = report.get("claims", {}) or {}
    timeline = report.get("timeline", {}) or {}
    health = report.get("mcp_health", {}) or {}
    continuation = report.get("continuation", {}) or {}
    report_repair = report.get("repair", {}) or {}
    report_qa = report.get("qa", {}) or {}
    report_qa_routing = report.get("qa_routing", {}) or {}
    report_evolve_context = report.get("evolve_context", {}) or {}
    report_evolve_proposal = report.get("evolve_proposal", {}) or {}
    report_evolve_apply = report.get("evolve_apply", {}) or {}
    report_evolve_rebuild = report.get("evolve_rebuild", {}) or {}
    report_rebuild_reentry = report.get("rebuild_reentry", {}) or {}
    report_post_rebuild_qa = report.get("post_rebuild_qa", {}) or {}
    report_evolve_cycle = report.get("evolve_cycle", {}) or {}
    report_release = report.get("release", {}) or {}
    samvil_tier = report_state.get("samvil_tier") or state.get("samvil_tier") or "standard"
    gate_verdicts = latest_gate_verdicts(claims)
    pending = [c for c in claims if c.get("status") == "pending"]
    pending_subjects = report_claims.get("pending_subjects")
    pending_count = len(pending_subjects) if isinstance(pending_subjects, list) else len(pending)
    obs_with, obs_total = experiment_coverage(experiments)
    return json.dumps(
        {
            "root": str(root),
            "sprint": state.get("sprint"),
            "stage": report_state.get("current_stage") or state.get("current_stage") or "?",
            "samvil_tier": samvil_tier,
            "gate_verdicts_latest": report_claims.get("latest_gate_verdicts") or gate_verdicts,
            "pending_claims_count": pending_count,
            "experiments": {
                "total": obs_total,
                "with_observations": obs_with,
                "coverage_pct": (obs_with / obs_total * 100.0) if obs_total else 0.0,
            },
            "run_report": {
                "present": bool(report),
                "generated_at": report.get("generated_at"),
                "events_total": (report.get("events", {}) or {}).get("total", 0),
                "failure_count": timeline.get("failure_count", 0),
                "retry_count": timeline.get("retry_count", 0),
                "mcp_failures": health.get("failures", 0),
                "mcp_events_total": health.get("total", 0),
                "continuation": continuation,
                "stage_timeline": timeline.get("stages") or [],
                "repair": report_repair,
                "release": report_release,
                "qa_routing": report_qa_routing,
                "evolve_context": report_evolve_context,
                "evolve_proposal": report_evolve_proposal,
                "evolve_apply": report_evolve_apply,
                "evolve_rebuild": report_evolve_rebuild,
                "rebuild_reentry": report_rebuild_reentry,
                "post_rebuild_qa": report_post_rebuild_qa,
                "evolve_cycle": report_evolve_cycle,
            },
            "inspection_report": {
                "present": bool(inspection),
                "generated_at": inspection.get("generated_at"),
                "scenario": inspection.get("scenario"),
                "status": (inspection.get("summary", {}) or {}).get("status"),
                "total_checks": (inspection.get("summary", {}) or {}).get("total_checks", 0),
                "failed_checks": (inspection.get("summary", {}) or {}).get("failed_checks", 0),
                "console_errors": (inspection.get("summary", {}) or {}).get("console_errors", 0),
                "screenshots": (inspection.get("summary", {}) or {}).get("screenshots", 0),
                "failure_types": (inspection.get("summary", {}) or {}).get("failure_types", []),
                "failures": inspection.get("failures") or [],
                "next_action": inspection.get("next_action"),
            },
            "repair": {
                "plan_present": bool(repair_plan),
                "report_present": bool(repair_report),
                "plan_status": (repair_plan.get("summary", {}) or {}).get("status"),
                "plan_actions": (repair_plan.get("summary", {}) or {}).get("total_actions", 0),
                "report_status": (repair_report.get("summary", {}) or {}).get("status"),
                "resolved_failures": (repair_report.get("summary", {}) or {}).get("resolved_failures", 0),
                "remaining_failures": (repair_report.get("summary", {}) or {}).get("remaining_failures", 0),
                "next_action": repair_report.get("next_action") or repair_plan.get("next_action"),
            },
            "qa": {
                "results_present": bool(qa_results),
                "report_present": qa_report.exists(),
                "verdict": ((qa_results.get("synthesis", {}) or {}).get("verdict")),
                "reason": ((qa_results.get("synthesis", {}) or {}).get("reason")),
                "next_action": ((qa_results.get("synthesis", {}) or {}).get("next_action")),
                "convergence": (
                    qa_results.get("convergence")
                    or ((qa_results.get("synthesis", {}) or {}).get("convergence"))
                    or {}
                ),
                "pass2_counts": (((qa_results.get("synthesis", {}) or {}).get("pass2", {}) or {}).get("counts") or {}),
                "pass3_verdict": (((qa_results.get("synthesis", {}) or {}).get("pass3", {}) or {}).get("verdict")),
                "qa_results_path": str(root / ".samvil" / "qa-results.json") if qa_results else "",
                "qa_report_path": str(qa_report) if qa_report.exists() else "",
                "run_report": report_qa,
            },
            "qa_routing": {
                "present": bool(qa_routing),
                "status": qa_routing.get("status"),
                "next_skill": ((qa_routing.get("primary_route", {}) or {}).get("next_skill")),
                "route_type": ((qa_routing.get("primary_route", {}) or {}).get("route_type")),
                "reason": ((qa_routing.get("primary_route", {}) or {}).get("reason")),
                "next_action": qa_routing.get("next_action"),
                "alternatives": qa_routing.get("alternative_routes") or [],
                "run_report": report_qa_routing,
            },
            "evolve_context": {
                "present": bool(evolve_context),
                "focus_area": ((evolve_context.get("focus", {}) or {}).get("area")),
                "issue_count": ((evolve_context.get("focus", {}) or {}).get("issue_count", 0)),
                "next_skill": ((evolve_context.get("routing", {}) or {}).get("next_skill")),
                "path": str(root / ".samvil" / "evolve-context.json") if evolve_context else "",
                "run_report": report_evolve_context,
            },
            "evolve_proposal": {
                "present": bool(evolve_proposal),
                "status": evolve_proposal.get("status"),
                "changes": len(evolve_proposal.get("proposed_changes") or []),
                "next_action": evolve_proposal.get("next_action"),
                "path": str(root / ".samvil" / "evolve-proposal.json") if evolve_proposal else "",
                "run_report": report_evolve_proposal,
            },
            "evolve_apply": {
                "present": bool(evolve_apply),
                "status": evolve_apply.get("status"),
                "operations": len(evolve_apply.get("operations") or []),
                "mutations": _mutation_count(evolve_apply.get("operations") or []),
                "from_version": evolve_apply.get("from_version"),
                "to_version": evolve_apply.get("to_version"),
                "next_action": evolve_apply.get("next_action"),
                "path": str(root / ".samvil" / "evolve-apply-plan.json") if evolve_apply else "",
                "preview_path": str(root / ".samvil" / "evolved-seed.preview.json") if evolve_apply else "",
                "run_report": report_evolve_apply,
            },
            "evolve_rebuild": {
                "present": bool(evolve_rebuild),
                "status": evolve_rebuild.get("status"),
                "from_version": evolve_rebuild.get("from_version"),
                "to_version": evolve_rebuild.get("to_version"),
                "next_skill": evolve_rebuild.get("next_skill"),
                "next_action": evolve_rebuild.get("next_action"),
                "path": str(root / ".samvil" / "evolve-rebuild.json") if evolve_rebuild else "",
                "next_skill_path": str(root / ".samvil" / "next-skill.json") if evolve_rebuild else "",
                "run_report": report_evolve_rebuild,
            },
            "rebuild_reentry": {
                "present": bool(rebuild_reentry),
                "status": rebuild_reentry.get("status"),
                "seed_name": rebuild_reentry.get("seed_name"),
                "seed_version": rebuild_reentry.get("seed_version"),
                "target_version": rebuild_reentry.get("target_version"),
                "next_skill": rebuild_reentry.get("next_skill"),
                "issue_count": len(rebuild_reentry.get("issues") or []),
                "next_action": rebuild_reentry.get("next_action"),
                "path": str(root / ".samvil" / "rebuild-reentry.json") if rebuild_reentry else "",
                "scaffold_input_path": str(root / ".samvil" / "scaffold-input.json") if rebuild_reentry else "",
                "run_report": report_rebuild_reentry,
            },
            "post_rebuild_qa": {
                "present": bool(post_rebuild_qa),
                "status": post_rebuild_qa.get("status"),
                "seed_name": post_rebuild_qa.get("seed_name"),
                "seed_version": post_rebuild_qa.get("seed_version"),
                "next_skill": post_rebuild_qa.get("next_skill"),
                "from_stage": post_rebuild_qa.get("from_stage"),
                "previous_verdict": (post_rebuild_qa.get("previous_qa") or {}).get("verdict"),
                "previous_issue_count": len((post_rebuild_qa.get("previous_qa") or {}).get("issue_ids") or []),
                "issue_count": len(post_rebuild_qa.get("issues") or []),
                "next_action": post_rebuild_qa.get("next_action"),
                "path": str(root / ".samvil" / "post-rebuild-qa.json") if post_rebuild_qa else "",
                "scaffold_output_path": str(root / ".samvil" / "scaffold-output.json") if post_rebuild_qa else "",
                "run_report": report_post_rebuild_qa,
            },
            "evolve_cycle": {
                "present": bool(evolve_cycle),
                "status": evolve_cycle.get("status"),
                "verdict": evolve_cycle.get("verdict"),
                "seed_name": evolve_cycle.get("seed_name"),
                "seed_version": evolve_cycle.get("seed_version"),
                "current_verdict": (evolve_cycle.get("current_qa") or {}).get("verdict"),
                "current_iteration": (evolve_cycle.get("current_qa") or {}).get("iteration"),
                "next_skill": evolve_cycle.get("next_skill"),
                "issue_count": len(evolve_cycle.get("issues") or []),
                "next_action": evolve_cycle.get("next_action"),
                "path": str(root / ".samvil" / "evolve-cycle.json") if evolve_cycle else "",
                "run_report": report_evolve_cycle,
            },
            "release": {
                "report_present": bool(release_report),
                "report_status": (release_report.get("summary", {}) or {}).get("status"),
                "passed_checks": (release_report.get("summary", {}) or {}).get("passed_checks", 0),
                "failed_checks": (release_report.get("summary", {}) or {}).get("failed_checks", 0),
                "missing_checks": (release_report.get("summary", {}) or {}).get("missing_checks", 0),
                "source": release_report.get("source"),
                "bundle_present": release_bundle.exists(),
                "bundle_path": str(release_bundle) if release_bundle.exists() else "",
                "next_action": release_report.get("next_action"),
            },
            "next_recommended_action": status_next_action(
                report,
                gate_verdicts,
                inspection,
                repair_plan,
                repair_report,
                release_report,
                qa_results,
                qa_routing,
            ),
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
