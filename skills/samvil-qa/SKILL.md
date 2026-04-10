---
name: samvil-qa
description: "3-pass verification against seed acceptance criteria. Ralph loop for auto-fix. Verdict: PASS/REVISE/FAIL."
---

# SAMVIL QA — 3-Pass Verification

You are adopting the role of **QA Judge**. Verify the built app against the seed spec.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "QA" task를 `in_progress`로 설정
1. Read `project.seed.json` → acceptance criteria and features
2. Read `project.state.json` → completed features, failed features, qa_history, `session_id`
3. Read `project.config.json` → `qa_max_iterations`, `selected_tier`
4. Read `references/qa-checklist.md` from this plugin directory

### Seed 없는 경우 (Brownfield QA)

`project.seed.json`이 없으면 — 기존 프로젝트에 직접 QA를 실행하는 경우.

AskUserQuestion으로:
```
question: "이 프로젝트에 SAMVIL seed가 없습니다. 어떻게 할까요?"
header: "QA 모드"
options:
  - label: "코드 분석 먼저 (추천)"
    description: "samvil-analyze로 코드 분석 → 역방향 seed 생성 → QA 실행"
  - label: "일반 QA만"
    description: "seed 없이 빌드 검증 + 코드 품질만 체크 (AC 검증 생략)"
```

**"코드 분석 먼저"** 선택 시: Invoke `samvil-analyze` → analyze가 seed 생성 후 QA로 체인.

**"일반 QA만"** 선택 시:
- Pass 1 (Mechanical): 빌드 검증 — 정상 실행
- Pass 2 (Functional): **생략** (AC가 없으므로)
- Pass 3 (Quality): 코드 품질 — 정상 실행
- `.samvil/` 디렉토리 생성 후 결과 저장

## Pass 1: Mechanical Verification

```bash
cd ~/dev/<seed.name>
npm run build > .samvil/build.log 2>&1
echo "Exit code: $?"
```

Check:
- Build exits with code 0
- No TypeScript errors in output (if exit code != 0, `tail -30 .samvil/build.log`)
- No "Module not found" errors

**If Pass 1 fails:** Verdict = REVISE with specific build errors. Skip Pass 1b, Pass 2 and 3.

## Pass 1b: Playwright Smoke Run (빌드 통과 후)

Build가 성공하면 Playwright로 dev server를 띄워서 콘솔 에러와 빈 화면을 검출:

```bash
cd ~/dev/<seed.name>
```

### Playwright 설치 확인 (최초 1회)
```bash
npx playwright install chromium 2>/dev/null
```

### Smoke Test 실행

Use the `mcp__plugin_playwright_playwright__browser_navigate` tool to visit the dev server:

1. **Start dev server in background:**
   ```bash
   cd ~/dev/<seed.name> && npm run dev &
   ```
   Wait for it to be ready (up to 15 seconds).

2. **Navigate to the app:**
   ```
   mcp__plugin_playwright_playwright__browser_navigate(url="http://localhost:3000")
   ```

3. **Check for console errors:**
   ```
   mcp__plugin_playwright_playwright__browser_console_messages(level="error")
   ```
   - **No errors**: `[SAMVIL] Smoke Run: ✓ (no console errors)` → Pass 2로 진행
   - **Console errors found**: `[SAMVIL] Smoke Run: ✗ (N console errors)` → List the errors

4. **Check for empty body:**
   ```
   mcp__plugin_playwright_playwright__browser_evaluate(function="() => document.body.innerHTML.trim().length > 0")
   ```
   - **Body has content**: PASS
   - **Empty body**: `[SAMVIL] Smoke Run: ✗ (empty <body>)` → Verdict = REVISE

5. **Take screenshot for evidence (optional):**
   ```
   mcp__plugin_playwright_playwright__browser_take_screenshot(type="png", filename=".samvil/smoke-screenshot.png")
   ```

6. **Visit each route** from `blueprint.routing`:
   For each route, navigate and check for console errors + non-empty body.

7. **Keep dev server running** — Pass 2 needs it for runtime verification.
   Dev server stays up through Pass 2 and is stopped after Pass 2 completes.

**Verdict:**
- All routes: no console errors + non-empty body → PASS → Pass 2로 진행
- Any route: console errors OR empty body → REVISE with specific issues

## QA Execution Mode by Tier

After reading `selected_tier` from `project.config.json` (Boot Sequence step 3), choose execution path:

### `minimal` — Inline QA (unchanged)

Run Pass 2 and Pass 3 inline in the main session. Follow the sections below directly. This is the existing flow — no changes to preserve the current user experience and cost profile.

### `standard` / `thorough` / `full` — Independent Evidence

Keep Pass 1 in the main session. Then **skip the inline Pass 2 and Pass 3 sections below** and instead spawn independent agents:

```
Pass 1:  main session (build + smoke)
Pass 2:  independent qa-functional agent → skip to "Spawn Pass 2 Independent Agent"
Pass 3:  independent qa-quality agent → skip to "Spawn Pass 3 Independent Agent"
synthesis: main session only → follow "Central Synthesis Rules"
```

**The main session is the ONLY writer of:**
- `.samvil/qa-report.md`
- `project.state.json`
- `.samvil/events.jsonl`
- overall verdict

Independent agents gather evidence only. They do not write files.

### Spawn Pass 2 Independent Agent

```
Agent(
  description: "SAMVIL QA Pass 2: independent functional verification",
  model: config.model_routing.qa || config.model_routing.default || "sonnet",
  prompt: "You are an independent QA judge for SAMVIL Pass 2.

<paste agents/qa-functional.md>

## Context
- Tech Stack: <paste seed.tech_stack only>
- Features + ACs: <paste seed.features with acceptance_criteria only>
- Constraints: <paste seed.constraints only>
- Full Seed: Read project.seed.json if you need additional context.
- Project path: ~/dev/<seed.name>/
- Dev server: http://localhost:3000 (already running)

## Task
Verify every acceptance criterion using Playwright MCP runtime testing.
Use browser_snapshot to find elements, browser_type/browser_click to interact, browser_snapshot to verify results.
Take screenshots of each AC result (save to .samvil/qa-evidence/).
Fall back to Grep/Read only for backend-only or non-UI logic.
You did not write this code.
Do not write files.
Return a markdown section using the required output format.",
  subagent_type: "general-purpose"
)
```

### Spawn Pass 3 Independent Agent

```
Agent(
  description: "SAMVIL QA Pass 3: independent quality verification",
  model: config.model_routing.qa || config.model_routing.default || "sonnet",
  prompt: "You are an independent QA judge for SAMVIL Pass 3.

<paste agents/qa-quality.md>

## Context
- Tech Stack: <paste seed.tech_stack only>
- Screens: <paste blueprint.screens only>
- Constraints: <paste seed.constraints only>
- Full Seed: Read project.seed.json if you need additional context.
- Project path: ~/dev/<seed.name>/

## Task
Review responsive design, accessibility basics, code structure, and UX polish.
You did not write this code.
Do not write files.
Return a markdown section using the required output format.",
  subagent_type: "general-purpose"
)
```

### Central Synthesis Rules

After both independent agents return their markdown evidence:

1. Read Pass 1 result from main-session checks
2. Read Pass 2 markdown returned by independent agent
3. Read Pass 3 markdown returned by independent agent
4. Apply verdict matrix from `references/qa-checklist.md`
5. Write `.samvil/qa-report.md`
6. **MCP (best-effort):** Emit all QA events via `mcp__samvil_mcp__save_event` (see Event Log section)
7. Update `project.state.json` (only completed_features, failed, qa_history — NOT current_stage, which MCP manages)

---

## Pass 2: Functional Verification (Runtime-first)

Dev server should still be running from Pass 1b. If not:
```bash
cd ~/dev/<seed.name> && npm run dev &
```

### Runtime Verification with Playwright MCP

For **EACH** item in `seed.acceptance_criteria`:

1. **Understand the AC** — What user action would prove this criterion?
2. **Navigate to the right page** — Use `browser_navigate` to the relevant route
3. **Capture current state** — Use `browser_snapshot` (accessibility tree) to see available elements
4. **Perform the action** — `browser_type` to fill inputs, `browser_click` to press buttons
5. **Wait if needed** — `browser_wait_for` for dynamic content (max 3 seconds)
6. **Verify the result** — `browser_snapshot` to confirm the expected outcome appeared in the DOM
7. **Screenshot evidence** — `browser_take_screenshot` for the AC result (save to `.samvil/qa-evidence/`)

**Example flows:**

```
AC: "User can add a new todo"
→ browser_snapshot → find input[role="textbox"]
→ browser_type(ref="input-ref", text="QA test todo")
→ browser_click the submit button
→ browser_wait_for(text="QA test todo")
→ browser_snapshot → confirm "QA test todo" in list → PASS

AC: "Completed todos are visually distinct"
→ browser_snapshot → find todo items
→ browser_click a todo's checkbox
→ browser_snapshot → confirm strikethrough or checked state → PASS

AC: "Empty state shows helpful message"
→ browser_navigate to a page with no items
→ browser_snapshot → check for "no items" text → PASS
```

### Fallback to Static Analysis

If Playwright MCP is unavailable OR an AC cannot be verified via browser interaction
(e.g., backend-only logic, webhook handling, email sending):

1. Use Grep/Read to search the codebase for implementing code
2. Verify the implementation is reachable (imported and rendered)
3. Mark as PARTIAL with `"reason": "runtime_unverifiable"` instead of PASS

### Stop Dev Server

After all ACs are verified, stop the dev server:
```bash
kill $(lsof -ti:3000) 2>/dev/null
```

### Verdict

Rate each criterion: **PASS** / **FAIL** / **PARTIAL** / **UNIMPLEMENTED**

**Verdict Taxonomy (v0.3.2 통일):**

| Verdict | 점수 | 의미 | 예시 |
|---------|------|------|------|
| **PASS** | 1.0 | AC 완전 충족 | 런타임에서 실제 동작 확인 + 스크린샷 증거 |
| **PARTIAL** | 0.5 | 런타임 검증 불가, 코드는 존재 | Playwright 접근 불가, 백엔드 로직, 비동기 타이밍 |
| **UNIMPLEMENTED** | 0.0 | stub/하드코딩/더미 | API 하드코딩 응답, simulated data, TODO 주석 |
| **FAIL** | 0.0 | 런타임에서 동작하지 않음 | 버튼 클릭해도 반응 없음, 에러 발생, 엣지케이스 미처리 |

**UNIMPLEMENTED 세부 규칙:**
- API/AI 호출이 stub(하드코딩 응답, simulated response)이면 → **UNIMPLEMENTED**
- seed의 core_experience에 언급된 기능이 stub → **자동 FAIL로 승격**
- "expected for v1"으로 면죄부 주지 않음. out_of_scope는 seed에 명시된 것만 인정.

**PARTIAL 세부 규칙:**
- PARTIAL은 **해당 AC에 대해 0.5점**. FAIL이 아님.
- PARTIAL ≥ 3개면 → Pass 3 Quality에서 CONCERN으로 표시 (REVISE 트리거 아님)
- Evolve auto-trigger 조건으로 활용 (partial_count ≥ 5 → Evolve 제안)

**If any criterion is FAIL or UNIMPLEMENTED:** Verdict = REVISE with the failing criteria listed.

## Pass 3: Quality Verification (minimal inline path)

Check by reading relevant code:
- **Responsive**: Tailwind responsive classes (`md:`, `lg:`) used for layout components
- **Accessibility**: Interactive elements are `<button>`/`<a>` (not `<div onClick>`), have labels or `aria-label`
- **Code structure**: Components in `components/`, lib in `lib/`
- **Empty states**: Lists/collections handle zero items (check this FIRST — most commonly missing)
- **Error states**: User-facing error messages are helpful (not raw error objects)
- **No debug code**: No console.log left in components
- **Performance**: First Load JS < 100KB (check build output). Use INP < 200ms as target metric.

**CONCERN 규칙**: 성능 CONCERN(First Load > 100KB 등)이 있으면 CONCERN으로만 표시하지 말고 **REVISE로 처리**. CONCERN은 무시되기 쉬움 — 발견했으면 수정해야 함.

**If critical quality issues or any CONCERN:** Verdict = REVISE with specific issues.

## Write QA Report

Write results to `~/dev/<seed.name>/.samvil/qa-report.md`:

```markdown
# QA Report — Iteration <N>

## Pass 1: Mechanical
- Build: PASS/FAIL

## Pass 2: Functional (Runtime)
| AC | Verdict | Method | Notes |
|----|---------|--------|-------|
| "<criterion>" | PASS | runtime | <what was tested + screenshot path> |
| "<criterion>" | PARTIAL | static | <why runtime unverifiable> |

## Pass 3: Quality
- Responsive: PASS/FAIL
- Accessibility: PASS/FAIL
- Code structure: PASS/FAIL

## Overall: PASS / REVISE / FAIL
Issues to fix:
- <issue 1>
- <issue 2>
```

## Verdict

Apply the verdict matrix from `references/qa-checklist.md`:

```
[SAMVIL] Stage 5/5: QA Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pass 1 (Mechanical): PASS ✓ / FAIL ✗
Pass 2 (Functional):
  - "<AC 1>" → PASS ✓
  - "<AC 2>" → FAIL ✗
  ...
Pass 3 (Quality): PASS ✓ / FAIL ✗

Overall Verdict: PASS / REVISE / FAIL
```

## Event Log (MCP 필수)

After writing QA Report, use MCP to save all events:

For each Pass 2 item marked **PARTIAL**:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="qa_partial", stage="qa", data='{"criterion":"<AC>","reason":"<brief>","source":"pass2"}')
```

For each Pass 2 item marked **UNIMPLEMENTED**:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="qa_unimplemented", stage="qa", data='{"criterion":"<AC>","reason":"<brief>","is_core_experience":<true|false>}')
```

Pass 3 concerns that are evidence-limited may also emit `qa_partial` with `"source":"pass3"`.

Final verdict event (always emitted):
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="qa_verdict", stage="qa", data='{"verdict":"<PASS|REVISE|FAIL>","iteration":<N>,"pass1":"<PASS|FAIL>","pass2":"<PASS|FAIL>","pass3":"<PASS|FAIL>"}')
```

**Event ownership:** Independent QA agents (if spawned) never emit events directly. The main session emits all QA events after synthesizing returned evidence.

## Ralph Loop (if REVISE)

If verdict is REVISE:

1. List the specific issues that need fixing
2. **Fix them directly** — read the error, write the fix, build verify:
   ```bash
   cd ~/dev/<seed.name>
   npm run build > .samvil/build.log 2>&1
   ```
   Circuit breaker: MAX_RETRIES=2 per fix attempt
3. Re-run all 3 QA passes
4. Update `qa_history` in `project.state.json`:
   ```json
   { "iteration": 1, "verdict": "REVISE", "issues": ["..."] }
   ```
5. **MAX_ITERATIONS = config.qa_max_iterations || 3**: After MAX_ITERATIONS REVISE cycles → verdict = FAIL

**Convergence check:** Each iteration MUST reduce total issue count compared to previous iteration.

**BLOCKED detection (PHI-04):** Compare issue lists across iterations:
- Extract issue identifiers from each iteration's `qa_history` entry
- If **identical issues persist for 2 consecutive iterations** → declare **BLOCKED**

Example:
```
Cycle 1: [A, B, C, D]
Cycle 2: [A, B, C, E]     ← D resolved, E new
Cycle 3: [A, B, C, F]     ← E resolved, F new
→ A, B, C cannot be auto-fixed.
```

On BLOCKED:
```
[SAMVIL] ✗ QA BLOCKED after iteration <N>
  Persistent issues that auto-fix cannot resolve:
    - <issue A>
    - <issue B>
    - <issue C>

  Manual intervention required. Options:
  1. Evolve seed — change the spec to avoid these issues
  2. Skip to retro — end this run with analysis
  3. Fix manually — the app is at ~/dev/<seed.name>/
```

**MCP (best-effort):** Emit BLOCKED event:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="qa_blocked", stage="qa", data='{"iteration":<N>,"persistent_issues":["<A>","<B>","<C>"],"total_attempts":<N>}')
```

## On PASS — Offer Evolve or Chain to Retro (INV-4)

```
[SAMVIL] ✓ QA Passed!
  All acceptance criteria met.
  Build: clean
  Quality: acceptable

  Try it: cd ~/dev/<seed.name> && npm run dev

  배포 방법:
  1. Vercel (추천): cd ~/dev/<seed.name> && npx vercel
  2. Railway: GitHub 연동 후 자동 배포 (Dockerfile 자동 감지)
  3. 수동: npm run build && npm start (standalone output 지원)

  배포 전 체크리스트:
  □ .env.local에 실제 API 키 설정
  □ Supabase 프로젝트 생성 + URL/KEY 입력 (Supabase 선택 시)
  □ npm run dev 로 최종 확인
  □ 모바일에서 반응형 확인
```

**런칭 준비 리포트**: `.samvil/launch-checklist.md`에 저장:
- 필요한 환경변수 목록 (.env.example 기반)
- 배포 명령어 (Vercel/Railway)
- Supabase 설정 가이드 (해당 시)

**스킵된 단계 표시**: Evolve를 스킵하는 경우:
```
[SAMVIL] Evolve: SKIPPED (quality score 충족)
```

**Auto-trigger 체크 (v0.3.2):** state.json에서 확인:
- build_retries ≥ 5 → Evolve 제안
- qa_history.length ≥ 2 → Evolve 제안
- partial_count ≥ 5 → Evolve 제안

If any auto-trigger condition is met:

```
QA passed, but quality could improve. Want to evolve the seed? (yes / no)
```

- **yes**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="evolve", data='{"reason":"quality_improvement"}')` → invoke `samvil-evolve`
- **no**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="retro", data='{"reason":"qa_pass"}')` → invoke `samvil-retro`

If QA Pass 3 all dimensions ≥ 4/5: skip evolve offer, go directly to retro:
  **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="retro", data='{"reason":"quality_excellent"}')`
  Invoke the Skill tool with skill: `samvil-retro`

## On FAIL (after 3 iterations)

```
[SAMVIL] ✗ QA Failed after 3 iterations
  Remaining issues:
    - <issue 1>
    - <issue 2>

  Options:
  1. Evolve seed — the spec might be the problem, not the code
  2. Skip to retro — end this run, analyze what went wrong
  3. Fix manually — the app is at ~/dev/<seed.name>/
```

- **Option 1**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="evolve", data='{"reason":"qa_fail_evolve"}')` → invoke `samvil-evolve`
- **Option 2**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="retro", data='{"reason":"qa_fail"}')` → invoke `samvil-retro`
- **Option 3**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="retro", data='{"reason":"manual_fix"}')` → invoke `samvil-retro`

## Rules

1. **Strict on Pass 1.** Build must pass. No exceptions.
2. **Fair on Pass 2.** PARTIAL counts as 0.5 (not a FAIL). Only FAIL and UNIMPLEMENTED trigger REVISE.
3. **Lenient on Pass 3.** Flag issues but don't FAIL for cosmetic problems alone.
4. **Fix during Ralph loop, don't rebuild from scratch.**
5. **All build output to .samvil/build.log (INV-2).**

**TaskUpdate**: "QA" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
- On PASS: Invoke the Skill tool with skill: `samvil-retro` (or `samvil-evolve` if quality < 4/5)
- On FAIL: User chooses evolve, retro, or manual fix

### Codex CLI (future)
Read the appropriate next skill's SKILL.md based on verdict.
