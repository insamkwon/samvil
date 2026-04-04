---
name: samvil-interview
description: "Socratic interview with app presets, unknown-unknown probing, and zero-question mode. Korean language."
---

# SAMVIL Interview — Socratic Requirement Clarification

**모든 대화는 한국어로.** 코드와 기술 용어만 영어 허용.

## Boot Sequence (INV-1)

1. Read `project.state.json` → confirm `current_stage` is `"interview"`, read `selected_tier`
2. Read `references/app-presets.md` → preset 매칭 준비
3. The app idea is in the conversation context (from orchestrator)

## Step 0: Mode Detection

앱 아이디어에서 모드 감지:

**Zero-Question Mode** — "그냥 만들어", "ㄱ", "대충", "빨리", "skip", "just build" 포함 시:
→ Step 1에서 preset 매칭 → Step 3 스킵 → Step 4에서 seed 자동 생성 → 유저 검토 1회 → 완료

**Normal Mode** — 그 외 모든 경우:
→ 전체 인터뷰 진행

## Step 1: Preset 매칭

앱 아이디어에서 키워드로 `references/app-presets.md` 매칭:

```
"할일"/"todo"/"task" → todo
"대시보드"/"dashboard" → dashboard
"블로그"/"blog" → blog
"칸반"/"kanban"/"보드" → kanban
"랜딩"/"landing" → landing-page
"쇼핑"/"shop" → e-commerce
"계산기"/"calculator" → calculator
"채팅"/"chat" → chat
"포트폴리오"/"portfolio" → portfolio
"폼"/"설문"/"survey" → form-builder
```

**매칭 성공**: preset의 기본 기능/data model/흔한 함정을 컨텍스트에 로드
**매칭 실패**: competitor-analyst 에이전트를 spawn해서 유사 앱 서치 (full tier만) 또는 빈 프리셋으로 진행

## Step 2: Tier 기반 인터뷰 깊이

`selected_tier`에 따라 질문 수와 모호도 목표 결정:

| Tier | 질문 수 | 모호도 목표 | Phase 2.5 |
|------|--------|-----------|-----------|
| minimal | 3-4개 | ≤ 0.10 | 없음 |
| standard | 5-6개 | ≤ 0.05 | 없음 |
| thorough | 6-8개 | ≤ 0.02 | 있음 |
| full | 8개 + | ≤ 0.01 | 있음 + Research |

## Step 3: 인터뷰 질문

모든 질문은 **AskUserQuestion** 도구로 객관식 제시. preset이 있으면 보기에 preset 기본값 포함.

### Phase 1: Core Understanding (2-3 questions)

**한 번에 하나씩.** 답변 후 다음 질문.

1. **타겟 유저**: "이 앱을 주로 누가 사용하나요?"
   - preset 있으면: preset 기반 보기
   - 없으면: 개인 도구 / 팀 협업 / 고객 서비스 / Other

2. **핵심 경험**: "앱을 열면 첫 30초에 사용자가 할 행동은?"
   - preset 있으면: preset 기본 기능에서 보기 생성
   - 없으면: 앱 아이디어 기반 보기 3개 + Other

3. **성공 기준**: "반드시 동작해야 하는 것은?" (multiSelect: true)
   - preset 있으면: preset 기본 기능 전부를 보기로
   - 없으면: 맥락 기반 보기 4개 + Other

### Phase 2: Scope Definition (2-3 questions)

4. **필수 기능** (multiSelect: true):
   - preset 있으면: preset의 "자주 추가" 항목을 보기로
   - 없으면: 맥락 기반 4개 + Other

5. **제외 항목** (multiSelect: true):
   - preset 있으면: preset 유형에 흔한 scope creep 보기
   - 기본 보기: 실시간 협업 / 결제 / 알림 / 다국어 / Other

6. **제약 조건** (multiSelect: true):
   - 보기: 백엔드 없음(localStorage) / 모바일 반응형 필수 / 인증 필요 / 제약 없음 / Other

### Phase 2.5: Unknown Unknowns (thorough/full tier만)

preset의 **"흔한 함정"**과 **"Pre-mortem"**을 활용:

7. **Pre-mortem**: "이 앱을 깔았다가 1주 만에 삭제한 사람이 있다면, 이유가 뭘까요?"
   - preset의 Pre-mortem 사유를 보기로 + Other
   - multiSelect: true

8. **Inversion**: "이 앱에서 사용자가 가장 짜증날 수 있는 순간은?"
   - preset의 흔한 함정을 보기로 + Other
   - multiSelect: true

→ 답변을 AC 또는 constraints에 자동 반영

### Phase 3: Convergence Check

3 gates (모두 Y여야 진행):
```
□ Goal:  1문장 problem statement 작성 가능? (Y/N)
□ Scope: P1 기능 ≤ 5개, 각각 1줄 설명 가능? (Y/N)
□ AC:    testable 기준 ≥ 3개 도출됨? (Y/N)
```

MCP `score_ambiguity` 사용 가능 시:
`[SAMVIL] 모호도: 0.32 → 0.18 → 0.07 → 0.04 ✓ (목표: ≤ {tier_target})`

### Phase 4: 요약 & 확인

```
[SAMVIL] 인터뷰 요약
━━━━━━━━━━━━━━━━━━━━

타겟 유저: <누구>
핵심 문제: <어떤 문제>
핵심 경험: <첫 30초 행동>
앱 유형: <매칭된 preset 또는 "커스텀">

필수 기능 (P1):
  1. <기능>
  ...

제외 항목:
  - <빼는 것>
  ...

제약 조건:
  - <제약>
  ...

성공 기준:
  1. <testable 기준>
  ...

디자인 프리셋: <productivity/creative/minimal/playful>

가정 사항:
  - <가정>
```

AskUserQuestion으로 확인:
```
question: "이 요약이 맞나요?"
options:
  - "좋아, 진행해" → 다음 단계
  - "수정할 부분 있어" → 수정 후 재확인
```

## Zero-Question Mode 흐름

Step 0에서 감지 시:

1. Preset 매칭 (Step 1)
2. Preset 기본값으로 seed 수준 요약 자동 생성
3. 유저에게 요약 1회 제시 (Phase 4와 동일)
4. "ㄱ" → 바로 다음 단계 / "수정" → 수정 후 진행

## After User Approves (INV-3 + INV-4)

### 1. 인터뷰 요약 저장
Write `~/dev/<project>/interview-summary.md`

### 2. 디자인 프리셋 저장
interview-summary.md에 `디자인 프리셋: <preset>` 포함 → seed가 읽음

### 3. 상태 업데이트
`project.state.json`의 `current_stage` → `"seed"`

### 4. 진행 표시
```
[SAMVIL] Stage 1/5: 인터뷰 ✓
[SAMVIL] Stage 2/5: Seed 생성 중...
```

### 5. 체인
Invoke the Skill tool with skill: `samvil:seed`

## Rules

1. **모든 질문은 AskUserQuestion 도구 사용** — 객관식 보기 + Other
2. **대화는 한국어로.** 기술 용어와 코드만 영어.
3. **한 번에 하나씩.** 2개 이상 질문 금지.
4. **preset 있으면 활용.** 질문을 줄이고 보기 품질 높임.
5. **Phase 2.5는 thorough/full만.** minimal/standard에서는 스킵.
6. **Zero-Question은 요약 검토 1회 필수.** 완전 무확인 빌드는 안 됨.
7. **tier별 모호도 목표 준수.** minimal=0.10, standard=0.05, thorough=0.02, full=0.01.
8. **Tech stack 기본값:** Next.js 14 + Tailwind + shadcn/ui + App Router.
