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

### Step 3: Generate 3 Improvement Suggestions

Produce **exactly 3** actionable suggestions targeting the harness (skills, references, templates):

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
  - <observation>

What Needs Improvement:
  - <observation>

Suggestions:
  1. <specific change to a SAMVIL skill/reference/template>
  2. <specific change>
  3. <specific change>
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

Append a JSON entry to `harness-feedback.log` in the SAMVIL **plugin** directory (`harness-feedback.log (SAMVIL 플러그인 캐시 루트: `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`)`):

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
  "suggestions": ["...", "...", "..."]
}
```

If the file doesn't exist, create it. If it exists, append (read existing content, parse as JSON array, add entry, write back).

### Step 4b: Resolved Suggestion 정리

새 항목을 추가한 후, **기존 런의 suggestions 중 이미 스킬/코드에 반영된 것을 정리**한다.

1. 전체 harness-feedback.log를 순회하며 각 런의 `suggestions[]`를 읽는다
2. 각 suggestion에 대해: 해당 스킬 파일을 Grep으로 검색하여 반영 여부를 확인
   - 키워드(예: "UNIMPLEMENTED", "Playwright", "monorepo")가 스킬에 존재하면 → 반영됨
3. 반영된 suggestion은 해당 런에서 제거하고, `resolved_in` 필드에 현재 버전과 함께 기록:
   ```json
   "resolved_in": "v0.X.Y — <resolved items summary>"
   ```
4. 미반영 suggestion만 `suggestions[]`에 남긴다

**원칙**: 메트릭 데이터(stages, timestamp, seed_name)는 절대 삭제하지 않는다. suggestions만 정리한다.

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

Append JSON entry to `harness-feedback.log` in the SAMVIL plugin directory:

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
  "suggestions": ["<suggestion 1>", "<suggestion 2>", "<suggestion 3>"]
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
  - <observation>

What Needs Improvement:
  - <observation>

Suggestions:
  1. <specific change to a SAMVIL skill/reference/template>
  2. <specific change>
  3. <specific change>
```

Exactly 3 suggestions. All data from files — zero conversation-dependent metrics.

## Anti-Patterns

1. Do NOT blame the user — target harness improvements only
2. Do NOT include vague suggestions — each must specify which file to change and what to change
3. Do NOT skip the MCP Health Report when `.samvil/mcp-health.jsonl` exists

## Rules

1. **Be honest.** If the run was rough, say so.
2. **Be specific.** "Interview was too long" → "Interview asked 12 questions. Suggestion: reduce follow-ups, cap at 6."
3. **Target the harness, not the user.** Improvements are for SAMVIL's skills/references/templates.
4. **Exactly 3 suggestions.** Not 1, not 5. Three focused improvements.
5. **All data from files.** No conversation-dependent metrics.
