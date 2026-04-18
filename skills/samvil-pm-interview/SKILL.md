---
name: samvil-pm-interview
description: "PM-mode interview. Collect vision → users → metrics → epics → tasks → ACs, then convert to engineering seed."
---

# SAMVIL PM Interview

Alternative entry point for the Interview stage. Runs a **product-management style** discovery pass and emits a PM seed. The PM seed is then flattened into a standard engineering seed (`project.seed.json`) via `pm_seed_to_eng_seed`.

Use this when:
- The request is vague ("앱 하나 만들고 싶어") and you need to force clear vision + metrics first.
- The user is a PM / founder rather than an engineer.
- You expect 10+ features and want epic-level grouping before AC decomposition.

Otherwise, `samvil-interview` (the engineering-first flow) is still the default.

## Boot Sequence

1. Read `project.config.json` if present; pick up `selected_tier`.
2. Read any existing `project.pm-seed.json` to resume. If present, start at the first unfilled section.
3. 한국어로 진행 (SAMVIL 원칙: 모든 사용자 대화 한국어).

## Phases

### Phase 1 — Vision (1 question)

- "한 문장으로, 이 제품이 **누구의 무슨 문제를** 해결하나요?"
- Capture as `pm_seed.vision`.

### Phase 2 — Users + Pain Points (2 questions)

- "주 사용자 세그먼트는 누구인가요? 한두 그룹으로 좁히면 좋겠어요."
- 각 세그먼트별로 "지금 이 문제를 어떻게 해결하고 있고, 왜 부족한가요?"
- Capture into `pm_seed.users = [{segment, pain_points}]`.

### Phase 3 — Metrics (1 question)

- "성공을 어떻게 측정할까요? 숫자 한두 개로요."
- 예시: "D7 retention >= 40%", "NPS >= 30".
- Capture into `pm_seed.metrics = [{name, target}]`.

### Phase 4 — Epics (1 round)

- "가장 먼저 배포할 MVP의 에픽을 3~5개로 쪼개주세요."
- 각 에픽에 `id` (E1, E2, ...) 와 `title` 부여.

### Phase 5 — Tasks per Epic (per epic)

For each epic, ask:
- "이 에픽을 구현하려면 어떤 태스크가 필요한가요? 각 태스크는 하나의 화면 또는 하나의 기능 단위로요."
- 각 task에 `id` (T{epic}.{idx}) + `description`.

### Phase 6 — Acceptance Criteria per Task

For each task, prompt user for **testable** acceptance criteria (아직 UX 세부사항은 금지, 행동 기반만):
- "이 태스크가 완료됐다고 어떻게 확인하나요? 3~7개의 관측 가능한 조건으로요."
- Each AC becomes a leaf: `{id: AC-<task>-<idx>, description, children: []}`.

After Phase 6, write `project.pm-seed.json` to disk.

## Conversion to Engineering Seed

1. Validate the PM seed:
   ```
   result = mcp__samvil_mcp__validate_pm_seed(pm_seed_json=<json>)
   ```
   If `result.valid` is false, report each error and resume Phase 4–6 to fix.

2. Convert:
   ```
   eng_seed_json = mcp__samvil_mcp__pm_seed_to_eng_seed(pm_seed_json=<json>)
   ```
   Output already has `schema_version: "3.0"` and `features[]` populated from epics/tasks.

3. Write to `project.seed.json`. Preserve `vision`, `users`, `metrics` at root.

4. Emit events (best-effort):
   ```
   mcp__samvil_mcp__save_event(event_type="pm_seed_complete", data='{"epics":<N>,"tasks":<M>}')
   mcp__samvil_mcp__save_event(event_type="pm_seed_converted", data='{"features":<len>}')
   ```

## Chain to next skill

After conversion, invoke `samvil-council` (if tier ≥ thorough) or `samvil-design` directly. Council/design always read `project.seed.json`, which is now populated.

## Anti-patterns

- Do NOT skip Vision/Metrics. If the user gives a single sentence, still probe for the numeric target in Phase 3.
- Do NOT stuff AC with vague words ("빠르게", "쉽게"). Re-ask until each AC is observable.
- Do NOT create Epics that span the whole product. 3~5 is a sweet spot for MVP.

## Output

Files written:
- `project.pm-seed.json` — the PM-level spec
- `project.seed.json` — converted engineering seed (v3 schema)

The harness then continues through Council → Design → Scaffold → Build → QA as usual.
