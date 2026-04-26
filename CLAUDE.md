# SAMVIL — AI Vibe-Coding Harness

> "Shape it on the anvil, root it like ginseng."
> "뿌리의 힘으로 벼려내다" (Sam=인삼 + Vil=모루)

## What is this?

SAMVIL is a CC Plugin that generates full applications (web/automation/game/mobile/dashboard) from a one-line prompt. Built for **1인 개발자**. Prioritizes **robustness over speed** via self-correcting convergence loops.

```
/samvil "할일 관리 앱"
  → Interview → Seed → [Council] → Design → Scaffold → Build → QA → Evolve → Retro
  
Completion levels:
  L1: Build passes      (npm run build success)
  L2: QA passes         (3-pass verification + evidence)
  L3: Evolve converges  (first cycle + 5 evolve_checks passed)
  Optional: Deploy
```

GitHub: https://github.com/insamkwon/samvil
Manifesto: see `~/docs/ouroboros-absorb/MANIFESTO-v3.md`
v3.2 decisions: see `~/docs/ouroboros-absorb/HANDOFF-v3.2-DECISIONS.md`

## 🛑 ABSOLUTE RULE — Pre-Commit Enforcement

**Every commit on this repo must pass `bash scripts/pre-commit-check.sh`.**
No exceptions. This rule exists because v3.2.0 shipped with hard-coded
author-machine absolute paths that broke every other install until a
portability fix landed. That regression is forbidden from reoccurring.

The check enforces:

1. **No hard-coded home paths** (`/Users/<name>/`, `/home/<name>/`) in any
   tracked `.sh / .py / .md / .json / .yaml / .yml / .toml` file.
2. **No author-specific emails or handles** in code.
3. **No obvious secret patterns** (provider token prefixes followed by
   20+ alphanumerics, or assignments of a raw value to known auth env
   vars — the exact patterns live in `scripts/pre-commit-check.sh`).
4. **Version sync** — `plugin.json` / `mcp/samvil_mcp/__init__.py` /
   `README.md` all agree.
5. **Glossary CI green** — banned v3.1 terms in new artifacts block.
6. **Full pytest suite passes** (`mcp/.venv/bin/python -m pytest`).
7. **Skill wiring smoke passes** (`scripts/check-skill-wiring.py`).
8. **MCP server imports clean** — broken `server.py` syntax caught here,
   not at someone else's plugin install.

### How it is enforced

- `.githooks/pre-commit` calls `scripts/pre-commit-check.sh`. Enable
  once per clone: `bash scripts/install-git-hooks.sh`.
- AI operators (Claude, etc.) working in this repo **must** run
  `bash scripts/pre-commit-check.sh` before every `git commit`, even
  when the `core.hooksPath` hook is not installed (some environments
  bypass hooks). Treat a red check as a BLOCKER — fix first, commit
  never.

### What to do when a check fails

- **Hard-coded path** → replace with `${CLAUDE_PLUGIN_ROOT}`,
  `$(dirname "$0")` relative, or an env-var lookup. See
  `hooks/_contract-helpers.sh` for the canonical pattern.
- **Version mismatch** → run the steps in *"버전업 체크리스트"* (below).
- **Glossary violation** → either pick the canonical v3.2 term (see
  `references/glossary.md`) or annotate the intentional use with
  `# glossary-allow` + a one-line reason.
- **pytest failure** → fix the test before committing. Don't skip.
- **Skill wiring broken** → a contract-layer tool reference was removed
  from a skill; restore it or update the wiring map in
  `scripts/check-skill-wiring.py`.
- **MCP import fail** → syntax error in `server.py` (most common) or a
  new module's import that wasn't added to the test suite.

### Bypass policy

`--no-verify` is reserved for *true emergencies* where the repo is
actively broken and the failing check is orthogonal (e.g., CI infra is
down, not code health). Every bypass must be followed by a fixing
commit within the same session. Do not use `--no-verify` to
"commit now, fix later" — that is how v3.2.0 shipped its portability
bug in the first place.

## 🛑 ABSOLUTE RULE — Development Discipline (not just commits)

Pre-commit check is the **minimum quality bar** for any change to this
repo, not just for commit time. Every Claude operator (and human) doing
development on SAMVIL must follow the rules below at edit time and
especially before claiming any task "done".

### 0. Before claiming "done" — non-negotiable

**Always run `bash scripts/pre-commit-check.sh` before reporting a task
complete.** If it exits non-zero, you are not done. Fix first. Never
report success to the user when the check is red. This applies even
for tasks that don't end in a commit (e.g., a refactor, a doc update,
a dependency bump that leaves the tree dirty).

### 1. Edit-time forbidden patterns

While editing any file in this repo:

| Forbidden | Why | Use instead |
|-----------|-----|-------------|
| Hard-coded `/Users/<name>/` or `/home/<name>/` | Breaks every other install | `${CLAUDE_PLUGIN_ROOT}` (shell) · `Path(__file__).resolve().parents[N]` (Python) · `$(dirname "${BASH_SOURCE[0]}")` (bash source-dir) |
| Raw secret values | Leak | `.env.example` placeholders only |
| Author-specific handles in code | Personal leak | Generic text or env vars |
| `#!/bin/bash` shebang | Alpine / Docker incompat | `#!/usr/bin/env bash` |
| v3.1 glossary terms (see §Vocabulary) | Terminology drift | `references/glossary.md` canonical names |

### 2. Task-type checklists

Follow the checklist that matches what you're doing. Running the
pre-commit script at the end is always the final step.

#### Adding a new MCP tool (to `mcp/samvil_mcp/server.py`)

- [ ] New tool implemented in the appropriate `samvil_mcp/*.py` module
- [ ] `@mcp.tool()` wrapper added in `server.py` with health logging
- [ ] Unit test added in `mcp/tests/test_<module>.py`
- [ ] `scripts/check-skill-wiring.py` updated if the tool is referenced from a skill body
- [ ] `cd mcp && .venv/bin/python -m pytest tests/` passes
- [ ] `bash scripts/pre-commit-check.sh` exits 0

#### Adding / editing a pipeline stage skill

- [ ] `Boot Sequence` entry has `save_event(<stage>_start, <stage>)` for auto-claim
- [ ] Chain continuation explicit at the end (e.g., *"반드시 samvil-retro invoke"*)
- [ ] If new event_type introduced: update `_EVENT_TYPE_TO_STAGE`,
  `_STAGE_ENTRY_EVENTS` / `_STAGE_EXIT_EVENTS` / `_STAGE_FAIL_EVENTS` in `server.py`
- [ ] `scripts/check-skill-wiring.py` green
- [ ] `references/contract-layer-protocol.md` updated if wrapper shape changed
- [ ] `bash scripts/pre-commit-check.sh` exits 0

#### Adding a new agent persona

- [ ] `agents/<name>.md` created with proper frontmatter
- [ ] Registered in `mcp/samvil_mcp/model_role.DEFAULT_ROLES` (or `OUT_OF_BAND`)
- [ ] `python3 scripts/apply-role-tags.py` run to inject `model_role:` frontmatter
- [ ] `python3 scripts/render-role-inventory.py` run to refresh `ROLE-INVENTORY.md`
- [ ] `mcp/tests/test_model_role.py` still green after change
- [ ] `bash scripts/pre-commit-check.sh` exits 0

#### Adding a new `save_event` event_type in a skill body

- [ ] Update `_STAGE_ENTRY_EVENTS` / `_STAGE_EXIT_EVENTS` / `_STAGE_FAIL_EVENTS` in `server.py`
- [ ] Update `_EVENT_TYPE_TO_STAGE` mapping
- [ ] Run stdio test: `python3 scripts/test-mcp-stdio-roundtrip.py`
- [ ] `bash scripts/pre-commit-check.sh` exits 0

#### Changing seed / state / retro / claim schema

- [ ] JSON schema updated in `references/*-schema.json`
- [ ] Schema version bumped if breaking
- [ ] Migration logic added in `mcp/samvil_mcp/migrate_v3_2.py` (or a new
  migration module if jumping major)
- [ ] At least one test exercising the migration in `mcp/tests/test_migrate*.py`
- [ ] `bash scripts/pre-commit-check.sh` exits 0

#### Touching hook scripts (`hooks/*.sh`, `.githooks/*`)

- [ ] Shebang is `#!/usr/bin/env bash`
- [ ] Path resolution dynamic (`${CLAUDE_PLUGIN_ROOT}` or script-relative)
- [ ] Best-effort error handling (hooks must never halt the pipeline;
  log failures to `.samvil/mcp-health.jsonl` and exit 0)
- [ ] Manual fire test from a tmp dir (see existing hook smoke patterns)
- [ ] `bash scripts/pre-commit-check.sh` exits 0

### 3. Version bump discipline (pushes)

`pre-push` hook blocks push to `origin/main` if `plugin.json.version`
matches remote. Decide the bump level per the *Versioning* table in
this file (PATCH / MINOR / MAJOR). Bump three places: `plugin.json`,
`mcp/samvil_mcp/__init__.py`, `README.md` first line. Add a CHANGELOG
entry. `hooks/validate-version-sync.sh` verifies the three match.

### 4. When you cannot follow the discipline

If an exception is genuinely needed (e.g., external CI is down, or a
single-file emergency hotfix that deliberately bypasses one of the
checks), document it:

1. Use `--no-verify` *explicitly* (never silently).
2. Within the same session, create a second commit that either fixes
   the root cause or explains why the check is incorrect (e.g., update
   the check itself).
3. Record the exception as a retro `observation[severity: high]` with
   `category: pre-commit-bypass`. Retro may mature this into a policy
   change.

### 5. AI operator-specific guidance

If you are Claude (or another LLM) working in this repo:

- **Check scripts are cheap.** `scripts/pre-commit-check.sh` runs in ~3
  seconds with 626 tests. Running it after meaningful edits costs
  essentially nothing versus the cost of shipping a regression.
- **When the user says "done"-related things** (e.g., "커밋해줘",
  "push해", "완료해"), run the check first. Report the check result
  alongside the completion status.
- **Never silently skip.** If a check fails and you know the fix,
  apply the fix and re-run. If you can't fix, stop and report the
  specific failure to the user.
- **Before "I'm confident" type answers**, re-run the checks. The
  Final Validation in personal CLAUDE.md (`자신있어?`) in this repo
  means "pre-commit-check + full 11-dimension verification from
  the v3.2.1 release session".

## 📚 Vocabulary (v3.2)

Single source of truth: `references/glossary.md`. Enforced in CI via
`scripts/check-glossary.sh`. Key v3.2 renames:

- Whole-pipeline rigor → **`samvil_tier`** (`minimal` / `standard` /
  `thorough` / `full` / `deep`). The legacy v3.1 parameter name is tracked
  in `references/glossary.md` and accepted as a deprecated alias on MCP
  tools during v3.2; removed in v3.3.
- Model cost band → **`cost_tier`** (`frugal` / `balanced` / `frontier`).
  Introduced in Sprint 2.
- Interview intensity → **`interview_level`** (`quick` / `normal` /
  `deep` / `max` / `auto`). Default stays `normal` until Sprint 4 ships
  AUTO.
- Evolve convergence checks → **`evolve_checks`** (reserve the word
  `gate` for the 8 stage gates in §3.⑥).
- Contract ledger entry → **`claim`** with typed whitelist; see
  `mcp/samvil_mcp/claim_ledger.py`.

| Term | Canonical file | v3.3 role |
|---|---|---|
| `Codebase Manifest` | `mcp/samvil_mcp/manifest.py` | compressed codebase context |
| `Decision Log ADR` | `mcp/samvil_mcp/decision_log.py` | PM-readable decision history |
| `Orchestrator` | `mcp/samvil_mcp/orchestrator.py` | stage order, skip, proceed/block |
| `HostCapability` | `mcp/samvil_mcp/host.py` | runtime capability declaration |

## 🧬 Identity (v3)

1. **Solo Developer First** — 1인 개발자 타겟. 팀 feature는 범위 밖.
2. **Universal Builder** — 5가지 solution_type (web/automation/game/mobile/dashboard).
3. **Robustness First** — 견고성 > 속도. tier로 trade-off 조절.
4. **Converge, Then Evolve** — 3-level 완성 (Build / QA / Evolve).
5. **Self-Contained** — 단독 하네스. 외부 MCP Bridge는 future.

## 🏛️ 4-Layer Architecture (v3.3)

v3.3 separates SAMVIL into four layers so the same project can run across
Claude Code, Codex CLI, OpenCode, or a generic host.

| Layer | Owns | v3.3 files |
|---|---|---|
| Skill | user-facing workflow, summaries, approval checkpoints | `skills/*/SKILL.md` |
| MCP | deterministic operations and contracts | `mcp/samvil_mcp/*.py` |
| Host Adapter | runtime differences and chain strategy | `host.py`, `.samvil/next-skill.json` |
| SSOT | durable project facts and audit files | `.samvil/manifest.json`, `.samvil/decisions/*.md`, `.samvil/claims.jsonl` |

Rules:
- Skills ask MCP for state instead of inferring stage flow from prompt text.
- Host-specific chaining goes through `HostCapability`; do not assume the
  Claude Code Skill tool exists.
- `.samvil/*` files remain the recovery boundary when MCP or host features
  degrade.

## ⚖️ 10 Core Principles (v3)

| # | 원칙 | 의미 |
|---|------|------|
| **P1** | Evidence-based Assertions | 모든 PASS는 file:line 증거 필수. 없으면 FAIL. |
| **P2** | Description vs Prescription | 사실(manifest)은 AI, 결정(목표/AC)은 사용자. |
| **P3** | Decision Boundary | "충분함"을 숫자로 명시. 감으로 결정 금지. |
| **P4** | Breadth First, Depth Second | tracks 리스트로 인터뷰 편향 방지. |
| **P5** | Regression Intolerance | 이전 세대 대비 퇴화 감지 시 수렴 거부. |
| **P6** | Fail-Fast, Learn Later | 빠른 포기 + 다음 cycle의 Wonder 재료로. |
| **P7** | Explicit over Implicit | 아이콘으로 AI 행동 표시 (ℹ️ 💬 🔍). |
| **P8** | Graceful Degradation | 일부 실패해도 전체 파이프라인 계속. |
| **P9** | Circuit of Self-Correction | 실패→학습→재시도 루프 내재화. |
| **P10** | Reversibility Awareness | Reversible은 빠르게, Irreversible은 사용자 확인. |

## Skills (15개, 체인 순서)

```
samvil           ← 오케스트레이터 (Health Check → Tier 선택 → 체인 시작)
samvil-interview ← 엔지니어링 중심 소크라틱 인터뷰 (preset 매칭, Phase 2.5, Zero-Question)
samvil-pm-interview ← [v3.0.0] PM 중심 인터뷰 (vision → epics → tasks → ACs)
samvil-seed      ← 인터뷰 → seed.json 변환
samvil-council   ← Council Gate A (2-round: Research → Review)
samvil-design    ← blueprint.json 생성 + Gate B
samvil-scaffold  ← Next.js 14 + shadcn/ui 프로젝트 생성
samvil-build     ← [v3.0.0] AC Tree leaf-level 기능 구현
samvil-qa        ← [v3.0.0] Tree aggregation 기반 3-pass 검증
samvil-deploy    ← QA PASS 후 배포 (Vercel/Railway/Coolify)
samvil-evolve    ← 시드 진화 (Wonder → Reflect → 수렴)
samvil-retro     ← 하네스 자체 개선 제안
samvil-analyze   ← 기존 프로젝트 분석 (Brownfield 모드)
samvil-doctor    ← 환경/플러그인 진단
samvil-update    ← [v3.0.0] GitHub 업데이트 + --migrate 지원
```

## Architectural Invariants (절대 규칙)

1. **INV-1: File is SSOT** — seed.json + state.json + handoff.md + qa-results.json + events.jsonl 5개 파일이 truth. 대화 컨텍스트 의존 금지.
2. **INV-2: Build logs to files** — `npm run build > .samvil/build.log 2>&1`. 에러 시에만 읽기.
3. **INV-3: Interview to file** — interview-summary.md로 저장. seed가 파일에서 읽음.
4. **INV-4: Chain pattern** — 각 스킬이 다음 스킬을 Skill tool로 invoke. state.json으로 복구 가능.
5. **INV-5: Graceful Degradation** — 일부 컴포넌트 실패해도 전체 파이프라인 계속. MCP 실패 시 파일 fallback. (v2.2.0 승격, P8 철학 반영)

## Agent 사용 규칙

- **현재 (adopted role)**: 스킬의 인라인 행동 규칙이 실행됨. `agents/*.md`는 참조용.
- **Council/Worker spawn 시**: `agents/*.md` 내용을 Agent tool prompt에 포함해서 전달.
- **양쪽 다 개선해야 함**: 규칙 변경 시 스킬 인라인 + agent 파일 모두 업데이트.
- 37개 에이전트, 4 Tier (minimal 10 / standard 20 / thorough 30 / full 36)

## Key Rules

1. **Seed is SSOT** — 모든 단계가 seed.json을 먼저 읽음
2. **Build must never break** — npm run build가 항상 통과해야 함
3. **Circuit Breaker** — MAX_RETRIES=2, 그 후 중단하고 사용자에게 보고
4. **User Checkpoints** — 인터뷰/시드 단계는 checkpoint 필수. 그 이후는 실패 시에만 개입 (자가복구 지향).
5. **한국어 대화** — 모든 사용자 대화는 한국어. 코드/커밋/기술 용어만 영어.
6. **Evidence Mandatory (v3)** — 모든 PASS 판정에 file:line 증거 필수 (P1).
7. **Description vs Prescription (v3)** — 기술 스택은 AI 자동 확인, 비즈니스 결정은 사용자 (P2, N3).
8. **Stub = FAIL (v3)** — Stub/Mock/하드코딩 자동 탐지 시 FAIL 처리 (Reward Hacking Detection, E1).

## Decision Boundaries (수치 기준)

| 단계 | 종료 조건 |
|------|----------|
| Interview | `ambiguity_score ≤ tier 임계값` (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01) |
| Build | `npm run build` 성공 + typecheck 통과 |
| QA | 3-pass 모두 PASS + evidence 존재 |
| Evolve 수렴 | similarity ≥ 0.95 + regression 0 + 5 evolve_checks 통과 |
| Circuit Breaker | 동일 실패 2회 연속 |
| Stall Detection | 5분간 이벤트 없음 |
| Rhythm Guard | AI 자동답변 3회 연속 → 다음은 강제 사용자 개입 |

## Error Philosophy (K3)

| 유형 | 취급 | 예시 |
|------|------|------|
| **Mechanical 실패** | 버그 (즉시 수정) | build 실패, lint, typecheck |
| **Semantic 실패** | 정보 (Wonder 입력) | AC FAIL, Reward Hacking, 의도 불일치 |

## Anti-Patterns (하지 말 것)

1. **Stub/Mock/하드코딩으로 AC 통과** → Reward Hacking이 자동 FAIL
2. **Evidence 없는 PASS 선언** → P1 위반, 자동 FAIL
3. **Blind convergence** → 5 evolve_checks 중 하나라도 실패 시 수렴 거부 (P5)
4. **사용자 대신 결정** → P2 위반. Rhythm Guard로 방어.
5. **요청 범위 외 코드 수정** → Zero-Refactor Rule (동호님 개인 CLAUDE.md 상속)
6. **Irreversible action without confirmation** → Deploy/push는 사용자 승인 필수 (P10)

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

### MINOR-bump cap relaxation (v3.3+)

The MINOR position (second number) is no longer auto-promoted to MAJOR when it
reaches 10. Versions like 3.10.0, 3.42.0, and 3.99.0 are valid and indicate
cumulative MINOR work without breaking changes. MAJOR bumps are reserved for
explicit breaking-change releases per the table above.

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

## v3.3.0 변경 내역 (v3.2.3 → v3.3.0) — 4-Layer Portability Foundation

v3.3 Phase 1 구현 완료. 758 unit tests · 121 MCP tools · 4-layer integration
smoke PASS · pre-commit-check PASS.

### Week 1 — Codebase Manifest (Layer 4)
- `mcp/samvil_mcp/manifest.py` — module discovery, public API extraction,
  convention detection, atomic `.samvil/manifest.json`, context renderer.
- MCP tools: `build_and_persist_manifest`, `read_manifest`,
  `render_manifest_context`, `refresh_manifest`.
- Reference: `references/samvil-ssot-schema.md` (Layer 4a — Codebase Manifest).

### Week 2 — Decision Log / ADR (Layer 4)
- `mcp/samvil_mcp/decision_log.py` — ADR markdown frontmatter, atomic I/O,
  supersession chains, reference lookup, council decision promotion.
- MCP tools: `write_decision_adr`, `read_decision_adr`,
  `list_decision_adrs`, `supersede_decision_adr`,
  `find_decision_adrs_referencing`, `promote_council_decision`.
- Reference: `references/samvil-ssot-schema.md` (Layer 4b — Decision Log / ADR).

### Week 3 — Orchestrator (Layer 2)
- `mcp/samvil_mcp/orchestrator.py` — canonical stage order, tier skip policy,
  event-derived proceed/block state, `complete_stage` planning.
- MCP tools: `get_next_stage`, `should_skip_stage`, `stage_can_proceed`,
  `complete_stage`, `get_orchestration_state`.
- Reference: `references/samvil-ssot-schema.md` (Layer 2 — Orchestrator state).

### Week 4 — HostCapability + ultra-thin seed PoC (Layer 3 + Layer 1)
- `mcp/samvil_mcp/host.py` — Claude Code / Codex CLI / OpenCode / generic
  capability resolver and chain strategy.
- `skills/samvil-seed/SKILL.md` reduced to 87-line MCP-driven PoC;
  `SKILL.legacy.md` preserves the old 512-line body.
- Reference: `references/samvil-ssot-schema.md` (Layer 3 — Host capability).

## v3.2.0 변경 내역 (v3.1.0 → v3.2.0) — Contract Layer

v3.2 흡수 13개 항목 모두 구현. 626 unit tests · 104 MCP tools · Sprint별 exit-gate PASS.

### Sprint 1 — Foundation primitives (① ⑥ ⑪)
- `mcp/samvil_mcp/claim_ledger.py` (18 tests) — `.samvil/claims.jsonl` SSOT. 10개 type 화이트리스트 + Generator ≠ Judge + file:line 해상도.
- `mcp/samvil_mcp/gates.py` (27 tests) + `references/gate_config.yaml` — 8 gates, `samvil_tier`별 기준치, 3개 escalation check.
- `references/glossary.md` + `scripts/check-glossary.sh` (CI) — `agent_tier → samvil_tier` rename. 5 gates → 5 evolve_checks.
- Observability v1: `scripts/view-claims.py`, `view-gates.py`, `samvil-status.py` (sprint + gates + budget pane).
- `references/gate-vs-degradation.md` — ⑥ vs P8 경계 결정표.
- `scripts/seed-experiments.py` + `.samvil/experiments.jsonl` (21 experiments 등록).
- `references/calibration-dogfood.md` runbook + `scripts/check-exit-gate-sprint1.py`.

### Sprint 2 — Model routing (④, Lite 흡수)
- `mcp/samvil_mcp/routing.py` (30 tests) — `cost_tier` (frugal/balanced/frontier), `ModelProfile`, `route_task`, escalation/downgrade.
- `references/model_profiles.defaults.yaml` — Opus/Sonnet/Haiku/Codex/gpt-4o-mini 기본 프로필.
- Exit-gate 시나리오 "build on Opus, QA on Codex" + 4/4 PASS.
- `references/model-routing-guide.md` + `model-profiles-schema.md` + `troubleshooting-codex.md`.

### Sprint 3 — Role (⑤) + AC schema (③)
- `mcp/samvil_mcp/model_role.py` (18 tests) + 50개 `agents/*.md`에 `model_role:` frontmatter.
- `agents/ROLE-INVENTORY.md` 자동 생성 (`scripts/render-role-inventory.py`).
- `mcp/samvil_mcp/ac_leaf_schema.py` (22 tests) — 2 user + 12 AI-inferred 필드, testability sniff, `compute_parallel_safety`.

### Sprint 4 — Interview full (②) + narrate
- `mcp/samvil_mcp/interview_v3_2.py` (29 tests) — 6 technique, `interview_level` (quick/normal/deep/max/auto), PAL adaptive selection.
- `mcp/samvil_mcp/narrate.py` (10 tests) + `scripts/samvil-narrate.py` — Compressor role 기반 1-page narrative.
- `references/interview-levels.md`.

### Sprint 5a — Jurisdiction (⑦) + Retro (⑧)
- `mcp/samvil_mcp/jurisdiction.py` (16 tests) — AI/External/User 3단계, 강성 우선, irreversibility 감지.
- `mcp/samvil_mcp/retro_v3_2.py` (10 tests) — 4-stage schema + `promote/reject/supersession`.
- `references/jurisdiction-boundary-cases.md`.

### Sprint 5b — Stagnation (⑩) + Consensus (⑨)
- `mcp/samvil_mcp/stagnation_v3_2.py` + `consensus_v3_2.py` (17 tests) — 4 signal detection + dispute resolver.
- `references/council-retirement-migration.md` — v3.2 opt-in → v3.3 removal 전환 계획.

### Sprint 6 — Release (⑫ ⑬)
- `mcp/samvil_mcp/migrate_v3_2.py` (6 tests) — backup + idempotent + dry-run + rollback snapshot.
- `mcp/samvil_mcp/performance_budget.py` (8 tests) — per-tier 한도, 80% warn, 150% hard-stop, consensus 면제.
- `references/performance_budget.defaults.yaml` + `migration-v3.1-to-v3.2.md`.

### Non-negotiables preserved
- INV-1~5 전부 유지. Claim ledger는 INV-1에 **첫 번째 SSOT 파일**로 추가됨 (view files는 재생성됨).
- `zero-refactor rule` — 포팅 대상 외 코드 변경 없음.

## v3.1.0 변경 내역 (v3.0.0 → v3.1.0) — Interview Renaissance + Stability + Universal Builder

27 dogfood backlog items (v3-001~027) 중 25건 구현. dogfood 실행이 필요한 5건(v3-001~004, v3-007)은 v3.1.1로 연기.

### Sprint 0 — Backlog Schema (1건)
- `v3-021` samvil-retro가 suggestions_v2 dict schema로 저장 + `scripts/view-retro.py` viewer + `test_retro_schema.py` 5 tests

### Sprint 1 — Interview Renaissance (2건, 가장 큰 leverage)
- `v3-022` Deep Mode tier + Phase 2.6 Non-functional + 2.7 Inversion + 2.8 Stakeholder/JTBD
- `v3-023` Phase 2.9 Customer Lifecycle Journey 8 stages (standard+ 의무)
- 신규 references: `interview-frameworks.md`, `interview-question-bank.md` (110개 Q)
- seed-schema: customer_lifecycle, non_functional, inversion, stakeholders

### Sprint 2 — Stability CRITICAL (3건)
- `v3-016` Design stall 복구 — heartbeat_state + is_state_stalled + reawake + 4 MCP tools
- `v3-017` 모델 호환성 — Claude/GLM/GPT 모두 작동. `references/model-specific-prompts.md`
- `v3-019` auto_chain 기본 활성화 + state-schema.auto_chain field

### Sprint 3 — Game + Automation (4건)
- `v3-013/014/015` game-interviewer 확장 (lifecycle + mobile spec + art)
- `agents/game-art-architect.md` 신규, samvil-design에서 spawn
- seed-schema: game_config, game_architecture, art_design
- `v3-025` automation scaffold external API model ID 외부화 (.env.example)

### Sprint 5 — Polish (7건)
- `v3-005/006` samvil-update cache rename + plugin.json fallback
- `v3-008` reflect-proposer AC Tree Mutation Rules inline
- `v3-009` state-schema stage enum sync test (council/design)
- `v3-018` cost-aware mode (`references/cost-aware-mode.md`)
- `v3-020` Sonnet 6x 측정값 README + samvil-doctor
- `v3-024` Council 한글화 (`references/council-korean-style.md` + 6 agents)

### Sprint 6 — Long Tail (3건)
- `v3-010` SAMPLE_RATE atomic counter (threading.Lock)
- `v3-011` suggest_ac_split MCP tool + `ac_split.py` heuristic
- `v3-012` SessionStart hook tool coverage check

### Sprint 4 — Dogfood preparation (2/7건 코드 작업)
- `v3-026` samvil-build Phase A.6 Scaffold Sanity Check
- `v3-027` samvil-qa Pass 1b automation API connectivity check
- 5건 (v3-001~004, v3-007)은 실 dogfood 필요 → v3.1.1

### Tests
- 375 → 406 (+31)

### Migration
- Non-breaking. v3.0.0 seed 그대로 로드. 신규 optional fields는 새 인터뷰 통과 시 populate.

---

## v3.0.0 변경 내역 (v2.7.0 → v3.0.0) — 🌳 AC Tree Era (BREAKING)

### ⚠️ Breaking changes

- `seed.features[].acceptance_criteria`가 tree 구조 `{id, description, children[], status, evidence[]}`로 변경
- `seed.schema_version` 필수 (기본 "3.0"). v2.x seed는 samvil-build 진입 시 자동 migrate (backup: `project.v2.backup.json`)
- Build/QA가 leaf 단위 순회 — flat v2 AC는 single-leaf branches로 migration됨

### T1 — AC Tree Build/QA (4 commits)

- `ac_tree.py`: `is_branch_complete`, `all_done`, `next_buildable_leaves`, `tree_progress` 헬퍼 추가
- `migrations.py`: `migrate_seed_v2_to_v3` + `migrate_with_backup` (idempotent, `.v2.backup.json` 자동)
- MCP tool 5개 신규: `next_buildable_leaves`, `tree_progress`, `update_leaf_status`, `migrate_seed`, `migrate_seed_file`
- `samvil-build`: Phase B-Tree가 기존 feature-batch dispatch 대체 (legacy Phase B는 참고용으로 유지)
- `samvil-qa`: Pass 2가 leaves 순회 + `aggregate_status`로 branch 집계 + tree 렌더링
- `samvil-update`: Step 7 v2 seed 감지 + `--migrate` 플래그

### T2 — LLM Dependency Planning

- `dependency_analyzer.py`: Kahn's toposort + cycle detection + serial_only 처리
- `analyze_ac_dependencies` MCP tool
- `samvil-build` Phase B-Tree Step 2.5: tier ≥ thorough & ≥5 ACs일 때 plan 적용

### T3 — Shared Rate Budget

- `rate_budget.py`: 파일 기반 cooperative slot tracker (`.samvil/rate-budget.jsonl`)
- MCP tool 4개: `rate_budget_acquire/release/stats/reset`

### T4 — PM Interview Mode

- 신규 스킬 `samvil-pm-interview` (vision → users → metrics → epics → tasks → ACs)
- `pm_seed.py`: `validate_pm_seed` + `pm_seed_to_eng_seed` (epics/tasks → features[])
- `references/pm-seed-schema.md` 작성
- MCP tool 2개: `validate_pm_seed`, `pm_seed_to_eng_seed`

### Validation 수정 (v3 호환)

- `seed_manager.validate_seed`: `schema_version`가 "3."로 시작하면 root-level `acceptance_criteria` 미필수. 대신 `features[i].acceptance_criteria`의 leaf 개수로 최소 1개 AC 보장 체크.

### 테스트

- 254 → 315 (+61): 24 tree+migration, 14 dependency, 8 rate, 10 PM, 5 v3 seed validation

### Migration

- `/samvil:update --migrate`로 CWD 프로젝트 seed 변환 (standalone path)
- `references/migration-v2-to-v3.md` 문서 참조

---

## v2.2.0 변경 내역 (v2.1.0 → v2.2.0) — Manifesto v3 (Philosophy)

1. **Identity 명문화** — 5가지 정체성 (Solo Developer / Universal Builder / Robustness First / Converge-then-Evolve / Self-Contained).
2. **10대 원칙 도입** — P1~P10 (Evidence / Description vs Prescription / Decision Boundary / Breadth First / Regression Intolerance / Fail-Fast+Learn / Explicit / Graceful Degradation / Self-Correction / Reversibility).
3. **INV-5 Graceful Degradation 승격** — 기존 INV-7(내부)을 INV-5로 정식 승격. 전 단계 적용.
4. **3-Level Completion 정의** — L1 Build / L2 QA / L3 Evolve 수렴. Deploy는 optional.
5. **Decision Boundaries 수치화** — 각 단계 종료 조건 명시 (ambiguity, similarity, timeout 등).
6. **Error Philosophy (K3)** — Mechanical=버그, Semantic=정보 (Wonder 입력).
7. **Anti-Patterns 명시** — Stub=FAIL, Evidence 없는 PASS=FAIL, Blind convergence 금지 등.
8. **흡수 계획** — Ouroboros v0.28.7 참고, 15개 기능 순차 흡수 (ROADMAP.md 참조).

**참고 문서**: `~/docs/ouroboros-absorb/` (MANIFESTO-v3.md, IMPLEMENTATION-PLAN.md, ROADMAP.md, 15개 feature 문서)

**주의**: v2.2.0은 문서 개정만. 코드 변경은 v2.3.0(Sprint 1 Quick Wins)부터 시작.

## v2.1.0 변경 내역 (v2.0.0 → v2.1.0) — Handoff & UX Improvements

1. **Handoff 패턴** — 각 스킬 완료 시 `.samvil/handoff.md`에 누적 append. context limit 도달 시 새 세션에서 `/samvil`로 handoff.md 읽고 복구. 7스킬 16포인트. Write tool 금지, Bash `cat >>` 또는 Edit로 append.
2. **시드 요약 포맷** — Step 4에서 플레이스홀더 대신 실제 값으로 구조적 요약. solution_type별 분기 (screen 패턴: web-app/dashboard/mobile, flow 패턴: automation/game).
3. **Council 결과 포맷** — 섹션별 판결(N/M APPROVE) + 에이전트별 2-3줄 근거 + 반대 의견 상세화.
4. **Retro 개선** — suggestion에 ISS-ID + severity(CRITICAL/HIGH/MEDIUM/LOW) + target_file + reason + expected_impact 구조화. feedback.log JSON도 구조화.
5. **구버전 캐시 자동 삭제** — samvil-update Step 5 추가. `$LATEST` empty check(`-z`) + 디렉토리 존재 check(`-d`) 이중 가드. 삭제 전후 용량 로깅.
6. **Resume 강화** — 오케스트레이터가 state.json + handoff.md 읽어서 이전 세션 결정 사항 요약 제시.

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
├── skills/                     # 15개 스킬
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
