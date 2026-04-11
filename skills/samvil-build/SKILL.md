---
name: samvil-build
description: "Build core experience + features from seed. Circuit breaker per feature. Context Kernel sync on every step."
---

# SAMVIL Build — Core Experience + Feature Implementation

You are adopting the role of **Full-Stack Developer**. Implement the seed spec as working code.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "Build" task를 `in_progress`로 설정
1. Read `project.seed.json` → know what to build
2. Read `project.state.json` → know what's already done (resume support), get `session_id`
3. Read `project.config.json` → `selected_tier`, `max_total_builds`
4. Read `project.blueprint.json` → architecture decisions (screens, data model, components, routes)
5. Read `decisions.log` → binding decisions from Council (if exists, respect them)
6. Read `references/web-recipes.md` from this plugin directory → patterns to use
7. Check `completed_features` in state — skip already-built features

## Structured Build Event Schema

Use these normalized `error_category` values everywhere build events are emitted:
- `import_error`
- `type_error`
- `config_error`
- `runtime_error`
- `dependency_error`
- `unknown`

Normalize `error_signature` to a brief, repeatable summary (for example: `Module not found: @/lib/utils`).

## Phase A: Core Experience

The seed's `core_experience` defines what the user does in the first 30 seconds. **Build this first.**

1. Read `seed.core_experience`
2. Create the primary screen component: `components/<primary_screen>.tsx`
3. Create supporting components (1-3 components, single responsibility each)
4. Create state management if the feature requires cross-component state sharing:
   - Zustand (`seed.tech_stack.state` = `"zustand"`): create `lib/store.ts`
   - useState: inline in components
5. Wire into page: update `app/page.tsx` to import and render the primary screen
6. **Build verify (INV-2):**

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

**Circuit Breaker (MAX_RETRIES=2):**
- On build success, **MCP (best-effort):**
  ```
  mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_pass", stage="build", data='{"attempt":1,"scope":"core"}')
  ```
- Build fails → `tail -30 .samvil/build.log` → fix → retry
- On every build failure, **MCP (best-effort):**
  ```
  mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_fail", stage="build", data='{"attempt":<N>,"scope":"core","error_signature":"<brief normalized error>","error_category":"<enum>","touched_files":["<paths>"]}')
  ```
- **에러를 수정할 때마다** `.samvil/fix-log.md`에 한 줄 append:
  ```
  [core] <에러 내용> → <해결 방법>
  ```
- **MCP (best-effort):** Log the fix:
  ```
  mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="fix_applied", stage="build", data='{"scope":"core","error_category":"<enum>","summary":"<brief fix summary>","files":["<paths>"]}')
  ```
- 2 failures → **Adaptive Tier 제안** (minimal/standard인 경우):
  ```
  [SAMVIL] Core experience 빌드가 2회 실패했습니다.
  현재 tier: <tier>. 더 높은 tier로 업그레이드하면 더 많은 에이전트가 도움을 줄 수 있습니다.
  업그레이드할까요? (yes → Council부터 재실행 / no → 중단)
  ```
  승인 시: `config.selected_tier` 업그레이드 → `state.current_stage` = `"council"` → `samvil-council` invoke
  거부 시: STOP, report to user

7. Update `project.state.json`: note core experience complete

```
[SAMVIL] Stage 4/5: Core Experience built ✓
  Component: <primary_screen>
  Build: passing
```

## Phase A.5: Dependency Pre-Resolution

모든 feature를 읽고, 필요한 npm 패키지를 **한 번에** 설치한다. feature 빌드 중 하나씩 발견하며 설치하면 시간 낭비.

```bash
# seed.features + blueprint.key_libraries에서 필요한 패키지 추출
# 예: DnD → @hello-pangea/dnd, 차트 → recharts, 날짜 → date-fns
npm install <packages> --save > .samvil/deps-install.log 2>&1
```

## Phase B: Features

Read `seed.features` sorted by priority (1 first, then 2).
Read `config.selected_tier` to determine build mode.

### Step 1: Classify Features into Batches

Group features by dependency and independence:

```
Batch 1: All independent=true P1 features (no depends_on)
  → Can be built in parallel if tier >= standard
Batch 2: Features that depend on Batch 1 (sequential)
Batch 3: Independent P2 features (parallel if applicable)
Batch 4: Dependent P2 features (sequential)
```

### Step 2: Build Each Batch

#### If tier is `minimal` — Sequential (inline, no spawn)

Build features one at a time (same as v1):

**For each feature:**

1. **Re-read Context Kernel (INV-1)** — Re-read `project.seed.json` + `project.state.json` before every feature. Context may have been compressed — files are the truth. **Also read `.samvil/fix-log.md`** (if exists) to prevent repeating the same errors.
   - **Context Compression**: seed에서 해당 feature만 추출하여 작업. 전체 seed를 컨텍스트에 유지하지 않음.
   - **Include**: feature_name, description, acceptance_criteria, ui_hints
   - **Exclude**: interview_summary, evolve_history, other features' details
2. **MCP (best-effort):** Log feature start:
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_feature_start", stage="build", data='{"feature":"<name>"}')
   ```
3. **Plan** — What components? What state changes? What routes? Max 3 new files per feature.
4. **Implement** — Create/modify components, lib, routes. Keep existing code working.
5. **Build verify (INV-2)**:
   ```bash
   cd ~/dev/<seed.name>
   npm run build > .samvil/build.log 2>&1
   ```
   On build success, **MCP (best-effort):**
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_pass", stage="build", data='{"attempt":1,"scope":"feature:<name>"}')
   ```
   Circuit Breaker: MAX_RETRIES=2. 2 failures on a feature → mark as `failed`, continue to next feature.
   On every build failure, **MCP (best-effort):**
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_fail", stage="build", data='{"attempt":<N>,"scope":"feature:<name>","error_signature":"<brief>","error_category":"<enum>","touched_files":["<paths>"]}')
   ```
   **Adaptive Tier**: 전체 failed features가 2개 이상이면 tier 업그레이드 제안 (P1-S5와 동일).
   **에러를 수정할 때마다** `.samvil/fix-log.md`에 한 줄 append:
   ```
   [feature:<name>] <에러 내용> → <해결 방법>
   ```
   **MCP (best-effort):** Log the fix:
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="fix_applied", stage="build", data='{"scope":"feature:<name>","error_category":"<enum>","summary":"<brief fix summary>","files":["<paths>"]}')
   ```
6. **MCP (best-effort):** Log feature result:
   On success:
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_feature_success", stage="build", data='{"feature":"<name>"}')
   ```
   On failure:
   ```
   mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_feature_fail", stage="build", data='{"feature":"<name>","error":"<brief error>","error_category":"<enum>","retry":<N>}')
   ```
7. **Drift Check** — Feature 구현 후, `seed.features`에서 해당 feature의 `description`을 다시 읽고, 구현이 description 범위를 벗어나면 경고:
   ```
   [SAMVIL] ⚠️ Drift: <feature-name>
     Seed: "<seed description>"
     구현: "<실제 구현 내용 요약>"
     → seed에 없는 기능이 추가됨. 제거하거나 seed를 업데이트하세요.
   ```
   Drift 감지 시 사용자에게 보고만 하고 진행은 계속한다 (blocking 아님).
8. **Update state** — Add to `completed_features` or `failed`.

```
[SAMVIL] Feature: <name> ✓  [N/M features complete]
```

#### If tier is `standard` or higher — Parallel Dispatch (spawn workers)

For batches with 2+ independent features, spawn CC Agent workers **in controlled parallel batches**.

### Dynamic Parallelism (MAX_PARALLEL)

Determine `MAX_PARALLEL` at runtime based on system resources:

```
## Step 0: Determine MAX_PARALLEL

# 1) 사용자 override 확인
if config.max_parallel is set:
    MAX_PARALLEL = config.max_parallel
else:
    # 2) CPU 코어 기반 기본값
    CPU_CORES = sysctl -n hw.ncpu (macOS) or nproc (Linux)
    if CPU_CORES <= 4:   MAX_PARALLEL = 1
    elif CPU_CORES >= 8: MAX_PARALLEL = 3
    else:                MAX_PARALLEL = 2  # 기본값

    # 3) 메모리 압박 시 감소
    MEM_USAGE = 현재 메모리 사용률 (%)
    if MEM_USAGE > 80%:  MAX_PARALLEL = max(1, MAX_PARALLEL - 1)

# 최종값 출력
[SAMVIL] MAX_PARALLEL = <N> (CPU: <cores> cores, Memory: <usage>%)
```

### Independence Verification (병렬 가능 여부 체크)

Before spawning parallel workers, verify that features in the same batch are truly independent:

```
## 독립성 체크리스트 — 모두 YES여야 병렬 실행 가능

1. 파일 겹침 없음: 두 feature가 같은 파일을 생성/수정하지 않는가?
   - OK: feature A → components/todo/, feature B → components/calendar/
   - NG: feature A와 B 모두 app/layout.tsx 수정 필요
2. Shared store 변경 없음: 두 feature가 같은 Zustand slice를 수정하지 않는가?
3. Routing 충돌 없음: 두 feature가 같은 route 경로를 사용하지 않는가?
4. 의존성 역방향 없음: feature B가 feature A의 컴포넌트를 import하지 않는가?
```

하나라도 NO이면 해당 feature쌍은 순차 실행으로 강등:

```
[SAMVIL] Independence check: <feature-A> + <feature-B> → SEQUENTIAL (reason: <why>)
```

모두 YES인 feature만 같은 chunk에서 병렬 실행.

### Worker Context Budget (토큰 최적화)

Worker에게 전달하는 컨텍스트는 **2000 토큰 이내**로 유지한다. 전체 seed를 전달하지 않고, 해당 feature만 slicing하여 전달한다.

**포함 (Include):**
- `feature_name`, `feature_description`, `acceptance_criteria` — 해당 feature 1개만
- `ui_hints` — 해당 feature에 관련된 것만
- `relevant_web_recipe` — references/web-recipes.md에서 해당 feature와 관련된 패턴만 발췌
- `tech_stack 요약` — framework, UI library, state management 3줄 요약
- `architecture` — blueprint.json의 architecture 섹션에서 디렉토리 구조 + 컴포넌트 계층만

**제외 (Exclude):**
- `interview_summary` — Worker에게 불필요
- `evolve_history` — Worker에게 불핀요
- `full preset data` — app-presets, design-presets 전체
- 다른 features의 상세 내용 — 다른 feature 이름 목록만 제공 (의존성 파악용)
- `core_experience` 전문 — 이미 Phase A에서 구현 완료

**압축 규칙:**
1. seed에서 feature를 추출할 때 JSON 그대로가 아닌 요약 형태로 변환:
   ```
   Feature: <name>
   Description: <description>
   AC: <acceptance_criteria를 bullet 3-5개로>
   UI: <ui_hints 요약>
   Depends: <depends_on 리스트>
   ```
2. tech_stack은 다음 형식으로 압축:
   ```
   Stack: Next.js 14 + TypeScript + Tailwind + shadcn/ui + Zustand
   ```
3. architecture는 디렉토리 트리 + 주요 컴포넌트 이름만:
   ```
   Arch: app/(page, layout), components/<primary>/, lib/(store, utils)
   ```

**공통 프리앰블 최소화 (Prompt Caching):**
- 모든 Worker에게 동일하게 전달되는 "Coding Standards" / "Rules" 섹션은 한 번만 작성
- Agent 프롬프트 내에서 공통 규칙은 파일 경로 참조로 대체:
  ```
  ## Coding Standards
  Read and follow: references/web-recipes.md from the SAMVIL plugin directory.
  Key rules: shadcn/ui 우선, cn() 사용, 'use client' 필수, TypeScript strict.
  ```
- 전체 Code Quality Rules 섹션을 inline paste하지 않고 핵심 3-5줄로 요약

### Chunk Dispatch

Split independent features into chunks of `MAX_PARALLEL`. Spawn each chunk in ONE message (parallel). Wait for all agents in a chunk to complete before spawning the next chunk.

```
Agent(
  description: "SAMVIL Build: <feature-name>",
  model: config.model_routing.build_worker || config.model_routing.default || "sonnet",
  prompt: "You are a feature builder for SAMVIL.

Read your persona:
<paste content of agents/frontend-dev.md>

## Context (≤2000 tokens)
Project: ~/dev/<seed.name>/
Stack: <tech_stack 1-line summary, e.g., "Next.js 14 + TypeScript + Tailwind + shadcn/ui + Zustand">
Constraints: <seed.constraints in 3 bullet points max>
Architecture: <blueprint directory tree + component hierarchy, 5-10 lines>
Other Features: <comma-separated list of OTHER feature names only>

## Your Feature
Name: <feature-name>
Description: <feature description>
AC:
  - <acceptance_criteria bullet 1>
  - <acceptance_criteria bullet 2>
  - <acceptance_criteria bullet 3>
UI Hints: <relevant ui_hints, 1-2 lines>
Depends On: <depends_on or "none">
Recipe: <relevant web-recipe pattern name + key code snippet only>

## Rules
- Read existing code first to understand current structure
- Create components in components/<feature-name>/
- Do NOT modify shared files (layout.tsx, store root) unless absolutely necessary
- Do NOT touch other features' components
- Run: cd ~/dev/<seed.name> && npx tsc --noEmit 2>&1 | head -20 && npx eslint . --quiet 2>&1 | head -20
- Report: files created, files modified, lint/typecheck status

## Coding Standards
Read: references/web-recipes.md from SAMVIL plugin directory for patterns.
Key: shadcn/ui 우선 | cn() 사용 | 'use client' 필수 | TypeScript strict | no `any`",
  subagent_type: "general-purpose"
)
```

### Progress Trim (실시간 진행 상황 출력)

각 Agent의 진행 상황을 실시간으로 출력:

```
[SAMVIL] [Worker 1/<total>] Feature: <name> — building...
[SAMVIL] [Worker 2/<total>] Feature: <name> — building...
[SAMVIL] [Worker 1/<total>] Feature: <name> — done ✓
[SAMVIL] [Worker 2/<total>] Feature: <name> — failed ✗ (see .samvil/build.log)
```

형식 규칙:
- Worker 번호는 해당 chunk 내 1부터 시작
- `<total>` = 현재 chunk의 전체 worker 수
- Agent가 완료되면 즉시 결과 라인 출력
- 실패 시 로그 파일 경로 안내

**Example with MAX_PARALLEL=2 and 5 independent features:**
- Chunk 1: spawn agents for feature A + feature B (parallel) → wait
- Chunk 2: spawn agents for feature C + feature D (parallel) → wait
- Chunk 3: spawn agent for feature E (single) → wait

After all chunks complete:

1. **Integration build** — Run `npm run build` to verify no conflicts
   - Do NOT run `npm run build` inside individual worker agents. Instead, workers run quick checks only:
     ```bash
     cd ~/dev/<seed.name> && npx tsc --noEmit && npx eslint . --quiet
     ```
   - Full `npm run build` runs only here (after all chunks complete) and during QA.
   - On build success, **MCP (best-effort):**
     ```
     mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_pass", stage="build", data='{"attempt":1,"scope":"integration"}')
     ```
   - On build failure, **MCP (best-effort):**
     ```
     mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_fail", stage="build", data='{"attempt":<N>,"scope":"integration","error_signature":"<brief>","error_category":"<enum>","touched_files":["<paths>"]}')
     ```
2. **Conflict detection** — If build fails after parallel workers:
   ```
   [SAMVIL] Parallel build conflict detected
     Likely cause: multiple workers modified shared files
     Resolution: re-building conflicting feature sequentially...
   ```
   Re-run the conflicting feature inline (sequential) reading the current state.
3. **Update state** — Mark each feature as completed or failed.

```
[SAMVIL] Batch 1 (parallel): auth ✓, task-crud ✓  [2/4]
[SAMVIL] Batch 2 (sequential): kanban-view ✓      [3/4]
[SAMVIL] Batch 3: dashboard ✓                      [4/4]
```

### After All Features

```
[SAMVIL] Stage 4/5: Build complete
  Features: N/M passed (X parallel, Y sequential)
  Failed: [list or "none"]
  Build: passing
  Agents spawned: <count>
  Builds run: <count>
```

**MCP (best-effort):** Save build stage completion with implementation rate:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="build_stage_complete", stage="qa", data='{"features_passed":<N>,"features_failed":<N>,"features_total":<M>,"implementation_rate":<N/M>,"agents_spawned":<N>,"builds_run":<N>}')
```

Update `project.state.json` with `implementation_rate`: `"implementation_rate": <N/M>` (e.g., 0.85 for 85%).

## Chain to QA (INV-4)

```
[SAMVIL] Stage 5/5: Running QA verification...
```

Invoke the Skill tool with skill: `samvil-qa`

## Output Format

Modified/created files in `~/dev/<seed.name>/`:
- `components/<primary_screen>.tsx`: core experience component
- `components/<feature-name>/*.tsx`: feature components (PascalCase, one per file)
- `lib/store.ts` (if zustand): state management with typed slices
- `app/page.tsx`: updated to import primary screen
- `app/<feature>/page.tsx`: feature pages (if applicable)

Verification output per feature:
- `[SAMVIL] Feature: <name> ✓ [N/M features complete]`
- `npm run build` exit code 0 after each feature

Progress trim (parallel workers):
```
[SAMVIL] [Worker <N>/<total>] Feature: <name> — building...
[SAMVIL] [Worker <N>/<total>] Feature: <name> — done ✓
[SAMVIL] [Worker <N>/<total>] Feature: <name> — failed ✗ (see .samvil/build.log)
[SAMVIL] Independence check: <A> + <B> → SEQUENTIAL (reason: <why>)
[SAMVIL] MAX_PARALLEL = <N> (CPU: <cores> cores, Memory: <usage>%)
```

Final summary:
```
[SAMVIL] Stage 4/5: Build complete
  Features: N/M passed (X parallel, Y sequential)
  Failed: [list or "none"]
  Build: passing
  Agents spawned: <count>
  Builds run: <count>
```

## Anti-Patterns

1. Do NOT add features not listed in seed.features
2. Do NOT hardcode API responses or use mock data — use env vars + real fetch patterns
3. Do NOT dump build logs into conversation — write to `.samvil/build.log`

## Code Quality Rules

1. **`'use client'`** on every component with hooks, event handlers, or browser APIs
2. **TypeScript strict** — no `any` in business logic. Use proper interfaces.
3. **PascalCase** components, one component per file
4. **State management** — follow `seed.tech_stack.state` pattern
5. **shadcn/ui 컴포넌트 우선** — Button, Card, Input, Dialog 등은 `@/components/ui/`의 shadcn 컴포넌트 사용. 직접 만들지 말 것. 필요한 컴포넌트가 없으면 `npx shadcn@latest add <component>` 실행.
6. **`cn()` utility** — `@/lib/utils`의 `cn()` 사용 (shadcn init이 자동 생성). 모든 className 조합에 사용.
7. **Responsive** — use `md:`, `lg:` prefixes for layout changes
8. **Context7 활용** — shadcn/ui 컴포넌트 사용법이 불확실하면 `mcp__plugin_context7_context7__query-docs` 도구로 최신 문서 조회.
8. **`@/` imports** — absolute imports via the alias
9. **Real content** — no "Lorem ipsum" or placeholder text
10. **Empty states** — every list/collection handles zero items
11. **No dead code** — don't generate unreachable code
12. **Hydration-safe** — use the `mounted` pattern from web-recipes.md for any localStorage/browser API usage
13. **localStorage defensive** — always wrap `JSON.parse(localStorage.getItem())` in try-catch with fallback to empty default. Corrupt data must not crash the app.
14. **UX Writing** — placeholder 텍스트, 빈 상태 메시지, 에러 메시지, 성공 토스트를 **사용자 관점에서** 작성. "Error occurred" → "저장에 실패했어요. 다시 시도해주세요." 한국어 앱이면 한국어로.
15. **첫 30초 가치 전달** — core_experience 구현 시 사용자가 앱을 열었을 때 **즉시 가치를 느끼도록**: 샘플 데이터 프리필, 가이드 텍스트, 또는 빈 상태에서 다음 행동 유도.
16. **프리미엄 게이트 규칙** — 결제가 out_of_scope인데 프리미엄 UI가 있으면, "현재 모든 기능 무료" 배너를 표시하거나 게이트 자체를 비활성화. 결제 안 되는데 잠긴 UI만 보여주면 사용자가 이탈함.

## What NOT To Do

- Don't add features not in the seed
- Don't change the tech stack
- Don't add testing frameworks
- Don't add linting beyond the template
- Don't create README.md
- Don't add premature optimization (memo, lazy loading)
- Don't dump build logs into conversation — use .samvil/build.log
- **Don't hardcode API responses or use mock data** — real integrations only:
  - External APIs → `fetch` with `process.env.NEXT_PUBLIC_*` / `process.env.*` env vars
  - Database → Supabase client (if interview selected Supabase), NOT localStorage for persistent data
  - Auth → Supabase Auth (if interview selected auth), NOT fake login
  - If an API key is required, create `.env.example` with the key name and a placeholder
  - If real integration is truly impossible (API key unavailable), use env var pattern with `if (!apiKey) return fallback` — NOT hardcoded responses

**TaskUpdate**: "Build" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
Invoke the Skill tool with skill: `samvil-qa`

### Codex CLI (future)
Read `skills/samvil-qa/SKILL.md` and follow its instructions.
