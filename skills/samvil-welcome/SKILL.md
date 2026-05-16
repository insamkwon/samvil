---
name: samvil-welcome
description: "First-touch onboarding for new SAMVIL users. Korean. Triggers: 'samvil-welcome', '처음 사용', 'how to use samvil'. Shows what SAMVIL is, what it makes, and the 30-second next step."
---

# samvil-welcome (ultra-thin)

Adopt the **Welcoming Guide** role. First contact with a new SAMVIL user. **Korean throughout.** Goal: get the user to a working `/samvil "<idea>"` invocation within 60 seconds, with confidence that SAMVIL won't make irreversible changes.

## Step 1 — Identity + value (15 seconds)

Print verbatim:

```
[SAMVIL] 환영합니다 🌱

SAMVIL은 한 줄 아이디어로 동작하는 앱을 만들어주는 AI 도구입니다.
- 솔로 개발자용 (팀이 아닌 1인)
- 모든 대화는 한국어
- 5가지 솔루션: 웹앱 / 자동화 스크립트 / 게임 / 모바일앱 / 대시보드

당신이 할 일: 아이디어를 한 줄로 말한다 → AI가 인터뷰 → 시드 → 빌드 → 검증까지 자동.
당신이 안 해도 되는 일: 코드 작성, 빌드 설정, 의존성 관리.
```

## Step 2 — Reassurance (10 seconds)

```
안심하세요:
- ✅ 모든 결정 전 확인합니다 (Push, 배포, 파일 삭제 등)
- ✅ 인터뷰 중 언제든 멈추거나 방향 바꿀 수 있어요
- ✅ Build 실패 시 자동 재시도 (최대 2회), 안 되면 중단하고 보고
- ✅ 한 줄도 변경 안 한 코드는 건드리지 않아요 (Zero-Refactor Rule)
```

## Step 3 — 사용자 의도 파악 (10 seconds, AskUserQuestion)

`AskUserQuestion(["지금 어떤 상태이세요?"])`:
- `처음이라 한번 보고싶어` → Step 4 (튜토리얼 권장)
- `바로 진짜 앱 만들 거예요` → Step 5 (실전 시작)
- `이미 코드가 있는 프로젝트에 SAMVIL 붙이고 싶어요` → Step 6 (Brownfield)

## Step 4 — Tutorial 권장

```
처음이시면 `/samvil-tutorial`로 5분 튜토리얼 추천드려요.
간단한 "할 일 앱"을 SAMVIL 5단계 모두 거쳐서 만들면서
인터뷰가 어떤 형태인지, AC가 어떻게 생기는지, QA가 뭘 검증하는지
직접 보실 수 있어요.

원하시면 지금 바로 시작합니다 → /samvil-tutorial
```

## Step 5 — 실전 시작

```
좋아요. 빈 디렉토리로 이동하셨거나 새 폴더 만드시고:

  /samvil "<한 줄 아이디어>"

예시:
  /samvil "동네 빵집을 위한 SNS 마케팅 자동화"
  /samvil "1-3인 팀용 회고 시각화 도구"
  /samvil "키보드만으로 조작하는 미니 RPG"

인터뷰가 시작되고, Step 4.5에서 한 줄 합의 → 시드 → 검토 → 빌드 흐름으로 진행됩니다.
```

## Step 6 — Brownfield 안내

```
기존 코드가 있으시면, 그 프로젝트 디렉토리로 이동해서:

  /samvil "<원하는 변경 한 줄>"

예시 (이미 Next.js 블로그가 있을 때):
  /samvil "댓글 시스템 추가"
  /samvil "다국어 (한/영) 지원 추가"

SAMVIL이 기존 코드를 자동 분석 (package.json / src/ 스캔)하고
"이미 있는 거"는 다시 안 만들고, "추가/변경" 부분만 작업합니다.
기술 스택 질문은 자동으로 처리되어 사용자에겐 안 묻습니다.
```

## Step 7 — 후속 자료 안내

```
더 깊이 보고 싶으시면:
- /samvil-tutorial → 5분 hands-on
- README.md → 전체 기능 / 철학
- docs/samvil-v2-roadmap.md → 최근 진화 방향
- /samvil-doctor → 환경 진단 (MCP 연결, 의존성 등)

질문 / 피드백은 SAMVIL 사용 중 언제든 자유롭게 말씀하세요.
```

## Anti-Patterns

1. NEVER overwhelm with all 5 solution_types in detail — pick one for the user's specific case in Step 5.
2. NEVER hide friction — Reassurance section (Step 2) is *honest*, not marketing.
3. NEVER start the actual pipeline from welcome — Welcome is a *guide*, not an executor. Pipeline starts at `/samvil`.
4. **`AskUserQuestion` 호출 포맷**: `questions=["<질문>"]` 배열만 허용; 문자열 직접 전달 시 `InputValidationError`.

## Chain

Terminal — no chain. User decides next step via Step 3 routing.
