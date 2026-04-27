# SAMVIL Update Stage (Codex CLI)

## Prerequisites

This is a standalone stage — no chain marker required.
Git must be available for pulling updates.

## Execution

1. Determine current SAMVIL version from `plugin.json`.
2. Check for updates on the remote repository:
   - `git fetch origin main`
   - Compare local vs remote HEAD
3. If update available:
   - Pull latest changes from `origin main`
   - Sync plugin cache
   - Re-register MCP server
4. If `--migrate` flag provided:
   - Detect seed schema version
   - Run MCP tool `migrate_seed_file(seed_path=<path>)` for v2→v3 migration
   - Create `.v2.backup.json` automatically
5. Run MCP tool `health_check()` to verify post-update health.
6. Report: old version → new version, any migration actions taken.

## Chain

Standalone stage — no chain continuation.
Present update results to the user.
