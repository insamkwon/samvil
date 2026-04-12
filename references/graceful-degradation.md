# Graceful Degradation (INV-7)

MCP 서버가 다운되거나 응답하지 않을 때 파일 기반으로 폴백하는 규칙.

**핵심 원칙:** `project.state.json`, `.samvil/metrics.json`, `.samvil/events.jsonl`은 항상 파일에 먼저 기록. MCP는 보조 채널.

## Dual-Write Pattern (모든 스킬 공통)

각 스킬이 상태를 변경할 때마다 다음 순서로 이벤트를 기록:

1. **항상 파일에 먼저 기록** — `.samvil/events.jsonl`에 append (절대 실패하지 않음)
2. **MCP는 best-effort** — `mcp__samvil_mcp__save_event` 호출 시도. 성공하면 좋고, 실패해도 파이프라인 계속 진행
3. **실패 시 기록** — MCP 호출이 실패하면 `.samvil/mcp-health.jsonl`에 `{status:"fail", tool:"<name>", error:"<msg>", timestamp:"..."}` append

```
# 파일 기록 (항상 실행)
append to .samvil/events.jsonl: {"event_type":"<type>","stage":"<stage>","data":{...},"timestamp":"<ISO>"}

# MCP 호출 (best-effort)
try:
  mcp__samvil_mcp__save_event(session_id=..., event_type=..., stage=..., data=...)
except:
  append to .samvil/mcp-health.jsonl: {"status":"fail","tool":"save_event","error":"<error>"}
```

**Retro에서 MCP 건강 리포트를 출력** — `.samvil/mcp-health.jsonl`이 있으면 성공률 집계.

## MCP 장애 감지

MCP 호출 시 다음 증상이 나타나면 장애로 판단:
- `mcp__samvil_mcp__*` 도구가 응답하지 않음 (timeout)
- MCP 도구 호출 시 에러 반환
- `mcp__samvil_mcp__health_check` 실패

**초기 감지** (Health Check 시):
```bash
# MCP health check (best-effort)
# MCP 도구가 보이지 않으면 자동으로 파일 모드로 전환
```

장애 감지 시 출력:
```
[SAMVIL] MCP 서버 응답 없음. 파일 기반 추적으로 전환합니다.
  상태 파일: project.state.json
  메트릭: .samvil/metrics.json
  이벤트: .samvil/events.jsonl
```

## 파일 기반 폴백 규칙

| 데이터 | MCP 도구 | 파일 폴백 |
|--------|----------|-----------|
| 세션 상태 | `create_session` / `get_session` | `project.state.json` |
| 이벤트 기록 | `save_event` | `.samvil/events.jsonl` (append) |
| 메트릭 | 없음 | `.samvil/metrics.json` (overwrite) |
| Seed 버전 | `save_seed_version` | `.samvil/seed-history/<version>.json` |
| 인터뷰 상태 | `score_ambiguity` | 인라인 계산 (threshold만 사용) |

**이벤트 파일 기록 형식:**
```
# .samvil/events.jsonl (한 줄에 하나의 JSON)
{"event_type":"stage_start","stage":"interview","data":{},"timestamp":"2024-01-01T00:00:00Z"}
{"event_type":"stage_end","stage":"interview","data":{"questions_asked":5},"timestamp":"2024-01-01T00:05:00Z"}
```

**MCP 건강 로깅** — MCP 호출 실패 시마다 `.samvil/mcp-health.jsonl`에 기록:
```
{"status":"fail","tool":"save_event","error":"connection refused","timestamp":"..."}
{"status":"fail","tool":"create_session","error":"timeout","timestamp":"..."}
```

Retro에서 `.samvil/mcp-health.jsonl`을 읽어 MCP 성공률 집계:
```
[SAMVIL] MCP 건강 리포트:
  총 호출: 18회
  성공: 15회 (83%)
  실패: 3회 (17%)
  실패 도구: save_event(2), create_session(1)
```

## MCP 복구

체인 실행 중 MCP가 복구되면 자동으로 전환:
1. MCP 호출이 다시 성공하면 파일 기반 로깅과 병행
2. 파일에 기록된 이벤트를 MCP에 백필하지 않음 (중복 방지)
3. 이후 이벤트는 Dual-Write 패턴 유지
