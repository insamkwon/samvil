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

**Refine Gate harvest (v4.21, when `refined_answers` present)**:
- `constraints_aggregated[]` → seed.constraints (사용자가 인터뷰에서 명시한 제약은 *모두* 보존, 추가 LLM 추론 금지)
- `out_of_scope_aggregated[]` → seed.exclusions (사용자 명시 제외는 *모두* 빌드/QA에서 차단되도록)
- `tech_preferences_aggregated[]` → seed.tech_stack (충돌 시 사용자 선호 우선)
- `refined_by_phase[<phase>][*].decision` → 해당 feature의 description seed로 활용 (LLM이 paraphrase 금지 — 사용자 wording 우선)
- 누락 검사: 위 4개 중 하나라도 seed에 매핑 안 되면 **consolidation summary에 명시 표시** + 사용자 confirm 1회 받음.

**Fallback (no progress file or empty)**: convert `interview-summary.md` into valid v3 `project.seed.json` per the legacy regeneration rules.

In both paths: validate against `references/seed-schema.json`, present, and ask approval. If edits are requested, revise and re-present.

## After Approval

1. Write approved JSON to `project.seed.json`.
2. Call:

```
mcp__samvil_mcp__save_seed_version(
  session_id="<session_id>",
  version=1,
  seed_json="<escaped approved seed JSON>",
  change_summary="Initial seed from interview"
)

mcp__samvil_mcp__complete_stage(
  session_id="<session_id>",
  stage="seed",
  verdict="pass"
)
```

3. Append a short `.samvil/handoff.md` entry; never overwrite.
4. Best-effort `mcp__samvil_mcp__clear_interview_progress(project_root=".")` — interview-progress.json is no longer authoritative once seed.json is approved (interview-summary.md remains the narrative record).

## Chain

Use `host_chain_strategy.chain_via`:

- `skill_tool`: invoke `samvil-council` for standard/thorough/full, or
  `samvil-design` for minimal.
- `file_marker`: write `.samvil/next-skill.json`:

```json
{
  "schema_version": "1.0",
  "chain_via": "file_marker",
  "host": "<host>",
  "next_skill": "samvil-design",
  "reason": "minimal tier skips council",
  "from_stage": "seed",
  "created_by": "samvil-seed"
}
```

For standard/thorough/full, use `samvil-council`.

If MCP is unavailable, fall back to the legacy chaining rules in
`SKILL.legacy.md` and mention that orchestration was degraded.

## Invariants

- Read interview output from files, not chat memory.
- Seed is immutable after approval.
- MCP orchestration is preferred; files remain recovery source.
- Runtime-specific chaining must go through host capability.
