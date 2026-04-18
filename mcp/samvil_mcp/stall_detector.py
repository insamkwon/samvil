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
