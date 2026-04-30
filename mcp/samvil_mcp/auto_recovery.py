"""SAMVIL auto-recovery orchestrator (Phase C.4).

Layered on top of `stall_detector` to answer the question that v0.x
runs surfaced repeatedly: "the pipeline went silent, now what?".

Existing primitives:
- `is_state_stalled` detects the 5-min no-heartbeat threshold.
- `heartbeat_state` updates `last_progress_at`.
- `increment_stall_recovery_count` tracks retry attempts.
- `build_reawake_message` formats user-facing copy.

This module composes them into a single decision-making call:
`evaluate_stuck_recovery(project_root)` returns one of four actions:

- **none** — pipeline is healthy, no recovery needed.
- **reentry** — stalled but under retry budget; re-enter the current
  stage. Caller emits a `stage_reentry` event and rewrites the chain
  marker to the same stage so the next host invocation resumes work.
- **escalate** — retry budget exhausted; halt automation and ask the
  user to intervene (Rhythm Guard pattern, P10).
- **block** — state corruption (e.g. missing/invalid state.json); cannot
  recover automatically.

The caller (skill body) is responsible for executing the recommended
action — this module only computes the verdict, never mutates state
unless `apply=True`. The default (read-only) avoids surprise side
effects, especially in dry-run / inspection contexts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .stall_detector import (
    MAX_STALL_RETRIES,
    STALL_TIMEOUT_SECONDS,
    increment_stall_recovery_count,
    is_state_stalled,
    build_reawake_message,
)

# After how many stall_recovery_count bumps we stop auto-recovering and
# escalate to the user. Matches the v3-016 contract (MAX_STALL_RETRIES=2).
ESCALATION_THRESHOLD: int = MAX_STALL_RETRIES


@dataclass
class RecoveryVerdict:
    action: str = "none"  # none | reentry | escalate | block
    reason: str = ""
    stage: str = ""
    elapsed_seconds: float | None = None
    recovery_count: int = 0
    max_retries: int = ESCALATION_THRESHOLD
    next_step: str = ""
    user_message: str = ""
    state_dirty: bool = False  # True if apply=True and we mutated state
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "stage": self.stage,
            "elapsed_seconds": self.elapsed_seconds,
            "recovery_count": self.recovery_count,
            "max_retries": self.max_retries,
            "next_step": self.next_step,
            "user_message": self.user_message,
            "state_dirty": self.state_dirty,
            "notes": list(self.notes),
        }


def _read_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate_stuck_recovery(
    project_root: str | Path,
    *,
    apply: bool = False,
    threshold_seconds: int = int(STALL_TIMEOUT_SECONDS),
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Inspect a project's state and recommend a recovery action.

    Args:
        project_root: directory holding `project.state.json`.
        apply: if True, mutate state on `reentry` (bump recovery count
            and write a `next_step` marker). Default False keeps the
            call side-effect-free for dry-run / observability use.
        threshold_seconds: stall threshold override (default: 5 min).
        now_iso: optional ISO timestamp override for testing.

    Returns:
        Dict shaped per `RecoveryVerdict.to_dict()`.
    """
    root = Path(project_root)
    state_path = root / "project.state.json"

    verdict = RecoveryVerdict()
    state = _read_state(state_path)

    if not state:
        verdict.action = "block"
        verdict.reason = "state_missing_or_invalid"
        verdict.next_step = (
            "verify project.state.json exists; cannot auto-recover without it"
        )
        return verdict.to_dict()

    stage = str(state.get("current_stage") or "")
    verdict.stage = stage
    recovery_count = int(state.get("stall_recovery_count", 0) or 0)
    verdict.recovery_count = recovery_count

    stall = is_state_stalled(
        str(state_path),
        now_iso=now_iso,
        threshold_seconds=threshold_seconds,
    )
    verdict.elapsed_seconds = stall.get("elapsed_seconds")

    if not stall.get("stalled"):
        verdict.action = "none"
        verdict.reason = stall.get("reason") or "within_threshold"
        verdict.next_step = "continue current stage"
        return verdict.to_dict()

    # Stalled. Decide between reentry vs escalate.
    if recovery_count >= ESCALATION_THRESHOLD:
        verdict.action = "escalate"
        verdict.reason = "retry_budget_exhausted"
        verdict.next_step = (
            "AskUserQuestion: '계속 대기 / 단계 건너뛰기 / 처음부터 재시작' — "
            "automation cannot recover (P10)"
        )
        verdict.user_message = build_reawake_message(
            stage or "unknown", stall, recovery_count + 1
        )
        return verdict.to_dict()

    verdict.action = "reentry"
    verdict.reason = "stall_detected_within_retry_budget"
    verdict.next_step = (
        f"rewrite .samvil/next-skill.json → samvil-{stage} and re-invoke; "
        f"emit save_event(event_type='stage_reentry', stage='{stage}')"
    )
    verdict.user_message = build_reawake_message(
        stage or "unknown", stall, recovery_count + 1
    )

    if apply:
        # Persist a bumped recovery count so subsequent calls escalate.
        new_count = increment_stall_recovery_count(str(state_path))
        verdict.recovery_count = new_count
        verdict.state_dirty = True
        verdict.notes.append(f"bumped stall_recovery_count to {new_count}")

    return verdict.to_dict()
