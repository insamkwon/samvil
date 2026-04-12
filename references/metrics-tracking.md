# Metrics Tracking (INV-5)

각 스테이지 시작/종료 시 `.samvil/metrics.json`을 업데이트하는 규칙.

이 규칙은 체인의 **모든 스킬이 따라야 한다.**

## 스테이지 메트릭 기록

```
# 스테이지 시작 시 (각 스킬의 Boot Sequence에서):
metrics.json을 읽기
metrics.stages.<stage>.started_at = <ISO timestamp now>
metrics.json에 저장

# 스테이지 종료 시 (각 스킬이 다음 스킬 invoke 직전):
metrics.json을 읽기
metrics.stages.<stage>.ended_at = <ISO timestamp now>
metrics.stages.<stage>.duration_ms = ended_at - started_at (milliseconds)
# 스테이지별 추가 메트릭 기록 (아래 참고)
metrics.json에 저장
```

## 스테이지별 메트릭 필드

| Stage | Fields |
|-------|--------|
| `interview` | `questions_asked` (int) |
| `seed` | _(duration만)_ |
| `council` | `agents_spawned` (int), `rounds_completed` (int) |
| `design` | `agents_spawned` (int), `blueprint_generated` (bool) |
| `scaffold` | `stack` (string), `files_created` (int) |
| `build` | `features_total` (int), `features_passed` (int), `features_failed` (int), `builds_run` (int), `agents_spawned` (int) |
| `qa` | `pass_rate` (float 0~1), `iterations` (int), `verdict` (PASS/REVISE/FAIL) |
| `evolve` | `cycles_run` (int), `seed_versions_created` (int) |

## 체인 종료 시 (Retro 직전)

오케스트레이터 또는 마지막 스킬이:

```
metrics.json을 읽기
metrics.total_duration_ms = now - metrics.timestamp (milliseconds)
metrics.json에 저장
```
