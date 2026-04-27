"""Health Tiers — 3-tier health classification for MCP telemetry (M4).

Classifies system health into three tiers:
  - healthy: <5% failure rate, no critical tools failing
  - degraded: 5-20% failure rate, or non-critical tools failing
  - critical: >20% failure rate, or critical tools failing

Critical tools are those that pipeline stages depend on:
  save_event, validate_seed, save_seed_version, gate_check,
  build_checklist, score_ambiguity, write_chain_marker
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SAMVIL_DIR = ".samvil"
HEALTH_LOG = "mcp-health.jsonl"

CRITICAL_TOOLS: frozenset[str] = frozenset({
    "save_event",
    "validate_seed",
    "save_seed_version",
    "gate_check",
    "build_checklist",
    "score_ambiguity",
    "write_chain_marker",
    "read_chain_marker",
    "get_pipeline_status",
})

HEALTHY_THRESHOLD = 0.05   # <5% fail rate
CRITICAL_THRESHOLD = 0.20  # >20% fail rate


@dataclass
class TierResult:
    tier: str  # "healthy" | "degraded" | "critical"
    fail_rate: float
    total_calls: int
    fail_count: int
    ok_count: int
    critical_failures: list[str] = field(default_factory=list)
    degraded_tools: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "fail_rate": round(self.fail_rate, 4),
            "total_calls": self.total_calls,
            "fail_count": self.fail_count,
            "ok_count": self.ok_count,
            "critical_failures": self.critical_failures,
            "degraded_tools": self.degraded_tools,
            "recommendation": self.recommendation,
        }


def classify_health(
    health_entries: list[dict[str, Any]],
) -> TierResult:
    """Classify system health from MCP health log entries.

    Each entry should have: status ("ok"|"fail"), tool (str).
    """
    if not health_entries:
        return TierResult(
            tier="healthy",
            fail_rate=0.0,
            total_calls=0,
            fail_count=0,
            ok_count=0,
            recommendation="No health data available. Run pipeline to generate.",
        )

    total = len(health_entries)
    fails = [e for e in health_entries if e.get("status") == "fail"]
    oks = total - len(fails)
    fail_rate = len(fails) / total if total > 0 else 0.0

    # Check critical tool failures
    critical_failures = list({
        e.get("tool", "") for e in fails
        if e.get("tool", "") in CRITICAL_TOOLS
    })

    # Check per-tool degradation (any tool >20% fail)
    tool_counts: dict[str, dict[str, int]] = {}
    for e in health_entries:
        tool = e.get("tool", "unknown")
        status = e.get("status", "ok")
        if tool not in tool_counts:
            tool_counts[tool] = {"ok": 0, "fail": 0}
        tool_counts[tool][status] = tool_counts[tool].get(status, 0) + 1

    degraded_tools = []
    for tool, counts in tool_counts.items():
        t = counts["ok"] + counts["fail"]
        if t >= 3 and counts["fail"] / t > 0.20:
            degraded_tools.append(tool)

    # Classify
    if critical_failures or fail_rate > CRITICAL_THRESHOLD:
        tier = "critical"
        rec = _critical_recommendation(critical_failures, fail_rate)
    elif fail_rate > HEALTHY_THRESHOLD or degraded_tools:
        tier = "degraded"
        rec = _degraded_recommendation(degraded_tools, fail_rate)
    else:
        tier = "healthy"
        rec = "System operating normally."

    return TierResult(
        tier=tier,
        fail_rate=fail_rate,
        total_calls=total,
        fail_count=len(fails),
        ok_count=oks,
        critical_failures=sorted(critical_failures),
        degraded_tools=sorted(degraded_tools),
        recommendation=rec,
    )


def get_health_tier(
    project_root: str,
    mcp_health_path: str | None = None,
) -> dict[str, Any]:
    """Load health log and classify. Returns TierResult as dict."""
    entries = _load_health_log(project_root, mcp_health_path)
    result = classify_health(entries)
    return result.to_dict()


def get_health_tier_summary(
    project_root: str,
    mcp_health_path: str | None = None,
) -> str:
    """Human-readable health tier summary."""
    result = get_health_tier(project_root, mcp_health_path)
    tier = result["tier"]
    icon = {"healthy": "✅", "degraded": "⚠️", "critical": "🔴"}.get(tier, "?")

    lines = [
        f"## Health Tier: {icon} {tier.upper()}",
        "",
        f"- Total calls: {result['total_calls']}",
        f"- OK: {result['ok_count']} | Fail: {result['fail_count']}",
        f"- Fail rate: {result['fail_rate']:.1%}",
    ]
    if result["critical_failures"]:
        lines.append(f"- Critical failures: {', '.join(result['critical_failures'])}")
    if result["degraded_tools"]:
        lines.append(f"- Degraded tools: {', '.join(result['degraded_tools'])}")
    lines.append(f"- {result['recommendation']}")

    return "\n".join(lines)


def _load_health_log(
    project_root: str,
    mcp_health_path: str | None = None,
) -> list[dict[str, Any]]:
    if mcp_health_path:
        path = Path(mcp_health_path).expanduser()
    else:
        path = Path.home() / ".samvil" / HEALTH_LOG

    if not path.exists():
        return []

    entries = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    return entries


def _critical_recommendation(failures: list[str], rate: float) -> str:
    parts = [f"Fail rate {rate:.0%} exceeds critical threshold."]
    if failures:
        parts.append(f"Critical tools failing: {', '.join(failures)}.")
    parts.append("Pipeline may not complete reliably. Check MCP server logs.")
    return " ".join(parts)


def _degraded_recommendation(tools: list[str], rate: float) -> str:
    parts = [f"Fail rate {rate:.0%} above normal threshold."]
    if tools:
        parts.append(f"Degraded tools: {', '.join(tools)}.")
    parts.append("Pipeline should continue but quality may be affected.")
    return " ".join(parts)
