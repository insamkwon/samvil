"""Smoke tests for samvil-doctor (T3.1 ultra-thin migration).

These tests exercise the new `diagnose_environment` MCP tool and the
underlying `samvil_mcp.diagnostic` module. They protect the behaviors
that the skill body now delegates instead of executing inline:

- mcp-health log summarization (ok/fail counts, recent failures, missing
  log handled gracefully).
- v3 tool coverage check (replaces the embedded heredoc).
- Model recommendation table (single source of truth).
- The aggregated `diagnose_environment` payload contract.

Shell-bound checks (node --version, pytest, du, git) are intentionally
not covered here — those stay in the skill body and are validated by
running `/samvil:samvil-doctor` interactively.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import diagnostic


# ── mcp-health summarization ──────────────────────────────────


def _write_health_log(base: Path, entries: list[dict]) -> Path:
    """Helper: write entries to <base>/.samvil/mcp-health.jsonl."""
    log = base / ".samvil" / "mcp-health.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return log


def test_health_summary_missing_log_is_zero_state(tmp_path: Path) -> None:
    """A missing mcp-health.jsonl must not raise — doctor still renders."""
    summary = diagnostic.summarize_mcp_health(base=tmp_path)
    assert summary.log_exists is False
    assert summary.total_lines == 0
    assert summary.ok_count == 0
    assert summary.fail_count == 0
    assert summary.recent_failures == []


def test_health_summary_counts_ok_and_fail(tmp_path: Path) -> None:
    _write_health_log(
        tmp_path,
        [
            {"status": "ok", "tool": "save_event", "timestamp": "t1"},
            {"status": "ok", "tool": "save_event", "timestamp": "t2"},
            {"status": "fail", "tool": "validate_seed", "error": "boom", "timestamp": "t3"},
        ],
    )
    summary = diagnostic.summarize_mcp_health(base=tmp_path)
    assert summary.log_exists is True
    assert summary.total_lines == 3
    assert summary.ok_count == 2
    assert summary.fail_count == 1
    assert len(summary.recent_failures) == 1
    assert summary.recent_failures[0]["tool"] == "validate_seed"
    assert summary.recent_failures[0]["error"] == "boom"


def test_health_summary_tolerates_garbage_lines(tmp_path: Path) -> None:
    """Bad jsonl lines must not crash the doctor."""
    log = tmp_path / ".samvil" / "mcp-health.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "not-json\n"
        + json.dumps({"status": "ok", "tool": "x"}) + "\n"
        + "{partial\n"
        + json.dumps({"status": "fail", "tool": "y", "error": "z"}) + "\n",
        encoding="utf-8",
    )
    summary = diagnostic.summarize_mcp_health(base=tmp_path)
    assert summary.parse_errors == 2
    assert summary.ok_count == 1
    assert summary.fail_count == 1


def test_health_summary_tail_respects_limit(tmp_path: Path) -> None:
    entries = [
        {"status": "ok", "tool": f"t{i}", "timestamp": str(i)} for i in range(20)
    ]
    _write_health_log(tmp_path, entries)
    summary = diagnostic.summarize_mcp_health(base=tmp_path, tail=5)
    assert len(summary.last_entries) == 5
    assert summary.last_entries[-1]["tool"] == "t19"


# ── Tool inventory ─────────────────────────────────────────────


def test_list_registered_tools_against_real_server() -> None:
    """v3 tools must all be registered (replaces heredoc check)."""
    from samvil_mcp.server import mcp

    inv = diagnostic.list_registered_tools(mcp)
    assert inv["count"] > 0
    assert inv["v3_missing"] == [], (
        f"v3 tools missing from registered set: {inv['v3_missing']}"
    )
    # Sanity: a known stable tool name should exist.
    assert "validate_seed" in inv["tools"]


def test_list_registered_tools_includes_diagnose_environment() -> None:
    """The new T3.1 tool itself must be wired in server.py."""
    from samvil_mcp.server import mcp

    inv = diagnostic.list_registered_tools(mcp)
    assert "diagnose_environment" in inv["tools"]


# ── Model recommendation table ────────────────────────────────


def test_model_recommendation_table_shape() -> None:
    table = diagnostic.model_recommendation_table()
    assert table["reference"] == "references/cost-aware-mode.md"
    rows = table["rows"]
    assert len(rows) >= 10
    # Every row must have the four columns the skill renders.
    for r in rows:
        assert set(r.keys()) >= {"stage", "recommended", "cost_tier", "notes"}
    # Stages must include the canonical pipeline stages.
    stages = {r["stage"] for r in rows}
    for required in {"Interview", "Seed", "Design", "Build worker", "QA", "Retro"}:
        assert required in stages


# ── Aggregated diagnose_environment ───────────────────────────


def test_diagnose_environment_payload_contract(tmp_path: Path) -> None:
    """The aggregated payload must include all three doctor sections."""
    from samvil_mcp.server import mcp

    _write_health_log(
        tmp_path,
        [{"status": "ok", "tool": "save_event", "timestamp": "t1"}],
    )
    result = diagnostic.diagnose_environment(mcp_server=mcp, base=tmp_path)
    assert result["schema_version"] == "1.0"
    assert "generated_at" in result
    assert "mcp_health" in result
    assert "tool_inventory" in result
    assert "model_recommendation" in result
    assert result["mcp_health"]["ok_count"] == 1
    assert "diagnose_environment" in result["tool_inventory"]["tools"]


@pytest.mark.asyncio
async def test_diagnose_environment_mcp_tool_returns_valid_json() -> None:
    """The @mcp.tool wrapper itself must return valid JSON without exception."""
    from samvil_mcp.server import diagnose_environment as tool

    raw = await tool()
    payload = json.loads(raw)
    assert "error" not in payload, payload
    assert "mcp_health" in payload
    assert "tool_inventory" in payload
    assert "model_recommendation" in payload
