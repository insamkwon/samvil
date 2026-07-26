# Host Continuation and Recovery

SAMVIL v4.33 uses `.samvil/next-skill.json` as durable recovery state. A native
Codex task drives stages through `get_stage_envelope`, `begin_stage`, and
`commit_stage_transition`; the marker records the controller result but is never
itself authority to commit a transition.

Legacy OpenCode/Gemini hosts may still consume the v1.0 file marker. Structural
compatibility is not machine-runtime parity, and every evidence report must keep
those classifications separate.

## Native host-driver marker (v1.1)

```json
{
  "schema_version": "1.1",
  "chain_via": "host_driver",
  "host": "codex_cli",
  "run_id": "run-123",
  "revision": 7,
  "status": "ready",
  "from_stage": "samvil-build",
  "next_skill": "samvil-qa",
  "reason": "build completed"
}
```

`run_id`, monotonic `revision`, and `status` bind recovery to one run. An
`in_progress` marker is owned by the transition controller; the legacy writer
must not replace it. Replaying a completed stage may preserve the existing v1.1
marker, but cannot mint a second transition.

## Legacy file marker (v1.0)

```json
{
  "schema_version": "1.0",
  "chain_via": "file_marker",
  "host": "codex_cli",
  "next_skill": "samvil-design",
  "reason": "council is default-off",
  "from_stage": "seed",
  "created_by": "samvil-seed"
}
```

## Legacy required fields

| Field | Meaning |
|---|---|
| `schema_version` | Marker schema version. Current value: `1.0` |
| `chain_via` | Must be `file_marker` |
| `next_skill` | Skill directory name under `skills/` |
| `reason` | Human-readable continuation reason |
| `from_stage` | Stage that wrote the marker |

`host` and `created_by` are recommended for diagnostics.

## Native Codex behavior

1. Read `get_stage_envelope`.
2. For `fresh`, run the orchestrator and create a session before beginning a stage.
3. Begin only the returned run/stage/revision claim.
4. Execute the exact absolute catalog instruction path.
5. Reread the envelope; compatibility instructions may already have advanced it.
6. If still in the same claim, retry `commit_stage_transition` with one fixed
   `transition_id` until its receipt is returned.
7. Stop only at `waiting_user`, `blocked`, or `complete`.

Conversation text is not recovery evidence. After restart or compaction, reread
the envelope and SSOT files.

## Legacy host behavior

Codex/OpenCode/generic hosts should:

1. Read `.samvil/next-skill.json`.
2. Validate required fields and ensure `skills/<next_skill>/SKILL.md` exists.
3. Read that skill file and continue its instructions.
4. Replace the marker after the next stage completes.

Use `scripts/host-continuation-smoke.py <project_root>` for legacy marker
validation. Native readiness is checked with
`python3 scripts/codex-native-e2e.py --check`.
