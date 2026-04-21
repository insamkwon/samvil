# Council Output Style — Korean-First (v3.1.0, v3-024)

> Purpose: council agent output을 한국어 dogfood 환경에서 **5초 안에 읽히도록** 하는 공통 스타일 가이드.
>
> **Triggered by**: `v3-024` — vampire-survivors dogfood에서 council 결과가 영어 용어 + 약어 가득이라 사용자가 의견 파악에 시간이 걸렸음.

---

## 1. 원칙

1. **한글 우선** — 결론/평가는 한국어로 먼저. 영어 용어는 필요 시 괄호로 병기.
2. **약어 풀어쓰기** (첫 등장 시) — PO / AC / P1 / P2 / MVP / GA 등.
3. **영어 원문 보존** — 영어 인용문은 원문 유지 + 한글 요약 1줄 병기.
4. **점수는 의미 해석 포함** — `0/3 APPROVE` 같은 숫자 뒤에 "3개 모두 보완 필요" 한 줄.
5. **Critical finding에 '왜 문제인지'** — 한 줄 plain Korean 설명 필수.

---

## 2. 표준 출력 블록

### 2a. 평가 표 (모든 council agent 공통)

```markdown
| 섹션 (Section) | 판정 (Verdict) | 심각도 (Severity) | 이유 (Reasoning) |
|---|---|---|---|
| 핵심 경험 (Core Experience) | APPROVE | - | 30초 행동이 명확. |
| 인수 기준 (Acceptance Criteria, AC) | CHALLENGE | BLOCKING | 테스트 불가한 모호 표현 3개 발견. |
```

### 2b. 요약 문장

```markdown
## 요약 (Summary)

<한 줄 한국어 판정 + 핵심 사유>. <영어 원문이 필요하면 괄호로>.
```

예시:
> 제품 가치는 명확하나 인수 기준이 테스트 가능하지 않음. ("User-friendly"는 testable AC가 아님.)

### 2c. 추천 변경사항

```markdown
## 추천 변경사항 (Recommended Changes)

1. **<change label in Korean>** — <why in Korean>.
   - 현재: <current state, quote if from seed>
   - 제안: <proposal>
   - 원문 (영어): <quoted English if applicable>
```

---

## 3. 용어 번역 사전 (Council agent 공통)

| 영어 | 한글(영어) 병기 | 처음 등장 시 풀어쓰기 |
|---|---|---|
| Acceptance Criteria | 인수 기준 (AC) | 인수 기준(Acceptance Criteria, AC) |
| Product Owner | 프로덕트 오너 (PO) | 프로덕트 오너(Product Owner, PO) |
| Priority 1 / P1 | 최우선 (P1) | 최우선(Priority 1, P1) |
| Priority 2 / P2 | 차순위 (P2) | 차순위(Priority 2, P2) |
| MVP | 최소 기능 제품 (MVP) | 최소 기능 제품(Minimum Viable Product, MVP) |
| GA | 정식 출시 (GA) | 정식 출시(General Availability, GA) |
| Consensus Score | 합의 점수 | 합의 점수(Consensus Score) |
| Business Viability | 사업성 | 사업성(Business Viability) |
| BLOCKING gap | 차단 수준 누락 | 차단 수준 누락(BLOCKING gap) |
| False independence | 거짓 독립성 (실제 의존) | 거짓 독립성(false independence) — 실제로는 의존 |
| Single point of failure | 단일 실패 지점 | 단일 실패 지점(Single Point of Failure, SPOF) |
| Sequential dataflow | 순차적 데이터 흐름 | 순차적 데이터 흐름(sequential dataflow) |
| Edge case | 엣지 케이스 | 엣지 케이스(edge case) — 드물지만 발생 가능 |
| Out of scope | 범위 외 | 범위 외(out of scope) |
| Blueprint | 설계도 (blueprint) | 설계도(blueprint) |
| Seed | 시드 (seed) — 모든 단계의 정본 spec |

---

## 4. 점수 의미 풀어쓰기

**Verdict 집계 시**:

| 원본 | 한글 해석 |
|---|---|
| `3/3 APPROVE` | ✅ 3개 에이전트 모두 승인 — 이대로 진행해도 됨 |
| `2/3 APPROVE, 1 CHALLENGE` | ⚠️ 2명 승인, 1명 이의 제기 — 이의 내용 검토 필요 |
| `1/3 APPROVE` | ❌ 1명만 승인 — 2명 이상 보완 제시, 재설계 권장 |
| `0/3 APPROVE` | ❌ 3명 모두 보완 필요 — 핵심 기준 재정의 후 재검토 |

---

## 5. Critical finding 설명 형식

**원본 (영어)**:
> BLOCKING gap: onboarding flow missing for new users

**v3-024 형식 (권장)**:
> ⚠️ **차단 수준 누락 (BLOCKING gap)**: 신규 사용자를 위한 onboarding flow가 없음.
> **왜 문제인가**: 첫 사용자가 앱을 열었을 때 뭘 해야 할지 모르는 상태로 이탈 가능. Aha moment 도달 실패.

즉 `**<한글 라벨 (영어 원문)**: <한글 설명>.\n**왜 문제인가**: <한 줄 이유>` 형식.

---

## 6. Council agent별 적용 방법

`agents/ceo-advisor.md`, `tech-lead.md`, `ux-designer.md`, `business-analyst.md`, `product-owner.md`, `ux-researcher.md`의 **Output** 섹션에 공통으로 다음 한 줄을 추가:

> Follow `references/council-korean-style.md` for Korean-first output format when running in Korean dogfood environment.

개별 agent의 output template 자체는 변경하지 않는다 (agent의 고유 perspective 유지). 스타일 가이드만 참조.

---

## 7. 관련 문서

- `references/council-protocol.md` — Council 토론 규칙 (verdict types)
- `references/tier-definitions.md` — Tier별 agent 구성
- `skills/samvil-council/SKILL.md` — Council 실행 프로토콜

---

_작성: 2026-04-21 · v3.1.0 Sprint 5 (v3-024)_
