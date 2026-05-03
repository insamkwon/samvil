---
name: samvil-build
description: "Build core experience + features from seed. Circuit breaker per feature. Context Kernel sync on every step."
---

# samvil-build (ultra-thin)

Adopt the **Full-Stack Developer** role. Boot pre-flight, per-batch
dispatch, and post-stage contract layer are aggregated by three MCP
tools. CC-specific Agent spawn (parallel chunk in one message) and
`npm run build` shell-out stay here — host-bound (P8). Per-`solution_type`
Korean prose, code-quality rules, anti-patterns, and verbatim
Phase A/B/Z bodies live in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. Read `project.seed.json`, `project.state.json`, `project.config.json`, `project.blueprint.json` (if present), `decisions.log` (if present).
2. **TaskUpdate** "Build" → `in_progress`.
3. **v3.2 Contract Layer — stage entry**: `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="build_started", stage="build", data="{}")`. Best-effort; auto-claims `evidence_posted subject="stage:build"`.
4. **L1 trace — stage start** (best-effort, INV-5): `mcp__samvil_mcp__trace_write(project_root=".", stage="build", action="stage_start", skill="samvil-build", result="ok", details_json="{}")`.

## Phase A — Core Experience

```
mcp__samvil_mcp__aggregate_build_phase_a(project_path="~/dev/<seed.name>", run_sanity_checks=true)
```

Returns `solution_type`, `framework`, `build_verify {command, log_path, language}`, `recipe_path`, `paths {handoff, fix_log, events, rate_budget, sanity_log}`, `sanity {passed, failures[], warnings[]}`, `resume_hint {completed_features, current_model_build}`, `errors[]`, `notes[]`. On `error`: `⚠ MCP unreachable`, fall back to `SKILL.legacy.md` Phase A boot/recipe lookup (P8, INV-5).

Read `recipe_path`. Build core_experience per legacy `### solution_type: "<type>"` (web-app/game/automation/mobile-app/dashboard). **Build verify (INV-2)**: `cd ~/dev/<seed.name> && <build_verify.command> > <build_verify.log_path> 2>&1; echo "Exit code: $?"`.

**Module Boundary pre-check (M1)**: if `.samvil/modules/` exists, run `enforce_boundary(project_root="~/dev/<seed.name>", module_name="<feature>")` for the feature's module. If `violation_count > 0`, surface violations in worker prompt so it avoids cross-module imports.

**Circuit Breaker (MAX_RETRIES=2)**:
- PASS → `save_event(event_type="build_pass", data='{"attempt":N,"scope":"core"}')`. Per-feature passes use `"scope":"feature:<name>"`; Step 4 integration build uses `"scope":"integration"`.
- FAIL → `tail -30 <log_path>` → fix → retry. Append `[core] <error> → <fix>` to `<paths.fix_log>`. Emit `event_type="build_fail"` with `"error_signature"`, `"error_category"` (one of `` `import_error` ``, `` `type_error` ``, `` `config_error` ``, `` `runtime_error` ``, `` `dependency_error` ``, `` `unknown` ``), and `"touched_files"` (legacy §"Structured Build Event Schema"); emit `event_type="fix_applied"` per fix.
- 2 fails → AskUserQuestion "Adaptive Tier 제안" (legacy Phase A circuit-breaker block). Approve → upgrade `config.selected_tier`, set `state.current_stage="council"`, re-invoke `samvil-council`. Decline → STOP, report user (P10).
**Phase A.5 — AC index** (best-effort, INV-5): `mcp__samvil_mcp__index_ac_tree(project_root=".", features_json=<json.dumps(seed.features)>)` — builds `.samvil/ac-search.db`; enables Phase B BM25 leaf fetch without full tree JSON for large seeds.

## Phase B — AC Tree Execution (per feature)

For each feature in `seed.features` not in `resume_hint.completed_features`:

**Reset rate budget at start** even when resuming: `rate_budget_reset(budget_path="<paths.rate_budget>")`. If `previous.active > 0` → emit `rate_budget_stale_recovery` event (legacy §"Rate budget lifecycle").

### Loop until `tree_progress.all_done`

1. **Per-batch dispatch**:
   ```
   mcp__samvil_mcp__dispatch_build_batch(seed_json=<seed>, feature_json=<feature>, feature_num=<i+1>,
     tree_json=<current tree>, completed_ids_json=<json>, blueprint_json=<bp or "">,
     config_json=<cfg or "">, consecutive_fail_batches=<int from prior iter or checkpoint>)
   ```
   Returns `max_parallel`, `parallel_meta`, `batch {leaves[], count}`, `worker_bundles[]` (≤2000 tok: persona pointer + ≤400-tok context + leaf + contract), `independence`, `circuit_breaker {consecutive_fail_batches, max_retries, halt}`, `notes`, `errors`.
   **BM25 leaf fetch** (best-effort, INV-5): `mcp__samvil_mcp__search_ac_tree_by_feature(project_root=".", feature_id="<feature.id>")` — use instead of full tree JSON for large (10+ feature) seeds.

2. If `batch.count == 0` or `circuit_breaker.halt == true`: break.

3. **L2 checkpoint + Agent spawn**. Per leaf in batch: `mcp__samvil_mcp__write_leaf_checkpoint(project_root=".", feature_id="<feature.id>", leaf_id="<leaf.id>", leaf_description="<leaf.description>")` (best-effort, INV-5). Then **Agent spawn — single message, parallel chunk** (CC-specific, host-bound): Agent tool call `description="SAMVIL Build: AC <leaf.id>"`, `subagent_type="general-purpose"`, `model=<resume_hint.current_model_build or "sonnet">`, `prompt=<bundle text verbatim>`. Emit all calls in ONE assistant message → parallel. Worker contract (in bundle): only edit `components/<feature>/` (or stack-equivalent), run `npx tsc --noEmit | head -20 && npx eslint . --quiet | head -20`, do **NOT** run `npm run build`, reply with parse block (`Leaf:/files_created:/files_modified:/typecheck_ok:/lint_ok:/notes:`).

4. **Parse + persist** per worker reply:
   - `status = "pass" if (typecheck_ok and files_created)` else `"fail"`.
   - `update_leaf_status(ac_tree_json=<tree>, leaf_id=<id>, status=<s>, evidence_json=<files>)` → use returned `tree` field as next `tree_json`.
   - Append id to `completed_ids`; `rate_budget_release(worker_id="build-<id>")`; `save_event(event_type="ac_leaf_complete", data='{"feature":"<n>","leaf_id":"<id>","status":"<s>"}')`.
   - **L1 trace** (best-effort, INV-5): `mcp__samvil_mcp__trace_write(project_root=".", stage="build", action="leaf_complete", skill="samvil-build", result="<status>", details_json='{"feature":"<n>","leaf_id":"<id>"}')`.

5. **HUD + checkpoint**: `print(json.loads(render_ac_tree_hud(ac_tree_json=tree_json))["ascii"])`; `save_checkpoint(seed_id="<sid>", phase="build", state_json=<{feature, completed_ids, tree_json, consecutive_fail_batches}>)`.

6. **Update breaker**: `consecutive_fail_batches = (prior+1) if all_failed_this_batch else 0`. Carry into next iter's dispatch call. ≥2 → emit `build_feature_fail` event, break feature loop (remaining leaves stay `pending`); next feature still runs.

### Step 4 — Integration build per feature

After loop ends (success or breaker), run `npm run build > .samvil/build.log 2>&1` **once per feature** (per-leaf workers only ran `tsc --noEmit`). Cross-feature integration regressions caught here. Mandatory; do NOT skip.

### Step 5 — Persist tree into seed

Write `tree_json` (minus transients) back into `seed.features[i].acceptance_criteria` (status is now SSOT for QA).

### Step 6 — Per-feature rate-budget summary

`save_event(event_type="rate_budget_summary", data=<rate_budget_stats(...) merged with {feature}>)`.

## Phase Z — post_stage Contract Layer

```
mcp__samvil_mcp__finalize_build_phase_z(project_path="~/dev/<seed.name>",
  rate_budget_stats_json=<stats JSON or "">, failed_features_json=<JSON array or "">,
  retries=<total retries this stage>)
```

Returns `samvil_tier`, `metrics {features_total/passed/failed, implementation_rate, total/passed/failed/pending leaves}`, `ac_verdict_claims[]` (one per `pass` leaf, payloads ready for `claim_post`), `stage_claim_id`, `gate_input`, `stagnation_hint`, `handoff_block`, `notes`, `errors`.

Apply in order (each best-effort, INV-5):
1. For each `ac_verdict_claims` entry: `mcp__samvil_mcp__claim_post(**entry)` — leaves stay `pending` until QA's Judge verifies.
2. If `stage_claim_id`: `mcp__samvil_mcp__claim_verify(claim_id=<id>, verified_by="agent:user")`.
3. `mcp__samvil_mcp__gate_check(gate_name="build_to_qa", samvil_tier=<tier>, metrics_json=<gate_input>, project_root=".")`. `verdict=block` → halt; emit `required_action`, append handoff, exit. `verdict=pass` → record `gate_verdict` claim + proceed.
4. If `stagnation_hint.evaluate == true` (2nd+ build pass with errors): `mcp__samvil_mcp__stagnation_evaluate(input_json=<stagnation_hint.payload>)`. `severity=HIGH` → halt build, invoke `lateral_propose` for the failure signature; do NOT chain to QA until clears.

## Chain to QA (INV-4)

1. Append `handoff_block` (already-rendered Korean) to `.samvil/handoff.md` via Bash `cat >>` or Edit (**never Write tool**).
2. **TaskUpdate** "Build" → `completed`. Print `[SAMVIL] Stage 5/5: Running QA verification...`.
3. **HostCapability**: claude-code → invoke the Skill tool with `samvil-qa`. Codex → write `.samvil/next-skill.json` `{"skill":"samvil-qa"}` and read `skills/samvil-qa/SKILL.md`.

## Anti-Patterns (preserved verbatim from legacy)

1. NO stub/mock/hardcoded API responses (Reward Hacking → automatic FAIL). Real `fetch` w/ `process.env.*`, Supabase client, real auth; `.env.example` placeholders only.
2. NO touching files outside the worker's feature folder (worker contract). Cross-feature edits go through Step 4 integration build.
3. NO dumping build logs into conversation — write to `.samvil/build.log`, only `tail -30` on failure.
4. NO skipping integration build (Step 4) — per-leaf `tsc --noEmit` does not catch cross-feature regressions.
5. NO adding features outside `seed.features` (Zero-Refactor Rule, P5). NO `@latest`, NO testing frameworks, NO premature `memo`/lazy, NO new README.md.
6. NO auto-retry past `MAX_RETRIES=2` (Circuit Breaker; P10).

## Code Quality (pointers to legacy)
- Web (Next.js + shadcn/ui): legacy §"Code Quality Rules" #1-11, 14-16 (`'use client'`, TS strict, PascalCase one-per-file, `@/components/ui/` shadcn-first, `cn()`, `@/` aliases, real content, empty states, hydration `mounted`, localStorage try-catch, Korean UX writing, 첫 30초 가치, premium gate).
- Game (Phaser + tsc --noEmit): legacy §"### solution_type: \"game\"" + §"Anti-Patterns".
- Mobile (Expo): legacy §"Code Quality Rules" #17-18 (`View`/`Text`/`TextInput`, `StyleSheet.create()`, 44px touch, Expo Router file-based).
- Automation/Dashboard: legacy §"### solution_type: \"automation\"" (`_run_dry`/`_run_live`, fixtures, env-based config, py_compile / tsc --noEmit, dry-run verification) + §"\"dashboard\"" + §"#### Dashboard Build Patterns".
## Legacy reference
Full per-`solution_type` Korean prose, Phase A.5 dependency pre-resolution, Phase A.6 sanity details, dependency-planning Step 2.5, MAX_PARALLEL formula, independence checklist, worker bundle template, progress trim format, Output Format blocks: see `SKILL.legacy.md`.
