"""`samvil narrate` — 1-page narrative observability (v3.2 Sprint 4).

Per HANDOFF-v3.2-DECISIONS.md §6.1, `samvil narrate` is the LLM-powered
layer of the observability spine. It reads local files (events.jsonl +
claims.jsonl + last retro), summarizes using the Compressor role (⑤),
and emits a three-section briefing:

  * What happened in the last window (sprint-/week-granular).
  * Where you're currently stuck (unresolved escalations, old pending
    claims, stagnation alerts).
  * What's next (top 3 actionable items).

This module owns:
  * The context-assembly logic — reads files, picks highlights, caps
    input size so the Compressor prompt stays within budget.
  * The prompt template.
  * The result parser — tolerant of malformed JSON.

The actual LLM call is made by the caller (a skill that invokes the
MCP tool `narrate_build_prompt` and then runs the model). Keeping the
LLM call out of the MCP server preserves INV-2 (build logs to files,
MCP doesn't block on external I/O).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ── Context assembly ─────────────────────────────────────────────────


@dataclass
class NarrateContext:
    """Everything the Compressor needs to produce a narrative."""

    window_description: str
    since_iso: str
    now_iso: str

    pending_claims: list[dict] = field(default_factory=list)
    recent_gate_verdicts: list[dict] = field(default_factory=list)
    latest_events: list[dict] = field(default_factory=list)
    retro_observations: list[dict] = field(default_factory=list)
    experiments_below_threshold: list[dict] = field(default_factory=list)

    def to_summary(self) -> str:
        """Deterministic textual summary for the prompt. Kept compact
        (≤ ~2k tokens) so the narrator prompt stays cheap."""
        parts: list[str] = [
            f"Window: {self.window_description} ({self.since_iso} → {self.now_iso})",
            "",
            f"Pending claims: {len(self.pending_claims)}",
        ]
        for c in self.pending_claims[:10]:
            parts.append(
                f"  · {c.get('type','?')}/{c.get('subject','?')} "
                f"claimed_by={c.get('claimed_by','?')} "
                f"ts={c.get('ts','?')}"
            )
        parts.append("")
        parts.append(f"Gate verdicts (latest {len(self.recent_gate_verdicts)}):")
        for v in self.recent_gate_verdicts[:10]:
            meta = v.get("meta", {}) or {}
            parts.append(
                f"  · {v.get('subject','?'):<22} {meta.get('verdict','?'):<9} "
                f"{meta.get('reason','')[:80]}"
            )
        parts.append("")
        parts.append(f"Retro observations: {len(self.retro_observations)}")
        for o in self.retro_observations[:10]:
            parts.append(
                f"  · [{o.get('severity','?')}] {o.get('category','?')}: "
                f"{o.get('summary','')[:80]}"
            )
        if self.experiments_below_threshold:
            parts.append("")
            parts.append(
                f"Experiments without observations: "
                f"{len(self.experiments_below_threshold)}"
            )
            for e in self.experiments_below_threshold[:5]:
                parts.append(f"  · {e.get('name','?')}")
        return "\n".join(parts)


def _load_jsonl(path: Path, limit: int | None = None) -> list[dict]:
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
    if limit is not None:
        rows = rows[-limit:]
    return rows


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _within_window(ts_iso: str, since: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except ValueError:
        return True  # can't parse → include
    return ts >= since


def _latest_gate_verdicts(claims: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for c in claims:
        if c.get("type") != "gate_verdict":
            continue
        subject = c.get("subject", "")
        ts = c.get("ts", "")
        if subject not in latest or latest[subject].get("ts", "") < ts:
            latest[subject] = c
    return sorted(latest.values(), key=lambda c: c.get("ts", ""), reverse=True)


def build_context(
    project_root: str | Path,
    *,
    since: str | None = None,
    window_description: str | None = None,
) -> NarrateContext:
    """Assemble a NarrateContext from the project's .samvil/ files.

    `since` is ISO-8601 UTC; default = last 7 days.
    """
    root = Path(project_root)
    now_dt = datetime.now(timezone.utc)
    since_dt = (
        datetime.fromisoformat(since.replace("Z", "+00:00"))
        if since
        else now_dt - timedelta(days=7)
    )

    claims = _load_jsonl(root / ".samvil" / "claims.jsonl")
    events = _load_jsonl(root / ".samvil" / "events.jsonl", limit=200)
    retro = _load_json(root / ".samvil" / "retro.json")
    experiments = _load_jsonl(root / ".samvil" / "experiments.jsonl")

    # Collapse claims to latest state per id, then filter in window.
    latest: dict[str, dict] = {}
    for c in claims:
        cid = c.get("claim_id")
        if cid:
            latest[cid] = c
    in_window_claims = [
        c for c in latest.values() if _within_window(c.get("ts", ""), since_dt)
    ]
    pending = [c for c in in_window_claims if c.get("status") == "pending"]
    pending_old_first = sorted(pending, key=lambda c: c.get("ts", ""))

    gate_verdicts = _latest_gate_verdicts(list(latest.values()))

    # Retro: expect retro.json to include an `observations` list of dicts.
    retro_observations = list(retro.get("observations") or [])

    experiments_below = [
        e for e in experiments if not (e.get("observations") or [])
    ]

    return NarrateContext(
        window_description=window_description or "last 7 days",
        since_iso=since_dt.isoformat(),
        now_iso=now_dt.isoformat(),
        pending_claims=pending_old_first,
        recent_gate_verdicts=gate_verdicts[:10],
        latest_events=events[-20:],
        retro_observations=retro_observations,
        experiments_below_threshold=experiments_below,
    )


# ── Prompt + parser ───────────────────────────────────────────────────


_NARRATE_PROMPT = """\
Role: Compressor for SAMVIL v3.2. Produce a one-page narrative.

Context (deterministic extract from .samvil/):
---
{summary}
---

Emit exactly this JSON shape:

  {{
    "what_happened": ["string", ...],     # 3-6 bullets
    "where_stuck": ["string", ...],       # 0-4 bullets; [] if nothing stuck
    "next_actions": ["string", ...]       # 3 bullets, imperative tone
  }}

Rules:
  - No filler. Each bullet ≤ 18 words.
  - Anchor bullets to a specific subject id (claim_id, gate name, AC id)
    when possible — the user will click to that record.
  - "where_stuck" is empty if no pending claim is older than 2 days and
    no gate is currently escalating.
  - "next_actions" must be concrete, e.g. "verify AC-2.1 (pending 3d)".
  - Korean output is acceptable if the user's prior messages are Korean;
    otherwise English.
"""


def build_narrate_prompt(ctx: NarrateContext) -> str:
    return _NARRATE_PROMPT.format(summary=ctx.to_summary())


@dataclass
class Narrative:
    what_happened: list[str] = field(default_factory=list)
    where_stuck: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines: list[str] = []
        if self.what_happened:
            lines.append("## What happened")
            for b in self.what_happened:
                lines.append(f"- {b}")
        if self.where_stuck:
            lines.append("")
            lines.append("## Where you're stuck")
            for b in self.where_stuck:
                lines.append(f"- {b}")
        if self.next_actions:
            lines.append("")
            lines.append("## Next actions")
            for b in self.next_actions:
                lines.append(f"- {b}")
        return "\n".join(lines) or "(no narrative)"


def parse_narrative(raw: str) -> Narrative:
    """Best-effort parser. Accepts the expected JSON object or falls back
    to a minimal heuristic that extracts `- ` bullets into `what_happened`.
    """
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return Narrative(
                what_happened=list(data.get("what_happened") or []),
                where_stuck=list(data.get("where_stuck") or []),
                next_actions=list(data.get("next_actions") or []),
            )
    except Exception:
        pass

    bullets: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("- "):
            bullets.append(s[2:].strip())
    return Narrative(what_happened=bullets[:6])
