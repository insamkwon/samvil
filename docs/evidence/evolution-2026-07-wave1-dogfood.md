# Wave 1 Dogfood Evidence

- 실행일: 2026-07-18
- 대상: 임시 minimal-tier 프로젝트 + 격리 SQLite DB
- 실행 방식: 실제 MCP `create_session` → `save_event` 2회 → file/reader/retro/projection 조회
- push/deploy: 수행하지 않음

## 결과

```json
{
  "events_file_exists": true,
  "events_file_bytes": 392,
  "event_count": 2,
  "event_stages": ["interview", "interview"],
  "stall_reader_last_event_type": "interview_complete",
  "stall_reader_is_stalled": false,
  "retro_flow_source": "events",
  "retro_actual_sequence": ["interview"],
  "retro_stage_durations_ms": {"interview": 55},
  "projection_found": true,
  "projection_event_count": 2
}
```

## 판정

- 프로젝트 `.samvil/events.jsonl`이 생성되고 392 bytes까지 성장했다.
- stall reader는 canonical 파일의 마지막 이벤트를 `interview_complete`로 읽었다.
- retro는 `source=events`로 flow를 계산하고 55ms stage duration을 산출했다.
- `query_projection`은 동일 2개 이벤트를 SQLite 보조 인덱스에서 조회했다.
