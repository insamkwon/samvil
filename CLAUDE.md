# SAMVIL — AI Vibe-Coding Harness

> "Shape it on the anvil, root it like ginseng."

## What is this?

SAMVIL is a CC Plugin that generates full web applications from a one-line prompt.

```
/samvil "할일 관리 앱"
  → Interview → Seed → [Council] → Design → Scaffold → Build → QA → [Evolve] → Retro
```

GitHub: https://github.com/insamkwon/samvil

## Skills (13개, 체인 순서)

```
samvil          ← 오케스트레이터 (Health Check → Tier 선택 → 체인 시작)
samvil-interview ← 소크라틱 인터뷰 (preset 매칭, Phase 2.5, Zero-Question)
samvil-seed      ← 인터뷰 → seed.json 변환
samvil-council   ← Council Gate A (2-round: Research → Review)
samvil-design    ← blueprint.json 생성 + Gate B
samvil-scaffold  ← Next.js 14 + shadcn/ui 프로젝트 생성
samvil-build     ← 기능 구현 (sequential or parallel)
samvil-qa        ← 3-pass 검증 (Mechanical → Functional → Quality)
samvil-deploy    ← QA PASS 후 배포 (Vercel/Railway/Coolify)
samvil-evolve    ← 시드 진화 (Wonder → Reflect → 수렴)
samvil-retro     ← 하네스 자체 개선 제안
samvil-analyze   ← 기존 프로젝트 분석 (Brownfield 모드)
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
- 37개 에이전트, 4 Tier (minimal 10 / standard 20 / thorough 30 / full 36)

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

**git push 전에 반드시 버전을 올린다.** SSOT: `.claude-plugin/plugin.json`의 `version` 필드.

### 판정 기준: "사용자가 차이를 느끼는가?"

| 레벨 | 기준 | 예시 |
|------|------|------|
| **PATCH** (0.0.+1) | 사용자가 차이를 모름 | 프롬프트 문구 개선, 오타, 버그 수정, 내부 리팩토링, 문서 수정 |
| **MINOR** (0.+1.0) | 사용자가 새로운 걸 보거나 경험함 | 새 스킬/에이전트/프리셋, 새 단계 추가 (Smoke Run 등), 새 스택 지원, 새 설정 옵션, 수동→자동 전환 |
| **MAJOR** (+1.0.0) | 기존 프로젝트가 깨질 수 있음 | seed 스키마 변경, INV 규칙 변경, config 필수 필드 변경, 체인 순서 변경 |

### 판정 테스트

- PATCH: `/samvil` 실행 시 사용자 경험이 동일
- MINOR: `/samvil` 실행 시 새로운 출력/질문/옵션이 보임
- MAJOR: 이전 버전으로 만든 프로젝트에 새 버전 실행 시 에러

### 버전업 체크리스트 (push 전 필수)

1. `hooks/validate-version-sync.sh` 실행 → 버전 일치 확인
2. `plugin.json`의 `version` 올리기 (SSOT)
3. `README.md` 첫 줄의 `` `vX.Y.Z` `` 동기화
4. `mcp/samvil_mcp/__init__.py`의 `__version__` 동기화
5. 캐시 동기화: 변경 파일을 plugin cache에 복사
6. minor/major 버전업 시 git tag: `git tag vX.Y.0 && git push --tags`

## 개발 컨벤션

### 코드 변경 후 필수

```bash
# 1. 캐시 동기화 (변경된 파일만)
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
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
4. ~~버전 불일치~~ — **v0.8.1에서 해결**. `hooks/validate-version-sync.sh`로 push 전 검증. plugin.json, __init__.py, README 동기화.

## v0.8.0 변경 내역 (v0.7.2 → v0.8.0)

1. **MAX_PARALLEL=2** — 병렬 Agent 동시 실행 제한 (build, council, design). CPU 100% 이슈 해결.
2. **모델 최적화** — Council R1: Haiku, QA: Sonnet, Evolve 2사이클+: Sonnet. Opus 사용 80% 감소.
3. **빌드 캐싱** — Worker는 lint/typecheck만, full build는 배치 완료 후 1회. 빌드 횟수 67% 감소.
4. **토큰 절약** — Agent에게 해당 feature만 전달 (전체 seed 대신). QA도 AC 관련만 전달.
5. **Agent Persona 경량화** — 5개 Agent에 Compact Mode 추가 (qa-mechanical, qa-quality, council R1 agents).
6. **qa_max_iterations** 5 → 3. Ralph Loop 과다 반복 방지.
7. **관측성** — build_stage_complete 이벤트에 agents_spawned, builds_run 메트릭 추가.

## v0.8.1 변경 내역 (retro-v0.8.0 기반 8개 개선)

1. **ISS-03 버전 동기화** — `hooks/validate-version-sync.sh` 추가. plugin.json / __init__.py / README 버전 일치 검증.
2. **ISS-01/02 MCP 의무 호출** — 11개 스킬에 18개 이벤트 타입 MCP 통합. 누락 시 경고.
3. **ISS-05 모호도 tier 파라미터** — interview_engine에 tier별 임계값 (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01).
4. **PHI-01 Playwright Smoke Run** — QA Pass 1b에서 dev server 콘솔 에러 + 빈 화면 자동 검출.
5. **PHI-03 Seed 버전 히스토리** — Evolve에서 시드 백업 + compare_seeds diff 자동 저장.
6. **PHI-04 QA ralph_max_iterations** — config 기반 반복 한도 (기본 3회).
7. **PHI-05 Build 구현률** — build_stage_complete에 implementation_rate 기록. Evolve diff 파일 저장.
8. **PHI-06 Testable AC** — Seed에 AC별 vague_words 태깅. Interview에 AC 재질문 로직.

## v0.9.0 변경 내역 (v0.8.2 → v0.9.0)

1. **QA 런타임 검증** — Pass 2를 정적 Grep에서 Playwright MCP 런타임 검증으로 전환. browser_snapshot/click/type으로 실제 상호작용 테스트. 스크린샷 증거 저장. Fallback: 정적 분석.
2. **MCP Dual-Write + 장애 추적** — 파일 먼저 기록 → MCP best-effort. 40+ MCP 호출 "필수"→"best-effort" 전환. mcp-health.jsonl 로깅. health_check 도구 추가. Retro에서 MCP 건강 리포트.
3. **실제 연동 기본화** — 인터뷰에 DB/Auth/API 질문 추가. Supabase 클라이언트 자동 설정. 스텁/하드코딩 금지. .env.example 자동 생성.
4. **배포 준비** — next.config.mjs에 output:'standalone'. QA 완료 후 Vercel/Railway/수동 배포 옵션 제시.
5. **Council 간접 토론** — Round 1 결과에서 논쟁점(consensus/debate/blind_spots) 추출 → Round 2 prompt에 주입.

## v2.0.0 변경 내역 (v1.0.0 → v2.0.0) — Universal Builder

1. **Seed Schema v2** — `solution_type` 필드 추가 (web-app/automation/game/mobile-app/dashboard). `mode` deprecated, 자동 마이그레이션. `tech_stack.framework` enum 확장 (phaser/expo/python-script/node-script). `core_experience` oneOf (screen + core_flow 패턴). `implementation` object 추가 (type/runtime/entry_point).
2. **3-Layer solution_type 감지** — 오케스트레이터 Step 2에 L1 키워드 매칭 + L2 컨텍스트 추론 + L3 인터뷰 검증 로직 추가. 감지된 타입을 인터뷰에 컨텍스트로 전달.
3. **validate_seed 확장** — MCP seed_manager가 새 프레임워크, solution_type, core_flow 패턴 검증 지원. 레거시 mode 자동 마이그레이션.
4. **Dependency Matrix 확장** — python-script, phaser-game, expo-mobile 스택 엔트리 추가.
5. **App Presets 확장** — Automation(5종), Game(3종), Mobile(3종), Dashboard(2종) 프리셋 카테고리 추가. solution_type별 매칭 규칙 추가.

## 디렉토리 구조

```
samvil/
├── .claude-plugin/plugin.json  # 플러그인 매니페스트 + 버전
├── CLAUDE.md                   # 이 파일 (프로젝트 규칙)
├── README.md                   # 사용자 가이드 (한국어)
├── skills/                     # 13개 스킬
├── agents/                     # 37개 에이전트 페르소나
├── references/                 # 참조 문서
│   ├── app-presets.md          # 10개 앱 유형 프리셋
│   ├── design-presets.md       # 4개 디자인 테마
│   ├── seed-schema.md          # seed.json 스키마
│   ├── web-recipes.md          # 웹 개발 패턴
│   ├── qa-checklist.md         # QA 기준
│   ├── tier-definitions.md     # Tier 구성 + 2-round Gate A
│   ├── council-protocol.md     # Council 토론 규칙
│   ├── evolve-protocol.md      # 시드 진화 규칙
│   ├── plugin-system.md        # Plugin hook 스펙 (Planned)
│   ├── prompt-patterns.md      # 프롬프트 패턴
│   ├── plugin-api.md           # Plugin API 레퍼런스
│   ├── tutorial.md             # 튜토리얼
│   ├── seed-schema.json        # Seed JSON 스키마
│   ├── state-schema.json       # State JSON 스키마
│   └── dependency-matrix.json  # 스택 버전 매트릭스
├── hooks/                      # 5개 자동화 스크립트 (plugin.json hooks로 적용)
│   ├── setup-mcp.sh            # SessionStart: MCP 자동 설치+등록
│   └── validate-version-sync.sh # 수동/CI: 버전 동기화 검증
├── (templates/ removed — CLI-only scaffold since v0.7.0)
├── mcp/                        # Python MCP 서버
│   ├── samvil_mcp/             # 서버 코드 (14 tools)
│   └── tests/                  # 25 tests
└── harness-feedback.log        # Self-evolution 피드백 로그
```
