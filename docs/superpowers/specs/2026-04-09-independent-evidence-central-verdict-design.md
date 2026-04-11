# Independent Evidence, Central Verdict — Design Spec

**Date:** 2026-04-09  
**Status:** Draft for review  
**Scope:** SAMVIL QA/Design/Evolve pipeline improvements before implementation

---

## 1. Goal

SAMVIL의 검증 품질을 올리되, 현재 체인의 단순성과 tier별 사용자 경험은 유지한다.

핵심 목표는 세 가지다.

1. **Blueprint feasibility를 build 전에 검증**해서 설계 문제로 인한 재시도를 줄인다.
2. **Independent QA를 standard+ tier에 도입**해서 자기 코드 자기 검사 bias를 줄인다.
3. **Evolve가 build/QA 이력을 구조적으로 읽게** 해서 근본 원인 파악 능력을 높인다.

이 개선의 설계 원칙은 하나로 요약된다.

> **Independent Evidence, Central Verdict**  
> 증거 수집과 평가 시각은 분산하되, 최종 판정과 상태 기록은 중앙에서 통제한다.

---

## 2. Why now

현재 구조에는 세 가지 병목이 있다.

### 2.1 QA bias
- Build와 QA를 같은 메인 세션이 연속 수행한다.
- 메인은 이미 "이 기능은 이렇게 동작할 것"이라는 구현 의도를 알고 있다.
- 그래서 실제로는 stub, hardcoded path, unreachable code인데도 PASS 또는 PARTIAL로 완화될 위험이 있다.

### 2.2 Late feasibility discovery
- blueprint의 비현실적 선택을 build 도중에야 발견한다.
- 예: 복잡한 chart library, stack mismatch, known conflict.
- 이 경우 build retry가 설계 검증의 대체재처럼 동작해 비용이 커진다.

### 2.3 Weak postmortem context for evolve
- 현재 wonder/reflect는 QA 결과 중심으로 사고한다.
- build 실패 패턴, 반복 수정, workaround 흔적을 구조적으로 읽지 못한다.
- 그래서 증상은 보지만 원인 패턴은 놓칠 수 있다.

---

## 3. Final decisions

| Area | Decision | Rollout |
|---|---|---|
| Blueprint feasibility | 기본 ON | all tiers |
| Evolve event schema | 기본 ON | all tiers |
| Independent QA | Pass 2 + Pass 3 분리 | `selected_tier >= standard` |
| Final verdict/report/state/events | 메인 세션만 수행 | all tiers |
| minimal tier | 기존 QA 흐름 유지 | unchanged |

---

## 4. Non-goals

이번 변경에서 하지 않는 것:

1. Pass 1 Mechanical까지 완전 독립 agent로 분리하지 않는다.
2. minimal tier의 QA 판정 방식을 바꾸지 않는다.
3. Evolve를 새로운 stage로 재구성하지 않는다.
4. build/qa 결과를 외부 저장소나 DB에 적재하지 않는다.
5. plugin 전체 아키텍처를 worktree/team 기반으로 재설계하지 않는다.

---

## 5. Architectural principle

### 5.1 Independent Evidence
Independent agent는 아래 역할만 맡는다.
- acceptance criterion별 근거 탐색
- quality dimension별 근거 탐색
- skeptical review
- verdict 초안 생성

### 5.2 Central Verdict
메인 세션은 아래 역할만 맡는다.
- stage orchestration
- verdict matrix 적용
- `.samvil/qa-report.md` 작성
- `project.state.json` 업데이트
- `.samvil/events.jsonl` append
- Ralph loop 재진입 여부 결정

이렇게 나누는 이유는 명확하다.
- 독립 agent가 bias를 줄인다.
- 메인이 SSOT를 유지한다.
- taxonomy drift나 state drift를 막는다.

---

## 6. Phase plan

## Phase 1 — Safe default-on changes

### 6.1 Blueprint feasibility check

**Target file:** `skills/samvil-design/SKILL.md`

**Insertion point:**
- Gate B 결과 반영 후
- 기존 user checkpoint 직전
- 즉, 최종 blueprint를 사용자에게 보여주기 전에 feasibility check를 실행한다.

**New flow:**
1. seed 기반 blueprint 생성
2. Gate B 결과 반영
3. feasibility reviewer 실행
4. `GO / CONCERN / BLOCKER` 반환
5. 메인이 blueprint 수정 여부 결정
6. 수정된 blueprint를 사용자에게 제시
7. 승인 후 scaffold/build 진행

**Why this placement:**
- build 직전이 아니라 **user checkpoint 전**이어야 한다.
- 사용자가 승인한 blueprint가 실제 build 입력과 같아야 한다.
- 중간에 몰래 blueprint가 바뀌는 구조를 방지한다.

**Reviewer checks:**
1. `key_libraries` installability
2. stack consistency
3. known conflict
4. scope realism
5. current scaffold conventions와의 호환성

**Output contract:**
- `GO`: 문제 없음
- `CONCERN`: 진행 가능하지만 경고 필요
- `BLOCKER`: build 전에 수정 필요

**Important rule:**
feasibility reviewer는 경고를 제시할 뿐, blueprint를 직접 수정하거나 stage를 이동시키지 않는다.

### 6.2 Event schema reinforcement

**Target files:**
- `skills/samvil-build/SKILL.md`
- `skills/samvil-qa/SKILL.md`
- `skills/samvil-evolve/SKILL.md`
- `agents/wonder-analyst.md`

이 단계의 목표는 evolve가 "마지막 로그 한 장"이 아니라 "실패 패턴의 연속성"을 읽게 만드는 것이다.

---

## Phase 2 — Taxonomy alignment before Independent QA

**Target files:**
- `agents/qa-functional.md`
- `agents/qa-quality.md`
- `references/qa-checklist.md` (필요 시 wording 보강)
- `skills/samvil-qa/SKILL.md` (agent synthesis wording 정리)

### Why this phase must come first
Independent QA를 먼저 붙이면 skill inline taxonomy와 agent taxonomy가 어긋난다.

현재 기준:
- `skills/samvil-qa/SKILL.md` → `PASS / PARTIAL / UNIMPLEMENTED / FAIL`
- `agents/qa-functional.md` → `PASS / PARTIAL / FAIL`

이 상태로 agent를 먼저 붙이면:
- stub/hardcoded 구현이 `FAIL`로 뭉개질 수 있고
- 메인의 합산 기준과 충돌한다.

따라서 **taxonomy alignment가 Independent QA의 선행 조건**이다.

### Alignment rules

#### Functional taxonomy
- `PASS`: AC 완전 충족
- `PARTIAL`: 코드 근거는 있으나 static analysis로 확증 불가
- `UNIMPLEMENTED`: stub, hardcoded response, TODO, simulated path
- `FAIL`: 버그, 결함, 누락, 도달 불가

#### Quality output alignment
`agents/qa-quality.md`는 점수 중심 agent로 유지하되, 메인 synthesis가 아래를 안정적으로 계산할 수 있어야 한다.
- dimension score
- critical issue list
- revise trigger condition
- empty/error/focus/mobile findings

---

## Phase 3 — Independent QA for standard+

**Target file:** `skills/samvil-qa/SKILL.md`

### Tier policy
- `minimal`: 기존 inline Pass 1/2/3 유지
- `standard`, `thorough`, `full`: Independent QA 활성화

### New QA architecture for standard+

#### Pass 1: Mechanical — main session
메인이 직접 수행한다.

이유:
- build.log 관리
- smoke run
- Ralph loop 진입
- state update
- retry control

이 축은 orchestration과 결합이 강해서 중앙 유지가 낫다.

#### Pass 2: Functional — independent agent
메인이 `qa-functional` prompt를 기준으로 독립 agent를 spawn한다.

agent 역할:
- AC별 구현 근거 탐색
- reachable 여부 확인
- empty state / persistence / edge case 확인
- verdict 초안 생성

#### Pass 3: Quality — independent agent
메인이 `qa-quality` prompt를 기준으로 독립 agent를 spawn한다.

agent 역할:
- responsive / accessibility / code structure / UX polish 검토
- 점수와 이슈를 반환

#### Final synthesis — main session only
메인이 수행한다.

메인 역할:
1. Pass 1 결과 해석
2. Pass 2/3 결과 병합
3. verdict matrix 적용
4. `.samvil/qa-report.md` 작성
5. `.samvil/events.jsonl` append
6. `project.state.json` update
7. Ralph loop / evolve / retro 진입 결정

### Why this split works
- bias 제거는 Pass 2/3에서 가장 중요하다.
- state safety는 메인에서 가장 중요하다.
- 따라서 **evidence는 분산, verdict는 중앙**이 가장 자연스럽다.

---

## Phase 4 — A/B validation before rollout confidence

Independent QA 도입 후에는 반드시 A/B 검증을 수행한다.

### Test setup
- 동일 seed
- 동일 코드베이스
- 동일 acceptance criteria
- 비교군 A: `minimal` tier (기존 QA)
- 비교군 B: `standard` tier (Independent QA)

### Comparison metrics
1. 발견 이슈 수
2. 오탐 수
3. 미탐 수
4. 총 소요 시간
5. 총 토큰 사용량
6. 판정 일관성
7. 수정 유도 품질

### Success condition
다음을 만족하면 rollout 품질이 충분하다고 본다.
- standard Independent QA가 minimal보다 issue discovery가 높거나 같음
- taxonomy 오분류가 감소함
- false positive가 관리 가능한 수준임
- latency/token increase가 acceptable range 안에 있음

---

## 7. File-level change map

| File | Responsibility after change |
|---|---|
| `skills/samvil-design/SKILL.md` | blueprint feasibility gate 추가, user checkpoint 전 위치 고정 |
| `skills/samvil-build/SKILL.md` | build/fix structured event emit |
| `skills/samvil-qa/SKILL.md` | standard+ Independent QA orchestration + synthesis |
| `skills/samvil-evolve/SKILL.md` | wonder/reflect에 structured context 전달 |
| `agents/qa-functional.md` | UNIMPLEMENTED 포함 taxonomy 정렬 |
| `agents/qa-quality.md` | synthesis-friendly output 정렬 |
| `agents/wonder-analyst.md` | build/fix/event artifacts 기반 postmortem 분석 |
| `references/qa-checklist.md` | QA taxonomy와 report examples SSOT 보강 |

---

## 8. Structured event schema

## 8.1 Design-stage events

### `blueprint_feasibility_checked`
```json
{"type":"blueprint_feasibility_checked","result":"GO|CONCERN|BLOCKER","concerns_count":2,"ts":"<ISO 8601>"}
```

### `blueprint_concern`
```json
{"type":"blueprint_concern","severity":"concern|blocker","category":"dependency|stack|scope|compatibility","message":"<brief>","ts":"<ISO 8601>"}
```

## 8.2 Build-stage events

### `build_fail`
```json
{"type":"build_fail","attempt":3,"scope":"core|feature:<name>|integration","error_signature":"Module not found: x","error_category":"import_error","touched_files":["app/page.tsx"],"ts":"<ISO 8601>"}
```

### `build_pass`
```json
{"type":"build_pass","attempt":4,"scope":"core|feature:<name>|integration","ts":"<ISO 8601>"}
```

### `fix_applied`
```json
{"type":"fix_applied","scope":"core|feature:<name>","error_category":"type_error","summary":"replace hardcoded import path","files":["lib/store.ts"],"ts":"<ISO 8601>"}
```

### `build_feature_start`
기존 이벤트 유지.

### `build_feature_success`
기존 이벤트 유지.

### `build_feature_fail`
기존 이벤트 유지하되 `error_category`를 optional field로 추가한다.

## 8.3 QA-stage events

### `qa_partial`
```json
{"type":"qa_partial","criterion":"<AC>","reason":"static analysis cannot verify runtime behavior","source":"pass2|pass3","ts":"<ISO 8601>"}
```

### `qa_unimplemented`
```json
{"type":"qa_unimplemented","criterion":"<AC>","reason":"hardcoded or simulated path","is_core_experience":false,"ts":"<ISO 8601>"}
```

### `qa_verdict`
기존 이벤트 유지.

## 8.4 Error category enum

| Value | Meaning |
|---|---|
| `import_error` | module path / alias / file resolution 문제 |
| `type_error` | TypeScript type mismatch |
| `config_error` | Tailwind / Next.js / build config 문제 |
| `runtime_error` | build는 되지만 smoke/dev에서 실패 |
| `dependency_error` | package 설치/버전/peer dependency 문제 |
| `unknown` | 분류 실패 |

---

## 9. Event emit ownership

| Event | Emit owner |
|---|---|
| `blueprint_feasibility_checked` | `skills/samvil-design/SKILL.md` |
| `blueprint_concern` | `skills/samvil-design/SKILL.md` |
| `build_fail` | `skills/samvil-build/SKILL.md` |
| `build_pass` | `skills/samvil-build/SKILL.md` |
| `fix_applied` | `skills/samvil-build/SKILL.md` |
| `build_feature_start` | `skills/samvil-build/SKILL.md` |
| `build_feature_success` | `skills/samvil-build/SKILL.md` |
| `build_feature_fail` | `skills/samvil-build/SKILL.md` |
| `qa_partial` | `skills/samvil-qa/SKILL.md` |
| `qa_unimplemented` | `skills/samvil-qa/SKILL.md` |
| `qa_verdict` | `skills/samvil-qa/SKILL.md` |
| `evolve_gen` / `evolve_converge` | `skills/samvil-evolve/SKILL.md` |

---

## 10. Prompt changes required

## 10.1 `qa-functional`
추가되어야 할 핵심 메시지:
- `UNIMPLEMENTED` taxonomy
- stub/hardcoded/simulated path examples
- core_experience stub는 severity가 더 높다는 설명
- evidence-first verdict rule

## 10.2 `qa-quality`
보강되어야 할 핵심 메시지:
- Pass 2와 중복 판정하지 않기
- score + concrete issue extraction
- mobile/focus/empty state 우선 확인
- synthesis가 쓰기 쉬운 형태로 issue grouping 유지

## 10.3 `wonder-analyst`
추가되어야 할 핵심 메시지:
- `build.log`, `fix-log.md`, `events.jsonl` 읽기
- repeated error signature 탐지
- reverted fix/workaround pattern 탐지
- QA summary보다 event ground truth 우선

---

## 11. Risks and mitigations

### Risk 1: Taxonomy drift
**Risk:** skill inline 규칙과 agent 파일이 다시 벌어진다.  
**Mitigation:** taxonomy를 `references/qa-checklist.md`에 명시하고, agent/skill 둘 다 동기화한다.

### Risk 2: Agent output variability
**Risk:** Pass 2/3 결과 표현이 들쭉날쭉하다.  
**Mitigation:** fixed output contract를 두고 메인이 parsing-friendly synthesis만 받는다.

### Risk 3: Token/time increase
**Risk:** standard+ QA 비용이 올라간다.  
**Mitigation:** minimal은 유지, standard+만 분리, A/B 비교로 비용 대비 효과 검증.

### Risk 4: Over-logging
**Risk:** event는 늘지만 통찰은 약할 수 있다.  
**Mitigation:** freeform 로그 대신 `error_category`, `scope`, `attempt` 같은 정규 필드 위주로 제한한다.

### Risk 5: False blockers in design
**Risk:** feasibility checker가 불필요하게 BLOCKER를 반환한다.  
**Mitigation:** 기본 판단은 `CONCERN` 중심으로 두고, build 불가에 가까운 경우만 `BLOCKER`를 사용한다.

---

## 12. Success metrics

이 설계가 성공했다고 판단하는 기준:

1. standard+ QA에서 stub/hardcoded 기능의 탐지율이 증가한다.
2. build retry 중 설계 문제 비중이 감소한다.
3. wonder analysis가 error category 반복 패턴을 인식한다.
4. minimal 사용자 경험은 기존과 동일하게 유지된다.
5. final verdict/report/state write path가 여전히 단일 메인 세션에 남아 있다.

---

## 13. Implementation readiness checklist

개발 착수 전 아래가 모두 명확해야 한다.

- [x] rollout policy 확정
- [x] phase ordering 확정
- [x] event schema 확정
- [x] emit ownership 확정
- [x] taxonomy alignment 필요성 확정
- [x] standard+ QA split 범위 확정
- [x] A/B validation metric 확정
- [x] version split: v0.5.0 (feasibility+events+taxonomy) / v0.6.0 (independent QA)
- [x] plugin cache sync step in every task

남은 것은 구현뿐이다.

---

## 14. Final recommendation

이 변경은 한 번에 크게 뒤엎는 작업이 아니라, **낮은 위험의 관측 강화 → 판정 기준 정렬 → selective independence 도입** 순서로 진행해야 한다.

가장 중요한 운영 원칙은 다음 한 문장이다.

> **Independent agents may gather evidence, but only the main session may decide, persist, and transition stages.**
