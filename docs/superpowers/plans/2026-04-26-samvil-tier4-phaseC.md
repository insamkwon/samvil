# SAMVIL Tier 4 Phase C — Hard Skill Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the 5 Hard skills (samvil/interview/scaffold/build/qa) to ultra-thin. **Most critical migration** — build/qa are SAMVIL's core value producers. End: **v4.0.0** "Consolidation milestone — all 14 skills ultra-thin."

**Architecture:** Same proven pattern from Phase A+B (single-source-of-truth aggregate MCP + SKILL.legacy.md backup + smoke tests). Difference: each skill gets **broader smoke coverage** (30+ tests target for build/qa) and **pre-migration analysis** for the most complex.

**Tech Stack:** Python 3.11+, FastMCP, pytest. No new deps. Likely 5-8 new MCP tools (1-2 per skill, +1 Pattern Registry expansion for build).

**Phase C horizon:** 12-16 weeks (estimate). Phase A/B compressed 50x — Phase C may compress similarly OR slow down due to higher complexity. Re-plan after each task.

---

## 0. Phase C Overview

| Skill | LOC | Risk | Order | Notable |
|---|---|---|---|---|
| `samvil` | 766 | Medium | **1st** | Orchestrator entry — chain logic |
| `samvil-interview` | 1259 | Medium-High | 2nd | Preset matching + question routing |
| `samvil-scaffold` | 1653 | High | 3rd | CLI scaffolder + dependency matrix |
| `samvil-build` | 1432 | **Critical** | 4th | Core value — 28 worker spawning + Pattern Registry |
| `samvil-qa` | 1713 | **Critical** | **5th** | Core value — 3-pass + Ralph loop |

**Total LOC**: 6,823 → ~750 (target -89%, Phase B achieved -82%).

**Order rationale**: Lowest-risk first (samvil orchestrator is structural). Build pattern confidence on simpler structures. Critical build/qa LAST so we have most experience by then.

**Re-planning checkpoints**: After EACH task. Especially before T4.8 (build) and T4.9 (qa) — the two highest-risk migrations.

---

## 1. Pre-flight — Smoke Test Scenarios

### S5. samvil orchestrator
- Chain entry: `/samvil "할일 앱"` → tier resolution → first stage skill (interview or pm-interview)
- Resume: state.json read → continue from last checkpoint
- Stage routing per tier (minimal skips council/design)

### S6. samvil-interview
- Preset matching from one-line prompt
- Question routing (5-path: AI auto / AI confirm / AI research / user judge / user confirm)
- Phase 2 (foundational) → 2.5 (visual) → 2.6 (non-functional) → 2.9 (lifecycle)
- Ambiguity score → tier-based termination
- Output: interview-summary.md schema

### S7. samvil-scaffold
- CLI execution (npx create-next-app, vite, astro etc.)
- Dependency matrix lookup per stack
- Sanity check (Phase A.6 from v3.1.0)
- Output: scaffolded project + tech_stack pin in seed

### S8. samvil-build (Critical)
- AC tree leaf identification
- Parallel worker spawn (MAX_PARALLEL=2)
- Per-feature dispatch (5 solution_types)
- Build log redirection (.samvil/build.log)
- Implementation rate calculation
- Stub/mock detection (Reward Hacking defense)

### S9. samvil-qa (Critical)
- 3-pass: mechanical / functional / quality
- Ralph loop (max iterations from config)
- Playwright runtime verification
- Evidence collection per AC (file:line)
- Aggregate verdict per branch (parent → child)
- Output: qa-results.json with full claim ledger

---

## 2. Pre-flight — New MCP Tools Analysis

### samvil (T4.5)
- **Likely**: `aggregate_orchestrator_state(session_id)` — boot context (state, manifest, recent decisions, current stage, next stage suggestion)
- Module: extend `orchestrator.py` (already exists from Phase 1)
- Pattern: T4.2 evolve aggregate_evolve_context

### samvil-interview (T4.6)
- **Likely 1-2**: `route_interview_question(question_text)` (already exists?), `aggregate_interview_state(state)` (boot context)
- Verify existing `interview_v3_2.py`, `path_router.py` first

### samvil-scaffold (T4.7)
- **Likely 1**: `evaluate_scaffold_target(stack)` — single source for CLI command + version pins
- Module: extend `dependency_matrix` or new `scaffold_targets.py`
- Pattern: T3.4 deploy_targets

### samvil-build (T4.8) — Critical
- **Likely 2-3**:
  - `evaluate_build_features(seed)` — feature dispatch logic
  - `aggregate_build_progress(session_id)` — progress tracking
  - Possibly `pattern_registry` expansion for new templates
- **Pre-analysis required** (separate dispatch before main migration)

### samvil-qa (T4.9) — Critical
- **Likely 2-3**:
  - `synthesize_qa_evidence` (already exists from earlier work)
  - `aggregate_qa_state` (boot)
  - `evaluate_ralph_step(prev_attempt, current_state)` — single ralph iteration logic
- **Pre-analysis required** (separate dispatch before main migration)

---

## 3. Migration Pattern (proven, with Phase C adjustments)

For each skill (Phase A/B pattern + reinforcements):

1. **(NEW for T4.8/T4.9) Pre-analysis dispatch**: separate Explore agent reads SKILL.md + dependent modules, proposes migration strategy. Controller approves before main migration.
2. **Backup**: `cp SKILL.md SKILL.legacy.md` + frontmatter rename
3. **Smoke test design**: 25+ tests for samvil/interview/scaffold, **30+ tests for build/qa**
4. **Identify roles**: orchestration → MCP, CC-specific → skill, prose → SKILL.legacy.md
5. **Add MCP tools** (if needed) with health logging + unit tests
6. **Write thin SKILL.md**: ≤150 LOC active (Phase B avg was 99 LOC)
7. **Verify**: smoke + pre-commit 9/9
8. **Commit**

---

# T4.5: samvil orchestrator Migration (Detailed)

**Files:**
- Backup: `skills/samvil/SKILL.legacy.md` (new)
- Modify: `skills/samvil/SKILL.md` (rewrite ultra-thin)
- Possibly extend: `mcp/samvil_mcp/orchestrator.py`
- Create: `mcp/tests/test_samvil_smoke.py`

## T4.5.1: Phase 1 — Baseline + behavior

- [ ] **Step 1**: Read `skills/samvil/SKILL.md` fully. Confirm 766 LOC.
- [ ] **Step 2**: List behaviors:
  - Health Check (boot)
  - Tier resolution (minimal/standard/thorough/full/deep)
  - solution_type detection (3-layer: keyword → context → interview)
  - Brownfield vs greenfield routing
  - State.json + handoff.md read
  - Resume logic (continue from checkpoint)
  - First stage chain (interview / pm-interview / analyze)
  - Skill chain via HostCapability
  - User checkpoint at key points

## T4.5.2: Phase 2 — MCP tool decision

- [ ] **Step 3**: Check existing tools (orchestrator.py from Phase 1):
  ```bash
  grep "@mcp.tool" mcp/samvil_mcp/server.py | grep -iE "session|stage|orchestr"
  ```

- [ ] **Step 4**: Decide on `aggregate_orchestrator_state` MCP tool. Pattern: T4.2 aggregate_evolve_context.

## T4.5.3: Phase 3 — Backup + smoke test

- [ ] **Step 5**: Backup with frontmatter rename to `samvil-legacy`
- [ ] **Step 6**: Write 20+ smoke tests covering tier resolution, resume, chain dispatch, brownfield routing

## T4.5.4: Phase 4 — Rewrite thin SKILL.md (~150 LOC)

## T4.5.5: Phase 5 — Verify + commit

```bash
git commit -m "refactor(skill-samvil): migrate orchestrator to ultra-thin (T4.5)"
```

---

# T4.6: samvil-interview (Outline)

> **Detailed plan after T4.5 retro.**

**Target**: 1259 → ~150 LOC
**Risk**: Medium-High (preset matching + question routing core)
**Likely MCP**: 1-2 (route_interview_question if not exists, aggregate_interview_state)

---

# T4.7: samvil-scaffold (Outline)

> **Detailed plan after T4.6 retro.**

**Target**: 1653 → ~180 LOC
**Risk**: High (CLI external dependencies)
**Likely MCP**: 1 (evaluate_scaffold_target — T3.4 deploy_targets pattern)

---

# T4.8: samvil-build (Outline) — CRITICAL

> **Detailed plan after T4.7 retro + dedicated pre-analysis dispatch.**

**Target**: 1432 → ~180 LOC
**Risk**: **CRITICAL** (core value producer)
**Pre-analysis required**: separate Explore dispatch to map current logic + propose migration strategy
**Likely MCP**: 2-3 (evaluate_build_features, aggregate_build_progress, possibly Pattern Registry expansion)
**Smoke tests target**: 30+

---

# T4.9: samvil-qa (Outline) — CRITICAL

> **Detailed plan after T4.8 retro + dedicated pre-analysis dispatch.**

**Target**: 1713 → ~200 LOC
**Risk**: **CRITICAL** (core verification, Ralph loop)
**Pre-analysis required**: separate Explore dispatch — Ralph loop pattern is novel
**Likely MCP**: 2-3 (synthesize_qa_evidence already exists, aggregate_qa_state, evaluate_ralph_step)
**Smoke tests target**: 30+

---

# T4.R: Phase C Release (v4.0.0) — Consolidation Milestone

After all 5 Hard skills migrated:

- [ ] Bump version to **v4.0.0** (MAJOR — consolidation complete, all 14 skills ultra-thin)
- [ ] CHANGELOG entry — major milestone summary
- [ ] PR + merge + tag

**v4.0.0 significance**:
- Consolidation phase fully complete
- All 14 skills ultra-thin (≤150 LOC each)
- Aggregate MCP pattern proven across full skill catalog
- Foundation ready for Mountain Stage (M1-M4)

---

# Phase C Done Criteria

- [ ] All 5 Hard skills migrated (LOC reduced > 80% each)
- [ ] All smoke tests pass (legacy + migrated equivalent)
- [ ] SKILL.legacy.md preserved for each
- [ ] New MCP tools have unit tests
- [ ] Pre-commit 9/9 green throughout
- [ ] Phase C retro written
- [ ] backlog updated
- [ ] **15 thin skills total** (Phase A 6 + Phase B 4 + Phase C 5)
- [ ] No regressions in build/qa core functionality (verified via real dogfood — small app build + qa pass)

---

## Plan Self-Review Notes

- ✅ T4.5 detailed; T4.6-T4.9 outlined per re-planning policy
- ✅ Smoke test scenarios upfront
- ✅ New MCP tool pre-analysis included
- ✅ **Pre-analysis dispatch added for T4.8/T4.9 (Critical)**
- ✅ Order rationale: lowest-risk → highest-risk
- ✅ **Smoke test target raised to 30+ for build/qa**
- ⚠️ build/qa carry highest risk — SKILL.legacy.md preservation + broad smoke coverage essential
- ⚠️ Real dogfood (small app build + qa) recommended before v4.0.0 release

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-26-samvil-tier4-phaseC.md`.

Recommended: **Subagent-Driven** (consistent with Tier 1-3 + Phase B). T4.5 (samvil orchestrator) implementer dispatched first.
