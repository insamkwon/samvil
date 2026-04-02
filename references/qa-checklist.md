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

Verdict per AC: **PASS** / **FAIL** / **PARTIAL**
Overall: All PASS = PASS, any FAIL = REVISE

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
| "Tasks persist on refresh" | FAIL | No localStorage logic found |

## Pass 3: Quality
- Responsive: PASS/FAIL
- Accessibility: PASS/FAIL
- Code structure: PASS/FAIL

## Overall: PASS / REVISE / FAIL
Issues to fix: [list]
```
