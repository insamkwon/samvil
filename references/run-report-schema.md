# Run Report Schema

`.samvil/run-report.json` is a generated telemetry snapshot for one SAMVIL
project run. It is deterministic and file-only; no LLM call is required.

## Shape

```json
{
  "schema_version": "1.0",
  "project_root": "/path/to/project",
  "generated_at": "2026-04-26T12:00:00Z",
  "state": {
    "session_id": "abc123",
    "project_name": "todo-app",
    "current_stage": "design",
    "samvil_tier": "minimal",
    "seed_version": 1
  },
  "events": {
    "total": 3,
    "by_type": { "seed_generated": 1 },
    "by_stage": { "design": 1 },
    "failure_count": 0,
    "latest_event_at": "2026-04-26T12:00:00Z"
  },
  "timeline": {
    "category_counts": {
      "start": 1,
      "complete": 1
    },
    "failure_count": 0,
    "retry_count": 0,
    "stages": [
      {
        "stage": "seed",
        "status": "complete",
        "event_count": 2,
        "start_at": "2026-04-26T12:00:00Z",
        "end_at": "2026-04-26T12:01:00Z",
        "duration_seconds": 60.0,
        "categories": {
          "start": 1,
          "complete": 1
        }
      }
    ]
  },
  "claims": {
    "total": 2,
    "by_status": { "pending": 0, "verified": 0, "rejected": 0 },
    "by_type": { "gate_verdict": 2 },
    "pending_subjects": [],
    "latest_gate_verdicts": []
  },
  "mcp_health": {
    "total": 1,
    "failures": 0,
    "oks_sampled": 1,
    "failures_by_tool": {},
    "latest_failure": {}
  },
  "continuation": {
    "present": true,
    "next_skill": "samvil-design",
    "from_stage": "seed",
    "reason": "minimal tier skips council",
    "chain_via": "file_marker"
  },
  "next_action": "continue with samvil-design"
}
```

## MCP Tools

- `build_run_report(project_root, persist=true, mcp_health_path?)`
- `read_run_report(project_root)`
- `render_run_report(project_root, refresh=false)`

## Notes

- Claims are collapsed to current state by `claim_id`.
- Gate verdicts are extracted from `gate_verdict` claims.
- MCP health defaults to project-local `.samvil/mcp-health.jsonl`; callers can
  pass another path when they need to summarize the host-level health log.
- Continuation is read from `.samvil/next-skill.json`.

## Event Categories

Phase 3 classifies event types into `start`, `complete`, `fail`, `retry`,
`blocked`, `skip`, or `other`.

- `*_started`, `*_start` → `start`
- `*_complete`, `*_pass`, `seed_generated`, `blueprint_generated` →
  `complete`
- `*_fail`, `*_error`, `qa_revise`, `qa_unimplemented` → `fail`
- `fix_applied`, `*retry*`, `*reawake*` → `retry`
- `qa_blocked`, `*stall*` → `blocked`
- `*skip*` → `skip`

Durations are computed per stage when timestamps exist.
