# Changelog

All notable changes to SAMVIL are documented here.

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
