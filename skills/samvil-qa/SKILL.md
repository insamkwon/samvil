---
name: samvil-qa
description: "3-pass verification against seed acceptance criteria. Ralph loop for auto-fix. Verdict: PASS/REVISE/FAIL."
---

# samvil-qa (ultra-thin)

Adopt the **QA Judge** role. Boot pre-flight, Pass 1/1b digest, and Phase Z (synthesis + claim verify/reject + gate + consensus + handoff + next-skill) are aggregated by three MCP tools. Playwright MCP calls (Pass 1b smoke, Pass 2 runtime), independent Pass 2/3 `Agent()` spawns (standard+ tiers), per-leaf `semantic_check` + `validate_evidence` (Pass 2.5), and the Ralph Loop iteration counter stay here — host-bound (P8). Per-`solution_type` Korean prose, verbatim Pass 1/1b/2/2.5/3 bodies, anti-patterns, and output format live in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. **TaskUpdate** "QA" → `in_progress`.
2. ```
   mcp__samvil_mcp__aggregate_qa_boot_context(project_path=".")
   ```
   Returns `solution_type`, `framework`, `seed_loaded`, `brownfield`, `pass1 {command, log_path, language, smoke}`, `qa_checklist_path`, `paths {seed,state,build_log,qa_results,qa_evidence_dir,handoff,events,fix_log,next_skill_marker,qa_routing}`, `role_separation_check {claimed_by:"agent:build-worker", verified_by:"agent:qa-functional"}`, `incremental_hint`, `resume_hint {session_id,selected_tier,qa_max_iterations,current_model_qa,qa_history_length,stage_claims}`, `notes[]`, `errors[]`. On `error` or `brownfield=true`: `⚠ MCP unreachable / brownfield`, fall back to `SKILL.legacy.md` "Boot Sequence" + "Seed 없는 경우" (P8, INV-5).
3. **v3.2 Contract Layer — stage entry** (best-effort, all per `references/contract-layer-protocol.md`):
   - `route_task(task_role="qa-functional", project_root=".", attempts=0)` → record into `state.current_model_qa`.
   - `validate_role_separation(**boot.role_separation_check)` → must return `valid=true`. If not: halt + escalate.
   - `claim_post(claim_type="evidence_posted", subject="stage:qa", statement="qa stage entered at tier=<tier>", authority_file="state.json", claimed_by="agent:qa-functional", evidence_json='["project.state.json"]')` → record `state.stage_claims.qa`.
   - `save_event(event_type="qa_started", stage="qa", data="{}")`.
4. **Pattern + Domain Packs** (best-effort): `render_pattern_context(...)` + `render_domain_context(stage="qa")` for `qa_focus` + risk checks.
5. **Incremental QA**: if `incremental_hint.present` and no `--full-qa` flag, plan to re-verify only features whose `seed_hash` changed (legacy "Incremental QA"). Else verify all.

## Ralph Loop Driver (max `boot.resume_hint.qa_max_iterations`, default 3)

### 1. Pass 1 + Pass 1b — run + digest

Shell `boot.pass1.command` (web-app/dashboard `npm run build`; game `npx tsc --noEmit && npm run build`; mobile-app `npx expo export --platform web`; automation `python -m py_compile` / `npx tsc --noEmit`). Capture exit code.

If `boot.pass1.smoke` is `playwright`/`-canvas`/`-mobile`: drive Playwright MCP per legacy `## Pass 1b: Playwright Smoke Run` for the matching solution_type — `browser_navigate` → `browser_console_messages(level="error")` → `browser_evaluate(...body length)` → `browser_take_screenshot` per route. Collect `{method, console_errors[], empty_routes[], screenshots[], fallback_reason}`. **Fallback**: 2 retries fail → `method="static"` + `fallback_reason="Playwright unavailable after 2 retries"` (P8). For automation: dry-run per legacy `### automation`, set `smoke_result=None`.

```
mcp__samvil_mcp__dispatch_qa_pass1_batch(project_path=".",
  pass1_exit_code=<int>, smoke_result_json=<JSON or "">,
  solution_type="<boot.solution_type>")
```

Returns `pass1`, `pass1b`, `should_proceed_to_pass2`, `verdict_reason`, `events[]`. Emit `events[]` via `save_event`. If `should_proceed_to_pass2 == false`: this iteration → REVISE; skip to step 4.

### 2. Pass 2 + Pass 2.5 — runtime AC verification

**Tier branch** per `boot.resume_hint.selected_tier`:
- **`minimal`** — inline per legacy `## Pass 2: Functional Verification`.
- **`standard` / `thorough` / `full`** — independent agents per legacy `### Spawn Pass 2 Independent Agent` + `### Spawn Pass 3 Independent Agent` (Agent tool, model `<resume_hint.current_model_qa.model_id or "sonnet">`, paste `agents/qa-functional.md` / `agents/qa-quality.md`, **agents do NOT write files** — main session is sole writer per legacy "Central Synthesis Rules").

For each Pass 2 leaf (legacy `### Pass 2 Tree Setup (v3.0.0+)`):
1. `tree_json = parse_ac_tree(ac_data_json=<feature.acceptance_criteria>)`.
2. Drive Playwright runtime per legacy `### Runtime Verification with Playwright MCP` (or static fallback per `### Fallback to Static Analysis`).
3. **Pass 2.5 Reward Hacking detection** per leaf evidence:
   - `validate_evidence(evidences_json=<["src/file:line",...]>, project_root=".")` — `all_valid=false` or `valid_count<1` → downgrade to FAIL (P1, E1).
   - `semantic_check(code=<snippet ±3 lines>, context_hint=<AC>)` — `risk_level=HIGH` → downgrade PASS/PARTIAL → FAIL; MEDIUM → PASS → PARTIAL with Socratic Questions surfaced.
4. `update_leaf_status(ac_tree_json=<tree>, leaf_id=<id>, status=<s>, evidence_json=<files+screenshots>)` → use returned `tree`.
5. `save_event(event_type="ac_verdict", data='{"feature":"...", "leaf_id":"...","status":"..."}')`.

After all leaves: `print(json.loads(render_ac_tree_hud(ac_tree_json=tree_json))["ascii"])`; append to `qa-report.md`.

### 3. Pass 3 — quality

`minimal` tier: inline per legacy `## Pass 3: Quality Verification` for solution_type. Higher tiers: returned by step-2 agent. Returns `{verdict: PASS/FAIL, issues[]}`. Performance CONCERN → REVISE (legacy rule, do not downgrade to informational).

### 4. Phase Z — synthesis + contract finalize

Build `evidence`:
```json
{"iteration":<N>, "max_iterations":<boot.resume_hint.qa_max_iterations>,
 "pass1":{"status":<pass1.status>,"issues":<pass1.errors>},
 "pass2":{"items":[<{id,criterion,verdict,evidence,method,reason}>...],"counts":{<computed>}},
 "pass3":<pass3>, "agent_writes":[]}
```

Query pending build claims: `claim_query_by_subject(project_root=".", subject_glob="<seed leaf id glob>")` (best-effort).

```
mcp__samvil_mcp__finalize_qa_verdict(project_path=".",
  evidence_json=<evidence>, pending_ac_claims_json=<query result or "[]">)
```

Returns `synthesis`, `convergence`, `claim_actions[]`, `consensus_triggers[]`, `gate_input` (qa_to_deploy), `blocked {detected, persistent_issue_ids}`, `next_skill_decision {verdict, suggested, reason, user_options}`, `handoff_block`, `samvil_tier`, `notes[]`, `errors[]`.

Apply in order (each best-effort, INV-5):
1. `materialize_qa_synthesis(project_root=".", synthesis_json=<finalize.synthesis>)` → writes qa-results.json, qa-report.md, events.jsonl, project.state.json.
2. For each `claim_actions[i]`: `action=="verify"` → `claim_verify(claim_id=<i.claim_id>, verified_by=<i.verified_by>, evidence_json=<i.evidence_json>)`; `action=="reject"` → `claim_reject(claim_id=<i.claim_id>, verified_by=<i.verified_by>, reason=<i.reason>)`. PARTIAL leaves claim pending (retro decides).
3. If `boot.resume_hint.stage_claims.qa`: `claim_verify(claim_id=<id>, verified_by="agent:product-owner")`.
4. For each `consensus_triggers[i]`: `consensus_trigger(input_json=<i.input_json>)`. `should_invoke=true` → 2-round resolver (legacy "consensus" rules) → `consensus_verdict` claim → use as final answer for that AC.
5. `gate_check(gate_name="qa_to_deploy", samvil_tier=<finalize.samvil_tier>, metrics_json=<finalize.gate_input.metrics>, project_root=".")`. `verdict=block` → REVISE (or FAIL if Ralph exhausted), emit `required_action.type`. `verdict=pass` → record `gate_verdict` claim → proceed.
6. If convergence is `blocked`/`failed`: `materialize_qa_recovery_routing(project_root=".")` → writes `<paths.qa_routing>` + `<paths.next_skill_marker>` for host continuation.

### 5. Iterate or terminate

- `verdict == PASS` → exit Ralph loop → "Chain on PASS".
- `finalize.blocked.detected == true` → `[SAMVIL] ✗ QA BLOCKED after iteration <N>` (legacy "BLOCKED" block), `save_event(event_type="qa_blocked", ...)`, exit Ralph, surface user options.
- `verdict == REVISE` and `iteration < qa_max_iterations` → fix per legacy `## Ralph Loop (if REVISE)` (read error, write fix, `npm run build > <paths.build_log> 2>&1`, append to `<paths.fix_log>`), append to state `qa_history`: `{iteration:<N>,verdict:"REVISE",issue_ids:[...]}`, increment iter. **Convergence rule**: each iter MUST reduce total issue count vs prior.
- `iteration >= qa_max_iterations` → FAIL → "Chain on FAIL".

## Chain on PASS / FAIL / BLOCKED (INV-4)

1. Append `finalize.handoff_block` to `<boot.paths.handoff>` via Bash `cat >>` or Edit (**never Write tool**).
2. Render console output per legacy `## On PASS — Offer Evolve or Chain to Retro` (PASS) or `## On FAIL (after 3 iterations)` (FAIL/BLOCKED) — Try-it line, 배포 방법, 배포 전 체크리스트, 3 user options.
3. `save_event(event_type="qa_verdict", data='{"verdict":"<PASS|REVISE|FAIL>","iteration":<N>,"pass1":"...","pass2":"...","pass3":"..."}')`.
4. **TaskUpdate** "QA" → `completed`. Print `[SAMVIL] Stage 5/5: QA complete`.
5. Chain per `finalize.next_skill_decision.suggested` — PASS→`samvil-deploy` (default) or `samvil-evolve` (auto-trigger: build_retries≥5, qa_history≥2, partial_count≥5); FAIL/BLOCKED→`samvil-retro` (default), surface `user_options` for evolve / manual.
6. **HostCapability**: claude-code → invoke the Skill tool with `<suggested>`. Codex → write `<boot.paths.next_skill_marker>` `{"skill":"<suggested>"}` and read `skills/<suggested>/SKILL.md`.

## Anti-Patterns (preserved verbatim from legacy)

1. NO accepting UNIMPLEMENTED for core_experience features — auto-promote to FAIL (E1, P1).
2. NO downgrading CONCERN to informational — performance CONCERN = REVISE.
3. NO full `npm run build` inside worker agents — workers run lint/typecheck only.
4. NO Evidence-less PASS — `validate_evidence` failure → automatic FAIL downgrade (P1).
5. NO Stub/Mock/hardcoded responses passing AC — `semantic_check` HIGH risk → automatic FAIL (Reward Hacking).
6. NO blind convergence — issue count must decrease per iteration; identical issue id sets across 2 iterations → BLOCKED (PHI-04).
7. NO independent agent writing files — main session is sole writer of qa-report.md, state.json, events.jsonl, qa-results.json.

## Legacy reference

Full per-`solution_type` Korean prose, verbatim Pass 1/1b/2/2.5/3 bodies (web/dashboard/game/mobile-app/automation), Pass 1b automation API connectivity probe (v3-027), Verdict Taxonomy (PASS/PARTIAL/UNIMPLEMENTED/FAIL with scores), Pass 2.5 downgrade matrix, Verification Questions in Checklist Items (v2.6.0+), Output Format blocks, incremental QA cache file format, brownfield AskUserQuestion, qa-checklist.md cross-references: see `SKILL.legacy.md`.
