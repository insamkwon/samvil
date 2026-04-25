# Orchestrator Schema (v3.3+)

The orchestrator is SAMVIL's stage-control layer. It lets skills ask:

- what stage comes next?
- should this stage be skipped for this tier?
- can this session proceed to a target stage?
- how should a completed stage be recorded?

It is intentionally derived from existing state:

- `sessions.current_stage` in the MCP event store
- event rows from the MCP event store
- `.samvil/claims.jsonl` for claim output from mutating operations

No new orchestration state file is introduced.

## Stage Order

```text
interview
seed
council
design
scaffold
build
qa
deploy
retro
evolve
complete
```

## Tier Skip Policy

Phase 1 uses a conservative skip policy:

| Stage | minimal | standard | thorough | full |
|---|---:|---:|---:|---:|
| `council` | skip | run | run | run |
| `deploy` | skip | skip | skip | skip |

`deploy` remains skipped until a later host/project capability layer can prove
that deployment is configured and reversible enough to run automatically.

## Event-Derived Status

The orchestrator reduces event rows into per-stage status:

| Event examples | Stage status |
|---|---|
| `interview_complete` | `interview=complete` |
| `seed_generated`, `pm_seed_complete` | `seed=complete` |
| `council_complete`, `council_verdict` | `council=complete` |
| `design_complete`, `blueprint_generated` | `design=complete` |
| `scaffold_complete` | `scaffold=complete` |
| `build_pass`, `build_stage_complete` | `build=complete` |
| `build_fail` | `build=failed` |
| `qa_pass` | `qa=complete` |
| `qa_fail`, `qa_blocked`, `qa_unimplemented` | `qa=failed` |
| `deploy_complete` | `deploy=complete` |
| `retro_complete` | `retro=complete` |
| `evolve_converge` | `evolve=complete` |

Later successful events override earlier failed events for the same stage. This
matches repair flows where a failed build is fixed and then passes.

## Proceed Rule

`stage_can_proceed(session_id, target_stage)` returns `can_proceed=true` only
when every prior non-skipped stage is complete.

Blocked examples:

- prior stage has no successful exit event
- prior stage has a latest `failed` status
- target stage itself is skipped by tier
- target stage is unknown

Skipped stages do not block. For example, `minimal` can proceed from `seed` to
`design` without running `council`.

## Complete Stage Rule

`complete_stage(session_id, stage, verdict)` is the only mutating orchestrator
tool. It writes:

1. one event row in the MCP event store
2. one `gate_verdict` claim in `.samvil/claims.jsonl` when the project path can
   be resolved

Verdict mapping:

| Verdict | Event | Next stage |
|---|---|---|
| `pass` | stage-specific success event | next non-skipped stage |
| `complete` | stage-specific success event | next non-skipped stage |
| `fail` | stage-specific failure event | none |
| `blocked` | stage-specific blocked event | none |

## MCP Tools

- `get_next_stage(current, samvil_tier)`
- `should_skip_stage(stage, samvil_tier)`
- `stage_can_proceed(session_id, target_stage)`
- `complete_stage(session_id, stage, verdict)`
- `get_orchestration_state(session_id)`

The `get_*` tools are read-only. `complete_stage` is the only mutating tool.

## Failure Behavior

If a session cannot be found, wrappers return structured JSON errors rather than
raising through MCP transport. If the project path cannot be resolved,
`complete_stage` still records the event and returns `claim_id=null`.
