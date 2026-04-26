---
name: samvil-update
description: "SAMVIL을 최신 버전으로 업데이트합니다."
---

# samvil-update (ultra-thin)

Update the SAMVIL plugin cache to the latest GitHub release and, if
asked, migrate project seeds in CWD. Plugin-cache mutations are
host-bound (`gh` / `rsync` / `mv`) and stay in this skill body. Seed
migration delegates to MCP. Full historic prose in `SKILL.legacy.md`.

## Modes

| Invocation | Behaviour |
|---|---|
| `/samvil:update` | Plugin cache update (Steps 1–3), then offer seed migration if `./project.seed.json` is pre-v3. |
| `/samvil:update --migrate` | Skip plugin update; migrate `./project.seed.json` v2 → v3 only. |
| `/samvil:update --migrate v3.2` | Skip plugin update; migrate `./project.seed.json` v3.1 → v3.2 (preview, then apply). |

End-users do **not** clone the repo or install git hooks. Contributors
modifying SAMVIL itself follow the README contributor section.

## Step 1 — Detect versions

```bash
CACHE_DIR=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
PLUGIN_JSON="${CACHE_DIR}.claude-plugin/plugin.json"
CURRENT=$(python3 -c "import json; print(json.load(open('${PLUGIN_JSON}'))['version'])" 2>/dev/null \
  || echo "unknown (folder: $(basename "$CACHE_DIR"))")
LATEST=$(gh api repos/insamkwon/samvil/contents/.claude-plugin/plugin.json --jq '.content' 2>/dev/null \
  | base64 -d | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])" 2>/dev/null \
  || echo "unknown")
```

Folder-name fallback (v3-006) prevents a corrupt plugin.json from
masquerading as a known version. `gh` missing → abort with the manual
fallback in Step 4.

## Step 2 — Update + cache hygiene

If `$CURRENT == $LATEST`: print `[SAMVIL] ✓ 이미 최신 버전입니다 (v$CURRENT)` and skip to Step 3.

Otherwise: `gh repo clone insamkwon/samvil` to `/tmp`, `rsync -a` into
`$CACHE_DIR` excluding `.git`, `mcp/.venv`, `node_modules`. If
`mcp/.venv` exists, refresh editable install (`uv pip install -e . --quiet`).
Then rename folder `$CACHE_DIR` → `$LATEST` (rsync keeps the old folder
name) and delete sibling version folders. Exact bash and `du` size
delta in `SKILL.legacy.md` Steps 3 + 5.

**Hard rule**: both `mv` and the cleanup `rm -rf` MUST be guarded by
`[ -n "$LATEST" ]` so an empty `$LATEST` cannot wipe the cache root.
Cleanup loop pattern:

```bash
for dir in "$CACHE_ROOT"/*/; do
  [ "$(basename "$dir")" != "$LATEST" ] && rm -rf "$dir"
done
```

## Step 3 — Project seed migration

Inspect `./project.seed.json` after a plugin update — or as a standalone
`--migrate` invocation. The MCP tools below are pinned by
`mcp/tests/test_update_smoke.py`.

**v2 → v3** (default `--migrate`): if `schema_version` doesn't start
with `3.`, ask via AskUserQuestion (*"v3는 AC Tree 기반입니다. v{X} → v3
로 마이그레이션할까요? [Yes/No/Later]"*). On **Yes**:
```
mcp__samvil_mcp__migrate_seed_file(seed_path=<CWD_SEED>)
```
Idempotent — already-v3 seeds return `already_v3: true` with no rewrite.
On v2 seeds writes `project.seed.v2.backup.json` before mutation.

**v3.1 → v3.2** (`--migrate v3.2`): two-phase. Preview, wait for approval, apply.
```
mcp__samvil_mcp__migrate_plan(project_root=".")
mcp__samvil_mcp__migrate_apply(project_root=".", dry_run=false)
```
Render `seed_changes` / `files_created` / `backups` from the plan.
Apply writes a rollback snapshot at `.samvil/rollback/v3_2_0/manifest.json`.
Manual rollback only until v3.3. Detail in
`references/migration-v3.1-to-v3.2.md`.

Best-effort observability after success:
```
mcp__samvil_mcp__save_event("update_complete", '{"from":"<CURRENT>","to":"<LATEST>"}')
```

One-shot — no automatic chain.

## Step 4 — Failure path

Host-bound failure (no `gh`, network error, rsync failure):
```
[SAMVIL] ✗ 업데이트 실패
  원인: <error>
  수동: gh repo clone insamkwon/samvil /tmp/samvil && rsync -a /tmp/samvil/ <CACHE_DIR> --exclude='.git' --exclude='mcp/.venv'
```

Seed-migration failure: surface the MCP `error` payload, leave the
backup intact, tell the user to retry or restore from
`.v2.backup.json` / `.v3-1.backup.json`.

## Output + Anti-Patterns

Console only — MCP migration tools write seed/backup files; this skill
writes nothing. Statuses: `[SAMVIL] ✓ 업데이트 완료! v{X} → v{Y}` + cleanup
summary / `[SAMVIL] ✓ 이미 최신 버전입니다 (v{X})` / `[SAMVIL] ✓ Seed migrated:
v{X} → v{Y}` + backup path / `[SAMVIL] ✗ 업데이트 실패` + manual recovery hint.

Don't: overwrite `mcp/.venv` (rsync excludes it), touch user project
source, proceed without `gh`, or `rm -rf` cache folders without the
empty-`$LATEST` guard.

## Legacy reference

Full Korean prose, exact bash for every step, contributor notes, and
historic step-by-step breakdown live in `SKILL.legacy.md`.
