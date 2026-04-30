# Changelog

All notable changes to SAMVIL are documented here.

---

## v4.14.0 — 2026-04-30

**Auto-recovery for stuck stages (MINOR)**

Phase C.④ of the 5-phase pipeline-improvement plan.

- `mcp/samvil_mcp/auto_recovery.py` (new): composes `is_state_stalled`
  + `stall_recovery_count` + `build_reawake_message` into a single
  decision call. Returns one of four actions:
  - `none`     pipeline healthy
  - `reentry`  stalled but under retry budget; re-enter current stage
  - `escalate` retries exhausted; halt automation, ask user (P10)
  - `block`    state corruption; cannot auto-recover
- `evaluate_stuck_recovery(project_root, apply, threshold_seconds)` MCP
  tool (175th tool). Default `apply=False` keeps the call side-effect
  free; `apply=True` on `reentry` bumps `stall_recovery_count` so the
  next call (still stalled) escalates correctly.
- Reuses existing primitives — no new state schema, no new event types.
  Just a new orchestrator that skill bodies can call without chaining
  three tools manually.
- `mcp/tests/test_auto_recovery.py` (new): 8 tests covering each verdict
  branch, the apply flag, MCP wrapping, and tool registration.

User-facing change: when a stage stalls, the pipeline can either resume
itself (within the 2-retry budget) or surface a clear AskUserQuestion
to the user, instead of silently sitting at idle.

---

## v4.13.0 — 2026-04-30

**Real-time progress panel + ETA (MINOR)**

Phase B.③ of the 5-phase pipeline-improvement plan.

- `mcp/samvil_mcp/progress_panel.py` (new): `compute_progress()` reads
  `project.state.json`, `project.seed.json`, `.samvil/events.jsonl` and
  emits a structured view (current stage, completed stages, leaf counts,
  elapsed-in-stage, last-event age, ETA). `render_panel()` renders an
  ASCII frame the user can read at a glance.
- `mcp/samvil_mcp/server.py`: new `render_progress_panel(project_root)`
  MCP tool (174th tool) that returns `{progress, panel}` JSON.
- ETA model: per-(stage, samvil_tier) baseline durations. build/qa
  scale by AC leaf count and remaining work. Missing data → ETA "unknown"
  rather than guessing (P3 / P10).
- `mcp/tests/test_progress_panel.py` (new): 8 tests covering empty
  state, leaf walking, pipeline marks, ETA scaling, elapsed timing,
  panel rendering, MCP wrapping, and tool registration.

User-facing change: any skill or script can now call this tool to give
the user a single-shot answer to "where am I, how long until done?".
A solo developer no longer needs to grep events.jsonl by hand to know
whether the pipeline is stuck.

---

## v4.12.0 — 2026-04-30

**Host parity CI — CC ↔ Codex drift detection (MINOR)**

Phase A.② of the 5-phase pipeline-improvement plan.

- `scripts/check-host-parity.py` (new): pairs every CC `skills/<name>/SKILL.md`
  with its Codex `references/codex-commands/<name>.md` twin and verifies:
  - Both files exist (no orphans).
  - Each side references its host-specific core MCP tool set
    (`CORE_TOOLS_CC` / `CORE_TOOLS_CODEX`).
  - Mechanical Codex stages (`samvil-evolve`, `samvil-retro`) declare an
    explicit `## Auto-Proceed Policy` heading — guards against the v4.11.0
    retro regression where the chain stopped between evolve and retro.
  - Non-terminal stages mention chain/next_skill on both sides.
- `references/host-parity-allowlist.yaml` (new): empty baseline allowlist
  for intentional gaps; entries require a `# why:` rationale.
- `scripts/pre-commit-check.sh`: now has check #10 running parity in
  --strict mode. Total 10 checks, 1592 tests gated on every commit.
- `mcp/tests/test_host_parity.py` (new): 6 tests including negative tests
  that delete the Auto-Proceed heading and verify the script catches it.

User-facing change: future SAMVIL changes that update one host's contract
without the other are blocked at commit time. Codex users will no longer
silently see a different pipeline behavior than CC users.

---

## v4.11.1 — 2026-04-30

**Plugin auto-sync — eliminate manual `cp` toil (PATCH)**

Phase A.① of the 5-phase pipeline-improvement plan.

- `scripts/sync-cache.sh` (new): copies the working tree to the
  installed plugin cache (`~/.claude/plugins/cache/samvil/samvil`)
  via rsync against a curated whitelist of 12 source dirs/files.
  Supports `--dry-run` and `--quiet`. Graceful degradation when
  the cache directory is absent (plugin not installed).
- `.githooks/post-commit` (new): auto-invokes `sync-cache.sh` after
  every successful commit so committed changes take effect immediately.
  Failures are non-fatal (commit already happened).
- `scripts/install-git-hooks.sh`: now reports the post-commit hook in
  the install summary.
- `mcp/tests/test_sync_cache_smoke.py` (new): 8 tests covering script
  existence, dry-run, real run, idempotency, cache-side file preservation,
  graceful degradation, quiet mode, and hook wiring.

User-facing change: maintainers no longer need to run 7-8 `cp` commands
after every code change — the post-commit hook handles it automatically,
and a manual `bash scripts/sync-cache.sh` is available for explicit re-syncs.

---

## v4.11.0 — 2026-04-30

**Pomodoro dogfood retro improvements: Vite deploy fix + CLI pin + retro fallback + Codex auto-proceed (MINOR)**

Four improvements from the pomodoro-timer Codex dogfood retro:

### v3-001 — Vite deploy artifact path fix

- `mcp/samvil_mcp/deploy_targets.py`: added `_VITE_LIKE_FRAMEWORKS` frozenset and
  `_artifact_paths_for_framework()` helper. `evaluate_deploy_target()` now resolves
  artifact paths from `seed.tech_stack.framework` (Vite/Astro → `dist/`,
  Next.js → `.next/`) instead of hardcoding per `solution_type`.
  Previously Vite web-app projects were blocked by Next.js artifact assumptions.
- 8 new tests in `test_deploy_smoke.py`.

### v3-002 — create-vite CLI version pin separation

- `references/dependency-matrix.json`: `vite-react` and `phaser-game` stacks now use
  `npm create vite@latest` in `cli_command` with a `scaffold_cli`, `_cli_preflight`,
  and `_cli_note` field. Previously `npm create vite@5` could be misread as
  `create-vite@5.4.21` (same as the runtime pin), which doesn't exist on npm.
- `mcp/tests/test_scaffold.py`: updated `test_cli_commands_are_valid` to allow `@latest`,
  and `test_version_format_consistency` to skip `_`-prefixed metadata keys and `scaffold_cli`.

### v3-003 — Retro metrics file-based fallback

- `mcp/samvil_mcp/retro_aggregate.py`: when `events.jsonl` is sparse (e.g., Codex
  runs that don't emit all MCP events), metrics now fall back to:
  - `qa-results.json` for QA verdict and AC leaf counts.
  - `project.state.json` `completed_stages` for flow compliance.
  - `seed.features` AC tree for leaf status counts (last resort).
  - `project.state.json` `qa_status` for verdict (always-written fallback).
- New helpers: `_derive_features_from_seed`, `_derive_qa_verdict_from_files`.
- `compute_v3_leaf_stats` and `compute_flow_compliance` now accept `qa_results`/`seed`/`state`
  optional params; results include a `source` field (`events|qa_results|seed|state_file`).
- `aggregate_retro_metrics` also reads `qa-results.json` and passes it through.
- 5 new tests in `test_retro_smoke.py` (total: 21 tests).

### User FB — Codex chain auto-proceed for evolve/retro

- `references/codex-commands/samvil-evolve.md`: added **Auto-Proceed Policy** section.
  After evolve completes (when convergence succeeds without regressions), Codex must
  immediately start `samvil-retro` without asking for user confirmation.
- `references/codex-commands/samvil-retro.md`: added **Auto-Proceed Policy** section.
  Retro is always mechanical — executes immediately when chained, no pause for confirmation.
  The only user-decision point is the optional evolve-cycle prompt at the very end.

---

## v4.10.4 — 2026-04-29

**health_check MCP tool + environment table (MINOR)**

- `server.py`: new `health_check()` MCP tool (173rd tool) returns
  `samvil_version`, `tool_count`, `db_ok`, `python_version`, `summary`.
  Previously referenced in SKILL.md but did not exist.
- `skills/samvil/SKILL.md`: boot step 1 now calls `health_check()` +
  `get_health_tier_summary()` + bash version checks in parallel, then
  renders a full 8-row environment table (SAMVIL / Node / Python / uv /
  gh / MCP tools / DB / Health Tier) before asking any question.
- 1 new smoke test in `test_server_tools_smoke.py`.

---

## v4.10.3 — 2026-04-29

**Health tier rolling window — prevent stale CRITICAL (PATCH)**

- `health_tiers.py`: `_load_health_log` now returns only the last
  `ROLLING_WINDOW=5000` entries (tail-window). Previously the entire
  `~/.samvil/mcp-health.jsonl` was scanned; after months of development
  this file grew to 124k entries with old `save_event`/`gate_check`
  failures, permanently forcing CRITICAL tier even when current health
  was fine.
- 3 new tests in `test_health_tiers.py`.

---

## v4.10.2 — 2026-04-29

**Codex CLI samvil.md health check parity (PATCH)**

- `references/codex-commands/samvil.md`: added `health_check()`,
  `get_health_tier_summary()`, `aggregate_orchestrator_state()`, tier
  selection prompt, brownfield routing, `.samvil/` initialization, and
  pipeline start banner — matching the Claude Code SKILL.md boot sequence.
  Previously Codex skipped all environment/version checks and jumped
  straight to "무엇을 만들까요?".

---

## v4.10.1 — 2026-04-28

**Codex CLI AGENTS.md path fix (PATCH)**

- `scripts/setup-codex.sh`: `_install_agents()` now uses `sed` to replace
  `references/` and `scripts/` prefixes with the absolute `SAMVIL_ROOT` path
  when installing `~/.codex/AGENTS.md`. Previously Codex CLI could not resolve
  instruction files (e.g. `references/codex-commands/samvil-interview.md`) when
  running from a user's project directory instead of the SAMVIL source tree.

---

## v4.10.0 — 2026-04-28

**Brownfield Interview Mode — code analysis + interview + seed merge (MINOR)**

- `interview_engine.py` v2.6.0: `pre_filled_dimensions` parameter added to
  `score_ambiguity`. Each pre-filled dimension is forced to 0.0 and reduces
  `MIN_QUESTIONS` by 1 (floor 2). Brownfield analysis pre-fills `technical` and
  `nonfunctional` dims so only improvement-goal questions are asked.
- `seed_manager.py`: `merge_brownfield_seed(existing_seed, interview_state, new_features)`
  merges analysis seed (status:existing) + interview findings (status:new), unions
  constraints, prefers interview metadata when more specific, preserves tech_stack.
- `server.py`: `score_ambiguity` tool gains `pre_filled_dimensions` (comma-separated),
  `merge_brownfield_seed` MCP tool added (172 tools total).
- `skills/samvil-analyze/SKILL.md`: Step 5 "기능 추가/개선" now routes through
  samvil-interview (Brownfield Mode) instead of directly to samvil-build. Full chain:
  analyze → interview → merge_brownfield_seed → samvil-build.
- `skills/samvil-interview/SKILL.md`: Brownfield Mode section — auto-detects
  `state._analysis_source == "brownfield"`, skips tech-stack phases, focuses on
  improvement goals, calls merge_brownfield_seed at the end instead of samvil-seed.
- `references/codex-commands/samvil-analyze.md`: updated with chain to samvil-interview.
- `references/codex-commands/samvil-interview.md`: full Brownfield Mode documentation
  — Phase 1B (brownfield goal), convergence with pre_filled_dimensions, merge chain.
- 17 new tests: 6 pre_filled_dimensions tests + 11 merge_brownfield_seed tests.

---

## v4.9.1 — 2026-04-28

**README update for deep interview engine (PATCH)**

- Comparison table: "최대 20개" → "깊이에 따라 10~40개+ (수렴 전까지 무제한)"
- Tier table: added "인터뷰 질문" column + "극한" (deep, 40개+) tier
- FAQ time estimate updated to 5~25분

---

## v4.9.0 — 2026-04-28

**Deep Interview Engine — 10-dimension scoring + min questions enforcement (MINOR)**

- `interview_engine.py` v2.5.0: scoring expanded from 3 → 10 dimensions
  - Core (60%): goal clarity, constraint clarity, criteria testability
  - Enriched (40%): technical specificity, failure modes depth, non-functional coverage,
    stakeholder specificity, scope boundary sharpness, success metrics quality, lifecycle awareness
- `MIN_QUESTIONS` per tier: minimal 5 / standard 10 / thorough 20 / full 30 / deep 40
  Convergence now requires threshold + floors + min questions — all three
- `score_ambiguity` MCP tool gains `questions_asked` parameter; returns `min_questions_met`,
  `min_questions_required`, and `dimension_scores` in result
- `skills/samvil-interview/SKILL.md`: removed "Cap 2 reprompts per phase" rule;
  convergence loop now runs until genuine convergence (no artificial stop)
- `references/codex-commands/samvil-interview.md`: full rewrite with 6 phases,
  min questions enforcement, and `dimension_scores`-guided loop — Codex CLI now
  matches Claude Code interview depth
- `references/interview-frameworks.md`: tier table updated with MIN_QUESTIONS values
- 28 new tests for 10-dimension engine + min questions logic

---

## v4.8.5 — 2026-04-28

**README "wow" factor: real conversation snippets + numbers (PATCH)**

- Add actual interview dialogue showing SAMVIL asking unexpected questions
- Add council debate snippet showing 5 AI agents reviewing design pre-code
- Upgrade comparison table with concrete numbers (20 questions, 5 reviewers,
  stub detection, 5 convergence criteria)

---

## v4.8.4 — 2026-04-28

**Claude Code + Codex CLI 동등 지원 명시 (PATCH)**

- README "시작하기" 섹션을 Claude Code / Codex CLI 두 섹션으로 분리
- Codex CLI를 `<details>` 밖으로 꺼내 첫 화면에 동등하게 노출
- 배지에 Codex CLI 추가
- FAQ 업데이트 / 비용 / 업데이트 항목에 Codex CLI 방법 병기

---

## v4.8.3 — 2026-04-28

**README pipeline diagram improvement (PATCH)**

- Highlight interview depth and council review as core differentiators
  in the pipeline diagram with inline annotations
- Add "다른 AI 도구와 뭐가 달라요?" comparison table showing interview,
  council, auto-recovery, and convergence criteria vs generic AI tools

---

## v4.8.0 — 2026-04-28

**Multi-host Onboarding (MINOR)**

- Add `AGENTS.md` — project-level instructions auto-read by Codex CLI and
  OpenCode. Covers chain marker flow, skill file table, key MCP tools,
  pipeline order, and critical rules (P1/P5/P8 citations).
- Add `scripts/setup-codex.sh` — one-command MCP setup for Codex CLI,
  OpenCode, and Gemini CLI. Installs Python venv, runs import smoke,
  prints host-specific MCP config snippets, and auto-applies to
  `~/.codex/config.toml` when Codex CLI config exists.
- Update `README.md` — new "Codex CLI / OpenCode / Gemini CLI" quick-start
  section with 4-step guide, per-host MCP config examples, and verification
  commands. Version badge updated to v4.8.0.

---

## v4.7.0 — 2026-04-27

**Option B: Regression Suite (MINOR)**

- Add `mcp/samvil_mcp/regression_suite.py` — 4 dataclasses (ACEntry,
  GenerationSnapshot, RegressionResult, CompareResult) + 4 functions:
  `snapshot_generation`, `validate_against_snapshot`,
  `aggregate_regression_state`, `compare_generations`
- Add 4 MCP tools: `snapshot_generation`, `validate_against_snapshot`,
  `aggregate_regression_state`, `compare_generations`
- Add `mcp/tests/test_regression_suite.py` — 32 tests across 6 classes
- Add `references/regression-suite.md` — schema doc + operator guide
- Update `skills/samvil-evolve/SKILL.md` — Boot step 4b: auto-snapshot +
  regression check; post-apply: snapshot new generation
- Storage: `.samvil/generations/gen-<N>/snapshot.json`
- Input: `.samvil/qa-results.json` pass2 list (seed v3 compatible, P8 graceful degradation)

Pre-commit: 9/9 PASS — 1523 tests total

---

## v4.6.1 — 2026-04-27

**Option A: E2E chain-marker dogfood (PATCH)**

- Add `mcp/tests/test_chain_marker_e2e.py` — 27 tests covering smoke script subprocess
  execution, marker schema compliance (schema_version/reason/from_stage), command file
  correctness for all 15 Codex + Gemini command files, phase2 cross-host smoke, and
  codex layer connectivity
- Add `scripts/check-host-command-files.py` — standalone validator for codex+gemini
  command reference files
- Fix `chain_markers.py`: `write_chain_marker()` now includes all required fields:
  `schema_version: "1.0"`, `reason`, `from_stage`
- Fix `references/codex-commands/`: added chain marker MCP tool references to
  `samvil-analyze.md`, `samvil-doctor.md`, `samvil-update.md`, `samvil-retro.md`

Pre-commit: 9/9 PASS — 1491 tests total

---

## v4.6.0 — Option D: 3-tier health UI + Enterprise BFF (2026-04-27)

### New
- **G4 (3-tier health UI)**: `samvil` Boot Sequence와 `samvil-doctor` 출력에 `✅/⚠️/🔴` health tier badge 추가. `get_health_tier_summary` MCP 툴 호출.
- **G5 (Enterprise BFF)**: `webapp-enterprise` domain pack `build_guidance`에 BFF 프록시 패턴, turborepo monorepo 구조, SSO 옵션(NextAuth/Clerk/Supabase Auth), OpenAPI client gen 4개 항목 추가.

### Tests
- `test_domain_packs.py`: BFF/monorepo/Clerk/openapi-typescript 회귀 테스트 4개.
- `test_health_tiers.py`: `get_health_tier_summary` 포맷(healthy/critical badge) 테스트 2개.

### Version bump reason: MINOR
사용자가 새 health badge(samvil 첫 화면, samvil-doctor 출력)와 새 build guidance를 보게 됨.

---

## [4.0.0] — 2026-04-27 — 🏔️ Consolidation Milestone (Tier 4 Phase C complete)

**Theme:** All 15 SAMVIL skills now ultra-thin. Single-source-of-truth aggregate MCP pattern proven across orchestrator, interview, scaffold, build (CRITICAL), and qa (CRITICAL).

### 🎯 Milestone

**14 actionable skills + samvil-pm-interview = 15 thin skills total, all ≤120 active LOC.**

This release completes the Consolidation phase that started at v3.32.0. The next phase (Mountain — M1-M4) recovers original promises (Module Boundary, multi-host real dogfood, domain packs, telemetry remote dashboard).

### Changed (skill migration — Phase C, the Hard 5)
- `samvil` (orchestrator): 766 → 93 LOC (-88%)
- `samvil-interview`: 1259 → 114 LOC (-91%)
- `samvil-scaffold`: 1653 → 120 LOC (-93%)
- `samvil-build` (CRITICAL): 1432 → 118 LOC (-92%) — 7 critical behaviors verified
- `samvil-qa` (CRITICAL): 1713 → 117 LOC (-93%) — 7 critical preservations verified
- Phase C total: 6,823 → 562 LOC (-92%)

### Added (MCP — 9 new aggregate tools)
- Orchestrator: `aggregate_orchestrator_state`
- Interview: `aggregate_interview_state`
- Scaffold: `evaluate_scaffold_target`
- Build: `aggregate_build_phase_a` + `dispatch_build_batch` + `finalize_build_phase_z`
- QA: `aggregate_qa_boot_context` + `dispatch_qa_pass1_batch` + `finalize_qa_verdict`

### Added (tests — 265 new smoke tests in Phase C)
- 31 samvil orchestrator + 42 interview + 36 scaffold + 109 build + 47 qa

### Counts (vs v3.36.0)
- MCP tools: 145 → **154** (+9)
- Tests: 1064 → **1314** (+250)
- Thin skills: 10 → **15** (+5 — Phase C)

### Cumulative Consolidation (v3.32.0 → v4.0.0)

- MCP tools: 175 → 154 (-21, -12%)
- Tests: 946 → 1314 (+368, +39%)
- Thin skills: 2 → 15 (+13)
- All 15 skills ≤ 120 active LOC
- 6 Releases: v3.33 (Tier 1) / v3.34 (Tier 2) / v3.35 (Phase A) / v3.36 (Phase B) / v4.0.0 (Phase C — this)

### Patterns proven across all 15 skills

1. **Single-source-of-truth aggregate MCP** — flat branching/policy logic into one MCP module per skill (10 aggregate tools added across Tier 3+4)
2. **SKILL.legacy.md backup** with frontmatter rename (`<skill>-legacy`) — host loader doesn't see, manual rollback always available
3. **Smoke tests pin behavior contracts** — not implementation; idempotency, edge cases, INV-5 graceful degradation
4. **CC-specific stays in skill** — Agent() parallel spawn, Bash, AskUserQuestion, TaskUpdate
5. **MCP gates for orchestration** — boot context, batch dispatch, finalize, persistence

### Foundation now ready for Mountain Stage

Consolidation phase done. Next is Mountain (M1-M4):
- **M1 Module Boundary** — `contract.json` system, big-app capability
- **M2 Multi-host real dogfood** — Codex/OpenCode E2E + Gemini adapter
- **M3 Domain Pack depth** — game-phaser + webapp-enterprise
- **M4 Telemetry remote + 3-tier health UI**

Target: v4.6.0 (Mountain complete = original Phase 2-4 promises 100% fulfilled).

### Backlog (deferred to maintenance)
- GitHub Actions Node.js 20 deprecation (June 2026)
- Flaky `test_periodic_checkpointer` (timing-sensitive)

---

## [3.36.0] — 2026-04-26 — Tier 4 Phase B: Medium Skills Ultra-Thin

**Theme:** All 4 Medium skills (retro/evolve/council/analyze) migrated to ultra-thin shells. Single-source-of-truth aggregate MCP tools pattern proven across post-processing, autonomous loops, parallel agents, and brownfield analysis.

### Changed (skill migration)
- `samvil-retro`: 506 → 117 LOC (-77%)
- `samvil-evolve`: 482 → 91 LOC (-81%)
- `samvil-council`: 554 → 107 LOC (-81%) — parallel Agent() calls preserved in skill, before/after logic in MCP
- `samvil-analyze`: 677 → 80 LOC (-88%) — heaviest reverse-engineering moved to MCP
- Phase B total: 2,219 → 395 LOC (-82%, target was -69%)
- Each skill preserves SKILL.legacy.md (frontmatter renamed to avoid loader collision)

### Added (MCP — aggregate pattern)
- `aggregate_retro_metrics(project_root, plugin_root, suggestion_major)` — single source of truth for retro metric aggregation, recurring-pattern detection, suggestion ID increment
- `aggregate_evolve_context(project_root)` — boot-time aggregator for auto-trigger detection, mode resolution, cycle counter, 4-dim baseline
- `synthesize_council_verdicts(round1_verdicts_json, round2_verdicts_json)` — Round 1 → debate-point extraction + Round 2 prompt assembly + final consensus/dissent/blocking aggregation
- `analyze_brownfield_project(project_root)` — reverse-seed generation from existing code (framework detection / module discovery / feature inference / confidence tagging / ADR-EXISTING suggestions)

### Added (tests)
- 85 new smoke tests (16 retro + 19 evolve + 22 council + 28 analyze) pinning behavior contracts

### Behavior changes (intentional)
- **samvil-analyze framework precedence**: Phaser/Expo deps now win over Vite/Astro config files (was: legacy false-positive `framework: react` for Phaser-on-Vite). Re-analyzing brownfield projects may produce a different `framework` value if they're games. Intentional fix per v3.1.0 universal builder design.

### Counts
- MCP tools: 141 → **145** (+4)
- Tests: 979 → **1064** (+85)
- 10 thin skills total (Phase A 6 + Phase B 4) — all ≤120 LOC active

### Limitations (deferred)
- `samvil-analyze` feature inference assumes `src/` layout. Next.js App Router projects with `app/`-only layouts produce empty features + warning. Future patch can extend `discover_modules`.

### Next
Tier 4 Phase C — Hard 5 skills migration (samvil / interview / build / scaffold / qa). Most complex tier. Target eventual v4.0.0 (consolidation milestone).

---

## [3.35.0] — 2026-04-26 — Tier 3 Phase A: Easy Skills Ultra-Thin

**Theme:** Migrate Easy 4 skills (doctor/pm-interview/update/deploy) to ultra-thin shells with single-source-of-truth MCP tools.

### Changed (skill migration)
- `samvil-doctor`: 178 → 87 LOC (-51%)
- `samvil-pm-interview`: 117 → 94 LOC (-20%)
- `samvil-update`: 285 → 120 LOC (-58%)
- `samvil-deploy`: 379 → 99 LOC (-74%)
- Phase A total: 959 → 400 LOC (-58%)
- Each skill preserves SKILL.legacy.md for rollback (frontmatter renamed to avoid name collision)

### Added (MCP)
- `diagnose_environment(project_root)` — single-source-of-truth diagnostic for samvil-doctor (mcp_health, tool_inventory, model_recommendation)
- `evaluate_deploy_target(project_root, platform)` — single-source-of-truth for samvil-deploy (5 solution_types × 4-5 platforms catalog, QA gate, env validation)

### Added (tests)
- 41 new smoke tests pinning behavioral contracts (9 doctor + 8 pm-interview + 7 update + 17 deploy)

### Counts
- MCP tools: 139 → **141** (+2)
- Tests: 938 → **979** (+41)
- 6 thin skills total: samvil-seed (91), samvil-design (116), samvil-doctor (87), samvil-pm-interview (94), samvil-update (120), samvil-deploy (99) — all ≤120 LOC

### Next
Tier 4 — Phase B+C: Medium 4 + Hard 5 skills migration. Target v3.36.0+ → eventual v4.0.0.

---

## [3.34.0] — 2026-04-26 — Consolidation Tier 2

**Theme:** WARM cleanup, module consolidation, doc/CI hygiene.

### Removed
- 7 unused @mcp.tool() registrations (inspection/repair/evolve dead surface)
- evolve_proposal.py + evolve_apply.py (merged into evolve_execution.py)
- release_publish.py + remote_release.py (merged into release_guards.py)

### Internalized (kept as Python helpers, no MCP exposure)
- 9 inspection/repair/release/evolve helpers

### Changed
- Schema docs: 4 individual schemas → 1 unified `references/samvil-ssot-schema.md` (+ 4 redirect stubs)
- CLAUDE.md: 705 → 457 lines (legacy v0.x~v3.2 versions → docs/CHANGELOG-legacy.md; numeric thresholds → references/decision-boundaries.md)
- Pre-push hook: tag-only pushes no longer trigger version check (was a bug requiring --no-verify on every tag push)

### Added
- scripts/check-broken-references.sh — verifies all .md cross-links resolve
- pre-commit section 9: "Markdown reference integrity" (90 files scanned)

### Counts
- MCP tools: 155 → **139** (-16)
- Modules: 60 → **57** (-3)
- Tests: 946 → **938** (-8 MCP wrapper tests removed; behavior coverage preserved)

### Next
Tier 3 — Phase A skill migration (4 Easy skills → ultra-thin). Target v3.35-v3.38.

---

## [3.33.0] — 2026-04-25 — Consolidation Tier 1

First milestone of the Consolidation phase. Reduces v3.32.0 noise (49%
dead/disconnected baseline) without behavior change. PATCH-only discipline
holds inside consolidation; the MINOR bump reflects user-visible tool
count drop (175 → 155) per the versioning policy.

### Added
- `mcp/tests/test_post_rebuild_qa.py` regression guard for missing
  scaffold-input contract (T1.1, defense-in-depth — bug already fixed in
  `e4f93b1`).

### Changed
- Merged `regression_detector` + `convergence_gate` modules into
  `convergence_check` (T1.3). Module count 60 → 59. Public surface
  preserved through re-exports.

### Removed
- 20 confirmed-COLD MCP tools (T1.2). Tool count 175 → 155 (-12%).
  No skill or test reference remained for the removed tools.

### Verified
- Full test suite: 946 passed (unchanged from v3.32.0).
- MCP server import smoke: 155 tools.
- `bash scripts/pre-commit-check.sh`: PASS.
- LOC delta: net negative (server.py -426 lines; merged module is
  smaller than the two it replaces).

### Next
- Tier 2 — WARM analysis + 2 module merges + docs slim. Target
  v3.34-v3.36.

---

## [3.32.0] — 2026-04-26 — Final E2E Bundle

Phase 30 of the multi-host SAMVIL architecture. This release adds the final
whole-chain bundle that verifies blocked QA -> evolve -> rebuild -> reentry ->
post-rebuild QA -> cycle closure from project-local artifacts and seed hashes.

### Added
- `mcp/samvil_mcp/final_e2e.py` for deterministic whole-chain E2E bundle
  generation.
- `.samvil/final-e2e-bundle.json` materialization.
- MCP `build_final_e2e_bundle` and `materialize_final_e2e_bundle`.
- Run-report `final_e2e` summary.
- `samvil-status` human/JSON output for final E2E status and issue count.
- `scripts/phase30-final-e2e-bundle-dogfood.py` proving the full Phase 23-29
  chain produces a passing final E2E bundle.
- Phase 30 dogfood as the first default release runner check.
- Phase 30 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.32-phase30.md`.

### Changed
- Release readiness defaults now require Phase 30 before Phase 29 and earlier
  recovery/evolve gates.

### Verified
- Phase 30 dogfood: PASS.
- Final E2E, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 945 passed.
- MCP server import smoke: 175 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.31.0] — 2026-04-26 — Evolve Cycle Closure

Phase 29 of the multi-host SAMVIL architecture. This release records the
post-rebuild QA outcome as an explicit cycle closure verdict so the harness can
close, continue, or stop the evolve loop without relying on conversation state.

### Added
- `mcp/samvil_mcp/evolve_cycle.py` for deterministic evolve cycle closure.
- `.samvil/evolve-cycle.json` materialization.
- MCP `build_evolve_cycle_closure` and `materialize_evolve_cycle_closure`.
- Run-report `evolve_cycle` summary.
- `samvil-status` human/JSON output for cycle verdict, current QA verdict, and
  next skill.
- `scripts/phase29-evolve-cycle-closure-dogfood.py` proving post-rebuild QA
  PASS closes the cycle and routes to `samvil-retro`.
- Phase 29 dogfood as the first default release runner check.
- Phase 29 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.31-phase29.md`.

### Changed
- Release readiness defaults now require Phase 29 before Phase 28 and earlier
  recovery/evolve gates.

### Verified
- Phase 29 dogfood: PASS.
- Evolve cycle, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 938 passed.
- MCP server import smoke: 173 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.30.0] — 2026-04-26 — Post-Rebuild QA Rejudge

Phase 28 of the multi-host SAMVIL architecture. This release materializes the
QA rejudge request after rebuilt scaffold output exists, pinning the evolved
seed hash and prior QA issues before routing back to `samvil-qa`.

### Added
- `mcp/samvil_mcp/post_rebuild_qa.py` for deterministic post-rebuild QA
  request generation.
- `.samvil/post-rebuild-qa.json` materialization.
- `.samvil/scaffold-output.json` contract checks for rebuilt seed version and
  sha256.
- MCP `build_post_rebuild_qa` and `materialize_post_rebuild_qa`.
- Run-report `post_rebuild_qa` summary.
- `samvil-status` human/JSON output for post-rebuild QA readiness and previous
  QA issue count.
- `scripts/phase28-post-rebuild-qa-dogfood.py` proving QA blocked -> evolve
  context -> proposal -> apply -> rebuild -> reentry -> scaffold output -> QA
  rejudge.
- Phase 28 dogfood as the first default release runner check.
- Phase 28 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.30-phase28.md`.

### Changed
- Release readiness defaults now require Phase 28 before Phase 27 and earlier
  recovery/evolve gates.

### Verified
- Phase 28 dogfood: PASS.
- Post-rebuild QA, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 931 passed.
- MCP server import smoke: 171 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.29.0] — 2026-04-26 — Rebuild Reentry Contract

Phase 27 of the multi-host SAMVIL architecture. This release turns the rebuild
handoff into an explicit scaffold reentry input so the next host can continue
from the evolved seed without reconstructing path, version, or hash from chat
history.

### Added
- `mcp/samvil_mcp/evolve_reentry.py` for deterministic rebuild reentry
  generation.
- `.samvil/rebuild-reentry.json` materialization.
- `.samvil/scaffold-input.json` scaffold input when reentry is ready.
- MCP `build_rebuild_reentry` and `materialize_rebuild_reentry`.
- Run-report `rebuild_reentry` summary.
- `samvil-status` human/JSON output for rebuild reentry readiness and scaffold
  input path.
- `scripts/phase27-rebuild-reentry-dogfood.py` proving QA blocked -> evolve
  context -> proposal -> apply -> rebuild -> scaffold reentry.
- Phase 27 dogfood as the first default release runner check.
- Phase 27 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.29-phase27.md`.

### Changed
- Release readiness defaults now require Phase 27 before Phase 26 and earlier
  recovery/evolve gates.

### Verified
- Phase 27 dogfood: PASS.
- Rebuild reentry, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 924 passed.
- MCP server import smoke: 169 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.28.0] — 2026-04-26 — Evolve Rebuild Handoff

Phase 26 of the multi-host SAMVIL architecture. This release materializes the
portable continuation marker after an evolved seed is applied so the next host
can rebuild from the updated seed.

### Added
- `mcp/samvil_mcp/evolve_rebuild.py` for applied-seed rebuild handoff
  generation.
- `.samvil/evolve-rebuild.json` materialization.
- `.samvil/next-skill.json` rewrite to `samvil-scaffold` after a successful
  evolve apply.
- MCP `build_evolve_rebuild_handoff` and
  `materialize_evolve_rebuild_handoff`.
- Run-report `evolve_rebuild` summary.
- `samvil-status` human/JSON output for rebuild handoff status and next skill.
- `scripts/phase26-evolve-rebuild-dogfood.py` proving the full QA route ->
  context -> proposal -> apply -> rebuild marker path.
- Phase 26 dogfood as the first default release runner check.
- Phase 26 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.28-phase26.md`.

### Changed
- `skills/samvil-evolve/SKILL.md` now materializes the rebuild handoff after a
  successful guarded apply.
- Release readiness defaults now require Phase 26 before Phase 25 and earlier
  recovery/evolve gates.

### Verified
- Phase 26 dogfood: PASS.
- Evolve rebuild, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 917 passed.
- MCP server import smoke: 167 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.27.0] — 2026-04-26 — Evolve Apply Plan

Phase 25 of the multi-host SAMVIL architecture. This release turns reviewed
evolve proposals into guarded seed patch previews and applies them only when
the current seed still matches the plan hash.

### Added
- `mcp/samvil_mcp/evolve_apply.py` for deterministic evolve apply plan
  generation and guarded application.
- `.samvil/evolve-apply-plan.json`, `.samvil/evolved-seed.preview.json`, and
  `.samvil/evolve-apply-report.md` materialization.
- MCP `build_evolve_apply_plan`, `materialize_evolve_apply_plan`, and
  `apply_evolve_apply_plan`.
- Hash-gated `project.seed.json` updates with `seed_history/vN.json` backup and
  `seed_history/vN_vN+1_diff.md` diff output.
- Run-report `evolve_apply` summary.
- `samvil-status` human/JSON output for apply status, version target, mutation
  count, and next action.
- `scripts/phase25-evolve-apply-dogfood.py` proving a blocked Pass 2 QA route
  can produce, preview, and apply a safe evolved seed.
- Phase 25 dogfood as the first default release runner check.
- Phase 25 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.27-phase25.md`.

### Changed
- `skills/samvil-evolve/SKILL.md` now prefers guarded apply plans over manual
  `project.seed.json` edits when a ready proposal exists.
- Release readiness defaults now require Phase 25 before Phase 24 and earlier
  recovery/QA gates.

### Verified
- Phase 25 dogfood: PASS.
- Evolve apply, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 910 passed.
- MCP server import smoke: 165 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.26.0] — 2026-04-26 — Evolve Proposal Materialization

Phase 24 of the multi-host SAMVIL architecture. This release turns
file-based evolve context into reviewable proposal artifacts before any seed
file is modified.

### Added
- `mcp/samvil_mcp/evolve_proposal.py` for deterministic evolve proposal
  construction from `.samvil/evolve-context.json`.
- `.samvil/evolve-proposal.json` and `.samvil/evolve-proposal.md`
  materialization.
- MCP `build_evolve_proposal` and `materialize_evolve_proposal`.
- Run-report `evolve_proposal` summary.
- `samvil-status` human/JSON output for proposal status, change count, and
  next action.
- `scripts/phase24-evolve-proposal-dogfood.py` proving blocked Pass 2 QA
  becomes a ready proposal without modifying `project.seed.json`.
- Phase 24 dogfood as the first default release runner check.
- Phase 24 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.26-phase24.md`.

### Changed
- `skills/samvil-evolve/SKILL.md` now materializes and reviews the evolve
  proposal before editing the seed.
- Release readiness defaults now require Phase 24 before earlier recovery and
  QA gates.

### Verified
- Phase 24 dogfood: PASS.
- Evolve proposal, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 903 passed.
- MCP server import smoke: 162 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.25.0] — 2026-04-26 — Evolve Intake Context

Phase 23 of the multi-host SAMVIL architecture. This release turns a blocked
QA recovery route into a file-based evolve context that `samvil-evolve` can
consume without relying on conversation history or session database state.

### Added
- File-based evolve context builder in `mcp/samvil_mcp/evolve_loop.py`.
- `.samvil/evolve-context.json` materialization with current seed, state,
  QA synthesis, convergence, route, ground-truth artifact paths, and seed
  history summary.
- MCP `build_evolve_context` and `materialize_evolve_context`.
- Run-report `evolve_context` summary.
- `samvil-status` human/JSON output for evolve focus and issue count.
- `scripts/phase23-evolve-intake-context-dogfood.py` proving blocked Pass 2 QA
  routed to evolve becomes a focused evolve context.
- Phase 23 dogfood as the first default release runner check.
- Phase 23 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.25-phase23.md`.

### Changed
- `skills/samvil-evolve/SKILL.md` now prefers `.samvil/evolve-context.json`
  and can materialize it from project artifacts when missing.

### Verified
- Phase 23 dogfood: PASS.
- Evolve context, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 897 passed.
- MCP server import smoke: 160 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.24.0] — 2026-04-26 — QA Recovery Routing

Phase 22 of the multi-host SAMVIL architecture. This release converts blocked
QA convergence into a deterministic recovery route and portable continuation
marker.

### Added
- `mcp/samvil_mcp/qa_routing.py` for deterministic blocked-QA routing.
- `.samvil/qa-routing.json` materialization with primary and alternative
  recovery routes.
- `.samvil/next-skill.json` materialization from blocked QA recovery routing.
- MCP `build_qa_recovery_routing` and `materialize_qa_recovery_routing`.
- Run-report `qa_routing` summary and route-prioritized next action.
- `samvil-status` human/JSON output for QA recovery routes.
- `scripts/phase22-qa-recovery-routing-dogfood.py`, including
  `host-continuation-smoke.py` validation for the generated marker.
- Phase 22 dogfood as the first default release runner check.
- Phase 22 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.24-phase22.md`.

### Changed
- Blocked Pass 2 functional QA now routes primarily to `samvil-evolve`.
- Blocked mechanical or quality-only QA routes primarily to `samvil-build`.
- Ownership/process violations route primarily to `samvil-retro`.
- `skills/samvil-qa/SKILL.md` now calls QA recovery routing when convergence is
  blocked or failed.

### Verified
- Phase 22 dogfood: PASS.
- QA routing, status, telemetry, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 892 passed.
- MCP server import smoke: 158 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.23.0] — 2026-04-26 — QA Convergence Gate

Phase 21 of the multi-host SAMVIL architecture. This release turns repeated QA
revise loops into a deterministic convergence gate so SAMVIL can stop blind
auto-fix attempts when the same issues keep returning.

### Added
- `evaluate_qa_convergence` in `mcp/samvil_mcp/qa_synthesis.py` to compare
  current QA synthesis issue IDs against `project.state.json.qa_history`.
- Stable QA `issue_ids` from mechanical, functional, quality, and protected
  write findings.
- `qa_convergence` gate materialization inside `.samvil/qa-results.json`.
- `last_qa_convergence` and convergence metadata in `qa_history`.
- `qa_blocked` / `qa_failed` event drafts when convergence blocks or exhausts.
- MCP `evaluate_qa_convergence` smoke coverage.
- `scripts/phase21-qa-convergence-gate-dogfood.py` proving repeated issues
  become blocked and status/run-report recommend manual intervention.
- Phase 21 dogfood as the first default release runner check.
- Phase 21 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.23-phase21.md`.

### Changed
- `materialize_qa_synthesis` now embeds convergence gate output in persisted
  QA results and state history.
- `build_run_report` and `samvil-status` prioritize blocked/failed QA
  convergence before ordinary `REVISE` next actions.
- `skills/samvil-qa/SKILL.md` now treats blocked convergence as a stop signal
  for the Ralph loop.

### Verified
- Phase 21 dogfood: PASS.
- QA convergence, status, release, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 885 passed.
- MCP server import smoke: 156 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.22.0] — 2026-04-26 — QA Materialization

Phase 20 of the multi-host SAMVIL architecture. This release persists the
central QA synthesis verdict into durable run artifacts and exposes it through
telemetry and `samvil-status`.

### Added
- `materialize_qa_synthesis` in `mcp/samvil_mcp/qa_synthesis.py` to write
  `.samvil/qa-results.json`, `.samvil/qa-report.md`, `.samvil/events.jsonl`,
  and `project.state.json.qa_history`.
- MCP `materialize_qa_synthesis` for the QA skill to persist central synthesis
  output after independent evidence is judged.
- QA summary integration in `build_run_report`.
- QA panel and JSON fields in `scripts/samvil-status.py`.
- `scripts/phase20-qa-materialization-dogfood.py` to prove report, results,
  events, state, run report, and status stay aligned.
- Phase 20 dogfood as a default release runner check before Phase 19/18 and
  full pre-commit.
- Phase 20 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.22-phase20.md`.

### Changed
- `skills/samvil-qa/SKILL.md` now calls `materialize_qa_synthesis` after
  `synthesize_qa_evidence` and continues from the materialized verdict.
- `samvil-status` prioritizes `REVISE` and `FAIL` QA next actions when no
  repair or release gate is blocking.

### Verified
- Phase 20 dogfood: PASS.
- QA materialization, status, telemetry, and MCP smoke tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 879 passed.
- MCP server import smoke: 155 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.21.0] — 2026-04-26 — QA Synthesis Gate

Phase 19 of the multi-host SAMVIL architecture. This release turns independent
QA evidence into a deterministic central `PASS` / `REVISE` / `FAIL` synthesis
owned by the main session.

### Added
- `mcp/samvil_mcp/qa_synthesis.py` for central QA synthesis from Pass 1,
  independent Pass 2, and independent Pass 3 evidence.
- MCP `synthesize_qa_evidence` for the QA skill to call after independent
  agents return evidence.
- `scripts/phase19-qa-synthesis-gate-dogfood.py` with pass, revise, fail,
  quality-only revise, and protected-write scenarios.
- `QA_FUNCTIONAL_JSON` and `QA_QUALITY_JSON` output contracts for independent
  QA agents.
- Phase 19 dogfood as a default release runner check before Phase 18 and full
  pre-commit.
- Phase 19 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.21-phase19.md`.

### Changed
- `skills/samvil-qa/SKILL.md` now routes standard+ independent QA evidence
  through `synthesize_qa_evidence` and treats that result as the central source
  of truth.
- Default release checks now include Phase 19, Phase 18, Phase 12/11/10/8, and
  full pre-commit.

### Verified
- Phase 19 dogfood: PASS.
- QA synthesis and MCP tool tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 875 passed.
- MCP server import smoke: 154 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.20.0] — 2026-04-26 — Independent Evidence Contract

Phase 18 of the multi-host SAMVIL architecture. This release locks the
Independent Evidence, Central Verdict principle into an executable contract so
future skill, agent, and checklist edits cannot silently drift from the intended
design/build/QA/evolve pipeline.

### Added
- `scripts/phase18-independent-evidence-dogfood.py` to validate blueprint
  feasibility ordering, structured build event emission, QA taxonomy alignment,
  independent QA ownership, and evolve context inputs.
- `mcp/tests/test_phase18_independent_evidence_dogfood.py` regression coverage.
- Phase 18 dogfood as a default release runner check before full pre-commit.
- Phase 18 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.20-phase18.md`.

### Changed
- `agents/qa-functional.md` now states that `PARTIAL` remains passable evidence
  with a count, while `UNIMPLEMENTED` and `FAIL` drive revise/fail outcomes.
- `agents/qa-quality.md` now explicitly reports stubs or missing core behavior
  as quality concerns without reclassifying Pass 2 functional states.

### Verified
- Phase 18 dogfood: PASS.
- Phase 18 pytest: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 867 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.19.1] — 2026-04-26 — Verified Publisher Fixture Patch

Patch release for Phase 17. The first v3.19.0 publisher run correctly blocked
tag publication when remote CI exposed that fixture dry-run tests still depended
on local `.samvil/release-report.json` state.

### Fixed
- `scripts/publish-verified-release.py` now uses an explicit passing local gate
  stub when `--skip-local-release-checks` is set.
- Publisher fixture tests no longer depend on machine-local or CI-local
  `.samvil/release-report.json` state.

### Verified
- Publisher fixture tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 866 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.19.0] — 2026-04-26 — Verified Release Publisher

Phase 17 of the multi-host SAMVIL architecture. This release turns the remote
release gate into a guarded publish workflow that pushes the release branch,
waits for GitHub Actions, verifies artifact evidence, and only then publishes
the release tag.

### Added
- `mcp/samvil_mcp/release_publish.py` for deterministic publish guard
  evaluation and rendering.
- `scripts/publish-verified-release.py` for verified branch push, Actions wait,
  remote artifact gate check, and tag push.
- Publish guard inputs for clean tree, version sync, local/remote tag
  existence, local release gate, remote release gate, branch, and HEAD.
- Dry-run fixture mode for deterministic pass/fail publisher testing.
- Unit and CLI tests for pass, dirty tree, existing tag, and blocked remote
  gate cases.
- Phase 17 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.19-phase17.md`.

### Dogfood
- Publish guard unit tests passed.
- Publisher dry-run fixture pass/fail tests passed.
- Default release runner executed Phase 12/11/10/8 and full pre-commit with all
  five checks passing.

### Verified
- Publisher fixture tests: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 866 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.18.0] — 2026-04-26 — Remote Release Gate

Phase 16 of the multi-host SAMVIL architecture. This release makes remote CI
evidence a deterministic gate by validating both the GitHub Actions run and
the uploaded `samvil-release-evidence` runner artifact.

### Added
- `mcp/samvil_mcp/remote_release.py` for remote release gate evaluation and
  markdown rendering.
- `scripts/check-remote-release-gate.py` for live `gh` checks and deterministic
  fixture mode.
- Remote gate validation for run status/conclusion, expected HEAD, artifact
  release report status, artifact gate verdict, and failed/missing checks.
- Pass/fail remote run and runner artifact fixtures under `mcp/tests/fixtures/`.
- Unit and CLI regression tests for pass, failed run, blocked artifact, and head
  mismatch cases.
- Phase 16 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.18-phase16.md`.

### Dogfood
- Fixture remote gate tests passed.
- Live remote gate passed against the latest successful main run
  `24948976774` for HEAD `60803ed`.
- Default release runner executed Phase 12/11/10/8 and full pre-commit with all
  five checks passing.

### Verified
- Remote gate fixture tests: PASS.
- Live remote release gate: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 858 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.17.3] — 2026-04-26 — External CI Mirror Fixture Patch

Patch release for Phase 15. The v3.17.2 remote run exposed that retro schema
tests depended on ignored machine-local `harness-feedback.log` state.

### Fixed
- Add committed fixture `mcp/tests/fixtures/harness-feedback.json`.
- Point retro schema tests at the fixture instead of ignored local
  `harness-feedback.log`.

### Verified
- CI workflow validator: PASS.
- Focused workflow pytest: 2 passed.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 851 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.17.2] — 2026-04-26 — External CI Mirror Test Runtime

Patch release for Phase 15. The v3.17.1 remote run correctly failed on blocked
release evidence, then exposed that the CI venv did not install pytest for the
pre-commit full-suite step.

### Fixed
- Install `pytest` and `pytest-asyncio` into `mcp/.venv` during GitHub Actions
  setup so `bash scripts/pre-commit-check.sh` can run the full suite remotely.
- Extend workflow validator and pytest contract coverage for the CI pytest
  runtime install.

### Verified
- CI workflow validator: PASS.
- Focused workflow pytest: 2 passed.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 851 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.17.1] — 2026-04-26 — External CI Mirror Patch

Patch release for Phase 15. The first remote run proved that artifact evidence
could report `blocked` while the Actions job stayed green because the runner
command was piped through `tee`.

### Fixed
- Install the exact Playwright browser runtime used by Phase 8 fixtures:
  `playwright@1.52.0 install --with-deps chromium`.
- Add `set -o pipefail` to release runner and bundle builder workflow steps so
  command failures propagate to the GitHub Actions job.
- Extend workflow validator and pytest contract coverage for the Playwright
  runtime install and pipefail guard.

### Verified
- CI workflow validator: PASS.
- Focused workflow pytest: 2 passed.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Full test suite: 851 passed.
- MCP server import smoke: 153 tools.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.17.0] — 2026-04-26 — External CI Mirror

Phase 15 of the multi-host SAMVIL architecture. This release mirrors the local
release runner in GitHub Actions and publishes the same release evidence bundle
as CI artifacts for PR/main review.

### Added
- GitHub Actions workflow at `.github/workflows/release-checks.yml`.
- CI setup for Python 3.12, Node 20, MCP package install, and Chromium system
  dependencies for the browser inspection regression.
- CI execution of `scripts/run-release-checks.py --format json`.
- CI execution of `scripts/build-release-bundle.py --format json`.
- `samvil-release-evidence` artifact upload containing release report,
  markdown summary, runner JSON, and bundle JSON.
- `scripts/validate-ci-workflow.py` for local workflow contract validation.
- Pytest coverage for the workflow contract and validator script.
- Phase 15 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.17-phase15.md`.

### Dogfood
- Local workflow validator passed against the GitHub Actions YAML.
- Focused workflow pytest passed.
- Default release runner executed Phase 12/11/10/8 and full pre-commit with all
  five checks passing.
- Release evidence bundle generated from the default runner output.

### Verified
- CI workflow validator: PASS.
- Focused workflow pytest: 2 passed.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Phase 12/11/10/8 regressions: PASS.
- Full test suite: 851 passed.
- MCP server import smoke: 153 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.16.0] — 2026-04-26 — Release Evidence Bundle

Phase 14 of the multi-host SAMVIL architecture. This release turns the
runner-generated release report into a one-file markdown evidence bundle for
review, continuation, and release audit.

### Added
- Release evidence bundle builder in `mcp/samvil_mcp/release.py`.
- Release bundle artifact: `.samvil/release-summary.md`.
- `scripts/build-release-bundle.py` CLI for building the bundle from the
  latest `.samvil/release-report.json`.
- MCP tools: `build_release_evidence_bundle`,
  `read_release_evidence_bundle`, and `render_release_evidence_bundle`.
- Bundle metadata for release gate verdict, report summary, git branch/head,
  tags at HEAD, dirty state, and version sync.
- Check-level bundle rows with command, exit code, duration, message, and
  stdout/stderr tails for failed checks.
- `samvil-status.py` bundle path output in both human and JSON modes.
- `scripts/phase14-release-evidence-bundle-dogfood.py`, covering all-pass and
  failed-output bundle states.
- Phase 14 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.16-phase14.md`.

### Dogfood
- `bundle-all-pass`: runner report pass, release gate pass, bundle path exposed
  in status.
- `bundle-failed-output`: runner report blocked, release gate blocked, failed
  stderr tail appears in the markdown bundle.
- Default release runner generated a pass report, then
  `scripts/build-release-bundle.py` generated `.samvil/release-summary.md`.

### Verified
- Phase 14 release evidence bundle dogfood: PASS.
- Phase 13 release check runner regression: PASS.
- Default release check runner: PASS.
- Release evidence bundle generation from default runner output: PASS.
- Phase 12/11/10/8 regressions: PASS.
- Full test suite: 849 passed.
- MCP server import smoke: 153 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.15.0] — 2026-04-26 — Release Check Runner

Phase 13 of the multi-host SAMVIL architecture. This release makes release
readiness evidence executable by adding a runner that executes release check
commands and writes the release report directly.

### Added
- Default release check command set for Phase 12 release readiness, Phase 11
  repair orchestration, Phase 10 repair regression, Phase 8 browser inspection,
  and full pre-commit.
- `run_release_checks` in `mcp/samvil_mcp/release.py`, capturing exit code,
  duration, stdout/stderr tails, timeout status, and evidence rows.
- `scripts/run-release-checks.py` CLI for generating
  `.samvil/release-report.json` from actual command execution.
- MCP tool `run_release_checks` for host/skill access to the same runner.
- Runner source and execution evidence in rendered release reports and
  `samvil-status.py`.
- `scripts/phase13-release-check-runner-dogfood.py`, covering all-pass,
  command-failed, and timeout runner states.
- Phase 13 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.15-phase13.md`.

### Dogfood
- `runner-all-pass`: gate=pass, next_action=`ready to tag release`.
- `runner-command-failed`: gate=blocked, next_action=`fix release check: runner_fail`.
- `runner-command-timeout`: gate=blocked, next_action=`fix release check: runner_timeout`.
- Default runner executed Phase 12/11/10/8 and full pre-commit with all five
  checks passing.

### Verified
- Phase 13 release check runner dogfood: PASS.
- Default release check runner: PASS.
- Phase 12 release readiness regression: PASS.
- Phase 11 repair orchestration regression: PASS.
- Phase 10 inspection repair regression: PASS.
- Phase 8 real browser inspection regression: PASS.
- Full test suite: 845 passed.
- MCP server import smoke: 150 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.14.0] — 2026-04-26 — Release Readiness Gate

Phase 12 of the multi-host SAMVIL architecture. This release makes final
release readiness deterministic by adding a release report and release gate
after the repair orchestration gate.

### Added
- `mcp/samvil_mcp/release.py` for deterministic release report generation,
  reading, persistence, markdown rendering, and release gate evaluation.
- Release artifact: `.samvil/release-report.json`.
- Release MCP tools: `build_release_report`, `read_release_report`,
  `render_release_report`, and `evaluate_release_gate`.
- Run report release summary and release gate fields under
  `.samvil/run-report.json`.
- `samvil-status.py` release summary and release gate output in both human and
  JSON modes.
- `scripts/phase12-release-readiness-dogfood.py`, covering repair-blocked,
  release-check-failed, and release-ready states.
- Phase 12 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.14-phase12.md`.

### Dogfood
- `release-repair-blocked`: gate=blocked, reason=`repair gate is blocked`.
- `release-check-failed`: gate=blocked, next_action=`fix release check: pre_commit`.
- `release-ready`: gate=pass, next_action=`ready to tag release`.

### Verified
- Phase 12 release readiness dogfood: PASS.
- Phase 11 repair orchestration regression: PASS.
- Phase 10 inspection repair regression: PASS.
- Phase 8 real browser inspection regression: PASS.
- Targeted release/status/telemetry/MCP tests: 27 passed.
- Full test suite: 840 passed.
- MCP server import smoke: 149 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.13.0] — 2026-04-26 — Repair Orchestration Gate

Phase 11 of the multi-host SAMVIL architecture. This release makes repair
state part of deterministic progression by adding a repair gate that blocks
unverified repair and passes verified repair into release checks.

### Added
- Deterministic repair gate evaluation with `pass`, `blocked`, and
  `not-applicable` verdicts.
- Run report repair summary and repair gate fields under
  `.samvil/run-report.json`.
- Status output for repair gate verdict, reason, and next action in both human
  and JSON modes.
- Repair lifecycle event classification for repair start, plan generation,
  application, verification, and failure events.
- Repeated repair type policy signal candidates via
  `derive_repair_policy_signals`.
- MCP tools: `evaluate_repair_gate` and `derive_repair_policy_signals`.
- `scripts/phase11-repair-orchestration-dogfood.py`, covering blocked missing
  plan, blocked unverified plan, and pass verified repair states.
- Phase 11 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.13-phase11.md`.

### Dogfood
- `repair-gate-missing-plan`: gate=blocked, next_action=`build repair plan`.
- `repair-gate-plan-only`: gate=blocked, next_action=repair plan action.
- `repair-gate-verified`: gate=pass, next_action=`continue to release checks`.
- Repeated `console-error` repair reports produce
  `repair-policy:console-error`.

### Verified
- Phase 11 repair orchestration dogfood: PASS.
- Phase 10 inspection repair regression: PASS.
- Phase 8 real browser inspection regression: PASS.
- Targeted repair/status/telemetry/MCP tests: 28 passed.
- Full test suite: 830 passed.
- MCP server import smoke: 145 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.12.0] — 2026-04-26 — Inspection Repair Execution Loop

Phase 10 of the multi-host SAMVIL architecture. This release closes the first
create -> inspect -> fail -> repair -> reinspect loop by adding repair plans
and before/after repair reports.

### Added
- `mcp/samvil_mcp/repair.py` for deterministic repair plan/report generation,
  reading, persistence, and markdown rendering.
- Repair artifacts: `.samvil/repair-plan.json` and
  `.samvil/repair-report.json`.
- Repair MCP tools: `build_repair_plan`, `read_repair_plan`,
  `render_repair_plan`, `build_repair_report`, `read_repair_report`, and
  `render_repair_report`.
- `samvil-status.py` repair summary in both human and JSON output.
- `scripts/phase10-inspection-repair-dogfood.py`, a before/after repair
  dogfood over broken dashboard and browser game fixtures.
- Phase 10 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.12-phase10.md`.

### Dogfood
- `repair-dashboard`: before_failed=4, after_failed=0, actions=4,
  resolved=4, status=verified.
- `repair-game`: before_failed=3, after_failed=0, actions=3, resolved=3,
  status=verified.
- Both scenarios end with `repair verified: re-run release checks`.

### Verified
- Phase 10 inspection repair dogfood: PASS.
- Phase 8 real browser inspection regression: PASS.
- Targeted repair/status/MCP tests: 12 passed.
- Full test suite: 821 passed.
- MCP server import smoke: 143 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.11.0] — 2026-04-26 — Inspection Feedback Loop

Phase 9 of the multi-host SAMVIL architecture. This release turns failed
inspection reports into actionable repair loops through failure taxonomy,
repair hints, retro observations, and status next-action priority.

### Added
- Inspection failure taxonomy for console errors, layout overflow, screenshot
  missing, interaction failures, blank canvas, viewport load failures, and
  missing/invalid evidence.
- Failure records in `.samvil/inspection-report.json` with severity,
  `repair_hint`, and `next_action`.
- `derive_inspection_observations`, converting failed inspection checks into
  retro observation candidates.
- MCP wrapper for `derive_inspection_observations`, including optional
  persistence to `.samvil/retro-observations.jsonl`.
- `samvil-status.py` priority for failed inspection reports so the next action
  points at inspection repair before generic run continuation.
- `scripts/phase9-inspection-feedback-dogfood.py`, a broken-fixture dogfood
  covering console, overflow, screenshot, interaction, and canvas failures.
- Phase 9 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.11-phase9.md`.

### Dogfood
- `broken-dashboard-feedback`: status=fail, failures=4, observations=4,
  types=`console-error,interaction-failed,layout-overflow,screenshot-missing`,
  next_action=`repair inspection failure: console-error (...)`.
- `broken-game-feedback`: status=fail, failures=3, observations=3,
  types=`canvas-blank,interaction-failed,screenshot-missing`,
  next_action=`repair inspection failure: canvas-blank (...)`.

### Verified
- Phase 9 broken-fixture feedback dogfood: PASS.
- Phase 8 real browser inspection regression: PASS.
- Targeted inspection/status/MCP tests: 15 passed.
- Full test suite: 814 passed.
- MCP server import smoke: 137 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

---

## [3.10.0] — 2026-04-26 — Real App Inspection Gate

Phase 8 of the multi-host SAMVIL architecture. This release promotes browser
dogfood from "the generated app runs" to "the generated app passes a
repeatable user-visible inspection gate."

### Added
- `mcp/samvil_mcp/inspection.py` for deterministic inspection report
  generation, persistence, reading, and markdown rendering.
- Inspection MCP tools: `build_inspection_report`, `read_inspection_report`,
  and `render_inspection_report`.
- `scripts/samvil-status.py` inspection summary in both human and JSON output.
- `scripts/phase8-real-app-inspection.py`, a real browser inspection dogfood
  that creates Vite React SaaS dashboard and Vite Phaser game projects.
- `mcp/tests/test_phase8_real_app_inspection.py`, an opt-in pytest wrapper
  enabled with `SAMVIL_RUN_BROWSER_DOGFOOD=1`.
- Phase 8 planning document under
  `docs/superpowers/plans/2026-04-26-samvil-v3.10-phase8.md`.

### Covered
- Real `npm install`, `npm run build`, Vite dev server, and Playwright Chromium.
- Desktop and mobile viewport inspection for both generated apps.
- Screenshot artifact existence.
- Console error checks.
- Layout overflow checks.
- Dashboard heading/KPI/filter/chart/table inspection.
- Game canvas nonblank pixel, keyboard movement, score increase, and restart
  reset inspection.
- Domain Pack matching, Pattern Registry lookup, Codebase Manifest generation,
  run report generation, status JSON rendering, and zero retro candidates.

### Dogfood
- `vite-saas-dashboard-inspection`: pack=`saas-dashboard`, confidence=high,
  checks=12, failed=0, console_errors=0, screenshots=2, viewports=2, retro=0.
- `vite-phaser-game-inspection`: pack=`browser-game`, confidence=high,
  checks=14, failed=0, console_errors=0, screenshots=2, viewports=2, retro=0.

### Verified
- Direct real app inspection dogfood: PASS.
- Opt-in pytest inspection dogfood:
  `SAMVIL_RUN_BROWSER_DOGFOOD=1 ./.venv/bin/python -m pytest tests/test_phase8_real_app_inspection.py -q`: 1 passed.
- Full test suite: 809 passed.
- MCP server import smoke: 136 tools.
- Cross-host replay: PASS.
- `bash scripts/pre-commit-check.sh`: PASS.

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
