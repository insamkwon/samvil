"""SAMVIL progress panel (Phase B.3).

Renders a single-shot progress view a user can call any time during a
pipeline run to answer "where am I, what's next, how long until done?".

Inputs (all best-effort, INV-5 / P8):
- `project.state.json` — current_stage, completed_stages, samvil_tier.
- `project.seed.json` — features[] AC tree (leaf counts).
- `.samvil/events.jsonl` — last event time, current-stage start time.

Outputs the same fields the rendered ASCII panel uses, so callers
(skills, scripts, CLIs) can re-format without re-reading files.

ETA model is intentionally conservative: a baseline duration table
per (stage, tier) — easy to refine later with historical data once
multiple runs accumulate. When inputs are insufficient, ETA falls
back to "unknown" rather than guessing.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIPELINE_STAGES: tuple[str, ...] = (
    "interview",
    "seed",
    "council",
    "design",
    "scaffold",
    "build",
    "qa",
    "deploy",
    "retro",
)

# Baseline median duration per (stage, samvil_tier) in seconds.
# These are rough first-pass numbers from observed runs; refine later.
# Values default to "standard" when an unknown tier is given.
_BASELINE_DURATION_SEC: dict[str, dict[str, int]] = {
    "interview": {"minimal": 180, "standard": 300, "thorough": 600, "full": 900, "deep": 900},
    "seed": {"minimal": 60, "standard": 120, "thorough": 180, "full": 240, "deep": 240},
    "council": {"minimal": 0, "standard": 240, "thorough": 600, "full": 900, "deep": 900},
    "design": {"minimal": 60, "standard": 180, "thorough": 360, "full": 600, "deep": 600},
    "scaffold": {"minimal": 90, "standard": 90, "thorough": 90, "full": 90, "deep": 90},
    "build": {"minimal": 360, "standard": 780, "thorough": 1500, "full": 2400, "deep": 2400},
    "qa": {"minimal": 180, "standard": 360, "thorough": 720, "full": 1200, "deep": 1200},
    "deploy": {"minimal": 60, "standard": 120, "thorough": 180, "full": 240, "deep": 240},
    "retro": {"minimal": 60, "standard": 120, "thorough": 180, "full": 240, "deep": 240},
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_events(path: Path, max_tail: int = 2000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines()[-max_tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _baseline_for(stage: str, tier: str) -> int:
    table = _BASELINE_DURATION_SEC.get(stage, {})
    return int(table.get(tier, table.get("standard", 0)))


def _count_leaves(seed: dict[str, Any]) -> dict[str, int]:
    """Walk seed.features[].acceptance_criteria tree and count by status."""
    counts = {"pass": 0, "fail": 0, "pending": 0, "total": 0}

    def walk(nodes: list[Any]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            children = node.get("children")
            if isinstance(children, list) and children:
                walk(children)
                continue
            counts["total"] += 1
            status = str(node.get("status", "")).lower()
            if status == "pass":
                counts["pass"] += 1
            elif status in ("fail", "failed"):
                counts["fail"] += 1
            else:
                counts["pending"] += 1

    for feature in seed.get("features") or []:
        if not isinstance(feature, dict):
            continue
        acs = feature.get("acceptance_criteria") or []
        if isinstance(acs, list):
            walk(acs)
    return counts


def _stage_started_at(events: list[dict[str, Any]], stage: str) -> float | None:
    """Return the unix timestamp of the most recent stage_start event for `stage`."""
    for ev in reversed(events):
        if ev.get("stage") != stage:
            continue
        et = str(ev.get("event_type", ""))
        if not et:
            continue
        # Accept any of the common stage-entry event names
        if et.endswith("_started") or et == "stage_change" or et == "stage_start":
            ts = ev.get("ts") or ev.get("timestamp")
            if isinstance(ts, (int, float)):
                return float(ts)
            if isinstance(ts, str):
                try:
                    # Try ISO 8601
                    from datetime import datetime
                    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
    return None


def _last_event_at(events: list[dict[str, Any]]) -> float | None:
    for ev in reversed(events):
        ts = ev.get("ts") or ev.get("timestamp")
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    minutes, secs = divmod(secs, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


@dataclass
class ProgressView:
    project_root: str = ""
    project_name: str = ""
    samvil_tier: str = "standard"
    current_stage: str = ""
    completed_stages: list[str] = field(default_factory=list)
    leaves: dict[str, int] = field(default_factory=dict)
    elapsed_in_stage_sec: float | None = None
    eta_sec: float | None = None
    last_event_age_sec: float | None = None
    pipeline: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "project_name": self.project_name,
            "samvil_tier": self.samvil_tier,
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "leaves": dict(self.leaves),
            "elapsed_in_stage_sec": self.elapsed_in_stage_sec,
            "eta_sec": self.eta_sec,
            "last_event_age_sec": self.last_event_age_sec,
            "pipeline": list(self.pipeline),
        }


def compute_progress(project_root: str | Path, *, now: float | None = None) -> dict[str, Any]:
    """Return a structured progress view for the panel renderer."""
    root = Path(project_root)
    state = _read_json(root / "project.state.json")
    seed = _read_json(root / "project.seed.json")
    events = _read_events(root / ".samvil" / "events.jsonl")

    current_stage = str(state.get("current_stage") or "")
    completed = state.get("completed_stages") or []
    if not isinstance(completed, list):
        completed = []
    completed = [str(s) for s in completed]

    samvil_tier = (
        str(state.get("samvil_tier") or "")
        or str((state.get("config") or {}).get("samvil_tier") or "")
        or str((state.get("config") or {}).get("selected_tier") or "")
        or "standard"
    )

    leaves = _count_leaves(seed)
    now_ts = float(now) if now is not None else time.time()

    started_at = _stage_started_at(events, current_stage) if current_stage else None
    elapsed = now_ts - started_at if started_at else None

    # ETA: baseline minus elapsed; scale build/qa by leaf ratio when available.
    eta_sec: float | None = None
    if current_stage:
        baseline = _baseline_for(current_stage, samvil_tier)
        if baseline > 0:
            scaled = float(baseline)
            if current_stage in {"build", "qa"} and leaves["total"] > 0:
                # Scale by remaining leaves vs an assumed reference of 8 ACs.
                ref = 8
                scaled = baseline * (max(leaves["total"], 1) / ref)
                # Knock down by progress so far.
                if leaves["total"]:
                    done_ratio = (leaves["pass"] + leaves["fail"]) / leaves["total"]
                    scaled *= max(0.0, 1.0 - done_ratio)
            elif elapsed is not None:
                scaled = max(0.0, baseline - elapsed)
            eta_sec = scaled

    last_event_at = _last_event_at(events)
    last_event_age = (now_ts - last_event_at) if last_event_at else None

    completed_set = set(completed)
    pipeline: list[dict[str, str]] = []
    for s in PIPELINE_STAGES:
        if s in completed_set:
            mark = "done"
        elif s == current_stage:
            mark = "active"
        else:
            mark = "pending"
        pipeline.append({"stage": s, "mark": mark})

    view = ProgressView(
        project_root=str(root),
        project_name=str(seed.get("name") or root.name),
        samvil_tier=samvil_tier,
        current_stage=current_stage,
        completed_stages=completed,
        leaves=leaves,
        elapsed_in_stage_sec=elapsed,
        eta_sec=eta_sec,
        last_event_age_sec=last_event_age,
        pipeline=pipeline,
    )
    return view.to_dict()


def render_panel(progress: dict[str, Any]) -> str:
    """Return an ASCII panel using the dict from compute_progress."""
    lines: list[str] = []
    width = 64

    title = f" SAMVIL Progress — {progress.get('project_name', '')} "
    lines.append("┌" + title.center(width, "─") + "┐")

    def row(label: str, value: str) -> str:
        text = f" {label}: {value}".ljust(width)
        return "│" + text + "│"

    tier = progress.get("samvil_tier", "standard")
    lines.append(row("Tier", tier))

    stage = progress.get("current_stage") or "—"
    elapsed = _format_duration(progress.get("elapsed_in_stage_sec"))
    lines.append(row("Current", f"{stage} (elapsed {elapsed})"))

    # Pipeline strip
    parts: list[str] = []
    for entry in progress.get("pipeline") or []:
        s = entry.get("stage", "")
        m = entry.get("mark", "")
        if m == "done":
            icon = "✓"
        elif m == "active":
            icon = "●"
        else:
            icon = " "
        parts.append(f"[{icon} {s}]")
    pipeline_text = " ".join(parts)
    if len(pipeline_text) > width - 12:
        pipeline_text = pipeline_text[: width - 12] + "…"
    lines.append(row("Pipeline", pipeline_text))

    leaves = progress.get("leaves") or {}
    total = leaves.get("total", 0)
    done = leaves.get("pass", 0) + leaves.get("fail", 0)
    leaves_text = (
        f"{done}/{total} leaves done "
        f"({leaves.get('pass', 0)} PASS / {leaves.get('fail', 0)} FAIL "
        f"/ {leaves.get('pending', 0)} pending)"
        if total
        else "no AC tree yet"
    )
    lines.append(row("AC Tree", leaves_text))

    eta = _format_duration(progress.get("eta_sec"))
    lines.append(row("ETA", eta))

    last_age = _format_duration(progress.get("last_event_age_sec"))
    lines.append(row("Last event", f"{last_age} ago" if last_age != "unknown" else "unknown"))

    lines.append("└" + "─" * width + "┘")
    return "\n".join(lines)
