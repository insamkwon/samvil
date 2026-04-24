"""Stagnation detector (⑩) — distinct from stall detection.

Per HANDOFF-v3.2-DECISIONS.md §3.⑩. `stall_detector.py` (Sprint 2 of
v3.1) handled "no events for N minutes"; stagnation handles "the loop
is moving but not making progress".

Triggers (any):
  * Same error signature repeated ≥ 2 times.
  * File hash unchanged across N minutes while work is claimed active.
  * QA score delta below threshold (initial estimate `< 0.02`) over N
    iterations.
  * Seed changed but Build output unchanged.

Response workflow:
  * Single-signal trigger → severity=medium, surface warning only.
  * Two independent signals → severity=high, halt normal flow.
  * On `high`: skill invokes `lateral_propose` to spawn a different-role
    diagnosis agent (⑨ consensus may also be invoked).

This module is pure detector logic. The "lateral_propose" action is a
prompt-builder plus a hint for which role to spawn; actual spawning is
the skill's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Signal(str, Enum):
    REPEATED_ERROR = "repeated_error"
    FILE_HASH_UNCHANGED = "file_hash_unchanged"
    QA_SCORE_FLAT = "qa_score_flat"
    SEED_CHANGED_BUILD_SAME = "seed_changed_build_same"


# (initial estimate) — registered as experimental_policy by
# scripts/seed-experiments.py. Retro promotes when data accumulates.
QA_SCORE_DELTA_FLOOR = 0.02
FILE_UNCHANGED_MINUTES = 10


@dataclass
class StagnationInput:
    """Per-cycle snapshot the detector consumes.

    Times are ISO-8601 UTC strings (same as claims.jsonl). The detector
    parses them lazily so the caller can pass `None` when a signal
    is not applicable this cycle.
    """

    error_history: list[str] = field(default_factory=list)
    current_error: str | None = None

    # file-hash signal
    last_file_change_ts: str | None = None
    now_ts: str | None = None
    work_active: bool = True

    # qa-score signal
    qa_score_history: list[float] = field(default_factory=list)
    qa_iterations_window: int = 3

    # seed-vs-build signal
    seed_version_changed: bool = False
    build_output_changed: bool = True


@dataclass
class StagnationVerdict:
    signals: list[str] = field(default_factory=list)
    severity: str = Severity.LOW.value
    should_halt: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "signals": self.signals,
            "severity": self.severity,
            "should_halt": self.should_halt,
            "reason": self.reason,
        }


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate(inp: StagnationInput) -> StagnationVerdict:
    """Apply the four signals. Return a verdict.

    Severity rules (§3.⑩ anti-false-positive clause):
      * no signals → low
      * 1 signal   → medium (warning only)
      * ≥2 signals → high (halt)
    """
    signals: list[str] = []
    reasons: list[str] = []

    # 1. Repeated error
    if inp.current_error and inp.error_history.count(inp.current_error) >= 2:
        signals.append(Signal.REPEATED_ERROR.value)
        reasons.append(f"error {inp.current_error!r} repeated {inp.error_history.count(inp.current_error)}x")

    # 2. File hash unchanged
    last = _parse_ts(inp.last_file_change_ts)
    now = _parse_ts(inp.now_ts) or datetime.now(timezone.utc)
    if inp.work_active and last is not None:
        delta = now - last
        if delta >= timedelta(minutes=FILE_UNCHANGED_MINUTES):
            signals.append(Signal.FILE_HASH_UNCHANGED.value)
            reasons.append(
                f"no file changes for {delta.total_seconds()/60:.0f}m "
                f"(threshold {FILE_UNCHANGED_MINUTES}m)"
            )

    # 3. QA score flat
    if len(inp.qa_score_history) >= inp.qa_iterations_window:
        tail = inp.qa_score_history[-inp.qa_iterations_window:]
        span = max(tail) - min(tail)
        if span < QA_SCORE_DELTA_FLOOR:
            signals.append(Signal.QA_SCORE_FLAT.value)
            reasons.append(
                f"QA score span {span:.3f} over last "
                f"{inp.qa_iterations_window} iterations (floor "
                f"{QA_SCORE_DELTA_FLOOR})"
            )

    # 4. Seed changed but build didn't
    if inp.seed_version_changed and not inp.build_output_changed:
        signals.append(Signal.SEED_CHANGED_BUILD_SAME.value)
        reasons.append("seed version changed but build output unchanged")

    if not signals:
        return StagnationVerdict(
            signals=[], severity=Severity.LOW.value, should_halt=False, reason=""
        )

    if len(signals) == 1:
        return StagnationVerdict(
            signals=signals,
            severity=Severity.MEDIUM.value,
            should_halt=False,
            reason="; ".join(reasons),
        )

    return StagnationVerdict(
        signals=signals,
        severity=Severity.HIGH.value,
        should_halt=True,
        reason="; ".join(reasons),
    )


# ── Lateral diagnosis ────────────────────────────────────────────────


_LATERAL_PROMPT = """\
Role: lateral diagnosis agent for SAMVIL v3.2.

Stagnation declared with severity=HIGH on this subject:
---
{subject}
---

Recent signals: {signals}
Reason: {reason}

Task:
  1. Hypothesize the **root cause** (one sentence).
  2. Propose an alternative implementation plan that differs in
     approach (not the same code with a tweak).
  3. Identify the smallest reversible experiment that would either
     confirm or disprove your hypothesis.

Return JSON:
  {{
    "root_cause_hypothesis": "string",
    "alternative_plan": "string (3-6 bullets, one action each)",
    "smallest_experiment": "string"
  }}

Rules:
  - Avoid the approach currently claimed_by the Generator role.
  - Favor changes that are reversible (new branch, feature flag,
    commented override) over irreversible ones.
  - Keep the alternative plan under 6 bullets.
"""


def build_lateral_prompt(
    *, subject: str, verdict: StagnationVerdict
) -> str:
    return _LATERAL_PROMPT.format(
        subject=subject,
        signals=", ".join(verdict.signals) or "(none)",
        reason=verdict.reason or "(none)",
    )
