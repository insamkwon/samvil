---
name: samvil-design
description: "MCP-driven design stage: turn project.seed.json into project.blueprint.json and chain portably."
---

# SAMVIL Design - Thin Orchestrated Entry

This is the v3.4 Phase 2 ultra-thin migration. Full blueprint rules are
preserved in `skills/samvil-design/SKILL.legacy.md`; use it for schema
mapping, design-council behavior, feasibility review, and output formats.

## Inputs

1. Read `project.state.json` for `session_id`, `current_stage`, and host name
   (`host`, `runtime`, or `agent_host`; default `generic`).
2. Read `project.config.json` for `selected_tier` / `samvil_tier`.
3. Read `project.seed.json`; it is the design authority.
4. Read `interview-summary.md` and `.samvil/decisions/*.md` if present.
5. Read `.samvil/manifest.json` if present; if absent, build or refresh it.
6. Read `skills/samvil-design/SKILL.legacy.md` for blueprint construction.

## MCP Gate

Call:

```
mcp__samvil_mcp__get_orchestration_state(session_id="<session_id>")
mcp__samvil_mcp__stage_can_proceed(session_id="<session_id>", target_stage="design")
mcp__samvil_mcp__resolve_host_capability(host_name="<host>")
mcp__samvil_mcp__host_chain_strategy(host_name="<host>")
```

If `stage_can_proceed.can_proceed` is false, show blockers and stop.

Best-effort entry event:

```
mcp__samvil_mcp__save_event(
  session_id="<session_id>",
  event_type="design_started",
  stage="design",
  data="{}"
)
```

## Context Refresh

Prefer the manifest over ad-hoc repo scanning:

```
mcp__samvil_mcp__read_manifest(project_root="<project_root>")
mcp__samvil_mcp__render_manifest_context(project_root="<project_root>", focus=null, max_modules=30)
```

If missing:

```
mcp__samvil_mcp__build_and_persist_manifest(project_root="<project_root>", project_name="<project_name>")
```

Use `list_decision_adrs(project_root="<project_root>", status="accepted")` to
load binding council decisions when available. If any MCP call fails, continue
from files and mention degraded orchestration.

## Build Blueprint

Using `SKILL.legacy.md`, create a valid `project.blueprint.json` for the seed's
`solution_type`. Preserve the legacy design rules:

- simplest architecture that satisfies the seed
- no screens/features outside the seed
- accepted ADRs override preferences
- Gate B only for thorough/full tiers
- feasibility review before user checkpoint
- mobile considerations for form-heavy or mobile-first apps

Present the blueprint summary and ask for approval. If edits are requested,
revise and re-present.

## After Approval

1. Write approved JSON to `project.blueprint.json`.
2. Call:

```
mcp__samvil_mcp__complete_stage(
  session_id="<session_id>",
  stage="design",
  verdict="pass"
)
```

3. Append a short `.samvil/handoff.md` entry; never overwrite.

## Chain

Use `host_chain_strategy.chain_via`:

- `skill_tool`: invoke `samvil-scaffold`.
- `file_marker`: write `.samvil/next-skill.json`:

```json
{
  "next_skill": "samvil-scaffold",
  "reason": "design completed",
  "from_stage": "design"
}
```

If MCP is unavailable, fall back to the legacy chaining rules in
`SKILL.legacy.md` and mention that orchestration was degraded.

## Invariants

- `project.seed.json` is the design authority.
- Main session is the only writer of `project.blueprint.json`.
- MCP orchestration is preferred; files remain recovery source.
- Runtime-specific chaining must go through host capability.
