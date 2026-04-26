# SAMVIL Consolidation + Mountain Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two-phase journey from v3.32.0 to fully-realized SAMVIL.
- **Consolidation (Tier 1-4, ~6 months)** — Clean up the 49% dead/disconnected, migrate all 14 skills to ultra-thin, retire WARM modules. End: gauche **v4.0.0** "clean foundation."
- **Mountain (M1-M4, ~4-8 months)** — Recover the original Phase 2-4 promises (Module Boundary, multi-host dogfood, domain packs, telemetry dashboard). End: **v4.6.0** "promise fulfilled."

**Architecture:** Sequential phases with explicit re-planning checkpoints between Tiers and Stages. Every Phase ships a release. Versioning: PATCH for cleanup, MINOR for new capability, MAJOR (v4.0.0) for the consolidation milestone.

**Tech Stack:** Python 3.11+, MCP (FastMCP), pytest. No new external dependencies.

**Total horizon:** 10-14 months. Re-planning every 2-4 weeks.

---

## 0. Phase Overview (10-14 months)

| Tier / Stage | Focus | Duration | End-state version |
|---|---|---|---|
| **T1** Quick wins | Bug fix + COLD removal + first merge | 1 week | v3.33.0 |
| **T2** Disconnected cleanup | WARM analysis + 2 module merges + docs slim | 2-3 weeks | v3.34.0 ~ v3.36.0 |
| **T3** Easy skill migration (Phase A) | 4 small skills → ultra-thin | 4 weeks | v3.37.0 ~ v3.40.0 |
| **T4** Hard skill migration (Phase B+C) | 9 remaining skills, including build/qa | 16-20 weeks | v3.99.0 → **v4.0.0** |
| **M1** Module Boundary | contract.json system, big-app capability | 2 weeks | v4.1.0 |
| **M2** Multi-host real dogfood | Codex/OpenCode E2E + Gemini adapter | 2-3 weeks | v4.2.0 |
| **M3** Domain Pack depth | game-phaser + webapp-enterprise | 2-3 weeks | v4.4.0 |
| **M4** Telemetry remote + 3-tier health | opt-in flow + mini dashboard + UI tier display | 2-3 weeks | v4.6.0 |

**Re-planning checkpoints:** End of each Tier/Stage. Don't write detailed plans for stages > 4 weeks ahead.

---

## 1. Re-planning Policy (non-negotiable)

After each Tier:
1. Run a short retro (`samvil-retro` or manual)
2. Update this plan's Tier outlines based on what was learned
3. Check: did we drift into another Phase 5+ rabbit hole?
4. Confirm next Tier scope still aligned with end-goal

**Hard rule during Consolidation:** No new feature MINOR releases. Only `chore(consolidate)` PATCH. New features wait for Mountain stage.

**Bypass policy:** Only with explicit user approval per drift event.

---

## 2. Risk Management

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Build/qa migration regression | High | Critical | SKILL.legacy.md preserved + feature flag `SAMVIL_SKILL_MODE=legacy\|thin` |
| Drift into Phase 5+ during cleanup | Medium | High | Hard rule above + retro every Tier |
| 6+ months feels too long, abandon mid-way | Medium | Critical | Each Tier ships v3.x release — value visible monthly |
| Hidden cross-skill dependencies break on migration | Medium | Medium | Cross-host smoke test runs after every skill migration |
| Multi-host promise stays unverified | Low (after Phase A skill thin) | High | M2 includes real Codex E2E, not just marker generation |

---

## 3. File Structure (immediately affected)

| Area | Files | Notes |
|---|---|---|
| MCP module merges | `mcp/samvil_mcp/{convergence_check,evolve_execution,release_guards}.py` | New unified modules |
| Removed COLD tools | `mcp/samvil_mcp/server.py` | Tool registrations deleted |
| Removed COLD source | `mcp/samvil_mcp/{claim_ledger,*}.py` partial | Functions dropped |
| Skill migration | `skills/*/SKILL.md` + `skills/*/SKILL.legacy.md` | Each skill → thin shell + legacy backup |
| Docs consolidation | `references/samvil-ssot-schema.md`, `docs/CHANGELOG-legacy.md`, `references/decision-boundaries.md` | New consolidations |
| Hardening backlog | `docs/superpowers/plans/2026-04-25-samvil-v3.3-phase1.md` | Reference for past notes |

---

# Tier 1 — Quick Wins (Detailed Plan)

**Goal:** In one week, reduce noise (175 → ~155 tools, 31 → 30 modules, 1 bug fixed). Pre-commit green throughout.

## File structure (Tier 1)

| File | Status | Responsibility |
|---|---|---|
| `mcp/samvil_mcp/post_rebuild_qa.py` | Modify | Fix scaffold-input silent failure |
| `mcp/tests/test_post_rebuild_qa.py` | Modify | Pin the bug fix |
| `mcp/samvil_mcp/server.py` | Modify | Remove ~20 COLD tool registrations |
| `mcp/samvil_mcp/{claim_ledger,interview_v3_2,retro_v3_2}.py` | Modify | Remove unused functions |
| Various test files | Modify/delete | Drop tests for removed COLD tools |
| `mcp/samvil_mcp/convergence_check.py` | Create | Merge regression_detector + convergence_gate |
| `mcp/samvil_mcp/{regression_detector,convergence_gate}.py` | Delete | Functions absorbed into convergence_check |
| `mcp/tests/test_convergence_check.py` | Create/merge | Combined tests |

---

## Task T1.1: Fix scaffold-input silent failure

**Files:**
- Modify: `mcp/samvil_mcp/post_rebuild_qa.py` (around line 115)
- Test: `mcp/tests/test_post_rebuild_qa.py`

- [ ] **Step 1: Locate the bug**

```bash
grep -n "scaffold-input\|scaffold_input" ${REPO_ROOT}/mcp/samvil_mcp/post_rebuild_qa.py
```

Confirm: `_issues()` checks rebuild-reentry and scaffold-output but skips scaffold-input.

- [ ] **Step 2: Write failing test**

Append to `mcp/tests/test_post_rebuild_qa.py`:

```python
def test_post_rebuild_qa_flags_missing_scaffold_input(tmp_path):
    """When scaffold-input.json is absent, _issues must report it (currently silent)."""
    samvil_dir = tmp_path / ".samvil"
    samvil_dir.mkdir()
    # rebuild-reentry exists with status=ready
    (samvil_dir / "rebuild-reentry.json").write_text(
        '{"status": "ready", "seed_version": "1.0", "seed_hash": "abc"}'
    )
    # scaffold-output exists with status=built
    (samvil_dir / "scaffold-output.json").write_text(
        '{"status": "built", "seed_version": "1.0", "seed_hash": "abc"}'
    )
    # scaffold-input.json deliberately missing

    from samvil_mcp.post_rebuild_qa import build_post_rebuild_qa

    result = build_post_rebuild_qa(project_root=str(tmp_path))
    assert result["status"] == "blocked"
    assert any("scaffold-input.json" in issue for issue in result["issues"])
```

- [ ] **Step 3: Run test, verify failure**

```bash
cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/test_post_rebuild_qa.py::test_post_rebuild_qa_flags_missing_scaffold_input -v
```

Expected: FAIL (status is "ready" or scaffold-input not in issues).

- [ ] **Step 4: Apply fix**

In `mcp/samvil_mcp/post_rebuild_qa.py`, locate `_issues()` function. After the existing `rebuild-reentry.json missing` check (around line 113), add:

```python
    if not (samvil_dir / "scaffold-input.json").exists():
        issues.append("scaffold-input.json missing — was samvil-scaffold invoked?")
```

(Adjust path resolution to match function's existing pattern.)

- [ ] **Step 5: Verify pass**

```bash
cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/test_post_rebuild_qa.py -v
```

Expected: All tests pass including new one.

- [ ] **Step 6: Commit**

```bash
cd ${REPO_ROOT}
bash scripts/pre-commit-check.sh
git checkout -b consolidate/tier1
git add mcp/samvil_mcp/post_rebuild_qa.py mcp/tests/test_post_rebuild_qa.py
git commit -m "fix(post-rebuild-qa): flag missing scaffold-input as blocking issue (T1.1)"
```

---

## Task T1.2: Confirm COLD inventory + remove dead tools

**Files:**
- Modify: `mcp/samvil_mcp/server.py` (remove tool registrations)
- Modify: `mcp/samvil_mcp/{claim_ledger,interview_v3_2,retro_v3_2}.py` (remove unused functions)
- Modify/delete: corresponding test files

### T1.2a: Re-verify COLD list (avoid false positives)

- [ ] **Step 1: Generate authoritative COLD list**

```bash
cd ${REPO_ROOT}
grep -r "@mcp.tool" mcp/samvil_mcp/server.py | sed 's/.*//' > /tmp/all-tools.txt
# Then for each tool, grep across skills + tests + scripts to confirm zero usage.
```

(Detailed script TBD — implementer should generate fresh list, not rely on baseline report alone.)

- [ ] **Step 2: Cross-check baseline candidates**

Baseline named these as COLD candidates (re-verify each):
- `claim_ledger_stats`, `claim_materialize_view`, `claim_query_by_subject`
- `experiment_promote`, `experiment_record_run`, `experiment_reject`
- `health_check`, `check_db_integrity`
- `confidence_followup`, `meta_probe_parse`
- `gate_list`, `get_seed_history`, `list_profiles`
- `mark_externally_satisfied`, `merge_llm_result`, `resolve_interview_level`
- `resume_session`, `refresh_manifest`, `budget_status`, `detect_ac_regressions`

For each: `grep -r "tool_name" skills/ mcp/tests/ scripts/` — if zero hits in skills AND zero in tests, confirm COLD.

- [ ] **Step 3: Save final removal list**

Write to `/tmp/cold-removal-list.txt`. This becomes input to T1.2b.

### T1.2b: Remove COLD tools

- [ ] **Step 1: For each confirmed COLD tool**

For each entry in `/tmp/cold-removal-list.txt`:
1. Remove `@mcp.tool()` registration in `server.py`
2. Remove `_impl` helper if it exists (used only by the tool)
3. Remove underlying function in `*.py` module if unused elsewhere
4. Remove its test if it exists

- [ ] **Step 2: Run full test suite**

```bash
cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/ -v
```

Expected: all passing tests still pass; some tests removed (count drops).

- [ ] **Step 3: Verify pre-commit**

```bash
cd ${REPO_ROOT} && bash scripts/pre-commit-check.sh
```

Expected: green. Tool count: 175 → ~155.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(consolidate): remove ~20 COLD MCP tools (T1.2)"
```

---

## Task T1.3: Merge regression_detector + convergence_gate → convergence_check

**Files:**
- Create: `mcp/samvil_mcp/convergence_check.py`
- Delete: `mcp/samvil_mcp/regression_detector.py`, `mcp/samvil_mcp/convergence_gate.py`
- Modify: `mcp/samvil_mcp/server.py` (update imports)
- Create/merge: `mcp/tests/test_convergence_check.py`

### T1.3a: Map current usage

- [ ] **Step 1: Find all imports**

```bash
grep -rn "from samvil_mcp.regression_detector\|from samvil_mcp.convergence_gate\|import regression_detector\|import convergence_gate" mcp/ scripts/ skills/
```

List all places that need to be updated.

### T1.3b: Create unified module

- [ ] **Step 2: Write convergence_check.py**

Combine the two modules. Suggested shape:

```python
"""Convergence check — unified regression + convergence gate (v3.33+).

Consolidates the prior regression_detector.py + convergence_gate.py into
a single module. The two were 1:1 coupled (regression only used by
convergence_gate), so the split was overhead.
"""

# Copy the data classes from both modules
# Copy the public functions: detect_regressions, evaluate_convergence
# Update internal calls so they no longer cross module boundaries
```

(Implementer: read both files first, then merge with careful attention to function signatures used externally.)

### T1.3c: Update imports + tests

- [ ] **Step 3: Update server.py imports**

Replace `from .regression_detector import ...` and `from .convergence_gate import ...` with `from .convergence_check import ...`.

- [ ] **Step 4: Merge test files**

Combine `test_regression_detector.py` + `test_convergence_gate.py` content into `test_convergence_check.py`. Delete the old two test files.

- [ ] **Step 5: Delete old module files**

```bash
git rm mcp/samvil_mcp/regression_detector.py
git rm mcp/samvil_mcp/convergence_gate.py
```

- [ ] **Step 6: Run full suite**

```bash
cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/ -v
```

Expected: all tests passing. Module count: 60 → 59.

- [ ] **Step 7: Verify pre-commit**

```bash
cd ${REPO_ROOT} && bash scripts/pre-commit-check.sh
```

Expected: green.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(consolidate): merge regression_detector + convergence_gate → convergence_check (T1.3)"
```

---

## Tier 1 Verification & Release

- [ ] **Step 1: Sanity check final state**

```bash
git log --oneline consolidate/tier1 ^main
# Expected: 3 commits (T1.1 fix, T1.2 chore, T1.3 refactor)
```

- [ ] **Step 2: Bump version to v3.33.0 (PATCH for consolidation work)**

Edit:
- `.claude-plugin/plugin.json` → `"version": "3.33.0"`
- `mcp/samvil_mcp/__init__.py` → `__version__ = "3.33.0"`
- `README.md` first line → `v3.33.0`

- [ ] **Step 3: CHANGELOG entry**

Add to CHANGELOG.md:

```markdown
## v3.33.0 — Consolidation Tier 1
- fix(post-rebuild-qa): flag missing scaffold-input
- chore: removed ~20 unused MCP tools (175 → ~155)
- refactor: merged regression_detector + convergence_gate into convergence_check
```

- [ ] **Step 4: Final pre-commit + commit**

```bash
bash scripts/pre-commit-check.sh
git add -A
git commit -m "chore(release): prepare v3.33.0 (Tier 1 complete)"
```

- [ ] **Step 5: Open PR to main**

```bash
gh pr create --title "Consolidation Tier 1 (v3.33.0)" --body "..."
```

After merge: tag `v3.33.0` and push.

---

## Tier 1 Done Criteria

Before declaring Tier 1 done and writing Tier 2 detailed plan:

- [ ] scaffold-input bug fix tested and merged
- [ ] ~20 COLD tools removed; tool count documented (target: 155 ± 5)
- [ ] convergence_check module exists; old two modules deleted
- [ ] Full pytest suite passes
- [ ] Pre-commit check green
- [ ] v3.33.0 released and tagged
- [ ] Short retro written (5 minutes): what worked, what didn't, surprises

If any item fails: do not proceed to Tier 2. Fix in Tier 1 first.

---

# Tier 2 — Disconnected Cleanup (Outline)

> **Status: Outline only. Detailed plan after Tier 1 retro.**

**Duration:** 2-3 weeks
**End version:** v3.34.0 ~ v3.36.0

## High-level tasks

1. **T2.1 WARM analysis (1 week)** — For each of ~62 WARM tools, decide:
   - Connect to a skill (production-ready)
   - Move to internal `_impl` only (testable but not exposed)
   - Remove (test only, no skill use, low confidence in usefulness)
2. **T2.2 evolve_proposal + evolve_apply merge** — `evolve_execution` module (547 LOC)
3. **T2.3 release_publish + remote_release merge** — `release_guards` module (206 LOC)
4. **T2.4 samvil-ssot-schema.md consolidation** — 4 schema docs → 1
5. **T2.5 CLAUDE.md slim** — 705 → 450 lines, archive v0.8/v2.x sections
6. **T2.6 CI broken-link check** — `scripts/check-broken-references.sh`

## Risks (planned)

- WARM analysis may reveal connections we missed in baseline (false negatives)
- evolve module merge: cross-skill dependencies need careful update
- CLAUDE.md slim: many internal links need updating

---

# Tier 3 — Phase A: Easy Skill Migration (Outline)

> **Status: Outline only.**

**Duration:** 4 weeks
**End version:** v3.37.0 ~ v3.40.0
**Target skills:** pm-interview (117 LOC), doctor (178), update (284), deploy (379) → all ultra-thin

## High-level tasks

1. **T3.1 samvil-pm-interview ultra-thin (1 week)** — preset matching → MCP `route_question` etc.
2. **T3.2 samvil-doctor ultra-thin (1 week)** — diagnostic checks → MCP one-shot
3. **T3.3 samvil-update ultra-thin (1 week)** — version check + clone, MCP-driven migration
4. **T3.4 samvil-deploy ultra-thin (1 week)** — platform select + MCP deploy chain

For each: SKILL.legacy.md backup, ultra-thin SKILL.md, no behavior change.

## Verification per skill

- Old skill behavior preserved (smoke test)
- LOC reduced ≥80%
- Pre-commit green

---

# Tier 4 — Phase B+C: Medium + Hard Skill Migration (Outline)

> **Status: Outline only. Most complex tier.**

**Duration:** 16-20 weeks
**End version:** v3.41.0 → v3.99.0 → **v4.0.0** (clean foundation)

## Phase B (Medium, 6-8 weeks)

| Skill | LOC | Strategy |
|---|---|---|
| samvil-evolve (482) | Wonder/Reflect agents stay; convergence to MCP | New MCP: `converge_check` |
| samvil-retro (506) | Metrics → MCP; suggestion logic kept thin | New MCP: `pattern_detect` |
| samvil-council (554) | Agent spawning kept; synthesis → MCP `consensus_synthesize` | New MCP: `consensus_synthesize` |
| samvil-analyze (677) | Code scanning Bash; reverse-seed → MCP | New MCP: `reverse_seed_from_code` |

## Phase C (Hard, 10-12 weeks)

| Skill | LOC | Strategy | Risk |
|---|---|---|---|
| samvil (766) | Orchestrator chain → MCP events | Medium |
| samvil-interview (1259) | Question routing → MCP | Medium |
| samvil-build (1432) | **Pattern Registry expansion required first** | **High** |
| samvil-scaffold (1653) | CLI choices → dependency-matrix MCP | High |
| samvil-qa (1713) | Ralph loop → MCP `ralph_step`; 3-pass cached | **High** |

**v4.0.0 release criteria:**
- All 14 skills ultra-thin (sum ~3,400 LOC, 65% reduction)
- All cross-host smoke tests pass
- No build/qa regression on real-world apps
- Hard rule retro: drift events documented

---

# Mountain (M1-M4) — Outline

> **Status: Outline only. Detailed plan after v4.0.0.**

## M1: Module Boundary contract (2 weeks → v4.1.0)

- `.samvil/modules/<name>/contract.json` schema
- New MCP: `validate_contract`, `enforce_boundary`
- skills opt-in: PM can request "auth module only" updates
- Recovery of "큰 규모" promise

## M2: Multi-host real dogfood (2-3 weeks → v4.2.0)

- Codex E2E: real chained execution, not just marker generation
- OpenCode E2E: same
- Gemini adapter: HostCapability + adapter
- Cross-host result equivalence test
- Recovery of "Codex/OpenCode 호환" promise

## M3: Domain Pack depth (2-3 weeks → v4.4.0)

- `game-phaser` pack: state machine + asset pipeline + 60fps budget
- `webapp-enterprise` pack: monorepo + BFF + OpenAPI + SSO
- Real dogfood with 1 game + 1 SaaS
- Recovery of "도메인 깊이" promise

## M4: Telemetry remote + 3-tier health (2-3 weeks → v4.6.0)

- opt-in flow at `/samvil` first run
- Anonymized telemetry sync to dongho's server
- Mini Next.js dashboard (separate project)
- 3-tier health UI in skill output
- Recovery of "원격 협업 + 신뢰성" promise

**v4.6.0 = 처음 두 야망(멀티호스트 + 큰 규모) 100% 이행 + v3.32 자동화 강점 유지**

---

## Plan Self-Review Notes

Reviewed against scope:

- ✅ Tier 1 fully detailed with TDD steps
- ✅ Tier 2-4 + M1-M4 outlines explicit; re-planning policy enforces detail-as-needed
- ✅ Risk management addresses all 5 user concerns from baseline (drift, abandonment, regression, hidden dependencies, multi-host verification)
- ✅ Versioning consistent: PATCH for cleanup, MINOR for new capability, v4.0.0 milestone
- ✅ End-state criteria explicit per Tier
- ⚠️ T1.2 detail (COLD removal) requires implementer to re-verify list; not pre-baked. Intentional to avoid acting on stale baseline data.
- ⚠️ Tier 4 (Hard skills) carries highest risk; SKILL.legacy.md + feature flag + cross-host smoke required throughout

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-samvil-consolidation-mountain.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review, fast iteration. Same pattern as Phase 1 v3.3 work.

**2. Inline Execution** — Execute tasks in this session with checkpoints.

For Tier 1 specifically (3 small tasks, ~7 hours), either works. Recommend Subagent-Driven for consistency with Phase 1 pattern.

Which approach?
