"""Council Gate A verdict synthesis (T4.3 ultra-thin migration).

The samvil-council skill is the only Phase B skill with **parallel agent
spawning** via the CC Agent tool. Agent spawn itself stays in the skill
body (host-bound), but the BEFORE (Round-1 → Round-2 debate-point
extraction) and AFTER (per-section verdict aggregation, Devil's Advocate
preservation, overall PROCEED/PROCEED_WITH_CHANGES/HOLD decision) logic
moves here as a pure function the skill can call once per round.

Distinct from `consensus_v3_2.py`:
  * `consensus_v3_2.py` is the v3.3-bound dispute resolver (Judge +
    Reviewer, triggered on QA mismatch / weak evidence / scope change /
    repeated failure / ambiguous intent / architecture tradeoff).
  * `council_synthesis.py` is the legacy v3.1 always-on Council Gate A
    that survives in v3.2 only behind the `--council` opt-in flag and
    is removed in v3.3. Mixing the two would fight the retirement plan.

INV-1 honored: this module never reads or writes files. The skill body
passes Round 1/Round 2 verdicts in, gets the synthesis dict back, and
is responsible for persisting `.samvil/council-results.md`,
`decisions.log`, and the claim ledger entry.

Synthesis follows `references/council-protocol.md`:
  * Per-section consensus_score = approve_count / total_reviewers
  * ≥ 80% → strong consensus, auto-proceed
  * 60-79% → moderate, proceed with noted concerns
  * < 60% → weak, present to user (HOLD or PROCEED_WITH_CHANGES)
  * Any BLOCKING severity → blocking_objections (must address)
  * Any minority verdict → preserved as Devil's Advocate
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

COUNCIL_SYNTHESIS_SCHEMA_VERSION = "1.0"

# Consensus thresholds (mirrors references/council-protocol.md).
STRONG_CONSENSUS_THRESHOLD = 0.80
MODERATE_CONSENSUS_THRESHOLD = 0.60

# Verdict normalization: agents may write APPROVE/CHALLENGE/REJECT or
# Go/No-Go/Hold or 동의/반대 — normalize to approve / challenge / reject.
_APPROVE_TOKENS = {"approve", "go", "동의", "찬성", "ok", "accept", "pass"}
_CHALLENGE_TOKENS = {"challenge", "concern", "warn", "보류", "유보"}
_REJECT_TOKENS = {"reject", "block", "blocking", "반대", "거부", "stop",
                  "halt", "fail", "no-go", "nogo", "no go"}


def _normalize_verdict(raw: str | None) -> str:
    """Normalize a raw agent verdict string to approve/challenge/reject.

    Match order is REJECT > CHALLENGE > APPROVE so that compound tokens
    like "No-Go" or "approve-but-blocking" are classified correctly.
    """
    if not raw:
        return "challenge"  # missing verdict → conservative
    token = str(raw).strip().lower()
    # Strip leading severity markers like "MINOR:" / "BLOCKING:" only when
    # the separator is followed by whitespace (avoids eating "No-Go" → "no").
    for sep in (": ", " — ", " - "):
        if sep in token:
            token = token.split(sep, 1)[0].strip()

    # Direct token match first.
    if token in _REJECT_TOKENS:
        return "reject"
    if token in _CHALLENGE_TOKENS:
        return "challenge"
    if token in _APPROVE_TOKENS:
        return "approve"

    # Substring fallback — same priority order so REJECT wins over a
    # spurious "go" inside "no-go".
    for tok in _REJECT_TOKENS:
        if tok in token:
            return "reject"
    for tok in _CHALLENGE_TOKENS:
        if tok in token:
            return "challenge"
    for tok in _APPROVE_TOKENS:
        if tok in token:
            return "approve"
    return "challenge"


def _normalize_severity(raw: str | None) -> str:
    """Normalize severity → minor / blocking. Default minor."""
    if not raw:
        return "minor"
    token = str(raw).strip().lower()
    if "block" in token:
        return "blocking"
    return "minor"


# ── Round 1 → debate point extraction ──────────────────────────


def extract_round1_debate_points(
    round1_verdicts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Pull consensus / debate / blind_spots from Round 1 research output.

    Each Round 1 verdict is shaped:
      {
        "agent": "<name>",
        "topics": [
          {
            "topic": "<short>",
            "stance": "<one-liner>",
            "is_blind_spot": bool   # optional, default False
          }
        ]
      }

    Output (used by Round 2 prompt assembly + state tracking):
      {
        "consensus":   [{topic, agents:[...], summary}],
        "debate":      [{topic, positions:[{agent, stance}], resolution_hint}],
        "blind_spots": [{topic, raised_by, why_important}]
      }
    """
    consensus: list[dict[str, Any]] = []
    debate: list[dict[str, Any]] = []
    blind_spots: list[dict[str, Any]] = []

    if not round1_verdicts:
        return {"consensus": consensus, "debate": debate,
                "blind_spots": blind_spots}

    # Build topic -> {agent, stance, is_blind_spot} index.
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for v in round1_verdicts:
        agent = v.get("agent") or "unknown"
        for t in (v.get("topics") or []):
            topic = (t.get("topic") or "").strip()
            if not topic:
                continue
            by_topic[topic].append({
                "agent": agent,
                "stance": (t.get("stance") or "").strip(),
                "is_blind_spot": bool(t.get("is_blind_spot")),
            })

    for topic, entries in by_topic.items():
        # Blind spot: only one agent raised it AND they marked it so.
        if len(entries) == 1 and entries[0]["is_blind_spot"]:
            blind_spots.append({
                "topic": topic,
                "raised_by": entries[0]["agent"],
                "why_important": entries[0]["stance"],
            })
            continue

        # Distinct stances → debate. Identical stances → consensus.
        stances = {e["stance"] for e in entries if e["stance"]}
        if len(stances) <= 1:
            consensus.append({
                "topic": topic,
                "agents": [e["agent"] for e in entries],
                "summary": next(iter(stances), ""),
            })
        else:
            debate.append({
                "topic": topic,
                "positions": [
                    {"agent": e["agent"], "stance": e["stance"]}
                    for e in entries
                ],
                "resolution_hint": "Round 2 should pick a side and justify.",
            })

    return {
        "consensus": consensus,
        "debate": debate,
        "blind_spots": blind_spots,
    }


def render_round2_debate_injection(debate_points: dict[str, Any]) -> str:
    """Render debate points as markdown for Round 2 agent prompts.

    Mirrors the legacy 'Round 1 Synthesis' block in SKILL.legacy.md so
    that Round 2 agents see the same structured debate they did before.
    """
    if not debate_points:
        return ""
    lines: list[str] = ["## Round 1 Synthesis"]
    consensus = debate_points.get("consensus") or []
    debate = debate_points.get("debate") or []
    blind_spots = debate_points.get("blind_spots") or []

    if consensus:
        lines.append("\n### Consensus (agents agree)")
        for c in consensus:
            agents = ", ".join(c.get("agents") or [])
            lines.append(f"- **{c.get('topic', '')}** — {c.get('summary', '')} "
                         f"_(agents: {agents})_")
    if debate:
        lines.append("\n### Debate Points (agents disagree)")
        for d in debate:
            positions = d.get("positions") or []
            stance_str = "; ".join(
                f"{p.get('agent', '?')}: {p.get('stance', '')}"
                for p in positions
            )
            lines.append(f"- **{d.get('topic', '')}** — {stance_str}")
    if blind_spots:
        lines.append("\n### Blind Spots (only one agent raised)")
        for b in blind_spots:
            lines.append(f"- **{b.get('topic', '')}** "
                         f"(raised by {b.get('raised_by', '?')}): "
                         f"{b.get('why_important', '')}")
    return "\n".join(lines) + "\n"


# ── Round 2 verdict synthesis ──────────────────────────────────


def _aggregate_section(
    section: str,
    section_verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate one section across all Round 2 reviewers."""
    total = len(section_verdicts)
    if total == 0:
        return {
            "section": section,
            "total_reviewers": 0,
            "approve_count": 0,
            "challenge_count": 0,
            "reject_count": 0,
            "consensus_score": 0.0,
            "majority_verdict": "challenge",
            "tier": "no-data",
            "blocking": False,
            "dissenting": [],
            "agent_lines": [],
        }

    counts: Counter[str] = Counter()
    blocking = False
    agent_lines: list[dict[str, Any]] = []
    for v in section_verdicts:
        verdict = _normalize_verdict(v.get("verdict"))
        severity = _normalize_severity(v.get("severity"))
        counts[verdict] += 1
        if severity == "blocking" and verdict in ("challenge", "reject"):
            blocking = True
        agent_lines.append({
            "agent": v.get("agent") or "unknown",
            "verdict": verdict,
            "severity": severity,
            "reasoning": (v.get("reasoning") or "").strip(),
        })

    approve = counts.get("approve", 0)
    challenge = counts.get("challenge", 0)
    reject = counts.get("reject", 0)
    score = approve / total

    # Majority verdict: highest count; ties → conservative (challenge > approve > reject).
    if approve > challenge and approve > reject:
        majority = "approve"
    elif reject > approve and reject > challenge:
        majority = "reject"
    else:
        majority = "challenge"

    # Strength tier.
    if score >= STRONG_CONSENSUS_THRESHOLD:
        tier = "strong"
    elif score >= MODERATE_CONSENSUS_THRESHOLD:
        tier = "moderate"
    else:
        tier = "weak"

    # Devil's Advocate: any agent whose verdict differs from majority.
    dissenting = [
        line for line in agent_lines
        if line["verdict"] != majority
    ]

    return {
        "section": section,
        "total_reviewers": total,
        "approve_count": approve,
        "challenge_count": challenge,
        "reject_count": reject,
        "consensus_score": round(score, 4),
        "majority_verdict": majority,
        "tier": tier,
        "blocking": blocking,
        "dissenting": dissenting,
        "agent_lines": agent_lines,
    }


def _decide_overall(
    sections: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Decide PROCEED / PROCEED_WITH_CHANGES / HOLD across sections."""
    if not sections:
        return "PROCEED", ["no sections to evaluate — defaulting to PROCEED"]

    reasons: list[str] = []
    has_blocking = any(s["blocking"] for s in sections)
    has_weak = any(s["tier"] == "weak" for s in sections)
    has_moderate = any(s["tier"] == "moderate" for s in sections)
    has_reject_majority = any(s["majority_verdict"] == "reject" for s in sections)

    if has_blocking:
        reasons.append("blocking objection on at least one section")
        return "HOLD", reasons
    if has_reject_majority:
        reasons.append("majority REJECT on at least one section")
        return "HOLD", reasons
    if has_weak:
        reasons.append("weak consensus (<60%) on at least one section — "
                       "user decision required")
        return "HOLD", reasons
    if has_moderate:
        reasons.append("moderate consensus (60-79%) on at least one section — "
                       "proceed with noted changes")
        return "PROCEED_WITH_CHANGES", reasons
    reasons.append("strong consensus (≥80%) on all sections")
    return "PROCEED", reasons


def synthesize_council_verdicts(
    round1_verdicts: list[dict[str, Any]] | None = None,
    round2_verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single-source-of-truth synthesis of Council Gate A verdicts.

    Args:
      round1_verdicts: list of `{agent, topics:[{topic, stance, is_blind_spot}]}`
        from research-phase agents. Optional (only ≥thorough tier runs Round 1).
      round2_verdicts: list of `{agent, sections:[{section, verdict, severity, reasoning}]}`
        from review-phase agents. Required for an actual synthesis; if
        absent the function still returns a well-formed empty result.

    Returns a dict shaped for direct use by the skill body:

    {
      "schema_version": "1.0",
      "round1_debate_points": {
        "consensus":   [...],
        "debate":      [...],
        "blind_spots": [...],
      },
      "round2_injection_md": "...",   # ready to paste into Round 2 prompts
      "sections": [
        {
          "section": "core_experience",
          "total_reviewers": 4,
          "approve_count": 3,
          "challenge_count": 1,
          "reject_count": 0,
          "consensus_score": 0.75,
          "majority_verdict": "approve",
          "tier": "moderate",
          "blocking": False,
          "dissenting": [{agent, verdict, severity, reasoning}],
          "agent_lines": [{agent, verdict, severity, reasoning}],
        }
      ],
      "blocking_objections": [
        {section, agent, severity, reasoning}
      ],
      "overall_verdict": "PROCEED" | "PROCEED_WITH_CHANGES" | "HOLD",
      "overall_reasons": [str],
      "agents_count": int,
    }

    Pure function — no I/O, no exceptions for missing fields. Idempotent:
    same input → same output (no clock fields, no random IDs).
    """
    debate_points = extract_round1_debate_points(round1_verdicts)
    injection_md = render_round2_debate_injection(debate_points)

    # Group Round 2 verdicts by section.
    section_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    agents_seen: set[str] = set()
    if round2_verdicts:
        for v in round2_verdicts:
            agent = v.get("agent") or "unknown"
            agents_seen.add(agent)
            for s in (v.get("sections") or []):
                section_name = (s.get("section") or "").strip()
                if not section_name:
                    continue
                section_index[section_name].append({
                    "agent": agent,
                    "verdict": s.get("verdict"),
                    "severity": s.get("severity"),
                    "reasoning": s.get("reasoning"),
                })

    # Stable section order — sorted alphabetically for idempotency.
    sections = [
        _aggregate_section(name, section_index[name])
        for name in sorted(section_index.keys())
    ]

    # Blocking objections: gather from every section.
    blocking_objections: list[dict[str, Any]] = []
    for s in sections:
        if not s["blocking"]:
            continue
        for line in s["agent_lines"]:
            if line["severity"] == "blocking" and line["verdict"] in ("challenge", "reject"):
                blocking_objections.append({
                    "section": s["section"],
                    "agent": line["agent"],
                    "verdict": line["verdict"],
                    "severity": line["severity"],
                    "reasoning": line["reasoning"],
                })

    overall, reasons = _decide_overall(sections)

    return {
        "schema_version": COUNCIL_SYNTHESIS_SCHEMA_VERSION,
        "round1_debate_points": debate_points,
        "round2_injection_md": injection_md,
        "sections": sections,
        "blocking_objections": blocking_objections,
        "overall_verdict": overall,
        "overall_reasons": reasons,
        "agents_count": len(agents_seen),
    }
