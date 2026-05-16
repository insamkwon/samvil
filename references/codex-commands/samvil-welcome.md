# SAMVIL Welcome (Codex CLI)

First-touch onboarding for new SAMVIL users. Korean.

## Prerequisites

None. This skill is a guide, not a pipeline stage. Optionally run
`read_chain_marker(project_root="${PWD}")` to detect if user already
has SAMVIL state — if so, point them to `/samvil-resume` instead.

## Steps

### 1. Identity + value (15s)

Print Korean intro:
- SAMVIL = 한 줄 아이디어로 동작하는 앱 만드는 AI 도구
- 솔로 개발자 타겟
- 모든 대화 한국어
- 5 솔루션 타입: web-app / automation / game / mobile-app / dashboard

### 2. Reassurance (10s)

- 모든 결정 전 확인
- 인터뷰 중 멈추거나 방향 변경 가능
- Circuit Breaker (최대 2회 재시도)
- Zero-Refactor Rule (불필요한 코드 안 건드림)

### 3. Route via ask_user

Ask: "지금 어떤 상태이세요?" with options:
- 처음이라 한번 보고싶어 → suggest `/samvil-tutorial`
- 바로 진짜 앱 만들 거예요 → Step 5
- 이미 코드가 있는 프로젝트에 SAMVIL 붙이고 싶어요 → Step 6

### 4. Tutorial path

Recommend `/samvil-tutorial` for 5-min hands-on.

### 5. Real project path

Direct user: `mkdir -p ~/dev/<slug> && cd ~/dev/<slug> && /samvil "<한 줄 아이디어>"`.

### 6. Brownfield path

Direct user: `cd <existing-project> && /samvil "<원하는 변경 한 줄>"`.
Explain: SAMVIL이 기존 코드 자동 분석 → 추가/변경만 작업.

### 7. Pointer to more resources

- `/samvil-tutorial` for hands-on
- README.md for full feature list
- `docs/samvil-v2-roadmap.md` for recent evolution
- `/samvil-doctor` for environment diagnosis

## Anti-Patterns

1. NEVER overwhelm with all 5 solution_types in detail — pick one
   for user's specific case.
2. NEVER hide friction — Reassurance section is honest, not marketing.
3. NEVER start actual pipeline from welcome — Welcome is a guide.

## Chain

Terminal skill — **do not call** `write_chain_marker`. User decides
next step via routing.
