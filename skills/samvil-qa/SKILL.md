---
name: samvil-qa
description: "3-pass verification against seed acceptance criteria. Ralph loop for auto-fix. Verdict: PASS/REVISE/FAIL."
---

# SAMVIL QA — 3-Pass Verification

You are adopting the role of **QA Judge**. Verify the built app against the seed spec.

## Boot Sequence (INV-1)

0. **TaskUpdate**: "QA" task를 `in_progress`로 설정
1. Read `project.seed.json` → acceptance criteria and features
2. Read `project.state.json` → completed features, failed features, qa_history
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

## Pass 1b: Smoke Run (빌드 통과 후)

Build가 성공하면 실제 dev server를 띄워서 앱이 HTTP 응답하는지 확인:

```bash
cd ~/dev/<seed.name>
npm run dev &
DEV_PID=$!
SMOKE_PASS=false
for i in {1..10}; do
  curl -s http://localhost:3000 > /dev/null 2>&1 && SMOKE_PASS=true && break
  sleep 2
done
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
kill $DEV_PID 2>/dev/null
wait $DEV_PID 2>/dev/null
echo "Smoke: $SMOKE_PASS (HTTP $HTTP_CODE)"
```

- **HTTP 200**: `[SAMVIL] Smoke Run: ✓ (HTTP 200)` → Pass 2로 진행
- **HTTP != 200 또는 timeout**: `[SAMVIL] Smoke Run: ✗ (HTTP $HTTP_CODE)` → Verdict = REVISE (빌드는 되지만 런타임 에러)

QA Report에 Smoke Run 결과 포함:
```markdown
## Pass 1b: Smoke Run
- Dev Server: PASS/FAIL (HTTP <code>)
```

## Pass 2: Functional Verification

For **EACH** item in `seed.acceptance_criteria`:

1. Use Grep/Read to search the codebase for code implementing this criterion
2. Verify the implementation is reachable (imported and rendered)
3. Check edge case: empty state handled?

Rate each criterion: **PASS** / **FAIL** / **PARTIAL** / **UNIMPLEMENTED**

**Verdict Taxonomy (v0.3.2 통일):**

| Verdict | 점수 | 의미 | 예시 |
|---------|------|------|------|
| **PASS** | 1.0 | AC 완전 충족 | 코드 존재 + 도달 가능 + 엣지케이스 처리 |
| **PARTIAL** | 0.5 | 코드는 있으나 검증 불가 | CSS/드래그앤드롭 느낌, 비동기 타이밍 — 코드 리딩만으로 확증 불가 |
| **UNIMPLEMENTED** | 0.0 | stub/하드코딩/더미 | API 하드코딩 응답, simulated data, TODO 주석 |
| **FAIL** | 0.0 | 버그/결함/누락 | 코드 없음, 런타임 에러, 엣지케이스 미처리 |

**UNIMPLEMENTED 세부 규칙:**
- API/AI 호출이 stub(하드코딩 응답, simulated response)이면 → **UNIMPLEMENTED**
- seed의 core_experience에 언급된 기능이 stub → **자동 FAIL로 승격**
- "expected for v1"으로 면죄부 주지 않음. out_of_scope는 seed에 명시된 것만 인정.

**PARTIAL 세부 규칙:**
- PARTIAL은 **해당 AC에 대해 0.5점**. FAIL이 아님.
- PARTIAL ≥ 3개면 → Pass 3 Quality에서 CONCERN으로 표시 (REVISE 트리거 아님)
- Evolve auto-trigger 조건으로 활용 (partial_count ≥ 5 → Evolve 제안)

**If any criterion is FAIL or UNIMPLEMENTED:** Verdict = REVISE with the failing criteria listed.

## Pass 3: Quality Verification

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

## Pass 2: Functional
| AC | Verdict | Notes |
|----|---------|-------|
| "<criterion>" | PASS/FAIL | <what was found/missing> |

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

## Event Log

After writing QA Report, append to `.samvil/events.jsonl`:

For each Pass 2 item marked **PARTIAL**:
```json
{"type":"qa_partial","criterion":"<AC>","reason":"<brief>","source":"pass2","ts":"<ISO 8601>"}
```

For each Pass 2 item marked **UNIMPLEMENTED**:
```json
{"type":"qa_unimplemented","criterion":"<AC>","reason":"<brief>","is_core_experience":<true|false>,"ts":"<ISO 8601>"}
```

Pass 3 concerns that are evidence-limited may also emit `qa_partial` with `"source":"pass3"`.

Final verdict event (always emitted):
```json
{"type":"qa_verdict","verdict":"<PASS|REVISE|FAIL>","iteration":<N>,"pass1":"<PASS|FAIL>","pass2":"<PASS|FAIL>","pass3":"<PASS|FAIL>","ts":"<ISO 8601>"}
```

**Event ownership:** Independent QA agents (if spawned) never append events directly. The main session emits all QA events after synthesizing returned evidence.

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

**Convergence check:** Each iteration MUST reduce total issue count compared to previous iteration. If issues increase or stay same for 2 consecutive iterations → FAIL with stagnation warning.

## On PASS — Offer Evolve or Chain to Retro (INV-4)

```
[SAMVIL] ✓ QA Passed!
  All acceptance criteria met.
  Build: clean
  Quality: acceptable

  Try it: cd ~/dev/<seed.name> && npm run dev

  다음 단계 (런칭 준비):
  □ npm run dev 로 실행 확인
  □ 환경변수 확인 (.env.local 필요 시)
  □ API 키 발급 + 설정 (외부 서비스 사용 시)
  □ 스텁→실동작 교체: <UNIMPLEMENTED 항목 목록>
  □ 모바일에서 확인 (반응형)
  □ 회고 진행 → 다음 개발 우선순위 결정
```

**런칭 준비 리포트**: `.samvil/launch-checklist.md`에 저장:
- UNIMPLEMENTED 항목별 실동작 교체 가이드
- 필요한 환경변수 목록 (.env.example 기반)
- 배포 명령어 (Vercel/Netlify 등)

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

- **yes**: Update state `current_stage` to `"evolve"`, invoke `samvil-evolve`
- **no**: Update state `current_stage` to `"retro"`, invoke `samvil-retro`

If QA Pass 3 all dimensions ≥ 4/5: skip evolve offer, go directly to retro:
  Update `project.state.json`: set `current_stage` to `"retro"`.
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

- **Option 1**: Update state `current_stage` to `"evolve"`, invoke `samvil-evolve`
- **Option 2**: Update state `current_stage` to `"retro"`, invoke `samvil-retro`
- **Option 3**: Update state `current_stage` to `"retro"`, invoke `samvil-retro`

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
