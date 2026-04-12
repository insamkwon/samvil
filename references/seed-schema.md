# Seed Schema Reference

## project.seed.json (v2)

```json
{
  "name": "string — kebab-case, valid npm package name",
  "description": "string — one-line project description",
  "solution_type": "web-app | automation | game | mobile-app | dashboard",
  "mode": "web (DEPRECATED — auto-migrated to solution_type)",
  "implementation": {
    "type": "string — e.g., nextjs-webapp, python-automation, phaser-game",
    "runtime": "node | python | browser | hybrid",
    "entry_point": "string — e.g., app/page.tsx, src/main.py, src/game.ts"
  },
  "tech_stack": {
    "framework": "nextjs | vite-react | astro | phaser | expo | python-script | node-script",
    "ui": "tailwind (optional — not needed for automation)",
    "state": "zustand | useState | none (optional)",
    "router": "app-router | react-router (optional — not needed for automation/game)"
  },
  "core_experience": {
    // screen pattern (web-app, dashboard):
    "description": "string — what user does in first 30 seconds",
    "primary_screen": "string — PascalCase component name",
    "key_interactions": ["string array — verb-noun format"]
    // OR core_flow pattern (automation, game, mobile-app):
    "description": "string — what this flow accomplishes",
    "input": "string — what goes in",
    "output": "string — what comes out",
    "trigger": "string — how it starts (manual, cron, webhook, user event)"
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
  "version": 1
}
```

## solution_type별 예시 seed

### web-app (기본)

```json
{
  "name": "todo-app",
  "description": "Simple task management with kanban board",
  "solution_type": "web-app",
  "tech_stack": { "framework": "nextjs", "ui": "tailwind", "state": "zustand", "router": "app-router" },
  "core_experience": {
    "description": "User sees their task list and can add a new task immediately",
    "primary_screen": "TaskDashboard",
    "key_interactions": ["create-task", "toggle-complete", "filter-by-status"]
  },
  "features": [
    { "name": "task-crud", "priority": 1, "independent": true },
    { "name": "kanban-view", "priority": 2, "independent": false, "depends_on": "task-crud" }
  ],
  "acceptance_criteria": ["AC: User can create a task with title and it appears in the list"],
  "constraints": ["Must work without authentication"],
  "out_of_scope": ["Multi-user collaboration", "Push notifications"],
  "version": 1
}
```

### automation

```json
{
  "name": "weather-slack-bot",
  "description": "Daily weather report sent to Slack channel",
  "solution_type": "automation",
  "implementation": { "type": "python-automation", "runtime": "python", "entry_point": "src/main.py" },
  "tech_stack": { "framework": "python-script" },
  "core_experience": {
    "description": "Fetches weather data from API and posts formatted summary to Slack",
    "input": "Weather API endpoint + Slack webhook URL",
    "output": "Formatted weather summary message in Slack channel",
    "trigger": "cron: 0 9 * * * (daily at 9am)"
  },
  "features": [
    { "name": "weather-fetch", "priority": 1, "independent": true },
    { "name": "slack-notify", "priority": 2, "independent": false, "depends_on": "weather-fetch" }
  ],
  "acceptance_criteria": ["AC: Script supports --dry-run and reads fixtures/input/ instead of API"],
  "constraints": ["Must support --dry-run with fixtures/", "No real API calls in dry-run mode"],
  "out_of_scope": ["Weather alerts", "Multi-city support"],
  "version": 1
}
```

### game

```json
{
  "name": "jump-game",
  "description": "Simple platformer with score tracking",
  "solution_type": "game",
  "implementation": { "type": "phaser-game", "runtime": "browser", "entry_point": "src/game.ts" },
  "tech_stack": { "framework": "phaser" },
  "core_experience": {
    "description": "Player controls a character that jumps over obstacles with increasing difficulty",
    "input": "Keyboard input (space/click to jump)",
    "output": "Score display + game over screen with restart option",
    "trigger": "User clicks Start button"
  },
  "features": [
    { "name": "player-movement", "priority": 1, "independent": true },
    { "name": "obstacle-generation", "priority": 2, "independent": false, "depends_on": "player-movement" },
    { "name": "score-system", "priority": 3, "independent": true }
  ],
  "acceptance_criteria": ["AC: Game starts on click, player can jump, score increments on obstacle pass"],
  "constraints": ["Must run in browser without server", "60fps target"],
  "out_of_scope": ["Multiplayer", "Sound effects"],
  "version": 1
}
```

### mobile-app

```json
{
  "name": "habit-tracker",
  "description": "Daily habit tracking mobile app",
  "solution_type": "mobile-app",
  "implementation": { "type": "expo-app", "runtime": "hybrid", "entry_point": "app/index.tsx" },
  "tech_stack": { "framework": "expo" },
  "core_experience": {
    "description": "User sees today's habits and can check off completed ones",
    "input": "Tap gesture on habit items",
    "output": "Completion state persisted locally + streak counter updated",
    "trigger": "User opens the app"
  },
  "features": [
    { "name": "habit-list", "priority": 1, "independent": true },
    { "name": "streak-tracking", "priority": 2, "independent": false, "depends_on": "habit-list" }
  ],
  "acceptance_criteria": ["AC: User can add a habit and toggle completion for today"],
  "constraints": ["Must work offline with local storage first"],
  "out_of_scope": ["Social features", "Push notifications"],
  "version": 1
}
```

### dashboard

```json
{
  "name": "sales-dashboard",
  "description": "Real-time sales analytics dashboard",
  "solution_type": "dashboard",
  "tech_stack": { "framework": "nextjs", "ui": "tailwind", "state": "zustand", "router": "app-router" },
  "core_experience": {
    "description": "User sees summary cards with key metrics and interactive charts",
    "primary_screen": "DashboardHome",
    "key_interactions": ["filter-by-date-range", "drill-down-chart", "export-csv"]
  },
  "features": [
    { "name": "metric-cards", "priority": 1, "independent": true },
    { "name": "chart-visualization", "priority": 2, "independent": false, "depends_on": "metric-cards" }
  ],
  "acceptance_criteria": ["AC: Dashboard shows 4 metric cards and a revenue chart with date filter"],
  "constraints": ["Charts must render within 2 seconds", "Mobile responsive"],
  "out_of_scope": ["Real-time WebSocket updates", "User authentication"],
  "version": 1
}
```

## Validation Rules

1. `name` must be valid npm package name (lowercase, hyphens, no spaces)
2. `solution_type` is required — one of: web-app, automation, game, mobile-app, dashboard
3. `mode` is deprecated — if present, auto-migrated: `mode: "web"` → `solution_type: "web-app"`
4. `features` must have at least 1 item with `priority: 1`
5. `acceptance_criteria` must have at least 1 item
6. `core_experience` uses screen pattern (primary_screen + key_interactions) for web-app/dashboard, or core_flow pattern (input + output + trigger) for automation/game/mobile-app
7. For screen pattern: `primary_screen` must be PascalCase
8. For core_flow pattern: all of input, output, trigger are required
9. If `independent: false`, `depends_on` must reference an existing feature name
10. `constraints` must have at least 1 item (empty = red flag)
11. `out_of_scope` must have at least 1 item (empty = scope creep risk)
12. `version` starts at 1, increments on evolve
13. `implementation` is optional — auto-filled by seed stage based on solution_type
14. `tech_stack.ui/state/router` are optional — not required for automation/game scripts

## project.config.json (실행 설정)

```json
{
  "selected_tier": "minimal | standard | thorough | full",
  "evolve_max_cycles": 5,
  "evolve_mode": "spec-only | full",
  "qa_max_iterations": 5,
  "max_total_builds": 15,
  "model_routing": {
    "interview": "opus",
    "council": "sonnet",
    "build_worker": "sonnet",
    "qa": "sonnet",
    "evolve": "opus",
    "lint_fix": "haiku",
    "default": "sonnet"
  },
  "skip_stages": []
}
```

**분리 원칙**: seed.json은 명세만, config.json은 실행 설정만. 설정 변경이 seed 버전에 영향 안 줌.

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
