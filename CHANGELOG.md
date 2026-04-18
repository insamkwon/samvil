# Changelog

All notable changes to SAMVIL are documented here.

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
