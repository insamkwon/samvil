# Independent Evidence, Central Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add blueprint feasibility gating, structured build/QA/evolve event trails, and standard+ independent QA while keeping final verdict/report/state ownership in the main session.

**Architecture:** Keep stage orchestration in existing SAMVIL skills. Add one new pre-build design gate, enrich append-only events in build/QA/evolve, align QA taxonomy across shared references and agent prompts, then branch QA behavior by tier so `minimal` stays inline and `standard+` uses independent Pass 2/3 evidence collection with main-session synthesis.

**Tech Stack:** Claude Code skills, agent markdown prompts, JSON event logs, Next.js/TypeScript plugin repo docs.

---

## File Structure

| File | Responsibility |
|---|---|
| `skills/samvil-design/SKILL.md` | Insert feasibility review before user checkpoint; emit design-stage events |
| `skills/samvil-build/SKILL.md` | Emit structured build/fix events with categories and scopes |
| `skills/samvil-qa/SKILL.md` | Add tier branch, spawn independent Pass 2/3 agents for standard+, synthesize final verdict centrally |
| `skills/samvil-evolve/SKILL.md` | Pass build/fix/event artifacts into wonder/reflect prompts |
| `agents/qa-functional.md` | Align taxonomy with PASS/PARTIAL/UNIMPLEMENTED/FAIL |
| `agents/qa-quality.md` | Make quality output synthesis-friendly for central verdict |
| `agents/wonder-analyst.md` | Read build/fix/event artifacts and analyze repeat patterns |
| `references/qa-checklist.md` | Remain taxonomy/report SSOT for QA language |
| `README.md` | Document changed QA/design/evolve behavior and tier differences |
| `.claude-plugin/plugin.json` | Bump plugin version |

---

### Task 1: Add blueprint feasibility gate before design approval

**Files:**
- Modify: `skills/samvil-design/SKILL.md`
- Modify: `README.md`
- Test: manual doc review of design stage flow in `skills/samvil-design/SKILL.md`

- [ ] **Step 1: Write the failing documentation expectation**

```md
Expected design flow after this task:
1. Generate blueprint
2. Run Gate B if applicable
3. Run blueprint feasibility review
4. Apply needed blueprint edits
5. Present final blueprint to user
6. Save state and chain to scaffold
```

- [ ] **Step 2: Verify the current skill does not satisfy it**

Run: `grep -n "User Checkpoint\|Invoke the Skill tool with skill: \`samvil-scaffold\`" skills/samvil-design/SKILL.md`
Expected: user checkpoint exists, but no feasibility review between Gate B and checkpoint.

- [ ] **Step 3: Update `skills/samvil-design/SKILL.md`**

Insert a new section before current Step 4/User Checkpoint with content shaped like:

```md
## Step 3b: Blueprint Feasibility Check

Run a lightweight feasibility review before the user sees the final blueprint.

Agent(
  description: "SAMVIL Blueprint feasibility check",
  model: config.model_routing.design_reviewer || config.model_routing.default || "haiku",
  prompt: "You are a build feasibility reviewer.

Read the final blueprint draft and answer:
1. Are all key_libraries realistically installable and maintainable?
2. Is the tech stack self-consistent with SAMVIL scaffold conventions?
3. Are there known compatibility risks?
4. Is the component/screen scope realistic for this build?

Return one of:
- GO
- CONCERN: <list>
- BLOCKER: <list>

Keep the response under 200 words.",
  subagent_type: "general-purpose"
)

If result is CONCERN or BLOCKER:
- revise the blueprint in the main session
- append `blueprint_feasibility_checked` and `blueprint_concern` events to `.samvil/events.jsonl`
- only then present the final blueprint to the user
```

Also update the existing user checkpoint copy so it explicitly presents the **post-feasibility** blueprint.

- [ ] **Step 4: Update README design-stage explanation**

Add a short bullet in `README.md` describing that SAMVIL now checks blueprint feasibility before build, without changing the user approval rule.

Suggested text:

```md
- 설계 단계 끝에서 blueprint를 한 번 더 점검해요.
  - 라이브러리/구조 충돌이 없는지
  - 지금 범위에서 현실적으로 만들 수 있는지
  - 문제 있으면 빌드 전에 바로 수정해요
```

- [ ] **Step 5: Review changed files for flow correctness**

Check:
- user checkpoint still exists
- feasibility runs before user approval
- main session remains the writer of blueprint/state/events

- [ ] **Step 6: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-design/SKILL.md "$CACHE/skills/samvil-design/SKILL.md"
cp README.md "$CACHE/README.md"
```

- [ ] **Step 7: Commit**

```bash
git add skills/samvil-design/SKILL.md README.md
git commit -m "improve: add blueprint feasibility gate before approval"
```

---

### Task 2: Add structured build and fix events with categories

**Files:**
- Modify: `skills/samvil-build/SKILL.md`
- Modify: `README.md`
- Test: grep review of new event names in build skill

- [ ] **Step 1: Write the failing event schema expectation**

```json
{"type":"build_fail","attempt":3,"scope":"feature:dashboard","error_signature":"Module not found: x","error_category":"import_error","touched_files":["app/page.tsx"],"ts":"2026-04-09T00:00:00Z"}
{"type":"build_pass","attempt":4,"scope":"integration","ts":"2026-04-09T00:00:10Z"}
{"type":"fix_applied","scope":"feature:dashboard","error_category":"type_error","summary":"replace invalid prop type","files":["components/dashboard/Card.tsx"],"ts":"2026-04-09T00:00:20Z"}
```

- [ ] **Step 2: Verify the current build skill lacks these events**

Run: `grep -n "build_fail\|build_pass\|fix_applied\|error_category" skills/samvil-build/SKILL.md`
Expected: no matches for the new event schema.

- [ ] **Step 3: Extend `skills/samvil-build/SKILL.md` core build verification section**

Add explicit event emission instructions after each build verify step in core, feature, and integration contexts.

Use code blocks like:

```md
On build failure, append:
{"type":"build_fail","attempt":<N>,"scope":"core|feature:<name>|integration","error_signature":"<brief normalized error>","error_category":"import_error|type_error|config_error|runtime_error|dependency_error|unknown","touched_files":["<paths>"],"ts":"<ISO 8601>"}

On build success, append:
{"type":"build_pass","attempt":<N>,"scope":"core|feature:<name>|integration","ts":"<ISO 8601>"}
```

- [ ] **Step 4: Add fix event emission to retry/fix instructions**

After each line that currently appends to `.samvil/fix-log.md`, add a paired event instruction:

```md
Also append to `.samvil/events.jsonl`:
{"type":"fix_applied","scope":"core|feature:<name>","error_category":"<enum>","summary":"<brief fix summary>","files":["<paths>"],"ts":"<ISO 8601>"}
```

- [ ] **Step 5: Keep existing feature start/success/fail events but add optional category**

Update the existing `build_feature_fail` example to include optional `error_category`.

```json
{"type":"build_feature_fail","feature":"<name>","error":"<brief error>","error_category":"type_error","retry":1,"ts":"<ISO 8601>"}
```

- [ ] **Step 6: Document event categories in README**

Add a short note that build retries now leave structured event traces used by evolve/postmortem analysis.

- [ ] **Step 7: Validate event ownership is explicit**

Check `skills/samvil-build/SKILL.md` contains all three event names and the category enum.

- [ ] **Step 8: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-build/SKILL.md "$CACHE/skills/samvil-build/SKILL.md"
cp README.md "$CACHE/README.md"
```

- [ ] **Step 9: Commit**

```bash
git add skills/samvil-build/SKILL.md README.md
git commit -m "improve: add structured build and fix events"
```

---

### Task 3: Align QA taxonomy before any independent QA rollout

**Files:**
- Modify: `agents/qa-functional.md`
- Modify: `agents/qa-quality.md`
- Modify: `references/qa-checklist.md`
- Test: markdown diff review across files

- [ ] **Step 1: Write the failing taxonomy contract**

```md
Shared QA taxonomy must be:
- PASS
- PARTIAL
- UNIMPLEMENTED
- FAIL

Shared meanings:
- PARTIAL = evidence exists but static analysis cannot fully confirm
- UNIMPLEMENTED = stub/hardcoded/simulated/TODO path
- FAIL = broken, missing, unreachable, or contradicted by evidence
```

- [ ] **Step 2: Verify the current functional agent lacks `UNIMPLEMENTED`**

Run: `grep -n "UNIMPLEMENTED" agents/qa-functional.md references/qa-checklist.md skills/samvil-qa/SKILL.md`
Expected: matches in checklist and QA skill, but not in `agents/qa-functional.md`.

- [ ] **Step 3: Update `agents/qa-functional.md` grading table and examples**

Replace the current 3-state grading section with a 4-state version:

```md
| Grade | Meaning | Example |
|-------|---------|---------|
| PASS | AC is fully implemented and evidenced | Real UI + real state + reachable path |
| PARTIAL | Evidence exists but static analysis cannot fully verify runtime behavior | CSS feel, async timing, drag feel |
| UNIMPLEMENTED | Stub, hardcoded response, TODO path, simulated data | Fake AI response, sample-only persistence |
| FAIL | Missing, broken, unreachable, or contradicted by code | No implementation, dead code, missing state wiring |
```

Also update output format examples so at least one row shows `UNIMPLEMENTED`.

- [ ] **Step 4: Update `agents/qa-quality.md` to stay synthesis-friendly**

Add guidance that quality review must not reclassify functional implementation states, and should instead return:
- dimension score
- concrete issue list
- revise-trigger concerns

Add wording like:

```md
Do not re-score functional implementation status from Pass 2.
If you see a stub or missing core behavior, flag it as a quality concern and let the main session reconcile it with Pass 2 evidence.
```

- [ ] **Step 5: Tighten `references/qa-checklist.md` as SSOT**

Ensure the checklist explicitly defines `UNIMPLEMENTED` and includes one report example for it.
If wording already exists, refine it so agent authors cannot confuse `UNIMPLEMENTED` with `FAIL`.

- [ ] **Step 6: Review for cross-file consistency**

Check the same taxonomy words and meanings appear consistently in:
- `agents/qa-functional.md`
- `agents/qa-quality.md`
- `references/qa-checklist.md`

- [ ] **Step 7: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp agents/qa-functional.md "$CACHE/agents/qa-functional.md"
cp agents/qa-quality.md "$CACHE/agents/qa-quality.md"
cp references/qa-checklist.md "$CACHE/references/qa-checklist.md"
```

- [ ] **Step 8: Commit**

```bash
git add agents/qa-functional.md agents/qa-quality.md references/qa-checklist.md
git commit -m "improve: align QA taxonomy before independent review"
```

---

### Task 4: Add independent Pass 2 and Pass 3 for standard+ tiers

**Files:**
- Modify: `skills/samvil-qa/SKILL.md`
- Modify: `README.md`
- Test: markdown review of tier branching and synthesis path

- [ ] **Step 1: Write the failing QA architecture contract**

```md
minimal:
- Pass 1 main
- Pass 2 main
- Pass 3 main

standard+:
- Pass 1 main
- Pass 2 independent agent
- Pass 3 independent agent
- final verdict/report/state/events main only
```

- [ ] **Step 2: Verify the current QA skill has no tier branch for pass ownership**

Run: `grep -n "selected_tier\|standard\|Pass 2\|Pass 3" skills/samvil-qa/SKILL.md`
Expected: selected tier exists, but no branch that changes pass execution ownership.

- [ ] **Step 3: Add tier-based execution branch to `skills/samvil-qa/SKILL.md`**

Insert a section before Pass 2 describing:

```md
## QA Execution Mode by Tier

- `minimal`: run Pass 2 and Pass 3 inline in the main session
- `standard`, `thorough`, `full`: keep Pass 1 in the main session, then spawn:
  - one independent `qa-functional` agent for Pass 2
  - one independent `qa-quality` agent for Pass 3

The main session is the only writer of:
- `.samvil/qa-report.md`
- `project.state.json`
- `.samvil/events.jsonl`
- overall verdict
```

- [ ] **Step 4: Add Pass 2 independent agent prompt block**

Add a concrete agent template like:

```md
Agent(
  description: "SAMVIL QA Pass 2: independent functional verification",
  model: config.model_routing.qa || config.model_routing.default || "opus",
  prompt: "You are an independent QA judge for SAMVIL Pass 2.

<paste agents/qa-functional.md>

## Context
- Seed: <seed JSON>
- Project path: ~/dev/<seed.name>/

## Task
Verify every acceptance criterion with skeptical, evidence-first review.
You did not write this code.
Do not write files.
Return a markdown section using the required output format.",
  subagent_type: "general-purpose"
)
```

- [ ] **Step 5: Add Pass 3 independent agent prompt block**

Add a concrete agent template like:

```md
Agent(
  description: "SAMVIL QA Pass 3: independent quality verification",
  model: config.model_routing.qa || config.model_routing.default || "opus",
  prompt: "You are an independent QA judge for SAMVIL Pass 3.

<paste agents/qa-quality.md>

## Context
- Seed: <seed JSON>
- Project path: ~/dev/<seed.name>/

## Task
Review responsive design, accessibility basics, code structure, and UX polish.
You did not write this code.
Do not write files.
Return a markdown section using the required output format.",
  subagent_type: "general-purpose"
)
```

- [ ] **Step 6: Add main-session synthesis rules**

Document exactly how the main session merges results:

```md
### Central Synthesis Rules
1. Read Pass 1 result from main-session checks
2. Read Pass 2 markdown returned by independent agent
3. Read Pass 3 markdown returned by independent agent
4. Apply verdict matrix from `references/qa-checklist.md`
5. Write `.samvil/qa-report.md`
6. Append `qa_partial`, `qa_unimplemented`, and `qa_verdict` events
7. Update `project.state.json`
```

- [ ] **Step 7: Preserve minimal-tier behavior explicitly**

Add an explicit note:

```md
For `minimal`, keep the current inline QA flow unchanged to preserve the existing user experience and cost profile.
```

- [ ] **Step 8: Update README tier explanation**

Add a brief note that standard+ tiers use stricter independent QA while minimal keeps the lightweight path.

- [ ] **Step 9: Review for SSOT rule**

Check the skill states clearly that agents gather evidence only and the main session alone decides and persists.

- [ ] **Step 10: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-qa/SKILL.md "$CACHE/skills/samvil-qa/SKILL.md"
cp README.md "$CACHE/README.md"
```

- [ ] **Step 11: Commit**

```bash
git add skills/samvil-qa/SKILL.md README.md
git commit -m "improve: add tier-gated independent QA synthesis"
```

---

### Task 5: Emit structured QA events during central synthesis

**Files:**
- Modify: `skills/samvil-qa/SKILL.md`
- Test: grep review of QA event instructions

- [ ] **Step 1: Write the failing QA event expectation**

```json
{"type":"qa_partial","criterion":"Tasks persist on refresh","reason":"static analysis cannot verify runtime persistence","source":"pass2","ts":"2026-04-09T00:00:00Z"}
{"type":"qa_unimplemented","criterion":"AI summary generation","reason":"hardcoded sample response","is_core_experience":false,"ts":"2026-04-09T00:00:05Z"}
{"type":"qa_verdict","verdict":"REVISE","iteration":1,"pass1":"PASS","pass2":"REVISE","pass3":"PASS","ts":"2026-04-09T00:00:10Z"}
```

- [ ] **Step 2: Verify the current QA skill lacks the new event names**

Run: `grep -n "qa_partial\|qa_unimplemented\|qa_verdict" skills/samvil-qa/SKILL.md`
Expected: `qa_verdict` exists, new partial/unimplemented events do not.

- [ ] **Step 3: Add event emission rules to synthesis section**

In the report-writing or verdict section, add instructions like:

```md
For each Pass 2 item marked PARTIAL, append:
{"type":"qa_partial","criterion":"<AC>","reason":"<brief>","source":"pass2","ts":"<ISO 8601>"}

For each Pass 2 item marked UNIMPLEMENTED, append:
{"type":"qa_unimplemented","criterion":"<AC>","reason":"<brief>","is_core_experience":<true|false>,"ts":"<ISO 8601>"}
```

Also allow Pass 3 concerns that are evidence-limited to emit `qa_partial` with `source":"pass3"`.

- [ ] **Step 4: Ensure event ownership stays central**

Add wording:

```md
Independent QA agents never append events directly.
The main session emits QA events after synthesizing returned evidence.
```

- [ ] **Step 5: Validate by grep review**

Check that `skills/samvil-qa/SKILL.md` contains all three event names and central-ownership language.

- [ ] **Step 6: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-qa/SKILL.md "$CACHE/skills/samvil-qa/SKILL.md"
```

- [ ] **Step 7: Commit**

```bash
git add skills/samvil-qa/SKILL.md
git commit -m "improve: add structured QA synthesis events"
```

---

### Task 6: Feed build/fix/event artifacts into evolve analysis

**Files:**
- Modify: `skills/samvil-evolve/SKILL.md`
- Modify: `agents/wonder-analyst.md`
- Modify: `README.md`
- Test: markdown review of evolve prompts and inputs

- [ ] **Step 1: Write the failing evolve context expectation**

```md
Wonder must read:
- `.samvil/build.log`
- `.samvil/fix-log.md`
- `.samvil/events.jsonl`

Wonder must prioritize:
- repeated error signatures
- repeated error categories
- reverted or compensating fixes
- workaround patterns that suggest spec problems
```

- [ ] **Step 2: Verify the current wonder agent does not read the full artifact set**

Run: `grep -n "build.log\|fix-log\|events.jsonl\|error_signature\|error_category" skills/samvil-evolve/SKILL.md agents/wonder-analyst.md`
Expected: limited or no matches for the new artifact-driven framing.

- [ ] **Step 3: Update `skills/samvil-evolve/SKILL.md` wonder prompt**

Expand the existing agent prompt so it explicitly includes:

```md
## Additional Ground Truth
Read these files if they exist:
- .samvil/build.log
- .samvil/fix-log.md
- .samvil/events.jsonl

Use them to identify:
- repeated error signatures
- repeated error categories
- reverted fixes
- workaround patterns that indicate a spec issue instead of an implementation issue
```

- [ ] **Step 4: Update `agents/wonder-analyst.md` inputs and framework**

Add the new files to the input list and extend the analysis framework with a section like:

```md
5. Build Failure Patterns
   - Which error categories repeated?
   - Which files were touched repeatedly?
   - Did fixes change symptoms without removing the root cause?
```

Also change the role language so it reads like a **postmortem analyst for this run**, not a literal owner of past work.

- [ ] **Step 5: Add README note for evolve**

Document that evolve now reads structured build and QA traces to propose better next-step seed improvements.

- [ ] **Step 6: Review for artifact-first wording**

Check both files make events/build/fix artifacts ground truth, not optional flavor text.

- [ ] **Step 7: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-evolve/SKILL.md "$CACHE/skills/samvil-evolve/SKILL.md"
cp agents/wonder-analyst.md "$CACHE/agents/wonder-analyst.md"
cp README.md "$CACHE/README.md"
```

- [ ] **Step 8: Commit**

```bash
git add skills/samvil-evolve/SKILL.md agents/wonder-analyst.md README.md
git commit -m "improve: feed build event traces into evolve analysis"
```

---

### Task 7: v0.5.0 release — feasibility + events + taxonomy

**Scope:** Tasks 1–3, 5–6 까지의 변경을 v0.5.0으로 릴리즈.

Independent QA (Task 4)는 아직 포함하지 않는다.
Taxonomy 정렬과 event schema가 먼저 검증되어야 하기 때문.

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Test: version sync review

- [ ] **Step 1: Decide version bump level**

Apply the project rule from `CLAUDE.md`:
- feasibility check, event schema, taxonomy changes are visible
- but independent QA is NOT included yet
- therefore this is a **MINOR** version bump

Target version:

```json
“version”: “0.5.0”
```

- [ ] **Step 2: Update plugin manifest version**

Modify `.claude-plugin/plugin.json` version field to `0.5.0`.

- [ ] **Step 3: Sync README title/version**

Update the first line of `README.md` from:

```md
# SAMVIL — AI 바이브코딩 하네스 `v0.4.0`
```

to:

```md
# SAMVIL — AI 바이브코딩 하네스 `v0.5.0`
```

- [ ] **Step 4: Add v0.5.0 release-note bullets to README**

Cover:
- blueprint feasibility check before user approval
- structured build/evolve event trace analysis
- QA taxonomy alignment (PASS/PARTIAL/UNIMPLEMENTED/FAIL)

Do NOT mention independent QA yet — that's v0.6.0.

- [ ] **Step 5: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp .claude-plugin/plugin.json “$CACHE/.claude-plugin/plugin.json”
cp README.md “$CACHE/README.md”
```

- [ ] **Step 6: Review version sync**

Check the manifest and README version match exactly.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/plugin.json README.md
git commit -m “chore: bump to v0.5.0 — feasibility + events + taxonomy”
```

---

### Task 8: v0.6.0 release — independent QA for standard+

**Scope:** Task 4 (Independent QA)를 별도 v0.6.0으로 릴리즈.

v0.5.0의 taxonomy와 event schema가 검증된 후에 진행.

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Test: version sync review

- [ ] **Step 1: Decide version bump level**

- independent QA changes visible behavior for standard+ users
- therefore this is a **MINOR** version bump

Target version:

```json
“version”: “0.6.0”
```

- [ ] **Step 2: Update plugin manifest version**

Modify `.claude-plugin/plugin.json` version field to `0.6.0`.

- [ ] **Step 3: Sync README title/version**

Update to `v0.6.0`.

- [ ] **Step 4: Add v0.6.0 release-note bullets to README**

Cover:
- independent Pass 2/3 QA for standard+ tiers
- minimal tier unchanged
- “Independent Evidence, Central Verdict” architecture

- [ ] **Step 5: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp .claude-plugin/plugin.json “$CACHE/.claude-plugin/plugin.json”
cp README.md “$CACHE/README.md”
```

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json README.md
git commit -m “chore: bump to v0.6.0 — independent QA for standard+”
```

---

### Task 9: Validate rollout with minimal vs standard A/B review

**Files:**
- Modify: `README.md` (optional, only if documenting validation approach is useful)
- Test: manual validation checklist using the updated docs/skills

- [ ] **Step 1: Write the validation matrix to run after implementation**

```md
Validation matrix:
- Same seed
- Same generated codebase
- A: minimal tier (inline QA)
- B: standard tier (independent Pass 2/3)

Compare:
1. issue count found
2. false positives
3. missed issues
4. elapsed time
5. token usage
6. verdict consistency
7. fix-list actionability
```

- [ ] **Step 2: Run document-level dry review of all changed files**

Read through:
- `skills/samvil-design/SKILL.md`
- `skills/samvil-build/SKILL.md`
- `skills/samvil-qa/SKILL.md`
- `skills/samvil-evolve/SKILL.md`
- `agents/qa-functional.md`
- `agents/qa-quality.md`
- `agents/wonder-analyst.md`
- `references/qa-checklist.md`
- `README.md`

Expected: ownership and taxonomy are consistent everywhere.

- [ ] **Step 3: Run targeted grep verification commands**

Run:
```bash
grep -n "blueprint_feasibility_checked\|blueprint_concern" skills/samvil-design/SKILL.md
grep -n "build_fail\|build_pass\|fix_applied\|error_category" skills/samvil-build/SKILL.md
grep -n "qa_partial\|qa_unimplemented\|central synthesis\|minimal" skills/samvil-qa/SKILL.md
grep -n "UNIMPLEMENTED" agents/qa-functional.md references/qa-checklist.md
grep -n "events.jsonl\|fix-log\|build.log" skills/samvil-evolve/SKILL.md agents/wonder-analyst.md
```
Expected: every grep returns the new lines.

- [ ] **Step 4: Capture validation notes for rollout decision**

Write a short note in the working session or commit description answering:
- Did minimal remain unchanged?
- Did standard+ clearly become stricter?
- Is central verdict ownership preserved?
- Are event emit points explicit?

- [ ] **Step 5: Commit**

```bash
git add skills/samvil-design/SKILL.md skills/samvil-build/SKILL.md skills/samvil-qa/SKILL.md skills/samvil-evolve/SKILL.md agents/qa-functional.md agents/qa-quality.md agents/wonder-analyst.md references/qa-checklist.md README.md .claude-plugin/plugin.json
git commit -m "improve: finalize independent evidence QA rollout"
```

---

## Spec Coverage Check

- Blueprint feasibility before approval: covered by Task 1
- Structured event schema and emit ownership: covered by Tasks 2 and 5
- Taxonomy alignment before independent QA: covered by Task 3
- Independent QA only for standard+: covered by Task 4
- Evolve artifact-driven analysis: covered by Task 6
- Version/README sync (v0.5.0 — feasibility+events+taxonomy): covered by Task 7
- Version/README sync (v0.6.0 — independent QA): covered by Task 8
- A/B validation matrix: covered by Task 9
- Plugin cache sync: covered in every Task commit step

No uncovered requirements remain.

## Version Release Plan

| Version | Tasks | Content |
|---------|-------|---------|
| v0.5.0 | 1, 2, 3, 5, 6, 7 | Feasibility + Event Schema + Taxonomy |
| v0.6.0 | 4, 8 | Independent QA + Release |
| (validation) | 9 | A/B comparison after both releases |

## Placeholder Scan

Checked for forbidden placeholders:
- No `TODO`
- No `TBD`
- No “write tests for the above” style placeholders
- Each task names exact files and exact commands

## Type / Naming Consistency Check

Shared names used consistently:
- `blueprint_feasibility_checked`
- `blueprint_concern`
- `build_fail`
- `build_pass`
- `fix_applied`
- `qa_partial`
- `qa_unimplemented`
- `qa_verdict`
- `error_category`
- `Independent Evidence, Central Verdict`

---

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
