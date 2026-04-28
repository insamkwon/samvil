# SAMVIL — 아이디어 한 줄로 앱 만들기 `v4.10.2`

> **코딩 몰라도 괜찮아요. AI가 대신 만들어드려요.**

[![버전](https://img.shields.io/badge/버전-v4.10.0-blue)](CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude_Code-지원-green)](https://claude.ai/code)
[![Codex CLI](https://img.shields.io/badge/Codex_CLI-지원-blueviolet)](https://github.com/openai/codex)
[![라이선스](https://img.shields.io/badge/라이선스-UNLICENSED-lightgrey)]()

---

## 이게 뭐예요?

SAMVIL은 **Claude Code와 Codex CLI에서 쓰는 AI 앱 개발 도우미**예요.

"할일 관리 앱 만들어줘" 한 마디면, AI가 알아서 물어보고, 설계하고, 코드를 짜고, 테스트까지 해요.
당신은 질문에 답하고 기다리기만 하면 돼요.

비개발자도 쓸 수 있고, 개발자라면 반복 작업을 통째로 날릴 수 있어요.

---

## 이런 게 만들어져요

| 이런 말 한마디면... | 이게 나와요 | 스택 |
|---|---|---|
| "할일 관리 앱" | 웹앱 (CRUD + 데이터 저장) | Next.js + TypeScript |
| "매일 9시 날씨 슬랙 알림" | 자동화 스크립트 | Python + cron |
| "간단한 점프 게임" | 브라우저 게임 | Phaser 3 |
| "습관 트래커" | iOS/Android 앱 | Expo (React Native) |
| "팀 매출 실시간 차트" | 대시보드 | Next.js + Recharts |

> 목록에 없는 앱도 돼요. AI가 어떻게 만들지 스스로 판단해요.

---

## 시작하기

두 가지 방법 중 쓰는 AI 도구에 맞게 고르세요.

| 방법 | 대상 | 설치 |
|---|---|---|
| **Claude Code** | Anthropic Claude 사용자 | 명령어 1줄 |
| **Codex CLI** | OpenAI Codex 사용자 | 스크립트 1개 |

---

### Claude Code로 시작하기

**1단계 — 설치**

Claude Code를 열고 이것만 입력하세요:

```
/install-plugin insamkwon/samvil
```

**2단계 — 새 세션 열기**

설치가 끝나면 대화창을 새로 열어요. SAMVIL이 자동으로 로드되고, MCP 서버도 자동 설치됩니다.

**3단계 — 시작!**

```
/samvil "할일 관리 앱 만들어줘"
```

만들어진 앱은 `~/dev/앱이름/` 폴더에 생겨요.

```bash
cd ~/dev/앱이름
npm run dev    # → 브라우저에서 localhost:3000
```

---

### Codex CLI로 시작하기

**1단계 — 저장소 받기**

```bash
git clone https://github.com/insamkwon/samvil.git
cd samvil
```

**2단계 — 자동 설치 스크립트 실행**

```bash
bash scripts/setup-codex.sh
```

스크립트가 모두 자동으로 처리해요:
- MCP 서버 설치 (Python venv + samvil-mcp)
- AGENTS.md 전역 등록 (`~/.codex/AGENTS.md`) → 어느 프로젝트에서든 자동 인식
- MCP 서버를 Codex 설정 파일에 자동 등록

**3단계 — 호스트 재시작 후 시작!**

```bash
cd ~/dev/내-새-앱
codex "SAMVIL로 할일 관리 앱 만들어줘"
```

문제 생기면: `bash scripts/setup-codex.sh` 다시 실행하면 돼요 (중복 없이 안전).

<details>
<summary>⚙️ OpenCode / Gemini CLI에서도 쓸 수 있어요</summary>

동일한 스크립트로 설치해요:

```bash
bash scripts/setup-codex.sh opencode  # OpenCode
bash scripts/setup-codex.sh gemini    # Gemini CLI
bash scripts/setup-codex.sh all       # 전부 한번에
```

</details>

---

## 이렇게 작동해요

```
  "할일 관리 앱 만들어줘"
           │
           ▼
  ╭──────────────────────────────────────────────────────────────────╮
  │                                                                  │
  │  🎤 인터뷰    "왜 만드나요?" "실패한다면 이유는?" ← 보통 AI는 안 물어봐요  │
  │       │       모호함이 기준 이하가 될 때까지 계속 질문              │
  │       │       당신이 미처 생각 못 한 가정까지 파악                  │
  │       │                                                          │
  │       ▼                                                          │
  │  📋 설계      대화 내용을 구조화된 명세서로 정리                   │
  │       │                                                          │
  │       ▼                                                          │
  │  🤝 팀 회의   AI 여럿이 설계를 검토 ← 코딩 전에 문제를 잡아요     │
  │       │       "이 구조는 나중에 확장 안 돼요"                     │
  │       │       "이 흐름은 사용자가 헷갈릴 것 같아요"               │
  │       │                                                          │
  │       ▼                                                          │
  │  🔨 코드 작성  독립 기능은 동시에, 당신은 기다리기만               │
  │       │                                                          │
  │       ▼                                                          │
  │  ✅ 검증       빌드 → 화면 → 기능, 3단계 자동 확인                │
  │       │                                                          │
  │       ├── 실패 ──▶ 자동 수정 ──▶ 다시 ────────────────────────┐  │
  │       │                                                       │  │
  │       ▼                                                       │  │
  │  🔁 진화       더 좋아질 여지 있음? ──▶ YES ────────────────────┘  │
  │                                     NO  ──▶ 완성! 🎉            │
  ╰──────────────────────────────────────────────────────────────────╯
```

### 🎤 인터뷰는 이런 식이에요

보통 AI는 "무엇을 만들까요?"만 묻고 바로 코딩해요. SAMVIL은 달라요.

```
SAMVIL  ▶  이 앱을 만들려는 이유가 뭔가요?
나      ▶  친구들이랑 약속 잡기 너무 귀찮아서요

SAMVIL  ▶  지금은 어떻게 하고 계세요? 카카오톡 단톡방인가요?
나      ▶  네, 날짜 정하는 게 매번 복잡해요

SAMVIL  ▶  6개월 후 아무도 안 쓴다면, 가장 큰 이유가 뭘까요?
나      ▶  ...앱 깔기 귀찮아서요?

SAMVIL  ▶  그러면 카카오 로그인이 필수고, 링크 하나로
           앱 설치 없이 참여할 수 있어야겠네요.
           그 방향으로 설계할게요.
```

> 당신이 미처 말하지 못한 요구사항을, 질문으로 끌어냅니다.

### 🤝 팀 회의는 이런 식이에요

코딩을 시작하기 전에, AI 5명이 설계를 검토해요.

```
🔴 보안 전문가   로그인 없이 약속 수정 가능하면 누구나 삭제할 수 있어요.
                 카카오 로그인 + 작성자만 수정 가능하도록 해야 해요.

🔵 UX 전문가    3단계 날짜 선택 흐름은 모바일에서 탈락률이 높아요.
                 캘린더 뷰로 한 화면에서 끝내는 게 낫겠어요.

🟢 아키텍트     투표 결과 실시간 업데이트는 WebSocket보다 SSE가
                 이 규모엔 훨씬 단순하고 적합해요.

→ 이 문제들을 코딩 전에 잡았어요. 수정 비용 0원.
```

> 혼자 만들지만, 팀이 검토한 것처럼 튼튼하게.

### 다른 AI 도구와 뭐가 달라요?

| | 보통 AI 도구 | SAMVIL |
|---|---|---|
| **코딩 전 질문** | 0~1개 | 깊이에 따라 10~40개+ (수렴 전까지 무제한) |
| **설계 검토** | 없음 | AI 5명이 코딩 전에 토론 |
| **스텁/하드코딩** | 그냥 통과 | 자동 감지 → FAIL → 재시도 |
| **실패 대응** | 사용자가 직접 고쳐야 | 자동 수정 → 자동 재시도 |
| **완성 기준** | 빌드 성공 | 5가지 조건 동시 충족 |

---

## 더 잘 쓰는 법

### 얼마나 꼼꼼하게 만들지 선택하기

시작할 때 5가지 중 하나를 고를 수 있어요:

| 옵션 | 인터뷰 질문 | 시간 | 어떤 경우에 |
|---|---|---|---|
| **빠르게** | 5개+ | ~5분 | 빠르게 프로토타입 볼 때 |
| **일반** | 10개+ | ~10분 | 대부분의 경우 이걸로 충분해요 |
| **꼼꼼하게** | 20개+ | ~15분 | 깊은 인터뷰 + 상세 설계 검토 원할 때 |
| **풀옵션** | 30개+ | ~20분 | 최고 품질, AI 에이전트 최대 동원 |
| **극한** | 40개+ | ~25분 | 복잡한 대규모 프로젝트, 최대 깊이 인터뷰 |

> 모든 옵션에서 AI는 10가지 관점으로 모호함을 측정하고, 기준 이하가 될 때까지 질문을 멈추지 않아요.

### 기존 앱 개선하기

이미 만들어진 앱을 더 좋게 만들고 싶을 때:

```
/samvil
→ "기존 프로젝트 개선" 선택
→ 프로젝트 경로 입력
```

AI가 코드를 분석하고, 뭘 개선할지 알려줘요.

### 특정 단계만 실행하기 (Claude Code)

전체 파이프라인이 아니라 원하는 부분만:

```
/samvil:qa        ← 기존 프로젝트 검증만
/samvil:build     ← 빌드만
/samvil:evolve    ← 개선 사이클만
/samvil:retro     ← 회고만
/samvil:doctor    ← 환경 문제 진단
```

---

## 자주 묻는 질문

<details>
<summary>코딩을 전혀 몰라도 되나요?</summary>

네, 괜찮아요. AI가 어떤 앱을 만들지 묻는 질문은 전부 객관식이에요.
"어떤 기능이 필요해요?" → □ A □ B □ C □ 기타 이런 식이에요.

</details>

<details>
<summary>얼마나 걸려요?</summary>

앱 복잡도와 선택한 깊이에 따라 다르지만, 대부분 5~25분이에요.
중간에 당신이 뭔가 해야 할 일은 없어요. 기다리면 돼요.

</details>

<details>
<summary>만들어진 결과물은 어디에 있어요?</summary>

`~/dev/앱이름/` 폴더에 코드가 생겨요. 폴더에 들어가서 `npm run dev`를 실행하면
브라우저에서 바로 볼 수 있어요.

인터넷에 올리고 싶으면 (배포) Vercel/Railway 자동 배포도 지원해요 (`/samvil:deploy`).

</details>

<details>
<summary>비용이 드나요?</summary>

SAMVIL 자체는 완전 무료예요.

- **Claude Code** 구독(월 $20)이 있어야 Claude Code에서 쓸 수 있어요.
- **Codex CLI**는 OpenAI API 키가 필요해요.

앱 하나 만들 때 API 비용은 보통 $0.10~$1 수준이에요.

</details>

<details>
<summary>업데이트는 어떻게 해요?</summary>

**Claude Code:**
```
/samvil:update
```

**Codex CLI:**
```bash
cd ~/samvil   # 설치한 폴더
git pull
bash scripts/setup-codex.sh
```

새 버전이 있으면 자동으로 알려주고, 업데이트할지 물어봐요.

</details>

<details>
<summary>중간에 멈추면 어떻게 돼요?</summary>

걱정 마세요. SAMVIL은 모든 진행 상황을 파일로 저장해요.
새 세션을 열고 `/samvil`을 실행하면 "이어서 할까요?"라고 물어봐요.

</details>

<details>
<summary>뭔가 잘못 됐어요. 어떻게 진단하나요?</summary>

**Claude Code:**
```
/samvil:doctor
```

**Codex CLI:**
```bash
python3 scripts/phase2-cross-host-smoke.py
```

환경 설정, MCP 서버, 버전 등을 자동으로 진단해줘요.

</details>

---

<details>
<summary>🔧 SAMVIL 자체를 수정하려는 개발자용 (Contributors)</summary>

이 섹션은 SAMVIL 플러그인 코드를 직접 수정하려는 분들을 위한 내용이에요.

```bash
# 1. Fork / clone
git clone https://github.com/insamkwon/samvil.git
cd samvil

# 2. git hooks 활성화 (1회)
bash scripts/install-git-hooks.sh

# 3. MCP 서버 venv 셋업
cd mcp
uv venv .venv
uv pip install -e .
cd ..

# 4. 전체 검증
bash scripts/pre-commit-check.sh   # 모두 PASS 떠야 정상
```

**절대 규칙** (`CLAUDE.md` §"🛑 Development Discipline" 참조):

- 편집 중 하드코딩된 홈 경로(`/Users/<name>/`) · 시크릿 · 개인 handle 금지
- 새 MCP tool / skill / agent 변경 시 CLAUDE.md의 체크리스트 따를 것
- "완료"라 말하기 전에 `bash scripts/pre-commit-check.sh` 실행 → exit 0 확인

</details>

---

<details>
<summary>📋 변경 이력</summary>

| 버전 | 주요 변경 |
|---|---|
| **v4.9.0** | **딥 인터뷰 엔진** — 10차원 모호함 채점 + tier별 최소 질문 수 (5/10/20/30/40). 수렴 전 무제한 질문. |
| **v4.8.5** | README에 인터뷰 대화 스니펫·AI 팀 회의 스니펫·수치 비교표 추가. |
| **v4.8.4** | Claude Code + Codex CLI 동등 지원 명시. README 시작하기 섹션 양분. |
| **v4.8.3** | README 파이프라인 다이어그램에 인터뷰 깊이·팀 회의 차별점 강조. |
| **v4.8.1** | setup-codex.sh 완전 자동화 (config 없어도 자동 생성, AGENTS.md 전역 등록) |
| **v4.8.0** | **멀티호스트 온보딩** — `AGENTS.md` + `scripts/setup-codex.sh` 추가. Codex/OpenCode/Gemini 딱 2단계로 설치 완료. |
| **v4.7.0** | **Regression Suite** — evolve 사이클 간 AC 회귀 자동 감지. 4개 MCP 도구 추가. |
| **v4.6.1** | **E2E Chain Marker** — Codex/OpenCode/Gemini 호스트용 체인 마커 스키마 검증 + cross-host smoke 테스트 27개. |
| **v4.5.0** | **Gemini 어댑터 + Codex 커맨드 15종** — 멀티호스트 체인 연결. |
| **v4.4.0** | **3-Tier 헬스 분류** — healthy/degraded/critical 자동 감지 + MCP 도구. |
| **v4.3.0** | **Domain Pack 강화** — game-phaser / webapp-enterprise 도메인 추가. |
| **v3.33.x** | **Consolidation** — 사용하지 않는 모듈/도구 정리. |
| **v3.3.x** | **4-Layer Portability** — 크로스호스트 체인 기반 구축. |
| **v3.2.0** | **Contract Layer** — Claim Ledger, 8 stage Gates, Model 라우팅, 626 unit tests. |
| **v3.1.0** | **Interview Renaissance** — Deep Mode, Design stall 자동 복구, Auto-chain 기본 활성. |
| **v3.0.0** ⚠️ | **AC Tree Era (BREAKING)** — AC 트리 구조 도입. PM Interview 모드 추가. |
| **v2.0.0** | **Universal Builder** — 웹앱 외 자동화/게임/모바일/대시보드 5종 지원. |

전체 릴리즈 노트: [`CHANGELOG.md`](CHANGELOG.md)

</details>

---

<sub>Made with ♥ for solo developers · [GitHub](https://github.com/insamkwon/samvil) · [이슈 리포트](https://github.com/insamkwon/samvil/issues)</sub>
