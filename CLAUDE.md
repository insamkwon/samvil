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

Release history: see `CHANGELOG.md` (v3.19+) and
`docs/CHANGELOG-legacy.md` (v0.x ~ v3.3.x archive).

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
  seconds with the full test suite. Running it after meaningful edits
  costs essentially nothing versus the cost of shipping a regression.
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

1. **INV-1: File is SSOT** — seed.json + state.json + handoff.md + qa-results.json + events.jsonl 5개 파일이 truth. 대화 컨텍스트 의존 금지. (Claim ledger `.samvil/claims.jsonl`은 v3.2에서 첫 번째 SSOT 파일로 추가됨.)
2. **INV-2: Build logs to files** — `npm run build > .samvil/build.log 2>&1`. 에러 시에만 읽기.
3. **INV-3: Interview to file** — interview-summary.md로 저장. seed가 파일에서 읽음.
4. **INV-4: Chain pattern** — 각 스킬이 다음 스킬을 Skill tool로 invoke. state.json으로 복구 가능. (v3.3부터는 `HostCapability` 통해 host-agnostic chain.)
5. **INV-5: Graceful Degradation** — 일부 컴포넌트 실패해도 전체 파이프라인 계속. MCP 실패 시 파일 fallback. (P8 철학 반영.)

## Agent 사용 규칙

- **현재 (adopted role)**: 스킬의 인라인 행동 규칙이 실행됨. `agents/*.md`는 참조용.
- **Council/Worker spawn 시**: `agents/*.md` 내용을 Agent tool prompt에 포함해서 전달.
- **양쪽 다 개선해야 함**: 규칙 변경 시 스킬 인라인 + agent 파일 모두 업데이트.
- 37개 에이전트, 4 Tier (minimal 10 / standard 20 / thorough 30 / full 36).

## Key Rules

1. **Seed is SSOT** — 모든 단계가 seed.json을 먼저 읽음.
2. **Build must never break** — npm run build가 항상 통과해야 함.
3. **Circuit Breaker** — MAX_RETRIES=2, 그 후 중단하고 사용자에게 보고.
4. **User Checkpoints** — 인터뷰/시드 단계는 checkpoint 필수. 그 이후는 실패 시에만 개입 (자가복구 지향).
5. **한국어 대화** — 모든 사용자 대화는 한국어. 코드/커밋/기술 용어만 영어.
6. **Evidence Mandatory (v3)** — 모든 PASS 판정에 file:line 증거 필수 (P1).
7. **Description vs Prescription (v3)** — 기술 스택은 AI 자동 확인, 비즈니스 결정은 사용자 (P2, N3).
8. **Stub = FAIL (v3)** — Stub/Mock/하드코딩 자동 탐지 시 FAIL 처리 (Reward Hacking Detection, E1).

## Decision Boundaries (수치 기준)

> 전체 임계값과 산출 근거는 **`references/decision-boundaries.md`**가 SSOT.
> 아래는 빠른 참조용 요약이며, 숫자가 다르면 references 파일이 옳다.

| 단계 | 종료 조건 |
|------|----------|
| Interview | `ambiguity_score ≤ samvil_tier 임계값` (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01 / deep 0.01) |
| Build | `npm run build` 성공 + typecheck 통과 |
| QA | 3-pass 모두 PASS + 모든 leaf에 file:line evidence |
| Evolve 수렴 | `similarity ≥ 0.95` + `regression == 0` + 5 evolve_checks 통과 |
| Circuit Breaker | 동일-원인 실패 2회 연속 |
| Stall Detection | 5분간 events.jsonl 변화 없음 |
| Rhythm Guard | AI 자동답변 3회 연속 → 다음은 강제 사용자 개입 |

## Error Philosophy (K3)

| 유형 | 취급 | 예시 |
|------|------|------|
| **Mechanical 실패** | 버그 (즉시 수정) | build 실패, lint, typecheck |
| **Semantic 실패** | 정보 (Wonder 입력) | AC FAIL, Reward Hacking, 의도 불일치 |

## Anti-Patterns (하지 말 것)

1. **Stub/Mock/하드코딩으로 AC 통과** → Reward Hacking이 자동 FAIL.
2. **Evidence 없는 PASS 선언** → P1 위반, 자동 FAIL.
3. **Blind convergence** → 5 evolve_checks 중 하나라도 실패 시 수렴 거부 (P5).
4. **사용자 대신 결정** → P2 위반. Rhythm Guard로 방어.
5. **요청 범위 외 코드 수정** → Zero-Refactor Rule (개인 CLAUDE.md 상속).
6. **Irreversible action without confirmation** → Deploy/push는 사용자 승인 필수 (P10).

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

- PATCH: `/samvil` 실행 시 사용자 경험이 동일.
- MINOR: `/samvil` 실행 시 새로운 출력/질문/옵션이 보임.
- MAJOR: 이전 버전으로 만든 프로젝트에 새 버전 실행 시 에러.

### 버전업 체크리스트 (push 전 필수)

1. `hooks/validate-version-sync.sh` 실행 → 버전 일치 확인.
2. `plugin.json`의 `version` 올리기 (SSOT).
3. `README.md` 첫 줄의 `` `vX.Y.Z` `` 동기화.
4. `mcp/samvil_mcp/__init__.py`의 `__version__` 동기화.
5. 캐시 동기화: 변경 파일을 plugin cache에 복사.
6. minor/major 버전업 시 git tag: `git tag vX.Y.0 && git push --tags`.

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

- 스킬 인라인 규칙 변경 → 해당 agent 파일도 같이 업데이트.
- 체인 변경 → 전후 스킬의 invoke 경로 확인.
- 새 스킬 추가 → plugin cache에 디렉토리 생성 필수.

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

1. **orphaned 마커** — CC가 directory source 플러그인 캐시에 `.orphaned_at`
   붙임. 로드 안 되면 해당 파일 삭제.
2. **QA → Retro 체인** — 수정 완료됐지만, 실행 시 체인 끊김이 또 발생하면
   스킬의 Invoke 지시 확인.

## Recent versions

Active changelog: `CHANGELOG.md` (v3.19+, every release with full
detail). The current line is the **v3.33.x Consolidation series**
(Tier 1 merge of dead modules / dead tools, Tier 2 in flight).

Pre-v3.19 history is archived in `docs/CHANGELOG-legacy.md` and covers:

- **v0.8 ~ v0.9** — early performance / observability work, MCP dual-write,
  Playwright runtime QA.
- **v2.x** — Universal Builder seed schema, handoff pattern, Manifesto v3
  philosophy promotion (Identity, P1~P10, INV-5).
- **v3.0** — 🌳 AC Tree era (BREAKING) plus PM Interview Mode.
- **v3.1** — Interview Renaissance (Phase 2.6~2.9), stability fixes,
  game/automation expansions.
- **v3.2** — Contract Layer (claim ledger, gates, glossary, model
  routing, jurisdiction, retro v2, performance budget).
- **v3.3** — 4-Layer Portability Foundation (Codebase Manifest,
  Decision Log ADR, Orchestrator, HostCapability).

When in doubt about an old behavior, prefer the implementation files over
the legacy changelog.
