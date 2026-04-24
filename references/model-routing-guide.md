# Model routing — non-developer guide (v3.2)

**What it is**: SAMVIL picks a different LLM for different jobs. Code
writing and verification may use different models. Routine tasks use
cheaper models; hard tasks use stronger ones.

**What it isn't**: an API key manager. SAMVIL does not make direct HTTP
calls to providers. Your Claude Code session executes the models; SAMVIL
just tells each skill which model to request.

## The cost_tier axis

Every task is labeled with one of three `cost_tier` values:

| cost_tier | Use for | Cost multiplier |
|-----------|---------|-----------------|
| `frugal`   | Routine checks, dependency audits, UI lint, researcher lookups. | 1× |
| `balanced` | Default for code writing, most reviews, most QA. | 10× |
| `frontier` | Tough judgements, complex planning, tricky bugs, final QA sign-off. | 30× |

`cost_tier` is **not** `samvil_tier`. `samvil_tier` controls *how rigorous
the pipeline is*; `cost_tier` controls *how expensive the model is*. See
`references/glossary.md`.

## Worked example — "build on Opus, QA on Codex"

This is the Sprint 2 exit-gate scenario.

1. In your project, copy the defaults:
   ```bash
   mkdir -p .samvil
   cp references/model_profiles.defaults.yaml .samvil/model_profiles.yaml
   ```
2. Edit `.samvil/model_profiles.yaml` so the first frontier profile is
   Opus for build and Codex for QA. Two simple strategies:

   **A — role_overrides**: assign roles to cost_tiers:
   ```yaml
   role_overrides:
     build-worker: frontier
     qa-functional: frontier
   ```
   The deterministic tie-break picks the first-listed profile in that
   tier. Put Opus before Codex to make build use Opus.

   **B — per-task profiles**: Sprint 3 will ship per-role filtering
   (role=generator prefers Opus, role=judge prefers Codex). Until then,
   skills can pass `requested_cost_tier="frontier"` and route against
   different profile orderings.

3. Verify:
   ```
   python3 scripts/view-routing.py --role build-worker
   python3 scripts/view-routing.py --role qa-functional
   ```
   (the view script ships in Sprint 2 final polish; see
   `mcp__samvil_mcp__route_task` tool in the meantime.)

## Escalation and downgrade

- **Escalation** happens automatically when a task fails. After one
  failure, the router bumps the cost_tier up one step on retry. After
  two failures, it bumps another step. Capped at `frontier`.
- **Downgrade** fires when the performance budget is ≥80% consumed. The
  router bumps the cost_tier down one step. Capped at `frugal`. If the
  same call is both escalating and in budget pressure, escalation wins.

Both are safeguards. Correctness trumps cost. The budget ceiling is
itself configurable; see `references/performance_budget.defaults.yaml`
(ships in Sprint 6).

## Monthly cost cap

The performance budget file sets a ceiling in `estimated_cost_usd` per
run. For a solo dev running 2–3 pipelines per day on `samvil_tier:
standard`, the rough cap is ~$60/month using the default profiles.
Override by editing `.samvil/performance_budget.yaml` once Sprint 6
ships, or (for now) by reducing `role_overrides` frontier assignments.

## What to do when you need a different provider

Add entries under `profiles:`. Example for an OpenRouter-hosted model:

```yaml
- provider: openrouter
  model_id: google/gemini-2.5-pro
  cost_tier: frontier
  nickname: gemini-pro
  max_tokens_out: 16000
  notes: Alt frontier with long context.
```

SAMVIL doesn't know how to talk to OpenRouter directly — your skill
execution environment does. The profile is a contract that says
"when the router picks this entry, use this model identifier".
