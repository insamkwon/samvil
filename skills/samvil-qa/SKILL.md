---
name: samvil-qa
description: "3-pass verification against seed acceptance criteria. Ralph loop for auto-fix. Verdict: PASS/REVISE/FAIL."
---

# SAMVIL QA — 3-Pass Verification

You are adopting the role of **QA Judge**. Verify the built app against the seed spec.

## Boot Sequence (INV-1)

1. Read `project.seed.json` → acceptance criteria and features
2. Read `project.state.json` → completed features, failed features, qa_history
3. Read `references/qa-checklist.md` from this plugin directory

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

**If Pass 1 fails:** Verdict = REVISE with specific build errors. Skip Pass 2 and 3.

## Pass 2: Functional Verification

For **EACH** item in `seed.acceptance_criteria`:

1. Use Grep/Read to search the codebase for code implementing this criterion
2. Verify the implementation is reachable (imported and rendered)
3. Check edge case: empty state handled?

Rate each criterion: **PASS** / **FAIL** / **PARTIAL**

**PARTIAL rule:** Items that cannot be verified by code reading alone (CSS visual correctness, async timing, drag-and-drop feel, hydration mismatch) should be marked PARTIAL with reason. PARTIAL counts as 0.5 in verdict — not a full FAIL.

**If any criterion is FAIL:** Verdict = REVISE with the failing criteria listed.

## Pass 3: Quality Verification

Check by reading relevant code:
- **Responsive**: Tailwind responsive classes (`md:`, `lg:`) used for layout components
- **Accessibility**: Interactive elements are `<button>`/`<a>` (not `<div onClick>`), have labels or `aria-label`
- **Code structure**: Components in `components/`, lib in `lib/`
- **Empty states**: Lists/collections handle zero items (check this FIRST — most commonly missing)
- **Error states**: User-facing error messages are helpful (not raw error objects)
- **No debug code**: No console.log left in components
- **Performance**: First Load JS < 100KB (check build output). Use INP < 200ms as target metric.

**If critical quality issues:** Verdict = REVISE with specific issues.

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
5. **MAX_ITERATIONS = 3**: After 3 REVISE cycles → verdict = FAIL

**Convergence check:** Each iteration MUST fix more issues than it introduces. If not converging → FAIL.

## On PASS — Offer Evolve or Chain to Retro (INV-4)

```
[SAMVIL] ✓ QA Passed!
  All acceptance criteria met.
  Build: clean
  Quality: acceptable

  Try it: cd ~/dev/<seed.name> && npm run dev
```

If QA Pass 3 noted quality improvements (score < 4/5 on any dimension):

```
QA passed, but quality could improve. Want to evolve the seed? (yes / no)
```

- **yes**: Update state `current_stage` to `"evolve"`, invoke `samvil:evolve`
- **no**: Update state `current_stage` to `"retro"`, invoke `samvil:retro`

If QA Pass 3 all dimensions ≥ 4/5: skip evolve offer, go directly to retro.

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

- **Option 1**: Update state `current_stage` to `"evolve"`, invoke `samvil:evolve`
- **Option 2**: Update state `current_stage` to `"retro"`, invoke `samvil:retro`
- **Option 3**: Update state `current_stage` to `"retro"`, invoke `samvil:retro`

## Rules

1. **Strict on Pass 1.** Build must pass. No exceptions.
2. **Fair on Pass 2.** PARTIAL is a FAIL for that criterion.
3. **Lenient on Pass 3.** Flag issues but don't FAIL for cosmetic problems alone.
4. **Fix during Ralph loop, don't rebuild from scratch.**
5. **All build output to .samvil/build.log (INV-2).**
