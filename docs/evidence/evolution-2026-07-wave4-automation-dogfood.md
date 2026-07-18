# Wave 4 standard automation trustworthy-core dogfood

- 기준일: 2026-07-18
- 시나리오: `매일 파트너 CSV를 정리해서 슬랙으로 보내는 자동화`
- tier / solution: `standard` / `automation` (`confidence=high`)
- 실행: `mcp/.venv/bin/python scripts/wave4-automation-dogfood.py`
- 회귀: `cd mcp && .venv/bin/python -m pytest tests/test_wave4_automation_dogfood.py -q`
- push/deploy: 수행하지 않음

## 실측 결과

```json
{
  "events_file_exists": true,
  "stage_durations_ms": {"interview": 1000},
  "raw_test_passed": 3,
  "qa_reported_passed": 3,
  "injected_failure_gate_verdict": "block",
  "destructive_guard_blocked": true,
  "ask_user_question_calls": 12,
  "interview_ambiguity": 0.038,
  "interview_converged": true
}
```

## 판정

- 프로젝트 canonical `.samvil/events.jsonl`에서 interview duration 1000ms를
  복원했다.
- Playwright-style reporter 원시 `expected=3`과 QA materialization의
  `runtime_evidence.passed=3`이 일치했다.
- reporter에 실패 1개를 주입하자 서술형 PASS metrics를 무시하고
  `qa_to_deploy=block`이 됐다.
- `rm -fr $TARGET` destructive 변형은 hook에서 차단됐다.
- standard automation happy path의 AskUserQuestion 호출은 12회로 목표 이하다.
