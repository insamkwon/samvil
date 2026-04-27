# SAMVIL Interview Stage (Codex CLI)

## Prerequisites

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
   If `next_skill` is not `samvil-interview`, stop and report to user.

## Brownfield Mode Detection

Read `project.state.json`. If `_analysis_source == "brownfield"`:
- Load `_analysis_context` (framework, solution_type, existing_feature_names, warnings).
- Announce: `[SAMVIL] Brownfield Mode — 기존 코드 분석 결과 로드됨. 기술 스택·기존 기능 질문 생략.`
- Skip Phase 1 tech questions (framework/DB/auth already known from analysis).
- Replace Phase 1 with **Brownfield Goal Phase** (see below).
- Pass `pre_filled_dimensions="technical,nonfunctional"` to all `score_ambiguity` calls.
- After convergence + user approval: call `merge_brownfield_seed` (see Chain section).

## Execution

Conduct a Socratic interview in Korean. Ask **one question at a time**.
Track `questions_asked` — increment each time a question is posed to the user.

### Phase 1A — Core Understanding (Greenfield only)

- 이 앱을 만들려는 이유가 뭔가요?
- 주요 사용자는 누구인가요? (역할 + 구체적인 맥락 포함, 예: "10개 이상 프로젝트를 관리하는 프리랜서 디자이너")
- 지금 이 문제를 어떻게 해결하고 계세요? (Excel/카카오톡/노션 등)
- 핵심 기능 3가지를 꼽는다면?
- 성공 기준은 어떻게 되나요? (측정 가능한 수치 포함)

### Phase 1B — Brownfield Goal Phase (Brownfield Mode only)

Context: already know `{framework}` / `{existing_feature_names}` from analysis.
- 이 앱에서 가장 불편한 점이나 빠진 것이 뭔가요?
- 어떤 기능을 추가하거나 어떤 부분을 개선하고 싶으세요?
- 이 개선이 성공했다면 어떻게 알 수 있나요? (수치/지표)
- 기존 기능 중 절대 건드리지 말아야 할 부분은?

### Phase 2 — Scope Definition (always)

- 이 앱이 절대로 다루지 않을 것은? (최소 3가지)
- (Greenfield only) 기술 제약이 있나요? (DB 종류, 인증 방식, 배포 환경 등)
- (Greenfield only) 데이터를 어디에 저장하나요?
- (Greenfield only) 로그인이 필요한가요?

### Phase 3 — Non-functional Requirements (thorough+, Greenfield only)

- 첫 화면 로딩 목표 시간이 있나요? (기본: 2초 이내)
- 보안/개인정보 처리 요구사항이 있나요? (HTTPS, 암호화, PII 처리)
- 모바일에서도 동작해야 하나요? (최소 화면 크기: 320px?)
- 오프라인에서도 기본 동작해야 하나요?

### Phase 4 — Failure Modes / Inversion (thorough+)

- 이 앱이 6개월 후 아무도 안 쓴다면, 가장 가능성 높은 이유 3가지는?
- (Brownfield) 기존 앱의 가장 큰 약점 / 사용자가 이탈하는 원인은?
- 절대로 다루지 않을 것은? (exclusions 보강)

### Phase 5 — Lifecycle (standard+)

- 사용자가 이 앱을 어떻게 알게 되나요?
- 처음 5초에 뭘 보나요? 빈 화면에는 뭐가 있나요?
- 매일/매주 다시 오는 이유는 무엇인가요?

### Phase 6 — Stakeholder / JTBD (full+)

- 주 사용자 상황을 1문장으로: "When <상황>, I want to <동기>, so I can <결과>."
- 결제/비용 모델이 있나요?

## Convergence Check

After each phase, run:

```
score_ambiguity(
  interview_state=<json with all collected answers>,
  tier="<tier>",
  questions_asked=<N>,
  pre_filled_dimensions="technical,nonfunctional"  // Brownfield only; omit for Greenfield
)
```

**Convergence requires ALL THREE:**
1. `ambiguity ≤ target` (minimal 0.10 / standard 0.05 / thorough 0.02 / full 0.01 / deep 0.005)
2. `floors_passed` is true
3. `min_questions_met` is true (minimal 5 / standard 10 / thorough 20 / full 30 / deep 40;
   reduced by 1 per pre-filled dim in Brownfield Mode)

Inspect `dimension_scores` for the highest-scoring dimension — ask more questions targeting it.
**No cap on reprompts** — keep asking until all three conditions hold.

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
- mode: greenfield | brownfield
- dimensions: <dimension_scores json>
```

## Chain

**Greenfield:**
Run: `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-interview", next_skill="samvil-seed")`

**Brownfield:**
1. Read `project.seed.json` (existing seed from analyze stage).
2. Build `interview_state_json` from all collected answers.
3. Run MCP tool: `merge_brownfield_seed(existing_seed_json=<project.seed.json contents>, interview_state_json=<answers>, new_features_json="[]")`.
4. Write merged result to `project.seed.json`.
5. Run: `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-interview", next_skill="samvil-build")`.
6. Tell user: "인터뷰 완료! Seed 병합 완료. 다음: `codex samvil-build 실행`"
