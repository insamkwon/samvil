---
name: run
description: Start or continue a SAMVIL project from its durable stage envelope.
---

# SAMVIL run

Use this skill for Korean or English requests to start or continue SAMVIL work.
Do not hijack unrelated coding, writing, or analysis requests.

Loop:

1. Call `mcp__samvil_mcp__get_stage_envelope`.
2. Stop on `waiting_user`, `blocked`, or `complete` and report the exact reason.
3. Call `mcp__samvil_mcp__begin_stage` with the returned run, stage, and revision.
4. Read the exact catalog instruction path returned by the envelope completely.
5. Execute that stage and commit only proven evidence with
   `mcp__samvil_mcp__commit_stage_transition`.
6. Continue from the returned receipt/envelope; never infer completion from prose
   and never edit marker or state files directly.

The public plugin owns the `samvil:` namespace; the frontmatter name remains bare
so unrelated personal skills are not renamed.
