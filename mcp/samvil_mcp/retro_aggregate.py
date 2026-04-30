"""SAMVIL retro metric aggregator (T4.1).

Centralizes the inputs the `samvil-retro` skill needs that are best
produced from inside the MCP process — single source of truth for the
metric extraction, recurring-pattern detection, and ID assignment that
previously lived inline in the skill body across ~500 LOC of Korean
prose:

- Run metric aggregation from `project.state.json`, `.samvil/metrics.json`,
  `.samvil/events.jsonl`, and `interview-summary.md`.
- Recurring-pattern detection across `harness-feedback.log` history
  (keywords appearing in 3+ historical suggestions).
- Bottleneck-stage identification (top stages by `duration_ms`).
- Flow compliance check (planned vs. actual stage sequence).
- Agent-utilization (configured tier vs. actually-spawned agents).
- v3 AC tree leaf stats (counts grouped by `data.status`).
- Next suggestion ID computation (max `vN-NNN` across all entries + N).
- MCP health summary from `.samvil/mcp-health.jsonl`.

What stays in the skill body:

- Choosing exactly 3 suggestions to write (semantic decision; LLM-bound).
- AskUserQuestion for the new-app-preset accumulation prompt.
- Writing the appended entry back to `harness-feedback.log` (the skill
  decides whether to mutate the file vs. dry-run).
- Pipeline-end Compressor narrate (separate `narrate_*` MCP tools).
- Console rendering of the dashboard text.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Planned canonical stage order for flow-compliance check.
PLANNED_STAGES: tuple[str, ...] = (
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

# Words too generic to count as a "recurring pattern" keyword.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on",
        "for", "with", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "this", "that", "these", "those", "it", "its", "as", "at",
        "by", "from", "into", "out", "up", "down", "off", "over", "under",
        "again", "more", "less", "very", "too", "no", "not", "only",
        "samvil", "skill", "stage", "step", "tier", "use", "used", "using",
        "fix", "add", "make", "ensure", "check",
    }
)

_KEYWORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-_]{3,}")


@dataclass
class RunMetrics:
    """Structured per-run metrics extracted from project files."""

    seed_name: str = ""
    schema_version: str = ""
    features_attempted: int = 0
    features_passed: int = 0
    features_failed: int = 0
    build_retries: int = 0
    qa_iterations: int = 0
    qa_verdict: str = ""
    interview_questions: int = 0
    stage_durations_ms: dict[str, int] = field(default_factory=dict)
    total_duration_ms: int = 0
    bottleneck_stages: list[str] = field(default_factory=list)
    build_pass_rate: float = 0.0
    qa_pass_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed_name": self.seed_name,
            "schema_version": self.schema_version,
            "features_attempted": self.features_attempted,
            "features_passed": self.features_passed,
            "features_failed": self.features_failed,
            "build_retries": self.build_retries,
            "qa_iterations": self.qa_iterations,
            "qa_verdict": self.qa_verdict,
            "interview_questions": self.interview_questions,
            "stage_durations_ms": dict(self.stage_durations_ms),
            "total_duration_ms": self.total_duration_ms,
            "bottleneck_stages": list(self.bottleneck_stages),
            "build_pass_rate": self.build_pass_rate,
            "qa_pass_rate": self.qa_pass_rate,
        }


# ── Helpers ────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _count_questions(interview_summary: Path) -> int:
    if not interview_summary.exists():
        return 0
    n = 0
    for line in interview_summary.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("Q") and "?" in s:
            n += 1
        elif s.endswith("?") and len(s) > 5:
            n += 1
    return n


def _normalize_keywords(text: str) -> list[str]:
    """Lower-cased keyword tokens longer than 3 chars, minus stopwords."""
    tokens = _KEYWORD_RE.findall(text or "")
    return [t.lower() for t in tokens if t.lower() not in _STOPWORDS]


# ── Sub-aggregators ────────────────────────────────────────────────────


def _derive_features_from_seed(seed: dict[str, Any]) -> tuple[int, int, int]:
    """Return (attempted, passed, failed) from seed.features when state is silent.

    Uses the leaf-level status fields that samvil-build writes back into
    the seed's AC tree. Falls back to feature count with unknown status.
    """
    features = seed.get("features") or []
    if not isinstance(features, list):
        return 0, 0, 0
    passed = failed = 0
    for f in features:
        if not isinstance(f, dict):
            continue
        acs = f.get("acceptance_criteria") or []
        if not isinstance(acs, list):
            continue
        for ac in acs:
            if not isinstance(ac, dict):
                continue
            status = str(ac.get("status", "")).upper()
            if status == "PASS":
                passed += 1
            elif status in ("FAIL", "FAILED"):
                failed += 1
    total = len(features)
    if passed == 0 and failed == 0:
        return total, 0, 0
    return passed + failed, passed, failed


def _derive_qa_verdict_from_files(
    state: dict[str, Any],
    qa_results: dict[str, Any],
) -> tuple[str, int]:
    """Return (qa_verdict, qa_iterations) from state/qa-results when
    events.jsonl doesn't carry qa_history.
    """
    verdict = ""
    iterations = 0
    # 1. Direct qa_status field in state (samvil writes this)
    raw = str(state.get("qa_status") or "").strip().upper()
    if raw:
        verdict = raw
    # 2. qa_results.json overall verdict
    if not verdict:
        raw = str(qa_results.get("verdict") or qa_results.get("overall_verdict") or "").strip().upper()
        if raw:
            verdict = raw
    # 3. Count iterations from qa_results passes array
    passes = qa_results.get("passes") or []
    if isinstance(passes, list):
        iterations = len(passes)
    return verdict, iterations


def extract_metrics(
    state: dict[str, Any],
    metrics: dict[str, Any],
    seed: dict[str, Any],
    interview_summary_path: Path,
    qa_results: dict[str, Any] | None = None,
) -> RunMetrics:
    rm = RunMetrics()
    rm.seed_name = str(seed.get("name", state.get("seed_name", "")))
    rm.schema_version = str(seed.get("schema_version", ""))

    completed = state.get("completed_features") or []
    failed = state.get("failed") or state.get("failed_features") or []
    rm.features_passed = len(completed) if isinstance(completed, list) else 0
    rm.features_failed = len(failed) if isinstance(failed, list) else 0
    rm.features_attempted = rm.features_passed + rm.features_failed

    # File-based fallback when state has no completed_features (sparse events)
    if rm.features_attempted == 0 and seed:
        rm.features_attempted, rm.features_passed, rm.features_failed = (
            _derive_features_from_seed(seed)
        )

    rm.build_retries = int(state.get("build_retries", 0) or 0)
    qa_history = state.get("qa_history") or []
    rm.qa_iterations = len(qa_history) if isinstance(qa_history, list) else 0
    if isinstance(qa_history, list) and qa_history:
        last = qa_history[-1]
        if isinstance(last, dict):
            rm.qa_verdict = str(last.get("verdict", "")).upper()
        elif isinstance(last, str):
            rm.qa_verdict = last.upper()

    # File-based fallback when qa_history is absent (Codex sparse events)
    if not rm.qa_verdict and qa_results is not None:
        derived_verdict, derived_iters = _derive_qa_verdict_from_files(state, qa_results)
        rm.qa_verdict = derived_verdict
        if rm.qa_iterations == 0 and derived_iters:
            rm.qa_iterations = derived_iters
    # Final fallback: qa_status on state (always written by samvil-qa)
    if not rm.qa_verdict:
        raw = str(state.get("qa_status") or "").strip().upper()
        if raw:
            rm.qa_verdict = raw

    rm.interview_questions = _count_questions(interview_summary_path)

    stages = metrics.get("stages") or {}
    if isinstance(stages, dict):
        for name, info in stages.items():
            if not isinstance(info, dict):
                continue
            d = info.get("duration_ms")
            if isinstance(d, (int, float)):
                rm.stage_durations_ms[name] = int(d)
        # Pass rates are sometimes pre-computed in metrics.json
        qa = stages.get("qa", {}) if isinstance(stages.get("qa"), dict) else {}
        pr = qa.get("pass_rate")
        if isinstance(pr, (int, float)):
            rm.qa_pass_rate = float(pr)

    rm.total_duration_ms = int(metrics.get("total_duration_ms", 0) or 0)
    if rm.total_duration_ms == 0 and rm.stage_durations_ms:
        rm.total_duration_ms = sum(rm.stage_durations_ms.values())

    if rm.features_attempted > 0:
        rm.build_pass_rate = round(
            rm.features_passed / rm.features_attempted, 3
        )

    # Top-2 bottleneck stages (>= 20% of total).
    if rm.total_duration_ms > 0 and rm.stage_durations_ms:
        ranked = sorted(
            rm.stage_durations_ms.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )
        rm.bottleneck_stages = [
            name
            for name, dur in ranked[:2]
            if dur / rm.total_duration_ms >= 0.20
        ]

    return rm


def detect_recurring_patterns(
    feedback_entries: list[dict[str, Any]],
    *,
    min_occurrences: int = 3,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Scan harness-feedback.log entries for keywords that repeat across
    distinct historical suggestions (suggestions_v2 + legacy suggestions).

    Returns a list of `{keyword, count, runs}` dicts sorted by count desc.
    """
    counter: Counter[str] = Counter()
    keyword_runs: dict[str, set[str]] = {}

    for entry in feedback_entries:
        run_id = str(entry.get("run_id", ""))
        items: list[str] = []
        for it in entry.get("suggestions_v2") or []:
            if isinstance(it, dict):
                items.extend(
                    [
                        str(it.get("name", "")),
                        str(it.get("problem", "")),
                        str(it.get("fix", "")),
                    ]
                )
        legacy = entry.get("suggestions") or []
        if isinstance(legacy, list):
            items.extend(str(x) for x in legacy)

        seen_in_entry: set[str] = set()
        for blob in items:
            for kw in _normalize_keywords(blob):
                if kw in seen_in_entry:
                    continue
                seen_in_entry.add(kw)
                counter[kw] += 1
                keyword_runs.setdefault(kw, set()).add(run_id)

    out: list[dict[str, Any]] = []
    for kw, n in counter.most_common(top_n * 4):
        if n < min_occurrences:
            continue
        out.append(
            {
                "keyword": kw,
                "count": n,
                "runs": sorted(keyword_runs.get(kw, set())),
            }
        )
        if len(out) >= top_n:
            break
    return out


def compute_flow_compliance(
    events: list[dict[str, Any]],
    *,
    planned: tuple[str, ...] = PLANNED_STAGES,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Walk events.jsonl, extract the actual stage sequence (deduped
    consecutive), count per-stage entries, and compare against the
    planned canonical order.

    Falls back to `state.completed_stages` when events.jsonl is sparse
    (e.g., Codex runs that didn't emit full stage events).
    """
    sequence: list[str] = []
    counts: Counter[str] = Counter()
    for ev in events:
        stage = ev.get("stage") or ""
        if not stage:
            continue
        counts[stage] += 1
        if not sequence or sequence[-1] != stage:
            sequence.append(stage)

    source = "events"
    # File-based fallback: completed_stages in project.state.json
    if not sequence and state:
        completed_stages = state.get("completed_stages") or []
        if isinstance(completed_stages, list):
            for s in completed_stages:
                s = str(s)
                if s and (not sequence or sequence[-1] != s):
                    sequence.append(s)
                counts[s] += 1
            if sequence:
                source = "state_file"

    deviations: list[str] = []
    for stage in planned:
        if stage in counts and counts[stage] > 3:
            deviations.append(
                f"{stage} executed {counts[stage]}× (expected 1-3)"
            )
    actual_set = set(sequence)
    skipped = [s for s in planned if s not in actual_set]
    if "evolve" in skipped:
        # Evolve is optional; report as info, not deviation.
        skipped.remove("evolve")

    return {
        "planned": list(planned),
        "actual_sequence": sequence,
        "stage_counts": dict(counts),
        "deviations": deviations,
        "skipped_stages": skipped,
        "matched": len(deviations) == 0 and not skipped,
        "source": source,
    }


def compute_agent_utilization(
    events: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Cross-reference configured tier agents against actually-spawned
    agents seen in events.jsonl.
    """
    tier = (
        state.get("config", {}).get("selected_tier")
        or state.get("selected_tier")
        or ""
    )
    # Tier agent counts mirror references/tier-definitions.md.
    tier_total = {
        "minimal": 10,
        "standard": 20,
        "thorough": 30,
        "full": 36,
        "deep": 36,
    }.get(str(tier), 0)

    spawned: set[str] = set()
    for ev in events:
        data = ev.get("data") or {}
        # Common shapes: data.agent / data.agents (list) / data.agent_role
        for key in ("agent", "agent_role", "role"):
            v = data.get(key) if isinstance(data, dict) else None
            if isinstance(v, str) and v:
                spawned.add(v)
        agents = data.get("agents") if isinstance(data, dict) else None
        if isinstance(agents, list):
            for a in agents:
                if isinstance(a, str) and a:
                    spawned.add(a)

    used = len(spawned)
    pct = round(used / tier_total, 3) if tier_total else 0.0
    return {
        "tier": str(tier),
        "tier_total": tier_total,
        "used": used,
        "spawned": sorted(spawned),
        "utilization": pct,
        "underutilized": pct < 0.5 and tier_total > 0,
    }


def compute_v3_leaf_stats(
    events: list[dict[str, Any]],
    qa_results: dict[str, Any] | None = None,
    seed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group `ac_leaf_complete` events by `data.status`.

    Falls back to qa-results.json AC counts and seed.features AC tree
    when events.jsonl is sparse (e.g., Codex runs that skipped MCP writes).
    """
    by_status: Counter[str] = Counter()
    leaves_seen = 0
    for ev in events:
        if ev.get("event_type") != "ac_leaf_complete":
            continue
        leaves_seen += 1
        data = ev.get("data") or {}
        status = ""
        if isinstance(data, dict):
            status = str(data.get("status", "unknown"))
        by_status[status or "unknown"] += 1

    feature_tree_complete: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "feature_tree_complete":
            continue
        data = ev.get("data") or {}
        if isinstance(data, dict):
            feature_tree_complete.append(
                {
                    "feature": data.get("feature") or data.get("feature_id"),
                    "passed": data.get("passed"),
                    "failed": data.get("failed"),
                    "total_leaves": data.get("total_leaves"),
                }
            )

    # File-based fallback: derive leaf stats from qa-results.json
    if leaves_seen == 0 and qa_results:
        ac_results = qa_results.get("ac_results") or qa_results.get("results") or []
        if isinstance(ac_results, list):
            for ac in ac_results:
                if not isinstance(ac, dict):
                    continue
                status = str(ac.get("status", "unknown")).upper()
                by_status[status] += 1
                leaves_seen += 1

    # Last resort: walk seed.features AC tree for status counts
    if leaves_seen == 0 and seed:
        for f in (seed.get("features") or []):
            if not isinstance(f, dict):
                continue
            for ac in (f.get("acceptance_criteria") or []):
                if not isinstance(ac, dict):
                    continue
                status = str(ac.get("status", "unknown")).upper()
                by_status[status] += 1
                leaves_seen += 1

    return {
        "total_leaf_events": leaves_seen,
        "by_status": dict(by_status),
        "feature_tree_complete": feature_tree_complete,
        "source": (
            "events"
            if any(ev.get("event_type") == "ac_leaf_complete" for ev in events)
            else ("qa_results" if (qa_results and qa_results.get("ac_results"))
                  else ("seed" if leaves_seen > 0 else "none"))
        ),
    }


_ID_RE = re.compile(r"^v(\d+)-(\d+)$")


def next_suggestion_id(
    feedback_entries: list[dict[str, Any]],
    major: int,
) -> str:
    """Scan all `suggestions_v2[].id` across history and return the
    next available `v<major>-<NNN>` for the requested major version.

    If no IDs exist for that major, starts at `v<major>-001`.
    """
    max_n = 0
    for entry in feedback_entries:
        for it in entry.get("suggestions_v2") or []:
            if not isinstance(it, dict):
                continue
            m = _ID_RE.match(str(it.get("id", "")))
            if not m:
                continue
            if int(m.group(1)) != major:
                continue
            n = int(m.group(2))
            if n > max_n:
                max_n = n
    return f"v{major}-{max_n + 1:03d}"


def summarize_mcp_health(path: Path) -> dict[str, Any]:
    """Lightweight mcp-health.jsonl summary for the retro report."""
    if not path.exists():
        return {
            "exists": False,
            "total": 0,
            "ok": 0,
            "fail": 0,
            "fail_rate": 0.0,
            "failed_tools": [],
        }
    total = ok = fail = 0
    failed: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        total += 1
        status = str(row.get("status", "")).lower()
        if status == "ok":
            ok += 1
        elif status == "fail":
            fail += 1
            tool = str(row.get("tool", "unknown"))
            failed[tool] += 1
    fail_rate = round(fail / total, 3) if total else 0.0
    return {
        "exists": True,
        "total": total,
        "ok": ok,
        "fail": fail,
        "fail_rate": fail_rate,
        "failed_tools": [
            {"tool": t, "count": c} for t, c in failed.most_common(10)
        ],
        "warning": fail_rate > 0.20,
    }


# ── Top-level aggregator ───────────────────────────────────────────────


def aggregate_retro_metrics(
    project_root: str,
    *,
    plugin_root: str = "",
    suggestion_major: int = 3,
) -> dict[str, Any]:
    """Single aggregator for the samvil-retro skill body.

    Reads (best-effort) from `project_root`:
      - `project.seed.json`
      - `project.state.json`
      - `.samvil/metrics.json`
      - `.samvil/events.jsonl`
      - `.samvil/mcp-health.jsonl`
      - `interview-summary.md`

    And from `plugin_root` (or auto-detected):
      - `harness-feedback.log`

    Returns a dict shaped for the skill to render directly:

    {
      "schema_version": "1.0",
      "project_root": "...",
      "feedback_log_path": "...",
      "metrics": {RunMetrics.to_dict()},
      "recurring_patterns": [{keyword, count, runs}, ...],
      "flow_compliance": {...},
      "agent_utilization": {...},
      "v3_leaf_stats": {...},
      "mcp_health": {...},
      "next_suggestion_id": "v3-NNN",
      "feedback_entries_count": N,
      "errors": [strings],   # non-fatal warnings
    }
    """
    errors: list[str] = []
    proj = Path(project_root)
    seed = _read_json(proj / "project.seed.json")
    state = _read_json(proj / "project.state.json")
    metrics = _read_json(proj / ".samvil" / "metrics.json")
    events = _read_jsonl(proj / ".samvil" / "events.jsonl")
    interview_summary = proj / "interview-summary.md"
    # v3-003: also load qa-results.json as a file-based fallback source
    qa_results = _read_json(proj / ".samvil" / "qa-results.json")

    rm = extract_metrics(state, metrics, seed, interview_summary, qa_results=qa_results or None)

    # Resolve harness-feedback.log location:
    # 1. explicit plugin_root arg
    # 2. CLAUDE_PLUGIN_ROOT env var (skill body responsibility, not here)
    # 3. fall back to project_root for self-hosted dogfood runs
    feedback_path: Path | None = None
    if plugin_root:
        cand = Path(plugin_root) / "harness-feedback.log"
        if cand.exists():
            feedback_path = cand
    if feedback_path is None:
        # Cache glob for installed plugin: ~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log
        cache_glob = list(
            (Path.home() / ".claude" / "plugins" / "cache" / "samvil" / "samvil")
            .glob("*/harness-feedback.log")
        )
        if cache_glob:
            feedback_path = sorted(cache_glob)[-1]
    if feedback_path is None:
        cand = proj / "harness-feedback.log"
        if cand.exists():
            feedback_path = cand

    feedback_entries: list[dict[str, Any]] = []
    if feedback_path is not None and feedback_path.exists():
        try:
            raw = json.loads(feedback_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                feedback_entries = [e for e in raw if isinstance(e, dict)]
            else:
                errors.append(
                    "harness-feedback.log is not a JSON array; ignoring"
                )
        except Exception as e:
            errors.append(f"harness-feedback.log parse error: {e}")

    return {
        "schema_version": "1.0",
        "project_root": str(proj),
        "feedback_log_path": (
            str(feedback_path) if feedback_path is not None else ""
        ),
        "metrics": rm.to_dict(),
        "recurring_patterns": detect_recurring_patterns(feedback_entries),
        "flow_compliance": compute_flow_compliance(events, state=state),
        "agent_utilization": compute_agent_utilization(events, state),
        "v3_leaf_stats": compute_v3_leaf_stats(events, qa_results=qa_results or None, seed=seed or None),
        "mcp_health": summarize_mcp_health(
            proj / ".samvil" / "mcp-health.jsonl"
        ),
        "next_suggestion_id": next_suggestion_id(
            feedback_entries, suggestion_major
        ),
        "feedback_entries_count": len(feedback_entries),
        "errors": errors,
    }
