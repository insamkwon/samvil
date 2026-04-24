# Migrating a project from SAMVIL v3.1 to v3.2

SAMVIL v3.2 ships a contract-layer harness (Claim ledger, Gate
framework, Role primitive, AC Tree schema) plus model routing,
interview levels, jurisdiction, retro evolution, and performance
budgets. Most v3.1 projects migrate cleanly via
`samvil-update --migrate v3.2`. This doc explains what changes, how to
revert, and how to verify.

## TL;DR

```bash
# 1. Dry-run to see the plan.
python3 -c "from samvil_mcp.migrate_v3_2 import apply_migration;
print(apply_migration('.', dry_run=True).to_dict())"

# 2. Run for real.
python3 -c "from samvil_mcp.migrate_v3_2 import apply_migration;
apply_migration('.', dry_run=False)"

# Or via the skill: /samvil-update --migrate v3.2
```

Backup (`project.v3-1.backup.json`) is written before any mutation.

## What the migration does

1. **`project.seed.json`**
   - `schema_version: "3.2"`.
   - `agent_tier` → `samvil_tier` (same values).
   - Adds `interview_level: "normal"` default.
   - Walks each `features[].acceptance_criteria` tree; on every leaf,
     adds the 12 AI-inferred fields (`description`, `input`, `action`,
     `expected`, `depends_on`, `risk_level`, `model_tier_hint`,
     `likely_files`, `shared_resources`, `parallel_safety`, `status`,
     `evidence`) with sensible defaults and `needs_review: true`. The
     next Design pass re-evaluates them.

2. **`.samvil/claims.jsonl`**
   - Created if missing. The ledger becomes the SSOT for verifiable
     statements (see `references/glossary.md`).
   - v3.1 seed / qa-results fields are still read by skills that
     haven't migrated yet — nothing is deleted. Over time, skills move
     to post `policy_adoption` and `ac_verdict` claims here.

3. **`.samvil/model_profiles.yaml`**
   - Created from `references/model_profiles.defaults.yaml` if absent.
   - Controls ④ routing. Edit to change Opus / Codex / Haiku assignments.

4. **`.samvil/retro/`**
   - `imported-from-v3_1.yaml` holds one observation per v3.1
     `council/*.md` file. Source files are marked read-only. New retros
     (Sprint 5a schema) land next to it.

5. **`.samvil/rollback/v3_2_0/manifest.json`**
   - Snapshot record. Contains the backup path and the exact seed
     changes made. Used by mid-sprint rollback (`samvil-update
     --rollback v3.2`).

## What does NOT change

- Your builds. `npm run build` / equivalents continue to work
  identically. v3.2 adds contract-layer verification **on top of** the
  existing pipeline.
- Your agents' behavior. v3.2 tags each agent with a `model_role`
  frontmatter, but the skills' instructions are unchanged.
- Your Claude Code session. v3.2 does not require a different model.

## Breaking-ish changes

1. **Glossary renames** (see `references/glossary.md`):
   - `agent_tier` → `samvil_tier` in seed files. The MCP tool
     `create_session` accepts the legacy name as a deprecated alias
     through v3.2; removed in v3.3.
   - "evolve gates" → `evolve_checks` in docs/logs. No code change
     needed unless your scripts parse the phrase.

2. **Council Gate A is opt-in.** Running `/samvil` without the new
   `--council` flag skips the legacy Council stage. Consensus still
   runs automatically when ⑨ triggers fire (see
   `references/council-retirement-migration.md`). v3.3 removes
   `--council` entirely.

3. **Seed schema version bumps to `3.2`.** Any tooling that asserts
   `schema_version == "3.0"` will fail until updated.

## Reverting to v3.1

Two paths:

1. **Rollback snapshot** (recommended within a week of migration):
   ```
   /samvil-update --rollback v3.2
   ```
   Restores `project.seed.json` from `project.v3-1.backup.json` and
   deletes the `.samvil/rollback/v3_2_0/` marker.

2. **Manual revert**:
   ```
   mv project.v3-1.backup.json project.seed.json
   rm -rf .samvil/rollback/v3_2_0
   rm -f .samvil/claims.jsonl
   ```
   Preserves other `.samvil/` state, which is still usable under v3.1.

## Verifying the migration

After running the migration:

```bash
# 1. Seed validates under v3.2 rules.
python3 -c "
from samvil_mcp.seed_manager import validate_seed
import json
with open('project.seed.json') as f:
    print(validate_seed(json.dumps(json.load(f))))"

# 2. Claim ledger initialized.
python3 scripts/view-claims.py --format count

# 3. Gate config loads.
python3 scripts/view-gates.py --samvil-tier standard

# 4. Status pane.
python3 scripts/samvil-status.py

# 5. Exit-gate checks per sprint.
python3 scripts/check-exit-gate-sprint1.py
python3 scripts/check-exit-gate-sprint3.py
```

If any of these fail, file a retro observation with
`category: v3_1_migration` and `severity: high`. The `imported-from-
v3_1.yaml` file is the shared context for further investigation.

## FAQ

**Q: Do I need to rerun the interview after migrating?**
A: No. The migration backfills AI-inferred fields with `needs_review:
true`; the next Design pass re-evaluates them without touching your
original `intent` / `verification`.

**Q: Will v3.2 change my model routing automatically?**
A: Not unless `.samvil/model_profiles.yaml` is missing. The migration
copies the defaults so your Sonnet/Opus/Haiku behavior is preserved.
Switch to Codex QA by editing the yaml; see
`references/model-routing-guide.md`.

**Q: My `samvil-council` skill broke.**
A: Run with `--council` for the v3.2 minor window. Migrate to the
dispute-resolver pattern by v3.3; see
`references/council-retirement-migration.md`.

**Q: What happens to `.samvil/council/*.md` and my prior retros?**
A: Council files are marked read-only and imported as observations into
`.samvil/retro/imported-from-v3_1.yaml`. v3.1 retros are unchanged.
