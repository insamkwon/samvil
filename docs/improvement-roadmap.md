# SAMVIL Robustness Roadmap (2026-06)

> `/goal` 실행용 SSOT. Wave당 goal 1개로 돌린다. 완료한 항목은 체크박스를
> 체크하고 커밋 해시 + 핵심 evidence(file:line)를 항목 아래에 한 줄 남긴다.
> 배경: 2026-06-12 코드베이스 분석 + ouroboros(Q00) 아키텍처 비교에서 도출.

## 실행 규칙 (모든 Wave 공통)

1. **항목 1개 = 커밋 1개.** Conventional Commit 메시지 (fix/feat/improve/chore).
2. 매 커밋 전 `bash scripts/pre-commit-check.sh` exit 0 필수. `--no-verify` 금지.
3. **push 금지.** push + 버전업은 Wave 종료 후 사용자가 결정한다.
4. 요청 범위 밖 코드 수정 금지 (Zero-Refactor Rule).
5. MCP 변경 시 `cd mcp && .venv/bin/python -m pytest tests/` green 확인.
6. 스킬/훅 변경 시 `scripts/check-skill-wiring.py` green 확인.
7. 항목 완료 판정에는 file:line evidence 필수 (P1).

---

## Wave 1 — 기반 다지기

- [x] **1.1 claim_ledger 파일 잠금**
  ✅ done — evidence: `mcp/samvil_mcp/claim_ledger.py:62` (`_locked`),
  post/verify/reject 잠금 적용, `integrity_errors()` + stats 노출,
  `mcp/tests/test_claim_ledger_lock.py` 4 tests green.
  `mcp/samvil_mcp/rate_budget.py`의 `_locked()` (fcntl.flock + `_HAS_FLOCK`
  폴백) 패턴을 `mcp/samvil_mcp/claim_ledger.py`의 post/verify/reject에 적용.
  로드 시 중복 claim_id 무결성 검사 추가.
  AC: 동시 post 테스트(`mcp/tests/`) 추가 + pytest green.
- [x] **1.2 hook 헬스 가시화**
  ✅ done — evidence: `hooks/_contract-helpers.sh` (`samvil_contract_log_health`,
  python-unavailable bash 폴백 포함), stage-start/end 양쪽 wiring,
  `health_check`에 `hook_failures_24h` + summary `Hooks ✅/⚠️`,
  `skills/samvil/SKILL.md` 부트 테이블 Hooks 행, tmp dir fire test 통과,
  `mcp/tests/test_health_check_hooks.py` 3 tests green.
  `hooks/_contract-helpers.sh` 경유 실패가 stderr로만 가는 문제. hook
  exit 상태를 `.samvil/mcp-health.jsonl`에 기록하고, samvil 오케스트레이터
  부트 헬스 테이블에 hook 상태 1줄 추가.
  AC: tmp dir에서 수동 fire test로 기록 확인. hook은 여전히 exit 0 유지 (P8).
- [x] **1.3 유틸 중복 제거**
  `_read_json_safe()`가 `build_phase_a.py`와 `build_phase_z.py`에 중복.
  `mcp/samvil_mcp/utils.py`로 추출 후 양쪽 import.
  AC: pytest green, 동작 동일.
  ✅ done — 실제 중복은 6개 모듈(2 변형)이었음: build_phase_a/z, qa_boot,
  qa_finalize (`read_json_safe`), resume, orchestrator (`read_json_or_empty`).
  evidence: `mcp/samvil_mcp/utils.py:14`, `mcp/tests/test_utils.py` 4 tests,
  전체 suite 1858 passed.
- [x] **1.4 미사용 도구 역방향 감사 (리포트만)**
  ✅ done — evidence: `scripts/check-skill-wiring.py` `--report` 모드 +
  `docs/unused-tools-report.md` (194 tools / 71 uncited / 26 deletable).
  보너스: 기존 역방향 체크 regex가 sync `def` 도구 31개를 못 보던 버그 수정,
  신규 가시화된 24개를 사유와 함께 allowlist 등록. scripts 자기참조 오염 제거.
  `scripts/check-skill-wiring.py` 확장: server.py의 `@mcp.tool()` 이름 중
  어떤 `skills/*/SKILL.md`(+ `.legacy.md`)에도 참조되지 않는 것 목록 출력.
  이 단계에서는 삭제하지 않는다. 결과를 `docs/unused-tools-report.md`로 저장.
  AC: 리포트 파일 생성, 도구별 사용처 0건 근거 포함.

## Wave 2 — 도구 정리 + 복원력

- [x] **2.1 미사용 도구 단계적 삭제**
  Wave 1.4 리포트 기반. doctor/디버깅용 화이트리스트 먼저 정의.
  한 커밋에 최대 10개씩 삭제, 매 커밋마다 wiring + pytest green.
  AC: 미사용 도구 0개(화이트리스트 제외), 전체 도구 수 감소 기록.
  ✅ done — 도구 194 → 186 (8개 삭제: validate_state, extract_query,
  format_research, adversarial_prompt, loop_should_stop, read_repair_report,
  render_repair_report, read_release_evidence_bundle). 모듈 함수는 유지
  (테스트가 모듈 직접 검증). 보존 결정: mechanical_toml 3종(v4.26 문서화된
  보류), compute_parallel_safety(W5.1), evaluate_qa_convergence(W4.2 후보),
  leaf checkpoint read/clear(write 사용 중), Mountain 복구 5종(W5.3에서
  모듈 단위 처분), 디버그 조회(get_events/list_sessions/list_checkpoints).
  체인 3종(advance_chain 등)은 W2.2에서 처분 결정. 잔여는 전부
  allowlist에 사유 기록됨. evidence: `docs/unused-tools-report.md` 재생성
  (63 uncited / 18 deletable), pytest 1858 passed, stdio roundtrip OK.
- [x] **2.2 체인 폴백 마커**
  스킬 체인 invoke 실패 시 `.samvil/next-skill.json` 자동 기록 +
  `chain_attempt` 이벤트(save_event) 추가. `_EVENT_TYPE_TO_STAGE` 등
  server.py 매핑 갱신 (CLAUDE.md 체크리스트 준수).
  AC: stdio roundtrip 테스트 green, QA→Retro 전환 경로에 우선 적용.
  ✅ done — 설계 변경: 스킬 본문 수정 대신 **hook 핸드셰이크**로 결정론화
  (120줄 thinness 캡 보호 + 이벤트 매핑 churn 회피. save_event는 v3.2부터
  lenient라 신규 enum 불필요; 관측은 W1.2의 hook health 채널 재사용).
  stage-end hook이 기대 next-skill 마커 기록 → stage-start hook이 진입
  일치 시 클리어 / divergence 시 fail 기록 → 마커 생존 = 체인 단절 =
  `resume_session()`이 마커의 next_skill을 복구 지점으로 우선 사용.
  QA→Retro 포함 전 전환에 일괄 적용됨. evidence:
  `hooks/contract-stage-end.sh` (marker write), `hooks/contract-stage-start.sh`
  (handshake), `mcp/samvil_mcp/resume.py` (`chain_marker` 필드),
  tmp dir fire test: 기록→클리어→divergence 감지 확인,
  `mcp/tests/test_resume.py` 37 passed.
- [x] **2.3 transient 오류 재시도**
  ✅ done — evidence: `mcp/samvil_mcp/error_classifier.py` (transient
  화이트리스트 12패턴 + permanent override 6패턴, 보수적: unknown→permanent,
  permanent 신호가 transient와 공존 시 permanent 우선), server.py
  `classify_build_failure` 도구 (P8: 분류기 장애 시 permanent 폴백),
  samvil-build Circuit Breaker wiring (transient → backoff 재시도 1회,
  breaker 카운트 미소모), samvil-deploy는 P10 유지 — 자동 재시도 없이
  리포트 주석만. `mcp/tests/test_error_classifier.py` 9 tests green.
  오류 분류기: transient 화이트리스트(network error / timeout /
  ECONNREFUSED / 503)만 백오프 1회 재시도, 나머지는 즉시 실패 유지.
  build/deploy 경로에 적용.
  AC: 분류기 단위 테스트 + 기존 circuit breaker(MAX_RETRIES=2)와 충돌 없음.

## Wave 3 — 스킬 구조 정리

- [ ] **3.1 부트 시퀀스 템플릿화**
  12개 스킬의 ~50줄 중복 부트 시퀀스를 `references/skill-boot-template.md`로
  추출. 핵심 3줄(save_event / jurisdiction / 파일 read)은 각 스킬에 인라인
  유지. `check-skill-wiring.py`에 부트 드리프트 검출 추가.
  AC: 12개 스킬 모두 템플릿 참조, wiring green.
- [ ] **3.2 compose_agent_prompt MCP 도구**
  에이전트 프롬프트 조립을 MCP가 소유: `compose_agent_prompt(agent_names,
  context)` 신설 → `agents/*.md` 로딩 + 컨텍스트 주입 + 최종 프롬프트 반환.
  council/qa/evolve 스킬의 `<paste agents/*.md>` 패턴 교체.
  MCP 장애 시 agent 파일 직접 read 폴백 유지 (P8, INV-5).
  AC: 단위 테스트 + 3개 스킬 wiring green + 이중 소스 제거 확인.
- [ ] **3.3 legacy 레시피 분할**
  비대 순서대로 samvil-qa(1,722줄) → samvil-scaffold(1,662줄) →
  samvil-build(1,442줄)의 `.legacy.md`를 solution_type별 recipe 파일로 분할,
  단계 ID로 인덱싱. 나머지 스킬은 범위 외.
  AC: 폴백 경로가 "스킬 → recipe 파일 직행"으로 단축됨.

## Wave 4 — 도약: Background Jobs + Ralph Loop (MINOR)

> ouroboros(Q00) 패턴 흡수. 코드 복사가 아니라 패턴 이식.
> 전제: Wave 1.1(잠금) + Wave 2.2(체인 폴백) 완료 — 동시 쓰기/무인 실패 증폭 방지.

- [ ] **4.1 Background Job 시스템 (최소 범위)**
  `start_build` / `job_status` / `job_result` / `cancel_job` 4개 도구 +
  heartbeat 기록. job 상태는 events 기반 영속(QUEUED→RUNNING→
  COMPLETED/FAILED/CANCELLED). zombie 감지는 v2로 보류.
  AC: 빌드를 백그라운드로 시작 → 다른 입력 가능 → 폴링으로 결과 수신,
  E2E 직접 검증.
- [ ] **4.2 MCP 소유 Ralph Loop 컨트롤러**
  루프 제어를 LLM에서 MCP로: max_iterations, oscillation window(3),
  regression window(2)를 결정론적으로 판정하는 도구 신설.
  samvil-qa Ralph 루프에 우선 wiring (evolve는 후속).
  AC: 진동/퇴화 시나리오 단위 테스트 + QA 체인에서 동작 확인.

## Wave 5 — 마무리 (선택)

- [ ] **5.1 QA Pass 2 병렬화** — `compute_parallel_safety` 활용, leaf 배치 스폰.
- [ ] **5.2 drift 측정 도구** — goal(0.5)/constraint(0.3)/ontology(0.2) 가중 이탈도.
- [ ] **5.3 server.py 도메인 분할** — Wave 2.1 이후 실행 (이중 작업 방지).
- [ ] **5.4 projection 쿼리 도구** — 기존 aiosqlite event store 위에 시점 상태 재구성.
