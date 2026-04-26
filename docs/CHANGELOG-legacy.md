# SAMVIL Changelog — Legacy (v0.x ~ v3.3.x)

> Archived from `CLAUDE.md` during T2.5 consolidation. For v3.19+
> release notes see `CHANGELOG.md` at the repo root. For active rules
> see `CLAUDE.md`. This file exists for historical context only — do not
> derive current behavior from anything below.

Order: oldest → newest within each major.

---

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

---

## v2.0.0 변경 내역 (v1.0.0 → v2.0.0) — Universal Builder

1. **Seed Schema v2** — `solution_type` 필드 추가 (web-app/automation/game/mobile-app/dashboard). `mode` deprecated, 자동 마이그레이션. `tech_stack.framework` enum 확장 (phaser/expo/python-script/node-script). `core_experience` oneOf (screen + core_flow 패턴). `implementation` object 추가 (type/runtime/entry_point).
2. **3-Layer solution_type 감지** — 오케스트레이터 Step 2에 L1 키워드 매칭 + L2 컨텍스트 추론 + L3 인터뷰 검증 로직 추가. 감지된 타입을 인터뷰에 컨텍스트로 전달.
3. **validate_seed 확장** — MCP seed_manager가 새 프레임워크, solution_type, core_flow 패턴 검증 지원. 레거시 mode 자동 마이그레이션.
4. **Dependency Matrix 확장** — python-script, phaser-game, expo-mobile 스택 엔트리 추가.
5. **App Presets 확장** — Automation(5종), Game(3종), Mobile(3종), Dashboard(2종) 프리셋 카테고리 추가. solution_type별 매칭 규칙 추가.

## v2.1.0 변경 내역 (v2.0.0 → v2.1.0) — Handoff & UX Improvements

1. **Handoff 패턴** — 각 스킬 완료 시 `.samvil/handoff.md`에 누적 append. context limit 도달 시 새 세션에서 `/samvil`로 handoff.md 읽고 복구. 7스킬 16포인트. Write tool 금지, Bash `cat >>` 또는 Edit로 append.
2. **시드 요약 포맷** — Step 4에서 플레이스홀더 대신 실제 값으로 구조적 요약. solution_type별 분기 (screen 패턴: web-app/dashboard/mobile, flow 패턴: automation/game).
3. **Council 결과 포맷** — 섹션별 판결(N/M APPROVE) + 에이전트별 2-3줄 근거 + 반대 의견 상세화.
4. **Retro 개선** — suggestion에 ISS-ID + severity(CRITICAL/HIGH/MEDIUM/LOW) + target_file + reason + expected_impact 구조화. feedback.log JSON도 구조화.
5. **구버전 캐시 자동 삭제** — samvil-update Step 5 추가. `$LATEST` empty check(`-z`) + 디렉토리 존재 check(`-d`) 이중 가드. 삭제 전후 용량 로깅.
6. **Resume 강화** — 오케스트레이터가 state.json + handoff.md 읽어서 이전 세션 결정 사항 요약 제시.

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

## v3.2.0 변경 내역 (v3.1.0 → v3.2.0) — Contract Layer

v3.2 흡수 13개 항목 모두 구현. 626 unit tests · 104 MCP tools · Sprint별 exit-gate PASS.

### Sprint 1 — Foundation primitives (① ⑥ ⑪)
- `mcp/samvil_mcp/claim_ledger.py` (18 tests) — `.samvil/claims.jsonl` SSOT. 10개 type 화이트리스트 + Generator ≠ Judge + file:line 해상도.
- `mcp/samvil_mcp/gates.py` (27 tests) + `references/gate_config.yaml` — 8 gates, `samvil_tier`별 기준치, 3개 escalation check.
- `references/glossary.md` + `scripts/check-glossary.sh` (CI) — `agent_tier → samvil_tier` rename. 5 gates → 5 evolve_checks.  <!-- glossary-allow: historical rename note -->
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

---

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
