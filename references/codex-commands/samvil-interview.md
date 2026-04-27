# SAMVIL Interview Stage (Codex CLI)

## Prerequisites

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
   If `next_skill` is not `samvil-interview`, stop and report to user.

## Execution

Conduct a Socratic interview in Korean. Ask **one question at a time**.
Track `questions_asked` — increment each time a question is posed to the user.

### Phase 1 — Core Understanding (always)

- 이 앱을 만들려는 이유가 뭔가요?
- 주요 사용자는 누구인가요? (역할 + 구체적인 맥락 포함, 예: "10개 이상 프로젝트를 관리하는 프리랜서 디자이너")
- 지금 이 문제를 어떻게 해결하고 계세요? (Excel/카카오톡/노션 등)
- 핵심 기능 3가지를 꼽는다면?
- 성공 기준은 어떻게 되나요? (측정 가능한 수치 포함, 예: "2초 이내 로딩")

### Phase 2 — Scope Definition (always)

- 이 앱이 절대로 다루지 않을 것은? (최소 3가지)
- 기술 제약이 있나요? (DB 종류, 인증 방식, 배포 환경 등)
- 데이터를 어디에 저장하나요? (localStorage / Supabase / 직접 DB)
- 로그인이 필요한가요? 어떤 방식? (없음 / 이메일 / OAuth / magic link)

### Phase 3 — Non-functional Requirements (thorough+)

- 첫 화면 로딩 목표 시간이 있나요? (기본: 2초 이내)
- 보안/개인정보 처리 요구사항이 있나요? (HTTPS, 암호화, PII 처리)
- 모바일에서도 동작해야 하나요? (최소 화면 크기: 320px?)
- 오프라인에서도 기본 동작해야 하나요?

### Phase 4 — Failure Modes / Inversion (thorough+)

- 이 앱이 6개월 후 아무도 안 쓴다면, 가장 가능성 높은 이유 3가지는?
- 이 앱이 절대로 다루지 않을 것은? (exclusions 목록 보강)
- 사용자가 못 하게 막아야 할 것은? (중복가입, 권한 오남용 등)

### Phase 5 — Lifecycle (standard+)

- 사용자가 이 앱을 어떻게 알게 되나요? (검색/추천/광고/지인)
- 처음 5초에 뭘 보나요? 로그인 없이 볼 수 있나요? 빈 화면에는 뭐가 있나요?
- '아 이거 좋네'라고 느끼는 순간은 언제인가요?
- 매일/매주 다시 오는 이유는 무엇인가요?
- 한 달 떠난 사용자를 다시 데려올 전략은?

### Phase 6 — Stakeholder / JTBD (full+)

- 주 사용자 상황을 1문장으로: "When <상황>, I want to <동기>, so I can <결과>."
- 결제가 필요하면 누가 돈을 내나요? (사용자 / 회사 / 무료)
- 팀이 쓰는 앱인가요, 혼자 쓰는 앱인가요?
- 이 앱 대신 경쟁 앱을 쓰는 이유는?

## Convergence Check

After each phase, run:

```
score_ambiguity(
  interview_state=<json with all collected answers>,
  tier="<tier>",
  questions_asked=<N>
)
```

**Convergence requires ALL THREE:**
1. `ambiguity ≤ target` (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01 / deep 0.005)
2. `floors_passed` is true
3. `min_questions_met` is true (minimal 5 / standard 10 / thorough 20 / full 30 / deep 40)

If not converged: inspect `dimension_scores` for the highest-scoring dimension and ask
more questions targeting that dimension. **No cap on reprompts** — keep asking until
all three conditions hold.

## Save Interview Results

Write to `.samvil/interview-summary.md`:

```markdown
# Interview Summary

## 사용자 / 문제
- 주 사용자: <target_user>
- 핵심 문제: <core_problem>
- 핵심 경험: <core_experience>

## 핵심 기능
<features list>

## 제외 범위
<exclusions list>

## 기술 제약
<constraints list>

## 수용 기준
<acceptance_criteria — each must include measurable target>

## 인터뷰 메타
- tier: <tier>
- questions_asked: <N>
- final_ambiguity: <score>
- dimensions: <dimension_scores json>
```

## Chain

Run: `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-interview")`

Tell the user: "인터뷰 완료! 다음 단계를 실행하세요."
