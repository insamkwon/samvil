# QA Checklist

## 🔑 Evidence Mandatory (v2.2.0+, P1)

**모든 PASS는 파일 증거를 동반해야 한다. 증거 없는 PASS는 자동 FAIL.**

- 각 AC 판정에 **file:line** 참조 필수 (최소 1개, 권장 2~3개)
- Tier와 무관하게 **모든 단계에서 강제**
- 증거 포맷:
  - `src/auth.ts:15` (최소)
  - `src/auth.ts:15 (zod emailSchema)` (권장 — 간단 rationale)
- Evidence 누락 시: Verdict 자동 FAIL + "No evidence provided" 경고

### 예시

```markdown
✓ AC-1 사용자 회원가입 [PASS]
  증거: src/lib/auth.ts:15 (zod emailSchema)
  증거: prisma/schema.prisma:12 (@@unique([email]))
  근거: 검증 + 중복 방지 모두 코드에서 확인

✗ AC-2 결제 [FAIL]
  증거: 없음 — "PASS"는 되었으나 실제 구현 미확인
  → Evidence-mandatory 정책에 따라 자동 FAIL
```

**구현 시점**: Phase 3 (v2.5.0)에서 QA 스킬 + MCP에 실제 검증 로직 구현.
현재 v2.2.0은 **규약 선언**만.

---

## Pass 1: Mechanical (all must pass)

- [ ] `npm run build` exits with code 0
- [ ] Zero TypeScript errors in build output
- [ ] No `any` type in core business logic (lib/, components/)
- [ ] All imports resolve (no "Module not found")

## Pass 2: Functional (check each AC)

For each `acceptance_criteria` in seed.json:

- [ ] Code exists that implements this criterion
- [ ] The implementation is reachable (not dead code, properly imported)
- [ ] Edge case: empty state handled (first-use experience)
- [ ] Edge case: if data persistence claimed, verify localStorage/DB code

Verdict per AC: **PASS** / **PARTIAL** / **UNIMPLEMENTED** / **FAIL**

| Verdict | 점수 | 의미 |
|---------|------|------|
| PASS | 1.0 | AC 완전 충족 — 실제 UI + 실제 state + reachable path |
| PARTIAL | 0.5 | 코드는 있으나 정적 분석으로 런타임 검증 불가 (CSS/UX 느낌, async timing, drag feel) |
| UNIMPLEMENTED | 0.0 | stub/하드코딩/더미/TODO — 실제 동작 불가. core_experience면 자동 FAIL 승격 |
| FAIL | 0.0 | 버그/결함/누락 — 코드가 broken, unreachable, 또는 AC와 모순됨 |

**UNIMPLEMENTED vs FAIL 구분**:
- UNIMPLEMENTED = 코드 형태는 있지만 실제로 동작하지 않음 (하드코딩, mock, TODO, sample data)
- FAIL = 코드가 broken하거나 아예 없거나 AC와 정면으로 모순됨

Overall: All PASS or PARTIAL = PASS, any UNIMPLEMENTED = REVISE, any FAIL = REVISE or FAIL

## Pass 3: Quality

- [ ] Responsive: Tailwind responsive classes (`md:`, `lg:`) used for layout
- [ ] Accessibility: Interactive elements have labels or `aria-label`
- [ ] Accessibility: Keyboard navigation works for core experience
- [ ] Code structure: Components in `components/`, lib code in `lib/`
- [ ] No hardcoded strings that should be configurable
- [ ] Loading/empty states for data-dependent components
- [ ] No console.log or debug code left in

## Verdict Matrix

| Pass 1 | Pass 2 | Pass 3 | Overall |
|--------|--------|--------|---------|
| PASS   | PASS   | PASS   | **PASS** |
| PASS   | PASS   | FAIL   | **REVISE** (quality fixes only) |
| PASS   | FAIL   | any    | **REVISE** (feature fixes) |
| FAIL   | any    | any    | **REVISE** (build fixes first) |

## Ralph Loop

- **MAX_ITERATIONS = 3**
- Each REVISE iteration targets specific issues from previous QA
- After 3 REVISE cycles without PASS: verdict = **FAIL**, report to user
- Each iteration MUST fix fewer issues than the previous. If not converging → FAIL.

## QA Report Format (.samvil/qa-report.md)

### v2.5.0+ (Evidence-mandatory 실구현 이후)

```markdown
# QA Report — Iteration N

## Pass 1: Mechanical
- Build: PASS/FAIL
- TS Errors: 0
- Evidence: .samvil/build.log:1-12

## Pass 2: Functional

### AC-1 "User can create tasks" [PASS]
  증거: src/components/CreateTask.tsx:8 (form handler)
  증거: src/lib/store.ts:22 (setTasks store)
  근거: 폼 입력 + state 반영 모두 확인

### AC-2 "AI generates summary" [UNIMPLEMENTED]
  증거 요구됨: LLM API 호출 코드
  증거 찾음: src/lib/ai.ts:5 — `return "summary here"` (하드코딩)
  근거: Reward Hacking 탐지 — 실제 API 호출 없음

### AC-3 "Tasks persist on refresh" [FAIL]
  증거 요구됨: localStorage 또는 DB 쓰기
  증거 찾음: 없음
  근거: persistence 로직 부재

## Pass 3: Quality
- Responsive: PASS (tailwind md:/lg: in app/page.tsx:12-20)
- Accessibility: PARTIAL (aria-label 일부 누락)
- Code structure: PASS

## Overall: REVISE
Issues to fix: [AC-2 real API, AC-3 add localStorage]
```

### v2.2.0~v2.4.0 (선언만, 기존 포맷 유지)

```markdown
# QA Report — Iteration N

## Pass 1: Mechanical
- Build: PASS/FAIL
- TS Errors: 0

## Pass 2: Functional
| AC | Verdict | Notes |
|----|---------|-------|
| "User can create tasks" | PASS | CreateTask component exists |

## Pass 3: Quality
- Responsive: PASS/FAIL
- Accessibility: PASS/FAIL

## Overall: PASS / REVISE / FAIL
Issues to fix: [list]
```
