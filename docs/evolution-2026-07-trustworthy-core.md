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
| G5 | 사용자 질문 다이어트 | standard ~25회 | **~12회 이하** | dogfood 런 터치포인트 카운트 |
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
- [ ] **0.7 rate_budget 크래시 워커 slot 영구 누수**
  `rate_budget.py:93` `_replay`가 TTL/heartbeat 없이 acquire/release 쌍으로만
  재구성 → 크래시한 워커의 slot이 영원히 점유. 수정: acquire 레코드에 timestamp
  기반 TTL(기본 30분) 추가, replay 시 만료 acquire 무시 + 테스트.
- [ ] **0.8 positional `save_event` 예시 교정**
  `samvil-pm-interview/SKILL.md:67-68`, `samvil-update/SKILL.md:88`이 positional
  호출 예시 — 나머지 전부 keyword-only라 LLM이 복사하면 InputValidationError.
  keyword 형태로 통일.

**Wave 0 완료 기준**: pre-commit green + 신규 회귀 테스트 전부 포함 + 위 8건 각각
독립 커밋.

---

## 4. Wave 1 — 이벤트 저장소 단일화 + SSOT 크래시 내성 (균열 ②③)

> 목적: "File is SSOT"(INV-1)를 선언이 아니라 사실로 만든다. 복구·스톨감지·retro가
> 처음으로 실전 작동하게 된다. **Wave 2(기계 증거)가 이 위에 선다** — 증거를
> 기록할 저장소부터 신뢰 가능해야 한다.

- [ ] **1.1 save_event 이중쓰기: 프로젝트 events.jsonl을 canonical로**
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
- [ ] **1.2 동명 프로젝트 세션 오염 수정**
  `event_store.py:129` `find_session_by_project`가 이름만 조회 → 같은 이름의 다른
  프로젝트 세션 오염. project_root 절대경로(또는 그 해시)를 세션 레코드에 저장하고
  조회 키에 포함.
- [ ] **1.3 SSOT writer 전체에 락+원자쓰기 적용**
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
- [ ] **1.4 hook의 state 파일 read-modify-write 원자화**
  `hooks/_contract-helpers.sh:291-302`가 락 없이 별도 python 프로세스로
  read-modify-write. heredoc python에서 fcntl.flock + tmp/rename 적용.
  (hook은 여전히 best-effort exit 0 유지 — P8.)
- [ ] **1.5 orchestrator deploy dead-mapping 정리**
  `orchestrator.py:124` deploy가 `should_skip_stage` 항상 True인데
  `SUCCESS_COMPLETE_EVENTS["deploy"]` 존재. 실제 의도(deploy는 opt-in 스테이지)에
  맞게 정리하고 죽은 매핑 제거.

**Wave 1 완료 기준**: dogfood 1회에서 `.samvil/events.jsonl` 생성·성장 실측 +
`query_projection`/stall/retro가 그 파일에서 실데이터를 읽는 것 확인 (증거 스샷/로그).

---

## 5. Wave 2 — 기계 증거 게이트 (균열 ① — 이 진화의 심장)

> 목적: "PASS"의 근거를 LLM 자가 신고에서 **하네스가 직접 실행·파싱한 아티팩트**로
> 옮긴다. Ouroboros의 transcript-grounding 원칙을, SAMVIL이 이미 가진
> tests-as-deliverable(v4.31) 자산으로 싸게 구현한다.

- [ ] **2.1 `collect_stage_evidence` MCP 도구 신설 (기계 증거 수집기)**
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
- [ ] **2.2 gate_check의 기계 metrics 모드**
  설계: `gate_check`에 `evidence_mode` 추가 — build/qa 게이트의 핵심 metrics
  (build_ok, test_pass_rate, runtime_verified)는 **호출자가 준 값이 있어도
  `collect_stage_evidence` 결과로 덮어쓴다**(LLM 공급값은 참고 필드로 보존해
  불일치 시 헬스 로그에 기록 — 이 불일치 자체가 리워드 해킹 신호다).
  스킬 배선: samvil-build Phase Z(:96)와 samvil-qa(:85)의 gate_check 호출을
  evidence_mode로 전환. **"best-effort" 문구에서 gate_check는 제외** —
  build/qa 게이트 실패 시 스킬은 진행 불가(3.3의 override 경로만 예외).
- [ ] **2.3 QA verdict 등급 분리 — `PASS(runtime)` vs `PASS(static)`**
  설계: `qa_finalize`/`qa_synthesis`의 verdict에 `verification_mode:
  "runtime"|"static"` 필드 추가. Playwright 폴백(samvil-qa/SKILL.md:31) 시
  static으로 강등 표기. **deploy 진입 게이트(qa_to_deploy)는
  `verification_mode == "runtime"`을 요구** — static이면 block + 사용자에게
  "runtime 검증 없이 배포하시겠어요? (위험: ...)" AskUserQuestion (3.3 경로).
  회귀 테스트: static PASS가 deploy 게이트에서 막히는지, override 시 claim에
  기록되는지.
- [ ] **2.4 `force_proceed` 제도화 (게이트 우회의 공식 경로)**
  현재: 어떤 스킬 프로즈에도 정의 없이 LLM이 임의로 씀(zep-auto-test 실증).
  설계:
  - gates.py에 `gate_override(gate, reason, approved_by="user")` 도구 신설 —
    claim ledger에 `type="gate_override", overridden_by="user", reason` 기록.
  - 스킬 규약: 게이트 block 시 유일한 진행 경로는 AskUserQuestion으로 사용자
    명시 승인 → `gate_override` 호출 → 진행. **승인 없이 진행하는
    force_proceed는 anti-pattern으로 전 스킬에 명문화.**
  - `contract-stage-end.sh`의 게이트 판정부가 override claim 존재를 인지하도록
    갱신.
- [ ] **2.5 AC 성공 계약 (경량판 AcceptanceCriterionSpec)**
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
- [ ] **2.6 리워드 해킹 결정론 검사 1건 추가 (Ouroboros 차용, 최소판)**
  `semantic_checker.py`에 셸 시맨틱 검사 추가: 테스트 명령이 `| tail`/`| grep`류
  파이프 뒤에서만 성공 판정되는 로그 형태면(exit code 마커 부재) 증거로 인정하지
  않음(EVIDENCE_FORM_MISMATCH 류 사유 반환). 2.1의 `SAMVIL_EXIT:` 마커 표준이
  있으므로 검사가 단순해진다.

**Wave 2 완료 기준**: dogfood(web 계열 1개)에서 (a) QA 리포트의 pass 숫자가
`.samvil/test-results.json`과 byte-일치, (b) 의도적으로 테스트 1개를 깨뜨렸을 때
gate가 LLM 서술과 무관하게 block, (c) static 폴백 강제 시 deploy가 막히고 override
경로가 claim에 남는 것 — 3가지 실측 증거.

---

## 6. Wave 3 — UX 다이어트 (균열 ⑤)

> 목적: standard tier 사용자 확인 ~25회 → **12회 이하**. "one-line → app" 약속을
> 실제 경험에 근접시킨다.

- [ ] **3.1 인터뷰 질문 예산제 (min → max 전환)**
  설계: `references/decision-boundaries.md`에 tier별 `max_questions` 단일 정의
  (제안: minimal 6 / standard 12 / thorough 20 / full 30). interview_engine에
  예산 카운터 추가 — 예산 소진 시 ambiguity가 임계 미달이어도 **"지금까지로 seed
  초안을 만들까요, 몇 가지 더 물을까요?"** 강제 오퍼(사용자가 연장 선택 시 +5).
  "No phase reprompt cap"(SKILL.md:70) 문구 제거. 진행률 표시: 매 질문에
  `[질문 7/12]` 프리픽스.
- [ ] **3.2 배치 질문 (왕복 절반화)**
  같은 Phase 내 독립 질문 2-3개를 AskUserQuestion 1회의 다중 질문(questions
  배열)으로 묶는 규약을 interview SKILL에 명문화. 서로 의존하는 질문만 순차.
- [ ] **3.3 오케스트레이터 시작 질문 3→1**
  - L3 solution_type 확인(samvil/SKILL.md:62-64): `confidence == high`면 확인
    생략하고 진행 알림만(ℹ️ 아이콘, P7) — anti-pattern 2(:109)를 "저신뢰일 때만
    확인"으로 완화. P2는 '결정'에 적용되는 원칙이지 키워드 타입 판별은
    description 영역이다.
  - 모드 질문(:54): brownfield 아티팩트 감지가 명확하면 생략.
  - tier 질문(:58)만 유지 (이게 진짜 사용자 결정).
- [ ] **3.4 ambiguity 스코어러 정리 + 한국어 대응**
  - 중복 스코어러 2개(interview_engine.score_ambiguity 10-dim vs
    interview_v3_2.compute_seed_readiness 5-dim — 후자는 LLM이 점수를 직접 매기게
    지시) 중 **engine 쪽으로 단일화**. compute_seed_readiness의 LLM 자가 채점은
    폐기(균열 ①의 인터뷰판).
  - vague 휴리스틱에 한국어 패턴 추가: "좋은/좋게", "빠른/빠르게", "간단한",
    "예쁘게", "직관적", target_user "누구나/모두/사람들". 길이 임계도 한국어 밀도
    보정(한글은 10자→6자 수준). 테스트: 한국어 vague 입력 fixture.
- [ ] **3.5 council 운명 확정**
  현상: 제거 예고(samvil-council/SKILL.md:13-14 "--council opt-in, v3.3 제거") vs
  오케스트레이터 Step 5가 태스크 생성(samvil/SKILL.md:76) vs seed가 standard+에서
  체인(samvil-seed/SKILL.md:92) vs 실런(classic-snake)에선 실행됨 — 4중 모순.
  **기본 결정(사용자 재가 전 default): 체인에서 완전 제거** — 오케스트레이터
  태스크 목록·seed 체인에서 빼고, `--council` 플래그 시에만 seed가 직접 라우팅.
  회귀: 오케스트레이터가 council 태스크를 만들지 않는지.
- [ ] **3.6 dogfood 터치포인트 실측**
  Wave 3 완료 후 standard tier 웹앱 1회 dogfood — AskUserQuestion 횟수를 세서
  이 문서 G5에 실측치 기록. 12회 초과 시 초과 원인 항목화(다음 wave 재료).

---

## 7. Wave 4 — 구조 다이어트 (균열 ④ + 유지비)

> 목적: 드리프트가 재발할 수 없는 구조. 삭제가 기능이다.

- [ ] **4.1 thin↔legacy 공유 상수의 단일 소스화 + drift CI**
  임계값·MAX_RETRIES·tier 테이블·게이트 이름 등 두 파일에 모두 나타나는 상수를
  `references/decision-boundaries.md`(기존 SSOT 선언 활용)에만 정의하고
  thin/legacy는 인용. `check-skill-wiring.py`에 "thin과 legacy에 동시에 등장하는
  수치 상수 불일치" 검출 추가. (0.5에서 인터뷰 건은 선행 처리됨 — 여기서 전 스킬
  일반화.)
- [ ] **4.2 contract layer의 hook 소유화 (스킬 프로즈에서 제거)**
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
- [ ] **4.3 에이전트 50→~40 + 문서 일치**
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
- [ ] **4.4 references 대청소 (65→~48)**
  orphan 27개 처분: 초소형 schema stub 8개 → `samvil-ssot-schema.md`로 통합,
  `migration-v2-to-v3` 아카이브, `gate-vs-degradation`→`graceful-degradation` 흡수,
  `plugin-api`+`plugin-system` 병합, `interview-levels`→`interview-frameworks` 흡수.
  **규범적 orphan(decision-boundaries, reversibility-guide, model-routing-guide)은
  삭제 금지 — 해당 스킬에서 실제 링크**(4.1이 decision-boundaries를 살리는 것과
  정합).
- [ ] **4.5 guard-destructive 강화 (speed-bump → 실가드)**
  현상: glob substring이라 공백 변형(`rm  -rf /`, `rm -fr /`)·변수(`rm -rf $X`)·
  `.next` 문자열 disarm 전부 우회, `git push -f` 미커버, SQL 대문자만.
  수정: `$TOOL_INPUT` JSON에서 command 필드를 추출해 정규화(연속 공백 축약,
  소문자화) 후 정규식 매칭. 커버 추가: `git push -f|--force`(force-with-lease
  제외), `rm -fr`, 옵션 순서 무관, SQL 대소문자 무관. 우회 시나리오를 테스트
  fixture로.
- [ ] **4.6 멀티호스트 정직화**
  **기본 결정: 문서 정직화 경로.** README·CLAUDE.md·glossary에서 현 상태를
  "Claude Code 네이티브 + Codex는 모델 라우팅 통합(네이티브 실행 아님) + Gemini
  실험적 stub"으로 명시. `check-host-parity.py`의 공허 통과(QA parity 양쪽 빈
  집합 :57,71, Gemini 미검사 :39-41)를 "미검사 항목은 red가 아니라 UNTESTED로
  표기"하도록 수정 — green 착시 제거. (네이티브 parity 실구현은 이번 범위 밖 —
  Mountain MA2/MA3로 유지.)
- [ ] **4.7 server.py 도메인 분할 계속 (기계적 반복)**
  기확립 패턴(`tools_jobs.py` + `register_*_tools`) 그대로: 한 커밋당 한 도메인
  (tools_qa, tools_evolve, tools_session, tools_release...), 매 커밋 도구 수 불변
  assert. 5,696 LOC → 도메인당 수백 LOC 라우터로.

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

---

*작성: 2026-07-18, Claude(Fable 5) 전면 감사 세션. 감사 방법: 4관점 병렬 리뷰
(Python 코어 / 스킬·에이전트·훅 레이어 / E2E UX·실런 로그 / Ouroboros v0.50.4
소스 해부) + 척추 문서 직접 정독 + pytest 1940 green 실측.*
