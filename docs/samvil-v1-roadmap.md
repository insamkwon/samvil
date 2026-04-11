# SAMVIL v1.0 Roadmap — 7전문가 종합 개선 플랜

> Generated: 2026-04-11
> Current version: v0.9.0 → Target: v1.0.0
> Source: 7-expert agent analysis (Dev / AI-AX / CEO / Design / QA / DevOps / PM)

---

## Executive Summary

SAMVIL은 v0.9.0까지 vibe-coding harness로서의 핵심 파이프라인(Interview → Seed → Build → QA → Retro)을 완성했다. v1.0에서는 **신뢰성(결정성)**, **지능력(AI 프롬프트 품질)**, **확장성(플러그인 생태계)**의 3축을 강화하여, "한 줄 프롬프트로 프로덕션급 웹앱 생성"이라는 가치를 확실히 전달한다.

---

## Phase Overview

| Phase | Theme | Version | Duration | Key Metric |
|-------|-------|---------|----------|------------|
| **P1** | Foundation — 결정성 & 안정성 | v0.10.0 | Sprint 1 | Scaffold 성공률 95%+ |
| **P2** | Intelligence — AI/Agent 품질 | v0.11.0 | Sprint 2 | AC 달성률 80%+ |
| **P3** | Scale — 성능 & 자동화 | v0.12.0 | Sprint 3 | 전체 파이프라인 10분 이내 |
| **P4** | Growth — 확장 & 에코시스템 | v1.0.0 | Sprint 4 | 외부 기여자 3명+ |

---

## Phase 1: Foundation — 결정성 & 안정성 (v0.10.0)

> "Same input → Same output. Every time."

### P1-1. Scaffold 결정적 재현

**문제:** Tailwind v4, shadcn/ui 버전 충돌로 scaffold가 실행마다 다르게 실패함
**해결:**

```
references/dependency-matrix.json  ← 버전 고정 매트릭스
{
  "nextjs14": {
    "tailwind": "4.0.6",
    "shadcn": "2.1.0",
    "typescript": "5.7.3"
  },
  "vite-react": { ... },
  "astro": { ... }
}
```

- [ ] `dependency-matrix.json` 생성 (스택별 고정 버전)
- [ ] scaffold 스킬에서 매트릭스 기반 `--exact-version` install
- [ ] Idempotent 재시도: 실패 시 동일 버전으로 재시도, 난수/시간 의존 제거
- [ ] scaffold 후 자동 검증 (`npm run build` + `npm run lint` 통과 확인)

**파일:** `skills/samvil-scaffold.md`, `references/dependency-matrix.json`
**에이전트:** `agents/scaffolder.md`

### P1-2. Inter-Stage Contract (JSON Schema)

**문제:** Seed → Design → Scaffold 간 데이터가 파이프라인 끝까지 잘못 전파됨
**해결:**

- [ ] `references/seed-schema.json` — JSON Schema Draft 7로 seed.json 검증
- [ ] 각 스테이지 시작 시 `ajv.validate(schema, data)` 호출
- [ ] 검증 실패 시 즉시 중단 + 구체적 에러 메시지
- [ ] blueprint.json, state.json에도 스키마 적용

**파일:** `references/seed-schema.json` (기존 md → json 스키마 변환)
**에이전트:** `agents/tech-architect.md`

### P1-3. SQLite 강화

**문제:** MCP 서버의 aiosqlite가 기본 설정이라 동시성/신뢰성 취약
**해결:**

- [ ] WAL 모드 활성화 (`PRAGMA journal_mode=WAL`)
- [ ] Connection Pooling (aiosqlite 내부 풀 활용)
- [ ] 핵심 쓰기 작업에 Transaction 래핑
- [ ] 데이터 무결성 체크 (`PRAGMA integrity_check`)

**파일:** `mcp/samvil_mcp/event_store.py`

### P1-4. Build Guard (정적 분석)

**문제:** 빌드 에러가 QA 단계에서야 발견됨
**해결:**

- [ ] Build 전 pre-check 스크립트: TypeScript 타입 체크 + ESLint
- [ ] Worker는 lint/typecheck만 실행, full build는 배치 완료 후 1회 (기존 로직 확인)
- [ ] 빌드 실패 시 diff 기반 원인 분석 (`build.log` 파싱)
- [ ] `hooks/log-build-result.sh` 개선 — 빌드 시간, 에러 카테고리 메트릭 추가

**파일:** `hooks/log-build-result.sh`, `skills/samvil-build.md`

### P1-5. 테스트 기반 강화

**문제:** MCP 테스트 3개(346 LOC) vs 소스 981 LOC. 커버리지 < 40%
**해결:**

- [ ] `tests/test_seed_manager.py` — Seed CRUD + 스키마 검증
- [ ] `tests/test_build_guard.py` — 빌드 전/후 검증 로직
- [ ] `tests/test_scaffold.py` — Scaffold idempotency 테스트
- [ ] 커버리지 80%+ 목표

**파일:** `mcp/tests/`

---

## Phase 2: Intelligence — AI/Agent 품질 (v0.11.0)

> "Write less, understand more."

### P2-1. 프롬프트 엔지니어링 체계화

**문제:** 스킬 프롬프트가 ad-hoc으로 작성되어, AI가 의도를 오해하는 경우가 많음
**해결:**

- [ ] `references/prompt-patterns.md` — 공통 프롬프트 패턴 가이드
  - Zero-shot vs Few-shot 선택 기준
  - Chain-of-Thought 유도 패턴
  - 출력 포맷 강제 패턴 (JSON mode)
- [ ] 각 스킬 프롬프트에 명시적 `Output Format` 섹션 추가
- [ ] 모호한 지시어 제거 ("적절히", "알맞게" → 구체적 수치/포맷)

**파일:** `skills/*.md` (11개 전체), `references/prompt-patterns.md`

### P2-2. Agent Persona 최적화

**문제:** 37개 에이전트가 대부분 비슷한 프롬프트 구조. 컨텍스트 낭비.
**해결:**

- [ ] Compact Mode 기본화 — 현재 5개 → 전체 37개에 적용
  - 프롬프트 템플릿: `역할(2줄) + 핵심 규칙(5개) + 출력 포맷(1개)` ≤ 30줄
  - 불필요한 배경 설명, 철학 선언 제거
- [ ] `mode: compact` 프론트매터 추가
- [ ] Worker 호출 시 full persona 대신 compact persona 전달

**파일:** `agents/*.md` (37개 전체)

### P2-3. Interview 적응형 질문

**문제:** 모든 사용자에게 동일한 질문 흐름. 답변 품질이 Seed 품질을 결정.
**해결:**

- [ ] 답변 분석 기반 후속 질문 생성 (긴 답변 → 구조화 질문, 짧은 답변 → 확장 질문)
- [ ] Phase 2.5 (기존) 강화 — 앱 유형 자동 감지 후 프리셋 질문 세트 로드
- [ ] Zero-Question 모드: 프리셋 + 티어만으로 Seed 생성 (기존 기능 검증)
- [ ] 인터뷰 종료 조건 명확화 (ambiguity_score ≤ tier 임계값)

**파일:** `skills/samvil-interview.md`, `mcp/samvil_mcp/interview_engine.py`

### P2-4. Council 토론 품질 향상

**문제:** Round 2가 Round 1을 제대로 반영하지 못함
**해결:**

- [ ] Round 1 결과에서 `consensus/debate/blind_spots` 자동 추출 (기존 v0.9.0 확인)
- [ ] Round 2 프롬프트에 논쟁점 명시적 주입
- [ ] 최종 합의도(Consensus Score) 산출 — 3/5 이상 동의만 채택
- [ ] 반대 의견(Devil's Advocate)을 별도 섹션으로 보존

**파일:** `skills/samvil-council.md`, `references/council-protocol.md`

### P2-5. QA 런타임 검증 강화

**문제:** v0.9.0에서 Playwright 전환했지만, fallback이 여전히 정적 분석
**해결:**

- [ ] Playwright MCP 연결 안정화 — timeout, retry 로직
- [ ] Pass 2 검증 항목 세분화:
  - 렌더링 검증 (빈 화면, 콘솔 에러)
  - 상호작용 검증 (버튼 클릭, 폼 제출)
  - 반응형 검증 (뷰포트 전환)
- [ ] 스크린샷 증거 저장 (`.samvil/qa-evidence/`)
- [ ] Fallback 시 사용자에게 명시적 알림

**파일:** `skills/samvil-qa.md`

---

## Phase 3: Scale — 성능 & 자동화 (v0.12.0)

> "Fast is a feature."

### P3-1. 병렬 실행 최적화

**문제:** MAX_PARALLEL=2로 제한했지만, 여전히 병목 존재
**해결:**

- [ ] 동적 병렬도 조절 — CPU/메모리 기반 자동 조정
  - `os.cpus().length` 기반으로 MAX_PARALLEL 계산
  - 메모리 80% 초과 시 병렬도 감소
- [ ] Agent 간 독립성 검증 — shared state 없는 작업만 병렬화
- [ ] 프로그레스 스트림 — 각 Agent 진행 상황 실시간 출력

**파일:** `skills/samvil-build.md`, `skills/samvil-council.md`

### P3-2. 토큰 사용량 최적화

**문제:** Agent에게 전체 seed 전달로 토큰 과다 사용
**해결:**

- [ ] Feature-slicing: Worker에게 해당 feature만 전달 (기존 v0.8.0 확인)
- [ ] 컨텍스트 압축: seed에서 불필요한 필드 제거 후 전달
- [ ] 프롬프트 캐싱: 공통 프리앰블 재사용
- [ ] 토큰 사용량 추적: MCP 이벤트에 `token_count` 필드 추가

**파일:** `skills/samvil-build.md`, `mcp/samvil_mcp/event_store.py`

### P3-3. 캐시 & 증분 빌드

**문제:** 매번 full scaffold + full build가 비효율적
**해결:**

- [ ] `.samvil/cache/` — 이전 빌드 결과 캐시
- [ ] Seed diff 감지 — 변경된 feature만 재빌드
- [ ] scaffold 생략: 기존 프로젝트 디렉토리가 있으면 scaffold 스킵
- [ ] 증분 QA: 변경된 feature의 AC만 재검증

**파일:** `skills/samvil-scaffold.md`, `skills/samvil-qa.md`

### P3-4. 관측성 대시보드

**문제:** 실행 상태를 파일에서만 확인 가능
**해결:**

- [ ] MCP `get_status` 도구 개선 — JSON 기반 상태 리포트
- [ ] `.samvil/metrics.json` 자동 생성:
  - 각 스테이지 소요 시간
  - 빌드 성공/실패율
  - QA 패스율
  - 토큰 사용량
- [ ] Retro에서 metrics 자동 분석

**파일:** `mcp/samvil_mcp/server.py`, `skills/samvil-retro.md`

### P3-5. 에러 복구 & Resilience

**문제:** 중간 단계 실패 시 처음부터 재시도해야 함
**해결:**

- [ ] Checkpoint 시스템: 각 스테이지 완료 시 state.json 업데이트
- [ ] Resume 모드: `state.json`의 마지막 완료 스테이지에서 재시작
- [ ] MCP 장애 추적 개선: `mcp-health.jsonl` + 자동 복구 로직
- [ ] Graceful degradation: MCP 서버 다운 시 파일 기반으로 폴백

**파일:** `skills/samvil.md` (오케스트레이터), `mcp/samvil_mcp/server.py`

---

## Phase 4: Growth — 확장 & 에코시스템 (v1.0.0)

> "Build once, use everywhere."

### P4-1. 커스텀 프리셋 시스템

**문제:** 10개 고정 프리셋만 제공. 사용자가 자주 만드는 앱 유형에 맞춤 불가.
**해결:**

- [ ] `~/.samvil/presets/` 디렉토리 — 사용자 정의 프리셋 저장
- [ ] 프리셋 포맷: 기존 `app-presets.md`와 동일한 YAML/JSON 구조
- [ ] 인터뷰에서 커스텀 프리셋 자동 감지 + 제안
- [ ] 프리셋 공유 기능 (file.zep.works 업로드)

**파일:** `references/app-presets.md`, `skills/samvil-interview.md`

### P4-2. 플러그인 아키텍처

**문제:** 새 기능 추가 시 항상 코어 코드 수정 필요
**해결:**

- [ ] Hook 기반 확장 포인트 정의:
  - `before_scaffold`, `after_scaffold`
  - `before_build`, `after_build`
  - `before_qa`, `after_qa`
- [ ] `~/.samvil/plugins/` — 서드파티 플러그인 디렉토리
- [ ] Plugin manifest 포맷 (`plugin.json`과 동일 구조)
- [ ] 플러그인 격리: 각 플러그인은 독립 프로세스에서 실행

**파일:** `skills/samvil.md`, 새 파일 `references/plugin-api.md`

### P4-3. 멀티 스택 심화

**문제:** Next.js/Vite/Astro 3개 스택만 지원. 실제 사용 패턴은 더 다양.
**해결:**

- [ ] Nuxt (Vue) 스택 추가
- [ ] SvelteKit 스택 추가
- [ ] 스택별 dependency-matrix 동기화 자동화
- [ ] 스택 선택 시 pros/cons 비교 제공

**파일:** `references/dependency-matrix.json`, `skills/samvil-scaffold.md`

### P4-4. 배포 자동화

**문제:** 빌드 후 수동 배포. "배포 준비" 옵션만 있고 실제 배포는 안 됨.
**해결:**

- [ ] `samvil-deploy` 스킬 추가 (체인의 마지막 단계)
- [ ] 지원 플랫폼: Vercel, Railway, Coolify
- [ ] `.env.example` → `.env` 자동 변환 + 필수 환경변수 검증
- [ ] 배포 URL 자동 발급 + QR 코드 생성

**파일:** 새 파일 `skills/samvil-deploy.md`, `agents/deployer.md`

### P4-5. 문서 & 온보딩

**문제:** README가 있지만, 첫 사용자 경험이 매끄럽지 않음
**해결:**

- [ ] 튜토리얼 모드: `/samvil --tutorial` → 대화형 단계별 가이드
- [ ] 예제 갤러리: 5개 사전 빌드된 예제 앱 (저장소/스크린샷)
- [ ] 아키텍처 다이어그램: Mermaid 기반 파이프라인 시각화
- [ ] CHANGELOG.md 자동 생성 (커밋 메시지 기반)

**파일:** `README.md`, 새 파일 `references/tutorial.md`

---

## Dependency Graph

```
P1-1 ──→ P3-3  (고정 버전이 캐시의 전제조건)
P1-2 ──→ P2-3  (스키마가 인터뷰 출력 검증에 필요)
P1-3 ──→ P3-4  (SQLite 강화가 메트릭 저장의 전제조건)
P1-5 ──→ P2-*  (테스트 기반이 리팩토링의 전제조건)

P2-1 ──→ P2-2  (프롬프트 패턴이 persona 최적화에 필요)
P2-4 ──→ P2-5  (Council 결과가 QA 기준에 영향)

P3-1 ──→ P3-2  (병렬 최적화 후 토큰 절감 가능)
P3-5 ──→ P4-2  (Resilience가 플러그인 아키텍처의 전제조건)

P4-1 ──→ P4-5  (커스텀 프리셋이 튜토리얼에 사용)
P4-2 ──→ P4-3  (플러그인 아키텍처가 스택 확장을 용이하게)
```

---

## Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Tailwind/shadcn 버전 충돌 | High | Critical | P1-1 dependency-matrix |
| 컨텍스트 윈도우 초과 | Medium | High | P3-2 토큰 최적화 |
| MCP 서버 장애 | Medium | Medium | P3-5 graceful degradation |
| Playwright 불안정 | Medium | Medium | P2-5 fallback 강화 |
| 외부 API 변경 | Low | High | P1-1 버전 고정 |

---

## Success Criteria (v1.0.0)

1. **Scaffold 성공률 95%+** — 10회 연속 실행 시 9.5회 이상 성공
2. **AC 달성률 80%+** — QA Pass 2에서 80% 이상의 AC가 PASS
3. **전체 파이프라인 10분 이내** — Interview → Deploy까지 10분
4. **토큰 사용량 50% 절감** — v0.9.0 대비 총 토큰 사용량 절반
5. **테스트 커버리지 80%+** — MCP 서버 코드 기준
6. **3개 이상 외부 기여자** — GitHub PR 기준

---

## Version Milestones

| Version | Phase | Breaking Changes |
|---------|-------|-----------------|
| v0.10.0 | P1 완료 | seed-schema.json 포맷 추가 (기존 md 호환) |
| v0.11.0 | P2 완료 | Agent persona compact mode 기본화 |
| v0.12.0 | P3 완료 | state.json 체크포인트 포맷 변경 |
| v1.0.0 | P4 완료 | samvil-deploy 스킬 체인 추가 |

---

*"Shape it on the anvil, root it like ginseng."*
