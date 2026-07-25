---
name: samvil-qa
description: "3-pass verification against seed acceptance criteria. Ralph loop for auto-fix. Verdict: PASS/REVISE/FAIL. gate_override is unavailable without a trusted host adapter; blocked gates halt and force_proceed is forbidden."
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

If `boot.pass1.smoke` is `playwright`/`-canvas`/`-mobile`: drive Playwright MCP per legacy `## Pass 1b: Playwright Smoke Run` for the matching solution_type — `browser_navigate` → `browser_console_messages(level="error")` → `browser_evaluate(...body length)` → `browser_take_screenshot` per route. Collect `{method, console_errors[], empty_routes[], screenshots[], fallback_reason}`. **Fallback**: `RUNTIME_PROBE_RETRIES` from `references/decision-boundaries.md` exhausted → `method="static"` + an honest fallback reason (P8). For automation: dry-run per legacy `### automation`, set `smoke_result=None`.

```
mcp__samvil_mcp__dispatch_qa_pass1_batch(project_path=".",
  pass1_exit_code=<int>, smoke_result_json=<JSON or "">,
  solution_type="<boot.solution_type>")
```

Returns `pass1`, `pass1b`, `should_proceed_to_pass2`, `verdict_reason`, `events[]`. Emit `events[]` via `save_event`. If `should_proceed_to_pass2 == false`: this iteration → REVISE; skip to step 4.

### 2. Pass 2 + Pass 2.5 — runtime AC verification

**Tier branch** per `boot.resume_hint.selected_tier`:
- **`minimal`** — inline per legacy `## Pass 2: Functional Verification`.
- **`standard` / `thorough` / `full` / `deep`** — independent agents per legacy `### Spawn Pass 2 Independent Agent` + `### Spawn Pass 3 Independent Agent` (Agent tool, model `<resume_hint.current_model_qa.model_id or "sonnet">`, prompt은 `mcp__samvil_mcp__compose_agent_prompt(agent_names_json='["qa-functional"]' or `'["qa-quality"]'`, context_files_json=..., task=<legacy spawn 블록의 Task>)`로 조립 — `missing_agents` 시 `agents/*.md` 직접 paste 폴백(P8), **agents do NOT write files** — main session is sole writer per legacy "Central Synthesis Rules").

**병렬 배치 (W5.1, standard+ tier)**: 전체 leaf를 `mcp__samvil_mcp__compute_parallel_safety(leaves_json=<[{id,likely_files,shared_resources}]>)`로 판정 → `safety=true` leaf들은 `MAX_PARALLEL` chunk로 나눠 Pass 2 에이전트를 **ONE message에 병렬 스폰** (Build Phase B 패턴). Playwright runtime이 필요한 leaf와 `safety=false` leaf는 main session 순차 처리 (단일 브라우저 세션 제약).

For each Pass 2 leaf (legacy `### Pass 2 Tree Setup (v3.0.0+)`):
1. `tree_json = parse_ac_tree(ac_data_json=<feature.acceptance_criteria>)`.
2. Drive Playwright runtime per legacy `### Runtime Verification with Playwright MCP` (or static fallback per `### Fallback to Static Analysis`). **While driving, record each action as a step** (`{action:goto|click|fill|press|reload|expect_text|expect_visible|expect_no_console_errors, role/name or selector, contains/equals/value/key/url}`) keyed by leaf — this becomes the deliverable spec (B).
3. **Emit before contract validation (browser)**: after a feature's runtime steps are recorded, call `mcp__samvil_mcp__emit_ac_spec(...)` and write `tests/e2e/<feature>.spec.ts` before validating any auto-generated `verify.command` that targets that file. `empty_acs` must be revisited; never claim a path that has not been emitted.
4. **AC contract validation + Pass 2.5 Reward Hacking detection**: when a leaf has `verify`, call `mcp__samvil_mcp__collect_ac_verification(project_root=".", ac_id=<id>, verify_json=<verify>)` and include `{verify, mechanical_verification:<result>}` in its Pass 2 item. Current MCP hosts have no portable trusted process sandbox, so this call validates the command contract but returns `ran=false`; it never executes seed-authored commands or produces PASS. `finalize_qa_verdict` therefore forces every such leaf (including omitted Pass 2 leaves) to FAIL until a trusted runner exists. Host-driven Playwright observations and emitted test files remain useful diagnostic evidence, with file:line as secondary evidence, but cannot override that contract. Then per leaf evidence:
   - `validate_evidence(evidences_json=<["src/file:line",...]>, project_root=".")` — `all_valid=false` or `valid_count<1` → downgrade to FAIL (P1, E1).
   - `semantic_check(code=<snippet ±3 lines>, context_hint=<AC>, shell_command=<verify.command or "">, execution_log=<mechanical log or "">, runner_exit_code=<trusted runner exit code>)` — filtered output behind `| tail`/`| grep` without a trusted successful runner status is `EVIDENCE_FORM_MISMATCH`; log text cannot self-authenticate with `SAMVIL_EXIT`. `risk_level=HIGH` → downgrade PASS/PARTIAL → FAIL; MEDIUM → PASS → PARTIAL with Socratic Questions surfaced.
5. **Module Boundary validation (M1)**: if `.samvil/modules/` exists, run `validate_contract(project_root=".", module_name="<module>")` per relevant module. `valid=false` → surface contract errors as FAIL evidence.
6. `update_leaf_status(ac_tree_json=<tree>, leaf_id=<id>, status=<s>, evidence_json=<files+screenshots>)` → use returned `tree`.
7. `save_event(event_type="ac_verdict", data='{"feature":"...", "leaf_id":"...","status":"..."}')`.

After all leaves: `print(json.loads(render_ac_tree_hud(ac_tree_json=tree_json))["ascii"])`; append to `qa-report.md`. Browser deliverable specs were already emitted before their mechanical commands in step 3, so the user can rerun them with `npm test`.

**Adversarial pass (A3, standard+ browser)**: 해피패스 검증 중 발견한 버튼 role-name / input selector를 모아 `mcp__samvil_mcp__emit_adversarial_spec(project_root="~/dev/<seed.name>", buttons_json=<["증가","리셋",...]>, inputs_json=<["#title",...]>, base_path="/")` → `tests/e2e/adversarial.spec.ts` (연타/초장문/빈값/새로고침 → 콘솔에러·크래시 0 단언). 적대 테스트가 빨간불이면 AC엔 없던 결함 → REVISE 입력으로 처리. **Mechanical runtime evidence**: browser solution types must execute generated specs with `npm test > .samvil/qa.log 2>&1; qa_exit=$?; echo "SAMVIL_EXIT:${qa_exit}" >> .samvil/qa.log; test "$qa_exit" -eq 0`, then call `mcp__samvil_mcp__collect_stage_evidence(project_root=".", stage="qa")`. A missing/invalid `.samvil/test-results.json`, or a report with zero tests, means `runtime_verified=false`; do not infer runtime success from narrative Pass 2 verdicts.

**Evaluation principles (v4.23/v4.25, when `seed.evaluation_principles` present)**: After Pass 2 verdicts collected, call `mcp__samvil_mcp__score_acs_against_principles(ac_verdicts_json=<JSON list>, evaluation_principles_json=<seed.evaluation_principles JSON>)` — returns per-leaf `principle_hits`, `weighted_score`, `downgrade_recommended`. Apply downgrades verbatim (PASS→PARTIAL where flagged). Phase Z calls `mcp__samvil_mcp__evaluate_exit_conditions(seed_json, qa_state_json)`; `verdict_blocked=true` → verdict cannot be PASS this iteration.

### 3. Pass 3 — quality

`minimal` tier: inline per legacy `## Pass 3: Quality Verification` for solution_type. Higher tiers: returned by step-2 agent. Returns `{verdict: PASS/FAIL, issues[]}`. Performance CONCERN → REVISE (legacy rule, do not downgrade to informational).

### 4. Phase Z — synthesis + contract finalize

Build `evidence = {iteration, max_iterations, pass1{status,issues}, pass2{items[{id,criterion,verdict,evidence,method,reason}],counts}, pass3, agent_writes:[]}`. Load `.samvil/claims.jsonl` (best-effort) and select rows with `type="ac_verdict"`, `status="pending"`, and `subject` matching a current seed leaf id; pass that list as the pending build claims.

```
mcp__samvil_mcp__finalize_qa_verdict(project_path=".",
  evidence_json=<evidence>, pending_ac_claims_json=<query result or "[]">)
```

Returns `synthesis`, `convergence`, `claim_actions[]`, `consensus_triggers[]`, `gate_input` (qa_to_deploy), `blocked {detected, persistent_issue_ids}`, `next_skill_decision {verdict, suggested, reason, user_options}`, `handoff_block`, `samvil_tier`, `notes[]`, `errors[]`.

Apply in order (best-effort except the evidence-backed `gate_check`, INV-5):
1. `materialize_qa_synthesis(project_root=".", synthesis_json=<finalize.synthesis>)` → writes qa-results.json, qa-report.md, events.jsonl, project.state.json.
2. For each `claim_actions[i]`: `action=="verify"` → `claim_verify(claim_id=<i.claim_id>, verified_by=<i.verified_by>, evidence_json=<i.evidence_json>)`; `action=="reject"` → `claim_reject(claim_id=<i.claim_id>, verified_by=<i.verified_by>, reason=<i.reason>)`. PARTIAL leaves claim pending (retro decides).
3. If `boot.resume_hint.stage_claims.qa`: `claim_verify(claim_id=<id>, verified_by="agent:product-owner")`.
4. For each `consensus_triggers[i]`: `consensus_trigger(input_json=<i.input_json>)`. `should_invoke=true` → 2-round resolver (legacy "consensus" rules) → `consensus_verdict` claim → use as final answer for that AC.
5. Select the gate **after** `finalize.next_skill_decision.suggested` is known: `samvil-evolve` → `qa_to_evolve`; `samvil-deploy` → `qa_to_deploy` with `evidence_mode="mechanical"`; `samvil-retro` → `any_to_retro` with `metrics_json='{"always_run":true}'`; `samvil-qa` means `REVISE + convergence=continue`, so run no cross-stage gate, write no marker, and continue Ralph. Artifact-only `.samvil/qa.log` and `test-results.json` are model-writable and therefore never set trusted `runtime_verified`; deploy remains blocked until a trusted host receipt adapter exists. Mandatory tool error or any verdict other than exact `pass` (including `block`, `escalate`, `skip`, or unknown) → record the `gate_verdict`, surface the reason, and halt. `gate_override` is unavailable on current hosts and `force_proceed` is forbidden. Exact `verdict=pass` → record `gate_verdict` → proceed.
6. If convergence is `blocked`/`failed`: `materialize_qa_recovery_routing(project_root=".")` → writes `<paths.qa_routing>` + `<paths.next_skill_marker>` for host continuation.

### 5. Iterate or terminate

- `verdict == PASS` → exit Ralph loop → "Chain on PASS".
- `finalize.blocked.detected == true` → `[SAMVIL] ✗ QA BLOCKED after iteration <N>` (legacy "BLOCKED" block), `save_event(event_type="qa_blocked", ...)`, exit Ralph, surface user options.
- `verdict == REVISE` → **루프 판정은 MCP 소유 (W4.2)**: `mcp__samvil_mcp__evaluate_qa_convergence(project_root=".", synthesis_json=<step 4 evidence>)` → `gate_verdict`가 `continue`일 때만 fix per legacy `## Ralph Loop (if REVISE)` (read error, write fix, `npm run build > <paths.build_log> 2>&1`, append to `<paths.fix_log>`), append to state `qa_history`: `{iteration:<N>,verdict:"REVISE",issue_ids:[...]}`, increment iter. `blocked`(동일 이슈 반복 / 이슈 수 미감소 / A→B→A 진동 감지) → exit Ralph, `next_action` 그대로 사용자에게 표시. `failed` → "Chain on FAIL". LLM이 수렴 여부를 자체 판단하지 않는다 (P3).
- `iteration >= qa_max_iterations` → FAIL → "Chain on FAIL".

## Standalone QA Modes (v4.23/v4.25/v4.27)

When invoked with `--target=<seed|artifact>`, skip Ralph Loop entirely. Two modes:

- **`--target=seed` (v4.23/v4.25)**: evaluate the *seed* against its source interview via `mcp__samvil_mcp__evaluate_seed_against_interview(project_root=".", seed_json=<seed>)` → `{verdict, coverage_score, traced, untraced, details}`. Verdict thresholds: ≥0.85 + zero untraced constraints → PASS; ≥0.60 → PARTIAL; else FAIL. `claim_post(claim_type="seed_verdict", ...)`.
- **`--target=artifact` (v4.27 SKILL / v4.29 implementation)**: lightweight QA verdict for *any* artifact (code/doc/API response/test_output/screenshot/custom). Inputs: `--artifact=<path or text>`, `--quality-bar=<one-line criterion>`, `--artifact-type=<type>`. Call `mcp__samvil_mcp__score_artifact_against_quality_bar(artifact=<text>, quality_bar=<text>, artifact_type=<type>, pass_threshold=0.8, revise_threshold=0.4)` → `{score, verdict, dimensions{correctness,completeness,quality,intent_alignment,domain_specific}, suggestions[], loop_action}`. Render to user + next-step pointer (PASS→proceed; REVISE→address suggestions then re-run; FAIL→consider re-interview / re-design). No claim_post by default (caller can request).

Both modes skip deploy/retro chain — pure evaluation output. Use cases: seed mode for "is my seed faithful to interview" check; artifact mode for code review / doc review / API response inspection.

## Chain on PASS / FAIL / BLOCKED (INV-4)

1. Append `finalize.handoff_block` to `<boot.paths.handoff>` via Edit (**never Write tool or Bash redirection**).
2. Render console output per legacy `## On PASS — Offer Evolve or Chain to Retro` (PASS) or `## On FAIL (after 3 iterations)` (FAIL/BLOCKED) — Try-it line, 배포 방법, 배포 전 체크리스트, 3 user options.
3. `save_event(event_type="qa_verdict", data='{"verdict":"<PASS|REVISE|FAIL>","iteration":<N>,"pass1":"...","pass2":"...","pass3":"..."}')`.
4. Record the authoritative terminal result with `complete_stage(session_id="<sid>", stage="qa", verdict="<pass|fail|blocked>")`: map synthesis PASS→`pass`, FAIL→`fail`, and convergence BLOCKED→`blocked`. Exact `status="ok"` is required before any cross-stage marker or Skill invocation; error halts. `REVISE + continue` remains inside QA and does not call `complete_stage`. On success, **TaskUpdate** "QA" → `completed` and print `[SAMVIL] Stage 5/5: QA complete`.
5. Chain per `finalize.next_skill_decision.suggested` — PASS→`samvil-deploy` (default) or `samvil-evolve` (auto-trigger: build_retries≥5, qa_history≥2, partial_count≥5); FAIL/BLOCKED→`samvil-retro` (default), surface `user_options` for evolve / manual.
6. **HostCapability**: claude-code → invoke the Skill tool with `<suggested>`. Codex → write `<boot.paths.next_skill_marker>` `{"skill":"<suggested>"}` and read `skills/<suggested>/SKILL.md`.

## Anti-Patterns (preserved verbatim from legacy)

1. UNIMPLEMENTED for core_experience → auto-FAIL (E1, P1). 2. CONCERN never downgraded to informational — performance CONCERN = REVISE. 3. NO full `npm run build` in worker agents (lint/typecheck only). 4. Evidence-less PASS → `validate_evidence` fail = auto-FAIL (P1). 5. Stub/Mock/hardcoded → `semantic_check` HIGH → auto-FAIL (Reward Hacking). 6. Issue count must decrease per iter; identical issue id set 2 iters → BLOCKED (PHI-04). 7. Independent agents NEVER write files — main session only. 8. **`AskUserQuestion`**: `questions=["<질문>"]` 배열 — 문자열 시 `InputValidationError`.

## Legacy reference

Full per-`solution_type` Korean prose, verbatim Pass 1/1b/2/2.5/3 bodies (web/dashboard/game/mobile-app/automation), Pass 1b automation API connectivity probe (v3-027), Verdict Taxonomy (PASS/PARTIAL/UNIMPLEMENTED/FAIL with scores), Pass 2.5 downgrade matrix, Verification Questions in Checklist Items (v2.6.0+), Output Format blocks, incremental QA cache file format, brownfield AskUserQuestion, qa-checklist.md cross-references: see `SKILL.legacy.md`.
