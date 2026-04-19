# Migration Guide: SAMVIL v2.x → v3.0

> v3.0.0 introduces the **AC Tree** — acceptance criteria are now tree nodes, and Build/QA iterate leaves instead of flat lists. This guide shows how to migrate an existing v2 project without manual edits.

## TL;DR

```bash
# Inside the project directory that has project.seed.json
/samvil:update --migrate
```

- Converts `features[].acceptance_criteria` to v3 tree nodes.
- Sets `schema_version: "3.0"`.
- Writes `project.v2.backup.json` next to your seed **only when an actual
  migration happens**. Re-running on a seed that's already v3 is a true
  no-op (no backup, no rewrite).
- Existing backup files are never overwritten — safe to re-run.

## What actually changes

### v2 flat AC

```json
{
  "features": [
    {
      "name": "auth",
      "acceptance_criteria": [
        "User can sign up",
        "User can log in"
      ]
    }
  ]
}
```

### v3 tree AC

```json
{
  "schema_version": "3.0",
  "features": [
    {
      "name": "auth",
      "acceptance_criteria": [
        {
          "id": "AC-auth-1",
          "description": "User can sign up",
          "children": [],
          "status": "pending",
          "evidence": []
        },
        {
          "id": "AC-auth-2",
          "description": "User can log in",
          "children": [],
          "status": "pending",
          "evidence": []
        }
      ]
    }
  ]
}
```

- Strings become single leaves.
- Existing `{"id", "description"}` dicts gain `children`, `status`, `evidence`.
- Legacy `{"criterion", "vague_words"}` dicts map to `{"id", "description", "vague_words"}`.

## Step-by-step

1. **Pull v3**:
   ```
   /samvil:update
   ```
2. **Migrate** (in the project directory):
   ```
   /samvil:update --migrate
   ```
   or invoke the MCP tool directly:
   ```
   mcp__samvil_mcp__migrate_seed_file(seed_path="<cwd>/project.seed.json")
   ```
3. Verify:
   ```bash
   jq '.schema_version' project.seed.json
   # "3.0"
   ```

## Rollback

If something breaks in the v3 run, restore the backup:
```bash
cp project.v2.backup.json project.seed.json
```
Then pin your plugin to the last v2 tag (`git checkout v2.7.0` in the plugin cache or roll back via `gh`).

## Manual tree decomposition (optional)

`migrate_seed_file` produces a **flat** tree — one leaf per original AC. If you want to exploit v3's recursive decomposition (up to depth 3), edit the migrated seed and add `children[]` to any leaf:

```json
{
  "id": "AC-auth-1",
  "description": "User can sign up",
  "children": [
    {"id": "AC-auth-1.1", "description": "Email format is validated client-side", "children": []},
    {"id": "AC-auth-1.2", "description": "Submit creates a record in Supabase", "children": []},
    {"id": "AC-auth-1.3", "description": "Success navigates to /onboarding", "children": []}
  ]
}
```

Depth > 3 is rejected by the tree loader to keep the HUD readable.

## Build/QA behavior after migration

- **Build** runs `next_buildable_leaves` with `MAX_PARALLEL` and spawns one Agent per leaf. Branch nodes never get workers.
- **QA** Pass 2 iterates leaves and marks status; branch verdicts come from `aggregate_status`.
- **`tree_progress`** drives the HUD: `total_leaves`, `passed`, `failed`, `progress_pct`, `all_done`.
- **Rate budget** is cooperative via `.samvil/rate-budget.jsonl` and bounded by the same `MAX_PARALLEL`.

## Known gaps

- Migration only adds structure; it does **not** split ambiguous ACs ("Validate email and hash password") into children. Use `suggest_ac_decomposition` or the Council to split manually.
- `vague_words` tagging from v2 carries over but is no longer auto-surfaced in Pass 2.5 — we'll revisit this in a future release.

## Troubleshooting

- **`Cycle detected among ACs`** when running dependency analysis: two ACs list each other in `depends_on`. Remove one.
- **Backup already exists**: safe — the migrator does not overwrite an existing `.v2.backup.json`.
- **Still see v2 behavior**: confirm `schema_version` is present at the root of the seed. If not, re-run `mcp__samvil_mcp__migrate_seed_file`.
