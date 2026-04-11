---
name: samvil-council
description: "Multi-agent council debate. Spawns agents via CC Agent tool, synthesizes verdicts, writes binding decisions."
---

# SAMVIL Council — Multi-Perspective Seed Review

Spawn multiple agents to debate seed quality. Each agent brings a different perspective. Verdicts are synthesized and binding decisions recorded.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Council" task를 `in_progress`로 설정
1. Read `project.seed.json` → the spec being reviewed
2. Read `project.state.json` → confirm stage, get `session_id`
3. Read `project.config.json` → `selected_tier`
4. Read `interview-summary.md` → interview context for agents
5. Read `references/council-protocol.md` → synthesis rules and format
6. Read `references/tier-definitions.md` → which agents to activate

## Step 1: Determine Active Agents

Read `config.selected_tier` and apply the Gate A activation table:

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

Then invoke `samvil-design` and return.

## Step 2: Round 1 — Research (if tier ≥ thorough)

Spawn research agents **in controlled parallel batches**:

```
MAX_PARALLEL = config.max_parallel || 2
```

Split Round 1 agents into chunks of `MAX_PARALLEL`. Spawn each chunk in ONE message (parallel). Wait for all agents in a chunk to complete before spawning the next chunk.

For each Round 1 agent, use the Agent tool:

```
Agent(
  description: "SAMVIL Council R1: <agent-name>",
  model: config.model_routing.council_research || config.model_routing.default || "haiku",
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

### Round 1 Debate Point Extraction

Before spawning Round 2, synthesize Round 1 findings into **debate points**.

Extract three categories:

1. **Consensus** — Issues all agents agree on (no debate needed)
2. **Debate Points** — Agents disagree or raise conflicting concerns
3. **Blind Spots** — Important aspects no agent covered

Output both a **displayable markdown format** AND a **structured JSON** for downstream consumption:

**Markdown format** (for Round 2 prompt injection):
```
## Round 1 Synthesis

### Consensus (agents agree)
- <point 1>
- <point 2>

### Debate Points (agents disagree)
- <agent A> says X, but <agent B> says Y about <topic>
- <agent C> raised concern about Z, no other agent addressed it

### Blind Spots (nobody mentioned)
- <potential risk or opportunity not covered>
```

**JSON format** (for state tracking, stored as `round1_debate_points`):
```json
{
  "consensus": [
    {"topic": "...", "agents": ["agent-a", "agent-b", "agent-c"], "summary": "..."}
  ],
  "debate": [
    {"topic": "...", "positions": [{"agent": "agent-a", "stance": "..."}, {"agent": "agent-b", "stance": "..."}], "resolution_hint": "..."}
  ],
  "blind_spots": [
    {"topic": "...", "why_important": "..."}
  ]
}
```

This JSON is passed to Round 2 agents and used for Consensus Score calculation in Step 4.

Print progress:

```
[SAMVIL] Council Round 1 (Research): 
  competitor-analyst: [1-line summary]
  business-analyst: [1-line summary]
  user-interviewer: [1-line summary]
```

## Step 3: Round 2 — Review (always, if council runs)

Spawn review agents **in controlled parallel batches**:

```
MAX_PARALLEL = config.max_parallel || 2
```

Split Round 2 agents into chunks of `MAX_PARALLEL`. Spawn each chunk in ONE message (parallel). Wait for all agents in a chunk to complete before spawning the next chunk.

```
Agent(
  description: "SAMVIL Council R2: <agent-name>",
  model: config.model_routing.council || config.model_routing.default || "sonnet",
  prompt: "You are <agent-name> for SAMVIL Council Gate A, Round 2 (Review).

Read your full persona and behavior rules:
<paste content of agents/<agent-name>.md here>

## Context

Project seed:
<paste project.seed.json content>

Interview summary:
<paste interview-summary.md content>

{If Round 1 ran:}
## Round 1 Synthesis (Research → Debate Points)
<paste round1_synthesis markdown format>

### 다음 논쟁점에 대해 명확히 의견을 제시하세요:
{For each debate point:}
- **[논쟁 주제]**: <agent A>은(는) X, <agent B>은(는) Y — 어느 쪽에 동의하며, 그 이유는?
{For each blind spot:}
- **[블라인드 스팟]**: 어떤 에이전트도 언급하지 않았지만, 이 주제가 이 프로젝트에 미치는 영향을 평가하세요.

당신의 평가에서 위 논쟁점과 블라인드 스팟에 대한 입장을 반드시 포함하세요.

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
2. Calculate **Consensus Score** per section
3. Identify and preserve **Dissenting Opinions**
4. Determine overall: **PROCEED** / **PROCEED WITH CHANGES** / **HOLD**

### Consensus Score 산출

각 seed section별로 합의도를 계산:

```
For each section:
  total_agents = number of Round 2 agents that reviewed this section
  approve_count = number of APPROVE verdicts
  consensus_score = approve_count / total_agents

  consensus_score >= 3/5 (60%) → section 채택
  consensus_score < 3/5 (60%)  → section 재검토 (사용자에게 제시)
```

**Threshold**: 최소 60% (3/5, 2/3, 또는 그에 상응하는 비율)의 에이전트가 동의해야 해당 section의 결정이 채택됩니다. 에이전트 수가 3명 미만인 경우 과반수(>50%)를 적용.

Consensus Score는 Round 1 debate_points JSON의 consensus 필드와 Round 2의 verdict를 결합하여 계산.

### Devil's Advocate (반대 의견) 보존

합의에 도달한 section이라도, 반대 의견이 있으면 별도로 기록:

```
For each section:
  if any agent's verdict differs from majority:
    record as dissenting_opinion
```

Dissenting opinion 포맷:
```json
{
  "section": "<section_name>",
  "agent": "<agent_name>",
  "verdict": "CHALLENGE|REJECT",
  "reasoning": "<agent's one-line reasoning>",
  "note": "이 의견은 최종 결정에 반영되지 않았지만 기록으로 남깁니다."
}
```

### Synthesis Output

Present the synthesis in a **user-friendly format** — 각 에이전트의 핵심 의견을 한 줄로 요약:

```
[SAMVIL] Council 결과
━━━━━━━━━━━━━━━━━━━━

  PO:         '모든 AC가 testable하고 명확함'
  Simplifier: 'P1 기능 3개, scope score 8/10'
  Scope Guard:'의존성 정직함. drag-drop → board-view 순서 맞음'

  Consensus Score: 3/3 (100%)
  결정: PROCEED ✓
  변경: 없음
```

변경이 있는 경우:
```
[SAMVIL] Council 결과
━━━━━━━━━━━━━━━━━━━━

  PO:         'AC 4번이 모호함 — "잘 동작한다"는 testable 아님'
  Simplifier: 'dashboard는 P2로 강등 권장'
  Scope Guard:'auth 없이 dashboard 데이터는 어디서?'

  Consensus Score: 1/3 (33%) — 재검토 필요
  결정: PROCEED WITH CHANGES
  변경:
    1. AC 4번 → "Dashboard에 최근 7일 task 통계가 표시된다"
    2. dashboard → priority 2로 이동
```

반대 의견이 있는 경우 (결과 하단에 별도 섹션):
```
⚠️ 반대 의견 (Devil's Advocate)
  • Scope Guard가 제안: "auth 없이 dashboard는 P2에서 다시 논의"
    → 이 의견은 최종 결정에 반영되지 않았지만 기록으로 남깁니다.
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

## Step 6b: MCP Event (필수)

```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="council_verdict", stage="design", data='{"verdict":"<PROCEED|PROCEED_WITH_CHANGES|HOLD>","agents_count":<N>}')
```

## Step 7: Chain to Design (INV-4)

```
[SAMVIL] Gate A complete. Proceeding to design...
```

Invoke the Skill tool with skill: `samvil-design`

## Output Format

1. **Per-agent output**: Each spawned agent returns markdown with APPROVE/CHALLENGE/REJECT per section, under 500 words.
2. **Synthesis display**: Print council results in `[SAMVIL] Council 결과` block with per-agent 1-line summary, Consensus Score, and overall verdict.
3. **Dissenting opinions**: When any agent's verdict differs from majority, display as a separate `⚠️ 반대 의견 (Devil's Advocate)` section below the synthesis.
4. **decisions.log**: Append JSON array entries to `~/dev/<project>/decisions.log`:
   ```json
   { "id": "d001", "gate": "A", "round": 2, "agent": "<name>", "decision": "<text>", "reason": "<text>", "severity": "MINOR|BLOCKING", "binding": true, "applied": true, "timestamp": "<ISO 8601>" }
   ```
   Append only — never overwrite or delete existing entries.
5. **Round 1 debate points**: Stored as `round1_debate_points` JSON (consensus/debate/blind_spots) for Round 2 injection and Consensus Score calculation.

## Anti-Patterns

1. Do NOT auto-modify seed without user approval on PROCEED WITH CHANGES
2. Do NOT spawn agents outside the tier's activation table
3. Do NOT skip Round 1 synthesis before Round 2 (when Round 1 runs)
4. Do NOT discard dissenting opinions — always preserve as Devil's Advocate section
5. Do NOT proceed with Consensus Score below 60% without user approval

## Rules

1. **Read agent .md files before spawning** — the agent's persona must be in its prompt
2. **All agents in a chunk spawn in ONE message** — parallel within chunk, sequential between chunks. MAX_PARALLEL (default 2) controls chunk size.
3. **500 word limit per agent** — prevent context bloat
4. **Respect tier boundaries** — never spawn agents the tier doesn't include
5. **decisions.log is append-only** — never delete previous decisions
6. **User checkpoint before applying changes** — never auto-modify seed without approval
7. **Consensus Score ≥ 60% required** — below threshold, always present to user for decision
8. **Preserve all dissenting opinions** — record in Devil's Advocate section and decisions.log even when overruled

**TaskUpdate**: "Council" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-design`

### Codex CLI (future)
Read `skills/samvil-design/SKILL.md` and follow its instructions.
