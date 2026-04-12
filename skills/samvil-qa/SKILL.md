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
5. **Follow `references/boot-sequence.md`** for metrics start/end and checkpoint rules.

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

## Incremental QA — 변경된 Feature만 재검증

### QA 결과 캐시 (.samvil/qa-results.json)

이전 QA 결과를 저장하여 변경 없는 feature의 재검증을 생략:

**캐시 파일 포맷** (`.samvil/qa-results.json`):
```json
{
  "_meta": {
    "seed_version": "<seed.version>",
    "seed_hash": "<features 해시>",
    "last_full_qa": "2025-01-01T00:00:00Z",
    "total_iterations": 3
  },
  "features": {
    "feature_name_1": {
      "status": "PASS",
      "timestamp": "2025-01-01T12:00:00Z",
      "seed_hash": "abc123def456",
      "ac_results": [
        { "criterion": "AC 설명", "verdict": "PASS", "method": "runtime" }
      ]
    },
    "feature_name_2": {
      "status": "FAIL",
      "timestamp": "2025-01-01T12:00:00Z",
      "seed_hash": "abc123def456",
      "ac_results": [
        { "criterion": "AC 설명", "verdict": "FAIL", "method": "runtime", "issue": "버튼 클릭 불가" }
      ]
    }
  }
}
```

### 증분 QA 실행 로직

1. **qa-results.json 읽기** (존재하는 경우)
2. **seed diff 계산** — 이전 seed_hash와 현재 seed_hash 비교
3. **변경된 feature 추출**:
   ```bash
   cd ~/dev/<seed.name>
   # 현재 features 해시
   node -e "
   const crypto = require('crypto');
   const seed = require('./project.seed.json');
   const features = seed.features || [];
   features.forEach(f => {
     const hash = crypto.createHash('sha256')
       .update(JSON.stringify(f)).digest('hex').slice(0, 12);
     console.log(f.name + '|' + hash);
   });
   "
   ```
4. **이전 결과와 비교** — 각 feature의 seed_hash가 동일하면 이전 결과 재사용
5. **재검증 대상만 Pass 1~3 실행**

### 증분 QA 출력

```
[SAMVIL] 증분 QA 모드
  이전 QA 결과: .samvil/qa-results.json
  전체 feature: N개
  변경 감지: M개 (재검증)
  변경 없음: K개 (이전 결과 재사용)

  재검증 대상:
    - feature_A (seed 변경)
    - feature_B (이전 FAIL)

  재사용 (스킵):
    - feature_C: PASS (2025-01-01T12:00:00Z)
    - feature_D: PASS (2025-01-01T12:00:00Z)
```

### 전체 재검증 (--full-qa)

사용자가 전체 재검증을 요청한 경우:
```
[SAMVIL] 전체 QA 모드 (--full-qa)
  모든 feature 재검증
```

전체 재검증 조건:
- 사용자가 명시적으로 `--full-qa` 요청
- seed.version이 변경됨 (메이저/마이너 버전업)
- `.samvil/qa-results.json`이 손상되었거나 없음
- 이전 QA에서 overall FAIL이었던 경우

### QA 결과 갱신

QA 완료 후 `.samvil/qa-results.json` 갱신:
1. 재검증한 feature의 결과 업데이트
2. 재사용한 feature는 타임스탬프 유지
3. `_meta.last_full_qa` 업데이트 (전체 QA 시에만)
4. `_meta.total_iterations` 증가

## Pass 1: Mechanical Verification

### web-app

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

### automation

**Python:**
```bash
cd ~/dev/<seed.name>
source .venv/bin/activate
python -m py_compile src/main.py > .samvil/build.log 2>&1
python -m py_compile src/processor.py >> .samvil/build.log 2>&1
python -m py_compile src/config.py >> .samvil/build.log 2>&1
echo "Compile exit code: $?"
pip check >> .samvil/build.log 2>&1
echo "Dependency check exit code: $?"
```

**Node:**
```bash
cd ~/dev/<seed.name>
npx tsc --noEmit > .samvil/build.log 2>&1
echo "TypeScript check exit code: $?"
npm ls >> .samvil/build.log 2>&1
echo "Dependency check exit code: $?"
```

**CC skill:** No compilation step. Skip to Pass 2.

Check:
- `py_compile`/`tsc` exits with code 0 (no syntax/type errors)
- `pip check`/`npm ls` reports no dependency conflicts
- No import errors in output

**If Pass 1 fails:** Verdict = REVISE with specific errors. Skip Pass 2 and 3.

## Pass 1b: Playwright Smoke Run (빌드 통과 후)

### web-app

Build가 성공하면 Playwright로 dev server를 띄워서 콘솔 에러와 빈 화면을 검출:

```bash
cd ~/dev/<seed.name>
```

### Playwright 설치 확인 (최초 1회)
```bash
npx playwright install chromium 2>/dev/null
```

### 증거 디렉토리 준비
```bash
mkdir -p ~/dev/<seed.name>/.samvil/qa-evidence
```

### Playwright MCP 연결 안정화

모든 Playwright 호출에 다음 규칙 적용:

- **Timeout**: 기본 30초. `project.config.json`의 `playwright_timeout`으로 설정 가능 (단위: ms).
- **Retry**: 최대 2회, exponential backoff (1초 → 2초).
- **연결 실패 로깅**: Playwright MCP 호출 시 에러가 발생하면, fallback 전에 반드시 에러 내용을 콘솔에 명시적 출력:
  ```
  [SAMVIL] ⚠ Playwright MCP error: <error message>
  [SAMVIL] Retrying (attempt N/2)...
  ```
- **Fallback 전환**: 2회 재시도 후에도 실패 시:
  ```
  [SAMVIL] ⚠ Playwright MCP unavailable after 2 retries.
  [SAMVIL] Falling back to static analysis (제한적 검증).
  ```
  이후 정적 분석(Grep/Read)으로 전환. QC 리포트에 `Method: static (Playwright unavailable)`로 기록.

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

5. **Take screenshot for evidence:**
   ```
   mcp__plugin_playwright_playwright__browser_take_screenshot(type="png", filename=".samvil/qa-evidence/smoke-desktop-pass.png")
   ```

6. **Visit each route** from `blueprint.routing`:
   For each route, navigate and check for console errors + non-empty body.

7. **Keep dev server running** — Pass 2 needs it for runtime verification.
   Dev server stays up through Pass 2 and is stopped after Pass 2 completes.

**Verdict:**
- All routes: no console errors + non-empty body → PASS → Pass 2로 진행
- Any route: console errors OR empty body → REVISE with specific issues

### automation

Automation 프로젝트는 Playwright Smoke Run을 스킵합니다. 대신 dry-run 테스트를 실행:

```bash
# Python
cd ~/dev/<seed.name>
source .venv/bin/activate
python src/main.py --dry-run > .samvil/dry-run-output.json 2> .samvil/dry-run-stderr.log
echo "Dry-run exit code: $?"

# Node
cd ~/dev/<seed.name>
npx tsx src/main.ts --dry-run > .samvil/dry-run-output.json 2> .samvil/dry-run-stderr.log
echo "Dry-run exit code: $?"
```

Check:
- Exit code is 0
- Output is valid JSON
- stderr does not contain real API URLs (no actual API calls in dry-run)

**If dry-run fails:** Verdict = REVISE. Skip Pass 2 and 3.

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

### web-app

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

### Pass 2-A: 렌더링 검증

모든 주요 라우트에 대해 다음 항목 검증:

1. **빈 화면 감지**:
   ```
   mcp__plugin_playwright_playwright__browser_evaluate(function="() => document.body.innerHTML.trim().length > 50")
   ```
   - 50자 미만이면 빈 화면으로 간주 → FAIL

2. **콘솔 에러 감지**:
   ```
   mcp__plugin_playwright_playwright__browser_console_messages(level="error")
   ```
   - React hydration 에러, chunk load 실패, undefined reference 등 치명적 에러만 FAIL 처리
   - CORS 경고, deprecated API 경고는 CONCERN으로 기록 (FAIL 아님)

3. **주요 텍스트/버튼 존재 확인**:
   - `browser_snapshot`으로 accessibility tree 확인
   - 각 페이지의 heading (h1, h2)이 존재하는지 확인
   - 주요 CTA 버튼(role="button" 또는 `<a>` 태그)이 존재하는지 확인
   - 누락 시 해당 AC에 대해 FAIL

### Pass 2-B: 상호작용 검증

AC에 상호작용이 포함된 경우 다음 검증 수행:

1. **주요 버튼 클릭 가능**:
   ```
   mcp__plugin_playwright_playwright__browser_click(ref="<button-ref>")
   ```
   - 클릭 후 `browser_snapshot`으로 변화 확인
   - 클릭해도 아무 반응 없으면 FAIL

2. **폼 제출 동작**:
   - 입력 필드에 `browser_type`으로 값 입력
   - 제출 버튼 `browser_click`
   - 제출 후 결과 확인: 성공 메시지, 에러 메시지, 또는 페이지 전환
   - 폼 제출 후 아무 피드백 없으면 FAIL

3. **네비게이션 동작**:
   - 링크/탭 클릭 후 `browser_navigate` 결과 확인
   - 404 페이지 또는 에러 페이지로 이동 시 FAIL
   - SPA 라우팅: URL 변경 + 콘솔 에러 없음 확인

### Pass 2-C: 반응형 검증

3개 뷰포트에서 레이아웃 확인:

```
viewports = [
  { name: "mobile",  width: 375,  height: 812 },
  { name: "tablet",  width: 768,  height: 1024 },
  { name: "desktop", width: 1280, height: 720 }
]
```

각 뷰포트마다:
1. **뷰포트 전환**:
   ```
   mcp__plugin_playwright_playwright__browser_resize(width=<width>, height=<height>)
   ```

2. **스크린샷 캡처**:
   ```
   mcp__plugin_playwright_playwright__browser_take_screenshot(
     type="png",
     filename=".samvil/qa-evidence/<feature>-<viewport>-pass.png"
   )
   ```
   - FAIL 시 파일명: `<feature>-<viewport>-fail.png`

3. **레이아웃 확인**:
   - 가로 스크롤 발생 여부 (mobile에서 `overflow-x` 체크)
   - 텍스트 오버플로우 (잘린 텍스트, 겹침)
   - 버튼/링크 터치 영역 (mobile에서 최소 44x44px)
   - 중요 콘텐츠가 뷰포트 밖으로 밀려나지 않았는지 확인

4. **desktop 뷰포트로 복원** (후속 테스트를 위해):
   ```
   mcp__plugin_playwright_playwright__browser_resize(width=1280, height=720)
   ```

**반응형 검증 결과**: 치명적 레이아웃 깨짐(콘텐츠 접근 불가)만 FAIL. 사소한 정렬 문제는 CONCERN.

### Fallback to Static Analysis

If Playwright MCP is unavailable (연결 안정화에서 2회 재시도 후에도 실패) OR
an AC cannot be verified via browser interaction (e.g., backend-only logic, webhook handling, email sending):

1. **명시적 경고 출력**:
   ```
   [SAMVIL] ⚠ Falling back to static analysis for: "<AC description>"
   [SAMVIL]   Reason: <Playwright unavailable | backend-only | runtime_unverifiable>
   ```

2. Use Grep/Read to search the codebase for implementing code
3. Verify the implementation is reachable (imported and rendered)
4. Mark as PARTIAL with `"reason": "runtime_unverifiable"` instead of PASS

**Fallback 결과는 "제한적 검증"으로 명시**:
- QC 리포트의 Method 컬럼에 `static (Playwright unavailable)` 또는 `static (backend-only)` 표시
- PASS 대신 PARTIAL로 처리 (정적 분석으로는 완전한 검증 불가)

### Stop Dev Server

After all ACs are verified, stop the dev server:
```bash
kill $(lsof -ti:3000) 2>/dev/null
```

### automation — Functional Verification

Automation은 Playwright 대신 `--dry-run` 실행으로 AC를 검증합니다.

**Pass 2-A: Dry-run Execution**
```bash
# Python
cd ~/dev/<seed.name>
source .venv/bin/activate
python src/main.py --dry-run 2> .samvil/qa-dry-run-stderr.log

# Node
cd ~/dev/<seed.name>
npx tsx src/main.ts --dry-run 2> .samvil/qa-dry-run-stderr.log
```

Check:
- Exit code is 0
- Output is valid JSON (or expected format)
- No real API calls detected (stderr must not contain real API domains)

**Pass 2-B: Output Comparison**

For each fixture pair in `fixtures/input/` and `fixtures/expected/`:
```bash
# Run with each fixture
cd ~/dev/<seed.name>
for f in fixtures/input/*.json; do
  echo "Testing: $f"
  python src/main.py --dry-run --input "$f" 2>/dev/null
  # Compare output against fixtures/expected/<name>.expected.json
done
```

Verify:
- Each fixture input produces output matching the expected file
- Differences are flagged as FAIL

**Pass 2-C: No Real API Calls**

```bash
# Check stderr for real API calls
grep -c "api\." .samvil/qa-dry-run-stderr.log || echo "0"
grep -c "https://" .samvil/qa-dry-run-stderr.log || echo "0"
```
- 0 real API calls: PASS
- Any real API call detected: FAIL (dry-run must not hit real APIs)

**For each AC:**
- AC about processing logic → verify output matches expected
- AC about error handling → verify errors logged, not crashed
- AC about output format → verify JSON structure matches spec

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

### web-app

Check by reading relevant code:
- **Responsive**: Tailwind responsive classes (`md:`, `lg:`) used for layout components
- **Accessibility**: Interactive elements are `<button>`/`<a>` (not `<div onClick>`), have labels or `aria-label`
- **Code structure**: Components in `components/`, lib in `lib/`
- **Empty states**: Lists/collections handle zero items (check this FIRST — most commonly missing)
- **Error states**: User-facing error messages are helpful (not raw error objects)
- **No debug code**: No console.log left in components
- **Performance**: First Load JS < 100KB (check build output). Use INP < 200ms as target metric.

### Pass 3 스크린샷 증거

Playwright가 연결된 상태면 Pass 3에서도 스크린샷 캡처:
```
mcp__plugin_playwright_playwright__browser_take_screenshot(
  type="png",
  filename=".samvil/qa-evidence/quality-desktop-pass.png"
)
```
- 반응형 검증이 Pass 2-C에서 수행되지 않은 경우, 여기서 3개 뷰포트 캡처
- 파일명 규칙: `quality-<mobile|tablet|desktop>-<pass|fail>.png`

**CONCERN 규칙**: 성능 CONCERN(First Load > 100KB 등)이 있으면 CONCERN으로만 표시하지 말고 **REVISE로 처리**. CONCERN은 무시되기 쉬움 — 발견했으면 수정해야 함.

**If critical quality issues or any CONCERN:** Verdict = REVISE with specific issues.

### automation — Quality Verification

Check by reading relevant code:

- **Error handling**: Every external call (API, file I/O, DB) is wrapped in try-catch. Retry logic exists for transient errors.
- **Logging**: Structured logging at appropriate levels (INFO for milestones, WARNING for recoverable issues, ERROR for failures). No print statements in production code.
- **Configuration externalization**: All settings loaded from `.env` or environment variables. No hardcoded URLs, API keys, or file paths.
- **README**: Usage instructions included — how to install, configure, run, and dry-run.
- **Fixtures realism**: Test fixtures represent realistic data, not minimal stubs. At least 2 fixture pairs (happy path + edge case).
- **No dead code**: All modules imported and used. No commented-out code blocks.
- **Dependencies**: All pinned in requirements.txt/package.json. No `@latest` or unversioned installs.
- **Entry point**: `--dry-run` flag works correctly. `--config` flag accepts custom config path. `--output` flag works.
- **CC skill**: `SKILL.md` has all required sections (description, when to use, usage, process, output format, error handling, requirements).

**If critical quality issues:** Verdict = REVISE with specific issues.

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
- **no**: **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="deploy", data='{"reason":"qa_pass"}')` → invoke `samvil-deploy`

If QA Pass 3 all dimensions ≥ 4/5: skip evolve offer, go directly to deploy:
  **MCP (best-effort):** `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="stage_change", stage="deploy", data='{"reason":"quality_excellent"}')`
  Invoke the Skill tool with skill: `samvil-deploy`

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

## Output Format

Write `~/dev/<seed.name>/.samvil/qa-report.md` with this exact structure:

```markdown
# QA Report — Iteration <N>

## Pass 1: Mechanical
- Build: PASS/FAIL

## Pass 1b: Smoke Run
- Verification Method: Playwright / Static (Playwright unavailable)
- Console Errors: <count> errors
- Empty Pages: <list of routes or "none">

## Pass 2: Functional (Runtime)
### Verification Method: Playwright / Static (제한적 검증)

| AC | Verdict | Method | Notes |
|----|---------|--------|-------|
| "<criterion>" | PASS/PARTIAL/UNIMPLEMENTED/FAIL | runtime/static (Playwright unavailable)/static (backend-only) | <evidence + screenshot path> |

### Rendering Verification (Pass 2-A)
- Empty pages: <list or "none">
- Console errors (critical): <list or "none">
- Missing headings/buttons: <list or "none">

### Interaction Verification (Pass 2-B)
- Button clicks: <count>/<count> passed
- Form submissions: <count>/<count> passed
- Navigation: <count>/<count> routes passed

### Responsive Verification (Pass 2-C)
- Mobile (375px): PASS/FAIL — .samvil/qa-evidence/<feature>-mobile-<pass|fail>.png
- Tablet (768px): PASS/FAIL — .samvil/qa-evidence/<feature>-tablet-<pass|fail>.png
- Desktop (1280px): PASS/FAIL — .samvil/qa-evidence/<feature>-desktop-<pass|fail>.png

## Pass 3: Quality
- Responsive: PASS/FAIL (<count> components checked)
- Accessibility: PASS/FAIL (<count> issues)
- Code structure: PASS/FAIL
- Empty states: PASS/FAIL (<count> lists checked)
- Error states: PASS/FAIL
- Debug code: PASS/FAIL (<count> console.log found)
- Performance: PASS/CONCERN (First Load JS: <size>)

## Evidence
- Screenshots: `.samvil/qa-evidence/`
- Build log: `.samvil/build.log`

## Overall: PASS / REVISE / FAIL
Issues to fix:
1. <issue>
```

Console output format:
```
[SAMVIL] Stage 5/5: QA Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Verification Method: Playwright / Static (제한적 검증)

Pass 1 (Mechanical): PASS ✓ / FAIL ✗
Pass 1b (Smoke Run): PASS ✓ / FAIL ✗ — Method: Playwright/Static
Pass 2 (Functional):
  Rendering: PASS ✓ / FAIL ✗
  Interaction: PASS ✓ / FAIL ✗
  Responsive: Mobile ✓ / Tablet ✓ / Desktop ✓
  - "<AC>" -> PASS ✓ / FAIL ✗ [runtime | static]
Pass 3 (Quality): PASS ✓ / FAIL ✗
Overall Verdict: PASS / REVISE / FAIL

Evidence: .samvil/qa-evidence/
```

Screenshots saved to `.samvil/qa-evidence/` with naming convention:
- `<feature>-<viewport>-<pass|fail>.png` (per AC per viewport)
- `smoke-desktop-pass.png` (Pass 1b)
- `quality-<viewport>-<pass|fail>.png` (Pass 3)

## Anti-Patterns

1. Do NOT accept UNIMPLEMENTED for core_experience features — auto-promote to FAIL
2. Do NOT downgrade CONCERN to informational — performance CONCERN = REVISE
3. Do NOT run full `npm run build` inside worker agents — workers run lint/typecheck only

## Rules

1. **Strict on Pass 1.** Build must pass. No exceptions.
2. **Fair on Pass 2.** PARTIAL counts as 0.5 (not a FAIL). Only FAIL and UNIMPLEMENTED trigger REVISE.
3. **Lenient on Pass 3.** Flag issues but don't FAIL for cosmetic problems alone.
4. **Fix during Ralph loop, don't rebuild from scratch.**
5. **All build output to .samvil/build.log (INV-2).**

**TaskUpdate**: "QA" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
- On PASS: Invoke the Skill tool with skill: `samvil-deploy`
- On FAIL: User chooses evolve, retro, or manual fix

### Codex CLI (future)
Read the appropriate next skill's SKILL.md based on verdict.
