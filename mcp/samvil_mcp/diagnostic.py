"""SAMVIL diagnostic aggregator (T3.1).

Centralizes the inputs the `samvil-doctor` skill needs that are best
produced from inside the MCP process:

- Recent MCP health summary (parses ~/.samvil/mcp-health.jsonl).
- Registered MCP tool inventory (replaces brittle Python heredoc that
  imported server.py from a shell).
- Per-stage model recommendation table (single source of truth so the
  skill doesn't repeat a static markdown block).

Anything that *requires* a shell (node --version, pytest, du, git) stays
in the skill body — those are intentionally CC-bound and aligned with
P8 (graceful degradation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _health_log_path(base: Path | None = None) -> Path:
    """Resolve the canonical mcp-health.jsonl path.

    Tests can override `base` to point at a temp directory.
    """
    root = base if base is not None else Path.home()
    return root / ".samvil" / "mcp-health.jsonl"


@dataclass
class HealthSummary:
    """Aggregate view of recent MCP-tool calls."""

    log_path: str
    log_exists: bool
    total_lines: int = 0
    ok_count: int = 0
    fail_count: int = 0
    recent_failures: list[dict[str, Any]] = field(default_factory=list)
    last_entries: list[dict[str, Any]] = field(default_factory=list)
    parse_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_path": self.log_path,
            "log_exists": self.log_exists,
            "total_lines": self.total_lines,
            "ok_count": self.ok_count,
            "fail_count": self.fail_count,
            "recent_failures": self.recent_failures,
            "last_entries": self.last_entries,
            "parse_errors": self.parse_errors,
        }


def summarize_mcp_health(
    *,
    base: Path | None = None,
    tail: int = 10,
    failure_window: int = 50,
) -> HealthSummary:
    """Read mcp-health.jsonl and produce a structured summary.

    - `tail` controls how many last entries to surface in `last_entries`.
    - `failure_window` controls how many trailing lines to scan for
      `status == "fail"` entries reported in `recent_failures`.
    - Missing log is treated as a healthy zero-state (not an error) so
      the doctor can still render its report.
    """
    path = _health_log_path(base)
    summary = HealthSummary(log_path=str(path), log_exists=path.exists())
    if not summary.log_exists:
        return summary

    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        # Treat unreadable file as missing rather than crashing.
        summary.log_exists = False
        return summary

    summary.total_lines = len(lines)
    parsed: list[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            summary.parse_errors += 1
            continue
        if not isinstance(entry, dict):
            summary.parse_errors += 1
            continue
        parsed.append(entry)

        status = entry.get("status")
        if status == "ok":
            summary.ok_count += 1
        elif status == "fail":
            summary.fail_count += 1

    if tail > 0:
        summary.last_entries = parsed[-tail:]

    if failure_window > 0:
        window = parsed[-failure_window:]
        summary.recent_failures = [
            {
                "tool": e.get("tool"),
                "error": e.get("error", ""),
                "timestamp": e.get("timestamp"),
            }
            for e in window
            if e.get("status") == "fail"
        ]

    return summary


V3_EXPECTED_TOOLS: list[str] = sorted(
    [
        "next_buildable_leaves",
        "tree_progress",
        "update_leaf_status",
        "migrate_seed",
        "migrate_seed_file",
        "analyze_ac_dependencies",
        "rate_budget_acquire",
        "rate_budget_release",
        "rate_budget_stats",
        "rate_budget_reset",
        "validate_pm_seed",
        "pm_seed_to_eng_seed",
    ]
)


async def list_registered_tools_async(mcp_server: Any) -> dict[str, Any]:
    """Async variant — safe to call from inside an existing event loop."""
    tool_objs = await mcp_server.list_tools()
    tool_names = sorted({t.name for t in tool_objs})
    present = sorted(set(V3_EXPECTED_TOOLS) & set(tool_names))
    missing = sorted(set(V3_EXPECTED_TOOLS) - set(tool_names))
    return {
        "count": len(tool_names),
        "tools": tool_names,
        "v3_expected": list(V3_EXPECTED_TOOLS),
        "v3_present": present,
        "v3_missing": missing,
    }


def list_registered_tools(mcp_server: Any) -> dict[str, Any]:
    """Sync introspection of a FastMCP server.

    Use only outside an event loop (tests, scripts). Inside MCP request
    handlers prefer `list_registered_tools_async`.
    """
    import asyncio

    try:
        return asyncio.run(list_registered_tools_async(mcp_server))
    except RuntimeError:
        # Already inside a loop — caller must use the async variant.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(list_registered_tools_async(mcp_server))
        finally:
            loop.close()


# Single source of truth for the per-stage model recommendation that the
# doctor used to render as static markdown. Kept here so the skill body
# doesn't drift out of sync with `references/cost-aware-mode.md`.
MODEL_RECOMMENDATIONS: list[dict[str, str]] = [
    {"stage": "Interview",   "recommended": "Opus / Sonnet", "cost_tier": "high", "notes": "Or GLM-5.1 (cost-aware)"},
    {"stage": "Seed",        "recommended": "Sonnet",        "cost_tier": "med",  "notes": "JSON schema precision"},
    {"stage": "Council R1",  "recommended": "Haiku 4.5",     "cost_tier": "low",  "notes": "Research breadth"},
    {"stage": "Council R2",  "recommended": "Sonnet",        "cost_tier": "med",  "notes": "Judgement"},
    {"stage": "Design",      "recommended": "Sonnet",        "cost_tier": "med",  "notes": "Faster than GLM (measured)"},
    {"stage": "Scaffold",    "recommended": "Sonnet / GLM",  "cost_tier": "low",  "notes": "File generation"},
    {"stage": "Build worker","recommended": "Sonnet",        "cost_tier": "med",  "notes": "AC leaf implementation"},
    {"stage": "QA",          "recommended": "Sonnet",        "cost_tier": "med",  "notes": "Playwright integration"},
    {"stage": "Evolve c1",   "recommended": "Haiku",         "cost_tier": "low",  "notes": "Wonder analysis"},
    {"stage": "Evolve c2+",  "recommended": "Sonnet",        "cost_tier": "med",  "notes": "Reflect depth"},
    {"stage": "Retro",       "recommended": "Haiku",         "cost_tier": "low",  "notes": "Aggregation"},
]


def model_recommendation_table() -> dict[str, Any]:
    """Return the per-stage model recommendation table as data."""
    return {
        "rows": list(MODEL_RECOMMENDATIONS),
        "reference": "references/cost-aware-mode.md",
        "note": (
            "Sonnet measured ~6x faster than GLM on Design "
            "(vampire-survivors dogfood). For cost-aware setup see §2b."
        ),
    }


async def diagnose_environment_async(
    *,
    mcp_server: Any | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Async aggregator — safe inside the live MCP event loop."""
    health = summarize_mcp_health(base=base)
    if mcp_server is not None:
        try:
            inventory = await list_registered_tools_async(mcp_server)
        except Exception as e:  # pragma: no cover - defensive
            inventory = {"error": str(e)}
    else:
        inventory = {
            "error": "mcp_server not provided; skill should pass server reference",
        }

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mcp_health": health.to_dict(),
        "tool_inventory": inventory,
        "model_recommendation": model_recommendation_table(),
    }


def diagnose_environment(
    *,
    mcp_server: Any | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Sync aggregator — for tests and scripts not running an event loop.

    Returns a dict shaped:
        {
          "schema_version": "1.0",
          "generated_at": ISO timestamp,
          "mcp_health": HealthSummary.to_dict(),
          "tool_inventory": {...} or {"error": str} if mcp_server is None,
          "model_recommendation": {...},
        }
    """
    import asyncio

    try:
        return asyncio.run(
            diagnose_environment_async(mcp_server=mcp_server, base=base)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                diagnose_environment_async(mcp_server=mcp_server, base=base)
            )
        finally:
            loop.close()
