# `interview_level` — v3.2 reference

Sprint 4 ships all six interview techniques behind a single axis:
`interview_level`. The axis is **orthogonal to `samvil_tier`**. Per the
glossary, their value sets are intentionally non-overlapping.

## Levels

| Level | Techniques | Est. wall-time (initial estimate) |
|-------|-----------|:-:|
| `quick` | T1 — seed_readiness only | ~10 min |
| `normal` ⭐ default | T1 + T2 + T4 | ~25 min |
| `deep` | T1 + T2 + T3 + T4 | ~35 min |
| `max` | T1 + T2 + T3 + T4 + T5 | ~50 min |
| `auto` | T6 selects among quick–max automatically | varies |

## Techniques

### T1 — multi-dimensional seed_readiness

Weighted sum over 5 dims (weights are `(initial estimate)`):

```
seed_readiness =
    intent_clarity        × 0.25
  + constraint_clarity    × 0.20
  + ac_testability        × 0.25
  + lifecycle_coverage    × 0.20
  + decision_boundary     × 0.10
```

Per-dimension floors are `samvil_tier`-dependent. See
`mcp/samvil_mcp/interview_v3_2.READINESS_FLOORS`. Interview → Seed gate
(§3.⑥) reads the total score; the three escalation checks
(`ac_testability`, `lifecycle_coverage`, `decision_boundary_clarity`)
are the per-dim floors.

### T2 — Meta Self-Probe

Once per phase, the AI asks itself "what did I miss?" and emits JSON:

```
{ "blind_spots": [...], "followups": [...] }
```

Use the MCP tool `meta_probe_prompt` to build the prompt, run the LLM,
then pipe the raw response through `meta_probe_parse`.

### T3 — User confidence marking

After each answer, the user rates confidence 1–5. ≤2 triggers a
tacit-extraction follow-up: *"Give me a concrete recent example."*

### T4 — Scenario simulation

Walk features through a fixed 4-step timeline (first arrival, happy
path, edge case, returning user). Flag contradictions (independent
feature with dependencies, dangling `depends_on`, etc.). Pure-Python,
no LLM call.

### T5 — Adversarial interviewer

Send the summary to a **different-provider** model and ask for plausible
failure paths. Requires ④ (Sprint 2) to be ready. If the router has no
non-primary provider configured, `max` automatically downgrades to
`deep` with a warning.

### T6 — PAL adaptive

Given a one-line project prompt, pick a level heuristically:

| Prompt markers | Level |
|----------------|-------|
| `multi-tenant`, `real-time`, `payments`, `auth`, `compliance`, `billing`, `offline sync` | `deep` (`max` on thorough+) |
| `dashboard`, `admin`, `workflow`, `pipeline` | `normal` |
| Nothing matches | `quick` |

Overrides: `solution_type=automation` → `quick`; `solution_type=game` → `normal`.

## How to choose a level

| Your goal | Level |
|-----------|-------|
| Throw-away prototype, lunch-break scope | `quick` |
| Most solo-dev projects | `normal` (default) |
| Project you'll maintain for ≥3 months | `deep` |
| Paid work / compliance / multi-tenant | `max` |
| Let SAMVIL decide | `auto` |

Set it in one of three ways:
- CLI: `/samvil "my project" --interview-level=deep`
- `.samvil/config.yaml`:
  ```yaml
  interview_level: deep
  ```
- Inline in the first interview message (Sprint 4 `samvil-interview`
  skill will accept it).

## What runs when

- `quick`: T1 only. The interview returns a score and (if below tier
  floor) a list of dimensions to expand. No extra LLM calls.
- `normal`: T1 + T2 + T4. T2 runs once per phase; T4 runs once at
  the end.
- `deep`: adds T3 — every answer gets a confidence prompt.
- `max`: adds T5 — one adversarial pass after T4.
- `auto`: T6 runs first, then one of the four above.

Expected costs follow `samvil_tier` cost-band defaults; see
`references/model-routing-guide.md` for the budget model.
