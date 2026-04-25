# Host Continuation Marker

SAMVIL hosts without native skill invocation continue through
`.samvil/next-skill.json`.

## Marker Shape

```json
{
  "schema_version": "1.0",
  "chain_via": "file_marker",
  "host": "codex_cli",
  "next_skill": "samvil-design",
  "reason": "minimal tier skips council",
  "from_stage": "seed",
  "created_by": "samvil-seed"
}
```

## Required Fields

| Field | Meaning |
|---|---|
| `schema_version` | Marker schema version. Current value: `1.0` |
| `chain_via` | Must be `file_marker` |
| `next_skill` | Skill directory name under `skills/` |
| `reason` | Human-readable continuation reason |
| `from_stage` | Stage that wrote the marker |

`host` and `created_by` are recommended for diagnostics.

## Host Behavior

Codex/OpenCode/generic hosts should:

1. Read `.samvil/next-skill.json`.
2. Validate required fields and ensure `skills/<next_skill>/SKILL.md` exists.
3. Read that skill file and continue its instructions.
4. Replace the marker after the next stage completes.

Use `scripts/host-continuation-smoke.py <project_root>` to validate a marker.
