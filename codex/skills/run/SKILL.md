---
name: run
description: Start or continue a SAMVIL project from its durable stage envelope.
---

# SAMVIL run

Use this skill for Korean or English requests to start or continue SAMVIL work.
Do not hijack unrelated coding, writing, or analysis requests.

Loop:

1. Call `mcp__samvil_mcp__get_stage_envelope`.
2. When `status=fresh`, read the returned orchestrator instruction completely and
   execute its boot sequence, including `mcp__samvil_mcp__create_session`. Then
   reread the envelope. Never call `begin_stage` with an empty `run_id`.
3. Stop on `waiting_user`, `blocked`, or `complete` and report the exact reason.
4. When `recovery_mode=retry_commit`, do not rerun the stage. Call
   `mcp__samvil_mcp__commit_stage_transition` immediately with the envelope's
   `claim_id`, `transition_id`, `requested_next_skill`, `verdict`, `evidence`,
   run, stage, and revision. Then reread the envelope.
5. Otherwise call `mcp__samvil_mcp__begin_stage` with the returned run, stage,
   and revision.
6. Read the exact absolute catalog instruction path returned by the envelope
   completely and execute the stage.
7. Reread the envelope before committing. Some compatibility instructions call
   `complete_stage`, which already advances through the shared transition
   controller. If the envelope already advanced to another stage or revision,
   do not commit the same stage again; continue from that durable envelope.
8. Only when the envelope still shows the same in-progress claim, commit proven
   evidence with `mcp__samvil_mcp__commit_stage_transition`. Reuse one fixed
   `transition_id` for retries of that exact transition.
9. Continue from the returned receipt/envelope; never infer completion from prose
   and never edit marker or state files directly.

Keep only `run_id`, `stage`, `claim_id`, `expected_revision`, and the exact
`stop_reason` in conversation. After compaction, reread the envelope and files;
conversation history is not recovery evidence.

The public plugin owns the `samvil:` namespace; the frontmatter name remains bare
so unrelated personal skills are not renamed.
