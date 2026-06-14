---
name: samvil-seed
description: "MCP-driven seed stage: crystallize interview-summary.md into project.seed.json and chain portably."
---

# SAMVIL Seed - Thin Orchestrated Entry

This is the v3.3 ultra-thin PoC. Full rules are preserved in
`skills/samvil-seed/SKILL.legacy.md`; use it for schema mapping, validation,
presentation, and defaults.

## Brownfield Presentation-Only Mode

**`state._brownfield_seed_merged == true` AND `project.seed.json` exists** →
skip "Build Seed" step entirely. Instead:

1. Read `project.seed.json` (already written by `merge_brownfield_seed`).
2. Present merged seed to user: list `status:existing` features (existing) + `status:new` features (new additions).
3. AskUserQuestion `이 병합된 seed가 맞나요?` → `맞아, 진행` / `수정 필요`.
   - 수정 필요 → AskUserQuestion으로 어떤 피처를 수정할지 받아 편집 후 재표시.
4. After approval: skip write (seed already on disk), call `save_seed_version` + `complete_stage`, append handoff.md, chain to samvil-council.

## Inputs

0. **Stage entry (boot contract — `references/skill-boot-template.md`)**: `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="seed_started", stage="seed", data="{}")` — best-effort; auto-claims `evidence_posted subject="stage:seed"`.
1. Read `project.state.json` for `session_id`, `current_stage`, `_brownfield_seed_merged`, and host name
   (`host`, `runtime`, or `agent_host`; default `generic`).
2. Read `project.config.json` for `selected_tier` / `samvil_tier`.
3. If NOT brownfield: load interview state in this order (v4.19 Progressive AC support):
   a. `mcp__samvil_mcp__load_interview_progress(project_root=".")` — if `exists==true`, use the returned `ac_by_phase` and `answers_by_phase` as the **primary** source. AC candidates are the consolidation base (do not regenerate from scratch).
   b. Read `interview-summary.md` from disk regardless — used as supplementary narrative for non-AC fields (description, tech stack, constraints).
   c. If neither exists → halt with a clear error; samvil-interview must run first.
4. Read `skills/samvil-seed/SKILL.legacy.md` for seed construction rules.

## MCP Gate

Call:

```
mcp__samvil_mcp__get_orchestration_state(session_id="<session_id>")
mcp__samvil_mcp__stage_can_proceed(session_id="<session_id>", target_stage="seed")
mcp__samvil_mcp__resolve_host_capability(host_name="<host>")
mcp__samvil_mcp__host_chain_strategy(host_name="<host>")
```

If `stage_can_proceed.can_proceed` is false, show blockers and stop.

## Build Seed

**Consolidate (v4.19, when `load_interview_progress.exists == true`)**:
1. Treat each `ac_by_phase[<phase>]` entry as a **confirmed AC candidate** that the user already saw and approved during the interview.
2. Group AC candidates into features (use `interview-summary.md` narrative for feature names; LLM judgment for clustering when phase-to-feature is non-obvious).
3. Deduplicate semantically equivalent ACs across phases (string-similar or LLM judgment). Prefer the user's exact wording when in doubt.
4. Assign IDs `F<N>.AC<N>` per `references/ac-tree-guide.md` (each AC gets `id`, `description`, `status: pending`, `evidence: []`).
5. Show the user a **consolidation summary**: "인터뷰에서 확정한 잠정 AC <N>개가 <M>개 feature로 정리되었습니다. 중복 <K>개 제거." then the seed preview.
6. **Negative/edge AC coverage (A1)**: per feature, `mcp__samvil_mcp__negative_ac_checklist(feature_name="<feature>", happy_acs_json=<[ac descriptions]>)` → for each `required_edges[]` entry, add one concrete AC (fill `ac_template`, set `kind: "negative"`) **or** mark it N/A with a one-line reason. Happy-path-only features are the #1 cause of "QA PASS but I keep fixing it" — do not skip silently. Present added negatives in the summary: "엣지 케이스 AC <P>개 추가 (빈 입력/경계/새로고침 등)." These become real ACs (verified by QA, serialized to specs like any other).

**Refine Gate harvest (v4.21, when `refined_answers` present)**:
- `constraints_aggregated[]` → seed.constraints (사용자가 인터뷰에서 명시한 제약은 *모두* 보존, 추가 LLM 추론 금지)
- `out_of_scope_aggregated[]` → seed.exclusions (사용자 명시 제외는 *모두* 빌드/QA에서 차단되도록)
- `tech_preferences_aggregated[]` → seed.tech_stack (충돌 시 사용자 선호 우선)
- `refined_by_phase[<phase>][*].decision` → 해당 feature의 description seed로 활용 (LLM이 paraphrase 금지 — 사용자 wording 우선)
- 누락 검사: 위 4개 중 하나라도 seed에 매핑 안 되면 **consolidation summary에 명시 표시** + 사용자 confirm 1회 받음.

**Fallback (no progress file or empty)**: convert `interview-summary.md` into valid v3 `project.seed.json` per the legacy regeneration rules.

**Evaluation principles derivation (v4.23.0)**: After the consolidation summary, derive `seed.evaluation_principles[]` from interview material — *source-trace, not invention*:
1. Each entry in `constraints_aggregated` becomes a candidate principle: `{principle: "<constraint as positive>", weight: 0.7, rationale: "<original constraint>", source_phase: "<phase>"}`. e.g. "100MB 이상 거부" → "사용자 업로드는 100MB 이하만 처리된다".
2. PHI-06 vague-AC rewrites become principles: `{principle: <rewritten AC>, weight: 0.6, source_phase: "<phase>"}`.
3. Each `refined_by_phase[*].decision` whose phase is `core` or `scope` adds: `{principle: <decision>, weight: 0.5, rationale: "core decision", source_phase: "<phase>"}`.
4. Hard ceiling: 8 principles. If more candidates, merge semantically-overlapping pairs and warn the user.
5. Present the derived principles to the user: `AskUserQuestion(["이 품질 기준이 맞나요?"], [좋아 / 가중치 조정 / 항목 추가/삭제])`. On adjust: collect changes, re-validate, re-present (max 2 loops).

**Exit conditions derivation (v4.23.0)**: Default to one entry — `"모든 features의 acceptance_criteria가 PASS이고 evaluation_principles 중 weight ≥ 0.5인 항목이 모두 PASS"`. If the user explicitly named tier-specific completion criteria in the interview (recorded in `refined_by_phase[*].out_of_scope` or interview-summary), append those verbatim.

`evaluation_principles` and `exit_conditions` are **optional schema fields** — old seeds without them remain valid (samvil-qa falls back to v4.22 logic).

In both paths: validate against `references/seed-schema.json`, present, and ask approval. If edits are requested, revise and re-present.

**Concrete behavior confirmation (A2)**: 추상 AC 텍스트만 보여주지 말 것 — 핵심 feature마다 AC(네거티브 포함)를 **실제 동작 시퀀스**로 풀어서 제시한다. 예: `"AC 통과" 대신 "증가 버튼 클릭 → 숫자 0→1 → 자동 저장 → 새로고침해도 1 유지 / 빈 값 추가 시도 → 거부 + 안내"`. 그 다음 `AskUserQuestion(["이렇게 동작하면 맞나요?"], [네 맞아요 / 다르게 동작해야 해요])`. "다르게" → 어느 동작이 어떻게 달라야 하는지 받아 AC 수정 후 재표시. 목적: "QA는 PASS인데 내 의도와 다름"을 빌드 전에 잡는다 (spec↔intent 격차).

## After Approval

1. Write approved JSON to `project.seed.json`.
2. `mcp__samvil_mcp__save_seed_version(session_id, version=1, seed_json=<escaped>, change_summary="Initial seed from interview")` + `mcp__samvil_mcp__complete_stage(session_id, stage="seed", verdict="pass")`.
3. Append `.samvil/handoff.md` (cat >> or Edit, never Write).
4. Best-effort `mcp__samvil_mcp__clear_interview_progress(project_root=".")` — interview-summary.md remains narrative record.

## Chain

Use `host_chain_strategy.chain_via`:
- `skill_tool`: invoke `samvil-council` (standard/thorough/full) or `samvil-design` (minimal).
- `file_marker`: write `.samvil/next-skill.json` with `{schema_version:"1.0", chain_via:"file_marker", host, next_skill, reason, from_stage:"seed", created_by:"samvil-seed"}` — `next_skill` per tier (minimal → `samvil-design`, else `samvil-council`).

If MCP unavailable: fall back to `SKILL.legacy.md` legacy chaining rules + announce degraded orchestration.

## Invariants

- Read interview output from files, not chat memory.
- Seed is immutable after approval.
- MCP orchestration is preferred; files remain recovery source.
- Runtime-specific chaining must go through host capability.
