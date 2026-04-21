"""Stall Detection (v2.6.0, #24).

Detects stalled pipeline execution based on event timestamps.
Since SAMVIL is skill-driven (not async orchestrator), stall detection
works by checking the gap between last event and current time.

Constants:
  STALL_TIMEOUT_SECONDS = 300 (5 min)
  MAX_STALL_RETRIES = 2

Flow:
  1. Build/QA skill records events with timestamps
  2. Before each Worker spawn, check last event time
  3. If gap > STALL_TIMEOUT → stall detected → checkpoint resume
  4. MAX_STALL_RETRIES exceeded → abandon
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

STALL_TIMEOUT_SECONDS = 300.0
MAX_STALL_RETRIES = 2


@dataclass(frozen=True)
class StallStatus:
    is_stalled: bool
    last_event_age_seconds: float
    last_event_type: str
    retry_count: int
    should_retry: bool


def detect_stall(
    events_path: str,
    timeout: float = STALL_TIMEOUT_SECONDS,
    retry_count: int = 0,
) -> StallStatus:
    """Check if pipeline is stalled based on last event timestamp.

    Args:
        events_path: Path to .samvil/events.jsonl
        timeout: Seconds before stall declared
        retry_count: Current retry attempt count
    """
    path = Path(events_path)
    if not path.exists():
        return StallStatus(
            is_stalled=False,
            last_event_age_seconds=0,
            last_event_type="",
            retry_count=retry_count,
            should_retry=False,
        )

    last_ts = 0.0
    last_type = ""
    try:
        lines = path.read_text().strip().split("\n")
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
                ts = evt.get("timestamp", "")
                if ts:
                    last_ts = _parse_ts(ts)
                    last_type = evt.get("event_type", "")
                    break
            except (json.JSONDecodeError, KeyError):
                continue
    except OSError:
        pass

    if last_ts == 0.0:
        return StallStatus(
            is_stalled=False,
            last_event_age_seconds=0,
            last_event_type="",
            retry_count=retry_count,
            should_retry=False,
        )

    age = time.time() - last_ts
    stalled = age > timeout
    should_retry = stalled and retry_count < MAX_STALL_RETRIES

    return StallStatus(
        is_stalled=stalled,
        last_event_age_seconds=round(age, 1),
        last_event_type=last_type,
        retry_count=retry_count,
        should_retry=should_retry,
    )


def _parse_ts(ts: str) -> float:
    """Parse ISO timestamp to epoch seconds."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


# ── v3.1.0 Sprint 2 additions (v3-016): state.json-driven heartbeat ─────────
#
# The events.jsonl-based `detect_stall` above still fires for build/qa where a
# leaf-level event is appended every few seconds. But design/council/evolve
# run long skill-internal loops without emitting events; the original mobile
# game dogfood hung for 25 minutes in samvil-design with no events at all.
#
# We add an orthogonal API that updates `project.state.json.last_progress_at`
# from any skill, so heartbeat is possible even when no domain event fires.

from datetime import datetime, timezone as _dt_tz


def heartbeat_state(state_path: str, now_iso: str | None = None) -> dict:
    """Update ``last_progress_at`` on ``project.state.json``.

    Returns the updated state dict. Creates the file with a minimal skeleton
    if it does not yet exist so early skills can heartbeat safely.
    """
    p = Path(state_path)
    now_iso = now_iso or _now_iso_v3()
    state: dict = {}
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state["last_progress_at"] = now_iso
    state.setdefault("stall_recovery_count", 0)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def is_state_stalled(
    state_path: str,
    now_iso: str | None = None,
    threshold_seconds: int = int(STALL_TIMEOUT_SECONDS),
) -> dict:
    """State-file stall verdict (v3-016).

    Returns a dict:
      {
        "stalled": bool,
        "reason": str | None,
        "elapsed_seconds": float | None,
        "last_progress_at": str | None,
        "threshold_seconds": int,
      }

    Missing or invalid state returns ``stalled=False`` with an explanatory
    ``reason`` so callers can log a health warning without mistaking the
    silence for a hang.
    """
    p = Path(state_path)
    now_iso = now_iso or _now_iso_v3()
    if not p.exists():
        return _stall_verdict(False, "state_missing", None, None, threshold_seconds)
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _stall_verdict(False, "state_invalid", None, None, threshold_seconds)
    last = state.get("last_progress_at")
    if not last:
        return _stall_verdict(False, "no_heartbeat_yet", None, None, threshold_seconds)
    try:
        elapsed = _seconds_between_v3(last, now_iso)
    except ValueError as exc:
        return _stall_verdict(False, f"invalid_timestamp: {exc}", None, last, threshold_seconds)
    stalled = elapsed >= threshold_seconds
    return _stall_verdict(
        stalled,
        "threshold_exceeded" if stalled else "within_threshold",
        round(elapsed, 1),
        last,
        threshold_seconds,
    )


def build_reawake_message(stage: str, detail: dict, count: int) -> str:
    """Explicit recovery message injected into the main session (v3-016)."""
    elapsed = detail.get("elapsed_seconds")
    elapsed_part = f" ({elapsed}s since last progress)" if elapsed is not None else ""
    if count >= MAX_STALL_RETRIES + 1:  # 3 attempts total (matches MAX_REAWAKES)
        return (
            f"[SAMVIL] ⚠️ 반복된 stall 감지 — {stage} 단계{elapsed_part}. "
            f"{count}회 reawake 후에도 진행 없음. 사용자 개입 필요."
        )
    return (
        f"[SAMVIL] ⏱️ {stage} 단계에서 5분 이상 응답 없음{elapsed_part}. "
        f"Step {count + 1}부터 다시 시작해주세요."
    )


def increment_stall_recovery_count(state_path: str) -> int:
    """Bump ``stall_recovery_count`` on state.json. Returns new value."""
    p = Path(state_path)
    state: dict = {}
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state["stall_recovery_count"] = int(state.get("stall_recovery_count", 0)) + 1
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(state["stall_recovery_count"])


def _stall_verdict(
    stalled: bool,
    reason: str | None,
    elapsed: float | None,
    last: str | None,
    threshold: int,
) -> dict:
    return {
        "stalled": stalled,
        "reason": reason,
        "elapsed_seconds": elapsed,
        "last_progress_at": last,
        "threshold_seconds": threshold,
    }


def _now_iso_v3() -> str:
    return datetime.now(tz=_dt_tz.utc).isoformat()


def _seconds_between_v3(earlier_iso: str, later_iso: str) -> float:
    earlier = _parse_iso_v3(earlier_iso)
    later = _parse_iso_v3(later_iso)
    return (later - earlier).total_seconds()


def _parse_iso_v3(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
