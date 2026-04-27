# SAMVIL — 아이디어 한 줄로 앱 만들기 `v4.8.2`

> **코딩 몰라도 괜찮아요. AI가 대신 만들어드려요.**

[![버전](https://img.shields.io/badge/버전-v4.8.2-blue)](CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude_Code-플러그인-green)](https://claude.ai/code)
[![라이선스](https://img.shields.io/badge/라이선스-UNLICENSED-lightgrey)]()

---

## 이게 뭐예요?

SAMVIL은 **Claude Code에서 쓰는 AI 앱 개발 도우미**예요.

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

### Claude Code (권장)

가장 쉽고 기능이 풍부한 방법이에요.

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

<details>
<summary>⚙️ Codex CLI / OpenCode / Gemini CLI에서 사용하기</summary>

Claude Code 외에도 MCP를 지원하는 다른 AI 도구에서 쓸 수 있어요.

**1단계 — 저장소 받기**

```bash
git clone https://github.com/insamkwon/samvil.git
cd samvil
```

**2단계 — 자동 설치 스크립트 실행**

```bash
bash scripts/setup-codex.sh          # Codex CLI
# bash scripts/setup-codex.sh opencode  # OpenCode
# bash scripts/setup-codex.sh gemini    # Gemini CLI
# bash scripts/setup-codex.sh all       # 전부 한번에
```

스크립트가 모두 자동으로 처리해요:
- MCP 서버 설치 (Python venv + samvil-mcp)
- AGENTS.md 전역 등록 (`~/.codex/AGENTS.md`) → 어느 프로젝트에서든 자동 인식
- MCP 서버를 호스트 설정 파일에 자동 등록

**3단계 — 호스트 재시작 후 사용**

```bash
cd ~/dev/내-새-앱
codex "SAMVIL로 할일 관리 앱 만들어줘"
```

문제 생기면: `bash scripts/setup-codex.sh` 다시 실행하면 돼요 (중복 없이 안전).

</details>

---

## 이렇게 작동해요

한 마디를 입력하면 6단계가 자동으로 돌아가요:

```
물어보기 → 설계 → [팀 회의] → 코드 짜기 → 테스트 → 반성
```

| 단계 | 비유 | 무슨 일이 일어나나요 |
|---|---|---|
| 🎤 **인터뷰** | 고객 미팅 | "누가 쓸 건가요?", "꼭 있어야 할 기능은?" 을 객관식으로 물어봐요 |
| 📋 **시드** | 기획서 작성 | 대화 내용을 설계서로 정리해요 |
| 🤝 **Council** | 팀 회의 | AI 여럿이 "이렇게 하면 문제 생길 것 같다"고 토론해요 |
| 🔨 **빌드** | 공사 | 독립적인 기능은 동시에 만들어요. 당신은 기다리기만 |
| ✅ **QA** | 품질 검사 | 빌드 → 화면 작동 → 기능 검증, 3단계로 확인해요 |
| 🔁 **진화** | 피드백 반영 | 더 좋아질 여지가 있으면 스스로 개선하고 다시 확인해요 |

> 전체 흐름이 자동으로 연결돼요. 중간에 뭔가 물어볼 때만 답하면 돼요.

---

## 더 잘 쓰는 법

### 얼마나 꼼꼼하게 만들지 선택하기

시작할 때 4가지 중 하나를 고를 수 있어요:

| 옵션 | 시간 | 어떤 경우에 |
|---|---|---|
| **빠르게** | ~5분 | 빠르게 프로토타입 볼 때 |
| **일반** | ~10분 | 대부분의 경우 이걸로 충분해요 |
| **꼼꼼하게** | ~15분 | 깊은 인터뷰 + 상세 설계 검토 원할 때 |
| **풀옵션** | ~20분 | 최고 품질, AI 에이전트 최대 동원 |

### 기존 앱 개선하기

이미 만들어진 앱을 더 좋게 만들고 싶을 때:

```
/samvil
→ "기존 프로젝트 개선" 선택
→ 프로젝트 경로 입력
```

AI가 코드를 분석하고, 뭘 개선할지 알려줘요.

### 특정 단계만 실행하기

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

앱 복잡도에 따라 다르지만, 대부분 5~20분이에요.
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
Claude Code 구독(월 $20)이 있어야 써요.
앱 하나 만들 때 API 비용은 보통 $0.10~$1 수준이에요.

</details>

<details>
<summary>업데이트는 어떻게 해요?</summary>

Claude Code에서 이것만 입력하면 돼요:

```
/samvil:update
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

```
/samvil:doctor
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
