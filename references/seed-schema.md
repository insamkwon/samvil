# Seed Schema Reference

## project.seed.json

```json
{
  "name": "string — kebab-case, valid npm package name",
  "description": "string — one-line project description",
  "mode": "web",
  "tech_stack": {
    "framework": "next-14",
    "ui": "tailwind",
    "state": "zustand | useState | none",
    "router": "app-router"
  },
  "core_experience": {
    "description": "string — what user does in first 30 seconds",
    "primary_screen": "string — PascalCase component name",
    "key_interactions": ["string array — verb-noun format"]
  },
  "features": [
    {
      "name": "string — kebab-case",
      "priority": 1,
      "independent": true,
      "depends_on": null
    }
  ],
  "acceptance_criteria": ["string array — testable statements"],
  "constraints": ["string array"],
  "out_of_scope": ["string array"],
  "agent_tier": "minimal | standard | thorough | full",
  "agent_overrides": {
    "add": [],
    "remove": []
  },
  "version": 1
}
```

## Validation Rules

1. `name` must be valid npm package name (lowercase, hyphens, no spaces)
2. `features` must have at least 1 item with `priority: 1`
3. `acceptance_criteria` must have at least 1 item
4. `core_experience.primary_screen` must be PascalCase
5. If `independent: false`, `depends_on` must reference an existing feature name
6. `constraints` must have at least 1 item (empty = red flag)
7. `out_of_scope` must have at least 1 item (empty = scope creep risk)
8. `version` starts at 1, increments on evolve

## project.state.json

```json
{
  "seed_version": 1,
  "current_stage": "interview | seed | scaffold | build | qa | retro | complete",
  "completed_features": [],
  "in_progress": null,
  "failed": [],
  "build_retries": 0,
  "qa_history": [],
  "retro_count": 0
}
```

## project.blueprint.json (M5+)

```json
{
  "screens": ["PascalCase screen names"],
  "data_model": {
    "EntityName": { "field": "type" }
  },
  "api_routes": [],
  "state_management": "zustand | useState",
  "auth_strategy": "none | localStorage | supabase"
}
```

## decisions.log (M3+)

JSON array, each entry:
```json
{
  "id": "d001",
  "phase": "gate-a | gate-b",
  "decision": "string",
  "reason": "string",
  "binding": true,
  "timestamp": "ISO 8601"
}
```
