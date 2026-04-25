---
name: samvil-seed
description: "MCP-driven seed stage: crystallize interview-summary.md into project.seed.json and chain portably."
---

# SAMVIL Seed - Thin Orchestrated Entry

This is the v3.3 ultra-thin PoC. Full rules are preserved in
`skills/samvil-seed/SKILL.legacy.md`; use it for schema mapping, validation,
presentation, and defaults.

## Inputs

1. Read `project.state.json` for `session_id`, `current_stage`, and host name
   (`host`, `runtime`, or `agent_host`; default `generic`).
2. Read `project.config.json` for `selected_tier` / `samvil_tier`.
3. Read `interview-summary.md` from disk, not from conversation.
4. Read `skills/samvil-seed/SKILL.legacy.md` for seed construction rules.

## MCP Gate

Call:

```
mcp__samvil_mcp__get_orchestration_state(session_id="<session_id>")
mcp__samvil_mcp__stage_can_proceed(session_id="<session_id>", target_stage="seed")
mcp__samvil_mcp__resolve_host_capability(host_name="<host>")
mcp__samvil_mcp__host_chain_strategy(host_name="<host>")
```

If `stage_can_proceed.can_proceed` is false, show blockers and stop.

## Build Seed

Using `SKILL.legacy.md`: convert `interview-summary.md` into valid v3
`project.seed.json`, validate, present the legacy summary, and ask approval.
If edits are requested, revise and re-present.

## After Approval

1. Write approved JSON to `project.seed.json`.
2. Call:

```
mcp__samvil_mcp__save_seed_version(
  session_id="<session_id>",
  version=1,
  seed_json="<escaped approved seed JSON>",
  change_summary="Initial seed from interview"
)

mcp__samvil_mcp__complete_stage(
  session_id="<session_id>",
  stage="seed",
  verdict="pass"
)
```

3. Append a short `.samvil/handoff.md` entry; never overwrite.

## Chain

Use `host_chain_strategy.chain_via`:

- `skill_tool`: invoke `samvil-council` for standard/thorough/full, or
  `samvil-design` for minimal.
- `file_marker`: write `.samvil/next-skill.json`:

```json
{
  "schema_version": "1.0",
  "chain_via": "file_marker",
  "host": "<host>",
  "next_skill": "samvil-design",
  "reason": "minimal tier skips council",
  "from_stage": "seed",
  "created_by": "samvil-seed"
}
```

For standard/thorough/full, use `samvil-council`.

If MCP is unavailable, fall back to the legacy chaining rules in
`SKILL.legacy.md` and mention that orchestration was degraded.

## Invariants

- Read interview output from files, not chat memory.
- Seed is immutable after approval.
- MCP orchestration is preferred; files remain recovery source.
- Runtime-specific chaining must go through host capability.
