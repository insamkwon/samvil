# SAMVIL Output Format Guide (v2.3.0+)

> 전 스킬 공통 출력 포맷. Manifesto v3 P7 (Explicit over Implicit) 구현.

---

## 🎯 원칙

**AI가 한 일은 모두 사용자에게 보여준다. 숨기지 않는다.**

출처를 **아이콘**으로 시각적 구분:

| 아이콘 | 의미 | 내부 기록 prefix |
|--------|------|-----------------|
| ℹ️ | **자동 감지** — 코드/manifest에서 읽은 사실 | `[from-code]` |
| 💬 | **사용자 선택** — 사용자가 직접 답변/결정 | `[from-user]` |
| 🔍 | **리서치 결과** — 외부 웹/문서 조회 결과 | `[from-research]` |
| ✓ | 단계/태스크 완료 | - |
| ✗ | 실패 / 차단 | - |
| ⚠ | 경고 / 주의 | - |
| ⏸ | 대기 / PENDING | - |
| ⟳ | 진행 중 / IN_PROGRESS | - |
| ⏭ | 스킵 | - |
| 🔁 | 재시도 | - |
| 🛡 | 게이트 차단 | - |

---

## 📋 표준 출력 포맷

### 스킬 시작

```
[SAMVIL] 🔵 Phase: Interview (Stage 1/5)
[SAMVIL] 종료 조건: ambiguity ≤ 0.05 (standard tier)
```

### 자동 감지 (P2 Description)

```
[SAMVIL] ℹ️ 자동 감지: Next.js 14 (package.json)
[SAMVIL] ℹ️ 자동 감지: Prisma + PostgreSQL (schema.prisma)
```

### 사용자 선택

```
[SAMVIL] 💬 사용자 선택: Stripe 결제
[SAMVIL] 💬 사용자 선택: saga 패턴으로 롤백
```

### 리서치 결과 (PATH 4)

```
[SAMVIL] 🔍 리서치 결과: Stripe rate limit 100 read/sec (stripe.com/docs)
```

### 진행률

```
[SAMVIL] ⟳ AC-2 결제 모듈 (Worker B) — 2분 경과
[SAMVIL] ✓ AC-1 회원가입 완료
[SAMVIL] ⏸ AC-3 관리자 (대기 중 — AC-1 의존)
```

### Rhythm Guard 발동

```
⚠️ [SAMVIL] 연속 3회 자동 확정. 이번 질문은 직접 답변해주세요.
```

### Gate 차단 (P5 Regression, P3 Decision Boundary)

```
🛡 [SAMVIL] 수렴 차단: AC-3 (결제)가 Cycle 2 PASS → Cycle 3 FAIL. 퇴화 감지.
  선택지:
    1. 이전 세대로 롤백
    2. AC-3 재설계 후 추가 cycle
    3. 중단하고 수동 디버그
```

### Evidence 표기 (P1)

```
[SAMVIL] ✓ AC-1 PASS
  증거: src/auth.ts:15 (zod emailSchema)
  증거: prisma/schema.prisma:12 (@@unique([email]))
```

---

## 🎨 Tier별 verbosity

| Tier | 상세도 |
|------|--------|
| minimal | 핵심 이벤트만 (✓/✗ + 총계) |
| standard | 일반 (이 가이드 기준) |
| thorough | 자세한 rationale 포함 |
| full | 전체 추적 (evidence + socratic questions) |

---

## 🔍 내부 로그 prefix 유지

UI는 아이콘이지만, `.samvil/events.jsonl`과 `interview-summary.md` 등 **내부 파일**은 prefix 유지:

```
[from-code][auto-confirmed] Next.js 14 (package.json)
[from-user] Stripe 선택
[from-research] Stripe rate 100/sec (source: stripe.com)
```

이유: grep으로 출처별 검색 용이, 추후 분석 툴 호환.

---

## ⛔ 금지 패턴

- ❌ 아무 prefix/아이콘 없이 `[SAMVIL] 진행 중...` (출처 불명)
- ❌ 복잡한 이모지 남발 (🎉🚀✨ 등)
- ❌ 색상 코드 직접 사용 (터미널 호환성)
- ❌ 시스템 정보 노출 (PID, PATH, 내부 경로 노출)

---

## 📎 참조

- Manifesto v3, Part 5 "Communication Policy"
- P7 Explicit over Implicit
- 관련 문서: [01-path-routing.md](~/docs/ouroboros-absorb/01-path-routing.md)
