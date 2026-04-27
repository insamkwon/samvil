"""QA Phase Z (post-stage) finalizer for samvil-qa ultra-thin migration.

Aggregates the post-stage Contract Layer work into one MCP call:

  1. Wraps the existing `qa_synthesis.synthesize_qa_evidence` to
     turn Pass 1/2/3 evidence into a central verdict (PASS/REVISE/FAIL).
  2. Computes per-AC `claim_verify` / `claim_reject` payloads from the
     Pass 2 verdicts. Skill body issues the actual MCP calls so the
     Generator-vs-Judge identity stays in the skill (G≠J).
  3. Builds the `gate_check` input (`qa_to_deploy` gate) including the
     required metrics — `three_pass_pass`, `zero_stubs`.
  4. Detects Generator/Judge dispute → returns the `consensus_trigger`
     payload for each AC where Generator said `pass` but Judge said
     `fail` / `partial`.
  5. Renders the QA-section handoff block (Korean, INV-1) ready to
     append to `.samvil/handoff.md`.
  6. Computes Ralph-loop BLOCKED detection from `qa_history` — if the
     same issue ids persist across 2 consecutive iterations, returns
     `blocked.detected = true` + the persistent issue list.
  7. Computes the `next_skill` decision from verdict + tier + auto-
     trigger conditions (build_retries ≥5 / qa_history ≥2 /
     partial_count ≥5 → suggest evolve; else deploy on PASS, retro on
     FAIL).

The actual `materialize_qa_synthesis` (which writes qa-results.json,
qa-report.md, events.jsonl, project.state.json) stays a separate MCP
tool — skill body decides when to materialize vs. just preview.

Inputs:
  - `project_path` — repo root.
  - `evidence_json` — the same JSON shape `synthesize_qa_evidence`
    consumes: `{iteration, max_iterations, pass1, pass2, pass3,
    agent_writes}`.
  - `pending_ac_claims_json` — list of pending build-stage `ac_verdict`
    claims so we can match them up to Pass 2 verdicts.

Outputs (all best-effort, no file writes here):
  - `synthesis` — full output of `synthesize_qa_evidence`.
  - `claim_actions[]` — list of `{action: 'verify'|'reject', claim_id,
    ...}` payloads ready for `claim_verify` / `claim_reject`.
  - `consensus_triggers[]` — list of payloads for `consensus_trigger`.
  - `gate_input` — payload for `gate_check(gate_name='qa_to_deploy')`.
  - `blocked` — `{detected: bool, persistent_issue_ids: [str]}`.
  - `next_skill_decision` — `{verdict, suggested: 'samvil-deploy' |
    'samvil-evolve' | 'samvil-retro', reason}`.
  - `handoff_block` — pre-rendered Korean handoff section.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .qa_synthesis import (
    evaluate_qa_convergence,
    synthesize_qa_evidence,
)

QA_FINALIZE_SCHEMA_VERSION = "1.0"


# ── Helpers ────────────────────────────────────────────────────────────


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_tier(state: dict[str, Any], config: dict[str, Any]) -> str:
    return str(
        state.get("samvil_tier")
        or state.get("selected_tier")
        or config.get("samvil_tier")
        or config.get("selected_tier")
        or "standard"
    )


def _build_claim_actions(
    pass2_items: list[dict[str, Any]],
    pending_ac_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map Pass 2 verdicts onto pending ac_verdict claims.

    For each Pass 2 item:
      - PASS → verify the matching pending claim
      - FAIL / UNIMPLEMENTED → reject the matching pending claim
      - PARTIAL → leave the claim pending (retro decides per legacy SKILL.md)

    Match is by AC id (Pass 2 item.id == claim.subject) when present;
    falls back to criterion text match when ids missing.
    """
    actions: list[dict[str, Any]] = []
    pending_by_subject: dict[str, dict[str, Any]] = {}
    pending_by_text: dict[str, dict[str, Any]] = {}
    for claim in pending_ac_claims:
        subject = str(claim.get("subject") or "")
        if subject:
            pending_by_subject[subject] = claim
        text = str(claim.get("statement") or "")
        if text:
            pending_by_text[text] = claim

    for item in pass2_items:
        verdict = str(item.get("verdict") or "").upper()
        if verdict == "PARTIAL":
            continue
        item_id = str(item.get("id") or "")
        criterion = str(item.get("criterion") or "")
        match = pending_by_subject.get(item_id) or pending_by_text.get(criterion)
        if not match:
            continue
        claim_id = str(match.get("claim_id") or match.get("id") or "")
        if not claim_id:
            continue
        evidence = item.get("evidence") or []
        if verdict == "PASS":
            actions.append({
                "action": "verify",
                "claim_id": claim_id,
                "verified_by": "agent:qa-functional",
                "evidence_json": json.dumps(list(evidence)),
            })
        elif verdict in ("FAIL", "UNIMPLEMENTED"):
            actions.append({
                "action": "reject",
                "claim_id": claim_id,
                "verified_by": "agent:qa-functional",
                "reason": str(item.get("reason") or item.get("notes") or verdict),
            })
    return actions


def _detect_consensus_triggers(
    pass2_items: list[dict[str, Any]],
    pending_ac_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find AC ids where Generator said PASS but Judge said FAIL/PARTIAL."""
    triggers: list[dict[str, Any]] = []
    pending_by_subject: dict[str, dict[str, Any]] = {}
    for claim in pending_ac_claims:
        subject = str(claim.get("subject") or "")
        if subject:
            pending_by_subject[subject] = claim

    for item in pass2_items:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        verdict = str(item.get("verdict") or "").lower()
        if verdict not in ("fail", "partial"):
            continue
        match = pending_by_subject.get(item_id)
        if not match:
            continue
        gen_verdict = str(match.get("statement_status") or match.get("generator_verdict") or "pass").lower()
        if gen_verdict != "pass":
            continue
        triggers.append({
            "input_json": json.dumps({
                "subject": item_id,
                "generator_verdict": "pass",
                "judge_verdict": verdict,
            })
        })
    return triggers


def _build_gate_input(
    synthesis: dict[str, Any],
    samvil_tier: str,
) -> dict[str, Any]:
    """Build `gate_check(gate_name='qa_to_deploy')` payload."""
    pass1_status = str((synthesis.get("pass1") or {}).get("status") or "").upper()
    pass3_verdict = str((synthesis.get("pass3") or {}).get("verdict") or "").upper()
    counts = (synthesis.get("pass2") or {}).get("counts") or {}
    fail = int(counts.get("FAIL", 0) or 0)
    unimplemented = int(counts.get("UNIMPLEMENTED", 0) or 0)
    three_pass_pass = (
        pass1_status == "PASS"
        and pass3_verdict == "PASS"
        and fail == 0
        and unimplemented == 0
    )
    zero_stubs = unimplemented == 0
    return {
        "gate_name": "qa_to_deploy",
        "samvil_tier": samvil_tier,
        "metrics": {
            "three_pass_pass": three_pass_pass,
            "zero_stubs": zero_stubs,
            "fail_count": fail,
            "unimplemented_count": unimplemented,
        },
    }


def _detect_blocked(
    qa_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Detect Ralph-loop BLOCKED state (PHI-04).

    BLOCKED ⇔ identical issue id sets across 2 consecutive iterations.
    """
    if len(qa_history) < 2:
        return {"detected": False, "persistent_issue_ids": []}
    last = qa_history[-1] or {}
    prev = qa_history[-2] or {}
    last_ids = set(map(str, last.get("issue_ids") or last.get("issues") or []))
    prev_ids = set(map(str, prev.get("issue_ids") or prev.get("issues") or []))
    if not last_ids or not prev_ids:
        return {"detected": False, "persistent_issue_ids": []}
    persistent = sorted(last_ids & prev_ids)
    # BLOCKED ⇔ identical issue id sets across 2 consecutive iterations.
    # Strict equality — a strict subset means at least one issue was
    # resolved (progress), so the loop has not stalled.
    if last_ids == prev_ids:
        return {"detected": True, "persistent_issue_ids": persistent}
    return {"detected": False, "persistent_issue_ids": persistent}


def _decide_next_skill(
    synthesis: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Decide the next skill to chain into based on verdict + auto-triggers."""
    verdict = str(synthesis.get("verdict") or "").upper()
    counts = (synthesis.get("pass2") or {}).get("counts") or {}
    partial_count = int(counts.get("PARTIAL", 0) or 0)
    qa_history = state.get("qa_history") or []
    build_retries = int(state.get("build_retries") or 0)

    if verdict in ("FAIL", "REVISE"):
        # FAIL → user choice (evolve / retro / manual). We default to retro.
        return {
            "verdict": verdict,
            "suggested": "samvil-retro",
            "reason": "qa_fail — default to retro; skill body offers user choice (evolve/retro/manual)",
            "user_options": ["samvil-evolve", "samvil-retro", "manual_fix"],
        }

    # PASS path — check auto-triggers for evolve.
    auto_triggers: list[str] = []
    if build_retries >= 5:
        auto_triggers.append(f"build_retries={build_retries} ≥ 5")
    if len(qa_history) >= 2:
        auto_triggers.append(f"qa_history.length={len(qa_history)} ≥ 2")
    if partial_count >= 5:
        auto_triggers.append(f"partial_count={partial_count} ≥ 5")

    if auto_triggers:
        return {
            "verdict": "PASS",
            "suggested": "samvil-evolve",
            "reason": "auto-trigger: " + "; ".join(auto_triggers),
            "user_options": ["samvil-evolve", "samvil-deploy"],
        }

    # Default PASS → deploy.
    return {
        "verdict": "PASS",
        "suggested": "samvil-deploy",
        "reason": "qa_pass — default to deploy",
        "user_options": ["samvil-deploy", "samvil-evolve"],
    }


def _render_handoff_block(
    synthesis: dict[str, Any],
    state: dict[str, Any],
    blocked: dict[str, Any],
    next_skill: dict[str, Any],
) -> str:
    """Render the QA section of `.samvil/handoff.md` (Korean, INV-1)."""
    verdict = synthesis.get("verdict") or "?"
    iteration = synthesis.get("iteration") or 1
    counts = (synthesis.get("pass2") or {}).get("counts") or {}
    pass_n = counts.get("PASS", 0)
    partial_n = counts.get("PARTIAL", 0)
    fail_n = counts.get("FAIL", 0)
    unimplemented_n = counts.get("UNIMPLEMENTED", 0)
    total = pass_n + partial_n + fail_n + unimplemented_n

    lines = [
        "",
        "## QA",
        f"- Verdict: {verdict}",
        f"- Iterations: {iteration}",
        f"- Pass 1 (Mechanical): {(synthesis.get('pass1') or {}).get('status') or '?'}",
        f"- Pass 2 (Functional): PASS={pass_n} / PARTIAL={partial_n} / "
        f"UNIMPLEMENTED={unimplemented_n} / FAIL={fail_n} (total {total})",
        f"- Pass 3 (Quality): {(synthesis.get('pass3') or {}).get('verdict') or '?'}",
    ]
    if blocked.get("detected"):
        persistent = blocked.get("persistent_issue_ids") or []
        lines.append(
            f"- Ralph Loop: BLOCKED on {len(persistent)} persistent issue(s) — manual intervention required"
        )
        for issue in persistent[:5]:
            lines.append(f"  - {issue}")
    lines.append(f"- Next: {next_skill.get('suggested')} ({next_skill.get('reason')})")
    return "\n".join(lines) + "\n"


# ── Aggregator ─────────────────────────────────────────────────────────


@dataclass
class QAFinalizeReport:
    schema_version: str = QA_FINALIZE_SCHEMA_VERSION
    project_path: str = ""
    samvil_tier: str = "standard"
    synthesis: dict[str, Any] = field(default_factory=dict)
    convergence: dict[str, Any] = field(default_factory=dict)
    claim_actions: list[dict[str, Any]] = field(default_factory=list)
    consensus_triggers: list[dict[str, Any]] = field(default_factory=list)
    gate_input: dict[str, Any] = field(default_factory=dict)
    blocked: dict[str, Any] = field(default_factory=dict)
    next_skill_decision: dict[str, Any] = field(default_factory=dict)
    handoff_block: str = ""
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_path": self.project_path,
            "samvil_tier": self.samvil_tier,
            "synthesis": self.synthesis,
            "convergence": self.convergence,
            "claim_actions": self.claim_actions,
            "consensus_triggers": self.consensus_triggers,
            "gate_input": self.gate_input,
            "blocked": self.blocked,
            "next_skill_decision": self.next_skill_decision,
            "handoff_block": self.handoff_block,
            "notes": self.notes,
            "errors": self.errors,
        }


def finalize_qa_verdict(
    project_path: str | Path,
    *,
    evidence: dict[str, Any],
    pending_ac_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Synthesize Pass 1/2/3 evidence + build full Phase Z payload.

    Args:
        project_path: Repo root.
        evidence: JSON shape consumed by `synthesize_qa_evidence`.
        pending_ac_claims: List of pending build-stage `ac_verdict`
            claims (e.g., output of `claim_query_by_subject`). When
            None or empty, `claim_actions` and `consensus_triggers`
            return empty.

    Returns:
        QAFinalizeReport dict.
    """
    report = QAFinalizeReport()
    root = Path(str(project_path)).expanduser()
    report.project_path = str(root)

    # Load state + config for tier + history.
    state = _read_json_safe(root / "project.state.json") or {}
    config = _read_json_safe(root / "project.config.json") or {}
    if not state:
        report.notes.append("project.state.json missing or invalid — assuming defaults")
    qa_history = state.get("qa_history") or []
    report.samvil_tier = _resolve_tier(state, config)

    # Synthesis.
    try:
        synthesis = synthesize_qa_evidence(evidence)
    except Exception as e:  # pragma: no cover — synthesize is robust
        report.errors.append(f"synthesize_qa_evidence failed: {e}")
        synthesis = {
            "verdict": "FAIL",
            "reason": f"synthesis error: {e}",
            "iteration": int(evidence.get("iteration") or 1),
            "max_iterations": int(evidence.get("max_iterations") or 3),
            "pass1": evidence.get("pass1") or {},
            "pass2": {"items": [], "counts": {}},
            "pass3": evidence.get("pass3") or {},
            "events": [],
        }
    report.synthesis = synthesis

    # Convergence (preview — actual write happens in materialize_qa_synthesis).
    try:
        report.convergence = evaluate_qa_convergence(synthesis, qa_history)
    except Exception as e:  # pragma: no cover
        report.errors.append(f"evaluate_qa_convergence failed: {e}")
        report.convergence = {}

    # Claim verify/reject actions.
    pending = list(pending_ac_claims or [])
    pass2_items = (synthesis.get("pass2") or {}).get("items") or []
    report.claim_actions = _build_claim_actions(pass2_items, pending)

    # Consensus triggers (Generator says PASS but Judge disagrees).
    report.consensus_triggers = _detect_consensus_triggers(pass2_items, pending)

    # Gate input.
    report.gate_input = _build_gate_input(synthesis, report.samvil_tier)

    # Ralph-loop BLOCKED detection.
    report.blocked = _detect_blocked(qa_history)

    # Next-skill decision.
    report.next_skill_decision = _decide_next_skill(synthesis, state)

    # Handoff block.
    report.handoff_block = _render_handoff_block(
        synthesis, state, report.blocked, report.next_skill_decision
    )

    # Notes.
    counts = (synthesis.get("pass2") or {}).get("counts") or {}
    if counts.get("UNIMPLEMENTED", 0) > 0:
        report.notes.append(
            f"{counts['UNIMPLEMENTED']} UNIMPLEMENTED leaf/leaves — Reward Hacking signal (E1/P1)"
        )
    if not pending:
        report.notes.append(
            "no pending ac_verdict claims supplied — claim_actions and consensus_triggers are empty"
        )
    if not report.gate_input["metrics"]["three_pass_pass"]:
        report.notes.append("qa_to_deploy gate input: three_pass_pass=False (gate may block)")

    return report.to_dict()
