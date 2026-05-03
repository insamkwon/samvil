# SAMVIL Resume (Codex CLI)

Resume an interrupted SAMVIL session without re-running the interview.
Reads `project.state.json` (or `.samvil/state.json`) to determine the
last in-progress stage, then chains to the appropriate stage command.

## Boot

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
   If a file marker exists (`has_marker: true`), use `next_skill` from the
   marker directly and skip to step 4 — the chain already knows where to go.
2. Run MCP tool `resume_session(project_root="${PWD}")`.
   Returns: `found`, `last_stage`, `stage_progress`, `next_skill`,
   `minutes_since`, `handoff_excerpt`, `completed_features`, `failed_acs`,
   `samvil_tier`, `project_name`.
3. If `found == false`:
   ```
   [SAMVIL-RESUME] No resumable session found.
   [SAMVIL-RESUME] Starting fresh with samvil-interview.
   ```
   Proceed to `samvil-interview.md` and stop here.
4. If `found == true`, print summary:
   ```
   [SAMVIL-RESUME] Session found
     Project   : <project_name or "(unnamed)">
     Tier      : <samvil_tier>
     Last stage: <last_stage>  (<stage_progress>)
     Elapsed   : <minutes_since>m ago
   ```
   If `handoff_excerpt` is non-empty, print:
   ```
   --- Last handoff note ---
   <handoff_excerpt>
   ---
   ```
   If `failed_acs` is non-empty, list up to 5:
   ```
   Warning: prior failed ACs: <list>
   ```
5. Run MCP tool `write_chain_marker(project_root="${PWD}",
   host_name="codex_cli", current_skill="samvil-resume")`.
   This writes `.samvil/next-skill.json` pointing to `<next_skill>`.
6. Print:
   ```
   [SAMVIL-RESUME] Resuming at: <next_skill>
   ```

## Chain

Proceed to the instruction file for `<next_skill>` from the skills table in
`references/codex-commands/`. On MCP error, default to `samvil-build.md`
for build stage or `samvil-interview.md` for unknown stage.
