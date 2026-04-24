---
name: samvil-retro
description: "Post-run retrospective. Analyze run metrics from files, suggest 3 harness improvements, append to feedback log."
---

# SAMVIL Retro — Self-Evolution Retrospective

You are adopting the role of **Retro Analyst**. Analyze this SAMVIL run and produce actionable improvement suggestions for the harness itself.

## Boot Sequence (INV-1) — All Metrics from Files

0. **TaskUpdate**: "Retro" task를 `in_progress`로 설정
1. Read `project.seed.json` → what was built
2. Read `project.state.json` → completed_features, failed, qa_history, build_retries
3. Read `.samvil/qa-report.md` → QA pass results (if exists)
4. Read `interview-summary.md` → count questions (count lines starting with a question pattern)
5. **Read `.samvil/metrics.json`** → 관측성 대시보드 메트릭 (stage durations, pass rates, etc.)
6. **Follow `references/boot-sequence.md`** for metrics end recording (Retro is the final stage).
7. **v3.2 Contract Layer — stage entry**: `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="retro_started", stage="retro", data="{}")`. Best-effort, MCP 내부 auto-claim이 `.samvil/claims.jsonl`에 `evidence_posted subject="stage:retro"` 자동 기록.

**Retro Boot에서 metrics 종료 처리** — metrics.json이 존재하면:
```json
{
  "stages": {
    "retro": {
      "started_at": "<ISO timestamp now>"
    }
  },
  "total_duration_ms": <now_ms - timestamp_ms>
}
```
`total_duration_ms`를 계산해서 저장한다 (파이프라인 전체 소요 시간).

**Do NOT rely on conversation history for metrics.** Files are the truth.

## Process

### Step 0: Read History for Pattern Detection

1. Read `harness-feedback.log` from the SAMVIL plugin directory (`harness-feedback.log (SAMVIL 플러그인 캐시 루트: `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`)`)
   — 이전 실행들의 suggestions를 수집
2. Read `.samvil/events.jsonl` from the project directory
   — 이번 실행의 전체 이벤트 이력

이전 suggestions에서 같은 키워드가 **3회 이상** 반복되면 **'반복 패턴'**으로 표시:

```
[SAMVIL] ⚠️ 반복 패턴 감지:
  "drag-drop 빌드 실패" — 3회 반복 (run-001, run-003, run-005)
  → 자동 수정 제안: web-recipes.md에 @hello-pangea/dnd 기본 설정 추가
```

반복 패턴이 있으면 Step 3의 suggestions에 자동 수정 제안을 포함한다.

### Step 1: Gather Metrics

From the files above, extract:

| Metric | Source |
|--------|--------|
| Features attempted / passed / failed | state.json: completed_features, failed |
| Build retries total | state.json: build_retries |
| QA iterations | state.json: qa_history length |
| QA final verdict | state.json: qa_history last entry |
| Interview question count | interview-summary.md |
| User seed edits | state.json (if tracked) |
| **Stage durations** | **metrics.json: stages.\*.duration_ms** |
| **QA pass rate** | **metrics.json: stages.qa.pass_rate** |
| **Build failure rate** | **metrics.json: stages.build (features_total - features_passed) / features_total** |
| **Total pipeline duration** | **metrics.json: total_duration_ms** |
| **Agents spawned per stage** | **metrics.json: stages.\*.agents_spawned** |
| **v3 AC leaf stats** | **events.jsonl: count of `ac_leaf_complete` events, grouped by `data.status`** |
| **v3 feature tree progress** | **events.jsonl: last `feature_tree_complete` per feature (`passed`, `failed`, `total_leaves`)** |
| **v3 rate budget usage** | **events.jsonl: `rate_budget_summary` events — peak, total_acquired per feature** |
| **v3 interrupted sessions** | **events.jsonl: any `rate_budget_stale_recovery` event with its `previous.active` count** |
| **v3 schema migration** | **events.jsonl: `seed_migrated` events** |

If the run was a v3 tree build (schema_version starts with "3." in project.seed.json), surface these v3 metrics in the Observability block alongside stage durations. Absence of leaf-level events on a v3 seed means Phase B-Tree didn't fire — flag this as a REGRESSION in the suggestion list.

#### Step 1b: 관측성 대시보드 분석

`.samvil/metrics.json`이 존재하면 아래 분석을 수행하고 콘솔에 출력:

**1. 병목 스테이지 식별** — duration_ms가 가장 큰 스테이지:

```
[SAMVIL] 관측성 대시보드 — 병목 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  스테이지별 소요 시간:
    interview    12.3s (36%)
    seed          2.3s ( 7%)
    design        3.5s (10%)
    scaffold      4.6s (14%)
    build        56.8s (■■ 45%) ← 병목
    qa           67.9s (■■ 54%) ← 병목
  ─────────────────────────────
  총 소요: 147.4s
  병목: build + qa (전체의 99%)
```

**2. 빌드 실패율 계산:**

```
  빌드 성공률: 4/5 (80%)
  빌드 실행 횟수: 3회
  기능별 통과: 4 passed / 1 failed
    ✗ failed: "<feature_name>" — <사유 from state.failed>
```

**3. QA 패스율 추이 (이전 실행과 비교):**

`harness-feedback.log`에서 이전 실행들의 `stages.qa.verdict`를 수집하여 현재 실행과 비교:

```
  QA 패스율 추이:
    run-001: FAIL (2 iterations)
    run-002: PASS (1 iteration)
    run-003 (현재): PASS (2 iterations, pass_rate=0.80)
  → 추세: 안정적 (최근 2회 연속 PASS)
```

**4. 병목 구간 개선 제안** — 상위 2개 병목 스테이지에 대해 구체적 개선안 제시:

```
  병목 개선 제안:
    1. build (56.8s): "features_total이 5개. 병렬 빌드(max_parallel=2)가 활성화되어 있으나,
       3개 이상 feature에서 순차 실행 발생. max_parallel=3으로 증가 권장."
    2. qa (67.9s): "QA iterations=2. Pass 2 런타임 검증이 주요 지연.
       config에서 qa_max_iterations=2로 조정 검토."
```

**metrics.json이 없으면** — 기존 Step 1 로직만으로 분석 진행 (경고 없이).

### Step 2: Analyze

Identify:
1. **What worked well** — stages that passed first try, smooth transitions
2. **What was slow or failed** — retries, user corrections, QA failures
3. **Patterns** — recurring issues (e.g., "drag features always fail")

### Step 2b: 플로우 준수 리포트

events.jsonl에서 실제 실행된 단계 순서를 추출하고, 계획된 플로우와 비교:

```
[SAMVIL] 플로우 준수 리포트
  계획: Interview → Seed → Council → Design → Scaffold → Build → QA → Retro
  실제: Interview → Seed → Council → Design → Scaffold → Build(×12) → QA(×2) → Retro
  편차:
    - Build 12회 실행 (예상 1~3회) — Tailwind v4 설정 문제
    - Evolve: SKIPPED
```

### Step 2c: 에이전트 활용도 리포트

config.selected_tier에서 배치된 에이전트 수와 events.jsonl에서 실제 사용된 에이전트를 비교:

```
[SAMVIL] 에이전트 활용도
  Tier: standard (20 에이전트 배치)
  실제 수행: 8/20 (40%)
    ✓ socratic-interviewer, seed-architect, product-owner, simplifier, scope-guard
    ✓ tech-architect, frontend-dev, qa-mechanical
    ✗ 미사용: backend-dev, infra-dev, ux-designer, ...
  → 활용도 50% 미만: 다음에 minimal tier 추천
```

### Step 3: Generate 3 Improvement Suggestions (suggestions_v2 schema)

Produce **exactly 3** actionable suggestions targeting the harness (skills, references, templates).

**v3.0.1 이후 schema** (v3-021에서 도입) — 각 suggestion은 `suggestions_v2` dict schema를 따른다:

| 필드 | 설명 | 필수 |
|---|---|---|
| `id` | 고유 ID. 포맷: `v<major>-<NNN>` (예: `v3-028`, `v3-029`). 기존 run의 마지막 ID에서 +1 | ✅ |
| `priority` | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `BENEFIT` | ✅ |
| `component` | 대상 파일/스킬 경로 (예: `samvil-build`, `agents/tech-lead.md`, `mcp:seed_manager`) | ✅ |
| `name` | 짧은 라벨 (한 줄) | ✅ |
| `problem` | 무엇이 잘못됐나. 근거 데이터 포함 (예: "QA 2회 반복, pass_rate=0.6") | ✅ |
| `fix` | 어떻게 고칠 건가. 구체적 변경 지시. 여러 단계면 `(a) ... (b) ...` | ✅ |
| `expected_impact` | 무엇이 좋아지나 | ✅ |
| `source` | dogfood 출처 (예: `<seed.name> dogfood`, `audit`) | ⭕ |
| `sprint` | `Sprint N — <이름>` 또는 빈 문자열 (사용자가 나중에 분류) | ⭕ |
| `risk_of_worse` | 이 개선이 악화시킬 가능성 (CLAUDE.md 개선안 포맷 준수) | ⭕ |

**priority 분류**:
- `CRITICAL`: 파이프라인 중단 원인 (build fail, QA 전체 실패, hang)
- `HIGH`: 반복 패턴 (3회 이상 동일 이슈), 성능 병목 (전체의 50%+ 소요)
- `MEDIUM`: 품질 저하 (QA 반복 2회+, 기능 누락)
- `LOW`: 사용성 개선 (프롬프트 개선, 출력 포맷)
- `BENEFIT`: 측정된 긍정 효과 (이미 작동하는 것의 근거/documentation 보강)

Console 출력 포맷:

```
[SAMVIL] Retrospective — Run Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

App: <seed.name>
Features: <N>/<M> passed
Build Retries: <N>
QA Iterations: <N>
Final Verdict: <PASS/FAIL>

Flow Compliance: <일치 / 편차 N건>
Agent Utilization: <M/N> (<percent>%)

What Worked:
  - <observation with specific data>

What Needs Improvement:
  - <observation with specific data>

Suggestions:
  1. v<major>-<NNN> [PRIORITY] <name>
     component: <file path>
     problem:   <what>
     fix:       <how>
     impact:    <expected>
     source:    <dogfood run id>

  2. v<major>-<NNN> [PRIORITY] <name>
     ...

  3. v<major>-<NNN> [PRIORITY] <name>
     ...
```

### Step 3b: Preset 자동 축적

이 앱의 유형(seed.name 또는 interview에서 매칭된 preset)이 `references/app-presets.md`에 **없으면**:

빌드 경험 기반으로 새 preset 초안을 생성:

```
[SAMVIL] 새 앱 유형 감지: "<app-type>"
  이 유형이 app-presets.md에 없습니다.
  빌드 경험 기반으로 preset 초안을 생성했습니다:

  ## <app-type>
  기본 기능: [이번에 구현한 features]
  추천 스택: [이번에 사용한 tech_stack]
  흔한 함정: [이번에 발생한 에러 패턴 from fix-log.md]
  Pre-mortem: [QA에서 발견된 주요 이슈]

  app-presets.md에 추가할까요? (yes / no)
```

사용자 승인 시 `references/app-presets.md`에 append.

### Step 4: Append to Feedback Log

Append a JSON entry to `harness-feedback.log` in the SAMVIL **plugin** directory (`~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`):

**중요 (v3.0.1부터)**: 새 entry는 반드시 `suggestions_v2` 필드를 사용한다. legacy `suggestions` (string array)는 절대 쓰지 않는다. `suggestions_v2`가 정본(SSOT).

**새 ID 할당 규칙**:
- `harness-feedback.log` 전체를 읽어서 모든 entry의 `suggestions_v2[].id`를 스캔
- 가장 큰 `v<major>-<NNN>`을 찾아 NNN + 1로 새 ID 할당
- 예: 마지막이 `v3-027`이면 새 suggestion은 `v3-028`, `v3-029`, `v3-030`
- major 버전은 현재 plugin.json의 version major를 따른다

```json
{
  "run_id": "samvil-YYYY-MM-DD-NNN",
  "seed_name": "<name>",
  "timestamp": "<ISO 8601>",
  "stages": {
    "interview": { "questions": 0 },
    "seed": { "user_edits": 0 },
    "scaffold": { "build_retries": 0 },
    "build": { "features_attempted": 0, "features_passed": 0, "retries": 0 },
    "qa": { "verdict": "PASS", "iterations": 0 }
  },
  "metrics": {
    "stage_durations_ms": {},
    "total_duration_ms": 0,
    "build_pass_rate": 0.0,
    "qa_pass_rate": 0.0,
    "bottleneck_stages": []
  },
  "suggestions_v2": [
    {
      "id": "v<major>-<NNN>",
      "priority": "CRITICAL|HIGH|MEDIUM|LOW|BENEFIT",
      "component": "<file path or skill/agent name>",
      "name": "<one-line label>",
      "problem": "<what went wrong with supporting data>",
      "fix": "<specific change instructions, multi-step allowed>",
      "expected_impact": "<what improves>",
      "source": "<seed.name> dogfood",
      "sprint": ""
    },
    { ... },
    { ... }
  ]
}
```

If the file doesn't exist, create it as `[entry]`. If it exists, append (read existing content, parse as JSON array, add entry, write back).

**legacy `suggestions` (string array)**: 과거 entries (1~5번)는 legacy schema 유지. 새 entry에는 `suggestions_v2`만 쓴다.

### Step 4b: Resolved Suggestion 정리

새 항목을 추가한 후, **기존 런의 suggestions 중 이미 스킬/코드에 반영된 것을 정리**한다.

1. 전체 harness-feedback.log를 순회하며 각 런의 `suggestions_v2[]` (또는 legacy `suggestions[]`)를 읽는다
2. 각 suggestion에 대해: `component` 필드(또는 legacy `target_file`)의 파일을 Grep으로 검색하여 반영 여부를 확인
   - `fix` 필드의 핵심 키워드 (예: "UNIMPLEMENTED", "Playwright", "Deep Mode", "Customer Lifecycle")가 스킬에 존재하면 → 반영됨
3. 반영된 suggestion은 해당 런에서 제거하고, `resolved_in` 필드에 현재 버전과 함께 기록:
   ```json
   "resolved_in": "v3.X.Y — <resolved items summary>"
   ```
4. 미반영 suggestion만 `suggestions_v2[]`에 남긴다
5. legacy `suggestions[]` (string array)는 자체 정리 대상이 아니다 (entries 1~5 historical). 건드리지 않는다.

**원칙**: 메트릭 데이터(stages, timestamp, seed_name, metrics)는 절대 삭제하지 않는다. suggestions_v2만 정리한다.

### Step 5: Update State

**MCP (best-effort):** Save retro completion:
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="retro_complete", stage="complete", data='{"suggestions_count":3,"features_passed":<N>,"features_failed":<N>,"build_retries":<N>,"qa_iterations":<N>}')
```

### Step 6: Final Message

### MCP Health Report

If `.samvil/mcp-health.jsonl` exists, read it and generate a report:

```
[SAMVIL] MCP Health Report:
  Total calls: <count>
  Successful: <count> (<%>)
  Failed: <count> (<%>)
  Failed tools: <list of tools that failed>

  → If failure rate > 20%: recommend running `setup-mcp.sh` or checking Python/uv installation
```

Append this report to `harness-feedback.log` as well.

If `.samvil/mcp-health.jsonl` does not exist: print `[SAMVIL] MCP Health: All calls successful (0 failures logged)`.

```
[SAMVIL] ✓ Pipeline complete!

  App: ~/dev/<seed.name>/
  Run: cd ~/dev/<seed.name> && npm run dev

  Retrospective saved to harness-feedback.log.
  3 improvement suggestions recorded for future runs.
```

## Output Format

Append JSON entry to `harness-feedback.log` in the SAMVIL plugin directory.

**v3.0.1+**: 새 entry는 `suggestions_v2`만 사용. legacy `suggestions` (string array)는 쓰지 않는다.

```json
{
  "run_id": "samvil-YYYY-MM-DD-NNN",
  "seed_name": "<name>",
  "timestamp": "<ISO 8601>",
  "stages": {
    "interview": { "questions": <N> },
    "seed": { "user_edits": <N> },
    "scaffold": { "build_retries": <N> },
    "build": { "features_attempted": <N>, "features_passed": <N>, "retries": <N> },
    "qa": { "verdict": "<PASS|FAIL>", "iterations": <N> }
  },
  "metrics": {
    "stage_durations_ms": { "interview": <N>, "seed": <N>, "build": <N>, "qa": <N>, ... },
    "total_duration_ms": <N>,
    "build_pass_rate": <float>,
    "qa_pass_rate": <float>,
    "bottleneck_stages": ["<stage>", "<stage>"]
  },
  "suggestions_v2": [
    {
      "id": "v<major>-<NNN>",
      "priority": "<CRITICAL|HIGH|MEDIUM|LOW|BENEFIT>",
      "component": "<skill name or file path>",
      "name": "<one-line label>",
      "problem": "<what — include supporting data>",
      "fix": "<specific change, multi-step allowed>",
      "expected_impact": "<what improves>",
      "source": "<seed.name> dogfood",
      "sprint": ""
    },
    { ... },
    { ... }
  ]
}
```

Console output:
```
[SAMVIL] Retrospective — Run Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
App: <seed.name>
Features: <N>/<M> passed
Build Retries: <N>
QA Iterations: <N>
Final Verdict: <PASS/FAIL>
Flow Compliance: <matched / N deviations>
Agent Utilization: <M/N> (<percent>%)

[SAMVIL] 관측성 대시보드 — 병목 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  스테이지별 소요 시간:
    interview    <duration>s (<percent>%)
    seed          <duration>s (<percent>%)
    design        <duration>s (<percent>%)
    scaffold      <duration>s (<percent>%)
    build        <duration>s (<percent>%) ← 병목 (있으면)
    qa           <duration>s (<percent>%) ← 병목 (있으면)
  ─────────────────────────────
  총 소요: <total>s
  병목: <top 2 stages> (전체의 <percent>%)

  빌드 성공률: <N>/<M> (<percent>%)
  빌드 실행 횟수: <N>회
  QA 패스율 추이: <trend summary>

What Worked:
  - <observation with data>

What Needs Improvement:
  - <observation with data>

Suggestions (v3.0.1+ suggestions_v2 schema):
  1. v<major>-<NNN> [PRIORITY] <name>
     component: <skill or file>
     problem:   <what>
     fix:       <how>
     impact:    <expected>
     source:    <seed.name> dogfood

  2. v<major>-<NNN> [PRIORITY] <name>
     ...

  3. v<major>-<NNN> [PRIORITY] <name>
     ...
```

Exactly 3 suggestions with `{id, priority, component, name, problem, fix, expected_impact, source, sprint}` schema. All data from files — zero conversation-dependent metrics.

## Pipeline-End Narrate (v3.2.0, §6.1)

At the very end, after retro is written, invoke the Compressor-role
narrator for a one-page briefing the user can read in 30 seconds. This
is the only point in the pipeline where `samvil narrate` runs
automatically; everywhere else it's user-invoked.

```
# 1. Build the Compressor prompt from .samvil/ files.
mcp__samvil_mcp__narrate_build_prompt(
  project_root=".",
  since=""  # default: last 7 days
)
→ Parse the returned prompt. Run it through the current Compressor
  model (frugal cost_tier; route_task(task_role="compressor") picks
  the model).

# 2. Parse the LLM output.
mcp__samvil_mcp__narrate_parse(
  raw="<LLM response>"
)
→ Print the returned markdown under a "Pipeline summary" header.

# 3. Record as policy_adoption claim (not a gate verdict).
mcp__samvil_mcp__claim_post(
  project_root=".",
  claim_type="policy_adoption",
  subject="pipeline_end:<seed.name>",
  statement="run summary recorded",
  authority_file=".samvil/retro/retro-<run_id>.yaml",
  claimed_by="agent:retro-analyst",
  evidence_json='[".samvil/retro/retro-<run_id>.yaml", ".samvil/events.jsonl"]'
)
```

Narrate failures → log to `.samvil/mcp-health.jsonl` and skip. The
retro itself is still persisted; narrate is best-effort polish.

## Anti-Patterns

1. Do NOT blame the user — target harness improvements only
2. Do NOT include vague suggestions — each must specify `component` (which file) and `fix` (what to change)
3. Do NOT skip the MCP Health Report when `.samvil/mcp-health.jsonl` exists
4. **Do NOT write to legacy `suggestions` (string array) in new entries.** Use `suggestions_v2` dict array only. Legacy field is for entries 1~5 historical record.
5. Do NOT invent ID numbers — always scan existing `suggestions_v2[].id` across all entries and increment.

## Rules

1. **Be honest.** If the run was rough, say so.
2. **Be specific.** "Interview was too long" → "Interview asked 12 questions. Suggestion: reduce follow-ups, cap at 6."
3. **Target the harness, not the user.** Improvements are for SAMVIL's skills/references/templates.
4. **Exactly 3 suggestions.** Not 1, not 5. Three focused improvements.
5. **All data from files.** No conversation-dependent metrics.
6. **suggestions_v2 is SSOT.** All new analysis data flows into the dict schema. Legacy `suggestions` string field never receives new writes.
