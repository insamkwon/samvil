# QA Checklist

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

```markdown
# QA Report — Iteration N

## Pass 1: Mechanical
- Build: PASS/FAIL
- TS Errors: 0

## Pass 2: Functional
| AC | Verdict | Notes |
|----|---------|-------|
| "User can create tasks" | PASS | CreateTask component exists |
| "AI generates summary" | UNIMPLEMENTED | Hardcoded sample text — needs real API |
| "Tasks persist on refresh" | FAIL | No localStorage logic found |

## Pass 3: Quality
- Responsive: PASS/FAIL
- Accessibility: PASS/FAIL
- Code structure: PASS/FAIL

## Overall: PASS / REVISE / FAIL
Issues to fix: [list]
```
