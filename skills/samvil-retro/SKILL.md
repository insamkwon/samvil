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

Update `project.state.json`:
- `current_stage`: `"complete"`
- `retro_count`: increment by 1

### Step 6: Final Message

```
[SAMVIL] ✓ Pipeline complete!

  App: ~/dev/<seed.name>/
  Run: cd ~/dev/<seed.name> && npm run dev

  Retrospective saved to harness-feedback.log.
  3 improvement suggestions recorded for future runs.
```

## Rules

1. **Be honest.** If the run was rough, say so.
2. **Be specific.** "Interview was too long" → "Interview asked 12 questions. Suggestion: reduce follow-ups, cap at 6."
3. **Target the harness, not the user.** Improvements are for SAMVIL's skills/references/templates.
4. **Exactly 3 suggestions.** Not 1, not 5. Three focused improvements.
5. **All data from files.** No conversation-dependent metrics.
