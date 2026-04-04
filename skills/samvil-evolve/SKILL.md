---
name: samvil-evolve
description: "Seed evolution loop. Wonder → Reflect → new seed version. Repeat until convergence or user stops."
---

# SAMVIL Evolve — Seed Evolution Loop

Improve the seed based on QA feedback. Spawn wonder + reflect agents, generate a better seed version, check convergence.

## When to Run

- After QA PASS with quality notes → user opts in to evolve
- After QA FAIL (Ralph exhausted) → evolve may fix the root cause
- User explicitly invokes `/samvil:evolve`

## Boot Sequence (INV-1)

1. Read `project.seed.json` → current seed
2. Read `project.state.json` → current stage, qa_history
3. Read `.samvil/qa-report.md` → QA results
4. Read `decisions.log` → binding decisions (if exists)

## Step 1: Gather Context

If MCP `get_evolve_context` tool is available:
```
get_evolve_context(session_id, qa_result JSON)
→ Returns: current seed, QA result, convergence trend, previous changes
```

If MCP not available, gather from files manually.

## Step 2: Wonder — "What did we miss?"

Spawn `wonder-analyst` agent:

```
Agent(
  description: "SAMVIL Evolve: wonder-analyst",
  prompt: "You are wonder-analyst.
<paste agents/wonder-analyst.md>

## Context
Current seed (v{N}): <seed JSON>
QA Report: <qa-report.md content>
{convergence info if available}

## Task
Analyze what was lacking. Find surprises and gaps.
Follow your Output Format. Under 400 words.",
  subagent_type: "general-purpose"
)
```

## Step 3: Reflect — "How to improve?"

Spawn `reflect-proposer` agent (sequentially, receives wonder output):

```
Agent(
  description: "SAMVIL Evolve: reflect-proposer",
  prompt: "You are reflect-proposer.
<paste agents/reflect-proposer.md>

## Context
Current seed (v{N}): <seed JSON>
Wonder Analysis: <wonder output>
{convergence info}

## Task
Propose concrete seed changes. Follow your Output Format. Under 400 words.",
  subagent_type: "general-purpose"
)
```

## Step 4: Generate New Seed

Apply reflect-proposer's recommendations to create seed v(N+1):

1. Read current seed
2. Apply proposed changes
3. Increment version: `version: N+1`
4. If MCP available: `validate_evolved_seed(original, evolved)` — check rules
5. If validation fails: fix issues, re-validate

## Step 5: User Checkpoint

Present the diff:

```
[SAMVIL] Seed Evolution: v{N} → v{N+1}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Wonder findings:
  1. [finding]
  2. [finding]

Proposed changes:
  1. [change]
  2. [change]

{If MCP: Convergence trend: [converging/diverging/stable]}

Apply this evolution? (yes / no / edit)
```

- **yes**: Save new seed, continue
- **no**: Keep current seed, stop evolving
- **edit**: User modifies, then save

## Step 6: Save and Check Convergence

1. Write updated `project.seed.json`
2. If MCP available:
   - `save_seed_version(session_id, version, seed_json, change_summary)`
   - `check_convergence(seed_history)` → converged?
3. If MCP not available: compare manually (same features? same ACs?)

### If Converged (similarity ≥ 0.95)

```
[SAMVIL] Seed converged at v{N+1}. No further evolution needed.
```
Stop evolving. Chain to rebuild if needed.

### If Not Converged and iterations < 30

```
[SAMVIL] Seed v{N+1} saved. Rebuilding changed features...
```
Rebuild only features that changed → re-QA → check results.
If QA passes: offer another evolve round.
If QA still fails: another wonder/reflect cycle.

### If Max Iterations (30) Reached

```
[SAMVIL] Max evolution iterations reached. Stopping.
  Current seed: v{N+1}
  Recommendation: Review the seed manually.
```

## Step 7: Chain

After evolve completes (converged, user stops, or max iterations):

Update `project.state.json`: set `current_stage` to `"retro"`.
Invoke the Skill tool with skill: `samvil:retro`

If user chose to rebuild with new seed:
Update `project.state.json`: set `current_stage` to `"scaffold"`.
Invoke the Skill tool with skill: `samvil:scaffold`

## Rules

1. **Wonder before Reflect** — always analyze before proposing
2. **Max 2 new features per evolution** — prevent scope explosion
3. **Preserve name, mode, core_experience** — evolve around the core, not through it
4. **User approves every evolution** — no auto-modification
5. **convergence ≥ 0.95 = stop** — diminishing returns beyond this
6. **Max 30 iterations** — hard cap to prevent infinite loops
