---
name: samvil-council
description: "Multi-agent council debate. Spawns agents via CC Agent tool, synthesizes verdicts, writes binding decisions."
---

# SAMVIL Council — Multi-Perspective Seed Review

Spawn multiple agents to debate seed quality. Each agent brings a different perspective. Verdicts are synthesized and binding decisions recorded.

## Boot Sequence (INV-1)

1. Read `project.seed.json` → the spec being reviewed
2. Read `project.state.json` → confirm stage
3. Read `interview-summary.md` → interview context for agents
4. Read `references/council-protocol.md` → synthesis rules and format
5. Read `references/tier-definitions.md` → which agents to activate

## Step 1: Determine Active Agents

Read `seed.agent_tier` and apply the Gate A activation table:

```
minimal  → Skip council entirely. Return immediately.
standard → Round 2 only: product-owner, simplifier, scope-guard
thorough → Round 1: business-analyst | Round 2: + ceo-advisor
full     → Round 1: all 3 | Round 2: all 4
```

If `agent_tier` is `"minimal"`, print:

```
[SAMVIL] Council: skipped (minimal tier)
```

Then invoke `samvil:design` and return.

## Step 2: Round 1 — Research (if tier ≥ thorough)

Spawn research agents **in parallel** (single message, multiple Agent tool calls):

For each Round 1 agent, use the Agent tool:

```
Agent(
  description: "SAMVIL Council R1: <agent-name>",
  prompt: "You are <agent-name> for SAMVIL Council Gate A, Round 1 (Research).

Read your full persona and behavior rules:
<paste content of agents/<agent-name>.md here>

## Context

Project seed:
<paste project.seed.json content>

Interview summary:
<paste interview-summary.md content>

## Your Task

Analyze this product from your specific perspective. Follow your persona's Output Format exactly.
Keep your response under 500 words — focus on key findings only.",
  subagent_type: "general-purpose"
)
```

**Read each agent's .md file** before spawning to include in the prompt.

After all Round 1 agents return, collect their outputs as `round1_context`.

Print progress:

```
[SAMVIL] Council Round 1 (Research): 
  competitor-analyst: [1-line summary]
  business-analyst: [1-line summary]
  user-interviewer: [1-line summary]
```

## Step 3: Round 2 — Review (always, if council runs)

Spawn review agents **in parallel**:

```
Agent(
  description: "SAMVIL Council R2: <agent-name>",
  prompt: "You are <agent-name> for SAMVIL Council Gate A, Round 2 (Review).

Read your full persona and behavior rules:
<paste content of agents/<agent-name>.md here>

## Context

Project seed:
<paste project.seed.json content>

Interview summary:
<paste interview-summary.md content>

{If Round 1 ran:}
## Research Findings (from Round 1)
<paste round1_context>

## Your Task

Review this seed from your perspective. For each section, state:
- APPROVE / CHALLENGE / REJECT
- Severity: MINOR or BLOCKING (for CHALLENGE/REJECT)
- One-line reasoning

Follow your persona's Output Format exactly.
Keep your response under 500 words.",
  subagent_type: "general-purpose"
)
```

Print progress:

```
[SAMVIL] Council Round 2 (Review):
  product-owner: APPROVE (ACs testable)
  simplifier: CHALLENGE — Scope Score 6/10
  scope-guard: APPROVE
  ceo-advisor: Go
```

## Step 4: Synthesize Verdicts

Apply synthesis rules from `references/council-protocol.md`:

1. Count verdicts per section across all Round 2 agents
2. Determine overall: **PROCEED** / **PROCEED WITH CHANGES** / **HOLD**

Present the full synthesis to the user:

```
[SAMVIL] Council Gate A Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{Round 1 summary if run}

Round 2 Review:
  product-owner:  {verdict} — {reasoning}
  simplifier:     {verdict} — {reasoning}
  scope-guard:    {verdict} — {reasoning}
  ceo-advisor:    {verdict} — {reasoning}

Synthesis: {PROCEED / PROCEED WITH CHANGES / HOLD}

{If changes recommended:}
Recommended changes:
  1. {change}
  2. {change}
```

## Step 5: Handle Result

### If PROCEED
Continue directly.

### If PROCEED WITH CHANGES
Ask user: **"Council recommends these changes. Apply them? (yes / no / I'll edit manually)"**

- **yes**: Modify `project.seed.json` with recommended changes, re-save
- **no**: Continue with original seed
- **edit**: Wait for user to make changes, then re-read seed

### If HOLD
Present all findings. Wait for user direction.

## Step 6: Write decisions.log

For each CHALLENGE or REJECT verdict, append to `~/dev/<project>/decisions.log`:

```json
[
  {
    "id": "d001",
    "gate": "A",
    "round": 2,
    "agent": "simplifier",
    "decision": "Remove dashboard from P1",
    "reason": "Scope Score 6/10, dashboard is P2 value",
    "severity": "MINOR",
    "binding": true,
    "applied": true,
    "timestamp": "2026-04-04T..."
  }
]
```

If decisions.log already exists, read it first and append (don't overwrite).

## Step 7: Chain to Design (INV-4)

Update `project.state.json`: set `current_stage` to `"design"`.

```
[SAMVIL] Gate A complete. Proceeding to design...
```

Invoke the Skill tool with skill: `samvil:design`

## Rules

1. **Read agent .md files before spawning** — the agent's persona must be in its prompt
2. **All agents in a round spawn in ONE message** — parallel, not sequential
3. **500 word limit per agent** — prevent context bloat
4. **Respect tier boundaries** — never spawn agents the tier doesn't include
5. **decisions.log is append-only** — never delete previous decisions
6. **User checkpoint before applying changes** — never auto-modify seed without approval
