# SAMVIL — AI Vibe-Coding Harness

> "Shape it on the anvil, root it like ginseng."

## What is this?

SAMVIL is a CC Plugin that generates full web applications from a one-line prompt.

```
/samvil "할일 관리 앱"
  → Interview → Seed → [Council] → Design → Scaffold → Build → QA → [Evolve] → Retro
```

GitHub: https://github.com/insamkwon/samvil

## Skills (11개, 체인 순서)

```
samvil          ← 오케스트레이터 (Health Check → Tier 선택 → 체인 시작)
samvil-interview ← 소크라틱 인터뷰 (preset 매칭, Phase 2.5, Zero-Question)
samvil-seed      ← 인터뷰 → seed.json 변환
samvil-council   ← Council Gate A (2-round: Research → Review)
samvil-design    ← blueprint.json 생성 + Gate B
samvil-scaffold  ← Next.js 14 + shadcn/ui 프로젝트 생성
samvil-build     ← 기능 구현 (sequential or parallel)
samvil-qa        ← 3-pass 검증 (Mechanical → Functional → Quality)
samvil-evolve    ← 시드 진화 (Wonder → Reflect → 수렴)
samvil-retro     ← 하네스 자체 개선 제안
samvil-update    ← GitHub에서 최신 버전 업데이트
```

## Architectural Invariants (절대 규칙)

1. **INV-1: File is SSOT** — seed.json + state.json을 디스크에서 읽는다. 대화 컨텍스트 의존 금지.
2. **INV-2: Build logs to files** — `npm run build > .samvil/build.log 2>&1`. 에러 시에만 읽기.
3. **INV-3: Interview to file** — interview-summary.md로 저장. seed가 파일에서 읽음.
4. **INV-4: Chain pattern** — 각 스킬이 다음 스킬을 Skill tool로 invoke. state.json으로 복구 가능.

## Agent 사용 규칙

- **현재 (adopted role)**: 스킬의 인라인 행동 규칙이 실행됨. `agents/*.md`는 참조용.
- **Council/Worker spawn 시**: `agents/*.md` 내용을 Agent tool prompt에 포함해서 전달.
- **양쪽 다 개선해야 함**: 규칙 변경 시 스킬 인라인 + agent 파일 모두 업데이트.
- 36개 에이전트, 4 Tier (minimal 10 / standard 20 / thorough 30 / full 36)

## Key Rules

1. **Seed is SSOT** — 모든 단계가 seed.json을 먼저 읽음
2. **Build must never break** — npm run build가 항상 통과해야 함
3. **Circuit Breaker** — MAX_RETRIES=2, 그 후 중단하고 사용자에게 보고
4. **User Checkpoints** — 사용자 승인 없이 다음 단계 진행 금지
5. **한국어 대화** — 모든 사용자 대화는 한국어. 코드/커밋/기술 용어만 영어.

## Target Output

Supports multiple stacks (CLI-based scaffold, no template folder):
- **Next.js 14** + Tailwind + shadcn/ui + TypeScript + App Router (default)
- **Vite + React** + Tailwind v4 + shadcn/ui + TypeScript
- **Astro** + Tailwind + React islands

## Versioning (필수)

**git push 전에 반드시 버전을 올린다.** `.claude-plugin/plugin.json`의 `version` 필드.

| 변경 유형 | 버전 | 예시 |
|----------|------|------|
| **PATCH** (0.0.+1) | 버그 수정, 오타, 프롬프트 미세 조정 | 체인 끊김 수정, Floor Rule 문구 개선 |
| **MINOR** (0.+1.0) | 기능 추가, 에이전트/프리셋/스킬 추가 | 새 앱 프리셋, 새 디자인 테마 |
| **MAJOR** (+1.0.0) | 호환 안 되는 변경, 아키텍처 변경 | seed 스키마 변경, INV 규칙 변경 |

Claude가 push 시 커밋 내용 보고 자동 판단 → plugin.json version 증가 → 함께 커밋.

현재 버전: `0.2.0`

## 개발 컨벤션

### 코드 변경 후 필수

```bash
# 1. 캐시 동기화 (변경된 파일만)
CACHE=~/.claude/plugins/cache/samvil/samvil/0.2.0
cp <변경 파일> "$CACHE/<같은 경로>/"

# 2. MCP 테스트 (MCP 변경 시)
cd mcp && source .venv/bin/activate && python -m pytest tests/ -v

# 3. 커밋 + 버전 증가 + push
```

### 스킬 수정 시

- 스킬 인라인 규칙 변경 → 해당 agent 파일도 같이 업데이트
- 체인 변경 → 전후 스킬의 invoke 경로 확인
- 새 스킬 추가 → plugin cache에 디렉토리 생성 필수

### 커밋 메시지

```
feat: 새 기능
fix: 버그 수정
improve: 기존 기능 개선 (프롬프트 품질 등)
refine: 에이전트/스킬 품질 개선
docs: 문서 변경
chore: 설정, 버전, 구조 변경
```

## 알려진 이슈

1. ~~CC Plugin hooks 미적용~~ — **v0.7.0에서 적용 완료**. PreToolUse (guard-destructive, validate-seed), PostToolUse (log-build-result).
2. **orphaned 마커** — CC가 directory source 플러그인 캐시에 `.orphaned_at` 붙임. 로드 안 되면 해당 파일 삭제.
3. **QA → Retro 체인** — 수정 완료됐지만, 실행 시 체인 끊김이 또 발생하면 스킬의 Invoke 지시 확인.

## 디렉토리 구조

```
samvil/
├── .claude-plugin/plugin.json  # 플러그인 매니페스트 + 버전
├── CLAUDE.md                   # 이 파일 (프로젝트 규칙)
├── README.md                   # 사용자 가이드 (한국어)
├── skills/                     # 11개 스킬
├── agents/                     # 36개 에이전트 페르소나
├── references/                 # 8개 참조 문서
│   ├── app-presets.md          # 10개 앱 유형 프리셋
│   ├── design-presets.md       # 4개 디자인 테마
│   ├── seed-schema.md          # seed.json 스키마
│   ├── web-recipes.md          # 웹 개발 패턴
│   ├── qa-checklist.md         # QA 기준
│   ├── tier-definitions.md     # Tier 구성 + 2-round Gate A
│   ├── council-protocol.md     # Council 토론 규칙
│   └── evolve-protocol.md      # 시드 진화 규칙
├── hooks/                      # 3개 자동화 스크립트 (현재 미적용)
├── (templates/ removed — CLI-only scaffold since v0.7.0)
├── mcp/                        # Python MCP 서버
│   ├── samvil_mcp/             # 서버 코드 (14 tools)
│   └── tests/                  # 25 tests
└── harness-feedback.log        # Self-evolution 피드백 로그
```
