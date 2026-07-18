# Wave 2 Mechanical Evidence Dogfood

- 실행일: 2026-07-18
- 테스트: `mcp/tests/test_wave2_dogfood.py`
- 실행 명령: `cd mcp && .venv/bin/python -m pytest tests/test_wave2_dogfood.py -q`
- push/deploy: 수행하지 않음

## 실측 결과

1. Playwright JSON reporter fixture의 `stats.expected=3`을 수집기가 `passed=3`으로
   읽었고, materialized `.samvil/qa-report.md`에도 `passed=3`이 기록됐다.
2. 호출자 metrics가 `test_pass_rate=1.0`, `runtime_verified=true`라고 주장한 상태에서
   reporter fixture를 `expected=2`, `unexpected=1`로 깨뜨리자 기계 값은
   `test_pass_rate=0.666667`이 되었고 `qa_to_deploy`는 `block`을 반환했다.
3. QA log와 reporter를 제거해 static fallback을 강제하자
   `verification_mode=static`, gate verdict `block`이 확인됐다. 그 block 뒤 사용자
   승인 `gate_override`를 기록하자 verified claim이 ledger에 남고 active override로
   조회됐다.

## 자동 회귀 증거

- raw reporter ↔ QA report pass 수 일치:
  `mcp/tests/test_wave2_dogfood.py:40`
- 고장 난 테스트가 서술형 PASS metrics를 덮어쓰고 gate block:
  `mcp/tests/test_wave2_dogfood.py:47`
- static deploy block + override claim 기록:
  `mcp/tests/test_wave2_dogfood.py:69`
