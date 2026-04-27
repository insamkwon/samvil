# Interview Frameworks (v3.1.0, Sprint 1)

> Purpose: `samvil-interview` + `agents/socratic-interviewer`가 사용하는 인터뷰 프레임워크의 레퍼런스.
>
> **Triggered by**: `v3-022` (Interview Renaissance) + `v3-023` (Customer Lifecycle Journey)

---

## Why frameworks? (P3 Decision Boundary 구체화)

인터뷰는 모든 후속 단계(seed/council/design/build/qa)의 **품질 천장**이다. 천장이 낮으면 아무리 빌드/QA가 잘 돼도 사용자가 "이게 정말 내가 원한 건가?"로 회귀한다.

SAMVIL은 1인 개발자 타겟이라 **컨설턴트급 깊이**를 목표로 한다. 아래 6가지 framework를 상황에 맞게 적용해 seed를 production-ready 수준까지 끌어올린다.

---

## 1. Deep Mode (v3.1.0 신설)

기존 4 tier (minimal / standard / thorough / full) 외에 **`deep`** 신설.

| Tier | 최소 질문 수 | ambiguity 임계값 | 필수 phase |
|---|---|---|---|
| minimal | **5** | ≤ 0.10 | Core + Scope (Phase 1+2) |
| standard | **10** | ≤ 0.05 | Core + Scope + Lifecycle (8Q) |
| thorough | **20** | ≤ 0.02 | + Phase 2.5 (Unknown) + Non-functional + Inversion |
| full | **30** | ≤ 0.01 | + Stakeholder/JTBD + PATH 4 Research |
| **deep** | **40** | **≤ 0.005** | **full + Domain pack 25~30Q + premortem 심화** |

> **최소 질문 수 규칙 (v2.5.0)**: `score_ambiguity`의 `converged` 필드는 임계값 달성 + 최소 질문 수 충족 + floors 통과 3가지가 모두 충족되어야 `true`가 된다. 임계값만 달성해도 최소 질문 수 미충족이면 계속 질문한다.

**활성화 방법**:
- `/samvil:interview --deeper` 슬래시 인자
- 인터뷰 중 사용자가 "더 깊게", "더 디테일", "production 수준" 이라고 입력 시 tier 즉시 승격
- Phase 3 Convergence Check에서 사용자가 "아직 부족한 느낌" 표현 시 AskUserQuestion으로 Deep Mode 제안

**Deep Mode 원칙**:
- AC는 function 명세뿐 아니라 metric 포함 (예: "검색 결과 2초 이내 표시", "offline 상태에서 입력 가능")
- 모든 vague word는 측정 가능한 문장으로 rewrite 강제
- Assumption 섹션 자체 검증 질문 (이 가정이 틀리면?)

---

## 2. Non-functional Phase (v3.1.0 신설, thorough+ 의무)

기능이 아닌 **품질 속성** 7가지를 인터뷰한다. 새 Phase 2.6으로 삽입.

| 카테고리 | 기본 질문 | 체크 |
|---|---|---|
| **Performance** | "첫 화면 로딩 목표 시간이 있나요?" | 명시적 target or 기본값 (TTFB < 1s, LCP < 2.5s) |
| **Accessibility** | "키보드만으로 조작 가능해야 하나요?" | WCAG AA 목표 / 장애인 접근 필요 여부 |
| **Security** | "개인정보/결제 정보를 다루나요?" | 있으면 인증 + HTTPS + 감사 로그 |
| **Data policy** | "사용자 데이터를 언제 삭제하나요?" | 보관 기간 + 삭제 정책 + export 권한 |
| **Offline** | "오프라인에서도 동작해야 하나요?" | 필수면 service worker + local DB 전제 |
| **i18n** | "영어/일본어 등 다국어 지원이 필요한가요?" | 지원 언어 목록 + date/number format |
| **Error handling** | "가장 흔한 에러는 어떻게 보여줄까요?" | toast/banner/full-page + retry 정책 |

**축약 모드** (standard tier): 위 7개 중 맥락상 중요한 3개만 질문.
**전체 모드** (thorough+ tier): 7개 전부.

---

## 3. Inversion Phase (v3.1.0 강화, thorough+ 의무)

"이게 실패하는 경로는?" / "일부러 안 다룰 케이스는?"

### 3a. Failure Path Premortem
> "이 앱이 6개월 후 폐기된다면, 가장 가능성 높은 이유 3가지는?"
- multiSelect: true, 4~5 보기 + Other
- 예시 보기: "사용자가 onboarding에서 이탈" / "core feature 경쟁 앱 대비 차별화 실패" / "API cost 초과" / "유지보수 부담" / "보안 사고"

### 3b. Explicit Exclusions
> "이 앱이 **절대로** 다루지 않을 것은?"
- multiSelect: true
- seed의 `exclusions` 필드에 직접 반영

### 3c. Anti-requirements
> "사용자가 **못** 하게 막아야 할 것은?"
- 예: 동일 email 2회 가입 / 결제 없이 premium feature 접근 / admin 계정 스스로 생성

---

## 4. Stakeholder / JTBD Phase (v3.1.0 신설, full+ 의무)

"사용자"를 단수 persona로 환원하지 않는다.

### 4a. Primary / Secondary Users
- Primary: 매일 여는 사람
- Secondary: 가끔 협업/관리하는 사람 (admin, reviewer, observer)
- Non-user but affected: 결정권자, 결제자, 컴플라이언스

### 4b. JTBD (Jobs To Be Done) 포맷
각 primary user에 대해:
> **When** <situation>, **I want to** <motivation>, **so I can** <expected outcome>.

예시:
- When 새벽 3시에 버그 리포트를 받을 때, I want to 5분 안에 관련 로그를 찾고 싶다, so I can 빨리 대응할 수 있다.

### 4c. Motivation vs Means
> "사용자는 왜 **이 앱을** 쓸까요? 비슷한 대안(엑셀, 노션, 종이 등)을 안 쓰는 이유는?"
- 대안 대비 차별화 강제 surfacing

---

## 5. Customer Lifecycle Journey (v3.1.0 신설, standard+ 의무) — v3-023

사용자가 제품을 **시간축**으로 어떻게 경험하는지. 기존 인터뷰는 features/AC 중심이어서 이 시간축이 누락됨.

### 5a. 8-Stage 구조

| # | Stage | 질문 예시 | Seed 필드 |
|---|---|---|---|
| 1 | **Discovery** | "사용자가 이 앱을 어떻게 알게 되나요? (검색/추천/광고/오프라인)" | `customer_lifecycle.discovery` |
| 2 | **First Open** | "앱을 처음 열었을 때 5초 안에 뭘 보나요? empty state는?" | `.first_open` + `.empty_state` |
| 3 | **Onboarding** | "가입 강제인가요? tutorial이 필요한가요? sample data 제공하나요?" | `.onboarding` |
| 4 | **Activation (Aha moment)** | "사용자가 '아 이거 좋네'라고 느끼는 정확한 순간은?" | `.activation` |
| 5 | **Habit Formation** | "다시 오게 하는 이유가 뭔가요? push/email 정책은?" | `.retention` |
| 6 | **Completion / Boredom** | "다 쓰고 나면? (게임 클리어, 할일 끝남, content 다 봄)" | `.completion` |
| 7 | **Re-engagement** | "한 달 떠난 사용자를 어떻게 다시 불러올까요?" | `.re_engagement` |
| 8 | **Churn** | "이탈 신호를 어떻게 감지하고, 이탈 시 데이터는?" | `.churn` + `.data_retention` |

### 5b. Unknown Unknowns 처리

Stage 중 사용자가 "모른다" / "아직 생각 안 해봤다" 답변 시:
- 해당 필드를 `"TBD — research needed"` 마킹
- PATH 4 Research (Tavily)에 위임
- Research 결과를 seed에 추가 후 사용자 최종 확인

### 5c. Council/Design 연결

- Customer Lifecycle 정보는 **samvil-council**의 `ux-designer` + `ux-researcher` agent prompt에 자동 주입
- **samvil-design**의 `blueprint.json`에 `onboarding_flow`, `empty_state_design`, `re_engagement_strategy` 섹션이 생성됨
- **samvil-build**의 feature 중 onboarding/retention 관련은 lifecycle 필드 참조

### 5d. Framework 근거

- **AARRR** (Dave McClure): Acquisition → Activation → Retention → Referral → Revenue
- **HEART** (Google): Happiness, Engagement, Adoption, Retention, Task success
- **JTBD** (Clayton Christensen): 사용자의 "job"을 situation/motivation/outcome으로

위 3개 framework 중 **standard tier는 AARRR**, **thorough는 AARRR+HEART**, **full은 JTBD까지** 적용.

---

## 6. PATH 4 Research (v3.1.0 강화)

기존 PATH router의 Path 4 (`research`)는 질문 한 개에 대해 Tavily 검색하는 용도였지만, v3.1.0부터 **인터뷰 깊이 강화**에 직접 연결:

### 6a. Research → Question 변환

1. 사용자가 "모른다"/"TBD" 답변한 필드 목록 추출
2. 각 필드에 대해 Tavily 검색 (도메인 + 키워드)
3. 검색 결과에서 **decision point 3개**를 AskUserQuestion 보기로 변환
4. 사용자 선택을 seed에 반영

### 6b. 예시

사용자: "Onboarding은 어떻게 할지 모르겠어요."
→ Tavily: "SaaS onboarding best practices 2026"
→ 결과에서 3개 옵션 추출:
  - (a) Product Tour (Intro.js 스타일)
  - (b) Sample Data + Contextual Hints
  - (c) Interactive Checklist
→ 사용자 선택 → seed.customer_lifecycle.onboarding에 저장

### 6c. Fallback

Tavily 실패 시:
- references/onboarding-patterns.md, engagement-patterns.md 등 내부 reference에서 보기 추출
- 그것도 없으면 "나중에 research" 마킹 후 다음 질문

---

## 7. 적용 매트릭스 (tier × framework)

| | Core (Phase 1~2) | Lifecycle (5) | Non-func (2) | Inversion (3) | JTBD (4) | Deep Mode (1) | PATH 4 (6) |
|---|---|---|---|---|---|---|---|
| **minimal** | ✅ | - | - | - | - | - | - |
| **standard** | ✅ | ✅ (AARRR 8Q) | 3Q | - | - | - | - |
| **thorough** | ✅ | ✅ (AARRR + HEART) | 7Q | ✅ | - | - | skip 시만 |
| **full** | ✅ | ✅ (full 8Q) | 7Q | ✅ | ✅ | - | ✅ |
| **deep** | ✅ | ✅ (full + 심화) | 7Q + 측정 | ✅ + anti-req | ✅ | ✅ | ✅ + 모든 TBD 탐색 |

---

## 8. 주의 사항

- **한 번에 하나씩** — Phase 내에서 질문은 multiSelect 활용하되 서로 다른 주제는 절대 섞지 않는다 (Anti-Pattern #1).
- **Rhythm Guard 유지** — AI auto-answer streak 3회 도달 시 forced_user path 강제 (Key Rule 4 Interview/Seed에만 사용자 개입).
- **Zero-Question Mode는 Deep Mode와 상호 배타** — Zero는 preset 완전 의존, Deep은 그 반대.
- **Framework 이름을 사용자에게 노출 금지** — "AARRR", "JTBD" 같은 용어 대신 평이한 한국어로 질문 표현.

---

## 9. 관련 문서

- `references/path-routing-guide.md` — PATH 1~4 라우팅 규칙
- `references/interview-question-bank.md` — 실제 질문 pool (domain 별)
- `references/seed-schema.md` + `seed-schema.json` — customer_lifecycle 필드 스펙
- `agents/socratic-interviewer.md` — agent persona + Inversion/Stakeholder prompt
- `skills/samvil-interview/SKILL.md` — Phase 실행 순서

---

_작성: 2026-04-21 · v3.1.0 Sprint 1 (Interview Renaissance)_
