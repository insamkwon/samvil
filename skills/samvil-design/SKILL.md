---
name: samvil-design
description: "Generate project.blueprint.json with architecture decisions. Gate B design council for thorough+ tiers."
---

# SAMVIL Design — Architecture & Blueprint Generation

Generate the technical blueprint that translates the seed spec into concrete architecture decisions. Optionally run a design council (Gate B) for quality review.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Design" task를 `in_progress`로 설정
1. Read `project.seed.json` → what we're building
2. Read `project.state.json` → confirm `current_stage` is `"design"`
3. Read `project.config.json` → `selected_tier`
4. Read `interview-summary.md` → user context
5. Read `decisions.log` → binding decisions from Gate A (if exists)
6. Read `references/seed-schema.md` → blueprint schema reference

## Step 1: Generate Blueprint

Adopt the `agents/tech-architect.md` persona. Read it for detailed behavior.

Create `project.blueprint.json` based on the seed:

```json
{
  "screens": ["PrimaryScreen", "SecondaryScreen"],
  "data_model": {
    "EntityName": {
      "id": "string",
      "field": "type",
      "createdAt": "string (ISO 8601)"
    }
  },
  "api_routes": [],
  "state_management": "zustand | useState | none",
  "auth_strategy": "none | supabase | custom",
  "key_libraries": ["zustand", "nanoid"],
  "component_structure": {
    "shared_ui": ["Button", "Card", "Input", "Modal"],
    "feature_components": {
      "feature-name": ["Component1", "Component2"]
    }
  },
  "routing": {
    "/": "HomePage or PrimaryScreen",
    "/feature": "FeaturePage"
  }
}
```

### Decision Rules

- **state_management**: `"useState"` if ≤ 2 entities with no cross-component sharing. `"zustand"` if persistence needed or 3+ entities. `"none"` if static content.
- **auth_strategy**: `"none"` unless seed explicitly requires auth. Respect Gate A decisions.
- **api_routes**: Empty array if seed uses localStorage. Populate if seed needs API.
- **key_libraries**: Only libraries the features actually need. Check seed.features for DnD, charts, dates, etc.
- **screens**: Derive from seed.core_experience.primary_screen + one per major feature that needs its own page.

## Step 2: Adopt UX Designer Perspective

Read `agents/ux-designer.md`. Define for each screen:

```
Screen: PrimaryScreen
  Purpose: [what user does here]
  Components: [list]
  States: Empty | Loading | Populated | Error
  Primary action: [main CTA]
```

Include this as a comment section in the blueprint or present to user.

## Step 3: Gate B — Design Council (if tier ≥ thorough)

Read `config.selected_tier`. If `thorough` or `full`:

Spawn design council agents **in parallel** via CC Agent tool:

| Tier | Agents |
|------|--------|
| thorough | ui-designer, ux-researcher, responsive-checker, accessibility-expert |
| full | + copywriter |

```
Agent(
  description: "SAMVIL Gate B: <agent-name>",
  model: config.model_routing.council || config.model_routing.default || "sonnet",
  prompt: "You are <agent-name> for SAMVIL Gate B (Design Review).

<paste agents/<agent-name>.md content>

## Context
Seed: <seed JSON>
Blueprint: <blueprint JSON>
Screen definitions: <screen definitions>

## Task
Review the design from your perspective. Follow your Output Format.
Keep response under 400 words.",
  subagent_type: "general-purpose"
)
```

### Gate B Synthesis

Same rules as Gate A (see `references/council-protocol.md`):
- Majority APPROVE → proceed
- CHALLENGE with changes → present to user
- REJECT → hold for user

Append design decisions to `decisions.log`.

If changes recommended and user approves, update blueprint.

## Step 4: User Checkpoint

Present the blueprint:

```
[SAMVIL] Blueprint Generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━

Screens: [list]
Data Model: [summary]
State: [strategy]
Libraries: [list]
Routes: [summary]

{Gate B results if run}

Blueprint looks good? Say 'go' to start building, or tell me what to change.
```

## Step 5: Save and Chain (INV-4)

1. Write `project.blueprint.json` to project directory
2. Update `project.state.json`: set `current_stage` to `"scaffold"`
3. Print progress:

```
[SAMVIL] Design ✓
[SAMVIL] Stage 3/5: Scaffolding project...
```

4. Invoke the Skill tool with skill: `samvil-scaffold`

## Rules

1. **Blueprint must be consistent with seed** — don't add screens for features not in seed
2. **Respect Gate A decisions** — read decisions.log, don't contradict binding decisions
3. **Be opinionated** — choose the simplest architecture that supports all seed features
4. **Gate B is optional** — only runs for thorough+ tiers
5. **One file output** — everything goes in project.blueprint.json

**TaskUpdate**: "Design" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-scaffold`

### Codex CLI (future)
Read `skills/samvil-scaffold/SKILL.md` and follow its instructions.
