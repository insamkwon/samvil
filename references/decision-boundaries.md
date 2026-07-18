# SAMVIL Decision Boundaries (numeric thresholds)

> Single source of truth for SAMVIL's quantitative decision rules.
> Used by MCP tools to make pipeline decisions and by humans to audit
> them. All numeric thresholds that gate stage transitions live here.
>
> Implements P3 (Decision Boundary): "충분함을 숫자로 명시. 감으로 결정 금지."

## Quick reference

| 단계 | 종료 조건 |
|------|----------|
| Interview | `ambiguity_score ≤ samvil_tier 임계값` |
| Build | `npm run build` 성공 + typecheck 통과 |
| QA | 3-pass 모두 PASS + evidence 존재 |
| Evolve 수렴 | `similarity ≥ 0.95` + `regression == 0` + 5 evolve_checks 통과 |
| Circuit Breaker | 동일 실패 2회 연속 |
| Stall Detection | 5분간 이벤트 없음 |
| Rhythm Guard | AI 자동답변 3회 연속 → 다음은 강제 사용자 개입 |

Per-section detail follows. Constants here MUST stay in lockstep with
the implementations cited under each section.

---

## Interview termination

Interview converges when `ambiguity_score` ≤ tier threshold, component floors
pass, and `min_questions_reference` is met. `max_questions` is a forced cap:
reaching it before convergence must offer draft-or-extend instead of silently
looping. Explicit extension adds 5 questions.

| `samvil_tier` | `ambiguity_score` 임계값 | `min_questions_reference` | `max_questions` |
|---|---|---|---|
| `minimal` | 0.10 | 5 | 6 |
| `standard` | 0.05 | 10 | 12 |
| `thorough` | 0.02 | 20 | 20 |
| `full` | 0.01 | 30 | 30 |
| `deep` | 0.005 | 40 | 40 |

**Current implementation:** `mcp/samvil_mcp/interview_engine.py`
(`TIER_TARGETS`, `MIN_QUESTIONS`, `MAX_QUESTIONS`, `score_ambiguity`).
`mcp/samvil_mcp/interview_v3_2.py` owns `interview_level`-aware
(quick/normal/deep/max/auto) selection.

**Why:** higher tier ⇒ more rigor ⇒ tighter ambiguity tolerance. Below
the threshold the residual ambiguity is acceptable for the chosen level
of robustness.

---

## Build success

**Rule:** A build PASS requires *all* of the following on the project
root:

1. `npm run build` exits 0 (logged to `.samvil/build.log` per INV-2).
2. TypeScript type-check passes (`tsc --noEmit` for TS projects).
3. No new `next-config.mjs` warnings classified as `error` severity.
4. For automation/CLI projects, the entry-point script imports cleanly.

**Implementation:** `mcp/samvil_mcp/build_runner.py` and the per-stack
adapters under `mcp/samvil_mcp/scaffold/*`.

**Failure handling:** On failure, the orchestrator routes to QA-recovery
(see `references/samvil-ssot-schema.md` Layer 2). Two consecutive
failures trip the Circuit Breaker.

---

## QA pass

**Rule:** QA returns `PASS` only when **all three passes** complete:

| Pass | Verifies | Required artifact |
|---|---|---|
| 1a Mechanical | build / lint / typecheck | `.samvil/build.log` exit 0 |
| 1b Smoke (web) or API connectivity (automation) | runtime starts cleanly | screenshot or HTTP 2xx evidence |
| 2 Acceptance | every leaf AC has file:line evidence | `qa-results.json` with `evidence[]` non-empty per leaf |
| 3 Independent | a separate verifier confirms Pass 2 | independent claim posted via `claim_post` |

**Evidence requirement (P1):** every PASS verdict at any pass level MUST
include at least one `file:line` evidence entry. PASS without evidence
is auto-converted to FAIL by `mcp/samvil_mcp/validate_evidence.py`.

**Reward-hacking guard (E1):** stub / mock / hard-coded shortcuts are
detected by `mcp/samvil_mcp/scaffold_sanity.py`; positive detection
forces FAIL regardless of evidence.

**Iteration cap:** `qa_max_iterations = 3` (Ralph loop; introduced
v0.8.0). Beyond 3 iterations the loop yields to user.

---

## Evolve convergence

**Rule:** A cycle is `CONVERGED` when **all** of the following hold:

| Check | Threshold | Implementation |
|---|---|---|
| Similarity to prior generation | `≥ 0.95` | `mcp/samvil_mcp/compare_seeds.py` |
| Regression count | `== 0` | `mcp/samvil_mcp/convergence_check.py` (regression detector) |
| `evolve_checks` (5 total, see below) | all PASS | `mcp/samvil_mcp/convergence_check.py` (gates) |

The five `evolve_checks`:

1. **Goal alignment** — new seed still serves the original `vision`.
2. **AC tree integrity** — no leaf orphaned, no branch lost.
3. **Evidence preservation** — prior PASS evidence still resolvable.
4. **Manifest delta sanity** — new `.samvil/manifest.json` matches
   declared file moves.
5. **Decision log continuity** — every changed AC links to an ADR or
   `claim` justification.

**Anti-pattern (P5):** *Blind convergence* — declaring CONVERGED while
even one of the five `evolve_checks` fails — is forbidden.

---

## Circuit Breaker

**Rule:** `MAX_RETRIES = 2`. After two **consecutive identical-cause
failures** at the same stage, the orchestrator stops the chain and
hands off to the user with a structured failure report.

- Identical-cause is hashed from the failure signature (error class +
  top-of-stack frame + first 80 chars of message).
- Different failures reset the counter.

**Implementation:** `mcp/samvil_mcp/circuit_breaker.py` (event-derived
counter via `events.jsonl`).

---

## Stall Detection

**Rule:** A stage is `STALLED` when no event of any type has been
appended to `.samvil/events.jsonl` for **5 minutes** while the stage is
marked active in `state.json`.

**Recovery:** `mcp/samvil_mcp/heartbeat_state.py` exposes `reawake`,
which posts a `stage_reawake` event and resets the timer. Three
re-awakes without progress promotes to Circuit Breaker.

**Implementation:** `is_state_stalled` MCP tool (introduced v3.1.0,
v3-016).

---

## Rhythm Guard

**Rule:** Three consecutive AI-authored answers without user input on a
question marked `decision-class: user` (per Jurisdiction module) forces
the next prompt back to the user. AI cannot self-answer four in a row
on user-jurisdiction items.

**Why (P2):** prevents AI from accidentally deciding business questions
the user owns. Implemented in `mcp/samvil_mcp/jurisdiction.py` plus the
`update_answer_streak` MCP tool.

---

## Performance budget (v3.2 Sprint 6)

Per-tier wall-clock budgets warn at 80% and hard-stop at 150% of the
declared budget for the stage. Consensus rounds are exempt.

**Implementation:** `mcp/samvil_mcp/performance_budget.py`,
defaults in `references/performance_budget.defaults.yaml`.

---

## Compliance

If you change any number in this file, also:

1. Update the matching constant in the implementation file cited under
   each section.
2. Add a regression test that exercises the new threshold.
3. Run `bash scripts/pre-commit-check.sh` and ensure green.
4. Note the change in `CHANGELOG.md` under the next release.
