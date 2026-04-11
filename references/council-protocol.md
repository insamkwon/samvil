# Council Protocol

> Multi-agent debate for seed quality validation.
> Agents are spawned via CC Agent tool, debate in parallel, verdicts synthesized.

## 2-Round Structure

Gate A uses 2 rounds to separate information gathering from evaluation.

### Round 1: RESEARCH (parallel spawn)

Gather external context. Each agent works independently.

| Agent | Task | Output |
|-------|------|--------|
| `competitor-analyst` | Web search for competing products | Competitive landscape, gaps, differentiation angle |
| `business-analyst` | Market sizing, unit economics | TAM/SAM/SOM, revenue model, competitive table |
| `user-interviewer` | Simulate target user experience | User journey, friction points, missing expectations |

**Round 1 results** are appended to the seed context for Round 2.

### Round 2: REVIEW (parallel spawn)

Evaluate the seed with enriched context.

| Agent | Focus | Verdict Format |
|-------|-------|---------------|
| `product-owner` | AC verifiability, story completeness | APPROVE / CHALLENGE / REJECT per section |
| `simplifier` | Scope minimality, feature count | Scope Score 1-10 + cut list |
| `scope-guard` | Dependency honesty, scope boundaries | Dependency graph + drift risk |
| `ceo-advisor` | Go/No-Go strategic decision | Go/No-Go + positioning + 1 strategic risk |

### Tier → Round Activation

| Tier | Round 1 | Round 2 |
|------|---------|---------|
| minimal | — | — (no council) |
| standard | — | PO + simplifier + scope-guard |
| thorough | business-analyst only | PO + simplifier + scope-guard + ceo-advisor |
| full | All 3 | All 4 |

## How to Spawn Agents

Use the CC Agent tool. Spawn all agents in a round **in a single message** (parallel):

```
Agent(
  prompt: "{Read the full content of agents/<name>.md for your persona.}

  You are reviewing this seed specification:
  {seed JSON}

  Interview context:
  {interview-summary.md content}

  {Round 1 results, if Round 2}

  Review from your perspective. Follow the Output Format in your persona file exactly.",
  subagent_type: "general-purpose"
)
```

**Important:**
- Each agent receives its full persona from `agents/<name>.md`
- Each agent receives the seed JSON
- Round 2 agents also receive Round 1 results (if available)
- All agents in a round are spawned in ONE message (parallel execution)

## Verdict Synthesis

After all agents return:

### Consensus Score Calculation

For each seed section (features, ACs, constraints, etc.), calculate a Consensus Score:

```
consensus_score = approve_count / total_reviewing_agents

Threshold: ≥ 60% (3/5, 2/3, or equivalent) to auto-adopt a section decision.
If fewer than 3 agents: majority (>50%) applies.
```

Score interpretation:
- **≥ 80%**: Strong consensus — auto-proceed
- **60-79%**: Moderate consensus — proceed with noted concerns
- **< 60%**: Weak/no consensus — present to user for decision

### Per-Section Counting

For each seed section (features, ACs, constraints, etc.):

```
Consensus Score ≥ 80% (e.g., 3/3 APPROVE) → auto-proceed
Consensus Score 60-79% (e.g., 2/3 APPROVE + 1 MINOR CHALLENGE) → note the challenge, proceed
Consensus Score < 60% (e.g., 2/3 CHALLENGE or any REJECT) → present to user with recommendations
Any BLOCKING severity → must address before proceeding
```

### Devil's Advocate Preservation

For every section, identify agents whose verdict differs from the majority:

```
For each section:
  majority_verdict = verdict with highest count
  for each agent with verdict != majority_verdict:
    record as dissenting_opinion
```

Dissenting opinions are:
1. Displayed in a separate `⚠️ 반대 의견 (Devil's Advocate)` section in synthesis output
2. Recorded in decisions.log with `binding: false` and `dissenting: true` fields
3. Prefixed with: "이 의견은 최종 결정에 반영되지 않았지만 기록으로 남깁니다."

This ensures minority perspectives are never lost and can be revisited in later stages (Evolve, Retro).

### Synthesis Output Format

```
[SAMVIL] Council Gate A Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Round 1 Research (if run):
  competitor-analyst: 3 competitors found, gap in [area]
  business-analyst: TAM $Xm, recommended [model] pricing
  user-interviewer: friction at [point], missing [expectation]

Round 2 Review:
  product-owner:  APPROVE (ACs testable, stories complete)
  simplifier:     CHALLENGE — Scope Score 6/10, suggest removing [feature]
  scope-guard:    APPROVE (dependencies correct)
  ceo-advisor:    Go — strategic risk: [risk]

Consensus Score: [score] ([approve_count]/[total_agents])

Synthesis: PROCEED / PROCEED WITH CHANGES / HOLD FOR USER
Changes recommended:
  1. [specific change from simplifier]
  2. [specific change from other agents]

⚠️ 반대 의견 (Devil's Advocate):
  • [agent]: [dissenting opinion]
    → 이 의견은 최종 결정에 반영되지 않았지만 기록으로 남깁니다.
```

### User Interaction

- **PROCEED**: Auto-continue to scaffold
- **PROCEED WITH CHANGES**: Present changes, ask user "Apply these? (y/n/edit)"
  - If yes: modify seed, re-save, continue
  - If no: continue with original seed
  - If edit: user makes manual changes
- **HOLD**: Present all findings, wait for user direction

## decisions.log Format

Every council decision is appended to `~/dev/<project>/decisions.log`:

```json
{
  "id": "d001",
  "gate": "A",
  "round": 2,
  "agent": "simplifier",
  "decision": "Remove dashboard from P1 features",
  "reason": "Scope Score 6/10 — 4 P1 features too many for v1, dashboard is P2 value",
  "severity": "MINOR",
  "binding": true,
  "applied": true,
  "dissenting": false,
  "consensus_score": 0.67,
  "timestamp": "2026-04-04T18:30:00+09:00"
}
```

For dissenting opinions (agents who disagreed with the majority):

```json
{
  "id": "d002",
  "gate": "A",
  "round": 2,
  "agent": "scope-guard",
  "decision": "Auth should be P1, not P2",
  "reason": "Dashboard data without auth is meaningless in production",
  "severity": "MINOR",
  "binding": false,
  "applied": false,
  "dissenting": true,
  "consensus_score": 0.33,
  "timestamp": "2026-04-04T18:30:00+09:00"
}
```

**Rules:**
- Decisions with `binding: true` are enforced in all subsequent stages
- Decisions with `dissenting: true` are preserved for reference but not enforced
- Build skill reads decisions.log and respects `binding: true` decisions
- To overturn a binding decision: user must explicitly request, or Council reconvenes
- `applied: false` means the user chose not to apply the recommendation

## Anti-Patterns

- **Don't rubber-stamp** — Floor Rules ensure each agent finds issues
- **Don't let one agent dominate** — synthesis uses majority, not loudest voice
- **Don't re-run council on minor edits** — only on seed version changes
- **Don't spawn agents the tier doesn't include** — respect tier boundaries
- **Don't discard minority opinions** — always preserve dissenting views as Devil's Advocate
- **Don't proceed below 60% consensus without user approval** — weak consensus requires user decision
