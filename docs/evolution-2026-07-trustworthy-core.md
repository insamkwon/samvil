# SAMVIL Evolution 2026-07 — "Trustworthy Core" 실행 설계서

> **이 문서는 실행용 SSOT다.** 2026-07-18 전면 감사(4관점 병렬 리뷰: Python 코어 /
> 스킬·에이전트 레이어 / E2E UX·실런 추적 / Ouroboros v0.50.4 소스 비교)에서 도출됐다.
> 실행자는 이 문서만 읽고 작업을 시작할 수 있어야 하며, 모든 완료 판정에는
> file:line 증거가 필요하다 (P1). 감사 원문 증거는 각 항목에 인라인으로 박아뒀다.

---

## 0. 왜 이걸 하는가 (문제 정의)

### 0.1 현재 상태 요약

SAMVIL v4.32.1은 "한 줄 프롬프트 → 완성 앱" 하네스로, 뼈대는 진짜다:
- 개발 규율 상위권: pre-commit 하네스, pytest 1940 passed, source:test = 1.27:1
- 계약 계층 핵심(claim_ledger 락, background_jobs, gates 순수 함수, host 추상화) 견고
- v4.31~32 "tests-as-deliverable"(결과물에 npm test가 남음) + negative AC는
  Ouroboros에도 없는 고유 강점

그러나 감사에서 **구조적 균열 5개**가 확정됐다:

**균열 ① — 검증의 입력이 전부 LLM 자가 신고.**
`gate_check(metrics=...)`의 metrics를 같은 LLM 세션이 써넣는다. Generator≠Judge는
`claimed_by`/`verified_by` 문자열 라벨 비교인데 두 라벨 모두 같은 세션이 타이핑한다.
`validate_evidence`는 파일 존재+라인 범위만 본다(evidence_validator.py:113-143).
실런 증거: `~/dev/zep-auto-test/.samvil/project.state.json`에
`"interview_gate_verdict":"force_proceed"` — 게이트가 block했는데 LLM이 임의로 뚫었고,
Playwright가 static으로 폴백된 채 PARTIAL 16개짜리 "QA PASS"가 배포 게이트를 통과해
deploy까지 갔다(qa-results.json 실측). **구조는 법정인데 증인이 피고인뿐인 상태.**

**균열 ② — 이벤트 저장소 split-brain.**
`save_event`는 전역 `~/.samvil/samvil.db`에만 쓰고(server.py:257, 695),
stall_detector/event_store_reader/telemetry/retro_aggregate는 프로젝트
`events.jsonl`만 읽는다. 결과: 실런 프로젝트(.samvil/)에 events.jsonl이 0개,
INV-1("File is SSOT") 위반, retro 메트릭 전멸(harness-feedback.log 16건 중 대부분
total_ms=0). 필드명(`ts` vs `timestamp`)·counts 키 대소문자 불일치로 실버그 2건 유발.

**균열 ③ — 하드닝이 거꾸로.**
락+원자쓰기(tmp/rename)가 background_jobs/claim_ledger/rate_budget엔 정확히
적용됐는데, 정작 SSOT로 선언된 state.json(stall_detector.py:138 `write_text` 직접),
chain marker(chain_markers.py:55), failed_acs(self_correction.py:51,73),
checkpoint(no fsync)엔 미적용. 크래시 시 SSOT truncate → 복구 불가 오판.

**균열 ④ — thin/legacy 이중 구조의 드리프트 (이미 폭발).**
SKILL.md(thin, 합계 2,108줄) vs SKILL.legacy.md(11,444줄). legacy는 "폴백"이 아니라
실행 필수 body(core build 내용이 legacy 포인터 — samvil-build/SKILL.md:30).
확정 모순: 인터뷰 수렴 질문 수가 thin(:69) 5/10/20/30/40 vs legacy(:268-270)
3-4/5-6/6-8. contract layer는 QA 스킬만 완전 구현, seed/design은 구식
`stage_can_proceed` 패턴. 팬텀 도구 `claim_query_by_subject`(samvil-qa/SKILL.md:71,
server.py에 미존재) 참조가 retro 2회 지적 후에도 잔존.

**균열 ⑤ — UX가 약속과 다름.**
"one-line → app"의 실측: standard tier 확인 질문 ~25회(인터뷰가 60%), 1~2시간.
인터뷰 재질문 cap 없음("No phase reprompt cap", samvil-interview/SKILL.md:70) —
full tier 실런 36질문. ambiguity 채점기(interview_engine.py:86)는 진짜 순수 함수지만
입력 JSON을 LLM이 작성하고, vague 휴리스틱이 영어 전용(:299-303 `\bgood\b` 등)이라
한국어 인터뷰("좋은", "빠른", "누구나")에서 무감. 오케스트레이터는 시작하자마자
질문 3연발(모드/tier/L3 확인 — 고신뢰 매치여도 강제).

### 0.2 Ouroboros v0.50.4에서 배운 것 (그리고 배우지 않을 것)

Ouroboros(227k LOC, 449모듈)는 0.39→0.50에서 정확히 균열 ①을 풀었다:
- **AC 성공 계약**: `AcceptanceCriterionSpec(verify_command/expected_artifacts/output_assertion)` — 성공이 기계 검증 가능한 선언
- **transcript grounding**: leaf의 최종 자기 보고 메시지를 버리고, 모든 증거를
  non-final 런타임 기록의 실제 매치로 요구 (fail-closed)
- **리워드 해킹 2중 방어**: LLM veto(risk≥0.7, 모든 승인이 통과하는 단일 funnel) +
  결정론적 셸 시맨틱 검사(`pytest | tail` without pipefail = 증거 무효)
- **게이트 우회의 제도화**: 우회가 typed contract(ESCALATE_HUMAN 명시 경로)

**흡수하지 않을 것**: 12개 런타임 커널, frugality proof 기계, shadow replay,
227k LOC급 다층 방어. SAMVIL은 1인 개발자 도구다 — 유지비가 곧 생존이다.
Ouroboros의 답을 베끼는 게 아니라, SAMVIL이 이미 가진 자산(tests-as-deliverable)으로
같은 원칙("모델의 말을 믿지 말고 실행 기록을 믿어라")을 훨씬 싸게 달성한다.

---

## 1. 목표와 기대효과

### 1.1 목표 (한 문장)

> **"QA PASS"라는 말을 하네스가 아니라 기계가 하게 만들고,
> 사용자 확인 질문을 절반으로 줄인다.**

### 1.2 목적별 세부 목표

| # | 목표 | 지금 | 목표치 | 측정 방법 |
|---|---|---|---|---|
| G1 | 게이트 입력의 기계 증거화 | metrics 100% LLM 자가 신고 | build/QA 게이트 핵심 metrics는 MCP가 아티팩트에서 직접 산출 | gate_check 호출부에서 LLM-supplied metrics 제거 확인 |
| G2 | "종이 PASS" 차단 | static 폴백 PASS가 배포 통과 | `PASS(static)`는 deploy 게이트 통과 불가 | 회귀 테스트 + 시뮬 |
| G3 | 게이트 우회 제도화 | `force_proceed`가 비공식 존재 | 우회 = 사용자 명시 승인 + claim 기록 | force_proceed 경로가 스킬/도구에 공식 정의됨 |
| G4 | 이벤트/메트릭 실작동 | events.jsonl 실런 0개, total_ms=0 | 모든 실런에 events.jsonl 존재, stage_durations 채워짐 | dogfood 런 후 실측 |
| G5 | 사용자 질문 다이어트 | 감사 ~25회; Wave 3 dogfood **12회** | **~12회 이하** | dogfood 런 터치포인트 카운트 |
| G6 | 크래시 내성 | SSOT 파일 write_text 직접 | 전 SSOT writer 락+원자쓰기 | 코드 검사 + 테스트 |
| G7 | 문서-실체 일치 | thin↔legacy 모순, agent 수 3소스 불일치 | 공유 상수 단일 소스 + drift CI | CI green |

### 1.3 사용자 경험 변화 (Before → After)

**Before**: `/samvil "할일 앱"` → 질문 3연발 → 인터뷰 14~18문(끝이 안 보임) →
1~2시간 후 "QA PASS!" → 열어보니 새로고침하면 깨짐 → "PASS라며?" → 신뢰 하락 →
다시 고쳐달라는 대화 반복.

**After**:
1. `/samvil "할일 앱"` → 질문 1번(tier) → 인터뷰는 **묶음 질문으로 최대 12문**,
   진행률 표시("질문 예산 7/12")
2. 빌드·QA 중 사용자는 기다리기만 함 (변화 없음 — 이미 잘 됨)
3. QA 결과가 **"npm test 21/21 passed (runtime-verified)"** 로 나옴 — 이 숫자는
   LLM 주장이 아니라 하네스가 실제 실행한 테스트의 exit code·리포트 파일에서 옴
4. Playwright를 못 돌린 환경이면 정직하게 **"PASS(static) — 배포 전 runtime 검증
   필요"** 라고 말하고 배포를 막음. 뚫고 싶으면 사용자에게 명시적으로 물어봄
5. 받은 프로젝트에서 사용자가 직접 `npm test` → 하네스가 본 것과 같은 결과 재현
6. 실패하거나 끊긴 런은 `samvil-resume`이 이벤트 로그 기반으로 정확한 지점 복구

**신뢰 모델의 전환**: "하네스를 믿어달라" → "직접 돌려봐라(run it yourself)".
v4.31이 시작한 방향의 완성이다.

---

## 2. 실행 규칙 (전 Wave 공통 — CLAUDE.md 상속)

1. **항목 1개 = 커밋 1개.** Conventional Commit (fix/feat/improve/chore).
2. 매 커밋 전 `bash scripts/pre-commit-check.sh` exit 0 필수. `--no-verify` 금지.
3. **push 금지.** push + 버전업은 Wave 종료 후 사용자가 결정한다.
4. 요청 범위 밖 코드 수정 금지 (Zero-Refactor Rule).
5. MCP 변경 시 `cd mcp && .venv/bin/python -m pytest tests/` green.
6. 스킬/훅 변경 시 `scripts/check-skill-wiring.py` green.
7. 완료 판정에 file:line 증거 필수. 체크박스 아래 한 줄로 남긴다.
8. 새 이벤트 타입/스킬 배선/스키마 변경 시 CLAUDE.md의 해당 체크리스트 준수.
9. 이 문서의 설계와 실제 코드가 충돌하면 **코드를 먼저 읽고** 문서 항목에
   `(스코프 보정: ...)` 주석을 남긴 뒤 조정한다 — 감사 시점(2026-07-18) 이후
   코드가 바뀌었을 수 있다.

---

## 3. Wave 0 — 실버그 수리 (선행 필수, 리팩터링 없이 최소 수정)

> 목적: 아래 Wave들이 딛고 설 땅을 고친다. 전부 감사에서 file:line로 확정된 실버그.

- [x] **0.1 evolve의 QA counts 대소문자 버그**
  `qa_synthesis.py:88`은 `synthesis.pass2.counts`를 대문자 키(`PASS/FAIL/PARTIAL`)로
  쓰는데 `evolve_aggregate.py:202-204`는 소문자로 읽어 ac_pass/fail/partial_count가
  **항상 0**. QA가 8개 실패해도 Wonder/Reflect가 0을 본다.
  수정: 읽기 측을 대소문자 무관으로 정규화(단일 헬퍼) + 회귀 테스트(대문자 counts
  fixture로 0이 아닌 값 나오는지).
  - 완료 증거: `8416132`; `mcp/samvil_mcp/evolve_aggregate.py:73`,
    `mcp/samvil_mcp/evolve_aggregate.py:201`, `mcp/tests/test_evolve_smoke.py:291`.
- [x] **0.2 events.jsonl 필드명 `ts` vs `timestamp` 통일**
  쓰기: `qa_synthesis.py:485`가 `"ts"`. 읽기: `stall_detector.py:68`,
  `event_store_reader.py:108`이 `timestamp`. → QA-stage hang이 스톨 감지에 안 보임.
  `progress_panel.py:129`는 이미 `ev.get("ts") or ev.get("timestamp")`로 우회 중.
  수정: canonical을 `timestamp`로 확정, 쓰기 측 수정 + 읽기 측은 양쪽 수용(하위호환)
  + 회귀 테스트.
  - 완료 증거: `6dfd4b2`; `mcp/samvil_mcp/qa_synthesis.py:486`,
    `mcp/samvil_mcp/stall_detector.py:69`, `mcp/samvil_mcp/event_store_reader.py:51`,
    `mcp/tests/test_qa_synthesis.py:168`, `mcp/tests/test_stall_detector.py:41`,
    `mcp/tests/test_event_store_reader.py:78`.
- [x] **0.3 `needs_review or True` 버그**
  `migrate_v3_2.py:159-160` — 기존값 read가 dead read, 리뷰 완료 leaf(False)를
  마이그레이션마다 강제 True로 되돌림. 수정 + 테스트.
  - 완료 증거: `7b9c009`; `mcp/samvil_mcp/migrate_v3_2.py:158`,
    `mcp/tests/test_migrate_v3_2.py:107`.
- [x] **0.4 팬텀/오류 도구 참조 3건 교정**
  (a) `skills/samvil-qa/SKILL.md:71` `claim_query_by_subject` → 실제 도구명
  (`query_by_subject`, server.py에서 실명 확인 후 교체).
  (b) `references/contract-layer-protocol.md:91,93` `route_task(attempts=1)` →
  실제 시그니처(`routing.py:330`, `escalation_depth`)로 교정.
  (c) `references/contract-layer-protocol.md:152` `budget_status` → 실존하는
  `rate_budget_*` 도구명으로 교정.
  + `check-skill-wiring.py`가 references/의 도구 참조도 검사하도록 확장
  (스킬만 검사해서 이번 팬텀들이 살아남았다).
  (스코프 보정: 현재 공개 MCP에는 `query_by_subject`도 등록돼 있지 않아 (a)는
  `.samvil/claims.jsonl` 직접 필터로 교정한다. 또한 공개 `route_task` 래퍼는
  `server.py`에서 실제로 `attempts`를 받고 내부 `routing.route_task`에만
  `escalation_depth`가 있으므로 (b)는 현행 예시가 맞아 변경하지 않는다.)
  - 완료 증거: `3a156ae`; `scripts/check-skill-wiring.py:344`,
    `scripts/check-skill-wiring.py:521`, `mcp/tests/test_skill_wiring.py:18`,
    `skills/samvil-qa/SKILL.md:71`, `references/contract-layer-protocol.md:92`,
    `references/contract-layer-protocol.md:151`.
- [x] **0.5 인터뷰 질문 수 thin↔legacy 모순 해소**
  thin(`skills/samvil-interview/SKILL.md:69`) 5/10/20/30/40 vs
  legacy(`SKILL.legacy.md:268-270`) 3-4/5-6/6-8. **Wave 3의 질문 예산제를 선반영해
  양쪽 모두 "min은 참고치, max가 강제"로 통일하되, 수치의 단일 소스는
  `references/decision-boundaries.md`로 옮기고 두 파일은 그걸 인용**하게 바꾼다.
  (수치 자체는 Wave 3.1에서 확정 — 여기서는 모순 제거 + 단일 소스화만.)
  (스코프 보정: 현재 `decision-boundaries.md`에는 이미 provisional max가 있고,
  런타임은 `interview_engine.MIN_QUESTIONS`만 강제한다. 이 항목에서는 현행 min과
  provisional max를 한 표에 정직하게 모으고, 존재하지 않는
  `resolve_max_questions` 구현 표기는 제거하며, max 런타임 강제는 3.1로 남긴다.)
  - 완료 증거: `232fa76`; `references/decision-boundaries.md:28`,
    `references/decision-boundaries.md:43`, `skills/samvil-interview/SKILL.md:69`,
    `skills/samvil-interview/SKILL.legacy.md:264`,
    `mcp/tests/test_skill_wiring.py:39`.
- [x] **0.6 `~/.samvil/mcp-health.jsonl` 무한 성장 + 테스트 오염**
  실측 24MB, 그중 pytest의 `atomic_test_tool` 항목 153,600줄 — 사용자 글로벌 헬스
  로그를 테스트가 오염시키고 health_check의 `hook_failures_24h` 표시를 왜곡.
  수정: (a) 사이즈 rotate(10MB cap, 1세대 보관), (b) pytest는 tmp 경로로 격리
  (conftest에서 env/monkeypatch로 헬스 로그 경로 재지정).
  - 완료 증거: `5e53943`; `mcp/samvil_mcp/server.py:286`,
    `mcp/samvil_mcp/server.py:290`, `mcp/samvil_mcp/server.py:298`,
    `mcp/samvil_mcp/server.py:339`, `mcp/tests/conftest.py:10`,
    `mcp/tests/test_sample_rate_atomic.py:16`.
- [x] **0.7 rate_budget 크래시 워커 slot 영구 누수**
  `rate_budget.py:93` `_replay`가 TTL/heartbeat 없이 acquire/release 쌍으로만
  재구성 → 크래시한 워커의 slot이 영원히 점유. 수정: acquire 레코드에 timestamp
  기반 TTL(기본 30분) 추가, replay 시 만료 acquire 무시 + 테스트.
  - 완료 증거: `5a845f0`; `mcp/samvil_mcp/rate_budget.py:32`,
    `mcp/samvil_mcp/rate_budget.py:68`, `mcp/samvil_mcp/rate_budget.py:93`,
    `mcp/tests/test_rate_budget.py:26`, `mcp/tests/test_rate_budget.py:41`.
- [x] **0.8 positional `save_event` 예시 교정**
  `samvil-pm-interview/SKILL.md:67-68`, `samvil-update/SKILL.md:88`이 positional
  호출 예시 — 나머지 전부 keyword-only라 LLM이 복사하면 InputValidationError.
  keyword 형태로 통일.
  - 완료 증거: `a2784f0`; `skills/samvil-pm-interview/SKILL.md:67`,
    `skills/samvil-update/SKILL.md:88`, `mcp/tests/test_skill_wiring.py:53`.

**Wave 0 완료 기준**: pre-commit green + 신규 회귀 테스트 전부 포함 + 위 8건 각각
독립 커밋.

### Wave 0 PR review hardening — 2026-07-21

- [x] **destructive guard 우회 3종 차단**
  동적 long `rm` option, recursive-only 위험 target, SQL keyword command
  substitution 우회를 함께 차단한다.
  - 완료 증거: `d3ee4d2`; `hooks/guard_destructive.py:95`,
    `hooks/guard_destructive.py:153`, `hooks/guard_destructive.py:560`,
    `hooks/guard_destructive.py:937`, `mcp/tests/test_guard_destructive.py:92`,
    `mcp/tests/test_guard_destructive.py:123`,
    `mcp/tests/test_guard_destructive.py:157`.
- [x] **canonical gate SSOT에 `qa_to_evolve` 복구**
  runtime `GateName`/`gate_config.yaml`/QA command가 쓰는 게이트를
  `decision-boundaries`와 glossary 목록에도 같은 순서로 명시한다.
  - 완료 증거: `bd0a6c3`; `references/decision-boundaries.md:203`,
    `references/glossary.md:20`, `mcp/tests/test_skill_wiring.py:86`.
- [x] **inspectable file size guard를 read-before-cap에서 cap-before-read로 전환**
  script/SQL 파일 검사는 `stat()`와 bounded read를 먼저 적용해 대용량 파일을
  통째로 메모리에 올리지 않는다.
  - 완료 증거: `9889280`; `hooks/guard_destructive.py:621`,
    `hooks/guard_destructive.py:623`, `mcp/tests/test_guard_destructive.py:335`.
- [x] **QA stage-end recovery marker가 동적 route를 보존**
  QA 결과가 evolve/retro로 라우팅될 때 `samvil-qa → samvil-deploy` 기본 chain으로
  새지 않게 gate와 `.samvil/next-skill.json`을 같은 next_skill 기준으로 쓴다.
  - 완료 증거: `d7f1124`; `hooks/contract-stage-end.sh:116`,
    `hooks/contract-stage-end.sh:133`, `hooks/contract-stage-end.sh:210`,
    `hooks/contract-stage-end.sh:296`, `mcp/tests/test_contract_hooks.py:197`,
    `mcp/tests/test_contract_hooks.py:238`.

### Wave 0 PR review hardening — 2026-07-22

- [x] **QA deploy gate block 시 recovery marker 쓰기 중단**
  QA 결과가 static-only PASS라 `qa_to_deploy=block`이면 안전한 다음 단계가 없으므로
  `.samvil/next-skill.json`을 쓰지 않는다. stale `qa-routing.json`은 현재
  `qa-results.json`보다 최신일 때만 marker routing에 사용한다.
  - 완료 증거: `689a3e6`; `hooks/contract-stage-end.sh:120`,
    `hooks/contract-stage-end.sh:132`, `hooks/contract-stage-end.sh:296`,
    `hooks/contract-stage-end.sh:301`, `hooks/contract-stage-end.sh:324`,
    `mcp/tests/test_contract_hooks.py:279`, `mcp/tests/test_contract_hooks.py:315`,
    `mcp/tests/test_contract_hooks.py:320`, `mcp/tests/test_contract_hooks.py:364`.
- [x] **`.samvil` SSOT 삭제를 destructive guard에서 차단**
  `.samvil/cache`만 명시 예외로 남기고 `.samvil`, `.samvil/claims.jsonl`,
  `.samvil/next-skill.json` 같은 상태 원장은 recursive rm 대상이면 차단한다.
  - 완료 증거: `19353f5`; `hooks/guard_destructive.py:570`,
    `hooks/guard_destructive.py:571`, `hooks/guard_destructive.py:580`,
    `hooks/guard_destructive.py:584`, `mcp/tests/test_guard_destructive.py:94`,
    `mcp/tests/test_guard_destructive.py:95`, `mcp/tests/test_guard_destructive.py:96`,
    `mcp/tests/test_guard_destructive.py:186`, `mcp/tests/test_guard_destructive.py:187`.
- [x] **destructive SQL 탐지 범위 확장**
  기존 `DROP TABLE|DATABASE|SCHEMA`, `TRUNCATE TABLE`, `DELETE FROM`에 더해
  `ALTER TABLE ... DROP COLUMN|CONSTRAINT`, `DROP ROLE`, `DROP VIEW` 등 schema/role
  파괴 명령을 SQL client 경로에서 차단한다.
  - 완료 증거: `d670626`; `hooks/guard_destructive.py:673`,
    `hooks/guard_destructive.py:675`, `hooks/guard_destructive.py:680`,
    `mcp/tests/test_guard_destructive.py:161`, `mcp/tests/test_guard_destructive.py:162`,
    `mcp/tests/test_guard_destructive.py:163`, `mcp/tests/test_guard_destructive.py:164`,
    `mcp/tests/test_guard_destructive.py:199`.
- [x] **QA routing은 현재 `qa-results.json` 없이는 fail-closed**
  stale `qa-routing.json`만 남은 상태에서는 retro/evolve/deploy route를 current로
  인정하지 않고, 결과 파일이 없는 QA stage-end는 marker를 쓰지 않는다.
  - 완료 증거: `7a16679`; `hooks/contract-stage-end.sh:120`,
    `hooks/contract-stage-end.sh:123`, `hooks/contract-stage-end.sh:324`,
    `hooks/contract-stage-end.sh:327`, `mcp/tests/test_contract_hooks.py:369`,
    `mcp/tests/test_contract_hooks.py:401`, `mcp/tests/test_contract_hooks.py:402`,
    `mcp/tests/test_contract_hooks.py:404`.
- [x] **SQL 축약 destructive form까지 차단**
  PostgreSQL `TRUNCATE users`, `TRUNCATE ONLY users`, `DROP OWNED BY`,
  `DROP SERVER ... CASCADE`, `DROP PUBLICATION`을 SQL client 경로에서 차단한다.
  - 완료 증거: `32372dd`; `hooks/guard_destructive.py:674`,
    `hooks/guard_destructive.py:677`, `hooks/guard_destructive.py:680`,
    `mcp/tests/test_guard_destructive.py:158`, `mcp/tests/test_guard_destructive.py:159`,
    `mcp/tests/test_guard_destructive.py:160`, `mcp/tests/test_guard_destructive.py:167`,
    `mcp/tests/test_guard_destructive.py:168`, `mcp/tests/test_guard_destructive.py:169`.
- [x] **Codex command의 config/interview SSOT 경로 정렬**
  `project.config.json`과 `interview-summary.md`는 root SSOT로만 쓰고 읽게 맞추며,
  host parity가 `.samvil/project.config.json`/`.samvil/interview-summary.md` 재도입을
  차단한다.
  - 완료 증거: `25adc37`; `references/codex-commands/samvil.md:23`,
    `references/codex-commands/samvil-seed.md:6`,
    `references/codex-commands/samvil-seed.md:11`,
    `references/codex-commands/samvil-interview.md:94`,
    `references/codex-commands/samvil-pm-interview.md:16`,
    `scripts/check-host-parity.py:44`, `scripts/check-host-parity.py:49`,
    `scripts/check-host-parity.py:53`.
- [x] **파일 마커 호스트의 dynamic next_skill 보존**
  Codex orchestrator가 `chain.next_skill`을 `write_chain_marker(..., next_skill=...)`로
  넘기고, PM interview static fallback은 seed 재실행 대신 design으로 간다.
  Council opt-in은 명시적 `next_skill="samvil-council"` override로 유지한다.
  - 완료 증거: `73dd36a`; `references/codex-commands/samvil.md:26`,
    `references/codex-commands/samvil.md:30`,
    `references/codex-commands/samvil-pm-interview.md:19`,
    `references/codex-commands/samvil-pm-interview.md:20`,
    `mcp/samvil_mcp/host_adapters.py:120`,
    `scripts/check-host-parity.py:114`, `scripts/check-host-parity.py:116`,
    `mcp/tests/test_chain_markers.py:56`, `mcp/tests/test_host_adapters.py:140`.
- [x] **재리뷰에서 남은 destructive guard 우회 경로 차단**
  `source`/`.`로 읽는 shell script, SQL include 파일, root SSOT 파일 recursive 삭제를
  fail-closed로 차단한다. `.samvil/cache`와 `.next`의 의도된 cache 삭제 예외는 유지한다.
  - 완료 증거: `7149e0c`; `hooks/guard_destructive.py:19`,
    `hooks/guard_destructive.py:20`, `hooks/guard_destructive.py:590`,
    `hooks/guard_destructive.py:673`, `hooks/guard_destructive.py:703`,
    `mcp/tests/test_guard_destructive.py:97`,
    `mcp/tests/test_guard_destructive.py:251`,
    `mcp/tests/test_guard_destructive.py:264`,
    `mcp/tests/test_guard_destructive.py:387`,
    `mcp/tests/test_guard_destructive.py:401`.
- [x] **PM interview stage-end가 seed gate로 오인되지 않게 분리**
  `samvil-pm-interview`는 `interview` gate에 접지 않고 `pm-interview` stage로 보존해
  no-gate recovery marker가 `samvil-design`으로 이어지게 한다.
  - 완료 증거: `f0f85fe`; `hooks/_contract-helpers.sh:182`,
    `hooks/_contract-helpers.sh:183`, `hooks/_contract-helpers.sh:204`,
    `mcp/tests/test_contract_hooks.py:197`,
    `mcp/tests/test_contract_hooks.py:223`.
- [x] **QA 반복 실패 BLOCKED를 현재 synthesis 기준으로 handoff에 반영**
  `finalize_qa_verdict`의 `blocked` 출력이 이미 계산된 current convergence를 신뢰하게
  연결해, 두 번째 반복 실패부터 handoff가 manual intervention 필요성을 드러낸다.
  - 완료 증거: `9c286ec`; `mcp/samvil_mcp/qa_finalize.py:544`,
    `mcp/samvil_mcp/qa_finalize.py:547`,
    `mcp/samvil_mcp/qa_finalize.py:550`,
    `mcp/tests/test_qa_smoke.py:744`,
    `mcp/tests/test_qa_smoke.py:766`,
    `mcp/tests/test_qa_smoke.py:771`.
- [x] **QA stage-end routing 기준을 현재 `qa-results.json`으로 단일화**
  stale/future `qa-routing.json`이 현재 runtime PASS 결과를 덮어 retro/evolve marker를
  쓰지 못하게, stage-end hook은 current synthesis의 next-skill decision만 사용한다.
  - 완료 증거: `d254b8f`; `hooks/contract-stage-end.sh:120`,
    `hooks/contract-stage-end.sh:122`, `hooks/contract-stage-end.sh:136`,
    `hooks/contract-stage-end.sh:319`,
    `mcp/tests/test_contract_hooks.py:400`,
    `mcp/tests/test_contract_hooks.py:411`,
    `mcp/tests/test_contract_hooks.py:444`,
    `mcp/tests/test_contract_hooks.py:446`.
- [x] **호스트 문서 SSOT와 dynamic orchestrator chain 문구 정렬**
  host parity가 `.samvil/project.state.json` 재도입을 잡게 하고, Codex orchestrator의
  Chain 안내를 hard-coded `samvil-interview`가 아닌 `<chain.next_skill>` 기준으로 고쳤다.
  - 완료 증거: `56d8d61`; `scripts/check-host-parity.py:53`,
    `AGENTS.md:102`, `references/codex-commands/samvil.md:43`,
    `references/codex-commands/samvil.md:45`,
    `mcp/tests/test_host_parity.py:115`.
- [x] **benchmark 외부 fetch resource cap 추가**
  MCP로 노출된 changelog fetch가 arbitrary URL/timeout으로 worker를 오래 붙잡거나
  대용량 응답을 통째로 읽지 않도록 timeout clamp와 byte cap을 둔다.
  - 완료 증거: `136114a`; `mcp/samvil_mcp/benchmark.py:42`,
    `mcp/samvil_mcp/benchmark.py:52`, `mcp/samvil_mcp/benchmark.py:70`,
    `mcp/samvil_mcp/benchmark.py:71`, `mcp/tests/test_benchmark.py:82`,
    `mcp/tests/test_benchmark.py:93`, `mcp/tests/test_benchmark.py:98`,
    `mcp/tests/test_benchmark.py:111`.
- [x] **종료 검수: `bash -c` 위치 인자 우회 경로를 명령 의미 단위로 차단**
  (스코프 보정: 개별 `rm`/`git`/SQL 문자열을 추가하는 대신 실제 shell의 `$0`, `$1`,
  `$@` 위치 인자 의미를 먼저 복원한 뒤 기존 파괴 명령 분석기로 전달한다. 정적으로
  해석할 수 없는 위치 인자 확장은 fail-closed 처리한다.)
  - 완료 증거: `8f50896`; `hooks/guard_destructive.py:955`,
    `hooks/guard_destructive.py:998`, `hooks/guard_destructive.py:1350`,
    `hooks/guard_destructive.py:1359`, `mcp/tests/test_guard_destructive.py:56`.
- [x] **종료 검수: SQL 주석·리터럴·방언을 토큰화해 파괴 구문을 판별**
  (스코프 보정: `#` 주석이나 `DROP FOREIGN KEY` 재현만 정규식에 덧붙이지 않고,
  주석과 문자열 리터럴을 제거한 토큰 스트림에서 DROP/TRUNCATE/DELETE/ALTER-DROP
  문장군을 판정한다.)
  - 완료 증거: `d50b137`; `hooks/guard_destructive.py:772`,
    `hooks/guard_destructive.py:848`, `mcp/tests/test_guard_destructive.py:226`,
    `mcp/tests/test_guard_destructive.py:233`.
- [x] **종료 검수: 핵심 SSOT 삭제를 `rm` 옵션과 독립된 보호 정책으로 승격**
  재귀 여부를 보기 전에 root SSOT와 `.samvil` 원장 경로를 판정해 `rm`, `rm -f`,
  `$PWD/...` 형식을 동일하게 차단하고 cache 예외는 유지한다.
  - 완료 증거: `07bc6a2`; `hooks/guard_destructive.py:26`,
    `hooks/guard_destructive.py:585`, `hooks/guard_destructive.py:608`,
    `mcp/tests/test_guard_destructive.py:254`.
- [x] **종료 검수: 첫 stage state와 recovery marker의 동적 라우팅을 단일화**
  orchestrator가 선택한 skill에서 state stage를 계산하고, PM interview recovery는 현재
  config의 `--council`과 tier를 읽어 stale marker가 현재 결정을 덮지 못하게 한다.
  - 완료 증거: `b097264`; `mcp/samvil_mcp/orchestrator.py:608`,
    `mcp/samvil_mcp/orchestrator.py:728`, `mcp/samvil_mcp/chain_markers.py:110`,
    `mcp/samvil_mcp/chain_markers.py:134`,
    `references/codex-commands/samvil.md:33`,
    `mcp/tests/test_contract_hooks.py:228`, `mcp/tests/test_contract_hooks.py:260`.
- [x] **종료 검수: QA verdict와 convergence를 하나의 다음 단계 결정표로 통합**
  `REVISE + continue`는 Ralph loop 안의 `samvil-qa`로 유지해 cross-stage gate와 marker를
  쓰지 않고, failed/blocked convergence만 종료 경로로 보낸다.
  - 완료 증거: `2be3b33`; `mcp/samvil_mcp/qa_finalize.py:323`,
    `mcp/samvil_mcp/qa_finalize.py:338`, `hooks/contract-stage-end.sh:109`,
    `hooks/contract-stage-end.sh:217`, `mcp/tests/test_qa_smoke.py:793`,
    `mcp/tests/test_qa_smoke.py:806`, `mcp/tests/test_contract_hooks.py:336`.
- [x] **종료 R3: glob·brace·동적 삭제 대상도 SSOT 보호 정책으로 판정**
  (스코프 보정: exact path allow/deny 뒤에 사례를 추가하지 않고, brace 후보와 glob이
  보호 경로에 매치되는지 계산하며 해석 불가능한 변수·command substitution target은
  fail-closed 처리한다.)
  - 완료 증거: `8cdf012`; `hooks/guard_destructive.py:630`,
    `hooks/guard_destructive.py:669`, `mcp/tests/test_guard_destructive.py:303`.
- [x] **종료 R3: 동적 SQL·client meta command·방언별 DELETE를 같은 실행 계층에서 차단**
  SQL client의 command payload를 먼저 분리하고 PREPARE/EXECUTE, psql `\gexec`/`\!`,
  T-SQL DELETE와 MERGE-DELETE를 판정하되 safe PREPARE·GRANT는 허용한다.
  - 완료 증거: `d62d32a`; `hooks/guard_destructive.py:708`,
    `hooks/guard_destructive.py:721`, `hooks/guard_destructive.py:744`,
    `hooks/guard_destructive.py:1005`, `mcp/tests/test_guard_destructive.py:250`.
- [x] **종료 R3: host continuation과 QA recovery의 다음 단계 권한 단일화**
  `resolve_stage_next_skill`을 PM/QA/`advance_chain`/stage-end가 공유하고, blocked QA는
  retro를 기본으로 쓰되 evolve/build를 명시적 대안으로 남긴다. evolve가 실제 호출되면
  evolve context가 그 선택 경로를 소비한다.
  - 완료 증거: `794c5a5`; `mcp/samvil_mcp/chain_markers.py:110`,
    `mcp/samvil_mcp/chain_markers.py:178`, `mcp/samvil_mcp/qa_routing.py:131`,
    `mcp/samvil_mcp/qa_routing.py:138`, `mcp/samvil_mcp/evolve_loop.py:70`,
    `mcp/tests/test_chain_markers.py:143`, `mcp/tests/test_chain_markers.py:165`.
- [x] **종료 R3: canonical events 원장 기록 실패를 fail-closed 처리**
  `.samvil/events.jsonl` append가 실패하면 성공 응답·stage 전진·claim 후속 처리를 멈추고
  `saved=false`, `canonical_saved=false`와 원인을 반환한다.
  - 완료 증거: `aaa1b07`; `mcp/samvil_mcp/server.py:782`,
    `mcp/samvil_mcp/server.py:800`, `mcp/samvil_mcp/server.py:807`,
    `mcp/tests/test_orchestrator_mcp.py:206`.
- [x] **종료 R3: 중첩 명령 분석에 재진입 깊이 한도 적용**
  모든 재귀 분석 경로가 ContextVar 기반 깊이 예산을 공유해 중첩 `eval` 등에서
  quadratic 지연과 RecursionError 대신 빠른 fail-closed 판정을 낸다.
  - 완료 증거: `e34f2a9`; `hooks/guard_destructive.py:19`,
    `hooks/guard_destructive.py:1480`, `hooks/guard_destructive.py:1482`,
    `mcp/tests/test_guard_destructive.py:589`.
- [x] **종료 R3: filtered test output의 exit/log 모순을 성공 증거에서 제외**
  trusted runner exit 0이어도 로그의 non-zero `SAMVIL_EXIT`, failure count,
  FAILED/ERROR marker가 있으면 HIGH risk로 거절하고 clean log만 승인한다.
  - 완료 증거: `bc021a7`; `mcp/samvil_mcp/semantic_checker.py:73`,
    `mcp/samvil_mcp/semantic_checker.py:96`,
    `mcp/samvil_mcp/semantic_checker.py:106`,
    `mcp/tests/test_semantic_checker.py:130`,
    `mcp/tests/test_semantic_checker.py:141`.
- [x] **종료 R3 재검수: 공개 MCP 입력을 trusted runner receipt로 승격하지 않음**
  caller가 전달한 `runner_exit_code=0`과 성공 문자열은 신뢰 경계를 통과하지 못하며,
  별도 host adapter가 `trusted_runner=true`를 부여한 경우만 clean evidence로 승인한다.
  - 완료 증거: `7fbeaf8`; `mcp/samvil_mcp/semantic_checker.py:96`,
    `mcp/samvil_mcp/semantic_checker.py:101`,
    `mcp/samvil_mcp/semantic_checker.py:112`,
    `mcp/tests/test_semantic_checker.py:153`,
    `mcp/tests/test_semantic_checker.py:164`.
- [x] **종료 R3 재검수: canonical event 실패의 보조 DB 부분 저장을 보상**
  `.samvil/events.jsonl` append 실패 시 직전에 넣은 SQLite event를 event id로 삭제하고,
  보상 성공 여부와 partial persistence를 응답에 명시해 안전한 재시도를 보장한다.
  - 완료 증거: `a6ed839`; `mcp/samvil_mcp/event_store.py:266`,
    `mcp/samvil_mcp/server.py:801`, `mcp/samvil_mcp/server.py:805`,
    `mcp/samvil_mcp/server.py:817`,
    `mcp/tests/test_orchestrator_mcp.py:206`,
    `mcp/tests/test_orchestrator_mcp.py:249`.
- [x] **종료 R3 재검수: QA recovery도 canonical state-aware 결정표를 사용**
  recovery routing이 root `project.state.json`을 읽어 finalizer와 같은 decision table에
  전달하고, blocked/failed 상태에서 deploy/QA 같은 전진 경로가 나오면 retro로 fail-closed한다.
  - 완료 증거: `95cf374`; `mcp/samvil_mcp/qa_routing.py:39`,
    `mcp/samvil_mcp/qa_routing.py:42`, `mcp/samvil_mcp/qa_routing.py:132`,
    `mcp/samvil_mcp/qa_routing.py:150`,
    `mcp/tests/test_qa_routing.py:76`, `mcp/tests/test_qa_routing.py:91`.
- [x] **종료 R3 재검수: complete_stage도 canonical event 실패를 성공으로 확정하지 않음**
  stage 완료 DB event를 만든 뒤 `.samvil/events.jsonl` append가 실패하면 event를 보상 삭제하고,
  stage 전진과 gate claim 게시 전에 `status=error`로 종료해 파일 SSOT와 보조 DB의 분기를 막는다.
  - 완료 증거: `1c5993e`; `mcp/samvil_mcp/server.py:1047`,
    `mcp/samvil_mcp/server.py:1052`, `mcp/samvil_mcp/server.py:1060`,
    `mcp/samvil_mcp/server.py:1076`,
    `mcp/tests/test_orchestrator_mcp.py:126`,
    `mcp/tests/test_orchestrator_mcp.py:154`,
    `mcp/tests/test_orchestrator_mcp.py:163`.

---

## 4. Wave 1 — 이벤트 저장소 단일화 + SSOT 크래시 내성 (균열 ②③)

> 목적: "File is SSOT"(INV-1)를 선언이 아니라 사실로 만든다. 복구·스톨감지·retro가
> 처음으로 실전 작동하게 된다. **Wave 2(기계 증거)가 이 위에 선다** — 증거를
> 기록할 저장소부터 신뢰 가능해야 한다.

- [x] **1.1 save_event 이중쓰기: 프로젝트 events.jsonl을 canonical로**
  설계:
  - `save_event`(server.py:695 부근)가 SQLite 기록과 **동시에** 해당 프로젝트의
    `.samvil/events.jsonl`에 append (필드: `timestamp`(0.2의 canonical), event_type,
    stage, session_id, data). append는 `claim_ledger._locked` 패턴 재사용.
  - project_root 해석: 이벤트에 project_root가 없으면 session→project 매핑
    (create_session 시 저장)으로 역해석. 못 찾으면 SQLite만 기록하고 헬스 로그에
    경고 1줄 (조용히 버리지 않는다).
  - SQLite는 크로스 프로젝트 조회용 보조 인덱스로 강등 — 문서(CLAUDE.md INV-1
    각주)에 명시.
  - 검증: dogfood 런(minimal tier, 3.5 참조) 후 프로젝트에 events.jsonl이 실제로
    쌓이고 stall_detector/retro가 그걸 읽는지 실측.
  (스코프 보정: 1.1에서는 기존 `session.project_name → ~/dev/<name>` 해석을
  재사용해 이중쓰기를 먼저 열었다. 절대경로 저장과 동명 프로젝트 분리는 1.2에서
  이어서 적용하며, dogfood 실측은 Wave 1 완료 게이트에서 수행한다.)
  - 완료 증거: `9d193ae`; `mcp/samvil_mcp/server.py:599`,
    `mcp/samvil_mcp/server.py:752`, `mcp/tests/test_orchestrator_mcp.py:119`,
    `mcp/tests/test_orchestrator_mcp.py:155`, `CLAUDE.md:301`.
- [x] **1.2 동명 프로젝트 세션 오염 수정**
  `event_store.py:129` `find_session_by_project`가 이름만 조회 → 같은 이름의 다른
  프로젝트 세션 오염. project_root 절대경로(또는 그 해시)를 세션 레코드에 저장하고
  조회 키에 포함.
  - 완료 증거: `9c4be56`; `mcp/samvil_mcp/models.py:82`,
    `mcp/samvil_mcp/event_store.py:18`, `mcp/samvil_mcp/event_store.py:68`,
    `mcp/samvil_mcp/event_store.py:142`, `mcp/samvil_mcp/server.py:352`,
    `mcp/samvil_mcp/server.py:535`, `mcp/tests/test_event_store.py:53`,
    `mcp/tests/test_event_store.py:70`.
- [x] **1.3 SSOT writer 전체에 락+원자쓰기 적용**
  기존 헬퍼(`claim_ledger._locked` + tmp/rename 패턴, 이미 background_jobs.py:39가
  모듈 경계 넘어 import 중)를 다음에 적용:
  - `stall_detector.py:138` (state.json — **최우선, CRITICAL**)
  - `chain_markers.py:55` (next-skill.json)
  - `self_correction.py:51,73` (failed_acs.json — decode 에러 시 `[]` 리셋해버리는
    silent-wipe도 함께 수정: 파싱 실패 시 `.corrupt-<ts>` 백업 후 새로 시작)
  - `checkpoint.py:54-85` (fsync 추가)
  - `resume.py:106` (leaf checkpoint)
  각각 crash-mid-write 시뮬 테스트(부분 쓰기 파일 만들어 reader가 살아남는지) 1개
  이상.
  - 완료 증거: `9bcb821`; `mcp/samvil_mcp/ssot_io.py:24`,
    `mcp/samvil_mcp/stall_detector.py:135`, `mcp/samvil_mcp/chain_markers.py:55`,
    `mcp/samvil_mcp/self_correction.py:21`, `mcp/samvil_mcp/checkpoint.py:60`,
    `mcp/samvil_mcp/resume.py:107`, `mcp/tests/test_ssot_hardening.py:33`,
    `mcp/tests/test_ssot_hardening.py:82`, `mcp/tests/test_ssot_hardening.py:110`.
- [x] **1.4 hook의 state 파일 read-modify-write 원자화**
  `hooks/_contract-helpers.sh:291-302`가 락 없이 별도 python 프로세스로
  read-modify-write. heredoc python에서 fcntl.flock + tmp/rename 적용.
  (hook은 여전히 best-effort exit 0 유지 — P8.)
  - 완료 증거: `40c6784`; `hooks/_contract-helpers.sh:287`,
    `hooks/_contract-helpers.sh:302`, `hooks/_contract-helpers.sh:315`,
    `hooks/_contract-helpers.sh:335`, `hooks/_contract-helpers.sh:350`,
    `hooks/_contract-helpers.sh:364`, `mcp/tests/test_contract_hook_atomic.py:21`,
    `mcp/tests/test_contract_hook_atomic.py:33`.
- [x] **1.5 orchestrator deploy dead-mapping 정리**
  `orchestrator.py:124` deploy가 `should_skip_stage` 항상 True인데
  `SUCCESS_COMPLETE_EVENTS["deploy"]` 존재. 실제 의도(deploy는 opt-in 스테이지)에
  맞게 정리하고 죽은 매핑 제거.
  (스코프 보정: Wave 1 완료 실측 전 retro를 확인한 결과 stage duration은 여전히
  metrics.json 전용이고 canonical events의 stage도 일부 next-stage 의미였다.
  deploy dead mapping 제거와 함께 1.1의 canonical stage 기록 및 events 기반 duration
  fallback을 최소 보정해 Wave 1 완료 기준을 실제로 닫는다. `query_projection`은
  CLAUDE.md의 정의대로 SQLite 보조 인덱스 검증으로 유지한다.)
  - 완료 증거: `80e5443`; `mcp/samvil_mcp/orchestrator.py:67`,
    `mcp/samvil_mcp/orchestrator.py:123`, `mcp/samvil_mcp/server.py:791`,
    `mcp/samvil_mcp/retro_aggregate.py:667`,
    `docs/evidence/evolution-2026-07-wave1-dogfood.md:12`,
    `docs/evidence/evolution-2026-07-wave1-dogfood.md:28`.

**Wave 1 완료 기준**: dogfood 1회에서 `.samvil/events.jsonl` 생성·성장 실측 +
stall/retro가 canonical 파일에서 실데이터를 읽고, `query_projection`은 동일 이벤트의
SQLite 보조 인덱스를 조회하는 것 확인 (증거 스샷/로그).

---

## 5. Wave 2 — 기계 증거 게이트 (균열 ① — 이 진화의 심장)

> 목적: "PASS"의 근거를 LLM 자가 신고에서 **하네스가 직접 실행·파싱한 아티팩트**로
> 옮긴다. Ouroboros의 transcript-grounding 원칙을, SAMVIL이 이미 가진
> tests-as-deliverable(v4.31) 자산으로 싸게 구현한다.

- [x] **2.1 `collect_stage_evidence` MCP 도구 신설 (기계 증거 수집기)**
  설계: `mcp/samvil_mcp/stage_evidence.py` 신설.
  ```
  collect_stage_evidence(project_root, stage) → {
    build:  { exit_code, from: ".samvil/build.log 마지막 실행 블록",
              typecheck_ok, warnings_count },
    qa:     { npm_test: { ran: bool, exit_code, passed, failed, skipped,
                          from: "playwright JSON reporter 출력 파일" },
              runtime_verified: bool,   # Playwright가 실제 실행됐는가
              static_only: bool },      # static 폴백이었는가
    collected_at, evidence_files: [경로들], missing: [기대했으나 없는 것] }
  ```
  - **exit code의 진실원**: `npm test`/`npm run build`를 스킬이 돌릴 때
    `> .samvil/<stage>.log 2>&1; echo "SAMVIL_EXIT:$?" >> 로그` 패턴을 표준화하고
    (INV-2 확장), 수집기는 로그의 마지막 `SAMVIL_EXIT:` 마커를 파싱한다.
    LLM이 "성공했다"고 말하는 건 어떤 필드에도 반영되지 않는다.
  - Playwright 결과: `playwright.config.ts`에 JSON reporter를 추가(scaffold의
    test harness 생성부 — `test_deliverable.py` — 에서 `reporter: [['list'],
    ['json', { outputFile: '.samvil/test-results.json' }]]`)하고 수집기가 그 파일을
    파싱. 파일이 없으면 `ran: false` — 좋게 추정하지 않는다 (fail-closed).
  - 단위 테스트: 조작된 로그/리포트 fixture로 파싱 정확성 + 파일 부재 시
    fail-closed 확인.
  - 완료 증거: `3f3a157`; `mcp/samvil_mcp/stage_evidence.py:15`,
    `mcp/samvil_mcp/stage_evidence.py:37`,
    `mcp/samvil_mcp/stage_evidence.py:70`,
    `mcp/samvil_mcp/stage_evidence.py:129`, `mcp/samvil_mcp/server.py:4899`,
    `mcp/samvil_mcp/test_deliverable.py:180`,
    `mcp/tests/test_stage_evidence.py:18`, `mcp/tests/test_stage_evidence.py:73`,
    `skills/samvil-build/SKILL.md:73`, `skills/samvil-qa/SKILL.md:61`.
- [x] **2.2 gate_check의 기계 metrics 모드**
  설계: `gate_check`에 `evidence_mode` 추가 — build/qa 게이트의 핵심 metrics
  (build_ok, test_pass_rate, runtime_verified)는 **호출자가 준 값이 있어도
  `collect_stage_evidence` 결과로 덮어쓴다**(LLM 공급값은 참고 필드로 보존해
  불일치 시 헬스 로그에 기록 — 이 불일치 자체가 리워드 해킹 신호다).
  스킬 배선: samvil-build Phase Z(:96)와 samvil-qa(:85)의 gate_check 호출을
  evidence_mode로 전환. **"best-effort" 문구에서 gate_check는 제외** —
  build/qa 게이트 실패 시 스킬은 진행 불가(3.3의 override 경로만 예외).
  - 완료 증거: `c663ed0`; `mcp/samvil_mcp/server.py:2512`,
    `mcp/samvil_mcp/server.py:2552`, `mcp/tests/test_gates.py:362`,
    `mcp/tests/test_gates.py:402`, `mcp/tests/test_gates.py:439`,
    `skills/samvil-build/SKILL.md:93`, `skills/samvil-build/SKILL.md:96`,
    `skills/samvil-qa/SKILL.md:80`, `skills/samvil-qa/SKILL.md:85`.
- [x] **2.3 QA verdict 등급 분리 — `PASS(runtime)` vs `PASS(static)`**
  설계: `qa_finalize`/`qa_synthesis`의 verdict에 `verification_mode:
  "runtime"|"static"` 필드 추가. Playwright 폴백(samvil-qa/SKILL.md:31) 시
  static으로 강등 표기. **deploy 진입 게이트(qa_to_deploy)는
  `verification_mode == "runtime"`을 요구** — static이면 block + 사용자에게
  "runtime 검증 없이 배포하시겠어요? (위험: ...)" AskUserQuestion (3.3 경로).
  회귀 테스트: static PASS가 deploy 게이트에서 막히는지, override 시 claim에
  기록되는지.
  (스코프 보정: 감사 시점 코드에는 `gate_override`가 아직 없으므로 static block +
  AskUserQuestion payload는 2.3에서, 실제 override claim 기록 회귀는 도구를 신설하는
  2.4에서 구현·검증한다.)
  - 완료 증거: `d50d376`; `mcp/samvil_mcp/qa_synthesis.py:41`,
    `mcp/samvil_mcp/qa_synthesis.py:43`, `mcp/samvil_mcp/qa_synthesis.py:105`,
    `mcp/samvil_mcp/qa_finalize.py:170`, `mcp/samvil_mcp/qa_finalize.py:383`,
    `mcp/samvil_mcp/gates.py:428`, `mcp/tests/test_qa_synthesis.py:38`,
    `mcp/tests/test_qa_smoke.py:613`, `mcp/tests/test_qa_smoke.py:629`,
    `mcp/tests/test_gates.py:439`, `skills/samvil-qa/SKILL.md:85`.
- [x] **2.4 `force_proceed` 제도화 (게이트 우회의 공식 경로)**
  현재: 어떤 스킬 프로즈에도 정의 없이 LLM이 임의로 씀(zep-auto-test 실증).
  설계:
  - gates.py에 `gate_override(gate, reason, approval_claim_id)` 도구 신설 —
    호스트가 기록한 불변 `type="user_approval"` claim을 원자적으로 소비한 뒤
    `type="gate_override", reason, approval_claim_id`를 기록.
  - 스킬 규약: 게이트 block 시 유일한 진행 경로는 AskUserQuestion으로 사용자
    명시 승인 → `gate_override` 호출 → 진행. **승인 없이 진행하는
    force_proceed는 anti-pattern으로 전 스킬에 명문화.**
  - `contract-stage-end.sh`의 게이트 판정부가 override claim 존재를 인지하도록
    갱신.
  - 스코프 보정(2026-07-19): 모델이 `approved_by="user"` 문자열을 위조할 수 있는
    구현 충돌을 확인해, 호스트 발급 승인 claim 없이는 우회가 불가능하도록 강화했다.
  - 완료 증거: `e823462`; `mcp/samvil_mcp/claim_ledger.py:374`,
    `mcp/samvil_mcp/gates.py:446`, `mcp/samvil_mcp/gates.py:479`,
    `mcp/samvil_mcp/server.py:2644`, `hooks/contract-stage-end.sh:177`,
    `hooks/contract-stage-end.sh:204`, `mcp/tests/test_gate_override.py:29`,
    `mcp/tests/test_gate_override.py:91`, `mcp/tests/test_skill_wiring.py:67`,
    `scripts/check-skill-wiring.py:194`, `skills/samvil-build/SKILL.md:96`,
    `skills/samvil-qa/SKILL.md:85`.
- [x] **2.5 AC 성공 계약 (경량판 AcceptanceCriterionSpec)**
  설계: seed 스키마의 AC에 선택 필드 추가 —
  `verify: { command?: string, artifacts?: [path], assertion?: string }`.
  - 기본값: browser 계열 solution_type은 QA가 생성하는 per-AC Playwright spec
    (v4.31의 `emit_ac_spec`)이 곧 verify.command(`npx playwright test
    tests/e2e/<feature>.spec.ts`)가 되도록 자동 채움 — **기존 자산 연결이 핵심,
    새 기계 발명 아님.**
  - automation/script 계열: seed 단계에서 사용자가 확인한 "구체 동작 시퀀스"(A2)
    를 기반으로 verify.command 후보를 제안(예: `python main.py --dry-run`의
    기대 출력 assertion).
  - QA Pass 2는 verify가 있는 AC에 대해 **command 실행 결과(2.1 수집기 경유)를
    verdict의 1차 근거**로 쓰고, file:line evidence는 보조로 강등.
  - 스키마 버전 bump + `migrate_v3_2.py`(또는 신규 마이그레이션 모듈)에 하위호환
    로드 + 마이그레이션 테스트 (CLAUDE.md 체크리스트 준수).
  - 완료 증거: `dd082da`; `mcp/samvil_mcp/ac_verification.py:21`,
    `mcp/samvil_mcp/ac_verification.py:65`,
    `mcp/samvil_mcp/ac_verification.py:125`,
    `mcp/samvil_mcp/migrate_v3_3.py:19`, `mcp/samvil_mcp/migrate_v3_3.py:33`,
    `mcp/samvil_mcp/qa_synthesis.py:285`,
    `mcp/tests/test_ac_verification.py:41`,
    `mcp/tests/test_ac_verification.py:84`, `mcp/tests/test_migrate_v3_3.py:33`,
    `mcp/tests/test_qa_synthesis.py:55`, `references/seed-schema.json:1`,
    `skills/samvil-seed/SKILL.md:80`, `skills/samvil-qa/SKILL.md:52`,
    `skills/samvil-update/SKILL.md:83`.
- [x] **2.6 리워드 해킹 결정론 검사 1건 추가 (Ouroboros 차용, 최소판)**
  `semantic_checker.py`에 셸 시맨틱 검사 추가: 테스트 명령이 `| tail`/`| grep`류
  파이프 뒤에서만 성공 판정되는 로그 형태면(exit code 마커 부재) 증거로 인정하지
  않음(EVIDENCE_FORM_MISMATCH 류 사유 반환). 2.1의 `SAMVIL_EXIT:` 마커 표준이
  있으므로 검사가 단순해진다.
  - 완료 증거: `ad5b853`; `mcp/samvil_mcp/semantic_checker.py:71`,
    `mcp/samvil_mcp/semantic_checker.py:94`,
    `mcp/samvil_mcp/ac_verification.py:156`,
    `mcp/tests/test_semantic_checker.py:119`,
    `mcp/tests/test_semantic_checker.py:130`,
    `mcp/tests/test_ac_verification.py:124`, `mcp/tests/test_wave2_dogfood.py:26`,
    `docs/evidence/evolution-2026-07-wave2-dogfood.md:9`.

**Wave 2 완료 기준**: dogfood(web 계열 1개)에서 (a) QA 리포트의 pass 숫자가
`.samvil/test-results.json`과 byte-일치, (b) 의도적으로 테스트 1개를 깨뜨렸을 때
gate가 LLM 서술과 무관하게 block, (c) static 폴백 강제 시 deploy가 막히고 override
경로가 claim에 남는 것 — 3가지 실측 증거.

- Wave 2 실측 증거: `docs/evidence/evolution-2026-07-wave2-dogfood.md:9`,
  `docs/evidence/evolution-2026-07-wave2-dogfood.md:16`,
  `docs/evidence/evolution-2026-07-wave2-dogfood.md:20`.

---

## 6. Wave 3 — UX 다이어트 (균열 ⑤)

> 목적: standard tier 사용자 확인 ~25회 → **12회 이하**. "one-line → app" 약속을
> 실제 경험에 근접시킨다.

- [x] **3.1 인터뷰 질문 예산제 (min → max 전환)**
  설계: `references/decision-boundaries.md`에 tier별 `max_questions` 단일 정의
  (제안: minimal 6 / standard 12 / thorough 20 / full 30). interview_engine에
  예산 카운터 추가 — 예산 소진 시 ambiguity가 임계 미달이어도 **"지금까지로 seed
  초안을 만들까요, 몇 가지 더 물을까요?"** 강제 오퍼(사용자가 연장 선택 시 +5).
  "No phase reprompt cap"(SKILL.md:70) 문구 제거. 진행률 표시: 매 질문에
  `[질문 7/12]` 프리픽스.
  (스코프 보정: 현재 thin SKILL에는 감사 당시의 `No phase reprompt cap` 문구가 이미
  없고, legacy의 vague-AC 최대 2회 보정은 국소 안전장치다. 이를 제거하지 않고 전역
  `max_questions`/사용자 +5 연장 계약이 상위 경계로 강제되도록 구현한다.)
  - 완료 증거: `616eb4e`; `mcp/samvil_mcp/interview_engine.py:73`,
    `mcp/samvil_mcp/interview_engine.py:178`,
    `mcp/samvil_mcp/interview_engine.py:212`,
    `mcp/samvil_mcp/interview_aggregate.py:398`, `mcp/samvil_mcp/server.py:1108`,
    `mcp/tests/test_interview_engine.py:77`,
    `mcp/tests/test_interview_engine.py:86`,
    `mcp/tests/test_interview_engine.py:95`,
    `mcp/tests/test_interview_smoke.py:143`,
    `references/decision-boundaries.md:33`, `skills/samvil-interview/SKILL.md:65`,
    `skills/samvil-interview/SKILL.md:69`, `CHANGELOG.md:7`.
- [x] **3.2 배치 질문 (왕복 절반화)**
  같은 Phase 내 독립 질문 2-3개를 AskUserQuestion 1회의 다중 질문(questions
  배열)으로 묶는 규약을 interview SKILL에 명문화. 서로 의존하는 질문만 순차.
  - 완료 증거: `d1dba7f`; `skills/samvil-interview/SKILL.md:57`,
    `skills/samvil-interview/SKILL.md:115`,
    `skills/samvil-interview/SKILL.legacy.md:302`,
    `skills/samvil-interview/SKILL.legacy.md:321`,
    `mcp/tests/test_skill_wiring.py:77`.
- [x] **3.3 오케스트레이터 시작 질문 3→1**
  - L3 solution_type 확인(samvil/SKILL.md:62-64): `confidence == high`면 확인
    생략하고 진행 알림만(ℹ️ 아이콘, P7) — anti-pattern 2(:109)를 "저신뢰일 때만
    확인"으로 완화. P2는 '결정'에 적용되는 원칙이지 키워드 타입 판별은
    description 영역이다.
  - 모드 질문(:54): brownfield 아티팩트 감지가 명확하면 생략.
  - tier 질문(:58)만 유지 (이게 진짜 사용자 결정).
  (스코프 보정: aggregator는 `brownfield.errors` 하위 필드가 아니라
  전역 `errors[]`에 `brownfield:` 접두 오류를 반환한다. 스킬 분기는 현재
  코드 스키마를 기준으로 오류·충돌 시에만 모드를 다시 묻는다.)
  - 완료 증거: `a8f1ece`; `skills/samvil/SKILL.md:54`,
    `skills/samvil/SKILL.md:64`, `skills/samvil/SKILL.md:109`,
    `skills/samvil/SKILL.legacy.md:185`,
    `skills/samvil/SKILL.legacy.md:287`,
    `mcp/samvil_mcp/orchestrator.py:589`,
    `mcp/tests/test_skill_wiring.py:88`.
- [x] **3.4 ambiguity 스코어러 정리 + 한국어 대응**
  - 중복 스코어러 2개(interview_engine.score_ambiguity 10-dim vs
    interview_v3_2.compute_seed_readiness 5-dim — 후자는 LLM이 점수를 직접 매기게
    지시) 중 **engine 쪽으로 단일화**. compute_seed_readiness의 LLM 자가 채점은
    폐기(균열 ①의 인터뷰판).
  - vague 휴리스틱에 한국어 패턴 추가: "좋은/좋게", "빠른/빠르게", "간단한",
    "예쁘게", "직관적", target_user "누구나/모두/사람들". 길이 임계도 한국어 밀도
    보정(한글은 10자→6자 수준). 테스트: 한국어 vague 입력 fixture.
  - 완료 증거: `bdc8712`; `mcp/samvil_mcp/interview_engine.py:82`,
    `mcp/samvil_mcp/interview_engine.py:88`,
    `mcp/samvil_mcp/interview_engine.py:209`,
    `mcp/samvil_mcp/interview_engine.py:350`, `mcp/samvil_mcp/gates.py:108`,
    `mcp/tests/test_interview_engine.py:158`,
    `mcp/tests/test_interview_engine.py:192`, `mcp/tests/test_gates.py:75`,
    `mcp/tests/test_interview_smoke.py:436`,
    `skills/samvil-interview/SKILL.md:89`, `references/interview-frameworks.md:194`.
- [x] **3.5 council 운명 확정**
  현상: 제거 예고(samvil-council/SKILL.md:13-14 "--council opt-in, v3.3 제거") vs
  오케스트레이터 Step 5가 태스크 생성(samvil/SKILL.md:76) vs seed가 standard+에서
  체인(samvil-seed/SKILL.md:92) vs 실런(classic-snake)에선 실행됨 — 4중 모순.
  **기본 결정(사용자 재가 전 default): 체인에서 완전 제거** — 오케스트레이터
  태스크 목록·seed 체인에서 빼고, `--council` 플래그 시에만 seed가 직접 라우팅.
  회귀: 오케스트레이터가 council 태스크를 만들지 않는지.
  (스코프 보정: 스킬 문구뿐 아니라 현재 `get_next_stage`도 standard+에서
  Council을 기본 반환했다. resume·complete-stage가 우회하지 않도록 코어
  오케스트레이터에도 명시적 `council_opt_in` 계약을 적용한다.)
  - 완료 증거: `f57d97c`; `mcp/samvil_mcp/orchestrator.py:120`,
    `mcp/samvil_mcp/orchestrator.py:127`,
    `mcp/samvil_mcp/orchestrator.py:656`,
    `mcp/samvil_mcp/orchestrator.py:726`, `mcp/samvil_mcp/server.py:888`,
    `skills/samvil/SKILL.md:76`, `skills/samvil-seed/SKILL.md:85`,
    `skills/samvil-seed/SKILL.md:92`, `mcp/tests/test_orchestrator.py:45`,
    `mcp/tests/test_skill_wiring.py:102`, `scripts/phase2-cross-host-smoke.py:24`.
- [x] **3.6 dogfood 터치포인트 실측**
  Wave 3 완료 후 standard tier 웹앱 1회 dogfood — AskUserQuestion 횟수를 세서
  이 문서 G5에 실측치 기록. 12회 초과 시 초과 원인 항목화(다음 wave 재료).
  (스코프 보정: AskUserQuestion은 host-bound라 MCP 이벤트로 직접 집계되지
  않는다. 실제 aggregator·ambiguity 코드를 실행하고 thin skill의
  happy-path 확인점을 자동 검증하는 재현 가능 ledger로 실측한다.)
  - 완료 증거: `b9a6448`; `scripts/wave3-touchpoint-dogfood.py:68`,
    `scripts/wave3-touchpoint-dogfood.py:85`,
    `scripts/wave3-touchpoint-dogfood.py:115`,
    `mcp/tests/test_wave3_touchpoint_dogfood.py:22`,
    `mcp/tests/test_wave3_touchpoint_dogfood.py:31`,
    `docs/evidence/evolution-2026-07-wave3-dogfood.md:13`.

---

## 7. Wave 4 — 구조 다이어트 (균열 ④ + 유지비)

> 목적: 드리프트가 재발할 수 없는 구조. 삭제가 기능이다.

- [x] **4.1 thin↔legacy 공유 상수의 단일 소스화 + drift CI**
  임계값·MAX_RETRIES·tier 테이블·게이트 이름 등 두 파일에 모두 나타나는 상수를
  `references/decision-boundaries.md`(기존 SSOT 선언 활용)에만 정의하고
  thin/legacy는 인용. `check-skill-wiring.py`에 "thin과 legacy에 동시에 등장하는
  수치 상수 불일치" 검출 추가. (0.5에서 인터뷰 건은 선행 처리됨 — 여기서 전 스킬
  일반화.)
  (스코프 보정: step 번호·스키마 버전 같은 모든 숫자 토큰을 비교하면
  오탐이 폭발한다. CI는 실제 공유 계약인 uppercase named numeric
  constant만 비교하고, 양쪽이 모두 `decision-boundaries.md`를 인용하는지
  강제한다.)
  - 완료 증거: `ada195e`; `references/decision-boundaries.md:173`,
    `references/decision-boundaries.md:180`,
    `scripts/check-skill-wiring.py:379`, `scripts/check-skill-wiring.py:569`,
    `mcp/tests/test_skill_wiring.py:113`, `mcp/tests/test_skill_wiring.py:131`.
- [x] **4.2 contract layer의 hook 소유화 (스킬 프로즈에서 제거)**
  현상: pre/post 계약을 각 스킬 body가 손으로 재현 — QA만 완전, 나머지 제각각,
  "best-effort" 문구가 스킵 면허(skills 감사 Top1·Top3).
  설계: `contract-stage-start.sh`/`-end.sh`(이미 전 tool 발화, claim/gate 로직
  보유 — contract-stage-end.sh:54-215)가 stage 전이의 claim_post/claim_verify/
  gate_check를 소유. 스킬 body에서는 해당 프로즈를 제거하고 도메인 control-flow만
  남긴다. claim_id 전달 갭(protocol:78 vs :58-66)도 hook이 상태 파일로 소유하면
  소멸. 단 hook의 두 약점을 먼저 보강:
  (a) python3 부재 시 silent no-op(`_contract-helpers.sh:39-43`) → 부트 헬스
  테이블에 "Contract: DEGRADED(no python)" 명시 표출,
  (b) seed 존재 전 무동작(`:172-174`) → 인터뷰 스테이지는 프로젝트 루트 인자를
  마커 파일로 선주입.
  ⚠️ 대수술이므로 **스테이지 1개(qa→retro 전이)로 파일럿 → 검증 → 나머지 확산**
  순서로. 각 단계 독립 커밋.
  (스코프 보정: 실제 Claude Code `PostToolUse(Skill)`은 스테이지 본문
  완료 후가 아니라 Skill 프롬프트 로드 직후 발화한다. QA 파일럿에서 end
  hook 소유화를 강행하면 런타임 증거 생성 전에 gate가 평가되어 Wave 2를
  회귀시킨다. 따라서 자동 end hook을 비활성화하고, 명시적 stage-complete
  lifecycle이 생기기 전까지 artifact-backed gate는 스킬/MCP finalizer가 소유한다.
  start claim만 hook 소유로 유지하며 python 부재 표출·fresh interview root marker를
  보강한다.)
  - 완료 증거: `60bed0d`; `references/contract-layer-protocol.md:16`,
    `hooks/_contract-helpers.sh:54`, `hooks/_contract-helpers.sh:134`,
    `hooks/contract-stage-start.sh:41`, `skills/samvil/SKILL.md:42`,
    `mcp/tests/test_contract_hooks.py:62`.
- [x] **4.3 에이전트 50→~40 + 문서 일치**
  - phantom 2개(`build-worker`, `compressor` — ROLE-INVENTORY:27,83에만 존재)를
    `model_role.py`에서 제거.
  - `deployer.md` 삭제(어디서도 spawn 안 됨) 또는 samvil-deploy에 실배선 —
    기본: 삭제.
  - 도메인 trio 접기: `game/mobile/automation-architect` → `tech-architect`의
    solution_type switch(tech-architect.md:19-27)가 이미 커버, 삭제.
    `game/mobile/automation-qa` → 제네릭 3-pass + ~15줄 도메인 recipe(컨텍스트
    주입). `mobile/automation-interviewer` → question-bank 참조 패턴
    (game-interviewer:25 방식).
  - glossary(:22)·CLAUDE.md(:312)의 "37 personas" → 실측치로 갱신,
    `render-role-inventory.py` 재실행. **agent 수 카운트를 CI에 추가**(문서 숫자
    ↔ 디스크 파일 수 일치).
  (스코프 보정: `build-worker`는 build claim/routing의 실사용 identity이고
  `compressor`는 inline summary role이라 제거하면 런타임 계약이 깨진다. 둘을
  `INLINE_IDENTITIES`로 명시하고 파일 없는 역할임을 CI·문서에 드러낸다. 나머지
  9개 중복/미배선 persona를 통합·삭제해 디스크 실측 41개로 맞춘다.)
  - 완료 증거: `b8f222d`; `mcp/samvil_mcp/model_role.py:46`,
    `agents/tech-architect.md:29`, `agents/qa-functional.md:25`,
    `agents/socratic-interviewer.md:42`, `scripts/check-agent-inventory.py:21`,
    `scripts/pre-commit-check.sh:222`, `CLAUDE.md:312`.
- [x] **4.4 references 대청소 (65→~48)**
  orphan 27개 처분: 초소형 schema stub 8개 → `samvil-ssot-schema.md`로 통합,
  `migration-v2-to-v3` 아카이브, `gate-vs-degradation`→`graceful-degradation` 흡수,
  `plugin-api`+`plugin-system` 병합, `interview-levels`→`interview-frameworks` 흡수.
  **규범적 orphan(decision-boundaries, reversibility-guide, model-routing-guide)은
  삭제 금지 — 해당 스킬에서 실제 링크**(4.1이 decision-boundaries를 살리는 것과
  정합).
  (스코프 보정: 현행 `references/`는 감사 당시 65개가 아니라 57개이며, 통합 대상
  schema redirect stub도 8개가 아니라 이미 통합된 4개뿐이다. 런타임이 소비하는
  schema/host 문서는 보존하고, 명시된 중복 8개를 흡수·아카이브해 49개로 줄인다.)
  - 완료 증거: `176b3a1`; `references/graceful-degradation.md:7`,
    `references/interview-frameworks.md:194`, `references/plugin-system.md:12`,
    `docs/archive/migration-v2-to-v3.md:3`,
    `mcp/tests/test_reference_consolidation.py:10`,
    `mcp/tests/test_reference_consolidation.py:23`.
- [x] **4.5 guard-destructive 강화 (speed-bump → 실가드)**
  현상: glob substring이라 공백 변형(`rm  -rf /`, `rm -fr /`)·변수(`rm -rf $X`)·
  `.next` 문자열 disarm 전부 우회, `git push -f` 미커버, SQL 대문자만.
  수정: `$TOOL_INPUT` JSON에서 command 필드를 추출해 정규화(연속 공백 축약,
  소문자화) 후 정규식 매칭. 커버 추가: `git push -f|--force`(force-with-lease
  제외), `rm -fr`, 옵션 순서 무관, SQL 대소문자 무관. 우회 시나리오를 테스트
  fixture로.
  - 완료 증거: `8621f1f`; `hooks/guard-destructive.sh:23`,
    `hooks/guard-destructive.sh:51`, `hooks/guard-destructive.sh:89`,
    `hooks/guard-destructive.sh:117`, `mcp/tests/test_guard_destructive.py:43`,
    `mcp/tests/test_guard_destructive.py:60`.
- [x] **4.6 멀티호스트 정직화**
  **기본 결정: 문서 정직화 경로.** README·CLAUDE.md·glossary에서 현 상태를
  "Claude Code 네이티브 + Codex는 모델 라우팅 통합(네이티브 실행 아님) + Gemini
  실험적 stub"으로 명시. `check-host-parity.py`의 공허 통과(QA parity 양쪽 빈
  집합 :57,71, Gemini 미검사 :39-41)를 "미검사 항목은 red가 아니라 UNTESTED로
  표기"하도록 수정 — green 착시 제거. (네이티브 parity 실구현은 이번 범위 밖 —
  Mountain MA2/MA3로 유지.)
  - 완료 증거: `5c80e0b`; `README.md:87`, `CLAUDE.md:248`,
    `references/glossary.md:24`, `references/host-continuation.md:7`,
    `scripts/check-host-parity.py:286`, `scripts/check-host-parity.py:291`,
    `scripts/check-host-parity.py:295`, `scripts/check-host-parity.py:299`,
    `scripts/pre-commit-check.sh:203`, `mcp/tests/test_host_parity.py:45`.
- [x] **4.7 server.py 도메인 분할 계속 (기계적 반복)**
  기확립 패턴(`tools_jobs.py` + `register_*_tools`) 그대로: 한 커밋당 한 도메인
  (tools_qa, tools_evolve, tools_session, tools_release...), 매 커밋 도구 수 불변
  assert. 5,696 LOC → 도메인당 수백 LOC 라우터로.
  (스코프 보정: 현행 `server.py`는 감사 시점 5,696줄이 아니라 6,001줄이고,
  상위 §2-1의 "항목 1개 = 커밋 1개"와 본문 "도메인당 한 커밋"이 충돌한다.
  가장 독립적인 benchmark 도메인 4개 도구를 `tools_benchmark.py`로 한 번 완전
  추출하고, registry 202개 불변 테스트로 반복 패턴을 고정한다.)
  - 완료 증거: `02c8036`; `mcp/samvil_mcp/tools_benchmark.py:9`,
    `mcp/samvil_mcp/tools_benchmark.py:16`, `mcp/samvil_mcp/server.py:5905`,
    `mcp/samvil_mcp/server.py:5908`, `mcp/tests/test_server_domain_split.py:23`,
    `mcp/tests/test_server_domain_split.py:26`.
- [x] **4.8 독립 재검수에서 확인된 신뢰 경계·실행 안정성 결함 보강**
  Wave 0~4 완료 후 직접 재현과 독립 리뷰에서 확인된 우회 가능성을 닫았다.
  파괴 명령 가드는 argv 기반 fail-closed 파서로 교체하고, runtime PASS는 성공 exit와
  실제 통과 테스트를 함께 요구한다. 게이트 override는 호스트 발급 승인 claim을
  원자적으로 한 번만 소비하며, 필터 파이프 증거는 신뢰된 runner exit가 없으면
  거부한다. 훅의 무-Python/손상 JSON 경로, SQLite 스키마 마이그레이션, AC timeout
  프로세스 그룹, mixed timestamp, 문서 배선·호스트 UNTESTED 집계도 회귀 테스트로
  고정했다. 도그푸드는 고정 숫자 fixture 대신 실제 recorder 호출 trace를 사용한다.
  - 완료 증거: `e7de43f`; `hooks/guard_destructive.py:179`,
    `mcp/samvil_mcp/stage_evidence.py:110`,
    `mcp/samvil_mcp/claim_ledger.py:418`,
    `mcp/samvil_mcp/semantic_checker.py:98`,
    `hooks/_contract-helpers.sh:372`, `mcp/samvil_mcp/event_store.py:73`,
    `scripts/dogfood_interactions.py:46`,
    `scripts/check-skill-wiring.py:366`, `scripts/pre-commit-check.sh:201`,
    `mcp/tests/test_guard_destructive.py:53`,
    `mcp/tests/test_gate_override.py:61`,
    `mcp/tests/test_contract_hook_atomic.py:56`,
    `mcp/tests/test_ac_verification.py:154`,
    `mcp/tests/test_stage_evidence.py:36`,
    `mcp/tests/test_semantic_checker.py:141`.
- [x] **4.9 R3 pre-PR 리뷰에서 재현된 잔여 우회 경로 전부 차단**
  142파일/8,402 LOC diff를 교차 엔진 + 독립 finder 5개 + finding별 verifier
  2표로 재검수해 확정된 P1/P2를 닫았다. 파괴 명령 가드는 줄바꿈·parent escape·
  wrapper/subshell을 재귀 분석하고, generic claim API는 host-only 승인/override를
  게시·검증할 수 없다. override 소비 시 실제 host approval의 consumed provenance를
  다시 검증한다. `complete_stage`는 persisted project root를 사용하고, AC 검증은
  event loop 밖에서 실행한다. deploy gate는 runtime 증거를 필수로 하며 `deep` tier는
  전 파이프라인에서 독립된 최상위 엄격도로 유지한다.
  - 완료 증거: `f5104fb`; `hooks/guard_destructive.py:71`,
    `hooks/guard_destructive.py:233`, `mcp/samvil_mcp/claim_ledger.py:54`,
    `mcp/samvil_mcp/claim_ledger.py:582`, `mcp/samvil_mcp/server.py:999`,
    `mcp/samvil_mcp/server.py:4830`, `mcp/samvil_mcp/gates.py:170`,
    `mcp/samvil_mcp/orchestrator.py:31`,
    `mcp/tests/test_guard_destructive.py:65`,
    `mcp/tests/test_gate_override.py:75`, `mcp/tests/test_gate_override.py:138`,
    `mcp/tests/test_gates.py:75`, `mcp/tests/test_server_domain_split.py:54`,
    `mcp/tests/test_samvil_smoke.py:173`.
- [x] **4.10 R4 최종 pre-PR 검수에서 신뢰 불가능한 경계를 fail-closed로 정직화**
  (스코프 보정: 4.8~4.9의 호스트 event id 기반 승인 claim과 모델 작성
  `qa.log`/`test-results.json` 기반 runtime PASS는 실제 호스트 보안 경계가 아니었다.
  현행 멀티호스트에는 모델이 호출할 수 없는 승인 attestation과 portable process
  sandbox가 없으므로, 이를 계속 "trusted"라고 부르는 대신 override·AC command
  execution·deploy runtime 승인을 모두 fail-closed로 전환한다. QA→Evolve/Retro는
  별도 게이트로 정직하게 라우팅하고, trusted runner가 생기기 전 verify leaf는
  누락·무-ID까지 합성 단계에서 FAIL한다.) 파괴 명령 wrapper 옵션, async file lock,
  canonical deep tier, Council opt-in, Codex root SSOT, dynamic marker command와
  Deploy→Retro 호스트 parity도 함께 고정했다.
  - 완료 증거: `887cc61`; `mcp/samvil_mcp/ac_verification.py:20`,
    `mcp/samvil_mcp/ac_verification.py:126`,
    `mcp/samvil_mcp/ac_verification.py:164`,
    `mcp/samvil_mcp/qa_finalize.py:81`,
    `mcp/samvil_mcp/qa_finalize.py:116`,
    `mcp/samvil_mcp/claim_ledger.py:388`,
    `mcp/samvil_mcp/stage_evidence.py:127`,
    `mcp/samvil_mcp/deploy_targets.py:308`,
    `mcp/samvil_mcp/chain_markers.py:51`,
    `hooks/guard_destructive.py:102`,
    `references/codex-commands/samvil-qa.md:17`,
    `references/codex-commands/samvil-deploy.md:19`,
    `mcp/tests/test_qa_smoke.py:437`,
    `mcp/tests/test_qa_smoke.py:459`,
    `mcp/tests/test_qa_smoke.py:478`,
    `mcp/tests/test_async_file_offload.py:23`,
    `mcp/tests/test_async_file_offload.py:56`.
- [x] **4.11 R5 재검수에서 남은 trust/core 안정성 결함 전부 보강**
  (스코프 보정: 4.10은 QA/deploy runtime 경계를 fail-closed로 정직화했지만,
  build→QA 게이트는 여전히 모델 작성 `.samvil/build.log`의 `SAMVIL_EXIT:0`을
  hard gate 통과 근거로 삼고 있었다. 현행 멀티호스트에는 모델이 쓸 수 없는
  trusted build receipt가 없으므로 build artifact도 QA artifact와 같은 경계로
  보고 fail-closed 처리한다.) 파괴 명령 가드는 셸 틸드 확장과 `exec -a`
  argv0 우회를 차단하고, `complete_stage`는 프로젝트 events SSOT에 단계 완료를
  기록한다. QA finalize와 seed migration의 동기 파일 작업은 MCP event loop 밖으로
  옮겼고, Design 진입은 명시적 `--council` opt-in을 orchestrator 게이트에 전달한다.
  pre-commit full suite에서 드러난 주기 checkpoint 타이밍 흔들림도 별도 테스트
  안정화 커밋으로 닫았다.
  - 완료 증거: `444988f`; `hooks/guard_destructive.py:225`,
    `mcp/tests/test_guard_destructive.py:41`.
  - 완료 증거: `d943eb1`; `mcp/tests/test_checkpoint.py:112`.
  - 완료 증거: `c19d3f5`; `hooks/guard_destructive.py:44`,
    `hooks/guard_destructive.py:257`, `mcp/tests/test_guard_destructive.py:63`.
  - 완료 증거: `44dcf85`; `mcp/samvil_mcp/stage_evidence.py:15`,
    `mcp/samvil_mcp/stage_evidence.py:89`, `mcp/samvil_mcp/server.py:2570`,
    `mcp/tests/test_gates.py:439`, `skills/samvil-build/SKILL.md:96`.
  - 완료 증거: `235a5e7`; `mcp/samvil_mcp/server.py:1004`,
    `mcp/samvil_mcp/server.py:1015`, `mcp/tests/test_orchestrator_mcp.py:85`.
  - 완료 증거: `25724a4`; `mcp/samvil_mcp/server.py:4496`,
    `mcp/tests/test_async_file_offload.py:75`.
  - 완료 증거: `f367ead`; `mcp/samvil_mcp/server.py:3137`,
    `mcp/tests/test_async_file_offload.py:93`.
  - 완료 증거: `0acaecf`; `skills/samvil-design/SKILL.md:16`,
    `skills/samvil-design/SKILL.md:27`,
    `references/codex-commands/samvil-design.md:14`,
    `mcp/tests/test_skill_wiring.py:212`.
- [x] **4.12 R6 pre-PR 재검수에서 확인된 PreToolUse 차단 의미론 보정**
  (스코프 보정: 4.5와 4.8~4.11은 파괴 명령의 파싱 정확도를 "실가드"로
  강화했지만, Claude Code `PreToolUse` hook의 실제 차단 의미론은 `exit 2`
  또는 deny JSON에 의존한다. 기존 `exit 1` + stdout은 script 단위 테스트에선
  차단처럼 보였지만 host 레벨에서는 non-blocking error가 될 수 있어, hook
  차단 경로를 stderr + `exit 2`로 교정하고 dogfood oracle도 같은 계약으로 맞췄다.)
  - 완료 증거: `095c835`; `hooks/guard-destructive.sh:13`,
    `hooks/guard-destructive.sh:19`, `hooks/guard-destructive.sh:25`,
    `mcp/tests/test_guard_destructive.py:77`,
    `mcp/tests/test_guard_destructive.py:78`,
    `scripts/wave4-automation-dogfood.py:170`.
- [x] **4.13 R7 pre-PR 재검수에서 확인된 Codex PATH 런타임 재현성 보정**
  (스코프 보정: GitHub Release check와 일반 터미널 PATH에서는 Phase 6 runtime dogfood가
  통과했지만, Codex 앱 기본 PATH는 Homebrew Node bin을 포함하지 않아 mandatory
  `bash scripts/pre-commit-check.sh`가 `npm` 탐색 실패로 red가 될 수 있었다. runtime
  dogfood가 `npm`을 PATH 우선으로 찾되 일반 macOS Node fallback 경로까지 확인하고,
  fallback으로 찾은 bin 디렉터리를 child PATH에 주입해 `npm run build`와 `npm start`
  둘 다 같은 재현성 계약을 따르게 했다.)
  - 완료 증거: `c88898e`; `scripts/phase6-real-runtime-dogfood.py:40`,
    `scripts/phase6-real-runtime-dogfood.py:313`,
    `scripts/phase6-real-runtime-dogfood.py:328`,
    `scripts/phase6-real-runtime-dogfood.py:342`,
    `mcp/tests/test_phase6_real_runtime_dogfood.py:44`,
    `mcp/tests/test_phase6_real_runtime_dogfood.py:60`.
- [x] **4.14 동일 HEAD 연속 클린 검수 전 문서 증거 드리프트 교정**
  (스코프 보정: 과거 Wave 2 dogfood의 모델 입력 기반 override 성공 기록은 현재의
  trusted-host fail-closed 정책과 충돌했고, 코드 이동 뒤 `collect_stage_evidence`
  MCP 도구의 file:line 포인터도 더는 구현을 가리키지 않았다. 과거 실측을 현재
  보안 보장으로 오해하지 않도록 거부 계약을 명시하고 현재 구현 위치를 다시 고정했다.)
  - 완료 증거: `4f59b5a`;
    `docs/evidence/evolution-2026-07-wave2-dogfood.md:15`,
    `docs/evidence/evolution-2026-07-wave2-dogfood.md:18`,
    `mcp/tests/test_wave2_dogfood.py:96`, `mcp/tests/test_wave2_dogfood.py:103`.
  - 완료 증거: `48366f6`; `docs/evolution-2026-07-trustworthy-core.md:584`,
    `mcp/samvil_mcp/server.py:4899`.
- [x] **4.15 최종 게이트에서 드러난 manifest 시각 경계 플래키 제거**
  (스코프 보정: 구현의 manifest와 module metadata는 각각 생성 시각을 보존하는 것이
  정상이나, 기존 멱등성 테스트는 최상위 `generated_at`만 제외했다. 두 호출이 초
  경계를 넘으면 중첩 `summary_generated_at`과 `last_updated` 때문에 간헐 실패했으므로,
  서로 다른 두 시각을 강제하고 모든 생성 시각만 정규화해 실제 결정론을 검증한다.)
  - 완료 증거: `1fceb8b`; `mcp/tests/test_manifest.py:616`,
    `mcp/tests/test_manifest.py:624`, `mcp/tests/test_manifest.py:637`,
    `mcp/tests/test_manifest.py:647`.
- [x] **4.16 동일 HEAD 2차 검수에서 확인된 Gemini QA 동적 라우팅 정직화**
  (스코프 보정: Gemini 명령의 기본 marker 호출은 기존 문구였지만, 이번 진화에서
  QA가 finalize → materialize → route-specific gate → dynamic next skill 계약으로
  강화되며 기본 `samvil-qa→samvil-deploy` 경로가 실제 회귀가 됐다. 생성기와 생성
  산출물을 함께 고치고 strict parity가 필수 lifecycle marker를 검사하게 했다.)
  - 완료 증거: `5b3ed7b`; `references/gemini-commands/samvil-qa.toml:12`,
    `references/gemini-commands/samvil-qa.toml:13`,
    `references/gemini-commands/samvil-qa.toml:14`,
    `references/gemini-commands/samvil-qa.toml:18`,
    `scripts/generate-host-commands.py:77`,
    `scripts/check-host-parity.py:65`, `scripts/check-host-parity.py:339`,
    `mcp/tests/test_host_parity.py:203`, `mcp/tests/test_host_parity.py:221`.
- [x] **4.17 클린 검수 재시작에서 확인된 단계 완료 claim 저하 의미론 보정**
  (스코프 보정: canonical event와 stage transition은 완료 진실이고 gate claim은 그
  진실의 관측 채널이다. claim append 실패를 전체 완료 실패로 반환하면 이미 완료된
  단계를 재시도해 event를 중복시킬 수 있으므로, 완료는 유지하고 `claim_saved=false`
  및 `claim_error`와 health evidence로 저하를 명시한다.)
  - 완료 증거: `c0445c4`; `mcp/samvil_mcp/server.py:1078`,
    `mcp/samvil_mcp/server.py:1093`, `mcp/samvil_mcp/server.py:1103`,
    `mcp/tests/test_orchestrator_mcp.py:169`,
    `mcp/tests/test_orchestrator_mcp.py:197`,
    `references/samvil-ssot-schema.md:476`.
- [x] **4.18 동일 HEAD 클린 검수에서 확인된 단계 claim 증거 우회 제거**
  (스코프 보정: `save_event`가 canonical event를 먼저 저장하고도 단계 시작 claim을
  검증할 때 합성 `event:*` 문자열과 `skip_file_resolution=True`를 사용하고 있었다.
  append 잠금 안에서 실제 줄 번호를 확정해 시작·완료 이벤트 모두
  `.samvil/events.jsonl:<line>` 증거를 사용하고, 일반 file resolution을 통과해야만
  verified 상태가 되도록 교정했다.)
  - 완료 증거: `340ea2f`; `mcp/samvil_mcp/server.py:627`,
    `mcp/samvil_mcp/server.py:646`, `mcp/samvil_mcp/server.py:682`,
    `mcp/samvil_mcp/server.py:700`, `mcp/samvil_mcp/server.py:703`,
    `mcp/tests/test_orchestrator_mcp.py:403`,
    `mcp/tests/test_orchestrator_mcp.py:437`.
- [x] **4.19 QA 결과 부재·손상 시 체인 진행 fail-closed**
  (`resolve_stage_next_skill`의 기존 `None` 계약은 유지하고, `advance_chain`의 현재
  단계가 QA일 때만 marker를 그대로 반환해 contract-stage-end QA gate 우회를
  막는다. missing/corrupt 결과를 같은 회귀 테스트로 고정했다.)
  - 완료 증거: `7783e6e`; `mcp/samvil_mcp/chain_markers.py:177`,
    `mcp/samvil_mcp/chain_markers.py:179`, `mcp/samvil_mcp/chain_markers.py:182`,
    `mcp/tests/test_chain_markers.py:190`, `mcp/tests/test_chain_markers.py:212`,
    `mcp/tests/test_chain_markers.py:214`.
- [x] **4.20 Event DB·canonical JSONL·session stage 원자성 보강**
  (이벤트 INSERT와 stage UPDATE를 SQLite 한 트랜잭션으로 묶고, 이후 canonical
  JSONL 저장 실패 시 이벤트 삭제와 이전 stage 복원을 조건부 보상 트랜잭션으로
  수행한다. 실제 SQLite stage UPDATE 실패를 주입한 뒤 두 API의 무잔여·무중복
  재시도를 검증했다.)
  - 완료 증거: `bb7af29`; `mcp/samvil_mcp/event_store.py:266`,
    `mcp/samvil_mcp/event_store.py:283`, `mcp/samvil_mcp/event_store.py:304`,
    `mcp/samvil_mcp/event_store.py:318`, `mcp/samvil_mcp/event_store.py:340`,
    `mcp/samvil_mcp/server.py:788`, `mcp/samvil_mcp/server.py:821`,
    `mcp/samvil_mcp/server.py:1047`, `mcp/samvil_mcp/server.py:1076`,
    `mcp/tests/test_orchestrator_mcp.py:172`,
    `mcp/tests/test_orchestrator_mcp.py:192`,
    `mcp/tests/test_orchestrator_mcp.py:211`,
    `mcp/tests/test_orchestrator_mcp.py:232`.
- [x] **4.21 v3.3 migration backup 원자 생성·검증**
  (존재 여부 대신 JSON 파싱과 v3.2 식별로 기존 백업을 판정한다. 유효한 최초
  백업은 보존하고, partial/corrupt 백업은 durable atomic write 후 원문과 파싱
  결과를 재검증한다. 백업 실패 시 seed 쓰기에 진입하지 않는다.)
  - 완료 증거: `8bdaf82`; `mcp/samvil_mcp/migrate_v3_3.py:18`,
    `mcp/samvil_mcp/migrate_v3_3.py:29`, `mcp/samvil_mcp/migrate_v3_3.py:38`,
    `mcp/samvil_mcp/migrate_v3_3.py:70`, `mcp/samvil_mcp/migrate_v3_3.py:80`,
    `mcp/tests/test_migrate_v3_3.py:69`, `mcp/tests/test_migrate_v3_3.py:83`,
    `mcp/tests/test_migrate_v3_3.py:97`, `mcp/tests/test_migrate_v3_3.py:117`.
- [x] **4.22 mobile-app Expo web 브라우저 AC 계약 연결**
  (`mobile-app`을 기존 browser solution type 집합에 포함해 Expo web surface도
  per-feature Playwright spec을 AC 1차 검증 명령으로 사용한다.)
  - 완료 증거: `d4c3def`; `mcp/samvil_mcp/ac_verification.py:15`,
    `mcp/samvil_mcp/ac_verification.py:85`, `mcp/samvil_mcp/ac_verification.py:94`,
    `mcp/tests/test_ac_verification.py:54`, `mcp/tests/test_ac_verification.py:61`,
    `mcp/tests/test_ac_verification.py:65`.
- [x] **4.23 제거된 interview readiness tool 문서 드리프트 차단**
  (스코프 보정: `references/contract-layer-protocol.md`의 직접 호출은 선행 커밋
  `bdc8712`에서 이미 `score_ambiguity`로 교정되어 있었다. 현재 코드 기준으로
  `seed_readiness`와 `converged`의 gate 매핑을 명시하고, 제거된
  `compute_seed_readiness`가 reference 문서에 재등장하면 wiring 검사가 실패하도록
  고정했다. 역사 기록은 수정하지 않았다.)
  - 완료 증거: `49af43e`; `references/contract-layer-protocol.md:145`,
    `references/contract-layer-protocol.md:155`,
    `references/contract-layer-protocol.md:157`, `scripts/check-skill-wiring.py:39`,
    `scripts/check-skill-wiring.py:43`, `scripts/check-skill-wiring.py:357`,
    `scripts/check-skill-wiring.py:382`, `scripts/check-skill-wiring.py:385`,
    `mcp/tests/test_skill_wiring.py:62`, `mcp/tests/test_skill_wiring.py:80`.
- [x] **4.24 동시 stage 보상 소유권을 고유 전이 토큰으로 교정**
  (초기 timestamp 기반 보상은 최신 전이를 되감지 않도록 좁혔지만 동일 timestamp와
  트랜잭션 밖 previous stage 읽기가 남았다. 최종적으로 session row를 write
  transaction 안에서 읽고 event id를 전이 소유권으로 저장·복원한다.)
  - 중간 보정: `cdd2b01`; 최종 완료: `d18ac93`;
    `mcp/samvil_mcp/event_store.py:293`, `mcp/samvil_mcp/event_store.py:314`,
    `mcp/samvil_mcp/event_store.py:323`, `mcp/samvil_mcp/event_store.py:339`,
    `mcp/samvil_mcp/event_store.py:379`, `mcp/tests/test_event_store.py:155`,
    `mcp/tests/test_event_store.py:186`.
- [x] **4.25 v3.3 백업 판정을 canonical seed 계약과 단일화**
  (중간 수동 구조 검사는 parseable partial을 거부했지만 정식 validator와 다른
  허용·거부 집합을 만들었다. 백업 판정도 `validate_seed`를 사용해 drift를 없앴다.)
  - 중간 보정: `2980e38`; 최종 완료: `bd4d985`;
    `mcp/samvil_mcp/migrate_v3_3.py:19`, `mcp/samvil_mcp/migrate_v3_3.py:27`,
    `mcp/tests/test_migrate_v3_3.py:107`.
- [x] **4.26 보호 SSOT 삭제 guard의 bounded expansion fail-closed**
  (brace expansion 후보가 검사 상한을 넘으면 뒤쪽 보호 경로가 누락되지 않도록
  전체 명령을 동적 위험 대상으로 차단한다.)
  - 완료 증거: `672eda3`; `hooks/guard_destructive.py:607`,
    `hooks/guard_destructive.py:643`, `mcp/tests/test_guard_destructive.py:312`.
- [x] **4.27 rm 외 보호 SSOT 파괴 경로 차단**
  (`truncate`, `/dev/null` 복사, shell output redirection으로 root/.samvil SSOT를
  비우거나 덮어쓰는 명령을 동일 guard 경계에서 차단한다.)
  - 완료 증거: `8ac1900`; `hooks/guard_destructive.py:708`,
    `hooks/guard_destructive.py:1546`, `mcp/tests/test_guard_destructive.py:331`.
- [x] **4.28 PM seed conversion의 MCP-free 복구 완료 의미론 보강**
  (`pm_seed_converted`를 seed 성공 이벤트로 분류해 state 파일이 없을 때 진행 중으로
  오인하지 않는다.)
  - 완료 증거: `294f18b`; `mcp/samvil_mcp/event_store_reader.py:45`,
    `mcp/tests/test_event_store_reader.py:238`.
- [x] **4.29 알 수 없는 QA verdict의 이중 fail-closed**
  (`resolve_stage_next_skill`은 기존 `None` 계약을 유지하고, 내부 decision helper도
  missing/unknown verdict를 QA 잔류로 제한해 deploy 기본값으로 떨어지지 않는다.)
  - 완료 증거: `8ad743f`; `mcp/samvil_mcp/chain_markers.py:117`,
    `mcp/samvil_mcp/chain_markers.py:121`, `mcp/samvil_mcp/qa_finalize.py:338`,
    `mcp/tests/test_chain_markers.py:223`, `mcp/tests/test_qa_smoke.py:823`.
- [x] **4.30 대용량 semantic 검사 event-loop offload**
  (코드와 실행 로그 분석을 worker thread로 보내 다른 MCP 요청의 이벤트 루프를
  점유하지 않는다.)
  - 완료 증거: `b55dace`; `mcp/samvil_mcp/server.py:1780`,
    `mcp/tests/test_async_file_offload.py:142`.
- [x] **4.31 rate budget worker lease heartbeat**
  (장시간 살아 있는 build worker가 최초 acquire 시각만으로 만료되지 않도록 heartbeat
  이벤트와 MCP tool을 추가하고, worker contract가 10분마다 lease를 갱신하게 한다.)
  - 완료 증거: `70274c3`; `mcp/samvil_mcp/rate_budget.py:99`,
    `mcp/samvil_mcp/rate_budget.py:152`, `mcp/samvil_mcp/server.py:2465`,
    `mcp/samvil_mcp/build_phase_b.py:304`, `skills/samvil-build/SKILL.md:59`,
    `mcp/tests/test_rate_budget.py:55`, `mcp/tests/test_rate_budget.py:74`.
- [x] **4.32 canonical events JSONL line index로 누적 O(n²) 제거**
  (파일 크기와 줄 수를 작은 sidecar index로 보존하고, size mismatch일 때만 전체
  재계산해 file:line 증거의 정확성과 정상 경로 O(1) append를 함께 유지한다.)
  - 완료 증거: `f12e17a`; `mcp/samvil_mcp/server.py:653`,
    `mcp/samvil_mcp/server.py:663`, `mcp/samvil_mcp/server.py:678`,
    `mcp/tests/test_orchestrator_mcp.py:411`.
- [x] **4.33 일반 event와 trusted stage transition 신뢰 경계 분리**
  (`save_event`는 telemetry-only로 저장하고 session stage를 바꾸지 않으며, user
  verification 또는 PASS gate claim을 합성하지 않는다. orchestration 상태는
  `complete_stage`의 trusted transition만 새 성공·실패로 인정한다.)
  - 완료 증거: `5abe17d`; `mcp/samvil_mcp/server.py:733`,
    `mcp/samvil_mcp/server.py:744`, `mcp/samvil_mcp/server.py:810`,
    `mcp/samvil_mcp/server.py:1058`, `mcp/samvil_mcp/orchestrator.py:308`,
    `mcp/tests/test_orchestrator_mcp.py:562`.
- [x] **4.34 event payload 개인정보·자격증명 redaction**
  (raw prompt를 event 호출에서 제거하고, DB/JSONL 저장 전 payload를 재귀 순회해
  prompt·email·token·secret·oversized text를 bounded redaction한다.)
  - 완료 증거: `d4130c2`; `mcp/samvil_mcp/event_sanitizer.py:32`,
    `mcp/samvil_mcp/server.py:784`, `skills/samvil/SKILL.md:79`,
    `mcp/tests/test_event_sanitizer.py:13`,
    `mcp/tests/test_orchestrator_mcp.py:375`.
- [x] **4.35 임의 event label을 bounded machine label로 정규화**
  (호출자가 event_type에 prompt·email·token을 섞어도 DB, JSONL, claim에 원문을
  남기지 않고 안전한 고정 라벨로 저장한다.)
  - 완료 증거: `afd5849`; `mcp/samvil_mcp/event_sanitizer.py:78`,
    `mcp/samvil_mcp/server.py:805`, `mcp/tests/test_event_sanitizer.py:25`.
- [x] **4.36 명령 없는 redirection과 dev-null overwrite도 SSOT 보호**
  (`>`, `>>`, `tee`, `dd`, `install`, `cp /dev/null`의 보호 대상 overwrite를
  동일한 destructive guard에서 fail-closed 처리한다.)
  - 완료 증거: `84f0f0f`; `hooks/guard_destructive.py:715`,
    `hooks/guard_destructive.py:727`, `hooks/guard_destructive.py:734`,
    `hooks/guard_destructive.py:739`, `mcp/tests/test_guard_destructive.py:336`.
- [x] **4.37 complete_stage의 현재 단계·선행 gate 검증**
  (현재 session stage와 요청 stage가 다르거나 선행 stage가 완료되지 않았으면
  trusted transition과 PASS claim을 만들지 않는다.)
  - 완료 증거: `6f8602c`; `mcp/samvil_mcp/server.py:1080`,
    `mcp/samvil_mcp/server.py:1085`, `mcp/tests/test_orchestrator_mcp.py:146`.
- [x] **4.38 stage label·camelCase key·bare token redaction 보강**
  (`stage_raw`, `accessToken`, `userPassword`, 라벨 없는 ghp/sk token까지 저장 전에
  정규화·제거한다.)
  - 완료 증거: `de38af7`; `mcp/samvil_mcp/event_sanitizer.py:19`,
    `mcp/samvil_mcp/event_sanitizer.py:46`, `mcp/samvil_mcp/event_sanitizer.py:84`,
    `mcp/samvil_mcp/server.py:819`, `mcp/tests/test_event_sanitizer.py:35`.
- [x] **4.39 brace 후보가 한도에 정확히 닿아도 미확장 대상을 fail-closed**
  (32개 후보 생성 뒤 남은 중첩 brace를 안전한 결과로 오인하지 않는다.)
  - 완료 증거: `4806c9d`; `hooks/guard_destructive.py:607`,
    `hooks/guard_destructive.py:627`, `mcp/tests/test_guard_destructive.py:322`.
- [x] **4.40 invalid v3.2 source를 backup·migration 전에 거부**
  (canonical seed validator가 거부한 원본은 백업도 v3.3 seed도 만들지 않는다.)
  - 완료 증거: `0b54e34`; `mcp/samvil_mcp/migrate_v3_3.py:77`,
    `mcp/tests/test_migrate_v3_3.py:123`.
- [x] **4.41 canonical event의 모든 저장 예외에서 DB 보상**
  (`UnicodeError` 등 비-`OSError`도 일반 event 삭제 또는 trusted stage 복구 경로로
  보내 부분 DB 저장을 남기지 않는다.)
  - 완료 증거: `f519f19`; `mcp/samvil_mcp/server.py:849`,
    `mcp/samvil_mcp/server.py:860`, `mcp/samvil_mcp/server.py:1134`,
    `mcp/tests/test_orchestrator_mcp.py:222`.
- [x] **4.42 canonical append 후 close 실패의 ghost row 보상**
  (append 전 byte offset을 보존하고 write·flush·fsync·close 중 실패하면 같은 file
  lock 안에서 원래 길이로 truncate한다.)
  - 완료 증거: `7b5ee53`; `mcp/samvil_mcp/server.py:653`,
    `mcp/samvil_mcp/server.py:669`, `mcp/samvil_mcp/server.py:672`,
    `mcp/tests/test_orchestrator_mcp.py:261`.
- [x] **4.43 project root 없는 trusted transition을 fail-closed**
  (canonical events/claims 경로를 해석할 수 없으면 DB stage만 전진시키지 않는다.)
  - 완료 증거: `53b8af6`; `mcp/samvil_mcp/server.py:1074`,
    `mcp/tests/test_orchestrator_mcp.py:482`.
- [x] **4.44 transition timestamp를 DB write lock 뒤에 생성**
  (동시 호출의 이벤트 시각과 실제 직렬화 순서가 반대로 기록되지 않게 한다.)
  - 완료 증거: `97a572d`; `mcp/samvil_mcp/event_store.py:281`,
    `mcp/samvil_mcp/event_store.py:283`, `mcp/tests/test_event_store.py:212`.
- [x] **4.45 acquire와 worker heartbeat의 rate budget 경로 단일화**
  (MCP cwd와 대상 프로젝트가 달라도 bundle은 Phase A가 반환한 exact budget path를
  갱신한다.)
  - 완료 증거: `8922a8b`; `skills/samvil-build/SKILL.md:52`,
    `mcp/samvil_mcp/build_phase_b.py:307`, `mcp/samvil_mcp/build_phase_b.py:520`,
    `mcp/tests/test_build_phase_b.py:222`.
- [x] **4.46 rate budget reset의 snapshot·unlink 원자화**
  (통계 lock과 삭제 lock 사이 새로 획득한 정상 worker lease를 지우지 않는다.)
  - 완료 증거: `caee22b`; `mcp/samvil_mcp/rate_budget.py:163`,
    `mcp/samvil_mcp/rate_budget.py:197`, `mcp/tests/test_rate_budget.py:166`.
- [x] **4.47 Codex fresh boot의 session 생성·지속 연결**
  (다음 skill로 marker를 넘기기 전에 `create_session` 결과를 root state의
  `session_id`로 보존하며 실패 시 chain을 중단한다.)
  - 완료 증거: `210f225`; `references/codex-commands/samvil.md:29`,
    `mcp/tests/test_host_parity.py:55`.
- [x] **4.48 interview completion을 trusted stage transition으로 연결**
  (telemetry-only `save_event` 대신 `complete_stage`가 canonical completion event와
  session stage를 함께 확정해 seed gate가 정상 통과한다.)
  - 완료 증거: `66954d3`; `skills/samvil-interview/SKILL.md:95`,
    `mcp/tests/test_skill_wiring.py:144`.
- [x] **4.49 token 형태 event/stage label의 원문 저장 차단**
  (machine label 정규식에 맞더라도 자격증명 형태면 redacted 고정 라벨로 치환한다.)
  - 완료 증거: `f99511d`; `mcp/samvil_mcp/event_sanitizer.py:78`,
    `mcp/samvil_mcp/event_sanitizer.py:83`, `mcp/samvil_mcp/event_sanitizer.py:93`,
    `mcp/tests/test_event_sanitizer.py:28`.
- [x] **4.50 동일 timestamp event의 결정적 최신 결과 복원**
  (SQLite rowid로 newest-first total order를 만들고 orchestrator 입력에서 정확히
  뒤집어, 같은 시각의 후속 성공·실패 결과가 삽입 순서대로 최종 판정된다.)
  - 완료 증거: `c0c68f4`; `mcp/samvil_mcp/event_store.py:415`,
    `mcp/samvil_mcp/event_store.py:425`, `mcp/samvil_mcp/server.py:972`,
    `mcp/tests/test_orchestrator_mcp.py:189`.
- [x] **4.51 Codex interview·seed 명령의 trusted completion 연결**
  (marker를 쓰기 전에 각 stage의 `complete_stage`가 성공해야 하며, 실패하면 다음
  skill로 진행하지 않는다.)
  - 완료 증거: `58661d5`; `references/codex-commands/samvil-interview.md:139`,
    `references/codex-commands/samvil-seed.md:23`, `mcp/tests/test_host_parity.py:75`,
    `mcp/tests/test_host_parity.py:82`.
- [x] **4.52 GitHub fine-grained PAT payload redaction**
  (`github_pat_` 장형 토큰도 중첩 payload 어디에서든 저장 전에 제거한다.)
  - 완료 증거: `75d0271`; `mcp/samvil_mcp/event_sanitizer.py:19`,
    `mcp/samvil_mcp/event_sanitizer.py:20`, `mcp/tests/test_event_sanitizer.py:36`,
    `mcp/tests/test_event_sanitizer.py:48`.
- [x] **4.53 대량 telemetry 뒤의 stage 완료 이력 보존**
  (공개 조회 기본 limit은 유지하고 orchestration·completion 판정만 전체 session
  이력을 읽어 1,000건 이전 trusted transition을 잃지 않는다.)
  - 완료 증거: `63421f1`; `mcp/samvil_mcp/event_store.py:405`,
    `mcp/samvil_mcp/event_store.py:425`, `mcp/samvil_mcp/server.py:989`,
    `mcp/samvil_mcp/server.py:1103`, `mcp/tests/test_orchestrator_mcp.py:129`.
- [x] **4.54 줄바꿈 없는 canonical JSONL tail 안전 append**
  (기존 마지막 행이 newline 없이 끝나도 구분 newline을 같은 lock·rollback 경계에서
  추가해 새 이벤트가 독립 행과 정확한 file:line 증거를 유지한다.)
  - 완료 증거: `b138098`; `mcp/samvil_mcp/server.py:659`,
    `mcp/samvil_mcp/server.py:696`, `mcp/tests/test_orchestrator_mcp.py:948`.
- [x] **4.55 인터뷰 trusted completion의 실제 exit evidence 검증**
  (빈 프로젝트나 요약만 있는 프로젝트는 전진시키지 않고, non-empty summary와 최신
  `interview_to_seed` pass claim이 함께 있어야 canonical event·stage를 확정한다.
  스코프 보정으로 Codex 명령도 gate→claim→complete 순서를 명시했다.)
  - 완료 증거: `2c509dd`; `mcp/samvil_mcp/server.py:1099`,
    `mcp/samvil_mcp/server.py:1215`, `mcp/tests/test_orchestrator_mcp.py:267`,
    `mcp/tests/test_orchestrator_mcp.py:300`,
    `references/codex-commands/samvil-interview.md:126`,
    `mcp/tests/test_skill_wiring.py:154`.
- [x] **4.56 성공 stage completion의 canonical artifact 검증**
  (seed·design·scaffold·build·QA는 각 단계의 정식 seed, blueprint, sanity 결과,
  종료 코드, PASS qa-results가 없거나 손상되면 trusted event와 stage를 만들지 않는다.)
  - 완료 증거: `89e5b17`; `mcp/samvil_mcp/server.py:1099`,
    `mcp/samvil_mcp/server.py:1215`, `mcp/samvil_mcp/server.py:1268`,
    `mcp/tests/test_orchestrator_mcp.py:367`.
- [x] **4.57 scaffold·build canonical completion과 chain 순서 정렬**
  (scaffold sanity 결과와 build gate PASS 뒤 각각 `complete_stage`가 성공해야만
  다음 skill marker 또는 native chain을 실행해 session과 실행 흐름이 갈라지지 않는다.)
  - 완료 증거: `3018ecf`; `skills/samvil-scaffold/SKILL.md:102`,
    `skills/samvil-build/SKILL.md:102`,
    `references/codex-commands/samvil-scaffold.md:20`,
    `references/codex-commands/samvil-build.md:23`,
    `mcp/tests/test_host_parity.py:75`, `mcp/tests/test_skill_wiring.py:278`.
- [x] **4.58 동시 동일 stage completion의 transaction CAS**
  (transaction 밖 precheck를 함께 통과해도 DB write lock 안에서 expected stage를
  다시 비교해 정확히 한 호출만 event·JSONL·claim을 생성한다.)
  - 완료 증거: `7928fa9`; `mcp/samvil_mcp/event_store.py:279`,
    `mcp/samvil_mcp/event_store.py:302`, `mcp/samvil_mcp/server.py:1133`,
    `mcp/tests/test_orchestrator_mcp.py:833`.
- [x] **4.59 build 완료의 trusted runtime 증거 강제**
  (모델이 직접 쓸 수 있는 `build.log`의 성공 exit code만으로는 trusted transition을
  만들지 않고, host adapter가 제공하는 `runtime_verified=true`를 함께 요구한다.)
  - 완료 증거: `ae612b6`; `mcp/samvil_mcp/server.py:1254`,
    `mcp/samvil_mcp/server.py:1263`, `mcp/tests/test_orchestrator_mcp.py:427`.
- [x] **4.60 QA 완료의 self-authored PASS 차단**
  (`qa-results.json` PASS와 성공 test artifact가 있어도 trusted runtime receipt가
  없으면 QA 완료 event·stage를 확정하지 않는다.)
  - 완료 증거: `0c0c4f5`; `mcp/samvil_mcp/server.py:1268`,
    `mcp/samvil_mcp/server.py:1283`, `mcp/samvil_mcp/server.py:1289`,
    `mcp/tests/test_orchestrator_mcp.py:470`.
- [x] **4.61 design blueprint canonical 계약 검증**
  (파싱 가능한 임의 객체를 blueprint로 승인하지 않고, documented screens·data model·
  API routes·state management·auth strategy 구조를 모두 검증한다.)
  - 완료 증거: `8fa3b42`; `mcp/samvil_mcp/server.py:1235`,
    `mcp/samvil_mcp/server.py:1295`, `mcp/tests/test_orchestrator_mcp.py:538`.
  - 스코프 보정: 이 커밋은 web-app 최소 계약의 최초 차단이었다. 현재의
    solution type별·중첩 계약은 4.62와 4.73에서 완성했다.
- [x] **4.62 solution type별 blueprint 계약 분기**
  (web-app 단일 형태를 모든 앱에 강제하지 않고 dashboard·mobile-app·automation·
  game의 documented top-level 계약을 각각 검증한다.)
  - 완료 증거: `e9cc6c2`; `mcp/samvil_mcp/server.py:1307`,
    `mcp/tests/test_orchestrator_mcp.py:779`.
- [x] **4.63 일반 문자열 내부 자격증명 redaction**
  (dict key가 아닌 prompt·message 문자열에 포함된 token·password·Authorization도
  canonical event 저장 전에 제거한다.)
  - 완료 증거: `a7ff262`; `mcp/samvil_mcp/event_sanitizer.py:41`,
    `mcp/tests/test_event_sanitizer.py:51`.
- [x] **4.64 inline language runtime의 직접 SSOT 변경 차단**
  (`python -c`, `node -e`, Ruby·Perl·PHP inline payload가 보호 SSOT를 직접
  unlink·truncate·write하지 못하도록 pre-tool guard에 포함한다.)
  - 완료 증거: `ebce756`; `hooks/guard_destructive.py:772`,
    `mcp/tests/test_guard_destructive.py:90`.
- [x] **4.65 parseable QA 구조 손상의 fail-closed routing**
  (유효 JSON이라도 synthesis·convergence 구조가 계약과 다르면 deploy로 진행하지
  않고 `resolve_stage_next_skill=None` 계약을 유지한다.)
  - 완료 증거: `e0a02a5`; `mcp/samvil_mcp/chain_markers.py:110`,
    `mcp/tests/test_chain_markers.py:267`.
- [x] **4.66 orchestration precheck의 transition-only 조회**
  (대량 telemetry 전체를 materialize하지 않고 stage 결정에 필요한 신뢰 전환
  후보만 EventStore에서 조회한다.)
  - 완료 증거: `8c457cd`; `mcp/samvil_mcp/event_store.py:451`,
    `mcp/tests/test_orchestrator_mcp.py:210`.
- [x] **4.67 최신 전환이 선행 이벤트를 소유할 때 보상 중단**
  (오래된 canonical append 보상이 더 최신 stage transition의 선행 증거를 삭제하거나
  session stage를 되감지 않도록 transition ownership을 재검증한다.)
  - 완료 증거: `08fdc64`; `mcp/samvil_mcp/event_store.py:345`,
    `mcp/tests/test_event_store.py:188`.
- [x] **4.68 quoted JSON credential·임의 Authorization scheme redaction**
  (따옴표로 직렬화된 credential key와 Basic·AWS4 등 bearer 외 Authorization
  scheme도 값 전체를 저장 전에 제거한다.)
  - 완료 증거: `f6d5129`; `mcp/samvil_mcp/event_sanitizer.py:16`,
    `mcp/tests/test_event_sanitizer.py:73`.
- [x] **4.69 inline runtime 간접 명령·표준 write API 차단**
  (`os.system`·`subprocess`·`execSync`, 문자열 결합 경로, copyfile·File.write·
  createWriteStream·fopen 우회를 보호 SSOT guard가 재귀 검사한다.)
  - 완료 증거: `68ecaec`; `hooks/guard_destructive.py:107`,
    `hooks/guard_destructive.py:801`, `mcp/tests/test_guard_destructive.py:90`.
- [x] **4.70 v3.3 migration의 동시 seed 변경 보호**
  (seed lock을 read→backup→replace 전체에 유지하고, 비협력적 외부 변경도 최종
  replace 직전에 검출해 concurrent writer의 내용을 덮어쓰지 않는다.)
  - 완료 증거: `dfd5206`; `mcp/samvil_mcp/migrate_v3_3.py:73`,
    `mcp/samvil_mcp/migrate_v3_3.py:99`, `mcp/tests/test_migrate_v3_3.py:205`.
- [x] **4.71 명시적 trusted transition만 gate 입력으로 승인**
  (`trusted_transition=true`가 없는 legacy/model-authored event는 인식 가능한 label을
  가져도 orchestration prerequisite를 충족하지 못한다.)
  - 완료 증거: `4977da0`; `mcp/samvil_mcp/event_store.py:451`,
    `mcp/tests/test_event_store.py:218`.
- [x] **4.72 QA nested 구조·encoding 손상의 fail-closed 보강**
  (`convergence=[]`, 비정상 `pass2/counts`, invalid UTF-8 결과 모두 예외나 deploy
  진행 없이 현재 QA marker를 유지한다.)
  - 완료 증거: `88d4d6f`; `mcp/samvil_mcp/chain_markers.py:110`,
    `mcp/tests/test_chain_markers.py:267`, `mcp/tests/test_chain_markers.py:291`.
- [x] **4.73 blueprint nested canonical 구조 검증**
  (빈 dict/list만 배치한 blueprint를 거부하고 routing·navigation·modules·fixtures·
  game config·dashboard source 등 solution type별 내부 계약까지 확인한다.)
  - 완료 증거: `7412853`; `mcp/samvil_mcp/server.py:1307`,
    `mcp/samvil_mcp/server.py:1433`, `mcp/tests/test_orchestrator_mcp.py:692`,
    `mcp/tests/test_orchestrator_mcp.py:779`.
- [x] **4.74 trusted transition 조회 전용 expression index**
  (orchestration query가 session telemetry 후보 전체를 읽지 않고 trusted-transition
  expression index를 사용하도록 실제 query plan으로 고정한다.)
  - 완료 증거: `891ee7d`; `mcp/samvil_mcp/event_store.py:51`,
    `mcp/samvil_mcp/event_store.py:462`, `mcp/tests/test_event_store.py:245`.
- [x] **4.75 동시 완료 회귀 테스트의 실제 precheck 경합 보장**
  (폐기된 `get_events` monkeypatch 대신 production `get_orchestration_events`에서
  두 호출이 모두 barrier에 도달했음을 확인한 뒤 transaction CAS를 검증한다.)
  - 완료 증거: `5c3639e`; `mcp/tests/test_orchestrator_mcp.py:1063`,
    `mcp/tests/test_orchestrator_mcp.py:1114`.
- [x] **4.76 canonical event 보상 완료 전 후속 stage 전환 직렬화**
  (DB stage 전환 뒤 canonical append가 실패한 요청의 보상이 끝나기 전에 동일 session의
  후속 stage가 선행 증거를 소비하지 못하도록 append·보상까지 lock 경계에 포함한다.)
  - 완료 증거: `4ef5da4`; `mcp/samvil_mcp/server.py:1137`,
    `mcp/samvil_mcp/server.py:1141`, `mcp/tests/test_orchestrator_mcp.py:1264`.
- [x] **4.77 QA scalar routing state 손상의 fail-closed 보강**
  (`counts`와 `build_retries`의 bool·음수·비정수, 비-list `qa_history`도 예외나
  deploy 진행 없이 QA marker에 머물게 한다.)
  - 완료 증거: `86c5528`; `mcp/samvil_mcp/chain_markers.py:110`,
    `mcp/samvil_mcp/chain_markers.py:135`, `mcp/samvil_mcp/chain_markers.py:147`,
    `mcp/tests/test_chain_markers.py:262`, `mcp/tests/test_chain_markers.py:318`.
- [x] **4.78 QA terminal verdict의 trusted stage 완료 선행**
  (PASS·FAIL·BLOCKED 결과가 marker나 다음 Skill을 호출하기 전에 `complete_stage`의
  exact `status=ok`를 통과하도록 Claude·Codex·Gemini 실행 계약을 정렬한다.)
  - 완료 증거: `6f990c9`; `skills/samvil-qa/SKILL.md:110`,
    `references/codex-commands/samvil-qa.md:25`, `mcp/tests/test_skill_wiring.py:357`.
- [x] **4.79 Council 승인 결과의 trusted stage 완료 선행**
  (승인된 Council 결과도 design chain 전에 `council_opt_in=true`인 `complete_stage`를
  통과해 단순 handoff·marker가 orchestration gate를 우회하지 못하게 한다.)
  - 완료 증거: `d3ccad5`; `skills/samvil-council/SKILL.md:103`,
    `references/codex-commands/samvil-council.md:22`,
    `mcp/tests/test_skill_wiring.py:388`.
- [x] **4.80 PM interview→seed의 trusted 전환 순서 고정**
  (`validate_pm_seed`의 결정적 readiness를 interview gate에 전달하고 interview 완료 뒤
  변환·seed 완료를 수행해 PM 경로도 정식 stage 계약을 따른다.)
  - 완료 증거: `1f8eab0`; `mcp/samvil_mcp/server.py:3127`,
    `skills/samvil-pm-interview/SKILL.md:51`, `skills/samvil-pm-interview/SKILL.md:66`,
    `mcp/tests/test_server_v3_tools.py:198`.
- [x] **4.81 runtime stdin·script file·env 경유 SSOT 변경 차단**
  (inline option뿐 아니라 heredoc/stdin payload, 실제 runtime script file, 환경변수로
  분리된 보호 경로까지 읽어 간접 mutation을 차단하고 read-only 경계는 유지한다.)
  - 완료 증거: `43466b3`; `hooks/guard_destructive.py:858`,
    `hooks/guard_destructive.py:911`, `mcp/tests/test_guard_destructive.py:108`,
    `mcp/tests/test_guard_destructive.py:121`, `mcp/tests/test_guard_destructive.py:136`.
- [x] **4.82 quoted credential의 공백·delimiter 전체 redaction**
  (따옴표 안에 공백·쉼표·세미콜론이 있어도 종료 quote까지 하나의 credential 값으로
  인식해 canonical event 저장 전에 전부 가린다.)
  - 완료 증거: `d622a95`; `mcp/samvil_mcp/event_sanitizer.py:29`,
    `mcp/samvil_mcp/event_sanitizer.py:68`, `mcp/tests/test_event_sanitizer.py:99`.
- [x] **4.83 trusted transition의 transaction provenance 분리**
  (model-authored JSON flag 대신 event+stage 원자 전환 경로만 DB provenance를 기록하고,
  raw INSERT·일반 save_event·직접 EventStore mutation은 prerequisite로 신뢰하지 않는다.)
  - 완료 증거: `38defe0`; `mcp/samvil_mcp/event_store.py:34`,
    `mcp/samvil_mcp/event_store.py:336`, `mcp/samvil_mcp/event_store.py:490`,
    `mcp/tests/test_event_store.py:283`, `mcp/tests/test_event_store.py:318`,
    `hooks/guard_destructive.py:837`, `mcp/tests/test_guard_destructive.py:197`.
- [x] **4.84 blueprint enum·leaf canonical 계약 검증**
  (web/dashboard의 `mobile_considerations`, solution type별 enum, navigation tab,
  dependency·asset·scene-flow 등 중첩 leaf가 documented shape를 벗어나면 design 완료를
  fail-closed한다.)
  - 완료 증거: `9450b69`; `mcp/samvil_mcp/server.py:1344`,
    `mcp/samvil_mcp/server.py:1399`, `mcp/samvil_mcp/server.py:1450`,
    `mcp/samvil_mcp/server.py:1479`, `mcp/samvil_mcp/server.py:1644`,
    `mcp/samvil_mcp/server.py:1667`, `mcp/tests/test_orchestrator_mcp.py:720`.
- [x] **4.85 secret scanner와 redaction 회귀 fixture의 책임 분리**
  (redaction 테스트가 실제 credential literal을 저장소에 심지 않으면서도 공백·delimiter
  값 전체가 제거되는 계약을 동일하게 검증한다.)
  - 완료 증거: `fc57c9c`; `mcp/tests/test_event_sanitizer.py:99`.
- [x] **4.86 chained SQL·동적 문자열 EventStore mutation 차단**
  (read-only SELECT 뒤에 이어진 write와 문자열 결합 SQL, imported `DB_PATH`를 통한 직접
  DB write도 destructive guard가 EventStore mutation으로 판정한다.)
  - 완료 증거: `2548d5b`; `hooks/guard_destructive.py:1002`,
    `hooks/guard_destructive.py:1234`, `mcp/tests/test_guard_destructive.py:219`,
    `mcp/tests/test_guard_destructive.py:227`.
- [x] **4.87 here-string·pipe runtime stdin mutation 차단**
  (`python - <<<`, `printf | python -`, `echo | node`로 전달한 payload도 inline/heredoc과
  동일한 SSOT mutation 검사 경계를 통과한다.)
  - 완료 증거: `12c5f0e`; `hooks/guard_destructive.py:1133`,
    `hooks/guard_destructive.py:1167`, `mcp/tests/test_guard_destructive.py:135`.
- [x] **4.88 namespaced env credential·multiline quoted value redaction**
  (`OPENAI_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `DATABASE_URL` 같은 prefix key와 여러 줄
  quoted password를 canonical event 저장 전에 값 전체 단위로 제거한다.)
  - 완료 증거: `ef27df6`; `mcp/samvil_mcp/event_sanitizer.py:25`,
    `mcp/samvil_mcp/event_sanitizer.py:30`, `mcp/tests/test_event_sanitizer.py:120`.
- [x] **4.89 legacy JSON transition flag의 provenance 승격 금지**
  (migration 전 event data가 스스로 `trusted_transition=true`를 주장해도 새 DB provenance
  column은 0으로 유지해 orchestration prerequisite로 소비하지 않는다.)
  - 완료 증거: `c0c8fc1`; `mcp/samvil_mcp/event_store.py:136`,
    `mcp/tests/test_event_store.py:122`.
- [x] **4.90 MCP 프로세스 간 stage 보상 경계 직렬화**
  (process-local asyncio lock에 DB/session별 flock을 더해 event+stage transaction부터
  canonical append 실패 보상 완료까지 다른 MCP 프로세스의 후속 전환을 차단한다.)
  - 완료 증거: `c052a02`; `mcp/samvil_mcp/server.py:273`,
    `mcp/samvil_mcp/server.py:293`, `mcp/samvil_mcp/server.py:1182`,
    `mcp/tests/test_orchestrator_mcp.py:1342`.
- [x] **4.91 보호 SSOT·EventStore의 우회 overwrite 차단**
  (임의 source의 cp/install/mv, in-place sed, ln, runtime copy와 URI·home·symlink alias를
  통한 canonical EventStore 교체·삭제·직접 write를 차단하고 안전한 임시 파일은 허용한다.)
  - 완료 증거: `f80864b`; `hooks/guard_destructive.py:644`,
    `hooks/guard_destructive.py:663`, `mcp/tests/test_guard_destructive.py:545`,
    `mcp/tests/test_guard_destructive.py:571`.
- [x] **4.92 blueprint 화면·장면 referential integrity 검증**
  (web/dashboard route target, mobile tab screen, game scene-flow source·target이 각 canonical
  name list에 실제 존재해야 하며 tabs navigation은 비어 있을 수 없다.)
  - 완료 증거: `bddccb0`; `mcp/samvil_mcp/server.py:1411`,
    `mcp/samvil_mcp/server.py:1481`, `mcp/samvil_mcp/server.py:1582`,
    `mcp/tests/test_orchestrator_mcp.py:713`, `mcp/tests/test_orchestrator_mcp.py:718`.
- [x] **4.93 directory destination의 보호 파일 overwrite 차단**
  (`cp source .`, `cp -t`, `cp samvil.db ~/.samvil`처럼 destination directory와 source
  basename이 결합돼 보호 SSOT·EventStore가 되는 경로도 최종 target으로 분석한다.)
  - 완료 증거: `c1b8c32`; `hooks/guard_destructive.py:734`,
    `mcp/tests/test_guard_destructive.py:545`.
- [x] **4.94 QA event의 canonical lock·index writer 통합**
  (QA synthesis도 별도 raw append를 하지 않고 공용 canonical writer를 사용해 동시 writer와
  같은 flock·fsync·line index 계약을 따른다.)
  - 완료 증거: `b030da4`; `mcp/samvil_mcp/server.py:687`,
    `mcp/samvil_mcp/qa_synthesis.py:524`, `mcp/tests/test_qa_synthesis.py:269`.
- [x] **4.95 arbitrary namespaced secret key redaction**
  (`STRIPE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY`처럼 vendor prefix 뒤의 secret/service-role
  key도 자유 event 문자열에서 값 전체를 제거한다.)
  - 완료 증거: `de0ab71`; `mcp/samvil_mcp/event_sanitizer.py:25`,
    `mcp/tests/test_event_sanitizer.py:120`.
- [x] **4.96 rsync·Perl in-place 보호 SSOT mutation 차단**
  (copy-like rsync와 `perl -pi`가 cp/sed와 동일한 protected destination 검사를 통과하고,
  read-only Perl·안전한 임시 rsync는 계속 허용한다.)
  - 완료 증거: `9367340`; `hooks/guard_destructive.py:63`,
    `hooks/guard_destructive.py:901`, `hooks/guard_destructive.py:907`,
    `mcp/tests/test_guard_destructive.py:545`.
- [x] **4.97 same-command symlink EventStore alias 추적**
  (분석 시점에 존재하지 않는 alias도 앞선 literal `ln -s` segment에서 추적해 후속 DB write·
  overwrite는 canonical target 기준으로 차단하고 read-only query는 허용한다.)
  - 완료 증거: `e281ba2`; `hooks/guard_destructive.py:683`,
    `mcp/tests/test_guard_destructive.py:598`.
- [x] **4.98 non-object chain marker의 fail-closed 처리**
  (유효 JSON이어도 list·string·number·bool이면 marker object가 아니므로 `None`으로 처리해
  advance/status `.get()` crash 없이 pipeline-complete 안전 응답을 반환한다.)
  - 완료 증거: `0f80bea`; `mcp/samvil_mcp/chain_markers.py:97`,
    `mcp/tests/test_chain_markers.py:106`.
- [x] **4.99 QA multi-event batch의 원자 append·retry 안전성**
  (여러 QA event 중 후속 직렬화가 실패하면 batch 시작 offset까지 전부 truncate하고,
  재시도 시 선행 event가 중복되지 않도록 index도 batch 단위로 갱신한다.)
  - 완료 증거: `f3d52d3`; `mcp/samvil_mcp/server.py:687`,
    `mcp/samvil_mcp/qa_synthesis.py:543`, `mcp/tests/test_qa_synthesis.py:307`.
- [x] **4.100 보호 handoff SSOT의 실행 지침 정합성**
  (guard가 차단하는 Bash `cat >>`를 활성 Skill에서 제거하고, handoff append는 Edit 전용으로
  안내해 보호 정책과 실제 실행 계약을 일치시킨다.)
  - 완료 증거: `b41a100`; `skills/samvil-qa/SKILL.md:107`,
    `skills/samvil-build/SKILL.md:101`, `mcp/tests/test_skill_wiring.py:504`.
- [x] **4.101 legacy session의 provenance 재검증 복구**
  (과거 JSON flag는 trusted column으로 승격하지 않되 column 최초 migration 때만 session을
  interview로 되돌려 gate를 재실행할 수 있게 하고, 이후 trusted transition은 유지한다.)
  - 완료 증거: `eac6f7e`; `mcp/samvil_mcp/event_store.py:135`,
    `mcp/samvil_mcp/event_store.py:138`, `mcp/tests/test_event_store.py:122`.

---

## 8. Wave 5 — 선택 흡수 (여유 시, 사용자 재가 후)

- [ ] **5.1 PAL Router 경량판 (retry 시 모델 tier 승격)**
  config.json의 model_routing 인프라 위에: leaf 빌드 실패 재시도 시 해당 leaf만
  한 단계 위 모델로(haiku→sonnet→opus). Ouroboros처럼 frugality proof까지 갈
  필요 없음 — 승격 이벤트만 events.jsonl에 기록해 retro가 "어떤 leaf가 비싼
  모델을 필요로 했나"를 보게.
- [ ] **5.2 세션 한도 대응 — 장기 빌드 분절 계약**
  실런 사망 원인 중 하나(image-batch-webp: build 완료 후 state 기록 전 세션 사망,
  zep-auto-test: 9+ phase 단일 세션 불가). background_jobs + leaf checkpoint를
  묶어 "N leaf마다 재개 가능 지점 보장"을 명문화.

**흡수 비권장 (명시적 non-goal)**: Ouroboros의 12-커널 지원, frugality proof 기계,
shadow replay, transcript grounding 전체 기계(2.1~2.6이 SAMVIL식 등가물),
동시 다층 verifier. 이유: 1인 유지 규모 초과 + SAMVIL 철학(Self-Contained,
Solo Developer First)과 충돌.

---

## 9. 진행 순서와 의존성

```
Wave 0 (실버그) ──→ Wave 1 (저장소/SSOT) ──→ Wave 2 (기계 증거) ──→ dogfood 실측
                                                    │
Wave 3 (UX 다이어트) ──────────────────────────────┤  (Wave 1과 병렬 가능,
                                                    │   3.4는 0.5 이후)
Wave 4 (구조 다이어트) ── 4.2는 Wave 2 완료 후 권장 ┘
Wave 5 (선택) ── 사용자 재가 후
```

- **최우선 경로**: 0 → 1 → 2. 이 셋이 "결과물이 못 미덥다"는 원 페인의 근본 수리.
- Wave 3은 독립성이 높아 병렬 진행 가능 (0.5 선행 필요).
- 각 Wave 종료 시: 사용자에게 요약 보고 + push/버전업 여부 확인 (실행 규칙 3).

## 10. 최종 완료 기준 (Definition of Done)

1. Wave 0~4 전 항목 체크 + 각 항목에 커밋 해시와 file:line 증거.
2. `bash scripts/pre-commit-check.sh` green (pytest 전체 포함).
3. dogfood 2회(web standard 1, 임의 solution_type 1) 실측:
   - `.samvil/events.jsonl` 존재 + stage_durations 채워짐 (G4)
   - QA 숫자가 test-results.json과 일치, 파괴 주입 시 게이트 실차단 (G1·G2)
   - 사용자 터치포인트 ≤ 12 (G5)
4. CHANGELOG 항목 작성(사용자 관점 서술), 버전 bump는 사용자 결정 대기.

### 완료 실측

- web standard: dashboard dogfood는 AskUserQuestion 12회, ambiguity 0.006,
  `converged=true` (`docs/evidence/evolution-2026-07-wave3-dogfood.md`).
- arbitrary solution type: standard automation dogfood는 canonical events에서
  interview 1000ms를 복원하고, raw test 3 = QA report 3을 확인했으며, 실패 주입 시
  deploy gate block, destructive command block, AskUserQuestion 12회,
  `converged=true`를 확인했다
  (`docs/evidence/evolution-2026-07-wave4-automation-dogfood.md`).
- `CHANGELOG.md`의 Unreleased에 사용자 관점 변경을 기록했고 version bump/push는
  요청대로 수행하지 않는다.

---

*작성: 2026-07-18, Claude(Fable 5) 전면 감사 세션. 감사 방법: 4관점 병렬 리뷰
(Python 코어 / 스킬·에이전트·훅 레이어 / E2E UX·실런 로그 / Ouroboros v0.50.4
소스 해부) + 척추 문서 직접 정독 + pytest 1940 green 실측.*
