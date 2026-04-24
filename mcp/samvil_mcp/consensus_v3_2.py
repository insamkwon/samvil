"""Consensus as dispute resolver (⑨) — v3.2.

Per HANDOFF-v3.2-DECISIONS.md §3.⑨:

  * Council Gate A's always-on form is retired. In v3.2 it runs only
    when `--council` is passed (opt-in, deprecation-warned). Removed
    entirely in v3.3.
  * The 2-round Research → Review pattern survives as a **dispute
    resolver** invoked only on specific triggers.
  * Phase 1 launch: Judge + Reviewer (2-person). Devil added in Phase
    2 if dogfood shows it's needed.

Dispute triggers (any):
  T1 — Generator PASS + Judge PARTIAL/FAIL mismatch.
  T2 — Reviewer flags evidence as weak while claim is PASS.
  T3 — Evolve proposes scope change.
  T4 — Same failure signature repeated 2+ times (also triggers ⑩).
  T5 — User intent ambiguous after L4 interview.
  T6 — Architectural tradeoff unresolved.

This module detects triggers and produces prompts. The skill drives the
resolver loop and records the final verdict as a `consensus_verdict`
claim in the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DisputeTrigger(str, Enum):
    GENERATOR_JUDGE_MISMATCH = "generator_judge_mismatch"
    WEAK_EVIDENCE = "weak_evidence"
    EVOLVE_SCOPE_CHANGE = "evolve_scope_change"
    REPEATED_FAILURE = "repeated_failure"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    ARCHITECTURE_TRADEOFF = "architecture_tradeoff"


class ConsensusVerdict(str, Enum):
    ACCEPT = "accept"  # Advocate wins
    REJECT = "reject"  # Devil wins
    ESCALATE = "escalate"  # Judge can't decide; user must


@dataclass
class DisputeInput:
    subject: str
    generator_verdict: str | None = None  # pass / partial / fail
    judge_verdict: str | None = None
    reviewer_flags: list[str] = field(default_factory=list)
    proposed_scope_change: str | None = None
    repeated_failure_signature: str | None = None
    intent_clarity: float | None = None
    architecture_note: str | None = None


@dataclass
class DisputeDetection:
    triggers: list[str] = field(default_factory=list)
    should_invoke: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "triggers": self.triggers,
            "should_invoke": self.should_invoke,
            "reason": self.reason,
        }


def detect_dispute(inp: DisputeInput) -> DisputeDetection:
    triggers: list[str] = []
    reasons: list[str] = []

    if inp.generator_verdict == "pass" and inp.judge_verdict in ("partial", "fail"):
        triggers.append(DisputeTrigger.GENERATOR_JUDGE_MISMATCH.value)
        reasons.append(
            f"generator=pass but judge={inp.judge_verdict}"
        )
    if "weak_evidence" in (inp.reviewer_flags or []):
        triggers.append(DisputeTrigger.WEAK_EVIDENCE.value)
        reasons.append("reviewer flagged evidence as weak")
    if inp.proposed_scope_change:
        triggers.append(DisputeTrigger.EVOLVE_SCOPE_CHANGE.value)
        reasons.append(
            f"evolve proposed scope change: {inp.proposed_scope_change[:60]}"
        )
    if inp.repeated_failure_signature:
        triggers.append(DisputeTrigger.REPEATED_FAILURE.value)
        reasons.append(
            f"repeated failure signature: {inp.repeated_failure_signature}"
        )
    if inp.intent_clarity is not None and inp.intent_clarity < 0.70:
        triggers.append(DisputeTrigger.AMBIGUOUS_INTENT.value)
        reasons.append(
            f"intent_clarity {inp.intent_clarity:.2f} below threshold"
        )
    if inp.architecture_note:
        triggers.append(DisputeTrigger.ARCHITECTURE_TRADEOFF.value)
        reasons.append(
            f"architecture: {inp.architecture_note[:60]}"
        )

    return DisputeDetection(
        triggers=triggers,
        should_invoke=bool(triggers),
        reason="; ".join(reasons),
    )


# ── Resolver prompts (Judge + Reviewer) ─────────────────────────────


_REVIEWER_PROMPT = """\
Role: Reviewer in the SAMVIL v3.2 dispute resolver.

Dispute subject:
---
{subject}
---

Triggers: {triggers}
Context: {context}

Task:
  * Read the subject, the claim history (below), and the evidence.
  * Produce a concise position: "accept" or "reject" with a
    one-paragraph rationale. If the evidence is genuinely ambiguous,
    return "escalate" and say what additional information would resolve
    it.
  * Stay neutral; do not rubber-stamp. Your input feeds the Judge.

Return JSON:
  {{ "position": "accept" | "reject" | "escalate", "rationale": "..." }}
"""


_JUDGE_PROMPT = """\
Role: Judge in the SAMVIL v3.2 dispute resolver.

Dispute subject:
---
{subject}
---

Reviewer position:
{reviewer_position}

Triggers that brought this dispute: {triggers}

Task:
  * Read the Reviewer's position and the evidence.
  * Decide the verdict: accept / reject / escalate.
  * If escalate, specify exactly what the user must confirm.
  * Do not re-argue the subject; decide based on the written record.

Return JSON:
  {{
    "verdict": "accept" | "reject" | "escalate",
    "reason": "...",
    "required_user_decision": "string — only when verdict=escalate"
  }}
"""


def build_reviewer_prompt(
    *, subject: str, triggers: list[str], context: str
) -> str:
    return _REVIEWER_PROMPT.format(
        subject=subject,
        triggers=", ".join(triggers) or "(none)",
        context=context or "(no context)",
    )


def build_judge_prompt(
    *, subject: str, triggers: list[str], reviewer_position: str
) -> str:
    return _JUDGE_PROMPT.format(
        subject=subject,
        triggers=", ".join(triggers) or "(none)",
        reviewer_position=reviewer_position or "(reviewer returned nothing)",
    )


# ── Deprecation warning string ───────────────────────────────────────


DEPRECATION_WARNING = (
    "Council Gate A is opt-in in v3.2 and removed in v3.3. Running "
    "with --council enables the legacy always-on pipeline. Prefer "
    "automatic consensus invocation via ⑨ triggers. See "
    "references/council-retirement-migration.md."
)
