# Wave 3 standard dashboard touchpoint dogfood

- 기준일: 2026-07-18
- 시나리오: `에이전시 프로젝트 KPI 대시보드`, standard tier, greenfield, Council default-off
- 실행 명령: `python3 scripts/wave3-touchpoint-dogfood.py`
- 회귀 명령: `cd mcp && .venv/bin/python -m pytest tests/test_wave3_touchpoint_dogfood.py -q`

## 결과

- `solution_type=dashboard`, `confidence=high`: 모드·L3 확인 질문 생략.
- 인터뷰 질문 10개를 4회 배치로 실행.
- 결정론적 ambiguity `0.006`, `converged=true`.
- AskUserQuestion 호출 **12회 / 목표 12회 이하** — PASS.
- `council_opt_in=false`: Seed → Design 기본 체인.

## 터치포인트 내역

| 단계 | 확인 | 호출 |
|---|---|---:|
| Orchestrator | tier 선택 | 1 |
| Interview | Epic Claim 확인 | 1 |
| Interview | core/scope/lifecycle/success metric 10문항, 4개 배치 | 4 |
| Interview | summary / restate / pain capture | 3 |
| Seed | principles / concrete behavior / final approval | 3 |
| **합계** |  | **12** |

## 측정 경계

AskUserQuestion은 host-bound라 MCP 이벤트로 직접 기록되지 않는다. 따라서 이
dogfood는 실제 `aggregate_orchestrator_state` 분기와 `score_ambiguity`
수렴 결과를 실행하고, thin skill의 happy-path 확인점을 명시적 ledger로
카운트한 재현 가능한 실측이다. 수정 요청·게이트 실패·예산 연장 같은
조건부 재질문은 happy path 범위에서 제외했다.

## 증거

- `scripts/wave3-touchpoint-dogfood.py`: 실제 라우팅·수렴 실행 + 터치포인트 ledger.
- `mcp/tests/test_wave3_touchpoint_dogfood.py`: 12회 상한, 10문항 수렴,
  high-confidence 자동 확인, Council default-off 회귀.
