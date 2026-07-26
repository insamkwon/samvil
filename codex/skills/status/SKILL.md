---
name: status
description: Show read-only SAMVIL progress, evidence, and safe next action.
---

# SAMVIL status

Use only the read-only `mcp__samvil_mcp__get_stage_envelope` tool. Never begin or
commit a stage from status. Separate confirmed, recoverable, degraded, blocked,
and unverified information, and report the exact stop reason when present.
