# `model_profiles.yaml` — schema reference

Path: `.samvil/model_profiles.yaml`. When absent,
`references/model_profiles.defaults.yaml` is used. When both are missing,
`mcp/samvil_mcp/routing.DEFAULT_PROFILES` is used.

## Top-level keys

```yaml
profiles: [ ... ]           # required; list of ModelProfile
role_overrides: { ... }     # optional; role → cost_tier map
```

## `profiles[]`

| Field | Type | Required | Notes |
|-------|------|:---:|-------|
| `provider` | string | yes | Free text. Convention: `anthropic`, `openai`, `google`, `openrouter`, `claude-code`, `codex-cli`. |
| `model_id` | string | yes | Provider-specific. Must be unique per `(provider, model_id)`. |
| `cost_tier` | enum | yes | `frugal`, `balanced`, `frontier`. No collision with `samvil_tier` values. |
| `nickname` | string | no | Short label surfaced in router reason strings and in `samvil status`. |
| `max_tokens_out` | int | no | Soft ceiling. Default 4096. Used by cost accounting, not enforced by router. |
| `notes` | string | no | Free text. |

**Validation rules** (enforced by `validate_profiles` MCP tool):

1. At least one profile per `cost_tier`. If any bucket is empty, routing
   can starve on that tier's requests.
2. `(provider, model_id)` must be unique.
3. `cost_tier` must be one of the three enum values — anything else is
   silently skipped when loading, which surfaces as "no profile for
   cost_tier=X" during validation.

## `role_overrides`

Map of `task_role` → `cost_tier`. Merged on top of
`DEFAULT_ROLE_TO_TIER` at load time.

```yaml
role_overrides:
  build-worker:   balanced
  qa-functional:  frontier
  ux-designer:    balanced
  scaffolder:     frugal
```

Unknown roles fall through to `balanced` at route time. An override with
an unknown `cost_tier` value is silently dropped and the default for
that role applies.

## How the router consumes this

1. Skill calls `route_task(task_role="...")` via the MCP tool.
2. The tool loads `.samvil/model_profiles.yaml` (or defaults), builds
   the role map, and returns a `RoutingDecision`:
   ```json
   {
     "task_role": "build-worker",
     "requested_cost_tier": "balanced",
     "chosen_cost_tier": "balanced",
     "provider": "anthropic",
     "model_id": "claude-sonnet-4-6",
     "nickname": "sonnet-4.6",
     "reason": "base=balanced (role=build-worker)",
     "escalation_depth": 0,
     "downgraded": false
   }
   ```
3. The skill records this as a `policy_adoption` claim (Sprint 3 wires
   this into build/QA skills).

## Diff with Ouroboros v0.29.x

SAMVIL v3.2 intentionally renames and simplifies:

- Ouroboros uses `Tier.STANDARD` (value=`standard`) for balanced; this
  collides with `samvil_tier.standard`. SAMVIL uses
  `CostTier.BALANCED` (value=`balanced`).
- Tie-breaking is deterministic (first-listed wins) in SAMVIL, random in
  Ouroboros. Reason: reproducibility matters more than load balancing
  for a 1-dev tool.
- Provider adapter classes are **not** ported. SAMVIL's "provider" is
  the Claude Code execution environment; skills translate
  `RoutingDecision` into the model call themselves.

See `references/glossary.md` and HANDOFF-v3.2-DECISIONS.md §3.④ for the
full decision record.
