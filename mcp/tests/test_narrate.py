"""Unit tests for samvil narrate (Sprint 4, §6.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from samvil_mcp.narrate import (
    NarrateContext,
    Narrative,
    build_context,
    build_narrate_prompt,
    parse_narrative,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_build_context_filters_to_window(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(
        tmp_path / ".samvil" / "claims.jsonl",
        [
            {
                "claim_id": "c1",
                "type": "ac_verdict",
                "subject": "AC-1",
                "statement": "old",
                "authority_file": "x.json",
                "claimed_by": "agent:a",
                "status": "pending",
                "ts": old,
            },
            {
                "claim_id": "c2",
                "type": "ac_verdict",
                "subject": "AC-2",
                "statement": "fresh",
                "authority_file": "x.json",
                "claimed_by": "agent:a",
                "status": "pending",
                "ts": recent,
            },
        ],
    )

    ctx = build_context(tmp_path)  # default last 7 days
    subjects = [c["subject"] for c in ctx.pending_claims]
    assert "AC-2" in subjects
    assert "AC-1" not in subjects


def test_build_context_collapses_claim_history(tmp_path: Path) -> None:
    """Two rows for the same claim_id — the latest wins (end state)."""
    ts1 = "2026-04-23T00:00:00Z"
    ts2 = "2026-04-23T12:00:00Z"
    _write_jsonl(
        tmp_path / ".samvil" / "claims.jsonl",
        [
            {
                "claim_id": "c1",
                "type": "ac_verdict",
                "subject": "AC-1",
                "statement": "x",
                "authority_file": "x.json",
                "claimed_by": "agent:a",
                "status": "pending",
                "ts": ts1,
            },
            {
                "claim_id": "c1",
                "type": "ac_verdict",
                "subject": "AC-1",
                "statement": "x",
                "authority_file": "x.json",
                "claimed_by": "agent:a",
                "verified_by": "agent:user",
                "status": "verified",
                "ts": ts2,
            },
        ],
    )
    ctx = build_context(tmp_path, since="2000-01-01T00:00:00Z")
    # Claim c1 is now verified — not pending.
    assert ctx.pending_claims == []


def test_build_context_picks_latest_gate_verdict(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / ".samvil" / "claims.jsonl",
        [
            {
                "claim_id": "c1",
                "type": "gate_verdict",
                "subject": "build_to_qa",
                "statement": "v1",
                "authority_file": "state.json",
                "claimed_by": "agent:build-worker",
                "status": "pending",
                "meta": {"verdict": "block"},
                "ts": "2026-04-22T00:00:00Z",
            },
            {
                "claim_id": "c2",
                "type": "gate_verdict",
                "subject": "build_to_qa",
                "statement": "v2",
                "authority_file": "state.json",
                "claimed_by": "agent:build-worker",
                "status": "pending",
                "meta": {"verdict": "pass"},
                "ts": "2026-04-23T00:00:00Z",
            },
        ],
    )
    ctx = build_context(tmp_path, since="2000-01-01T00:00:00Z")
    assert len(ctx.recent_gate_verdicts) == 1
    assert ctx.recent_gate_verdicts[0].get("meta", {}).get("verdict") == "pass"


def test_build_context_flags_uncalibrated_experiments(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / ".samvil" / "experiments.jsonl",
        [
            {"name": "exp1", "observations": []},
            {"name": "exp2", "observations": [{"value_seen": 0.9}]},
        ],
    )
    ctx = build_context(tmp_path, since="2000-01-01T00:00:00Z")
    names = [e["name"] for e in ctx.experiments_below_threshold]
    assert names == ["exp1"]


def test_summary_shape() -> None:
    ctx = NarrateContext(
        window_description="last 7 days",
        since_iso="2026-04-17",
        now_iso="2026-04-24",
        pending_claims=[{"type": "ac_verdict", "subject": "AC-1"}],
        recent_gate_verdicts=[
            {"subject": "build_to_qa", "meta": {"verdict": "block"}}
        ],
    )
    s = ctx.to_summary()
    assert "last 7 days" in s
    assert "AC-1" in s
    assert "build_to_qa" in s


def test_build_narrate_prompt_includes_summary() -> None:
    ctx = NarrateContext(
        window_description="today",
        since_iso="2026-04-24",
        now_iso="2026-04-24",
    )
    prompt = build_narrate_prompt(ctx)
    assert "today" in prompt
    assert "JSON" in prompt
    assert "next_actions" in prompt


def test_parse_narrative_json() -> None:
    raw = json.dumps(
        {
            "what_happened": ["Built feature A", "Passed QA for B"],
            "where_stuck": ["AC-3 pending 3 days"],
            "next_actions": ["Verify AC-3", "Run dogfood", "Bump version"],
        }
    )
    n = parse_narrative(raw)
    assert len(n.what_happened) == 2
    assert len(n.next_actions) == 3


def test_parse_narrative_heuristic_fallback() -> None:
    raw = """
    Some prose with:
    - Built the login flow
    - QA passed on three features
    """
    n = parse_narrative(raw)
    assert "Built the login flow" in n.what_happened
    assert len(n.what_happened) == 2


def test_narrative_to_markdown() -> None:
    n = Narrative(
        what_happened=["Shipped A"],
        where_stuck=["AC-2 stuck"],
        next_actions=["Fix AC-2"],
    )
    md = n.to_markdown()
    assert "## What happened" in md
    assert "## Where you're stuck" in md
    assert "## Next actions" in md
    assert "- Shipped A" in md


def test_narrative_to_markdown_empty() -> None:
    n = Narrative()
    assert n.to_markdown() == "(no narrative)"
