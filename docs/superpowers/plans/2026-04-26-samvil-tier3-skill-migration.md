# SAMVIL Tier 3 — Phase A Skill Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate 4 Easy skills from current form to ultra-thin (~80% LOC reduction). Preserve behavior via `SKILL.legacy.md` backup + smoke test scenarios. End: **v3.35.0 ~ v3.38.0** (one MINOR per skill).

**Architecture:** Each skill becomes a thin shell that:
1. Reads file SSOT (state.json, manifest, ADR)
2. Calls MCP tools for orchestration decisions
3. Performs minimal CC-specific tool calls (Bash, Edit) only when needed
4. Uses HostCapability resolver for chain/sub-agent decisions
5. Falls back to SKILL.legacy.md content if needed (during transition period)

**Tech Stack:** Same as Phase 1 — Python 3.11+, FastMCP, pytest. No new external deps. May add 2-4 new MCP tools.

**Tier 3 horizon:** 4 weeks (1 skill per week — first one with retro).

---

## 0. Phase A Overview (4 weeks)

| Skill | Current LOC | Target LOC | Migration Risk | Order |
|---|---|---|---|---|
| `samvil-doctor` | 178 | ~80 | **Low** (단순 진단, fewest deps) | **1st** |
| `samvil-pm-interview` | 117 | ~80 | Low (preset matching only) | 2nd |
| `samvil-update` | 284 | ~120 | Medium (version check + migrate) | 3rd |
| `samvil-deploy` | 379 | ~150 | Medium (platform branching) | 4th |

**Total LOC**: 958 → ~430 (55% reduction).

**Order rationale**: doctor first (lowest risk, builds confidence + pattern). pm-interview second (small, similar). Then update + deploy by complexity.

**Re-planning checkpoint**: After T3.1 (doctor), measure actual time/risk. If T3.1 takes > 1 week or surfaces unexpected MCP-tool needs, re-plan T3.2~T3.4.

---

## 1. Pre-flight — Smoke Test Scenarios

Each migrated skill must demonstrate behavioral equivalence via a smoke test. Defined upfront:

### S1. samvil-doctor smoke
**Scenario**: Run `/samvil:doctor` in a project directory.
**Expected output**: Health check across MCP/disk/git/version with explicit OK/WARN/FAIL per item. UI/format same as legacy.
**Verification**: Diff legacy vs migrated output — should be functionally equivalent (key/value pairs match; format minor differences OK if PM-readable).

### S2. samvil-pm-interview smoke
**Scenario**: Run `/samvil:pm-interview` to start a PM-style interview from an empty project.
**Expected output**: First question asks about vision, captures answer, advances to next phase (users/metrics/...). Final output: `pm-seed.json` with all required fields.
**Verification**: Run interview to completion in legacy + migrated. pm-seed.json should be schema-equivalent.

### S3. samvil-update smoke
**Scenario**: Run `/samvil:update` on a project with v3.x seed.
**Expected output**: Detects current version, fetches latest from GitHub, runs migration if `--migrate` flag, reports diff.
**Verification**: Both versions should detect the same current version and propose the same migration plan. Actual file changes should be identical.

### S4. samvil-deploy smoke
**Scenario**: Run `/samvil:deploy` after a passing QA.
**Expected output**: Platform selection (Vercel/Railway/Coolify), env var check, deploy command, URL captured.
**Verification**: Both versions should reach the same deploy command for the same input. (Don't actually deploy in smoke test — abort before push.)

---

## 2. Pre-flight — New MCP Tools Analysis

Each skill migration requires identifying which logic moves to MCP. Pre-analysis:

### samvil-doctor (T3.1) — likely no new MCP tools needed
Current logic: file-system checks (`.samvil/` exists, MCP healthy, git status, version sync). All can use existing MCP tools (`health_check` was removed in T1.2 — re-verify; if needed, may need to bring back as `_impl` exposed via thin tool, or add new `diagnose_environment` MCP tool).

**Action**: During T3.1 implementer phase, identify if any new MCP tool needed. If yes, add as sub-task before main migration.

### samvil-pm-interview (T3.2) — likely no new MCP tools
Existing tools cover PM seed validation, phase routing. Re-verify during T3.2.

### samvil-update (T3.3) — possibly 1 new MCP tool
May need `fetch_latest_release_metadata` (from GitHub) — currently a Bash call; could be useful as MCP tool for cross-host. **Decide during T3.3.**

### samvil-deploy (T3.4) — possibly 1-2 new MCP tools
Platform-specific deploy commands (Vercel/Railway/Coolify) — currently inline in skill. Could move to `mcp/samvil_mcp/deploy_targets.py` with `evaluate_deploy_target(platform)`. **Decide during T3.4.**

**Hard rule**: Don't pre-build MCP tools speculatively. Add only when implementer hits "I need this" wall.

---

## 3. Migration Pattern (applied to all 4 skills)

For each skill, follow this pattern:

### Pattern Step 1: Backup
- Copy current `skills/<name>/SKILL.md` → `skills/<name>/SKILL.legacy.md`
- Add header: "Legacy version preserved for rollback. New ultra-thin entry is SKILL.md."

### Pattern Step 2: Write smoke test
- Document the smoke scenario in `mcp/tests/test_<skill>_smoke.py` (or new dedicated test file).
- Smoke test calls the skill (or simulates input/output paths) and verifies behavior.

### Pattern Step 3: Identify roles
- What in current SKILL.md is **orchestration** (when to do what) → move to MCP tool calls
- What is **CC-specific** (Bash, Edit, file read/write) → keep in skill
- What is **legacy detail** (specific commands, prompts) → reference SKILL.legacy.md

### Pattern Step 4: Write thin SKILL.md
- Section 1: Boot Sequence (read state, manifest, ADR — file SSOT)
- Section 2: MCP gate (call orchestration tool to decide what to do)
- Section 3: Execute (CC-specific tools only when needed)
- Section 4: Chain (file marker or Skill tool, depending on HostCapability)
- Each section: bullet steps, < 30 lines

### Pattern Step 5: Update server.py if new MCP tool needed

### Pattern Step 6: Run smoke test
- Validate behavioral equivalence

### Pattern Step 7: Pre-commit + commit

---

# Tier 3 — Detailed Plan (T3.1 only; T3.2-T3.4 outline)

---

## Task T3.1: samvil-doctor migration (Detail)

**Files:**
- Create: `skills/samvil-doctor/SKILL.legacy.md` (backup)
- Modify: `skills/samvil-doctor/SKILL.md` (rewrite as ultra-thin)
- Possibly create: `mcp/tests/test_doctor_smoke.py`

### T3.1.1: Backup current SKILL.md as legacy

- [ ] **Step 1: Read current samvil-doctor**

```bash
wc -l ${REPO_ROOT}/skills/samvil-doctor/SKILL.md
cat ${REPO_ROOT}/skills/samvil-doctor/SKILL.md
```

Document key behaviors to preserve.

- [ ] **Step 2: Backup**

```bash
cp ${REPO_ROOT}/skills/samvil-doctor/SKILL.md ${REPO_ROOT}/skills/samvil-doctor/SKILL.legacy.md
```

- [ ] **Step 3: Add legacy header**

Edit `SKILL.legacy.md` to prepend:

```markdown
> **Legacy version (T3.1 backup).** Preserved for rollback. The new ultra-thin
> entry is `SKILL.md`. If migration breaks behavior, this file documents the
> exact behavior to restore.
```

- [ ] **Step 4: Commit backup**

```bash
git add skills/samvil-doctor/SKILL.legacy.md
git commit -m "chore(skill-doctor): backup current as SKILL.legacy.md (T3.1.1)"
```

### T3.1.2: Identify MCP tools needed

- [ ] **Step 1: Analyze what samvil-doctor does**

Categorize each behavior in current SKILL.md:
- **Read state** (file SSOT): which files?
- **Check** (validation): MCP/disk/git/version?
- **Output** (rendering): markdown report?

- [ ] **Step 2: Find existing MCP tools that cover each check**

```bash
grep -rn "@mcp.tool" ${REPO_ROOT}/mcp/samvil_mcp/server.py | grep -iE "health|diagnose|check|validate"
```

- [ ] **Step 3: Decide on new tool**

If existing tools don't cover everything, design ONE new tool: `diagnose_environment(project_root)` returning `{mcp: {...}, disk: {...}, git: {...}, version: {...}}`.

If existing tools suffice, skip this step.

- [ ] **Step 4: (Optional) Add new MCP tool**

Only if Step 3 decided "need new tool". Implement in `mcp/samvil_mcp/diagnostic.py` (new module) or appropriate existing module. Add `@mcp.tool()` wrapper to server.py with health logging. Add unit tests.

### T3.1.3: Write smoke test

- [ ] **Step 1: Define behavioral equivalence**

Identify 5-10 things current `samvil-doctor` does. Write each as a test assertion in `mcp/tests/test_doctor_smoke.py`.

Example:
```python
def test_doctor_reports_mcp_status():
    """samvil-doctor must include MCP status in output."""
    # Setup: a fixture project
    # Run: equivalent of /samvil:doctor (call _impl directly if available, else simulate)
    # Assert: output contains MCP status section with OK/WARN/FAIL
```

- [ ] **Step 2: Verify legacy passes the smoke test**

Run smoke test against current behavior (before migration). If it doesn't pass, the smoke test itself is wrong — fix.

- [ ] **Step 3: Commit smoke test**

```bash
git add mcp/tests/test_doctor_smoke.py
git commit -m "test(skill-doctor): add smoke scenarios pre-migration (T3.1.3)"
```

### T3.1.4: Rewrite SKILL.md as ultra-thin

- [ ] **Step 1: Write the thin version**

New `skills/samvil-doctor/SKILL.md`:
```markdown
---
name: samvil-doctor
description: Diagnose SAMVIL environment health.
---

# samvil-doctor (ultra-thin)

## Boot Sequence

1. Read `.samvil/state.json` (if exists, else default state).
2. Read project root from cwd or argument.

## MCP Gate

Call `diagnose_environment(project_root)` (or compose from existing MCP tools if no new tool added).

## Output

Render returned dict as markdown:
```
[SAMVIL] Doctor Report
- MCP: <status>
- Disk: <status>
- Git: <status>
- Version: <plugin.json> / <__init__.py> / <README>
- Conclusion: <ALL OK | N issues>
```

## Chain

This is a one-shot diagnostic. No chain to next skill.

## Legacy reference

For detailed inspection patterns and edge cases, see `SKILL.legacy.md`.
```

Target: 60-80 lines.

- [ ] **Step 2: Run smoke test against migrated**

```bash
cd ${REPO_ROOT}/mcp && .venv/bin/python -m pytest tests/test_doctor_smoke.py -v
```

Expected: all assertions pass.

- [ ] **Step 3: Verify thin LOC**

```bash
wc -l ${REPO_ROOT}/skills/samvil-doctor/SKILL.md
```

Expected: < 100 lines.

### T3.1.5: Pre-commit + commit

- [ ] **Step 1: Pre-commit check**

```bash
cd ${REPO_ROOT}
bash scripts/pre-commit-check.sh
```

Note: skill-thinness check should pass (already migrated samvil-seed, samvil-design under threshold; doctor joins).

- [ ] **Step 2: Commit**

```bash
git add skills/samvil-doctor/SKILL.md
git commit -m "refactor(skill-doctor): migrate to ultra-thin (T3.1.4)"
```

### T3.1.6: Retro + plan adjust

- [ ] **Step 1: Run retro**

Document in `docs/samvil-tier3-retro.md` (append to existing or new):
- Time spent (target: < 1 week)
- Surprises
- New MCP tools added (if any)
- LOC change (legacy → thin)

- [ ] **Step 2: Adjust T3.2-T3.4 plans based on retro**

If T3.1 surfaced unexpected complexity, update the outlines below before T3.2 starts.

---

## Task T3.2: samvil-pm-interview migration (Outline)

> **Detailed plan after T3.1 retro.**

**Target LOC**: 117 → ~80
**Risk**: Low
**Pattern**: Same as T3.1 (backup → smoke test → migrate → verify → commit)
**Likely focus**: PM phase routing (vision/users/metrics/epics/tasks/ACs) — uses existing MCP tools likely.

---

## Task T3.3: samvil-update migration (Outline)

> **Detailed plan after T3.2 retro.**

**Target LOC**: 284 → ~120
**Risk**: Medium (version detection + migration application)
**Likely new MCP tools**: `fetch_latest_release_metadata` (or use existing `gh` Bash)

---

## Task T3.4: samvil-deploy migration (Outline)

> **Detailed plan after T3.3 retro.**

**Target LOC**: 379 → ~150
**Risk**: Medium (3 platform branches: Vercel/Railway/Coolify)
**Likely new MCP tools**: `evaluate_deploy_target(platform)` to centralize platform decisions.

---

# Tier 3 Release (T3.R)

After all 4 skills migrated:

- [ ] Bump version to **v3.35.0** (MINOR — visible behavior change: skills are thinner, may have new MCP tools)
- [ ] CHANGELOG entry with all 4 skill counts (LOC before/after)
- [ ] PR + merge + tag

(Or: ship one MINOR per skill — v3.35 (doctor), v3.36 (pm-interview), v3.37 (update), v3.38 (deploy). Decide at T3.R based on momentum.)

---

# Tier 3 Done Criteria

Before declaring Tier 3 done and writing Tier 4 plan:

- [ ] All 4 skills migrated (LOC reduced > 50% each)
- [ ] All 4 smoke tests pass (legacy and migrated equivalent)
- [ ] SKILL.legacy.md preserved for each
- [ ] New MCP tools (if any) have unit tests
- [ ] Pre-commit green throughout
- [ ] Tier 3 retro written
- [ ] backlog updated (any new findings)

---

## Plan Self-Review Notes

- ✅ T3.1 fully detailed; T3.2-T3.4 outlined per re-planning policy
- ✅ Smoke test scenarios defined upfront (Action item A1 from retro)
- ✅ New MCP tool pre-analysis included (Action item A2)
- ✅ Backlog file already created (Action item A3)
- ✅ SKILL.legacy.md preservation pattern explicit
- ⚠️ T3.1 may need new MCP tool — decided in implementer phase, not pre-baked

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-26-samvil-tier3-skill-migration.md`.

Recommended: **Subagent-Driven** (consistent with Tier 1+2 pattern). T3.1 implementer dispatched first.

Which approach?
