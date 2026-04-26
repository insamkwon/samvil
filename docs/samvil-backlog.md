# SAMVIL Backlog

> 장기 트래킹용 — Tier/Phase 진행 중 발견된 항목 + Mountain Stage 약속.
> 처음 추가: 2026-04-26 (Tier 1+2 retro 후)

---

## 🔧 Maintenance

| ID | Item | Found | Status | Priority |
|---|---|---|---|---|
| M1 | pre-push hook tag-push false positive | T1.R | ✅ Fixed in T2.6 (v3.34.0) | — |
| M2 | GitHub Actions Node 20 deprecation (actions/checkout@v4 등) | T2.R | Open | Sept 2026 |
| M3 | Flaky `test_periodic_checkpointer` (timing-sensitive) | T2.2 | Open | Low |
| M4 | scaffold-input silent failure | T1.1 | ✅ Already fixed in `e4f93b1` (regression test added) | — |

---

## 📋 Consolidation (Tier 3-4)

| ID | Item | Tier | Notes |
|---|---|---|---|
| C1 | Phase A: Easy 4 skills migration | T3 | samvil-pm-interview / doctor / update / deploy |
| C2 | Phase B: Medium 4 skills | T4 | samvil-evolve / retro / council / analyze |
| C3 | Phase C: Hard 5 skills | T4 | samvil / interview / build / scaffold / qa (가장 위험) |
| C4 | SKILL.legacy.md 보존 패턴 정착 | T3+ | 모든 마이그레이션에 적용 |

---

## 🏔️ Mountain Stage (M1-M4) — Original promises

| ID | Item | Stage | 기간 |
|---|---|---|---|
| **MA1** | Module Boundary `contract.json` 시스템 | M1 | 2주 |
| **MA2** | Codex E2E real dogfood (마커 → 실제 chained 실행) | M2 | 2-3주 |
| **MA3** | OpenCode E2E real dogfood | M2 | 2-3주 |
| **MA4** | Gemini adapter 추가 | M2 | 1-2주 |
| **MA5** | Cross-host result equivalence test 자동화 | M2 | 1주 |
| **MA6** | Domain Pack: game-phaser (Phaser 상태기계 + asset pipeline + 60fps budget) | M3 | 2주 |
| **MA7** | Domain Pack: webapp-enterprise (monorepo + BFF + OpenAPI + SSO) | M3 | 2주 |
| **MA8** | Telemetry opt-in flow (`/samvil` 첫 실행 시) | M4 | 1주 |
| **MA9** | 익명화 telemetry sync to dongho 서버 | M4 | 1주 |
| **MA10** | Mini Next.js dashboard (별도 프로젝트) | M4 | 2주 |
| **MA11** | 3-tier health UI in skill output | M4 | 1주 |

---

## 🐛 Known limitations (not bugs, design choices)

| ID | Item | Source | 결정 |
|---|---|---|---|
| L1 | `Manifest.project_root` 절대/상대 caller 통제 (resolve 안 함) | Phase 1 T1.6 | 의도된 동작. 문서화됨. |
| L2 | `extract_public_api` regex 기반 (export* 미지원, 코멘트 best-effort) | Phase 1 T1.4 | Phase 2 AST resolver로 교체 예정 (deferred) |
| L3 | `_now_iso` 형식 (RFC 3339, second precision) | Phase 1 T1.1 | 의도. claim_ledger와 일치. |
| L4 | 5-cascade marker (rebuild-reentry → scaffold-input → ... → evolve-cycle) | Phase 28-30 | T1.1 재검토 결과 통합 보류. Phase 33+ 검토. |

---

## 💡 Ideas (not committed, just captured)

- 정기 retro 자동화 — 매 Tier 끝에 retro md 자동 생성 트리거?
- Skill migration helper MCP tool — 스킬 구조 분석 + ultra-thin 변환 제안?
- Documentation auto-slim — CLAUDE.md 누적 감지 + slim 제안?

---

작성: 2026-04-26 (Tier 1+2 retro 후)
