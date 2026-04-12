---
name: samvil-seed
description: "Crystallize interview results into project.seed.json — the immutable spec all stages reference."
---

# SAMVIL Seed — Specification Crystallization

You are adopting the role of **Seed Architect**. Transform interview results into a structured, machine-readable spec.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Seed" task를 `in_progress`로 설정
1. Read `project.state.json` → confirm `current_stage` is `"seed"`, get `session_id`
2. Read `interview-summary.md` from the project directory (INV-3 — **read from file, not conversation**)
3. Read `references/seed-schema.md` from this plugin directory for the schema
4. **Follow `references/boot-sequence.md`** for metrics start/end and checkpoint rules.

## Process

### Step 1: Map Interview to Seed

Read `interview-summary.md` and map each section.

#### solution_type: "web-app" (기본)

| Interview Section | Seed Field |
|---|---|
| Target User + Core Problem | `description` |
| Core Experience | `core_experience` (description, primary_screen, key_interactions) |
| Must-Have Features | `features` with priority assignment |
| Out of Scope | `out_of_scope` |
| Constraints | `constraints` |
| Success Criteria | `acceptance_criteria` |

**Derive automatically:**
- `name`: kebab-case from the app idea (e.g., "task management SaaS" → "task-manager")
- `solution_type`: `"web-app"` (default)
- `mode`: `"web"` (deprecated, kept for migration)
- `tech_stack`: defaults unless interview specified otherwise
  - `state`: `"zustand"` if complex state (multiple entities, persistence), `"useState"` if simple
- `core_experience.primary_screen`: PascalCase component name from core experience
- `features[].independent`: `false` if a feature clearly needs another feature's data
- `features[].depends_on`: set to the dependency feature name if not independent
- `version`: `1`
- Note: `agent_tier` is now in `project.config.json`, not in seed

#### solution_type: "automation"

| Interview Section | Seed Field |
|---|---|
| 해결할 문제 | `description` |
| 입력과 출력 | `core_flow` (description, input, output, trigger) |
| Must-Have Features | `features` with priority assignment |
| Out of Scope | `out_of_scope` |
| Constraints | `constraints` (+ auto-added dry-run constraint) |
| Success Criteria | `acceptance_criteria` |

**Derive automatically:**
- `name`: kebab-case from the automation idea (e.g., "daily weather slack bot" → "weather-slack-bot")
- `solution_type`: `"automation"`
- `core_flow`: `{ description, input, output, trigger }` — replaces `core_experience`
  - `description`: what the automation does (1 sentence)
  - `input`: data source description (e.g., "Weather API JSON response")
  - `output`: expected output (e.g., "Slack message with formatted forecast")
  - `trigger`: execution trigger (e.g., "cron: 0 9 * * *", "manual", "webhook", "file-change")
- `tech_stack`:
  - `framework`: `"python-script"` | `"node-script"` | `"shell-script"` | `"cc-skill"`
  - No `ui`, `state`, `router` fields (automation doesn't need them)
- `implementation`:
  - `type`: `"python-automation"` | `"node-automation"` | `"cc-skill"`
  - `runtime`: `"python"` | `"node"` | `"shell"`
  - `entry_point`: `"src/main.py"` | `"src/main.ts"` | `"SKILL.md"`
- **Auto-add constraint**: `"Script must support --dry-run mode with fixtures/ for testing without real API calls"`
- `features[].independent`: `true` for most automation features (they're usually standalone processing steps)
- `version`: `1`

### solution_type: "game"

| Interview Section | Seed Field |
|---|---|
| 장르 | `description` |
| 게임 요소 | `core_experience` (description, game_config, game_states) |
| 게임 요소/기능 | `features` with priority assignment |
| Out of Scope | `out_of_scope` |
| Constraints | `constraints` |
| Success Criteria | `acceptance_criteria` |

**Derive automatically:**
- `name`: kebab-case from the game idea (e.g., "simple jump game" → "jump-game")
- `solution_type`: `"game"`
- `core_experience`:
  - `description`: what the player does (e.g., "Jump over obstacles and collect coins")
  - `game_config`: `{ width: 800, height: 600, physics: "arcade", input: "keyboard" }`
    - `width`/`height`: from interview (default 800x600)
    - `physics`: `"arcade"` (default) — only arcade physics supported
    - `input`: from interview answer (keyboard/mouse/touch)
  - `game_states`: `["Menu", "Play", "GameOver"]` — standard 3-state game loop
  - `key_interactions`: derived from genre (e.g., platformer → ["jump", "move-left", "move-right"])
- `tech_stack`:
  - `framework`: `"phaser"`
  - No `ui`, `state`, `router` fields (game doesn't need them)
- `implementation`:
  - `type`: `"phaser-game"`
  - `runtime`: `"browser"`
  - `entry_point`: `"src/main.ts"`
- **Auto-add constraints**:
  - `"Game must run in browser via Phaser 3 — no native executable"`
  - `"All assets must be generated in code (no external asset files unless user provided)"`
- `features[].independent`: `false` for game mechanics (they share scene lifecycle, physics world)
- `features[].depends_on`: core mechanics depend on scene setup
- `version`: `1`

### Step 2: Be Opinionated

- **Don't ask the user** "zustand or redux?" — choose what's simplest.
- **Fewer features is better.** If in doubt, make it priority 2.
- **Acceptance criteria must be testable.** "App looks nice" → "Layout renders correctly at 375px mobile width"
- **Constraints must not be empty.** Add "No backend server — client-only with localStorage" if none specified.
- **Out of scope must not be empty.** Add at least 2 reasonable exclusions.

### Step 3: Self-Validate

Check against schema rules from `references/seed-schema.md`:

- [ ] `name` is valid npm package name
- [ ] At least 1 feature with `priority: 1`
- [ ] At least 1 acceptance criterion
- [ ] `primary_screen` is PascalCase
- [ ] All `depends_on` references exist in features list
- [ ] `constraints` is not empty
- [ ] `out_of_scope` is not empty
- [ ] No feature name appears in both `features` and `out_of_scope`
- [ ] **CRUD completeness**: data entity를 만드는 feature가 있으면, 해당 entity의 Create/Read/Update/Delete 중 빠진 것이 없는지 확인. 빠진 CRUD가 있으면 AC에 추가하거나 out_of_scope에 명시.
- [ ] **AC가 모든 P1 feature를 커버**: 각 P1 feature에 대해 최소 1개 AC가 존재하는지 확인. 커버 안 되는 P1 feature가 있으면 AC 추가.
- [ ] **데이터 영속성 체크**: feature에 사용자가 생성하는 데이터(글, 할일, 설정 등)가 있으면 → constraints에 영속성 전략 명시. 없으면 자동 추가:
  - "No backend server — client-only with localStorage" (기본)
  - 데이터 손실이 치명적인 앱(이력서, 문서 등)이면 AC에 "데이터가 브라우저 재시작 후에도 유지된다" 추가
- [ ] **첫 30초 가치 전달**: core_experience에 "사용자가 앱을 열었을 때 즉시 가치를 느끼는가?" 체크. 빈 화면만 나오면 → AC에 "빈 상태에서 다음 행동을 유도하는 가이드가 있다" 추가
- [ ] **Stub 허용 판정**: AC 중 AI/API 연동이 필요한 항목은 stub으로 대체 가능한지 판정. core_experience에 직결되는 기능은 stub 불허 (QA에서 UNIMPLEMENTED = FAIL 처리됨). out_of_scope에 명시적으로 "v1은 mock 데이터" 등으로 적어야만 stub 허용.
- [ ] **Testable AC (PHI-06)**: 각 acceptance_criteria 항목에 대해 vague 단어를 감지하고 `vague_words` 배열을 태깅:

Vague patterns: "좋은", "빠른", "깔끔한", "직관적인", "부드러운", "전문적인", "모던한", "사용자 친화적인", "good", "nice", "fast", "clean", "intuitive", "smooth", "professional", "modern", "user-friendly", "well-designed"

AC JSON format:
```json
{
  "description": "UI가 직관적이다",
  "vague_words": ["직관적"],
  "rewrite_hint": "주요 기능이 3클릭 이내 도달 가능하다"
}
```

**vague_words가 비어있지 않은 AC가 있으면**: Seed presentation 시 경고 표시:
```
⚠️ Vague AC detected: "UI가 직관적이다"
  → Rewrite hint: "주요 기능이 3클릭 이내 도달 가능하다"
```
vague AC는 1개까지 허용. 2개 이상이면 자동으로 rewrite_hint 기반으로 재작성.

### Step 4: Present to User with Preview

Seed의 `core_experience`와 `features`를 기반으로 **텍스트 와이어프레임**을 함께 표시:

```
[SAMVIL] Seed Generated — project.seed.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Preview:
┌─────────────────────────────┐
│  <App Name>                 │
│  ┌───────────────────────┐  │
│  │ <Primary Screen>      │  │
│  │  [core_experience]    │  │
│  │  • key_interaction 1  │  │
│  │  • key_interaction 2  │  │
│  └───────────────────────┘  │
│                             │
│  Features:                  │
│  ✓ <P1 feature 1>          │
│  ✓ <P1 feature 2>          │
│  ○ <P2 feature (if any)>   │
└─────────────────────────────┘

<pretty-printed seed JSON>
```

Then ask: **"Seed looks good? Say 'go' to start building, or tell me what to change."**

If user requests changes: modify the seed and re-present. Do NOT re-interview.

## After User Approves (INV-4)

### 1. Write seed to file

Write the approved seed JSON to `~/dev/<project>/project.seed.json` using the Write tool.

### 1b. MCP Event + Seed Version (필수)

```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="seed_generated", stage="seed", data='{"version":1,"features_count":<N>}')

mcp__samvil_mcp__save_seed_version(session_id="<session_id>", version=1, seed_json='<escaped seed JSON>', change_summary="Initial seed from interview")
```

### 2. Update state and chain

Read `project.config.json` → `selected_tier` to determine next step:

**If tier is `"minimal"` (no council):**

**MCP (best-effort):** Update stage:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="design", data='{"skipped":"council","reason":"minimal tier"}')
```

```
[SAMVIL] Stage 2/5: Seed ✓
[SAMVIL] Council: skipped (minimal tier)
```

Invoke the Skill tool with skill: `samvil-design`

**If tier is `"standard"` or higher (council runs):**

**MCP (best-effort):** Update stage:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="council", data='{"council_activated":true}')
```

```
[SAMVIL] Stage 2/5: Seed ✓
[SAMVIL] Running Council Gate A...
```

Invoke the Skill tool with skill: `samvil-council`

## Output Format

Write `~/dev/<project>/project.seed.json` — valid JSON conforming to `references/seed-schema.md`.

### web-app (기본)

Required fields and constraints:
- `name`: valid npm package name, kebab-case (e.g., "task-manager")
- `description`: 1-sentence string
- `solution_type`: `"web-app"`
- `mode`: always `"web"` (deprecated)
- `tech_stack`: `{ framework, ui, state, router }` — use simplest valid choice
- `core_experience`: `{ description, primary_screen (PascalCase), key_interactions[] }`
- `features[]`: each has `{ name, description, priority (1 or 2), independent, depends_on? }` — at least 1 with priority 1
- `acceptance_criteria[]`: each has `{ description, vague_words[], rewrite_hint? }` — at least 3 items, all testable
- `constraints[]`: at least 1 item (default: "No backend server — client-only with localStorage")
- `out_of_scope[]`: at least 2 items
- `version`: integer, starts at 1

No extra fields beyond the schema. No comments in JSON.

### automation

Required fields and constraints:
- `name`: kebab-case (e.g., "weather-slack-bot")
- `description`: 1-sentence string
- `solution_type`: `"automation"`
- `tech_stack`: `{ framework: "python-script"|"node-script"|"shell-script"|"cc-skill" }` — no ui/state/router
- `core_flow`: `{ description, input, output, trigger }` — replaces `core_experience`
  - `description`: what the automation does
  - `input`: data source description
  - `output`: expected output description
  - `trigger`: `"manual"` | `"cron: <schedule>"` | `"webhook"` | `"file-change"`
- `implementation`:
  - `type`: `"python-automation"` | `"node-automation"` | `"cc-skill"`
  - `runtime`: `"python"` | `"node"` | `"shell"`
  - `entry_point`: `"src/main.py"` | `"src/main.ts"` | `"SKILL.md"`
- `features[]`: each has `{ name, description, priority (1 or 2), independent, depends_on? }` — at least 1 with priority 1
- `acceptance_criteria[]`: each has `{ description, vague_words[], rewrite_hint? }` — at least 3 items, all testable
- `constraints[]`: must include `"Script must support --dry-run mode with fixtures/ for testing without real API calls"` + any user-specified constraints
- `out_of_scope[]`: at least 2 items
- `version`: integer, starts at 1

No extra fields beyond the schema. No comments in JSON.

### game

Required fields and constraints:
- `name`: kebab-case (e.g., "jump-game")
- `description`: 1-sentence string
- `solution_type`: `"game"`
- `tech_stack`: `{ framework: "phaser" }` — no ui/state/router
- `core_experience`:
  - `description`: what the player does
  - `game_config`: `{ width: 800, height: 600, physics: "arcade", input: "keyboard" }`
  - `game_states`: `["Menu", "Play", "GameOver"]`
  - `key_interactions`: `["<interaction>", ...]`
- `implementation`:
  - `type`: `"phaser-game"`
  - `runtime`: `"browser"`
  - `entry_point`: `"src/main.ts"`
- `features[]`: each has `{ name, description, priority (1 or 2), independent, depends_on? }` — at least 1 with priority 1
  - Feature names are game mechanics: "player-movement", "enemy-spawn", "collision-detection", "scoring-system", "level-progression"
- `acceptance_criteria[]`: each has `{ description, vague_words[], rewrite_hint? }` — at least 3 items, all testable
  - Game ACs should be verifiable via browser: "Player sprite moves left when left arrow is pressed", "Score increases when collectible is picked up", "GameOver screen appears when player hits enemy"
- `constraints[]`: must include `"Game must run in browser via Phaser 3"` + any user-specified constraints
- `out_of_scope[]`: at least 2 items
- `version`: integer, starts at 1

No extra fields beyond the schema. No comments in JSON.

## Anti-Patterns

1. Do NOT ask the user implementation choices — be opinionated (e.g., choose zustand vs useState yourself)
2. Do NOT leave `constraints` or `out_of_scope` empty — add defaults if none specified
3. Do NOT accept vague ACs — rewrite any with vague_words automatically

## Rules

1. **Seed is immutable after approval.** No changes during build. User can edit manually between stages.
2. **Read from files, not conversation.** Interview results come from `interview-summary.md`.
3. **Be opinionated.** Make technical decisions. Don't burden the user with implementation choices.

**TaskUpdate**: "Seed" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
- If minimal tier: Invoke the Skill tool with skill: `samvil-design`
- If standard+ tier: Invoke the Skill tool with skill: `samvil-council`

### Codex CLI (future)
Read the next skill's SKILL.md based on tier and follow its instructions.
