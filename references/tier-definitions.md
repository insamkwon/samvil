# Agent Tier Definitions

> Controls how many agents activate per SAMVIL run.
> All 31 agents are always **defined** in `agents/`. Tier controls which are **activated**.

## Tiers

| Tier | Count | Extra Tokens | Extra Time | Best For |
|------|-------|-------------|-----------|----------|
| `minimal` | 10 | 0 (adopted only) | 0 | Quick prototypes, landing pages |
| **`standard`** | 20 | ~50K | +2min | **Most projects (default)** |
| `thorough` | 30 | ~120K | +5min | Quality-critical projects |
| `full` | 36 | ~200K | +8min | Large projects, team-shared products |
| `custom` | varies | varies | varies | User-defined via `agent_overrides` |

## Tier Composition

```
minimal (10):
  Phase A: socratic-interviewer, seed-architect              [2]
  Phase B: ux-designer                                      [1]
  Phase C: tech-architect, scaffolder, orchestrator-agent    [3]
  Phase D: qa-mechanical, qa-functional, qa-quality          [3]
  Phase F: retro-analyst                                     [1]

standard (20) = minimal + :
  Phase A: + product-owner, simplifier, scope-guard          [+3 Gate A Council]
  Phase C: + frontend-dev, backend-dev, infra-dev            [+3 Workers]
  Phase D: + tech-lead, dog-fooder                           [+2 Extended QA]
  Phase E: + wonder-analyst, reflect-proposer                [+2 Evolve]

thorough (30) = standard + :
  Phase A: + ceo-advisor, business-analyst                   [+2 Gate A extended]
  Phase B: + ui-designer, ux-researcher,                     [+4 Gate B Council]
           + responsive-checker, accessibility-expert
  Phase C: + ui-builder, dependency-auditor                  [+2 Build extended]
  Phase D: + performance-auditor, security-auditor           [+2 QA extended]

full (36) = thorough + :
  Phase A: + user-interviewer, competitor-analyst             [+2 Gate A full]
  Phase B: + copywriter                                      [+1 Gate B full]
  Phase C: + test-writer, error-handler                      [+2 Build full]
  Phase E: + growth-advisor                                  [+1 Evolve full]
```

## Selection Logic

```python
def get_active_agents(tier: str, overrides: dict) -> list:
    agents = TIER_MAP[tier].copy()
    agents += overrides.get("add", [])
    for removed in overrides.get("remove", []):
        agents.discard(removed)
    return sorted(agents)
```

## Seed Configuration

```json
{
  "agent_tier": "standard",
  "agent_overrides": {
    "add": ["security-auditor"],
    "remove": ["business-analyst"]
  }
}
```

## Gate A: 2-Round Structure (M3+)

Planning Council uses 2 rounds to separate information gathering from evaluation:

```
Round 1: RESEARCH (parallel spawn, results fed to Round 2)
  competitor-analyst — market landscape
  business-analyst   — numbers and unit economics
  user-interviewer   — simulated user perspective

Round 2: REVIEW (parallel spawn, seed quality validation)
  product-owner  — AC verifiability, story completeness
  simplifier     — scope minimality
  scope-guard    — dependency honesty
  ceo-advisor    — Go/No-Go strategic decision
```

**Tier → Round activation:**

| Tier | Round 1 | Round 2 |
|------|---------|---------|
| minimal | — | — |
| standard | — | PO + simplifier + scope-guard |
| thorough | business-analyst only | PO + simplifier + scope-guard + ceo-advisor |
| full | All 3 | All 4 |

## Agent File Format

Each agent `.md` in `agents/` has:

```yaml
---
name: agent-id             # kebab-case, matches filename
description: "one-line"    # what this agent does
phase: A|B|C|D|E|F        # pipeline phase
tier: minimal|standard|thorough|full  # lowest tier that includes this agent
mode: adopted|worker|council|evaluator
tools: []                  # (optional) allowed tools for worker/evaluator
---
```

## Mode Descriptions

| Mode | Behavior | Token Cost | When Used |
|------|----------|-----------|-----------|
| **adopted** | Claude assumes the role directly, no spawn | 0 extra | v1 (all agents) |
| **worker** | CC Agent tool spawn, parallel capable | ~15K each | M4+ (parallel builds) |
| **council** | CC Agent tool spawn, 3-4 debate | ~10K each | M3+ (Gate A/B) |
| **evaluator** | CC Agent tool spawn, structured verdict | ~10K each | M3+ (QA extended) |
