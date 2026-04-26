---
name: samvil-pm-interview
description: "PM-mode interview. Collect vision → users → metrics → epics → tasks → ACs, then convert to engineering seed."
---

# samvil-pm-interview (ultra-thin)

PM-style entry point for the Interview stage. Captures
vision → users → metrics → epics → tasks → ACs into `project.pm-seed.json`,
then converts it into a v3 engineering seed via
`mcp__samvil_mcp__pm_seed_to_eng_seed`.

Detailed Korean phase prompts, anti-patterns, and historical context are
preserved in `SKILL.legacy.md`. Use this when the requester is a PM /
founder, the request is vague, or you expect 10+ features that benefit
from epic-level grouping. Otherwise `samvil-interview` (engineering-first)
remains the default.

## Boot Sequence

1. Read `project.config.json` if present; pick up `selected_tier`.
2. Read existing `project.pm-seed.json` to resume at the first
   unfilled section.
3. 한국어로 진행 (모든 사용자 대화 한국어).

## Phase Loop

For each phase, ask the Korean question (full prompts in `SKILL.legacy.md`),
capture the answer, and append to the in-memory PM seed:

| Phase | Asks | Writes |
|---|---|---|
| 1 — Vision | 한 문장 문제 정의 | `vision` |
| 2 — Users | 세그먼트 + pain points | `users[]` |
| 3 — Metrics | 성공 지표 1~2개 (숫자) | `metrics[]` |
| 4 — Epics | MVP 에픽 3~5개 | `epics[]` (id, title) |
| 5 — Tasks | 에픽별 화면/기능 단위 | `epics[].tasks[]` (id, description) |
| 6 — ACs | 태스크별 관측 가능 조건 3~7개 | leaf `acceptance_criteria[]` |

Save `project.pm-seed.json` after each phase (INV-1 file is SSOT). Each
AC is a leaf `{id, description, children: []}` — vague words ("빠르게",
"쉽게") are forbidden and trigger a re-ask.

## Convert + Chain

1. Validate the PM seed before conversion:
   ```
   mcp__samvil_mcp__validate_pm_seed(pm_seed_json=<json>)
   ```
   On `valid: false`, surface every error and resume Phases 4–6 to fix.

2. Convert. If engineering-only choices are already known
   (tech stack, solution_type, visual direction), pass them as
   `defaults_json`; otherwise the tool fills conservative placeholders
   (`solution_type="web-app"`, `tech_stack.framework="nextjs"`, …) that
   `validate_seed` accepts and Council/Design refine later.
   ```
   mcp__samvil_mcp__pm_seed_to_eng_seed(pm_seed_json=<json>, defaults_json=<json|None>)
   ```
   Output already carries `schema_version: "3.0"`, flattened `features[]`
   (one per task), and preserves `vision`/`users`/`metrics` at root.

3. Write the result to `project.seed.json`.

4. Best-effort events (P8 — file write is the source of truth):
   ```
   mcp__samvil_mcp__save_event("pm_seed_complete", '{"epics":N,"tasks":M}')
   mcp__samvil_mcp__save_event("pm_seed_converted", '{"features":N}')
   ```

## Chain to next skill (INV-4)

After `project.seed.json` is written, invoke the next stage via the
Skill tool. Both Council and Design read `project.seed.json`; nothing
else needs to be passed.

- `selected_tier` ∈ {`thorough`, `full`} → invoke `samvil-council`
- `selected_tier` ∈ {`minimal`, `standard`} → invoke `samvil-design`
- Missing/unset tier → invoke `samvil-design`, emit `tier_missing`
  event (best-effort).

## Output

Files written:

- `project.pm-seed.json` — PM-level spec
- `project.seed.json` — converted engineering seed (v3 schema)

The harness then continues through Council → Design → Scaffold → Build → QA.

## Legacy reference

Full Korean phase prompts, anti-patterns, and historical context in
`SKILL.legacy.md`.
