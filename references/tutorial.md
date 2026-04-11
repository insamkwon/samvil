# SAMVIL 튜토리얼

> 처음 사용하는 분들을 위한 대화형 가이드입니다.

## 시작하기 전에

SAMVIL을 사용하려면 다음이 필요합니다:

- **Claude Code** — [설치 가이드](https://docs.anthropic.com/en/docs/claude-code)
- **Node.js 18+** — [다운로드](https://nodejs.org/)
- **시간** — 첫 앱은 약 5분이면 완성됩니다

나머지 도구(Python, GitHub CLI 등)는 없어도 기본 기능이 동작하며, 필요시 자동으로 안내합니다.

---

## Step 1: 설치

Claude Code 세션에서 한 줄 입력:

```
/install-plugin insamkwon/samvil
```

설치 후 **새 세션**을 열면 SAMVIL이 자동으로 로드됩니다.

---

## Step 2: 첫 앱 만들기 (Zero-Question 모드)

가장 간단한 방법입니다. 인터뷰 없이 바로 앱이 생성됩니다:

```
/samvil "카운터 앱"
```

AI가 판단해서 "질문이 필요 없겠다"고 판단하면 Zero-Question 모드로 바로 실행됩니다.
결과는 `~/dev/counter-app/` 에 생성됩니다.

```bash
cd ~/dev/counter-app
npm run dev    # → localhost:3000 에서 확인
```

---

## Step 3: 커스텀 앱 만들기

원하는 앱을 자세히 설명할수록 더 좋은 결과가 나옵니다:

```
/samvil "나만의 포트폴리오 사이트"
```

인터뷰가 시작되면 AI가 객관식으로 질문합니다:

```
1. 이 포트폴리오의 주요 목적이 무엇인가요?
   □ 취업용
   □ 프리랜서 클라이언트 유치
   □ 개인 브랜딩
   □ Other

2. 어떤 섹션을 포함하고 싶으신가요?
   □ 프로젝트 갤러리
   □ About Me
   □ 기술 스택
   □ 연락처 폼
   □ Other
```

답변에 따라 맞춤형 앱이 생성됩니다.

---

## Step 4: Tier 선택

SAMVIL은 4가지 품질 티어를 제공합니다:

| Tier | 언제 쓰나 | 에이전트 수 | 예상 시간 |
|------|----------|-----------|---------|
| **빠르게** (minimal) | 아이디어 빠른 검증, 프로토타입 | 10명 | ~5분 |
| **일반** (standard) | 기본적인 웹 앱 | 20명 | ~10분 |
| **꼼꼼하게** (thorough) | 실제 서비스 수준 | 30명 | ~15분 |
| **풀옵션** (full) | 최고 품질, 36명 AI 총동원 | 36명 | ~20분 |

처음이라면 **빠르게** 또는 **일반**을 추천합니다.

---

## Step 5: 결과 확인

앱이 생성되면:

```bash
# 1. 프로젝트로 이동
cd ~/dev/<app-name>/

# 2. 로컬 실행
npm run dev

# 3. 브라우저에서 확인
open http://localhost:3000
```

### 생성된 파일 구조

```
~/dev/<app-name>/
├── project.seed.json       # 앱 명세 (무엇을 만들지)
├── project.config.json     # 실행 설정 (어떻게 돌릴지)
├── project.state.json      # 현재 상태 (어디까지 진행됐는지)
├── .samvil/
│   ├── events.jsonl        # 전체 이벤트 이력
│   ├── build.log           # 빌드 출력
│   └── qa-report.md        # QA 결과
└── (앱 코드)
```

---

## Step 6: 기존 프로젝트 개선하기

이미 만든 앱을 개선하고 싶을 때:

```
/samvil
```

1. "기존 프로젝트 개선" 선택
2. 프로젝트 경로 입력 (예: `~/dev/my-app`)
3. AI가 자동으로 코드를 분석합니다

분석 후 선택할 수 있는 작업:
- **기능 추가** — 새 기능 코드 작성
- **코드 품질 개선** — 리팩토링, 버그 수정
- **디자인 개선** — UI/UX 개선, shadcn/ui 적용
- **테스트/검증** — 현재 코드 품질 검증만

---

## Step 7: 단일 단계만 실행

파이프라인 전체가 아니라 원하는 단계만 실행할 수 있습니다:

```
/samvil:qa          # 기존 프로젝트 QA 검증만
/samvil:build       # 빌드만
/samvil:evolve      # 시드 진화만
/samvil:retro       # 회고만
/samvil:council     # Council 토론만
/samvil:analyze     # 코드 분석만
```

---

## FAQ

### Q: 어떤 종류의 앱을 만들 수 있나요?
A: 웹 앱이라면 거의 모든 종류를 만들 수 있습니다. 할일 관리, 블로그, 대시보드, 포트폴리오, 쇼핑몰, 채팅, 칸반보드, 설문 폼 등 10가지 앱 유형을 자동 감지하며, 목록에 없는 앱도 AI가 자동으로 분석해서 적절한 기본값을 찾습니다.

### Q: 어떤 기술 스택이 사용되나요?
A: 기본적으로 **Next.js 14 + Tailwind + shadcn/ui + TypeScript**를 사용합니다. 필요에 따라 **Vite + React** 또는 **Astro**도 선택할 수 있습니다.

### Q: 인터뷰를 건너뛸 수 있나요?
A: 네. 프롬프트 끝에 "그냥 만들어"를 붙이면 Zero-Question 모드로 실행됩니다:
```
/samvil "블로그" 그냥 만들어
```

### Q: 생성된 앱을 배포할 수 있나요?
A: 네. QA 완료 후 Vercel, Railway, 수동 배포 옵션이 자동으로 제시됩니다. Next.js 프로젝트는 `output: 'standalone'` 설정이 포함되어 있습니다.

### Q: 비용은 얼마나 드나요?
A: SAMVIL 자체는 무료입니다. Claude Code 사용량에 따라 Anthropic API 비용이 발생합니다. `빠르게` 티어를 사용하면 비용을 최소화할 수 있습니다.

### Q: 생성된 코드의 품질은 어떤가요?
A: 3단계 QA 검증(Mechanical → Functional → Quality)을 거칩니다. Playwright를 활용한 런타임 테스트도 포함되어 있어, 단순한 빌드 성공이 아닌 실제 동작까지 검증합니다.

### Q: SAMVIL을 업데이트하려면?
A: Claude Code에서 다음 명령을 실행하세요:
```
/samvil:update
```
새 버전이 나오면 자동으로 알려줍니다.

---

## 다음 단계

- [README.md](../README.md) — 전체 기능 문서
- [앱 프리셋](app-presets.md) — 10가지 앱 유형별 자동 포함 기능
- [디자인 프리셋](design-presets.md) — 4가지 테마 옵션
- [Tier 정의](tier-definitions.md) — 티어별 상세 구성
