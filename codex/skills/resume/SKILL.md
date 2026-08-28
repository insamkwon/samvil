---
name: resume
description: Reconcile and safely resume an interrupted SAMVIL stage.
---

# SAMVIL resume

Read the durable stage envelope first. Re-run the same stage when completion is
not proven, and use begin/commit MCP tools for every mutation. A corrupt marker,
ambiguous state, missing QA evidence, or user checkpoint is a stop condition.

Use `mcp__samvil_mcp__get_stage_envelope`,
`mcp__samvil_mcp__begin_stage`, and
`mcp__samvil_mcp__commit_stage_transition` only through the shared controller.

Bounded handoff fields are `run_id`, `stage`, `claim_id`, `expected_revision`,
and `stop_reason`; reread everything else after re-entry or context compaction.
