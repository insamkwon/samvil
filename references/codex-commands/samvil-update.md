# SAMVIL Update Stage (Codex CLI)

## Prerequisites

Git must be available for pulling updates.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
2. If marker exists and `next_skill` is not `samvil-update`, report expected stage and stop.
3. Determine current SAMVIL version from `plugin.json`.
4. Check for updates on the remote repository:
   - `git fetch origin main`
   - Compare local vs remote HEAD
5. If update available:
   - Pull latest changes from `origin main`
   - Sync plugin cache
   - Re-register MCP server
6. If `--migrate` flag provided:
   - Detect seed schema version
   - Run MCP tool `migrate_seed_file(seed_path=<path>)` for v2→v3 migration
   - Create `.v2.backup.json` automatically
7. Run MCP tool `health_check()` to verify post-update health.
8. Report: old version → new version, any migration actions taken.
9. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-update")` on completion.

## Chain

Standalone stage — no chain continuation.
Present update results to the user.
