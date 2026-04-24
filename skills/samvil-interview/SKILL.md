---
name: samvil-interview
description: "Socratic interview with app presets, unknown-unknown probing, and zero-question mode. Korean language."
---

# SAMVIL Interview — Socratic Requirement Clarification

**모든 대화는 한국어로.** 코드와 기술 용어만 영어 허용.

## Boot Sequence (INV-1) — 명시적 Step 패턴 (v3.1.0, v3-017)

> 이 섹션은 모든 LLM (Claude / GLM / GPT) 에서 동일하게 실행되어야 한다. 각 step은 **"무엇을 하고 → 무엇을 확인한다"** 형식으로 명시. implicit reasoning에 의존하지 않는다.

**Step 0 — TaskUpdate**
- Do: "Interview" task를 `in_progress`로 설정
- → Result: task tracker에서 current task가 in_progress

**Step 1 — Read project.state.json**
- Do: `project.state.json`을 Read tool로 읽기
- → Result: `current_stage == "interview"` 확인, `session_id` 변수에 저장
- → If fail: state.json 없으면 orchestrator 재시작 필요 — 사용자에게 보고 + STOP

**Step 2 — Read project.config.json**
- Do: `project.config.json` Read
- → Result: `selected_tier` 변수에 저장 (minimal/standard/thorough/full/deep 중 하나)
- → If fail: tier unknown → default `standard` 사용

**Step 3 — Read references/app-presets.md**
- Do: `references/app-presets.md`를 Read (built-in preset pool)
- → Result: preset 매칭용 context 확보

**Step 4 — 커스텀 프리셋 스캔**
- Do: `~/.samvil/presets/` 디렉토리 체크
  - 없으면: `mkdir -p ~/.samvil/presets` 실행 → 빈 상태로 진행
  - 있으면: `*.json` 파일 목록 수집, 각 파일의 `name` + `keywords` 파싱
- → Result: `custom_presets` 변수에 배열 저장 (비어있을 수 있음)

**Step 5 — Pipeline context**
- Do: 오케스트레이터가 전달한 app idea를 대화 컨텍스트에서 추출
- → Result: `app_idea` 변수에 문장 저장

**Step 6 — Boot sequence common protocol**
- Do: `references/boot-sequence.md` Read → metrics 시작, checkpoint rules 적용
- → Result: `.samvil/metrics.json` 초기화됨

**Step 7 — MCP interview_start event (best-effort)**
- Do: `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="interview_start", stage="interview", data='{"tier":"<selected_tier>","custom_presets":<N>}')`
- → Result: events.jsonl에 start 이벤트 기록
- → If MCP fail: graceful degradation (INV-5) — continue without event

## Step 0: Mode Detection

앱 아이디어에서 모드 감지:

**Zero-Question Mode** — "그냥 만들어", "ㄱ", "대충", "빨리", "skip", "just build" 포함 시:
→ Step 1에서 preset 매칭 → Step 3 스킵 → Step 4에서 seed 자동 생성 → 유저 검토 1회 → 완료

**Normal Mode** — 그 외 모든 경우:
→ 전체 인터뷰 진행

## Step 0.5: 커스텀 프리셋 선택

Boot Sequence에서 감지한 커스텀 프리셋이 있을 경우:

**감지된 프리셋이 있는 경우:**
```
[SAMVIL] 감지된 커스텀 프리셋: <N>개
  - <프리셋명1>: <설명>
  - <프리셋명2>: <설명>
```

AskUserQuestion으로 선택:
```
question: "저장된 프리셋을 사용하시겠어요?"
header: "커스텀 프리셋"
options:
  - label: "<프리셋명1>"
    description: "<설명>"
  - label: "<프리셋명2>"
    description: "<설명>"
  - label: "새로 만들게요"
    description: "저장된 프리셋 없이 인터뷰 진행"
```

**선택 시**: 해당 커스텀 프리셋을 preset으로 로드 → Phase 2.5 자동 활성화
**"새로 만들게요"**: 기존 Step 1 빌트인 매칭으로 진행

**커스텀 프리셋이 없는 경우**: 이 단계를 건너뛰고 Step 1로 진행

## Step 0.7: PATH Routing + Rhythm Guard + Tracks (v2.4.0+, P2/P4)

**v2.4.0부터 실제 활성화.** 상세 규칙은 `references/path-routing-guide.md` 참조.

### 0.7a. 초기 스캔 (1회)

인터뷰 시작 시 프로젝트 manifest 스캔:

```
manifest_facts = mcp__samvil_mcp__scan_manifest(project_path="<CWD>")
```

결과를 state.json에 `manifest_facts` 필드로 저장 (향후 재사용).

Brownfield인 경우 사용자에게 표시:
```
[SAMVIL] 🔍 프로젝트 스캔 중...
[SAMVIL] ℹ️ 자동 감지: Next.js 14.2.0, TypeScript, Prisma+PostgreSQL
         출처: package.json, prisma/schema.prisma
```

### 0.7b. 각 질문마다 라우팅

모든 인터뷰 질문은 다음 프로세스:

```
1. 현재 streak 읽기: streak = state.get("ai_answer_streak", 0)
2. Rhythm Guard 체크: force_user = streak >= 3
3. 라우팅:
   result = mcp__samvil_mcp__route_question(
       question=<질문>,
       manifest_facts=<JSON>,
       force_user=force_user
   )
4. Path별 액션 (아래 표)
5. 답변 후 streak 업데이트:
   source = mcp__samvil_mcp__extract_answer_source(answer)
   result = mcp__samvil_mcp__update_answer_streak(streak, source)
   state["ai_answer_streak"] = result["new_streak"]
```

| Path | 액션 |
|------|------|
| `auto_confirm` | 사용자 미개입. `[from-code][auto-confirmed]` 바로 기록 + ℹ️ 표시 |
| `code_confirm` | AskUserQuestion Y/N. Yes → `[from-code]`, No → 수정 입력 `[from-user][correction]` |
| `user` | 일반 AskUserQuestion. `[from-user]` |
| `research` | Tavily 검색 → 사용자 Y/N 확인 → `[from-research]` or `[from-user][correction]` |
| `forced_user` | ⚠️ Rhythm Guard 메시지 + AskUserQuestion. `[from-user]` |

### 0.7c. Tracks 관리 (Breadth-Keeper, P4)

Features 파악 후 초기화:
```
tracks = mcp__samvil_mcp__manage_tracks(action="init", features=<JSON>)
state["interview_tracks"] = tracks
```

매 라운드마다 active track 업데이트 + Breadth check:
```
tracks = mcp__samvil_mcp__manage_tracks(action="update", tracks_json=..., track_name=<current>)
verdict = mcp__samvil_mcp__manage_tracks(action="check", tracks_json=...)

if verdict["force_breadth"]:
    # 다른 tracks로 전환 리마인드
    ask: "{reason} — 이 중 먼저 정할 게 있나요?"
```

토픽 완료 시:
```
tracks = mcp__samvil_mcp__manage_tracks(action="resolve", tracks_json=..., track_name=<done>)
```

### 0.7d. Milestone 시각화 (#05)

`score_ambiguity` 결과에 v2.4.0+ 추가 필드:
- `milestone` — INITIAL / PROGRESS / REFINED / READY
- `floors_passed` — 모든 component floor 통과 여부
- `floor_violations` — 위반 리스트
- `missing_items` — 아직 없는 필드 목록

매 라운드 끝 사용자에게 표시:
```
[SAMVIL] 진행: PROGRESS (0.35 → 0.22)
  ┌─ Goal Clarity        0.92 ✓
  ├─ Constraint Clarity  0.58 ⚠ (floor 0.65 미달)
  └─ Success Criteria    0.85 ✓
  
  약한 부분: Constraint
  미정: {missing_items 중 상위 3개}
```

### 0.7e. Fallback (MCP 실패 시 — INV-5)

MCP 호출 실패하면:
- `scan_manifest` 실패 → facts={} (greenfield로 간주)
- `route_question` 실패 → path="user" (안전하게 사용자에게)
- `update_answer_streak` 실패 → streak 유지, guard 비활성
- 파이프라인은 중단하지 않음

## Step 1: Preset 매칭

앱 아이디어에서 키워드로 매칭. **커스텀 프리셋 > 빌트인 프리셋** 순서로 검색.

### 1a. 커스텀 프리셋 매칭

`~/.samvil/presets/*.json` 파일들의 `keywords` 필드와 앱 아이디어 비교:
- 키워드가 앱 아이디어에 포함되면 매칭
- 여러 개 매칭 시 가장 많은 키워드가 일치하는 것 선택

### 1b. 빌트인 프리셋 매칭

커스텀 매칭 실패 시 `references/app-presets.md` 매칭:

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

### 1c. 프리셋 내보내기 (Post-Interview)

인터뷰 완료 후, 사용자가 이 앱 유형을 재사용할 수 있도록 프리셋으로 저장 가능:

```
/samvil --export-preset <name>
```

실행 시 `project.seed.json`에서 프리셋 포맷(JSON)으로 변환하여 `~/.samvil/presets/<name>.json`에 저장.
저장 시 `keywords` 필드에 앱 아이디어의 핵심 명사를 자동 추출하여 포함.

## Step 2: Tier 기반 인터뷰 깊이 (v3.1.0 확장, v3-022)

`selected_tier`에 따라 질문 수, 모호도 목표, 필수 Phase 세트를 결정.

| Tier | 질문 수 | 모호도 목표 | 필수 Phase |
|------|--------|-----------|-----------|
| minimal | 3-4개 | ≤ 0.10 | Core(1) + Scope(2) |
| standard | 5-6개 | ≤ 0.05 | Core + Scope + **Lifecycle(2.9, 8Q)** |
| thorough | 6-8개 | ≤ 0.02 | + Unknown(2.5) + **Non-func(2.6, 3Q)** + **Inversion(2.7)** |
| full | 8개 + | ≤ 0.01 | + **Stakeholder/JTBD(2.8)** + PATH 4 Research |
| **deep** | **10개 +** | **≤ 0.005** | full + **Domain pack 25~30Q 심화** + premortem 반복 |

**Deep Mode 활성화 경로** (v3-022 fix f):
- `/samvil:interview --deeper` 플래그가 있으면 tier를 `deep`로 승격
- 인터뷰 중 사용자가 "더 깊게", "더 디테일", "production 수준"이라 입력 시 tier 즉시 승격 후 AskUserQuestion으로 확인
- Phase 3 Convergence Check 종료 시 사용자가 "아직 부족한 느낌"이라 답하면 AskUserQuestion으로 Deep Mode 제안 (한 번만)

**Framework reference**: `references/interview-frameworks.md` 읽어서 각 Phase 수행 방법 확인. `references/interview-question-bank.md`에서 solution_type별 pool 참조.

**Tier → Phase 매핑 (MCP tool, v3.1.0 Polish #5)**

Tier별 필수 phase를 하드코딩하지 말고 MCP에서 읽어온다:

```
phases_info = mcp__samvil_mcp__get_tier_phases(tier=<selected_tier>)
# Returns: {"tier": "...", "phases": [...], "ambiguity_target": 0.xx, "all_tiers": [...]}
```

예:
- `tier=standard` → phases=["core", "lifecycle", "scope"], target=0.05
- `tier=thorough` → phases=["core", "inversion", "lifecycle", "nonfunc", "scope", "unknown"], target=0.02
- `tier=deep` → 모든 phase 활성 + `domain_deep`, target=0.005

SKILL이 각 Phase 진입 전에 phases 리스트 멤버십을 체크해서 skip 여부 결정:
- `"nonfunc"` ∈ phases → Phase 2.6 실행
- `"inversion"` ∈ phases → Phase 2.7 실행
- `"stakeholder"` ∈ phases → Phase 2.8 실행
- `"lifecycle"` ∈ phases → Phase 2.9 실행
- `"domain_deep"` ∈ phases → Domain pack 25~30Q 강제

MCP 실패 시 fallback: tier 이름 기반 prose lookup (이 SKILL의 기존 표).

## Step 3: 인터뷰 질문

모든 질문은 **AskUserQuestion** 도구로 객관식 제시. preset이 있으면 보기에 preset 기본값 포함.

### 답변 적응형 질문 (Adaptive Follow-up)

각 답변 후 길이/내용을 분석하여 후속 질문 전략을 선택:

| 답변 유형 | 판정 기준 | 후속 질문 전략 |
|-----------|----------|---------------|
| **긴 답변** | 100자 이상 또는 여러 주제 포함 | 구조화 질문: "구체적으로 어떤 화면에서 어떻게 동작하나요?" / "말씀하신 A와 B 중 먼저 만들 건가요?" |
| **짧은 답변** | 30자 미만 또는 단어 1-2개 | 확장 질문: "~하는 이유가 무엇인가요? 어떤 문제를 해결하고 싶나요?" / "예를 들면 어떤 상황인가요?" |
| **모호한 답변** | vague 단어 포함 또는 "적당히", "알아서", "대충" | 선택 질문: "A와 B 중 어떤 방향에 더 가까운가요?" / "구체적으로 수치나 기준이 있나요?" |

**적용 규칙:**
- adaptive follow-up은 Phase 1~2 내에서만. Phase 3(Convergence)에서는 미적용.
- 같은 주제에 대한 연속 follow-up은 최대 1회. 2회 연속 시 다음 Phase로 전환.
- 짧은 답변이어도 선택지 중 하나를 선택한 경우 → follow-up 없이 다음 질문.

### Phase 1: Core Understanding (2-3 questions)

**한 번에 하나씩.** 답변 후 다음 질문.

#### solution_type: "web-app" (기본)

1. **타겟 유저**: "이 앱을 주로 누가 사용하나요?"
   - preset 있으면: preset 기반 보기
   - 없으면: 개인 도구 / 팀 협업 / 고객 서비스 / Other

2. **핵심 경험**: "앱을 열면 첫 30초에 사용자가 할 행동은?"
   - preset 있으면: preset 기본 기능에서 보기 생성
   - 없으면: 앱 아이디어 기반 보기 3개 + Other

3. **성공 기준**: "반드시 동작해야 하는 것은?" (multiSelect: true)
   - preset 있으면: preset 기본 기능 전부를 보기로
   - 없으면: 맥락 기반 보기 4개 + Other

#### solution_type: "automation"

1. **해결할 문제**: "이 자동화가 해결할 문제는 무엇인가요?"
   - 보기: 반복 수작업 자동화 / 데이터 수집 및 변환 / 알림/리포트 자동 생성 / 외부 시스템 연동 / Other

2. **입력과 출력**: "무엇을 넣고, 무엇을 얻고 싶나요?"
   - 보기: API 데이터 → 정리된 리포트 / 파일(CSV/JSON) → 변환된 파일 / 이메일/메시지 → 요약 / 웹페이지 → 추출 데이터 / Other

3. **실행 트리거**: "이 자동화는 언제 실행되나요?" (multiSelect: false)
   - 보기: 수동 실행 (명령어로 직접) / 정기 실행 (cron, 매일/매주) / 웹훅 (외부 이벤트 수신) / 파일 변경 감지 / Other

#### solution_type: "game"

**안내 메시지 (최초 1회 표시):**
```
[SAMVIL] 게임 모드로 진행합니다.
  Claude Code는 Unity, Unreal Engine, Godot 등의 네이티브 게임 엔진을 실행할 수 없습니다.
  대신 Phaser 3 (웹 기반 2D 게임 엔진)로 브라우저에서 동작하는 게임을 만듭니다.
  - 가능: 2D platformer, puzzle, arcade, 간단한 RPG
  - 불가능: 3D 게임, 복잡한 물리 시뮬레이션, 대형 MMORPG
```

1. **장르**: "어떤 장르의 게임인가요?"
   - 보기: platformer (점프/달리기) / puzzle (퍼즐/매칭) / arcade (슈팅/회피) / 간단한 RPG / Other

2. **조작 방식**: "플레이어 조작은 어떻게 하나요?" (multiSelect: true)
   - 보기: keyboard (방향키/WASD) / mouse (클릭/드래그) / touch (모바일 터치) / Other

3. **게임 목표**: "게임의 핵심 목표는 무엇인가요?"
   - 보기: 점수 달성 (score attack) / 시간 생존 (survival) / 레벨 클리어 (level completion) / 아이템 수집 (collection) / Other

4. **그래픽 스타일**: "그래픽 스타일은 어떻게 할까요?"
   - 보기: pixel art (8-bit/16-bit) / simple shapes (원, 사각형 기반) / minimal flat / Other
   - **안내**: "Phaser 3는 2D 스프라이트 기반입니다. 3D 모델링은 불가능합니다. 복잡한 애니메이션은 코드로 생성하는 simple shapes를 추천합니다."

#### solution_type: "mobile-app"

**안내 메시지 (최초 1회 표시):**
```
[SAMVIL] 모바일 앱 모드로 진행합니다.
  Claude Code는 네이티브 iOS/Android 앱을 직접 빌드할 수 없습니다.
  대신 Expo (React Native)로 크로스 플랫폼 앱을 만듭니다.
  - 가능: iOS + Android 동시 지원, 카메라/GPS/푸시알림 접근, 웹 미리보기
  - 불가능: Swift/Kotlin 전용 기능, App Store 직접 제출 (가이드만 제공)
```

1. **플랫폼**: "어떤 플랫폼을 타겟으로 하나요?"
   - 보기: iOS만 / Android만 / 둘 다 (추천) / Other

2. **핵심 경험**: "앱을 열면 첫 30초에 사용자가 할 행동은?"
   - 보기: 앱 아이디어 기반 보기 3개 + Other

3. **성공 기준**: "반드시 동작해야 하는 것은?" (multiSelect: true)
   - 보기: 맥락 기반 보기 4개 + Other

### Phase 2: Scope Definition (2-3 questions)

#### solution_type: "web-app" (기본)

4. **필수 기능** (multiSelect: true):
   - preset 있으면: preset의 "자주 추가" 항목을 보기로
   - 없으면: 맥락 기반 4개 + Other

5. **제외 항목** (multiSelect: true):
   - preset 있으면: preset 유형에 흔한 scope creep 보기
   - 기본 보기: 실시간 협업 / 결제 / 알림 / 다국어 / Other

6. **제약 조건** (multiSelect: true):
   - 보기: 백엔드 없음(localStorage) / 모바일 반응형 필수 / 인증 필요 / 제약 없음 / Other

6b. **데이터 & 인프라** (인증 필요 또는 제약 없음 선택 시):
   AskUserQuestion:
   ```
   question: "데이터 저장과 인증을 어떻게 할까요?"
   header: "인프라"
   options:
     - label: "Supabase (추천)"
       description: "PostgreSQL DB + 인증 + Storage. 실제 프로덕션 배포 가능."
     - label: "로컬 localStorage"
       description: "백엔드 없이 브라우저에만 저장. 빠르지만 새로고침 시 유지."
     - label: "별도 설정 안 함"
       description: "나중에 직접 연동하겠습니다."
   ```

6c. **외부 API** (필요 시):
   If the app idea involves external APIs (AI, payment, maps, etc.):
   ```
   question: "외부 API 연동이 필요한가요?"
   header: "API"
   options:
     - label: "네, API 키를 가지고 있어요"
       description: ".env.example에 API 키 설정을 포함합니다."
     - label: "나중에 연동할게요"
       description: "API 호출 부분은 env var 패턴으로 작성, 키는 나중에 설정."
     - label: "필요 없어요"
       description: "외부 API 없이 자체 데이터만 사용합니다."
   ```

#### solution_type: "game"

4. **게임 요소** (multiSelect: true):
   - 보기: 적 (enemy) / 아이템/수집품 (collectible) / 장애물 (obstacle) / 점수 시스템 (scoring) / 타이머 (timer) / 레벨/스테이지 (levels) / Other

5. **게임 난이도**:
   ```
   question: "게임 난이도를 어떻게 할까요?"
   header: "난이도"
   options:
     - label: "쉬움 (casual)"
       description: "누구나 쉽게 즐길 수 있는 난이도. 클론 코딩 수준."
     - label: "보통 (normal)"
       description: "일반적인 게임 난이도. 약간의 도전."
     - label: "어려움 (hard)"
       description: "하드코어 게이머 대상. 정밀한 조작 필요."
   ```

6. **제약 조건** (multiSelect: true):
   - 보기: 모바일 터치 지원 필수 / 외부 에셋 사용 안 함 (코드로 생성) / 사운드 포함 / Other

#### solution_type: "automation"

4. **API 연동** (multiSelect: true):
   ```
   question: "어떤 외부 시스템과 연동하나요?"
   header: "연동"
   options:
     - label: "REST API"
       description: "외부 HTTP API 호출 (날씨, 주식, CRM 등)"
     - label: "Slack / Discord"
       description: "메시지 전송 또는 수신"
     - label: "데이터베이스"
       description: "PostgreSQL, MySQL, Supabase 등"
     - label: "파일 시스템"
       description: "CSV/JSON/Excel 파일 읽기/쓰기"
     - label: "이메일"
       description: "SMTP로 메일 발송"
     - label: "Other"
       description: "다른 시스템 (직접 입력)"
   ```

5. **에러 처리**:
   ```
   question: "실행 중 에러가 발생하면 어떻게 할까요?"
   header: "에러 처리"
   options:
     - label: "재시도 + 로깅 (추천)"
       description: "일시적 에러는 자동 재시도, 영구 에러는 로그 남기고 종료."
     - label: "침묵 (건너뛰기)"
       description: "에러 아이템은 건너뛰고 나머지 계속 처리."
     - label: "즉시 알림"
       description: "에러 발생 즉시 Slack/이메일로 알림."
     - label: "Other"
       description: "다른 방식 (직접 입력)"
   ```

6. **실행 환경**:
   ```
   question: "이 자동화를 어디서 실행할까요?"
   header: "실행 환경"
   options:
     - label: "로컬 Python (추천)"
       description: "Python 스크립트. API/데이터 처리에 강점. pip 설치 필요."
     - label: "로컬 Node.js"
       description: "TypeScript/JavaScript. JS 생태계 활용."
     - label: "간단한 Shell"
       description: "단순 시스템 작업 (파일 이동, 백업 등)."
     - label: "CC 스킬"
       description: "Claude Code 내에서 실행. AI 판단이 필요한 작업에 적합."
   ```

#### solution_type: "mobile-app"

4. **네이티브 기능** (multiSelect: true):
   ```
   question: "네이티브 기능이 필요한가요?"
   header: "네이티브"
   options:
     - label: "카메라"
       description: "사진 촬영, QR 코드 스캔"
     - label: "GPS / 위치"
       description: "현재 위치, 지도 연동"
     - label: "푸시 알림"
       description: "원격 푸시 알림 수신"
     - label: "센서"
       description: "가속도, 자이로, 생체인증 등"
     - label: "필요 없어요"
       description: "일반적인 UI 앱"
     - label: "Other"
       description: "다른 네이티브 기능 (직접 입력)"
   ```

5. **네비게이션**:
   ```
   question: "앱의 기본 네비게이션 구조는?"
   header: "네비게이션"
   options:
     - label: "탭바 (추천)"
       description: "하단 탭으로 화면 전환. 대부분의 앱에 적합."
     - label: "드로어"
       description: "사이드 메뉴. 설정이 많은 앱에 적합."
     - label: "스택"
       description: "화면 위에 화면 쌓기. 상세 페이지 중심."
     - label: "Other"
       description: "다른 네비게이션 (직접 입력)"
   ```

6. **오프라인 지원**:
   ```
   question: "오프라인에서도 동작해야 하나요?"
   header: "오프라인"
   options:
     - label: "아니요, 온라인만"
       description: "인터넷 연결 필수. 구현 단순."
     - label: "네, 기본 오프라인"
       description: "캐싱으로 이전 데이터 표시. 온라인 복구 시 동기화."
     - label: "네, 완전 오프라인"
       description: "모든 기능 오프라인 동작. 로컬 DB 필요."
   ```

### Phase 2.5: Unknown Unknowns (thorough/full tier + 자동 감지)

**활성화 조건** (둘 중 하나):
- `selected_tier`가 `thorough` 또는 `full`
- **자동 감지**: Phase 1~2 답변에서 불확실성이 높은 경우 (preset 매칭 실패 + 짧은 답변 비율 > 50%)

자동 감지 시 minimal/standard라도 Phase 2.5를 활성화하되, 질문은 1개로 축소 (Pre-mortem만).

preset의 **"흔한 함정"**과 **"Pre-mortem"**을 활용:

7. **Pre-mortem**: "이 앱을 깔았다가 1주 만에 삭제한 사람이 있다면, 이유가 뭘까요?"
   - preset의 Pre-mortem 사유를 보기로 + Other
   - multiSelect: true

8. **Inversion (짜증 포인트)**: "이 앱에서 사용자가 가장 짜증날 수 있는 순간은?"
   - preset의 흔한 함정을 보기로 + Other
   - multiSelect: true

→ 답변을 AC 또는 constraints에 자동 반영

### Phase 2.6: Non-functional (thorough+ 의무, v3.1.0 신설, v3-022)

기능이 아닌 **품질 속성**을 인터뷰. `references/interview-frameworks.md` § 2 참조.

thorough tier: **3개 필수** (맥락상 중요한 것만)
full/deep tier: **7개 전체**

질문 pool (`references/interview-question-bank.md` Common § 1~7):
- Performance target (LCP / first paint)
- Accessibility target (WCAG AA / keyboard-only)
- Security sensitivity (pii / payment / enterprise / none)
- Data retention (탈퇴 시 보관 기간)
- Offline support (none / cached / full-offline)
- i18n languages
- Error UX style

결과는 `seed.non_functional` 객체로 저장 (seed-schema.json 참조).

### Phase 2.7: Inversion Phase (thorough+ 의무, v3.1.0 강화, v3-022)

`references/interview-frameworks.md` § 3 참조. Phase 2.5의 Pre-mortem/Inversion과는 중복 아닌 **강화**:

9. **Failure Path Premortem**: "이 앱이 6개월 후 폐기된다면, 가능성 높은 이유 3가지는?"
   - multiSelect: true, 4~5 보기 + Other
   - 예시 보기: onboarding 이탈 / 경쟁 차별화 실패 / API cost 초과 / 유지보수 부담 / 보안 사고

10. **Explicit Exclusions**: "이 앱이 **절대로** 다루지 않을 것은?"
    - multiSelect: true, seed.exclusions + seed.inversion.anti_requirements에 기록

11. **Anti-requirements**: "사용자가 **못** 하게 막아야 할 것은?"
    - 예시: 중복 가입 / 결제 우회 / admin 권한 스스로 부여
    - 답변을 seed.inversion.anti_requirements에 저장

deep tier면 추가:
12. **Abuse vectors**: "악의적 사용자가 어떻게 남용할 수 있을까요?"
    - 예시: spam/bot/결제 우회/스크래핑

### Phase 2.8: Stakeholder / JTBD (full+ 의무, v3.1.0 신설, v3-022)

`references/interview-frameworks.md` § 4 참조. full tier 이상에서만 수행.

13. **Primary user JTBD**:
    - 템플릿: "When <상황>, I want to <동기>, so I can <결과>."
    - AskUserQuestion으로 각 필드 분리 수집 후 합성
    - seed.stakeholders.primary_user_jtbd에 저장

14. **Secondary users**: "가끔 협업/관리하는 다른 역할이 있나요? (admin/reviewer/observer/없음)"

15. **Decision maker + Payer**: "누가 사용을 결정하나요?" + "결제 시 누가 내나요?"

16. **Motivation vs Alternatives**: "엑셀/노션/종이 대신 이 앱을 써야 하는 결정적 이유는?"

### Phase 2.9: Customer Lifecycle Journey (standard+ 의무, v3.1.0 신설, v3-023)

`references/interview-frameworks.md` § 5 참조. **8단계 각 1-2Q = 10-15Q 추가**.

**사용자에게는 framework 이름(AARRR/HEART/JTBD)을 노출하지 않는다.** 자연스러운 한국어 질문으로 바꿔 묻는다.

standard tier: 축약 (각 1Q, 핵심 8개)
thorough/full/deep: 상세 (각 1-2Q, 하위 정책 포함)

| Stage | 질문 패턴 | Seed 필드 |
|---|---|---|
| Discovery | 사용자가 이 앱을 어떻게 알게 되나요? (검색/추천/광고/오프라인) | `customer_lifecycle.discovery` |
| First Open | 처음 5초에 뭘 보나요? empty state는? | `.first_open` |
| Onboarding | 가입 강제? tutorial? sample data? | `.onboarding` |
| Activation | '아 이거 좋네'라고 느끼는 정확한 순간은? | `.activation` |
| Retention | 다시 오는 이유? push/email 정책? | `.retention` |
| Completion | 다 쓰고 나면? (게임 클리어/할일 완수/content 소진) | `.completion` |
| Re-engagement | 한 달 떠난 사용자 win-back 전략? | `.re_engagement` |
| Churn | 이탈 감지 + 데이터 보관 정책? | `.churn` + `.data_retention` |

**Unknown Unknowns 처리** (v3-023 fix e):
- 사용자가 "모르겠다", "아직 생각 안 해봤다" 답변 시 해당 필드에 `"TBD — research needed"` 저장
- PATH 4 Research에 자동 위임 (deep tier면 즉시, 다른 tier는 Phase 3 종료 후 일괄)
- Research 결과를 AskUserQuestion 3개 보기로 변환해 재확인

**Council/Design 연결** (v3-023 fix d):
- samvil-council의 ux-designer/ux-researcher agent prompt에 `customer_lifecycle` 자동 주입
- samvil-design의 blueprint.json에 `onboarding_flow`, `empty_state_design`, `re_engagement_strategy` 섹션 생성

### Phase 3: Convergence Check

#### 인터뷰 종료 조건

인터뷰는 **ambiguity_score ≤ tier 임계값**일 때 종료 가능:

| Tier | 종료 임계값 | 재질문 없이 종료 가능 |
|------|-----------|---------------------|
| minimal | ≤ 0.10 | O (preset 매칭 시) |
| standard | ≤ 0.05 | preset 매칭 + Phase 1 + Phase 2.9 Lifecycle 충실 시 |
| thorough | ≤ 0.02 | X (Phase 2.5 + 2.6 + 2.7 + 2.9 필수) |
| full | ≤ 0.01 | X (+ Phase 2.8 + Research 필수) |
| **deep** | **≤ 0.005** | **X (full + Domain pack 25~30Q + premortem 심화 필수)** |

**종료 루프:**
1. Phase 3 gates 평가
2. `mcp__samvil_mcp__score_ambiguity` 호출
3. score ≤ 임계값 AND 모든 gates = Y → Phase 4로 진행
4. score > 임계값 → vague AC 재질문 + 부족한 gate 보충 질문
5. 재질문 후 다시 평가 (최대 2회 반복, 이후 강제 진행)

4 gates (모두 Y여야 진행):
```
□ Goal:        1문장 problem statement 작성 가능? (Y/N)
□ Scope:       P1 기능 ≤ 5개, 각각 1줄 설명 가능? (Y/N)
□ AC:          testable 기준 ≥ 3개 도출됨? (Y/N)
□ Constraints: 제약 조건 1개 이상 명시됨? (Y/N)
```

**AC Testability Gate (PHI-06):** 각 AC에 대해 vague 단어가 있는지 검사.
Vague: "좋은", "빠른", "깔끔한", "직관적인", "부드러운", "전문적인", "모던한", "사용자 친화적인", "good", "nice", "fast", "clean", "intuitive", "smooth", "user-friendly"

vague AC가 있으면 재질문:
```
question: "이 성공 기준이 좀 모호해요. 구체적으로 어떤 걸 의미하나요?"
header: "AC 구체화"
options:
  - label: "<자동 제안된 rewrite>"
    description: "<rewrite_hint 기반>"
  - Other로 직접 입력
```

Constraints가 비어있으면 추가 질문: "이 앱에 제약 조건이 있나요? (예: 백엔드 없음, 모바일 필수, 특정 브라우저만 등)"
답변이 없어도 기본값 추가: "No backend server — client-only with localStorage"

**MCP (best-effort):** Call `mcp__samvil_mcp__score_ambiguity` with interview state JSON and tier:
```
mcp__samvil_mcp__score_ambiguity(interview_state='{"target_user":"...","core_problem":"...","core_experience":"...","features":[...],"exclusions":[...],"constraints":[...],"acceptance_criteria":[...]}', tier="<selected_tier>")
```
Display: `[SAMVIL] 모호도: 0.32 → 0.18 → 0.07 → 0.04 ✓ (목표: ≤ {tier_target})`

### Phase 3.5: 스택 추천

#### solution_type: "web-app"

preset의 **추천 스택**을 기반으로 스택 제안:

```
question: "기술 스택을 추천합니다. 변경할 수 있어요."
header: "스택"
options:
  - label: "<추천 스택> (추천)"
    description: "<추천 이유>"
  - label: "Next.js"
    description: "SSR, API routes, SEO. 대부분의 웹앱에 적합."
  - label: "Vite + React"
    description: "가벼운 SPA. SSR 불필요한 도구/유틸리티에 적합."
  - label: "Astro"
    description: "정적 사이트. 랜딩 페이지, 블로그에 최적."
```

선택 결과를 interview-summary.md에 `추천 스택: <선택>` 으로 저장.
Seed에서 `tech_stack.framework`에 매핑:
- Next.js → `"nextjs"`
- Vite + React → `"vite-react"`
- Astro → `"astro"`

#### solution_type: "game"

```
question: "게임 기술 스택을 추천합니다."
header: "스택"
options:
  - label: "Phaser 3 + Vite + TypeScript (추천)"
    description: "2D 웹 게임 표준. Canvas/WebGL 렌더링. 모든 브라우저 지원."
  - label: "Phaser 3 + Vite + JavaScript"
    description: "TypeScript 없이 순수 JavaScript. 더 간단한 설정."
```

선택 결과를 interview-summary.md에 `추천 스택: <선택>` 으로 저장.
Seed에서 `tech_stack.framework`에 매핑:
- Phaser 3 + TypeScript → `"phaser"`
- Phaser 3 + JavaScript → `"phaser"`

#### solution_type: "automation"

Phase 2에서 선택한 실행 환경 기반으로 스택 확정:

```
question: "자동화 기술 스택을 추천합니다."
header: "스택"
options:
  - label: "Python (추천)"
    description: "API/데이터 처리 강점. requests, pandas 등 풍부한 라이브러리."
  - label: "Node.js (TypeScript)"
    description: "JS 생태계 활용. Slack/Discord SDK 등 네이티브 지원."
  - label: "Shell Script"
    description: "간단한 시스템 작업. 파일 이동, 백업, cron 작업."
  - label: "CC 스킬"
    description: "Claude Code 내에서 실행. AI 판단이 필요한 작업."
```

선택 결과를 interview-summary.md에 `추천 스택: <선택>` 으로 저장.
Seed에서 `tech_stack.framework`에 매핑:
- Python → `"python-script"`
- Node.js → `"node-script"`
- Shell → `"shell-script"`
- CC 스킬 → `"cc-skill"`

#### solution_type: "mobile-app"

```
question: "모바일 기술 스택을 추천합니다."
header: "스택"
options:
  - label: "Expo + React Native + TypeScript (추천)"
    description: "iOS + Android 동시 지원. Expo로 빠른 개발. Claude Code에서 웹 미리보기 가능."
  - label: "Expo + React Native + JavaScript"
    description: "TypeScript 없이 순수 JavaScript. 더 간단한 설정."
```

**안내**: "Expo는 Claude Code가 네이티브 앱을 직접 빌드할 수 없는 환경에서 유일하게 사용 가능한 모바일 프레임워크입니다. 웹 버전으로 미리보기하고 EAS Build로 실제 APK/IPA를 생성합니다."

선택 결과를 interview-summary.md에 `추천 스택: <선택>` 으로 저장.
Seed에서 `tech_stack.framework`에 매핑:
- Expo + TypeScript → `"expo"`
- Expo + JavaScript → `"expo"`

### Phase 4: 요약 & 확인

#### web-app 요약

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

#### game 요약

```
[SAMVIL] 인터뷰 요약 (Game)
━━━━━━━━━━━━━━━━━━━━

장르: <platformer/puzzle/arcade/RPG>
조작: <keyboard/mouse/touch>
목표: <score/survival/level completion>
그래픽: <pixel art/simple shapes/minimal flat>

게임 요소:
  - <적, 아이템, 장애물 등>
난이도: <casual/normal/hard>

필수 기능 (P1):
  1. <기능>
  ...

제약 조건:
  - <제약>
  ...

성공 기준:
  1. <testable 기준>
  ...

추천 스택: Phaser 3 + Vite + TypeScript
런타임: 브라우저 (Canvas/WebGL)
```

#### automation 요약

```
[SAMVIL] 인터뷰 요약 (Automation)
━━━━━━━━━━━━━━━━━━━━

해결할 문제: <어떤 문제>
입력 → 출력: <입력> → <출력>
실행 트리거: <수동/cron/webhook/파일변경>
연동 시스템: <API, Slack, DB 등>
에러 처리: <재시도+로깅/침묵/알림>
실행 환경: <Python/Node/Shell/CC skill>

필수 기능 (P1):
  1. <기능>
  ...

제약 조건:
  - <제약>
  ...

성공 기준:
  1. <testable 기준>
  ...

추천 스택: <python-script / node-script / shell-script / cc-skill>
```

#### mobile-app 요약

```
[SAMVIL] 인터뷰 요약 (Mobile)
━━━━━━━━━━━━━━━━━━━━

플랫폼: <iOS만/Android만/둘 다>
네이티브 기능: <카메라, GPS, 푸시, 센서, 없음>
네비게이션: <탭바/드로어/스택>
오프라인: <온라인만/기본 오프라인/완전 오프라인>

필수 기능 (P1):
  1. <기능>
  ...

제약 조건:
  - <제약>
  ...

성공 기준:
  1. <testable 기준>
  ...

추천 스택: Expo + React Native + TypeScript
런타임: hybrid (Expo web preview + native)
```

AskUserQuestion으로 확인:
```
question: "이 요약이 맞나요?"
options:
  - "좋아, 진행해" → 다음 단계
  - "수정할 부분 있어" → 수정 후 재확인
```

**빌트인 프리셋에 매칭되지 않은 커스텀 앱 유형**이거나 **매칭 실패 후 인터뷰로 구체화한 경우**:
```
question: "이 앱 유형을 프리셋으로 저장할까요? 다음에 비슷한 앱을 만들 때 빠르게 시작할 수 있어요."
header: "프리셋 저장"
options:
  - label: "저장할게요"
    description: "~/.samvil/presets/에 JSON으로 저장. 프리셋 이름을 알려주세요."
  - label: "나중에 할게요"
    description: "저장 없이 진행. 언제든 /samvil --export-preset으로 저장 가능."
```

저장 시: 인터뷰 결과에서 프리셋 JSON 포맷(`references/app-presets.md` Custom Presets 섹션 참조)으로 변환하여 `~/.samvil/presets/<name>.json`에 Write.

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
**MCP (best-effort):** Save stage transition event (auto-updates session stage):
```
mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="interview_complete", stage="seed", data='{"questions_asked":<N>,"preset_matched":"<preset>"}')
```

### 3.5. Contract Layer — post_stage (v3.2.0, ②+⑥)

> Spec: `references/contract-layer-protocol.md`.

Compute `seed_readiness` from the interview dimensions (intent_clarity /
constraint_clarity / ac_testability / lifecycle_coverage /
decision_boundary). Score each on [0,1] from the answers you recorded;
if a dimension wasn't probed, pass its current best estimate and flag
it in the summary.

```
# 1. Multi-dimensional readiness
mcp__samvil_mcp__compute_seed_readiness(
  dimensions_json='{"intent_clarity":<float>,"constraint_clarity":<float>,"ac_testability":<float>,"lifecycle_coverage":<float>,"decision_boundary":<float>}',
  samvil_tier="<from project.config.json>"
)
→ Parse total + below_floor. Attach the total to state.json.seed_readiness.

# 2. Gate check for interview → seed
mcp__samvil_mcp__gate_check(
  gate_name="interview_to_seed",
  samvil_tier="<tier>",
  metrics_json='{"seed_readiness": <total>}',
  project_root="."
)
→ On verdict=block: DO NOT chain to samvil-seed yet. Emit the
  required_action.type (split_ac / run_research / stronger_model / ask_user)
  and loop back to the relevant Phase. Reprompt until either the gate
  passes or the user accepts a residual gap.
→ On verdict=escalate: bump interview_level one step (normal → deep → max)
  and re-run the Phase that owns the failed check. Cap at two escalations
  via mcp__samvil_mcp__gate_should_force_user.
→ On verdict=pass: record a gate_verdict claim and proceed to chain.

# 3. Record the gate verdict as a claim (anti reward-hacking)
mcp__samvil_mcp__claim_post(
  project_root=".",
  claim_type="gate_verdict",
  subject="interview_to_seed",
  statement="verdict=<v>, seed_readiness=<total>",
  authority_file="state.json",
  claimed_by="agent:socratic-interviewer",
  evidence_json='["interview-summary.md"]',
  meta_json='<the full verdict dict>'
)
→ Judge role verifies in samvil-seed's pre_stage (seed-architect is
  Generator, so the Judge here is agent:user or agent:product-owner
  invoked out-of-band during approval).
```

MCP failures: log to `.samvil/mcp-health.jsonl` and proceed (INV-5).
Never fake a pass verdict — if `gate_check` couldn't run, chain as
normal but record an `evidence_posted` claim noting the skipped check.

### 4. 진행 표시
```
[SAMVIL] Stage 1/5: 인터뷰 ✓
[SAMVIL] Stage 2/5: Seed 생성 중...
```

### 5. 체인

→ See **Chain (Runtime-specific)** section below.

## 인터뷰 마인드셋 (온톨로지)

모든 인터뷰 질문에 다음 원칙을 적용한다:

1. **증상이 아닌 본질을 파고든다** — "뭘 만들지"보다 "무엇을 해결하는지"를 먼저 이해한다.
   예: "할일 앱" → "왜 기존 할일 앱이 안 맞나요? 어떤 상황에서 쓸 건가요?"
2. **숨은 가정을 드러낸다** — 사용자가 당연하다고 생각하는 것을 질문한다.
   예: "데이터는 기기 간에 공유돼야 하나요, 한 기기에서만 쓰나요?"
3. **Breadth control** — Phase 내에서 같은 기능에 대한 질문이 2회 연속이면 다른 주제로 전환한다.

## Output Format

Write `~/dev/<project>/interview-summary.md` with these sections (Korean):

### web-app (기본)

```markdown
# Interview Summary

## 타겟 유저
<target user>

## 핵심 문제
<1-sentence problem statement>

## 핵심 경험
<first 30 seconds behavior>

## 앱 유형
<preset name or "커스텀">

## 필수 기능 (P1)
1. <feature>
...

## 제외 항목
- <excluded item>
...

## 제약 조건
- <constraint>
...

## 성공 기준
1. <testable criterion>
...

## 디자인 프리셋
<preset: productivity/creative/minimal/playful>

## 추천 스택
<framework name>

## 가정 사항
- <assumption>
...

## 코딩 컨벤션 (brownfield only)
<detected conventions>
```

### game

```markdown
# Interview Summary

## 솔루션 타입
game

## 장르
<platformer/puzzle/arcade/RPG>

## 조작 방식
<keyboard/mouse/touch>

## 게임 목표
<score/survival/level completion/collection>

## 그래픽 스타일
<pixel art/simple shapes/minimal flat>

## 게임 요소
- <적, 아이템, 장애물, 점수, 타이머, 레벨 등>

## 난이도
<casual/normal/hard>

## 앱 유형
<preset name or "커스텀">

## 필수 기능 (P1)
1. <feature>
...

## 제외 항목
- <excluded item>
...

## 제약 조건
- <constraint>
...

## 성공 기준
1. <testable criterion>
...

## 추천 스택
Phaser 3 + Vite + TypeScript

## 가정 사항
- <assumption>
...
```

### automation

```markdown
# Interview Summary

## 솔루션 타입
automation

## 해결할 문제
<1-sentence problem statement>

## 입력과 출력
- 입력: <input description>
- 출력: <output description>

## 실행 트리거
<수동/cron/webhook/파일변경>

## 연동 시스템
- <API, Slack, DB, 파일, 이메일 등>

## 에러 처리 방식
<재시도+로깅/침묵/알림>

## 실행 환경
<local Python/Node.js/Shell/CC skill>

## 앱 유형
<preset name or "커스텀">

## 필수 기능 (P1)
1. <feature>
...

## 제외 항목
- <excluded item>
...

## 제약 조건
- <constraint>
...

## 성공 기준
1. <testable criterion>
...

## 추천 스택
<python-script / node-script / shell-script / cc-skill>

## 가정 사항
- <assumption>
...
```

### mobile-app

```markdown
# Interview Summary

## 솔루션 타입
mobile-app

## 플랫폼
<iOS만/Android만/둘 다>

## 네이티브 기능
- <카메라, GPS, 푸시 알림, 센서 등 또는 "없음">

## 네비게이션
<탭바/드로어/스택>

## 오프라인 지원
<온라인만/기본 오프라인/완전 오프라인>

## 앱 유형
<preset name or "커스텀">

## 필수 기능 (P1)
1. <feature>
...

## 제외 항목
- <excluded item>
...

## 제약 조건
- <constraint>
...

## 성공 기준
1. <testable criterion>
...

## 추천 스택
Expo + React Native + TypeScript

## 가정 사항
- <assumption>
...
```

Each section must be non-empty. Constraints must have >= 1 item. Success criteria must have >= 3 items.

## Anti-Patterns

1. Do NOT ask 2+ questions at once (one at a time via AskUserQuestion)
2. Do NOT skip the summary verification (even in Zero-Question mode)
3. Do NOT accept vague ACs without offering a rewrite suggestion

## Rules

1. **모든 질문은 AskUserQuestion 도구 사용** — 객관식 보기 + Other
2. **대화는 한국어로.** 기술 용어와 코드만 영어.
3. **한 번에 하나씩.** 2개 이상 질문 금지. Framework 이름(AARRR/JTBD/HEART) 사용자에게 노출 금지.
4. **preset 있으면 활용.** 질문을 줄이고 보기 품질 높임.
5. **Phase 2.5 (Unknown Unknowns)**: thorough/full/deep 기본 + 자동 감지. preset 매칭 실패 + 짧은 답변 비율 > 50%면 minimal/standard도 활성화.
6. **Phase 2.6 (Non-functional)**: thorough+ 의무 — thorough는 3Q, full/deep는 7Q 전체. (v3.1.0)
7. **Phase 2.7 (Inversion)**: thorough+ 의무 — failure paths / anti-requirements / abuse vectors. (v3.1.0)
8. **Phase 2.8 (Stakeholder/JTBD)**: full+ 의무 — primary/secondary users + JTBD + payer. (v3.1.0)
9. **Phase 2.9 (Customer Lifecycle Journey)**: standard+ 의무 — 8 stages. (v3.1.0, v3-023)
10. **Zero-Question은 요약 검토 1회 필수.** 완전 무확인 빌드는 안 됨.
11. **tier별 모호도 목표 준수.** minimal=0.10 / standard=0.05 / thorough=0.02 / full=0.01 / **deep=0.005**.
12. **Deep Mode 승격 경로** (v3.1.0): `--deeper` 플래그 / "더 깊게" / Phase 3 "아직 부족" 답변.
13. **Tech stack 기본값:** preset 추천 스택 우선. 없으면 Next.js 14 + Tailwind + shadcn/ui.
14. **Breadth rule:** 같은 기능 질문 2회 연속이면 다른 주제로 전환.
15. **커스텀 프리셋 우선.** `~/.samvil/presets/`의 프리셋이 빌트인보다 먼저 매칭. 같은 키워드면 커스텀이 우선.
16. **프리셋 자동 제안.** 매칭 실패 후 인터뷰로 구체화한 앱은 프리셋 저장을 제안.
17. **Framework reference**: 각 Phase 실행 시 `references/interview-frameworks.md` + `interview-question-bank.md` 읽기. 단 전체를 매번 로드하지 않고 solution_type + active phase 섹션만.

**TaskUpdate**: "Interview" task를 `completed`로 설정
## Chain (Runtime-specific)

### Claude Code
**NO COMPACT** — interview 컨텍스트가 seed 생성에 직접 필요하므로 compact 없이 바로 진행.
Invoke the Skill tool with skill: `samvil-seed`

### Codex CLI (future)
Read the next skill's SKILL.md and follow its instructions:
`skills/samvil-seed/SKILL.md`
