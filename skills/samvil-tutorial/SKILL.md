---
name: samvil-tutorial
description: "5-min hands-on tour through a sample SAMVIL pipeline. Builds a simple todo app while explaining what each stage does. Korean. Triggers: 'samvil-tutorial', '튜토리얼'."
---

# samvil-tutorial (ultra-thin)

Adopt the **Tutorial Guide** role. Walk a new user through a complete SAMVIL pipeline using a simple sample ("할 일 앱"). **Korean throughout.** Goal: user finishes with a running app + understanding of each stage's purpose. Tutorial is non-destructive — uses `~/dev/samvil-tutorial-app/` (separate from user's real projects).

## Step 0 — 환경 확인

`AskUserQuestion(["튜토리얼 시작할까요?"])`:
- `네, 시작` → Step 1
- `먼저 환경 진단부터` → invoke `/samvil-doctor` 후 돌아오기
- `취소` → stop

## Step 1 — 디렉토리 안내

```
[튜토리얼] ~/dev/samvil-tutorial-app/ 에 샘플 앱을 만들 거예요.
실제 프로젝트와 분리되어 있어요. 끝나고 자유롭게 지우셔도 됩니다.
```

`mkdir -p ~/dev/samvil-tutorial-app && cd ~/dev/samvil-tutorial-app` (실제 실행은 사용자가 다음 명령 입력 시).

## Step 2 — 인터뷰 단계 설명

```
[튜토리얼] 1/5 — 인터뷰 단계

SAMVIL은 한 줄 아이디어로 시작하지만, 코드를 만들려면 결정해야 할 게 많아요.
인터뷰는 그 결정을 한 번에 다 묻지 않고, 5-10분 동안 1개씩 묻습니다.

각 답변 후 SAMVIL이 보여주는 것:
- ✅ Confirmed [Phase] — 이번 단계에서 확정된 것
- 잠정 AC — 이 답변에서 도출된 테스트 가능한 기준 (실시간 가시화)
- ℹ️ 자동확인 — Brownfield면 package.json 등에서 자동 추출한 fact

특별한 게이트:
- Step 0.5 Epic Claim: 처음 한 줄 합의
- Step 1 Refine Gate: 자유 텍스트 답변을 5-section으로 정리 (정보 손실 0)
- Step 4.5 Restate Gate: 시드 직전 한 줄 재진술
```

다음 명령: `/samvil "간단한 할 일 앱 만들어줘"` — Step 3 안내 (인터뷰 진행하면 그 자체가 학습).

## Step 3 — 시드 → 카운슬 → 디자인 단계

```
[튜토리얼] 2/5 — 시드 (자동)

인터뷰 끝나면 samvil-seed가 답변 + 잠정 AC를 모아 seed.json 생성.
v4.21+ Refine Gate 데이터가 있으면 LLM 추측 없이 그대로 보존됩니다.
v4.23+ evaluation_principles + exit_conditions도 자동 도출.

[튜토리얼] 3/5 — 카운슬 + 디자인 (자동, standard tier 이상)

여러 AI 에이전트가 시드를 다관점에서 토론 → blueprint.json 생성.
실패 가능성을 미리 차단 (Inversion / 비기능 요구사항 등).
```

## Step 4 — Scaffold + Build 단계

```
[튜토리얼] 4/5 — Scaffold + Build (자동)

samvil-scaffold가 Next.js / Vite / Phaser 등 프로젝트 골격 생성.
samvil-build가 AC tree leaf 단위로 코드 작성 (병렬).

빌드 실패 시 Circuit Breaker (최대 2회 재시도). 그 후 사용자에게 보고.
```

## Step 5 — QA + 종료

```
[튜토리얼] 5/5 — QA

samvil-qa가 3-pass 검증:
- Pass 1: 빌드 / typecheck / lint 통과
- Pass 2: 각 AC가 코드에 실제 존재 + evidence
- Pass 3: 품질 검토 + Reward Hacking (Stub/Mock) 검출
- v4.23+: seed.evaluation_principles로 weighted 점수
- v4.25+: --target=seed 모드로 시드 자체 검증 가능

PASS면 배포 옵션 (samvil-deploy → Vercel/Railway/Coolify).
종료 후 samvil-retro가 회고 — 다음 사용 시 자동 개선.

[튜토리얼] 완료 🎉

이제 본인 프로젝트로 시작할 준비 OK.
디렉토리 정리하시려면: rm -rf ~/dev/samvil-tutorial-app
```

`AskUserQuestion(["튜토리얼 어땠어요?"])`: `[좋아요 → /samvil "<진짜 아이디어>" / 헷갈리는 부분 있어 → 질문 입력 / 그냥 종료]`

## Anti-Patterns

1. NEVER overload — 5단계 각각 한 화면만, 다 펼치지 않음.
2. NEVER skip 잠시 멈춤 (각 단계 사이 사용자가 흡수할 시간).
3. NEVER hide failure paths — Circuit Breaker / Manual override 명시.
4. **`AskUserQuestion` 호출 포맷**: `questions=["<질문>"]` 배열만 허용; 문자열 직접 전달 시 `InputValidationError`.

## Chain

Terminal — no chain. User invokes `/samvil` 실제 프로젝트로 별도.
