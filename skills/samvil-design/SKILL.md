---
name: samvil-design
description: "Generate project.blueprint.json with architecture decisions. Gate B design council for thorough+ tiers."
---

# SAMVIL Design — Architecture & Blueprint Generation

Generate the technical blueprint that translates the seed spec into concrete architecture decisions. Optionally run a design council (Gate B) for quality review.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Design" task를 `in_progress`로 설정
1. Read `project.seed.json` → what we're building
2. Read `project.state.json` → confirm `current_stage` is `"design"`, get `session_id`
3. Read `project.config.json` → `selected_tier`
4. Read `interview-summary.md` → user context
5. Read `decisions.log` → binding decisions from Gate A (if exists)
6. Read `references/seed-schema.md` → blueprint schema reference
7. **Follow `references/boot-sequence.md`** for metrics start/end and checkpoint rules.

## Step 1: Generate Blueprint

Adopt the `agents/tech-architect.md` persona. Read it for detailed behavior.

Read `seed.solution_type` to determine blueprint format.

### solution_type: "web-app" (기본)

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

### solution_type: "automation"

Create `project.blueprint.json` with automation-specific structure:

```json
{
  "entry_point": "src/main.py",
  "modules": {
    "core": ["main.py", "processor.py"],
    "utils": ["logger.py", "config.py"]
  },
  "fixtures": {
    "input": "fixtures/input/",
    "expected": "fixtures/expected/"
  },
  "dependencies": ["requests"],
  "error_handling": "retry_with_logging",
  "execution": {
    "type": "cli|cron|webhook|cc-skill",
    "schedule": "0 9 * * *"
  }
}
```

### solution_type: "game"

Create `project.blueprint.json` with game-specific structure:

```json
{
  "scenes": ["BootScene", "MenuScene", "GameScene", "GameOverScene"],
  "entities": ["Player", "Enemy", "Collectible"],
  "game_config": {
    "width": 800,
    "height": 600,
    "physics": "arcade",
    "input": "keyboard"
  },
  "assets": {
    "sprites": [],
    "audio": []
  },
  "scene_flow": {
    "BootScene": "MenuScene",
    "MenuScene": "GameScene",
    "GameScene": "GameOverScene",
    "GameOverScene": "MenuScene"
  },
  "key_libraries": ["phaser"],
  "state_management": "phaser-scene",
  "component_structure": {
    "scenes": ["BootScene", "MenuScene", "GameScene", "GameOverScene"],
    "entities": ["Player", "Enemy", "Collectible"],
    "config": ["game-config"]
  }
}
```

#### Game Blueprint Decision Rules

- **scenes**: Always include BootScene (asset preloading), MenuScene (start/restart), GameScene (main gameplay), GameOverScene (score + restart). Additional scenes for levels.
- **entities**: Derived from seed.features — each game mechanic maps to an entity class:
  - player-movement → Player entity
  - enemy-spawn → Enemy entity
  - collision-detection → physics config between entities
  - scoring-system → ScoreManager (scene-level)
  - level-progression → LevelManager (scene-level)
- **game_config**: Copied from `seed.core_experience.game_config`. Defaults: `{ width: 800, height: 600, physics: "arcade", input: "keyboard" }`
- **assets.sprites**: If `seed.core_experience.graphics` = "pixel art" → note that pixel art sprites need to be generated in code (no external files). If "simple shapes" → all graphics via Phaser graphics primitives.
- **assets.audio**: Empty by default (sound is optional). Add if seed.constraints include sound.
- **scene_flow**: Standard game loop. BootScene → MenuScene → GameScene → GameOverScene → (restart) → MenuScene.
- **key_libraries**: Always `["phaser"]`. No other game libraries.
- **state_management**: `"phaser-scene"` — Phaser scenes manage their own state via `init()`, `create()`, `update()` lifecycle.

#### Automation Blueprint Decision Rules

- **entry_point**:
  - Python: `"src/main.py"` | Node: `"src/main.ts"` | CC skill: `"SKILL.md"`
- **modules.core**: Always include `main.py/ts` (entry + argparse) and `processor.py/ts` (core logic)
- **modules.utils**: Always include `logger` and `config` (separation of concerns)
- **fixtures**: Always include `input/` and `expected/` subdirectories
- **dependencies**: Derived from `seed.features` and `seed.core_flow.input/output`
  - API calls → `["requests"]` (Python) or `["axios"]` (Node)
  - CSV processing → `+ ["pandas"]` or `["csv-parse"]`
  - HTML parsing → `+ ["beautifulsoup4"]` or `["cheerio"]`
  - Slack → `+ ["slack-sdk"]` or `["@slack/web-api"]`
- **error_handling**: `"retry_with_logging"` (default) | `"skip_and_continue"` | `"fail_fast"` — from interview Phase 2 answer
- **execution.type**: From `seed.core_flow.trigger`
  - `"manual"` → `"cli"`
  - `"cron: ..."` → `"cron"` (copy schedule)
  - `"webhook"` → `"webhook"`
  - CC skill → `"cc-skill"`
- **execution.schedule**: Extracted from trigger if cron format (e.g., `"0 9 * * *"`)

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

Spawn design council agents **in controlled parallel batches**:

```
MAX_PARALLEL = config.max_parallel || 2
```

Split design council agents into chunks of `MAX_PARALLEL`. Spawn each chunk in ONE message (parallel). Wait for all agents in a chunk to complete before spawning the next chunk.

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

## Step 3b: Blueprint Feasibility Check

Run a lightweight feasibility review before the user sees the final blueprint.

Use the CC Agent tool:

```
Agent(
  description: "SAMVIL Blueprint feasibility check",
  model: config.model_routing.design_reviewer || config.model_routing.default || "haiku",
  prompt: "You are a build feasibility reviewer for SAMVIL.

Read the final blueprint draft and answer:
1. Are all key_libraries realistically installable and maintainable?
2. Is the tech stack self-consistent with SAMVIL scaffold conventions?
3. Are there known compatibility risks?
4. Is the component/screen scope realistic for this build?

Return one of:
- GO
- CONCERN: <list>
- BLOCKER: <list>

Keep the response under 200 words.",
  subagent_type: "general-purpose"
)
```

### Main-session ownership rules

- The main session remains the only writer of `project.blueprint.json` and `project.state.json`
- **MCP (best-effort):** After feasibility check:
  ```
  mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="blueprint_feasibility_checked", stage="design", data='{"result":"GO|CONCERN|BLOCKER"}')
  ```
- If the result is `CONCERN` or `BLOCKER`, revise the blueprint in the main session first
- For each issue carried forward:
  ```
  mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="blueprint_concern", stage="design", data='{"summary":"<brief issue>","severity":"concern|blocker"}')
  ```
- Only present the final blueprint to the user after feasibility review and any needed edits

## Step 4: User Checkpoint

Present the post-feasibility blueprint:

```
[SAMVIL] Blueprint Generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━

Screens: [list]
Data Model: [summary]
State: [strategy]
Libraries: [list]
Routes: [summary]

{Gate B results if run}
{Feasibility review results}

Final blueprint (post-feasibility check) looks good? Say 'go' to start building, or tell me what to change.
```

## Step 5: Save and Chain (INV-4)

1. Write `project.blueprint.json` to project directory
2. **MCP (best-effort):** Save stage transition:
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="blueprint_generated", stage="scaffold", data='{"screens":<N>,"libraries":[<list>]}')
   ```
3. Print progress:

```
[SAMVIL] Design ✓
[SAMVIL] Stage 3/5: Scaffolding project...
```

4. Invoke the Skill tool with skill: `samvil-scaffold`

## 모바일 우선 입력 UX 가이드

폼이 많은 앱(이력서, 설문 등)에서는:
- 섹션별 단계 wizard (한 화면에 전부 보여주지 않기)
- Progress bar로 완료 현황 표시
- Auto-save (입력 중 데이터 손실 방지)
- 모바일 터치 타겟: 최소 44px

blueprint에 `mobile_considerations` 필드를 추가하여 Build 단계에서 참조.

## Output Format

Write `~/dev/<project>/project.blueprint.json` — valid JSON with these required fields:

### web-app

```json
{
  "screens": ["<PascalCase name>"],
  "data_model": { "<Entity>": { "id": "string", "<field>": "<type>" } },
  "api_routes": [],
  "state_management": "zustand | useState | none",
  "auth_strategy": "none | supabase | custom",
  "key_libraries": ["<lib>"],
  "component_structure": {
    "shared_ui": ["<Component>"],
    "feature_components": { "<feature>": ["<Component>"] }
  },
  "routing": { "/": "<Screen>" },
  "mobile_considerations": {}
}
```

Decision rules for each field:
- `state_management`: "useState" if <= 2 entities, no cross-component sharing. "zustand" if persistence or 3+ entities. "none" if static.
- `auth_strategy`: "none" unless seed explicitly requires auth.
- `api_routes`: empty array if localStorage. Populate if API needed.
- `key_libraries`: only libraries features actually need.
- `screens`: primary_screen + one per major feature needing its own page.

### automation

```json
{
  "entry_point": "src/main.py",
  "modules": {
    "core": ["main.py", "processor.py"],
    "utils": ["logger.py", "config.py"]
  },
  "fixtures": {
    "input": "fixtures/input/",
    "expected": "fixtures/expected/"
  },
  "dependencies": ["<dep>"],
  "error_handling": "retry_with_logging|skip_and_continue|fail_fast",
  "execution": {
    "type": "cli|cron|webhook|cc-skill",
    "schedule": "<cron expression or null>"
  }
}
```

Decision rules for each field:
- `entry_point`: Python → `src/main.py`, Node → `src/main.ts`, CC skill → `SKILL.md`
- `modules.core`: Always `main` (argparse + --dry-run) + `processor` (core logic)
- `modules.utils`: Always `logger` + `config` (separation of concerns)
- `dependencies`: Derived from features and I/O requirements
- `error_handling`: From interview Phase 2 answer, default `"retry_with_logging"`
- `execution.type`: Mapped from `seed.core_flow.trigger`

### game

```json
{
  "scenes": ["BootScene", "MenuScene", "GameScene", "GameOverScene"],
  "entities": ["<Entity>"],
  "game_config": { "width": 800, "height": 600, "physics": "arcade", "input": "keyboard" },
  "assets": { "sprites": [], "audio": [] },
  "scene_flow": { "BootScene": "MenuScene", "MenuScene": "GameScene", "GameScene": "GameOverScene", "GameOverScene": "MenuScene" },
  "key_libraries": ["phaser"],
  "state_management": "phaser-scene",
  "component_structure": { "scenes": [], "entities": [], "config": [] }
}
```

Decision rules for each field:
- `scenes`: Always BootScene + MenuScene + GameScene + GameOverScene minimum
- `entities`: Derived from seed.features (Player, Enemy, Collectible, etc.)
- `game_config`: From `seed.core_experience.game_config`
- `assets`: Empty arrays by default. All graphics generated in code.
- `scene_flow`: Standard game loop chain
- `key_libraries`: Always `["phaser"]`
- `state_management`: Always `"phaser-scene"`

### mobile-app

```json
{
  "screens": ["<PascalCase name>"],
  "navigation": {
    "type": "tabs|drawer|stack",
    "tabs": [{ "name": "<Tab>", "screen": "<Screen>", "icon": "<icon>" }]
  },
  "data_model": { "<Entity>": { "id": "string", "<field>": "<type>" } },
  "state_management": "zustand",
  "native_modules": ["<expo-module>"],
  "key_libraries": ["expo-router", "zustand"],
  "component_structure": {
    "shared_ui": ["<Component>"],
    "feature_components": { "<feature>": ["<Component>"] }
  }
}
```

Decision rules for each field:
- `screens`: primary_screen + one per major feature needing its own page
- `navigation.type`: from seed.implementation.navigation, default `"tabs"`
- `native_modules`: from seed.implementation.native_features, mapped to expo packages
- `key_libraries`: always `["expo-router", "zustand"]` + feature-specific additions
- `state_management`: always `"zustand"`

### solution_type: "mobile-app"

Create `project.blueprint.json` with mobile-specific structure:

```json
{
  "screens": ["HomeScreen", "SettingsScreen"],
  "navigation": {
    "type": "tabs",
    "tabs": [
      { "name": "Home", "screen": "HomeScreen", "icon": "home" },
      { "name": "Settings", "screen": "SettingsScreen", "icon": "settings" }
    ]
  },
  "data_model": {
    "EntityName": {
      "id": "string",
      "field": "type",
      "createdAt": "string (ISO 8601)"
    }
  },
  "state_management": "zustand",
  "native_modules": [],
  "key_libraries": ["expo-router", "zustand"],
  "component_structure": {
    "shared_ui": ["Button", "Card", "Input"],
    "feature_components": {
      "feature-name": ["Component1", "Component2"]
    }
  }
}
```

#### Mobile Blueprint Decision Rules

- **screens**: Derive from seed.core_experience.primary_screen + one per major feature. Each screen maps to an Expo Router page in `app/`.
- **navigation.type**: From `seed.implementation.navigation`. Default `"tabs"`.
  - `"tabs"` → `app/(tabs)/_layout.tsx` with BottomTabNavigator
  - `"drawer"` → `app/(drawer)/_layout.tsx` with DrawerNavigator
  - `"stack"` → `app/_layout.tsx` with StackNavigator
- **native_modules**: From `seed.implementation.native_features`.
  - camera → `expo-camera`
  - gps → `expo-location`
  - push → `expo-notifications`
  - sensors → `expo-sensors`
- **key_libraries**: Always `["expo-router", "zustand"]`. Add based on features:
  - offline → `+ ["@react-native-async-storage/async-storage"]`
  - maps → `+ ["react-native-maps"]`
  - forms → `+ ["react-hook-form"]`
- **state_management**: `"zustand"` for all mobile apps (same pattern as web-app).
- **component_structure**: Same pattern as web-app but uses React Native components (View, Text, TextInput, ScrollView) instead of HTML elements.

## Anti-Patterns

1. Do NOT add screens for features not in seed
2. Do NOT contradict Gate A binding decisions from decisions.log
3. Do NOT include libraries without a clear feature-level justification

## Rules

1. **Blueprint must be consistent with seed** — don't add screens for features not in seed
2. **Respect Gate A decisions** — read decisions.log, don't contradict binding decisions
3. **Be opinionated** — choose the simplest architecture that supports all seed features
4. **Gate B is optional** — only runs for thorough+ tiers
5. **One file output** — everything goes in project.blueprint.json
6. **Design은 모든 tier에서 실행** — minimal이라도 design preset 선택은 필수. 1분 안에 끝남.

**TaskUpdate**: "Design" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-scaffold`

### Codex CLI (future)
Read `skills/samvil-scaffold/SKILL.md` and follow its instructions.
