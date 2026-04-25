# Changelog

All notable changes to SAMVIL are documented here.

---

## [3.9.1] — 2026-04-26 — Telemetry Classifier Patch

Patch release for v3.9 browser dogfood. This fixes a telemetry classifier false
positive where `install_started` was categorized as blocked because `install`
contains the substring `stall`.

### Fixed
- Event categorization now treats `stall`, `stalled`, and `blocked` as explicit
  tokens instead of arbitrary substrings.
- `install_started` + `install_complete` now reports the install stage as
  complete, not blocked.
- Phase 7 browser dogfood now records `install_started`/`install_complete`
  directly instead of using the temporary `package_setup_*` workaround.

### Added
- Regression coverage proving install events stay complete while
  `qa_stall_detected` and `deploy_blocked` still report blocked stages.

### Verified
- Telemetry tests: 8 passed.
- Direct browser dogfood: PASS with `install_started`/`install_complete` and
  `retro=0`.
- Full test suite: 802 passed.
- MCP server import smoke: 133 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.9.0] — 2026-04-26 — Browser Runtime Dogfood

Phase 7 of the multi-host SAMVIL architecture. This release adds the first
network-dependent browser dogfood path: generated apps install real npm
packages, build with Vite, run on localhost, and pass Playwright Chromium
checks.

### Added
- `scripts/phase7-browser-runtime-dogfood.py`, a browser runtime harness that
  creates Vite React SaaS dashboard and Vite Phaser game projects in temp dirs.
- `mcp/tests/test_phase7_browser_runtime_dogfood.py`, an opt-in pytest wrapper
  enabled with `SAMVIL_RUN_BROWSER_DOGFOOD=1` for network/browser validation.
- Phase 7 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.9-phase7.md`.

### Covered
- Real `npm install` for both generated browser projects.
- `npm run build` for both generated browser projects.
- Vite dev servers on dynamic localhost ports.
- Playwright Chromium page load and screenshot capture.
- Dashboard DOM checks: heading, KPI cards, chart text, table text, and filter
  button interaction.
- Browser game checks: canvas nonblank pixel, ArrowRight movement, score
  increase, and restart reset.
- Domain Pack matching, Pattern Registry lookup, Codebase Manifest generation,
  run report generation, status JSON rendering, and zero retro candidates.

### Dogfood
- `vite-saas-dashboard-browser`: pack=`saas-dashboard`, confidence=high,
  patterns=2, modules=1, events=18, retro=0, browser=`dashboard browser check ok`.
- `vite-phaser-game-browser`: pack=`browser-game`, confidence=high,
  patterns=1, modules=1, events=18, retro=0, browser=`game browser check ok`.

### Verified
- Direct browser dogfood: PASS.
- Opt-in pytest browser dogfood:
  `SAMVIL_RUN_BROWSER_DOGFOOD=1 ./.venv/bin/python -m pytest tests/test_phase7_browser_runtime_dogfood.py -q`: 1 passed.
- Full test suite: 801 passed.
- MCP server import smoke: 133 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.8.0] — 2026-04-26 — Real Runtime Dogfood

Phase 6 of the multi-host SAMVIL architecture. This release moves beyond
file-only dogfood by proving generated apps can build, start a local HTTP
runtime, and serve domain-specific user-visible content.

### Added
- `scripts/phase6-real-runtime-dogfood.py`, a network-free runtime harness
  that creates SaaS dashboard and browser game projects in temp dirs.
- `mcp/tests/test_phase6_real_runtime_dogfood.py`, a pytest wrapper that keeps
  the runtime dogfood in the full regression suite.
- Phase 6 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.8-phase6.md`.

### Covered
- `npm run build` for both generated runtime projects.
- `npm start` for both generated runtime projects.
- Localhost `/health` checks and served HTML response validation.
- SaaS dashboard runtime markers: KPI, date filter, chart, table, empty state.
- Browser game runtime markers: canvas, ArrowRight input, score, collision,
  restart.
- Domain Pack matching, Pattern Registry lookup, Codebase Manifest generation,
  run report generation, status JSON rendering, and zero retro candidates.

### Dogfood
- `saas-dashboard-runtime`: pack=`saas-dashboard`, confidence=high,
  patterns=2, modules=1, events=16, retro=0.
- `browser-game-runtime`: pack=`browser-game`, confidence=high, patterns=1,
  modules=1, events=16, retro=0.

### Verified
- Full test suite: 801 passed.
- MCP server import smoke: 133 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.7.0] — 2026-04-26 — Dual Full-Chain Dogfood

Phase 5 of the multi-host SAMVIL architecture. This release adds a
deterministic dual dogfood harness that cross-checks a business dashboard and a
browser game through the same product-domain, pattern, source, QA, telemetry,
status, and retro surfaces.

### Added
- `scripts/phase5-dual-dogfood.py`, a network-free dogfood harness that
  materializes both `saas-dashboard` and `browser-game` projects in temp dirs.
- `mcp/tests/test_phase5_dual_dogfood.py`, a pytest wrapper that keeps the
  dual dogfood in the full regression suite.
- Phase 5 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.7-phase5.md`.

### Covered
- Domain Pack matching for both scenarios.
- Pattern Registry context lookup for both scenarios.
- Codebase Manifest generation and rendering over generated source files.
- Scenario-specific QA checks:
  - dashboard: KPI cards, date range filter, empty state, chart/table sync
  - game: canvas surface, keyboard input, score loop, collision/restart
- Telemetry run reports with complete stage timelines, zero failures, zero
  retries, zero MCP failures, and zero retro candidates.
- `samvil-status.py` JSON rendering over generated run reports.

### Dogfood
- `saas-dashboard`: pack=`saas-dashboard`, confidence=high, patterns=2,
  modules=3, QA checks=4, events=14, retro=0.
- `browser-game`: pack=`browser-game`, confidence=high, patterns=1,
  modules=1, QA checks=4, events=14, retro=0.

### Verified
- Full test suite: 800 passed.
- MCP server import smoke: 133 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.6.0] — 2026-04-26 — Domain Packs

Phase 4 of the multi-host SAMVIL architecture. This adds deterministic
product-domain context that stages can request without embedding long domain
rules in skill bodies.

### Added
- `references/domain-pack-schema.md` documenting the Domain Pack boundary,
  schema, matching, and MCP tool surface.
- `mcp/samvil_mcp/domain_packs.py` with three built-in packs:
  `saas-dashboard`, `browser-game`, and `mobile-habit`.
- Domain Pack MCP tools: `list_domain_packs`, `read_domain_pack`,
  `render_domain_context`, and `match_domain_packs`.
- Deterministic pack matching from seed `solution_type`, domain fields, text
  signals, and core entity hits, including `score`, `confidence`, and
  human-readable `reasons`.
- Unit and MCP wrapper tests for pack filtering, rendering, matching, and
  invalid input handling.

### Changed
- `samvil-interview`, `samvil-design`, `samvil-build`, and `samvil-qa` now
  request `render_domain_context` with stage-specific filters instead of
  copying domain prose.
- `scripts/check-skill-wiring.py` now verifies Domain Pack tool references in
  the wired stage skills.

### Dogfood
- Synthetic seeds for all three built-in packs selected the expected top match
  with high confidence.
- Live-ish SaaS dashboard seed rendered domain context for interview, design,
  build, and QA stages.
- MCP `match_domain_packs` returned `saas-dashboard` with score 11 for the
  live-ish dashboard seed.

### Verified
- Full test suite: 799 passed.
- MCP server import smoke: 133 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.5.0] — 2026-04-26 — Telemetry + Run Observability

Phase 3 of the multi-host SAMVIL architecture. This adds a deterministic
operator telemetry layer over project state, Claim Ledger, events, MCP health,
continuation markers, retro candidates, and the status surface.

### Added
- `mcp/samvil_mcp/telemetry.py` for deterministic `.samvil/run-report.json`
  generation, reading, markdown rendering, and retro observation derivation.
- Run report MCP tools: `build_run_report`, `read_run_report`,
  `render_run_report`.
- Retro MCP tools: `derive_retro_observations`,
  `append_retro_observations`.
- Event timeline taxonomy for `start`, `complete`, `fail`, `retry`,
  `blocked`, `skip`, and `other`, including per-stage duration and
  failure/retry counters.
- MCP health failure signatures grouped by tool and normalized error text.
- `.samvil/retro-observations.jsonl` append flow with `dedupe_key` suppression.
- `mcp/tests/test_samvil_status_script.py` coverage for the status surface.

### Changed
- `scripts/samvil-status.py` now reads `.samvil/run-report.json` when present
  and prefers it for stage, tier, latest gate verdicts, pending claim count,
  MCP health, continuation, stage timeline, and next action.
- `references/run-report-schema.md` documents run report, retro observation,
  MCP tool, and status-surface contracts.

### Dogfood
- Synthetic project produced a report with 1 failure, 1 retry, stage timeline
  rendering, status output, and 5 retro candidates.
- Live repo dogfood generated `.samvil/run-report.json` for this repository
  and confirmed `samvil-status.py --format json` reports
  `run_report.present=true`.
- Dogfood caught a missing-stage JSON blind spot; status JSON now returns `?`
  instead of `null` when project state has no stage.

### Verified
- Full test suite: 787 passed.
- MCP server import smoke: 129 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.4.0] — 2026-04-26 — Multi-Host Runtime + Pattern Registry

Phase 2 of the multi-host SAMVIL architecture. This turns the v3.3 skeleton
into a practical Codex/OpenCode-compatible runtime with repeatable skill
migration rules, portable continuation markers, pattern lookup, smarter
manifest context, and cross-host regression coverage.

### Added
- `references/skill-migration-checklist.md` and
  `scripts/skill-thinness-report.py` for repeatable ultra-thin skill migration.
- `references/host-continuation.md` and
  `scripts/host-continuation-smoke.py` for `.samvil/next-skill.json` schema
  validation.
- `mcp/samvil_mcp/pattern_registry.py` with five built-in patterns:
  Next.js app router, Vite React, Phaser game, Expo mobile, Recharts dashboard.
- Pattern Registry MCP tools: `list_patterns`, `read_pattern`,
  `render_pattern_context`.
- Manifest schema `1.1`: TS/JS/Python import graph extraction, module
  summaries, `summary_generated_by`, `summary_generated_at`, and confidence
  tags such as `imports:regex` and `summary:heuristic`.
- Cross-host replay fixture under `mcp/tests/fixtures/phase2/small-web-app/`
  plus `scripts/phase2-cross-host-smoke.py`.

### Changed
- `skills/samvil-design/SKILL.md` is now a 120-line ultra-thin, host-aware
  entry. The previous 649-line body is preserved as
  `skills/samvil-design/SKILL.legacy.md`.
- `skills/samvil-seed/SKILL.md` and `skills/samvil-design/SKILL.md` now use
  the canonical continuation marker shape.
- `skills/samvil-build/SKILL.md` and `skills/samvil-qa/SKILL.md` now request
  Pattern Registry context by `solution_type` and framework.
- `scripts/pre-commit-check.sh` now verifies migrated skill thinness and
  cross-host continuation replay.

### Still Legacy
- Active high-traffic skills not yet ultra-thin: `samvil-interview`,
  `samvil-build`, `samvil-qa`, `samvil-scaffold`.
- Supporting legacy-active skills still to migrate or retire in later phases:
  `samvil-council`, `samvil-retro`, `samvil-evolve`, `samvil-deploy`.

### Verified
- Full test suite: 773 passed.
- MCP server import smoke: 124 tools.
- Cross-host replay: `claude_code` (`skill_tool`) and `codex_cli`
  (`file_marker`) both reach `seed_next=samvil-design` and
  `design_next=samvil-scaffold`.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.3.1] — 2026-04-26 — v3.3 Dogfood Manifest Patch

Patch release from direct v3.3 dogfood on a tiny Vite/React project.

### Fixed
- Codebase Manifest now represents files directly under `src/` as a synthetic
  `src` module. Small apps that start with `src/App.tsx` / `src/main.tsx` no
  longer produce an empty `.samvil/manifest.json`.
- Rendered Manifest context now includes a capped file preview per module, so
  stage-entry AI context exposes representative paths such as `src/App.tsx`
  instead of only module names.

### Verified
- Dogfood flow: interview gate blocks seed before completion, seed validates
  and saves, HostCapability selects `.samvil/next-skill.json` on Codex, standard
  tier routes seed → council → design, Council decision promotes to ADR, claims
  are posted for interview/seed/council exits, and Manifest context includes
  the app file.
- Full test suite: 761 passed.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.3.0] — 2026-04-26 — 4-Layer Portability Foundation

Phase 1 of the multi-host SAMVIL architecture. This release separates the
harness into Skill / MCP / Host Adapter / SSOT layers so future Codex,
OpenCode, and larger-app support can build on explicit contracts instead of
Claude Code assumptions.

### Added
- `mcp/samvil_mcp/manifest.py` + 4 MCP tools for Codebase Manifest build,
  read, render, and refresh. Manifest writes to `.samvil/manifest.json`.
- `mcp/samvil_mcp/decision_log.py` + 6 MCP tools for PM-readable ADRs under
  `.samvil/decisions/*.md`, including supersession and council promotion.
- `mcp/samvil_mcp/orchestrator.py` + 5 MCP tools for next-stage lookup,
  skip policy, proceed/block checks, event-derived state, and `complete_stage`.
- `mcp/samvil_mcp/host.py` + 2 MCP tools for `HostCapability` and chain
  strategy resolution across Claude Code, Codex CLI, OpenCode, and generic
  hosts.
- Schema references: `references/manifest-schema.md`,
  `references/decision-log-schema.md`, `references/orchestrator-schema.md`,
  `references/host-capability-schema.md`.
- Phase 2 planning document for the next mass-migration step.

### Changed
- `skills/samvil-seed/SKILL.md` is now an 87-line ultra-thin, host-aware PoC.
  The previous 512-line body is preserved as `SKILL.legacy.md`.
- `skills/samvil-council/SKILL.md` now promotes council decision rows to ADRs
  through `promote_council_decision` on a best-effort basis.
- Versioning policy now allows minor versions such as `3.10.0` through
  `3.99.0`; minor reaching 10 no longer auto-promotes to major.

### Verified
- Full test suite: 758 passed.
- MCP server import smoke: 121 tools.
- 4-layer integration smoke: Manifest + Decision Log + Orchestrator +
  HostCapability passed.
- `bash scripts/pre-commit-check.sh`: PASS.

## [3.2.3] — 2026-04-25 — README onboarding (contributors + end-users)

Docs-only patch. No code or skill behavior change.

### Added
- `README.md` gains a "SAMVIL 자체를 개선하려면 (Contributors)" section
  covering the 4-step local dev setup: clone → `bash scripts/install-git-
  hooks.sh` (mandatory, 1× per clone) → `mcp/` venv → pre-commit-check
  verification. End-users who only run `/samvil "..."` still read only
  the "빠른 시작" section.
- `README.md` v3.2.x patch changelog block (v3.2.1 / v3.2.2 / v3.2.3)
  so history is visible from the top-level README, not only CHANGELOG.md.
- `skills/samvil-update/SKILL.md` Step 6.5 distinguishes end-user
  upgrade path (no clone, no hooks — everything automatic via
  SessionStart + .mcp.json + save_event auto-claim) from contributor
  path (clone + install-git-hooks).

### Unchanged
- All code and pipeline behavior identical to v3.2.2.
- `/samvil:update` on existing installs still works as before (cache
  rename + venv re-install + tool coverage check). End-users see no
  additional prompts.

## [3.2.2] — 2026-04-25 — Development Discipline (CLAUDE.md)

Docs-only patch. No code change. Extends the "pre-commit check" rule
beyond commit time into the entire development workflow, so AI operators
(Claude, etc.) and human contributors apply the same quality bar at
edit time.

### Added
- `CLAUDE.md` §"🛑 ABSOLUTE RULE — Development Discipline (not just
  commits)" covering:
  - "Before claiming done" mandatory pre-commit-check.sh execution
  - Edit-time forbidden patterns table
  - Task-type checklists: new MCP tool / new skill / new agent / new
    event_type / schema change / hook script edit
  - Version bump discipline (references pre-push hook)
  - Exception workflow (--no-verify + fix commit + retro observation)
  - AI operator-specific guidance

No user-visible change. End-users running `/samvil` experience the
same pipeline as v3.2.1.

## [3.2.1] — 2026-04-25 — Portability + Pre-Commit Enforcement

Hardening patch. No user-visible feature change; internal safeguards
against the regression class that almost shipped in v3.2.0.

### Fixed
- Removed hard-coded `/Users/<name>/` absolute paths from `.mcp.json`
  (2 spots), `hooks/_contract-helpers.sh` (5 spots),
  `hooks/contract-stage-end.sh` (1 spot), and
  `skills/samvil-doctor/SKILL.md` (6 spots). All replaced with
  `${CLAUDE_PLUGIN_ROOT}` / dynamic resolution.
- `.mcp.json` switched to `uvx --from ${CLAUDE_PLUGIN_ROOT}/mcp samvil-mcp`
  (same pattern as Ouroboros), removing the first-install venv race.
- Shell shebangs unified to `#!/usr/bin/env bash` so hook scripts run
  on Alpine / Docker images where `/bin/bash` is absent.

### Added — absolute pre-commit gate
- `scripts/pre-commit-check.sh`: 6-check enforcement (hard-coded paths,
  version sync, glossary, pytest, skill wiring, MCP import) that blocks
  commits on failure.
- `.githooks/pre-commit`: delegate hook activated via
  `bash scripts/install-git-hooks.sh` (one-time per clone).
- `CLAUDE.md` absolute rule: `--no-verify` reserved for true emergencies
  with a mandatory fix commit in the same session.
- `.gitignore` excludes `.claude/settings.local.json` (machine-local
  permission prompts that would leak worktree paths).

### Verified
- `git ls-files | xargs grep -l '/Users/<name>'` → 0 hits.
- pytest 626 / glossary green / skill wiring PASS / MCP import clean.

## [3.2.0] — 2026-04-24 — Contract Layer

13개 흡수 항목(①~⑬) 전부 반영. v3.2는 "자동으로 앱을 빌드하는 도구"에서
**"요구사항·실행·검증·학습을 계약으로 관리하는 하네스"**로 전환한다.

### Added — 3 primitives

- **① Claim ledger** (`mcp/samvil_mcp/claim_ledger.py`) — `.samvil/claims.jsonl`이 append-only SSOT. 10개 type 화이트리스트 + Generator ≠ Judge 불변식 + file:line 증거 해상도.
- **⑤ Role primitive** (`mcp/samvil_mcp/model_role.py`) — 50개 agents에 `model_role:` frontmatter. generator/reviewer/judge/repairer/researcher/compressor 6 역할. 런타임 G≠J enforcement.
- **⑥ Gate framework** (`mcp/samvil_mcp/gates.py` + `references/gate_config.yaml`) — 8개 stage gate, `samvil_tier`별 기준치, 3개 escalation check (`ac_testability` / `lifecycle_coverage` / `decision_boundary_clarity`).

### Added — 7 policies

- **② Interview v3.2** (`interview_v3_2.py`) — 6 technique (seed_readiness / meta self-probe / confidence marking / scenario simulation / adversarial / PAL adaptive) + 5 `interview_level` (quick/normal/deep/max/auto).
- **③ AC leaf schema** (`ac_leaf_schema.py`) — 2 user-owned + 12 AI-inferred 필드, testability sniff, `compute_parallel_safety`.
- **④ Model routing** (`routing.py`, Lite absorb) — `cost_tier` (frugal/balanced/frontier), `.samvil/model_profiles.yaml`, escalation + downgrade. "build on Opus, QA on Codex" 시나리오 exit-gate 통과.
- **⑦ Jurisdiction** (`jurisdiction.py`) — AI/External/User 3단계, strictest-wins. git push / migration / auth 자동 escalation.
- **⑧ Retro policy evolution** (`retro_v3_2.py`) — 4-stage observations/hypotheses/policy_experiments/adopted. 21개 `(initial estimate)` 자동 experimental_policy 등록.
- **⑨ Consensus** — dispute resolver로 축소. Council Gate A는 v3.2에서 opt-in (`--council`), v3.3에서 제거 예정 (`references/council-retirement-migration.md`).
- **⑩ Stagnation** (`stagnation_v3_2.py`) — 4 signal detector, 2 신호 이상 시 severity=HIGH + lateral diagnosis prompt.

### Added — 3 infrastructure

- **⑪ Glossary + rename sweep** (`references/glossary.md` + `scripts/check-glossary.sh`) — `agent_tier → samvil_tier`, "5 gates" → `evolve_checks`. CI enforcement.
- **⑫ Migration v3.1 → v3.2** (`migrate_v3_2.py`) — backup-first, idempotent, `--dry-run`, mid-sprint rollback snapshot.
- **⑬ Performance budget** (`performance_budget.py` + `performance_budget.defaults.yaml`) — per-tier ceiling, 80% warn, 150% hard-stop, consensus 면제.

### Added — observability + docs

- `samvil status` (v1 MVP) — `scripts/samvil-status.py` (sprint + gates + budget pane, zero LLM calls)
- `samvil narrate` — Compressor-role 1-page briefing. `scripts/samvil-narrate.py` + 파이프라인 종료 시 자동.
- `scripts/view-claims.py`, `scripts/view-gates.py`, `scripts/view-retro.py` (single-topic viewer).
- 12 신규 reference 문서: glossary, gate-vs-degradation, model-routing-guide, model-profiles-schema, troubleshooting-codex, interview-levels, jurisdiction-boundary-cases, council-retirement-migration, migration-v3.1-to-v3.2, calibration-dogfood, contract-layer-protocol, performance_budget.defaults.yaml.

### Added — skill wiring (β plan)

- `samvil-interview` — post_stage `compute_seed_readiness` + `gate_check(interview_to_seed)` + claim post.
- `samvil-build` — pre_stage `route_task(build-worker)` + stage_start claim. Post_stage per-leaf `claim_post(ac_verdict)` + `gate_check(build_to_qa)` + stagnation sniff.
- `samvil-qa` — pre_stage `route_task(qa-functional)` + `validate_role_separation`. Post_stage per-leaf `claim_verify` / `claim_reject` + `consensus_trigger` + `gate_check(qa_to_deploy)`.
- `samvil-council` — `--council` opt-in + deprecation warning.
- `samvil-update` — `/samvil:update --migrate v3.2` flag (dry-run + apply).
- `samvil-retro` — 파이프라인 종료 시 `narrate_build_prompt` + `narrate_parse`.
- `samvil` (orchestrator) — Contract Layer protocol 참조 + `check_jurisdiction` pre-flight.
- `scripts/check-skill-wiring.py` — grep 기반 smoke test.

### Changed

- 50개 `agents/*.md`에 `model_role:` frontmatter 자동 주입 (`scripts/apply-role-tags.py` + `scripts/render-role-inventory.py`).
- `Session.samvil_tier` — v3.1 legacy tier field rename. DB column도 같이 rename. Migration 포함.  <!-- glossary-allow: changelog history -->
  (기존 이름은 `references/glossary.md` 참조)
- `convergence_gate.py` — docstring에서 "5 gates" → "5 evolve_checks" 리네임 (기능 동일).
- `CLAUDE.md` 상단에 Vocabulary (v3.2) 섹션 추가.

### Fixed

- v3.1 스킬들의 legacy tier 파라미터 사용을 `samvil_tier`로 통일 (기존 이름은 deprecated alias로 여전히 수용; 상세는 `references/glossary.md`).

### Deprecated

- `--council` 플래그 (v3.3에서 제거).
- legacy MCP 파라미터 (v3.3에서 제거; 이름은 `references/glossary.md` 참조).

### Tests

- 406 → **626** unit tests (+220).
- MCP tool count: 63 → **104** (+41).
- 7개 Sprint exit-gate 스크립트 (`scripts/check-exit-gate-sprint*.py`) 전부 PASS.

### Known gaps (deferred to v3.2.1 / v3.3)

- 자동 rollback CLI (`samvil-update --rollback v3.2`) — 스냅샷은 있지만 복원 루틴 미구현. 수동 복원 가능.
- 실제 dogfood 1회가 아직 미실행 — synthetic bootstrap observation만 있음. 사용자 실행 후 real observation 주입.
- seed / design / scaffold / deploy / evolve 5개 스킬의 contract layer 결선은 β 설계상 의도 제외. 필요 시 각 15~20줄 추가로 완성 가능.

---

## [3.1.0] — 2026-04-21 — Interview Renaissance + Stability + Universal Builder

Post-v3.0.0 dogfood (vampire-survivors + game-asset-gen) surfaced 27 backlog
items. v3.1.0 lands 25 of them (2 remaining are dogfood-dependent, deferred to
v3.1.1). Net effect: seed production-ready depth + GLM/GPT compatibility +
auto stall recovery + Korean-first council output.

### Sprint 0 — Backlog Schema (v3-021)
- `samvil-retro` now writes `suggestions_v2` dict schema (id / priority / component / name / problem / fix / expected_impact / sprint / source). Auto-increments IDs across entries so new retros never duplicate. `scripts/view-retro.py` CLI viewer.

### Sprint 1 — Interview Renaissance (v3-022, v3-023)
- **Deep Mode tier** — `ambiguity ≤ 0.005` + Domain pack 25~30Q. Triggers: `--deeper` flag, "더 깊게" during interview, "아직 부족한 느낌" at Phase 3.
- **Phase 2.6 Non-functional** (thorough+): perf / accessibility / security / data retention / offline / i18n / error UX.
- **Phase 2.7 Inversion** (thorough+): failure path premortem / anti-requirements / abuse vectors.
- **Phase 2.8 Stakeholder/JTBD** (full+): primary/secondary users + JTBD template + payer + motivation-vs-alternatives.
- **Phase 2.9 Customer Lifecycle** (standard+): 8 stages Discovery → Churn. Pulls AARRR/HEART/JTBD frameworks behind the scenes without exposing the acronyms to the user.
- References: `interview-frameworks.md` + `interview-question-bank.md` (110 questions across common + 5 domain packs).
- Seed schema: `customer_lifecycle`, `non_functional`, `inversion`, `stakeholders` objects.

### Sprint 2 — Stability CRITICAL (v3-016, v3-017, v3-019)
- **Stall detection for design/council/evolve** — `state.json`-driven heartbeat complements the events.jsonl-based `detect_stall` (v2.6.0). 4 new MCP tools: `heartbeat_state`, `is_state_stalled`, `build_reawake_message`, `increment_stall_recovery_count`.
- `samvil-design` Step 3a-3d + `samvil-council` Step 2a integrate pre-spawn announcement + per-agent progress + between-batch stall check. Regression case from mobile-game dogfood (25-minute hang) now auto-recovers within 5 minutes.
- **Model compatibility** (`references/model-specific-prompts.md`): Claude/GLM/GPT per-stage guidance. Measured 6×+ Sonnet-vs-GLM gap surfaced in docs, **not** enforced as rejection.
- **Auto-chain policy** (`state-schema.auto_chain`): pipeline stages chain without user approval by default. Interview/Seed still require confirmation. Legacy `'go' to proceed` prompts removed.

### Sprint 3 — Game Domain + Automation Scaffold (v3-013, v3-014, v3-015, v3-025)
- `game-interviewer` agent expanded with 3 new question blocks: lifecycle architecture (solo/multi, login, save, ranking, IAP), mobile spec (resolution, orientation, input, supported devices), art direction.
- `agents/game-art-architect.md` new — translates `seed.art_design` into Phaser-ready specs (sprite strategy, palette, HUD layout, animation plan, audio spec). Spawned by `samvil-design` when `solution_type == "game"`.
- Seed schema: `game_config`, `game_architecture`, `art_design` objects (no more 800×600 default).
- `samvil-scaffold` automation: external API model IDs externalized to `.env.example` per `seed.external_api_config.providers`. `game-asset-gen` regression (Gemini hardcoded → 404) now impossible.

### Sprint 5 — Polish (v3-005, v3-006, v3-008, v3-009, v3-018, v3-020, v3-024)
- `samvil-update` Step 1 fallback (plugin.json missing/corrupt → explicit "unknown" + folder name), Step 5a folder rename so `cache/samvil/samvil/3.0.0/` → `3.1.0/` after rsync.
- `agents/reflect-proposer.md`: AC Tree Mutation Rules section — node shape, allowed mutations (add/split/merge/remove/update), status transitions, evidence requirements.
- `test_stage_enum_sync.py` pins Stage enum vs state-schema so council/design can't silently drop out of the enum.
- `references/cost-aware-mode.md` — GLM-main + Claude-sub pattern as first-class supported workflow.
- README + `samvil-doctor` Step 10: per-stage recommended model table with the 6x+ measurement cited.
- `references/council-korean-style.md` — 6 council agents route their output through the Korean-first style guide (labels in Korean, English jargon parenthesized, "왜 문제인가" line for BLOCKING findings).

### Sprint 6 — Long Tail (v3-010, v3-011, v3-012)
- Atomic counter for `_HEALTH_OK_SAMPLE_RATE` (threading.Lock), so concurrent MCP calls don't lose increments or mis-sample.
- `suggest_ac_split` MCP tool + `ac_split.py` heuristic for evolve cycle — detects compound connectors / multi-verb / many-commas and proposes a split.
- `hooks/setup-mcp.sh` SessionStart tool coverage check — diffs expected tools against what the server exposes.

### Sprint 4 — Dogfood preparation (v3-026, v3-027)
- `samvil-build` Phase A.6 Scaffold Sanity Check: empty config files / unsubstituted `{{VARS}}` / broken imports detected before Phase B-Tree.
- `samvil-qa` Pass 1b API Connectivity Check for automation — probes each provider in `seed.external_api_config.providers`, warns on 401/403/429, fails on 404 (deprecated model).
- Remaining dogfood items (v3-001~004, v3-007) defer to v3.1.1 once dogfood sessions produce measurement data.

### Tests

- 375 → 406 (+31): retro schema 5 · deep-mode interview 9 · state-based stall 11 · stage enum sync 3 · atomic counter 2 · AC split 6.

### Migration

- No breaking seed schema changes. v3.0.0 seeds load unchanged. New optional fields populate when interview goes through the new phases.
- Retro entries from before v3.0.1 keep legacy `suggestions` string array; new entries always use `suggestions_v2`.

### Known follow-ups (v3.1.1)

- v3-001: real Next.js dogfood end-to-end (web-app type)
- v3-002: 50+ AC Phase B-Tree measurement
- v3-003: Worker contract real-call capture
- v3-004: `_log_mcp_health` sampling tune with production data
- v3-007: PM-interview live user run

---

## [3.0.0] — 2026-04-19 — 🌳 AC Tree Era (BREAKING)

Sprint 3 converts SAMVIL's acceptance-criteria handling from flat lists to a
tree structure with leaf-level build/QA execution. **v2.x seeds need
migration** — see `references/migration-v2-to-v3.md`.

### ⚠️ Breaking changes

- `seed.features[].acceptance_criteria` is now a tree of `{id, description, children[], status, evidence[]}` nodes.
- `seed.schema_version` is required and defaults to `"3.0"`. v2.x seeds still load but Phase B auto-migrates them (backup written to `project.v2.backup.json`).
- Build/QA iterate **leaves**, not features. Flat v2 ACs become single-leaf branches after migration, so visible behavior is unchanged for simple seeds.

### T1 — AC Tree Build/QA (4 commits)

- **Tree traversal helpers** (`mcp/samvil_mcp/ac_tree.py`): `is_branch_complete`, `all_done`, `next_buildable_leaves`, `tree_progress`. Honors blocked parents, completed sets, `max_parallel`.
- **Migration module** (`mcp/samvil_mcp/migrations.py`): `migrate_seed_v2_to_v3` + `migrate_with_backup` (idempotent, writes sidecar backup).
- **MCP tools** (server.py): `next_buildable_leaves`, `tree_progress`, `update_leaf_status`, `migrate_seed`, `migrate_seed_file`.
- **samvil-build rewrite** (`skills/samvil-build/SKILL.md`): Phase B-Tree replaces feature-batch dispatch. Legacy Phase B retained as documentation for Dynamic Parallelism / Independence Check / Worker Context Budget (all reused by tree path).
- **samvil-qa aggregation** (`skills/samvil-qa/SKILL.md`): Pass 2 iterates leaves; branch verdicts come from `aggregate_status`; report renders the tree; `qa-results.json` stores `schema_version: "3.0"`.
- **samvil-update --migrate** (`skills/samvil-update/SKILL.md`): post-update Step 7 detects v2.x seeds and offers migration; `--migrate` flag runs migration standalone.

### T2 — LLM Dependency Planning

- `mcp/samvil_mcp/dependency_analyzer.py`: Kahn's toposort with serial-only stage splitting, cycle detection, structured + LLM-inferred dep merging.
- MCP tool `analyze_ac_dependencies` (JSON-in / plan-out).
- samvil-build Phase B-Tree Step 2.5: optional plan for tier ≥ thorough and ≥ 5 ACs. `full` tier invokes LLM from the skill layer.

### T3 — Shared Rate Budget

- `mcp/samvil_mcp/rate_budget.py`: file-based cooperative slot tracker (`acquire`, `release`, `stats`, `reset`).
- MCP tools: `rate_budget_acquire`, `rate_budget_release`, `rate_budget_stats`, `rate_budget_reset`.
- samvil-build Phase B-Tree: acquire before spawn, release after return, summary event at feature end.

### T4 — PM Interview Mode

- New optional entry point skill `samvil-pm-interview` (vision → users → metrics → epics → tasks → ACs).
- `mcp/samvil_mcp/pm_seed.py`: `validate_pm_seed` + `pm_seed_to_eng_seed` (flattens epics/tasks into v3 features).
- `references/pm-seed-schema.md` documents the PM spec shape.
- MCP tools: `validate_pm_seed`, `pm_seed_to_eng_seed`.

### Tests

- 254 → 310 (+56): 24 AC tree helpers / migrations, 14 dependency analyzer, 8 rate budget, 10 PM seed.

### Migration

- `/samvil:update --migrate` runs `migrate_seed_file` standalone in the current project directory.
- Backup is written to `project.v2.backup.json` before rewrite; re-running is idempotent.
- See `references/migration-v2-to-v3.md` for manual recovery.

---

## [2.5.0] — 2026-04-18 — Phase 3+4+5+6 통합 (QA, Evolve, Resilience, AC Tree)

단일 릴리즈로 나머지 모든 Phase 통합. Ouroboros 15개 기능 중 **핵심 9개 실구현 완료**.

### Phase 3: QA 강화 (P1/#04/#08)

- **Per-AC Checklist Aggregator** (`checklist.py`) — ACCheckItem/ACChecklist/RunFeedback 구조
- **Evidence Mandatory 실구현** (`evidence_validator.py`) — file:line 파싱 + 검증
- **Reward Hacking Detection** (`semantic_checker.py`) — stub/mock/하드코딩/empty catch 패턴 탐지
- **QA skill Pass 2.5 추가** — Evidence validation + Semantic check + Downgrade rules
  - HIGH risk → 자동 FAIL (E1 "Stub=FAIL")
  - MEDIUM risk → PARTIAL + Socratic Questions
  - LOW risk → PASS 유지
- **QA report 구조화** — per-AC checklist, evidence tracking

### Phase 4: Evolve Gates + Self-Correction (P5/#03/#P9)

- **Regression Detector** (`regression_detector.py`) — PASS→FAIL 전환 감지
- **5-Gate Convergence** (`convergence_gate.py`) — Eval/Per-AC/Regression/Evolution/Validation
  - 하나라도 실패하면 수렴 거부 (blind convergence 제거)
  - Fail-fast: 모든 이유를 사용자에게 투명하게 표시
- **Self-Correction Circuit** (`self_correction.py`) — 실패가 다음 cycle의 Wonder 입력이 됨
  - `.samvil/qa-failures.json` (current cycle)
  - `.samvil/failed_acs.json` (accumulated)
  - Wonder에 구조화된 summary 자동 주입

### Phase 5: Resilience — Progress Viz (#15)

- **Double Diamond Renderer** (`progress_renderer.py`) — ASCII 진행 상황
  - Discover/Define/Develop/Deliver 4-phase
  - Stage status: ✓/⟳/⏸/✗
  - Feature별 AC progress 추가 표시 가능
- `.samvil/progress.md` 자동 업데이트 (매 stage 완료 시)

### Phase 6: AC Tree Infrastructure (#06, backward-compat)

- **ACNode Tree 구조** (`ac_tree.py`) — recursive, MAX_DEPTH=3
- **Status Aggregation** — branch = aggregate of children
- **ASCII HUD Renderer**
- **Backward-compatible Loader** — string/dict 자동 변환
- **Seed Schema 확장** — flat + tree 혼합 허용
- **Heuristic Decomposition Suggestion** (LLM 없이)
- 실제 Build/QA tree 순회는 **v2.6+ 이후** (v2.5.0은 infrastructure only)

### MCP Tools 추가 (11개)

Phase 3:
- `build_checklist`, `aggregate_run_feedback`, `validate_evidence`, `semantic_check`

Phase 4:
- `check_convergence_gates`, `detect_ac_regressions`, `record_qa_failure`, `load_failures_for_wonder`

Phase 5:
- `update_progress`

Phase 6:
- `parse_ac_tree`, `render_ac_tree_hud`, `suggest_ac_decomposition`

### 신규 MCP 모듈 (7개)

- `checklist.py` — Per-AC checklist data structures
- `evidence_validator.py` — file:line parser + validator
- `semantic_checker.py` — Reward Hacking detection
- `convergence_gate.py` — 5-gate validation
- `regression_detector.py` — AC regression detection
- `self_correction.py` — failed_acs.json handling
- `progress_renderer.py` — ASCII Double Diamond
- `ac_tree.py` — Recursive AC Tree

### 테스트 (81개 신규)

- `test_checklist.py` (10)
- `test_semantic_checker.py` (11)
- `test_convergence_gate.py` (17)
- `test_ac_tree.py` (13)
- `test_progress_renderer.py` (6)
- `test_evidence_validator.py` (10)
- `test_self_correction.py` (8)

누적 전체 MCP 테스트: **179 passed / 2 failed** (둘 다 phase와 무관한 기존 이슈)

### 스킬 업데이트

- `samvil-qa/SKILL.md` — Pass 2.5 (Semantic Verification) 추가
- `samvil-evolve/SKILL.md` — Step 6 전면 개편 (5-gate + self-correction)
- `samvil/SKILL.md` — Progress visualization 자동 호출

### References 신규

- `references/ac-tree-guide.md` — AC Tree 사용 가이드
- `references/reversibility-guide.md` — P10 Reversibility Awareness

### Seed Schema 변경

- `acceptance_criteria` — flat + ACNode tree 혼합 허용 (backward-compat)

### v2.5.0은 실질적으로 v3.0.0 수준의 개선

- 9/15 Ouroboros 기능 실구현 (나머지 6개는 infrastructure 또는 future)
- 10개 중 9개 원칙(P1~P10) 코드 수준에서 적용
- 단, AC Tree는 infrastructure만 — 실제 build/qa 순회는 v2.6+에서

---

## [2.4.0] — 2026-04-18 — Phase 2: Interview 심화

인터뷰 피로도 감소 + 명료화 강화. PATH routing 활성화로 1인 개발자 체감 큰 변화.

### Added

- **#01 PATH Routing 실구현** — 5가지 경로 자동 분기
  - `mcp/samvil_mcp/path_router.py` (신규, 338줄)
  - PATH 1a (auto_confirm), 1b (code_confirm), 2 (user), 3 (hybrid), 4 (research), forced_user
  - Description vs Prescription 원칙 (P2) 코드 수준 구현

- **#02 Rhythm Guard 활성화** — AI 독주 방지 장치
  - 연속 3회 AI 자동답변 → 다음 질문은 강제로 사용자에게
  - `interview_engine.update_streak()` 함수
  - `answer_source` prefix로 출처 추적

- **#05 Milestones + Component Floors** — 다차원 모호도
  - INITIAL → PROGRESS → REFINED → READY 4단계 마일스톤
  - Component floor (goal 0.75 / constraint 0.65 / criteria 0.70) 강제
  - `missing_items` 자동 추출 → UI 피드백

- **#P4 Breadth-Keeper Tracks** — 인터뷰 편향 방지 (간소화)
  - `interview_tracks` 필드 실제 작동
  - 한 토픽 3라운드 이상 몰리면 자동 리마인드
  - `manage_tracks` MCP tool (init/update/resolve/check)

### Changed

- `mcp/samvil_mcp/interview_engine.py` — score_ambiguity 반환에 milestone/floors/missing_items 추가 (하위호환 유지)
- `mcp/samvil_mcp/server.py` — 5개 신규 MCP tool (scan_manifest, route_question, update_answer_streak, manage_tracks, extract_answer_source)
- `skills/samvil-interview/SKILL.md` — Step 0.7 실제 작동 로직 기술

### Added files

- `mcp/samvil_mcp/path_router.py` (신규)
- `mcp/tests/test_path_router.py` (14 test cases)
- `mcp/tests/test_interview_engine_v2.py` (20 test cases)
- `references/path-routing-guide.md` (신규)

### Tests

- 34개 신규 테스트 전부 통과
- 기존 테스트 6개 + 신규 34 = 40 interview-related tests passing
- 전체 MCP 테스트 99 passed / 1 failed (기존 이슈, Phase 2 무관 — scaffold cli_command 검증)

### Behavior change

- **1인 개발자 체감**: Brownfield 프로젝트에서 Framework/Language/DB 질문 자동 확정. 인터뷰 질문 **70% 감소 예상**.
- **안전 장치**: MCP 실패 시 전부 user path fallback (INV-5 Graceful Degradation).

---

## [2.3.0] — 2026-04-18 — Phase 1: Quick Wins

Phase 1 of the Ouroboros absorption plan. Additive changes only — no breaking.

### Added

- **Deferred MCP Loading (#14)** — `references/boot-sequence.md` Section 0 추가. 모든 스킬이 자동으로 상속. samvil 오케스트레이터 + samvil-analyze에도 별도 명시.
- **Icon-based Output Format (#P7)** — `references/output-format.md` 신규. ℹ️/💬/🔍 아이콘으로 AI 행동 출처 구분 (v3 P7 Explicit over Implicit).
- **Decision Boundary Display (#P3)** — `references/boot-sequence.md` Section 0a. 각 스킬 시작 시 종료 조건을 사용자에게 표시.
- **Evidence-Mandatory Rule (#P1, 선언만)** — `references/qa-checklist.md` 최상단에 Evidence 필수 섹션 추가. 실제 구현은 v2.5.0 (Phase 3).
- **Rhythm Guard Scaffold (#02)** — `references/state-schema.json`에 `ai_answer_streak`, `interview_tracks`, `failed_acs` 필드 추가. samvil-interview SKILL에 Step 0.7 규칙 명시. 실제 강제는 v2.4.0 (Phase 2).

### Notes

- 기존 스킬 행동 변화 없음 (문서/스키마 추가만)
- 실제 강제는 Phase 2+ (PATH routing, Reward Hacking 등)에서 시작
- v3.0.0 목표까지 12주 로드맵 진행 중

### Files Changed

- `references/boot-sequence.md` (+MCP Loading +Decision Boundary)
- `references/output-format.md` (신규)
- `references/qa-checklist.md` (+Evidence-mandatory 섹션)
- `references/state-schema.json` (+3 필드 스캐폴드)
- `skills/samvil/SKILL.md` (+ToolSearch in Health Check)
- `skills/samvil-analyze/SKILL.md` (+MCP Prerequisites)
- `skills/samvil-interview/SKILL.md` (+Step 0.7 Rhythm Guard scaffold)

---

## [2.2.0] — 2026-04-18 — Manifesto v3 (Philosophy)

문서 전용 릴리즈. 코드 변경 없음. 철학 명문화 + Ouroboros 흡수 계획 수립.

### Added

- **Identity (5가지 정체성)**: Solo Developer First / Universal Builder / Robustness First / Converge-then-Evolve / Self-Contained
- **10 Core Principles (P1~P10)**:
  - P1 Evidence-based Assertions — 모든 PASS는 file:line 증거 필수
  - P2 Description vs Prescription — 사실은 AI, 결정은 사용자
  - P3 Decision Boundary — "충분함"을 숫자로 명시
  - P4 Breadth First, Depth Second — tracks 리스트로 편향 방지
  - P5 Regression Intolerance — 퇴화 감지 시 수렴 거부
  - P6 Fail-Fast, Learn Later — 빠른 포기 + 다음 cycle 재료로
  - P7 Explicit over Implicit — 아이콘(ℹ️ 💬 🔍)으로 표시
  - P8 Graceful Degradation — 일부 실패해도 전체 계속
  - P9 Circuit of Self-Correction — 실패→학습→재시도 루프
  - P10 Reversibility Awareness — Irreversible은 확인 필수
- **INV-5: Graceful Degradation** — 기존 내부 패턴(INV-7)을 정식 Invariant로 승격
- **3-Level Completion 정의** — L1 Build / L2 QA / L3 Evolve 수렴 (Deploy 선택)
- **Decision Boundaries 수치화** — 각 단계 종료 조건 명시
- **Anti-Patterns 섹션** — Stub=FAIL, Evidence 없는 PASS=FAIL 등 명시
- **Error Philosophy** — Mechanical=버그, Semantic=정보
- **흡수 로드맵** — `~/docs/ouroboros-absorb/` 문서 17개 생성 (Ouroboros v0.28.7 → SAMVIL v3.0.0 흡수 계획)

### Changed

- README 슬로건: "한 줄 입력 → 완성된 앱" → "한 줄 입력 → 자가 진화하는 견고한 시스템"
- Description in plugin.json 업데이트 (견고성/자가 진화 강조)
- User Checkpoints 규칙 업데이트 — 인터뷰/시드 이후는 실패 시에만 개입

### Notes

- v2.2.0은 **문서 개정만**. 실제 코드 변경은 v2.3.0 (Sprint 1 Quick Wins)부터 시작.
- 다음 단계: IMPLEMENTATION-PLAN.md의 Phase 1 진행 승인 대기.

---

## [2.1.0] — 2026-04 — Handoff & UX Improvements

- Handoff 패턴 (세션 간 복구)
- 시드 요약 포맷 구조화
- Council 결과 포맷 개선
- Retro suggestion 구조화 (ISS-ID + severity + target_file)
- 구버전 캐시 자동 삭제
- Resume 강화

## [2.0.0] — Universal Builder

- Seed Schema v2 (solution_type 추가)
- 3-Layer solution_type 감지
- validate_seed 확장
- Dependency Matrix 확장 (Python, Phaser, Expo)
- App Presets 확장 (Automation, Game, Mobile, Dashboard)

## [1.0.0] — Initial stable

- 11개 스킬 체인
- 4 Tier (minimal/standard/thorough/full)
- Next.js 14 + shadcn/ui scaffold
- 3-pass QA
- Council 2-round
