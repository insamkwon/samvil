---
name: samvil-interview
description: "Socratic interview with app presets, unknown-unknown probing, and zero-question mode. Korean language."
---

# samvil-interview (ultra-thin)

Adopt the **Socratic Interviewer** role. **All conversation is in Korean**;
code/technical terms only in English. Tier resolution, Zero-Question Mode
detection, preset matching (custom > built-in), and manifest scan are
aggregated by `mcp__samvil_mcp__aggregate_interview_state`. Phase 0–4
question loops, AskUserQuestion checkpoints, per-question PATH routing,
and summary verification stay here (host-bound, Korean-prompt heavy).
Existing MCP tools cover ambiguity / seed-readiness / gate / domain
context. Full Korean prose, per-`solution_type` question banks, Phase
2.x expansion templates, and tier-by-tier tables in `SKILL.legacy.md`.

## Non-Skippable Gates (v4.20 — 절대 건너뛸 수 없는 6개)

1. **Phase 강제** — tier별 `get_tier_phases` 결과 phase는 모두 실행 (Step 2). LLM 판단으로 스킵 금지.
2. **AC Testability (PHI-06)** — vague AC ("좋은", "빠른"…) 발견 시 rewrite. 침묵 수용 금지 (Step 3).
3. **Convergence 3-조건 AND** — `ambiguity ≤ target` + `floors_passed` + `min_questions_met` 동시 충족까지 loop (Step 3).
4. **`gate_check(interview_to_seed)`** — verdict이 `pass`일 때만 다음 stage chain (Step 5).
5. **Step 4 사용자 검토** — Zero-Question Mode 포함, 무조건 single review.
6. **Restate Gate (v4.20)** — 시드 직전 한 줄 합의. 사용자가 "단어 수정" 또는 "빠진 범위" 선택 시 해당 Phase 재방문 (Step 4.5).

## Boot Sequence (INV-1)

1. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="interview_start", stage="interview", data="{}")` — best-effort. Auto-claim posts `evidence_posted subject="stage:interview"`.
2. Files are SSOT — read `project.state.json`, `project.config.json`, `references/app-presets.md`. Read `references/interview-frameworks.md` + `interview-question-bank.md` only when entering a Phase 2.x.
3. **Interview Resume (v4.19)**: `mcp__samvil_mcp__load_interview_progress(project_root=".")` → if `exists==true`, restore `completed_phases[]` + `answers_by_phase` + `ac_by_phase` (잠정 AC). Print `[SAMVIL] 인터뷰 재개 — 답변 <N>개 / 잠정 AC <M>개 복원. 완료 Phase 건너뜀.`. Schema in `references/interview-progress-schema.md`.
4. `mcp__samvil_mcp__aggregate_interview_state(project_root="<cwd or ~/dev/<slug>>", prompt="<one-line>")` → `tier.{samvil_tier,source,valid_tiers}` (5-valued: includes `deep`), `ambiguity_target`, `required_phases[]` (`core/scope/lifecycle/unknown/nonfunc/inversion/stakeholder/research/domain_deep`), `mode.{is_zero_question,matched_signals}`, `preset.{name,keywords,source,description?}`, `custom_presets_count`, `manifest`, `paths.{interview_summary,state_file,config_file,preset_dir}`, `errors[]`. On error: fall back to manual reads from `SKILL.legacy.md` (P8).
5. `mcp__samvil_mcp__render_domain_context(solution_type="<from orchestrator>", stage="interview")` — best-effort. `interview_probes` / `risk_checks` / `core_entities` are question candidates only; never override user input.

## Step 0 — Mode + Preset

- `mode.is_zero_question` true → render `[SAMVIL] Zero-Question Mode`. Skip Phase 2/3 loops, generate seed-level summary from `preset` defaults, jump to Step 4 (single review **mandatory**).
- `custom_presets_count > 0` and `preset.source == "builtin"` → AskUserQuestion: "저장된 커스텀 프리셋 중 사용하시겠어요?" with custom presets + "새로 만들게요". Re-run aggregator with the chosen preset's keywords on selection.
- `preset.name` non-empty → load that preset's "기본 기능"/"흔한 함정"/"Pre-mortem" rows from `references/app-presets.md`. Otherwise spawn `competitor-analyst` (full tier only) or proceed empty.

## Step 0.5 — Epic Claim 합성 (v4.19, A-2)

앱 아이디어로 한 문장 합성: `"<주체>가 <대상>의 <문제>를 <방식>으로 해결합니다."`. AskUserQuestion `["이 방향이 맞나요?"]` with options `[확인 후 진행 / 한 줄 수정]`. "수정" 시 사용자 paraphrase 1회만 허용 (wordsmithing 깊이 금지). 앱 아이디어 너무 짧거나 모호하면 합성 스킵하고 Step 1로. Epic Claim은 모든 후속 Phase 질문의 frame.

## Step 1 — PATH Routing + Rhythm Guard (per-question)

Per question: `route_question(question, manifest_facts, force_user=(streak>=3))` → path ∈ `auto_confirm / code_confirm / user / research / forced_user` (full decision table: `SKILL.legacy.md §0.7b`). Update streak: `update_answer_streak(streak, extract_answer_source(answer))`. Breadth: `manage_tracks(action="init|update|check|resolve")`.

**자동확인 표시 (v4.19, A-3)**: `auto_confirm` path마다 사용자에게 명시 출력 — `ℹ️ 자동확인: <fact> (<source-file>)` 예: `ℹ️ 자동확인: Next.js 14.2 (package.json)`. 출처는 반드시 파일명; "자동" 같은 모호 표현 금지.

**답변 즉시 저장 (v4.19, INV-3 structural)**: 매 답변 직후 `mcp__samvil_mcp__persist_interview_answer(project_root=".", phase=<id>, question=<q>, answer=<a>, source=<from-user|from-code|from-research>, ac_candidates_json=<JSON array>, refine_payload_json=<v4.21 JSON dict, 옵션>)`. Phase 완료 시 `mark_interview_phase_complete`.

**Refine Gate (v4.21)**: 사용자 자유 텍스트 답변이 결정/제약/exclusion/기술선호를 *섞어서* 담을 때 (e.g. "Excel 받아서 Slack 보내, 100MB는 거부, d3.js로, 모바일은 안 해도 돼"), 다음 질문 전 5-section 구조로 재구성: `{decision, reasoning, constraints[], out_of_scope[], codebase_context, tech_preferences[]}`. AskUserQuestion `[그대로 보내 / 제약 추가 / out-of-scope 추가 / 다시 쓰기]` 확인 후 위 호출의 `refine_payload_json`으로 전달 + `source="from-user-refined"`. **Skip 조건**: 짧은 답변 (~30자), 객관식 단일 선택, PATH 1a 자동확인. **예외**: Restate Gate (Step 4.5) 의 "단어 수정"/"빠진 범위" 답변은 항상 Refine 통과.

## Step 2 — Phase Loop (Korean, host-bound)

Run **only the phases in `aggregate.required_phases`**. **한 번에 하나씩** AskUserQuestion (객관식 + Other), preset-aware options. Adaptive follow-up (short→expand, long→structure, vague→choose). Framework names (AARRR/JTBD/HEART) never exposed to user.

Per-`solution_type` question bodies + Phase id/trigger/body 매핑 표: `SKILL.legacy.md` §"Phase id / Trigger / Body 매핑 표".

**Progressive Confirmed + 잠정 AC (v4.19, A-1.deep)**: 각 Phase 완료 직후 사용자에게 `✅ Confirmed [Phase 한국명]` + `잠정 AC (seed 단계에서 확정): - <ac_text>` 형식 출력. AC 추출 규칙: 답변의 implementable 행위문 ("사용자는 X할 수 있다", "Y가 표시된다") 1~3개. 추출한 AC는 Step 1 `persist_interview_answer`의 `ac_candidates_json`으로 함께 저장. Phase 완료 시 `mark_interview_phase_complete`.

## Step 3 — Convergence Check

Track `questions_asked` (increment per user question). Re-score after each Phase:
`mcp__samvil_mcp__score_ambiguity(interview_state='<json>', tier="<tier>", questions_asked=<N>)`.
Render milestone + `floor_violations` + `missing_items` + `min_questions_met` + `dimension_scores`.

**Convergence** = `ambiguity ≤ target` + `floors_passed` + `min_questions_met` (minimal 5 / standard 10 / thorough 20 / full 30 / deep 40).
No phase reprompt cap — loop until all 3 hold. Check `dimension_scores`: highest-scoring dimension's Phase is the next loop target.

**AC Testability Gate (PHI-06)**: vague AC ("좋은", "빠른", "직관적인", "smooth"…) → AskUserQuestion to rewrite. Never accept vague AC silently.

## Step 4 — Summary + User Verification

Render `solution_type`-specific summary (template: `SKILL.legacy.md §"Phase 4: 요약 & 확인"`). AskUserQuestion → `좋아 진행해` / `수정할 부분 있어`. **Zero-Question Mode 포함** single review mandatory.

If `preset.source == "none"` or 큰 방향 변경: AskUserQuestion → preset 저장 여부 → write `<aggregate.paths.preset_dir>/<name>.json` (schema: `references/app-presets.md`).

## Step 4.5 — Restate Gate (v4.20)

Step 5 직전 한 줄 재진술. Epic Claim과 *같은 한 줄에 수렴*이 이상적. 템플릿: `목표: "<주체>가 <대상>의 <문제>를 <방식>으로 해결한다 — <핵심 제약>."`. `AskUserQuestion(["다른 사람이 이 한 줄만 읽어도 같은 결과?"], [좋아, seed / 단어 수정 / 빠진 범위])`.
- **좋아** → Step 5.
- **단어 수정** → paraphrase 1회 → `persist_interview_answer(phase="restate", source="from-user-correction")` → Restate 재시도 (최대 2회, 후 user-forced proceed).
- **빠진 범위** → 입력 받음 → 해당 차원 Phase 추론 (manifest/scope/inversion) → Phase 재방문 + Step 3 재실행.

## Step 5 — Persist + Contract Layer (post_stage)

1. `mcp__samvil_mcp__load_interview_progress(project_root=".")` → use returned `qa_entries` + `ac_by_phase` as source of truth for summary generation. Do NOT rely on conversation context. Write summary to `aggregate.paths.interview_summary` (Korean, sections per `SKILL.legacy.md` §"Output Format" by `solution_type`). Each section non-empty; constraints ≥1; success criteria ≥3. **삭제하지 않음** — samvil-seed가 progress 파일을 consume 후 `clear_interview_progress` 호출.
2. `mcp__samvil_mcp__compute_seed_readiness(dimensions_json='{"intent_clarity":<f>,"constraint_clarity":<f>,"ac_testability":<f>,"lifecycle_coverage":<f>,"decision_boundary":<f>}', samvil_tier="<tier>")` — score each dim from recorded answers; flag estimates in summary.
3. `mcp__samvil_mcp__gate_check(gate_name="interview_to_seed", samvil_tier="<tier>", metrics_json='{"seed_readiness":<total>}', project_root=".")`.
   - `block` → loop back to failing dim's owning Phase (`required_action.type` ∈ `split_ac/run_research/stronger_model/ask_user`). Cap 2 escalations via `gate_should_force_user`.
   - `escalate` → bump `interview_level` one step (`normal→deep→max`) and re-run that Phase.
   - `pass` → continue.
4. `mcp__samvil_mcp__claim_post(project_root=".", claim_type="gate_verdict", subject="interview_to_seed", statement="verdict=<v>, seed_readiness=<total>", authority_file="state.json", claimed_by="agent:socratic-interviewer", evidence_json='["interview-summary.md"]', meta_json='<verdict dict>')`. Per `references/contract-layer-protocol.md`, the Judge here is `agent:user` or `agent:product-owner` invoked out-of-band during approval — do NOT self-verify.
5. `mcp__samvil_mcp__save_event(event_type="interview_complete", stage="seed", data='{"questions_asked":<N>,"preset_matched":"<preset.name>"}')`.
6. Append the Interview block to `.samvil/handoff.md` via Bash `cat >>` or Edit (never the Write tool).

## Brownfield Mode (auto-detected from `state._analysis_source == "brownfield"`)

Load `state._analysis_context`; announce `[SAMVIL] Brownfield Mode`. Pass `pre_filled_dimensions="technical,nonfunctional"` to all `score_ambiguity` calls. Focus phases: `core` (improvement goals), `scope` (gaps/new features), `inversion` (why existing app underperforms).

**Manifest 강제 읽기 (v4.19, B-5)**: Brownfield 진입 직후 우선순위로 첫 번째 존재 파일 Read — `package.json > pyproject.toml > go.mod > Cargo.toml > requirements.txt`. 추출한 fact (framework / language / version / dependencies)는 자동으로 PATH 1a (auto_confirm) 처리, 사용자에게 `ℹ️ 자동확인: <fact> (<file>)` 형식 announce. 같은 기술 질문 사용자에게 다시 묻지 않음.

After Step 5 approval: `mcp__samvil_mcp__merge_brownfield_seed(existing_seed_json='<project.seed.json>', interview_state_json='<answers JSON>', new_features_json='[]')` → write merged seed to `project.seed.json` → set `state._brownfield_seed_merged: true` → proceed to Step 6.

## Step 6 — Chain

**Greenfield**: Invoke Skill tool with `samvil-seed`. **NO COMPACT**. Codex CLI fallback: read `skills/samvil-seed/SKILL.md`.
**Brownfield**: Invoke Skill tool with `samvil-seed` (merged seed already written; samvil-seed enters presentation-only mode → samvil-council → samvil-scaffold → samvil-build). Same full pipeline as greenfield.

## Anti-Patterns

1. Asking 2+ questions in a single AskUserQuestion. 2. Skipping summary verification (Zero-Question Mode included). 3. Accepting a vague AC without offering a rewrite (PHI-06). 4. Exposing framework names (AARRR/JTBD/HEART) to the user. 5. Self-verifying the `interview_to_seed` gate verdict (Generator ≠ Judge). 6. Hard-coding `chain.next_skill` instead of always invoking `samvil-seed`. 7. **`AskUserQuestion` 호출 포맷**: `questions` 파라미터는 반드시 배열 — `questions=["<질문>"]`. 문자열 직접 전달 시 `InputValidationError` 발생.

## Legacy reference

Full Korean Phase bodies, 5-path routing tables, Tier rule tables, summary templates, adaptive follow-up matrix: `SKILL.legacy.md`.
