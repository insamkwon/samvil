# Regression Suite Reference (Option B)

SAMVIL tracks passing ACs across evolve cycles using generation snapshots.
Each snapshot captures which ACs passed (with evidence) at a point in time.
The next cycle validates against the previous snapshot to detect regressions.

## Storage Layout

```
.samvil/
  generations/
    gen-1/
      snapshot.json   ← ACEntry list for cycle 1
    gen-2/
      snapshot.json   ← ACEntry list for cycle 2
```

## Snapshot Schema (`snapshot.json`)

```json
{
  "schema_version": "1.0",
  "generation_id": "gen-1",
  "created_at": "2026-04-27T12:00:00Z",
  "passing_ac_count": 15,
  "total_ac_count": 20,
  "acs": [
    {
      "id": "AC-1",
      "criterion": "User can create a task",
      "verdict": "PASS",
      "evidence": ["app/page.tsx:45"]
    }
  ]
}
```

## Input Source

Reads `.samvil/qa-results.json` → `pass2` array (from QA synthesis).
Each entry: `{ "id", "criterion", "verdict", "evidence" }`.
Missing file → empty snapshot (P8 graceful degradation).

## MCP Tools

| Tool | Purpose |
|---|---|
| `snapshot_generation(project_root, generation_id?)` | Capture current passing ACs |
| `validate_against_snapshot(project_root, snapshot_id)` | Check for regressions |
| `aggregate_regression_state(project_root)` | Overview of all generations |
| `compare_generations(project_root, gen_a, gen_b)` | Diff two snapshots |

## Evolve Integration

Called automatically from `samvil-evolve`:
- **Pre-Wonder** (Boot step 4b): snapshot current state, validate against prior gen
- **Post-apply** (end of cycle): snapshot the new generation

## Seed v3 Compatibility

Regression suite reads from `qa-results.json` (not seed.json directly).
No seed schema changes required. Compatible with v3.0+.
