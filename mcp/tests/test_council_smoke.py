"""Smoke tests for samvil-council (T4.3 ultra-thin migration).

The samvil-council skill is the only Phase B skill with **parallel agent
spawning** via the CC Agent tool. Agent spawn (Round 1 research +
Round 2 review) stays in the skill body — it's host-bound and cannot
move to MCP. What CAN be machine-pinned, and is pinned here, is the
new `synthesize_council_verdicts` tool that the thin skill delegates to:

  1. Round 1 → debate point extraction (consensus / debate / blind_spots).
  2. Markdown injection block ready for Round 2 prompts.
  3. Round 2 per-section aggregation:
     - Consensus score = approve_count / total_reviewers.
     - Tier: ≥80% strong / 60-79% moderate / <60% weak.
     - Devil's Advocate dissent preservation.
     - BLOCKING-severity challenge → blocking_objections.
  4. Overall verdict: PROCEED / PROCEED_WITH_CHANGES / HOLD.
  5. Idempotency — same verdicts → same synthesis.

The 2-round parallel agent spawn flow itself, the CC Agent tool calls,
and the per-agent persona content are NOT unit-tested (they're host-
bound). The dispute resolver from `consensus_v3_2.py` is tested
separately in `test_stagnation_consensus.py`.
"""

from __future__ import annotations

import json

import pytest

from samvil_mcp import council_synthesis


# ── Round 1: debate-point extraction ───────────────────────────


def test_round1_empty_returns_well_formed() -> None:
    """No Round 1 verdicts → empty consensus / debate / blind_spots."""
    out = council_synthesis.extract_round1_debate_points(None)
    assert out == {"consensus": [], "debate": [], "blind_spots": []}
    out = council_synthesis.extract_round1_debate_points([])
    assert out == {"consensus": [], "debate": [], "blind_spots": []}


def test_round1_consensus_when_all_agents_agree() -> None:
    """All agents agree on a topic → consensus, not debate."""
    r1 = [
        {"agent": "competitor-analyst",
         "topics": [{"topic": "pricing", "stance": "freemium recommended"}]},
        {"agent": "business-analyst",
         "topics": [{"topic": "pricing", "stance": "freemium recommended"}]},
    ]
    out = council_synthesis.extract_round1_debate_points(r1)
    assert len(out["consensus"]) == 1
    assert out["consensus"][0]["topic"] == "pricing"
    assert set(out["consensus"][0]["agents"]) == {"competitor-analyst",
                                                   "business-analyst"}
    assert out["debate"] == []


def test_round1_debate_when_agents_disagree() -> None:
    """Distinct stances on the same topic → debate point with positions."""
    r1 = [
        {"agent": "competitor-analyst",
         "topics": [{"topic": "pricing", "stance": "freemium"}]},
        {"agent": "business-analyst",
         "topics": [{"topic": "pricing", "stance": "subscription only"}]},
    ]
    out = council_synthesis.extract_round1_debate_points(r1)
    assert len(out["debate"]) == 1
    assert out["debate"][0]["topic"] == "pricing"
    stances = {p["stance"] for p in out["debate"][0]["positions"]}
    assert stances == {"freemium", "subscription only"}


def test_round1_blind_spot_when_only_one_agent_flags() -> None:
    """Single agent + is_blind_spot=True → blind_spots, not consensus."""
    r1 = [
        {"agent": "user-interviewer",
         "topics": [
             {"topic": "accessibility", "stance": "no a11y plan",
              "is_blind_spot": True}
         ]},
    ]
    out = council_synthesis.extract_round1_debate_points(r1)
    assert len(out["blind_spots"]) == 1
    assert out["blind_spots"][0]["topic"] == "accessibility"
    assert out["blind_spots"][0]["raised_by"] == "user-interviewer"


def test_round2_injection_md_renders_all_sections() -> None:
    """Markdown injection block contains consensus + debate + blind_spots."""
    debate = {
        "consensus": [
            {"topic": "stack", "agents": ["a", "b"], "summary": "Next.js OK"}
        ],
        "debate": [
            {"topic": "auth",
             "positions": [{"agent": "a", "stance": "OAuth"},
                           {"agent": "b", "stance": "magic link"}],
             "resolution_hint": "..."}
        ],
        "blind_spots": [
            {"topic": "i18n", "raised_by": "c", "why_important": "key market"}
        ],
    }
    md = council_synthesis.render_round2_debate_injection(debate)
    assert "## Round 1 Synthesis" in md
    assert "Consensus (agents agree)" in md
    assert "Debate Points (agents disagree)" in md
    assert "Blind Spots" in md
    assert "Next.js OK" in md
    assert "OAuth" in md
    assert "i18n" in md


def test_round2_injection_md_empty_when_no_debate() -> None:
    """No debate points → still returns a header-free or near-empty string."""
    md = council_synthesis.render_round2_debate_injection(
        {"consensus": [], "debate": [], "blind_spots": []}
    )
    # Should at least contain the heading; no crash.
    assert "Round 1 Synthesis" in md


# ── Round 2: per-section aggregation ───────────────────────────


def test_synthesize_strong_consensus_proceed() -> None:
    """All agents APPROVE all sections → PROCEED + strong tier."""
    r2 = [
        {"agent": "product-owner",
         "sections": [
             {"section": "core_experience", "verdict": "approve"},
             {"section": "features", "verdict": "approve"},
         ]},
        {"agent": "simplifier",
         "sections": [
             {"section": "core_experience", "verdict": "approve"},
             {"section": "features", "verdict": "approve"},
         ]},
        {"agent": "scope-guard",
         "sections": [
             {"section": "core_experience", "verdict": "approve"},
             {"section": "features", "verdict": "approve"},
         ]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    assert out["overall_verdict"] == "PROCEED"
    assert out["agents_count"] == 3
    assert len(out["sections"]) == 2
    for s in out["sections"]:
        assert s["consensus_score"] == 1.0
        assert s["tier"] == "strong"
        assert s["majority_verdict"] == "approve"
        assert s["dissenting"] == []
    assert out["blocking_objections"] == []


def test_synthesize_moderate_consensus_proceed_with_changes() -> None:
    """2/3 APPROVE, 1 CHALLENGE (minor) → PROCEED_WITH_CHANGES."""
    r2 = [
        {"agent": "po",
         "sections": [{"section": "features", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "features", "verdict": "approve"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "features", "verdict": "challenge",
                       "severity": "minor",
                       "reasoning": "scope a bit wide"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["consensus_score"] == pytest.approx(2 / 3, rel=1e-3)
    assert sec["tier"] == "moderate"
    assert sec["majority_verdict"] == "approve"
    assert len(sec["dissenting"]) == 1
    assert sec["dissenting"][0]["agent"] == "scope-guard"
    assert sec["blocking"] is False
    assert out["overall_verdict"] == "PROCEED_WITH_CHANGES"
    assert out["blocking_objections"] == []


def test_synthesize_weak_consensus_hold() -> None:
    """1/3 APPROVE, 2 CHALLENGE → weak (33%) → HOLD."""
    r2 = [
        {"agent": "po",
         "sections": [{"section": "scope", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "scope", "verdict": "challenge",
                       "severity": "minor"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "scope", "verdict": "challenge",
                       "severity": "minor"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["consensus_score"] < council_synthesis.MODERATE_CONSENSUS_THRESHOLD
    assert sec["tier"] == "weak"
    assert out["overall_verdict"] == "HOLD"


def test_synthesize_blocking_severity_forces_hold() -> None:
    """Even with majority APPROVE, BLOCKING dissent → HOLD."""
    r2 = [
        {"agent": "po",
         "sections": [{"section": "tech_stack", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "tech_stack", "verdict": "approve"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "tech_stack", "verdict": "reject",
                       "severity": "blocking",
                       "reasoning": "missing data layer"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["blocking"] is True
    assert out["overall_verdict"] == "HOLD"
    assert len(out["blocking_objections"]) == 1
    assert out["blocking_objections"][0]["section"] == "tech_stack"
    assert out["blocking_objections"][0]["agent"] == "scope-guard"
    assert out["blocking_objections"][0]["severity"] == "blocking"


def test_synthesize_majority_reject_holds() -> None:
    """Majority REJECT (even minor) on any section → HOLD."""
    r2 = [
        {"agent": "po",
         "sections": [{"section": "features", "verdict": "reject",
                       "severity": "minor"}]},
        {"agent": "simplifier",
         "sections": [{"section": "features", "verdict": "reject",
                       "severity": "minor"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "features", "verdict": "approve"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["majority_verdict"] == "reject"
    assert out["overall_verdict"] == "HOLD"


def test_synthesize_dissent_preserved_for_majority_approve() -> None:
    """Devil's Advocate: minority verdict on majority-APPROVE section is kept."""
    r2 = [
        {"agent": "po",
         "sections": [{"section": "ac", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "ac", "verdict": "approve"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "ac", "verdict": "challenge",
                       "severity": "minor",
                       "reasoning": "AC4 not testable"}]},
        {"agent": "ceo-advisor",
         "sections": [{"section": "ac", "verdict": "approve"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["majority_verdict"] == "approve"
    assert sec["consensus_score"] == 0.75
    assert len(sec["dissenting"]) == 1
    assert sec["dissenting"][0]["agent"] == "scope-guard"
    assert sec["dissenting"][0]["reasoning"] == "AC4 not testable"


def test_synthesize_normalizes_alternative_verdict_tokens() -> None:
    """Go / 동의 / OK normalize to approve; No-Go / 반대 to reject."""
    r2 = [
        {"agent": "ceo-advisor",
         "sections": [{"section": "go_no_go", "verdict": "Go"}]},
        {"agent": "simplifier",
         "sections": [{"section": "go_no_go", "verdict": "동의"}]},
        {"agent": "scope-guard",
         "sections": [{"section": "go_no_go", "verdict": "No-Go"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    sec = out["sections"][0]
    assert sec["approve_count"] == 2
    assert sec["challenge_count"] == 0  # No-Go → reject (not challenge)
    assert sec["reject_count"] == 1


def test_synthesize_combines_round1_and_round2() -> None:
    """End-to-end: Round 1 debate points + Round 2 verdicts both populated."""
    r1 = [
        {"agent": "competitor-analyst",
         "topics": [{"topic": "stack", "stance": "Next.js"}]},
        {"agent": "business-analyst",
         "topics": [{"topic": "stack", "stance": "Astro"}]},  # debate!
    ]
    r2 = [
        {"agent": "po",
         "sections": [{"section": "tech_stack", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "tech_stack", "verdict": "approve"}]},
    ]
    out = council_synthesis.synthesize_council_verdicts(
        round1_verdicts=r1, round2_verdicts=r2
    )
    assert len(out["round1_debate_points"]["debate"]) == 1
    assert "stack" in out["round2_injection_md"]
    assert "Next.js" in out["round2_injection_md"]
    assert out["overall_verdict"] == "PROCEED"


def test_synthesize_idempotent() -> None:
    """Same input → identical output across two calls."""
    r1 = [
        {"agent": "a", "topics": [{"topic": "x", "stance": "alpha"}]},
        {"agent": "b", "topics": [{"topic": "x", "stance": "beta"}]},
    ]
    r2 = [
        {"agent": "po",
         "sections": [{"section": "f", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "f", "verdict": "challenge",
                       "severity": "minor"}]},
    ]
    a = council_synthesis.synthesize_council_verdicts(
        round1_verdicts=r1, round2_verdicts=r2
    )
    b = council_synthesis.synthesize_council_verdicts(
        round1_verdicts=r1, round2_verdicts=r2
    )
    assert a == b


def test_synthesize_empty_round2_returns_well_formed() -> None:
    """No Round 2 verdicts → empty sections, default PROCEED."""
    out = council_synthesis.synthesize_council_verdicts()
    assert out["sections"] == []
    assert out["blocking_objections"] == []
    assert out["agents_count"] == 0
    # Default: nothing to evaluate → PROCEED with explanation.
    assert out["overall_verdict"] == "PROCEED"
    assert out["schema_version"] == "1.0"


def test_synthesize_sections_sorted_alphabetically() -> None:
    """Section order is alphabetical → idempotent independent of input order."""
    r2_a = [
        {"agent": "po", "sections": [
            {"section": "zebra", "verdict": "approve"},
            {"section": "apple", "verdict": "approve"},
        ]},
    ]
    r2_b = [
        {"agent": "po", "sections": [
            {"section": "apple", "verdict": "approve"},
            {"section": "zebra", "verdict": "approve"},
        ]},
    ]
    a = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2_a)
    b = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2_b)
    assert a == b
    assert [s["section"] for s in a["sections"]] == ["apple", "zebra"]


def test_synthesize_missing_severity_defaults_to_minor() -> None:
    """Severity omitted → minor; doesn't accidentally trigger blocking."""
    r2 = [
        {"agent": "po", "sections": [
            {"section": "f", "verdict": "challenge"}  # no severity field
        ]},
        {"agent": "simplifier", "sections": [
            {"section": "f", "verdict": "approve"}
        ]},
    ]
    out = council_synthesis.synthesize_council_verdicts(round2_verdicts=r2)
    assert out["sections"][0]["blocking"] is False


# ── MCP tool wrapper integration ───────────────────────────────


@pytest.mark.asyncio
async def test_mcp_tool_returns_valid_json() -> None:
    """The @mcp.tool() wrapper returns parseable JSON."""
    from samvil_mcp.server import synthesize_council_verdicts as mcp_tool

    r2 = [
        {"agent": "po",
         "sections": [{"section": "core", "verdict": "approve"}]},
        {"agent": "simplifier",
         "sections": [{"section": "core", "verdict": "approve"}]},
    ]
    raw = await mcp_tool(
        round1_verdicts_json="",
        round2_verdicts_json=json.dumps(r2),
    )
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "1.0"
    assert parsed["overall_verdict"] == "PROCEED"
    assert parsed["agents_count"] == 2


@pytest.mark.asyncio
async def test_mcp_tool_handles_empty_inputs() -> None:
    """Both args empty → wrapper returns well-formed empty synthesis."""
    from samvil_mcp.server import synthesize_council_verdicts as mcp_tool

    raw = await mcp_tool()
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["sections"] == []


@pytest.mark.asyncio
async def test_mcp_tool_handles_invalid_json() -> None:
    """Malformed JSON in args → returns {error: ...} envelope, no crash."""
    from samvil_mcp.server import synthesize_council_verdicts as mcp_tool

    raw = await mcp_tool(
        round1_verdicts_json="{not valid",
        round2_verdicts_json="",
    )
    parsed = json.loads(raw)
    assert "error" in parsed


@pytest.mark.asyncio
async def test_mcp_tool_ignores_non_list_inputs() -> None:
    """Inputs that parse but aren't lists are silently ignored."""
    from samvil_mcp.server import synthesize_council_verdicts as mcp_tool

    raw = await mcp_tool(
        round1_verdicts_json='{"not": "a list"}',
        round2_verdicts_json='[]',
    )
    parsed = json.loads(raw)
    # Treats non-list as None → no crash, empty synthesis.
    assert parsed["round1_debate_points"]["consensus"] == []
