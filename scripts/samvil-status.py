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


def _load_release_report(root: Path) -> dict:
    return _load_json(root / ".samvil" / "release-report.json")


def _release_bundle_path(root: Path) -> Path:
    return root / ".samvil" / "release-summary.md"


def _qa_report_path(root: Path) -> Path:
    return root / ".samvil" / "qa-report.md"


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


def qa_recommended_action(report: dict, qa_results: dict) -> str | None:
    report_qa = (report.get("qa", {}) or {})
    synthesis = qa_results.get("synthesis", {}) or {}
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
) -> str:
    repair_action = repair_recommended_action(repair_plan, repair_report)
    if repair_action:
        return repair_action
    repair_verified = (repair_report.get("summary", {}) or {}).get("status") == "verified"
    release_action = release_recommended_action(report, release_report or {})
    if release_action:
        return release_action
    qa_action = qa_recommended_action(report, qa_results or {})
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
    report_release = report.get("release", {}) or {}
    release_gate = report_release.get("gate", {}) or {}
    inspection_summary = inspection.get("summary", {}) or {}
    repair_plan_summary = repair_plan.get("summary", {}) or {}
    repair_report_summary = repair_report.get("summary", {}) or {}
    qa_synthesis = qa_results.get("synthesis", {}) or {}
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
    if qa_report.exists():
        lines.append(f"QA report: {qa_report}")
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
        if qa_report.exists():
            lines.append(f"  Report:          {qa_report}")
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
        f"{status_next_action(report, gate_verdicts, inspection, repair_plan, repair_report, release_report, qa_results)}"
    )
    return "\n".join(lines)


def render_json(root: Path) -> str:
    state = _load_state(root)
    report = _load_run_report(root)
    inspection = _load_inspection_report(root)
    repair_plan = _load_repair_plan(root)
    repair_report = _load_repair_report(root)
    qa_results = _load_qa_results(root)
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
                "pass2_counts": (((qa_results.get("synthesis", {}) or {}).get("pass2", {}) or {}).get("counts") or {}),
                "pass3_verdict": (((qa_results.get("synthesis", {}) or {}).get("pass3", {}) or {}).get("verdict")),
                "qa_results_path": str(root / ".samvil" / "qa-results.json") if qa_results else "",
                "qa_report_path": str(qa_report) if qa_report.exists() else "",
                "run_report": report_qa,
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
