# SAMVIL Tier 4 Phase B — Medium Skill Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate 4 Medium skills to ultra-thin (~50% LOC reduction). Phase A patterns (single-source-of-truth MCP, SKILL.legacy.md backup, smoke tests) applied throughout. End: **v3.36.0** (single bundled release after all 4).

**Architecture:** Same pattern as Phase A (T3.1-T3.4):
1. Skill body becomes thin shell calling MCP for orchestration
2. Branching/policy logic extracted to MCP tools (single source of truth)
3. Korean prose / phase prompts / detailed legacy stays in `SKILL.legacy.md`
4. Smoke tests pin behavior contracts (not implementation)

**Tech Stack:** Python 3.11+, FastMCP, pytest. No new deps. Likely 3-5 new MCP tools across 4 skills.

**Phase B horizon:** 6-8 weeks (estimate). 1 skill per 1.5-2 weeks based on Phase A pacing (which was much faster than estimate, so this may compress).

---

## 0. Phase B Overview

| Skill | Current LOC | Target LOC | Risk | Order | New MCP candidate |
|---|---|---|---|---|---|
| `samvil-retro` | 506 | ~150 | Low (post-processing only) | **1st** | `pattern_detect` (recurring failure detection) |
| `samvil-evolve` | 482 | ~150 | Medium (core autonomous loop) | 2nd | `converge_check` likely already covered by T1.3's convergence_check |
| `samvil-council` | 554 | ~180 | Medium (parallel agents — first in Phase B) | 3rd | `consensus_synthesize` (round results aggregation) |
| `samvil-analyze` | 677 | ~200 | High (code → reverse seed, complex logic) | **4th** | `reverse_seed_from_code` (reverse-engineering helper) |

**Total LOC**: 2,219 → ~680 (-69%).

**Order rationale**: Start safest (retro is post-processing). Build pattern confidence. End hardest (analyze has most LOC + most novel logic). Council 3rd because parallel agent spawning is a new pattern not in Phase A.

**Re-planning checkpoints**: After T4.1 (retro) — measure time, confirm pattern. After T4.2 (evolve) — confirm parallel-agent pattern works. After T4.3 — final outline adjust before T4.4.

---

## 1. Pre-flight — Smoke Test Scenarios

### S1. samvil-retro smoke
**Scenario**: Run `/samvil:retro` after a cycle (with events.jsonl populated).
**Expected**: Generate `retro-XXX.md` with structured suggestions (issue/fix proposals categorized by severity).
**Verification**: pattern detection finds recurring failures across multiple cycles. Suggestion shape matches retro-schema (id/severity/target_file/reason/expected_impact).

### S2. samvil-evolve smoke
**Scenario**: Run `/samvil:evolve` after QA fail/partial.
**Expected**: Wonder analysis → Reflect proposes seed mutations → Convergence check passes/blocks → next cycle or stop.
**Verification**: 5 evolve_checks (eval, per-AC, regression, evolution, validation) all evaluated. Converge OR continue decision is deterministic given same inputs.

### S3. samvil-council smoke
**Scenario**: Run `/samvil:council` on a seed with a contentious section.
**Expected**: 2-round (Research → Review) parallel agent spawn. Verdicts aggregated. Blocking objections surfaced explicitly.
**Verification**: Each agent's verdict captured in claim_ledger. Synthesis is independent (Generator ≠ Judge). Round-2 prompts include Round-1 debate points.

### S4. samvil-analyze smoke
**Scenario**: Run `/samvil:analyze` on an existing Next.js project (brownfield).
**Expected**: Detect framework, scan src/ modules, generate reverse-engineered seed.json with realistic features.
**Verification**: Generated seed validates against schema_version 3.x. Features list matches actual src/ subdirectories. ADR `EXISTING-NNN` auto-generated for inferred decisions.

---

## 2. Pre-flight — New MCP Tools Analysis

### samvil-retro (T4.1)
**Likely new tool**: `detect_recurring_patterns(events_jsonl_path, claims_jsonl_path)` returning list of `{pattern, frequency, last_occurrence, suggested_action}`.
- Module: `mcp/samvil_mcp/retro_patterns.py` (new)
- Use existing `retro_v3_2.py` as base; extract pattern detection.

### samvil-evolve (T4.2)
**Likely no new tool**: `convergence_check` already exists (from T1.3 merge). evolve_loop functions already cover wonder/reflect orchestration. Verify during implementation.

### samvil-council (T4.3)
**Likely new tool**: `consensus_synthesize(round_results)` returning `{verdict, dissent, debate_points, next_round_seed}`.
- Module: `mcp/samvil_mcp/consensus_v3_2.py` already exists — extend rather than create new.

### samvil-analyze (T4.4)
**Likely new tool**: `reverse_seed_from_code(project_root)` returning seed.json structure with `confidence_tags` for inferred fields.
- Module: `mcp/samvil_mcp/brownfield_analyzer.py` (new) — heavy logic.
- Could be a major new tool similar to T3.4's `evaluate_deploy_target`.

**Hard rule**: Add MCP tools only when migration genuinely needs them.

---

## 3. Migration Pattern (T3.1-T3.4 proven)

For each skill:
1. **Backup**: `cp SKILL.md SKILL.legacy.md`, prepend rollback header, rename frontmatter to `<skill>-legacy`
2. **Smoke test**: write `mcp/tests/test_<skill>_smoke.py` pinning behavior contracts
3. **Identify roles**: orchestration → MCP, CC-specific → skill, legacy detail → SKILL.legacy.md reference
4. **Write thin SKILL.md**: ≤150 LOC active (Phase B target slightly higher than Phase A's ≤120 due to complexity)
5. **(If needed) Add new MCP tool**: with health logging, unit tests
6. **Verify**: smoke tests pass, pre-commit 9/9 green
7. **Commit**: `refactor(skill-<name>): migrate to ultra-thin (T4.X)`

---

# T4.1: samvil-retro Migration (Detailed)

**Files:**
- Backup: `skills/samvil-retro/SKILL.legacy.md` (new)
- Modify: `skills/samvil-retro/SKILL.md` (rewrite ultra-thin)
- Possibly create: `mcp/samvil_mcp/retro_patterns.py` (new module)
- Create: `mcp/tests/test_retro_smoke.py`

## T4.1.1: Phase 1 — Baseline + behavior

- [ ] **Step 1**: Read `skills/samvil-retro/SKILL.md` fully. Confirm actual LOC.

- [ ] **Step 2**: List 5-10 specific behaviors:
  - Reads events.jsonl, claims.jsonl, qa-results.json
  - Detects recurring failure patterns (e.g., same error 3+ times)
  - Generates suggestions with structured shape (id/severity/target_file/reason/expected_impact)
  - Writes retro-vX.Y.Z.md to `.samvil/retro/`
  - Updates `harness-feedback.log`
  - (others to identify)

## T4.1.2: Phase 2 — MCP tool decision

- [ ] **Step 3**: Check existing tools:
  ```bash
  grep -A1 "@mcp.tool" ${REPO_ROOT}/mcp/samvil_mcp/server.py | grep -iE "retro|pattern|detect"
  ```

- [ ] **Step 4**: Decide on `detect_recurring_patterns` MCP tool. If existing `retro_v3_2.py` has the logic, expose via thin wrapper. If new logic needed, add `retro_patterns.py`.

## T4.1.3: Phase 3 — Backup + smoke test

- [ ] **Step 5**: Backup
  ```bash
  cd ${REPO_ROOT}
  cp skills/samvil-retro/SKILL.md skills/samvil-retro/SKILL.legacy.md
  ```
  Add legacy header, rename frontmatter to `samvil-retro-legacy`.

- [ ] **Step 6**: Write `mcp/tests/test_retro_smoke.py`:
  - Test pattern detection on synthetic events.jsonl
  - Test suggestion shape against retro schema
  - Test idempotency (same input → same suggestions)

## T4.1.4: Phase 4 — Rewrite thin SKILL.md

- [ ] **Step 7**: Write thin SKILL.md (~150 LOC):
  ```markdown
  ---
  name: samvil-retro
  description: <preserved>
  ---
  
  # samvil-retro (ultra-thin)
  
  Post-cycle retrospective. Reads events + claims, detects patterns, writes
  structured suggestions. Detailed prompts and edge cases in SKILL.legacy.md.
  
  ## Boot Sequence
  [Read state, events.jsonl, claims.jsonl]
  
  ## MCP Pattern Detection
  [Call detect_recurring_patterns]
  
  ## Suggestion Synthesis
  [Render suggestions with id/severity/target/reason/expected_impact]
  
  ## Persist
  [Write retro-vX.md + update harness-feedback.log]
  
  ## Chain
  [One-shot — no chain]
  
  ## Legacy reference
  ```

## T4.1.5: Phase 5 — Verify + commit

- [ ] **Step 8**: Smoke tests pass
  ```bash
  cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/test_retro_smoke.py -v
  ```

- [ ] **Step 9**: Pre-commit 9/9 green
  ```bash
  cd ${REPO_ROOT} && bash scripts/pre-commit-check.sh
  ```

- [ ] **Step 10**: Commit
  ```bash
  git add -A
  git commit -m "refactor(skill-retro): migrate to ultra-thin (T4.1)"
  ```

## T4.1.6: Mini retro

- [ ] **Step 11**: Document in this plan (append T4.1 outcomes):
  - Time spent
  - LOC achieved
  - New MCP tools added
  - Surprises
  - Adjust T4.2-T4.4 outlines if needed

---

# T4.2: samvil-evolve Migration (Outline)

> **Detailed plan after T4.1 retro.**

**Target LOC**: 482 → ~150
**Risk**: Medium (core autonomous loop — affects QA failure → seed mutation cycle)
**Likely new MCP tools**: 0-1 (`convergence_check` already exists)
**Pattern**: Wonder analysis → Reflect proposal → Convergence verdict → Continue/Stop

**Critical**: SKILL.legacy.md backup essential. Smoke test must verify Wonder→Reflect→Converge chain stable.

---

# T4.3: samvil-council Migration (Outline)

> **Detailed plan after T4.2 retro.**

**Target LOC**: 554 → ~180
**Risk**: Medium (parallel agents — new pattern in Phase B)
**Likely new MCP tools**: 1 (`consensus_synthesize` — extend existing consensus_v3_2.py)
**Pattern**: 2-round (Research → Review) parallel agent spawning + verdict aggregation

**Critical**: First Phase B skill that spawns parallel agents (Phase A had none). Verify Agent tool calls remain in skill body (CC-specific) but synthesis moves to MCP.

---

# T4.4: samvil-analyze Migration (Outline)

> **Detailed plan after T4.3 retro.**

**Target LOC**: 677 → ~200
**Risk**: High (most LOC + most novel logic — reverse-seed from code)
**Likely new MCP tools**: 1-2 (`reverse_seed_from_code` — heavy module like T3.4 deploy_targets)
**Pattern**: Brownfield analysis → framework detect → src/ scan → reverse seed + confidence_tags + ADR-EXISTING

**Critical**: Most complex Phase B skill. Smoke test against real Next.js project (or fixture).

---

# T4.R: Phase B Release (v3.36.0)

After all 4 skills migrated:

- [ ] Bump version to **v3.36.0** (MINOR — visible: 4 more thin skills, new MCP tools)
- [ ] CHANGELOG entry with all 4 LOC changes
- [ ] PR + merge + tag (single bundled release for momentum)

**Note**: Could also do 1 release per skill (v3.36, 37, 38, 39) but bundling reduces overhead and matches Phase A's single-release pattern.

---

# Phase B Done Criteria

- [ ] All 4 Medium skills migrated (LOC reduced > 50% each)
- [ ] All smoke tests pass (legacy and migrated equivalent)
- [ ] SKILL.legacy.md preserved for each
- [ ] New MCP tools (if any) have unit tests + docstrings
- [ ] Pre-commit 9/9 green throughout
- [ ] Phase B retro written
- [ ] backlog updated (any new findings)
- [ ] 10 thin skills total (6 + Phase B 4) — only Hard 5 remain

---

## Plan Self-Review Notes

- ✅ T4.1 fully detailed; T4.2-T4.4 outlined per re-planning policy
- ✅ Smoke test scenarios upfront (carries Action item A1 from Tier 1+2 retro)
- ✅ New MCP tool pre-analysis included (Action item A2)
- ✅ Order rationale: safest first (retro), hardest last (analyze)
- ✅ Re-planning checkpoints between every task
- ⚠️ T4.4 (analyze) carries highest risk — may need separate detailed plan when reached

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-26-samvil-tier4-phaseB.md`.

Recommended: **Subagent-Driven** (consistent with Tier 1-3). T4.1 (retro) implementer dispatched first.
