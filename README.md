# SAMVIL — AI 바이브코딩 하네스

> **한 줄 입력 → 완성된 웹앱 출력**
>
> "뿌리의 힘으로 벼려내다" (Sam=인삼 + Vil=모루)

```
/samvil "할일 관리 앱 with 칸반보드"
  → 인터뷰 → 설계 → 제작 → 검증 → 완성
  → npm run dev → localhost:3000 🎉
```

## SAMVIL이 뭐야?

Claude Code 플러그인이야. **한 줄**로 앱 아이디어를 말하면, AI가 인터뷰하고 설계하고 코드 짜고 검증까지 해서 **동작하는 Next.js 앱**을 만들어줘.

## 설치

### 1. Claude Code settings.json에 추가

`~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "samvil": {
      "source": { "repo": "insam/samvil", "source": "github" }
    }
  },
  "enabledPlugins": {
    "samvil@samvil": true
  }
}
```

### 2. Claude Code 재시작

새 세션을 열면 SAMVIL 스킬이 자동 로드됨.

### 3. (선택) MCP 서버 설치

세션 간 상태 유지, 모호도 수치 측정, 시드 진화를 원하면:

```bash
cd <samvil-plugin-path>/mcp
uv venv .venv && source .venv/bin/activate
uv pip install -e .
```

settings.json에 MCP 등록:
```json
{
  "mcpServers": {
    "samvil-mcp": {
      "command": "<samvil-path>/mcp/.venv/bin/python",
      "args": ["-m", "samvil_mcp.server"],
      "cwd": "<samvil-path>/mcp"
    }
  }
}
```

## 사용법

### 기본

```
/samvil "간단한 계산기"
```

인터뷰 질문에 답하면 나머지는 자동.

### 빠르게 (질문 없이)

```
/samvil "블로그" 그냥 만들어
```

preset 자동 적용 → 시드 검토 1회 → 바로 빌드.

### Tier 선택

시작할 때 4가지 중 선택:

| Tier | 설명 | 시간 |
|------|------|------|
| **빠르게** (minimal) | 질문 적게, 바로 빌드 | ~5분 |
| **일반** (standard) | Council 토론 + 병렬 빌드 | ~10분 |
| **꼼꼼하게** (thorough) | 깊은 인터뷰 + 디자인 리뷰 | ~15분 |
| **풀옵션** (full) | 모든 에이전트 총동원 | ~20분 |

## 파이프라인

```
인터뷰 → 시드 → [Council] → 디자인 → 스캐폴드 → 빌드 → QA → [진화] → 회고
```

| 단계 | 하는 일 |
|------|---------|
| **인터뷰** | 소크라틱 질문으로 요구사항 명확화. 앱 유형 자동 감지. |
| **시드** | 인터뷰 결과를 JSON 명세서로 변환 |
| **Council** | 3-7명 AI 에이전트가 시드 품질 토론 (standard+) |
| **디자인** | 아키텍처 결정 + 블루프린트 생성 |
| **스캐폴드** | Next.js 14 + shadcn/ui 프로젝트 생성 |
| **빌드** | 기능별 구현. 독립 기능은 병렬 빌드 (standard+) |
| **QA** | 3-pass 검증: 빌드 → 기능 → 품질 |
| **진화** | QA 피드백으로 시드 개선 (선택) |
| **회고** | 하네스 자체 개선 제안 → 쓸수록 좋아짐 |

## 주요 특징

### 🎯 10개 앱 유형 프리셋

할일, 대시보드, 블로그, 칸반, 랜딩, 쇼핑몰, 계산기, 채팅, 포트폴리오, 설문.
프리셋에 없는 앱은 자동 서치.

### 🎨 디자인 프리셋

productivity / creative / minimal / playful — shadcn/ui 테마로 기본부터 예쁘게.

### 🤖 36개 AI 에이전트

기획(9) → 디자인(6) → 개발(10) → 검증(7) → 진화(3) → 회고(1).
Tier에 따라 필요한 만큼만 활성화.

### 🔄 Self-Evolution

매 실행마다 회고 → 개선 제안 → 하네스 자체 진화. 새 앱 유형도 자동 축적.

### 🧠 Unknown Unknowns 탐지

Pre-mortem ("1주 후 삭제 이유?") + Inversion ("가장 짜증날 순간?")으로 사용자가 모르는 것까지 끌어냄.

## 기술 스택

| 구성 | 기술 |
|------|------|
| 플러그인 | Claude Code Plugin (Markdown skills + agents) |
| 생성 앱 | Next.js 14 + Tailwind CSS + shadcn/ui + TypeScript |
| 영속성 | Python MCP Server + SQLite (선택) |
| 컴포넌트 | shadcn/ui (40+ 컴포넌트) |

## 디렉토리 구조

```
samvil/
├── skills/          # 10개 스킬 (파이프라인 각 단계)
├── agents/          # 36개 에이전트 (AI 페르소나)
├── references/      # 프리셋, 프로토콜, 체크리스트
├── hooks/           # 자동화 훅
├── templates/       # Next.js 14 템플릿
└── mcp/             # Python MCP 서버 (선택)
```

## 라이선스

UNLICENSED

## 만든 사람

**insam** — "빠르게 만들어서 팔아야 생존한다"
