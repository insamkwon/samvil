# SAMVIL Pipeline Orchestrator (Codex CLI)

## Boot

1. Run MCP tool `health_check()` — log the result (version, MCP tool count).
2. Run MCP tool `get_health_tier_summary(project_root="${PWD}")` — report
   Healthy / Degraded / Critical. Degraded MCP is non-fatal; continue.
3. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
   - Marker exists → read `next_skill` and jump directly to that stage file.
   - No marker → fresh start; continue to step 4.
4. Run MCP tool `aggregate_orchestrator_state(project_root="${PWD}",
   prompt="<user's one-line idea>", host_name="codex_cli")`.
   - Captures: `tier.samvil_tier`, `solution_type.solution_type`,
     `brownfield.is_brownfield`, `chain.next_skill`.
   - On MCP error: default to `samvil_tier="standard"`, ask user for
     `solution_type` manually (web/automation/game/mobile/dashboard).
5. **Tier selection** — if `tier.source == "default"` (user didn't pass `--tier`):
   Ask: "어떤 수준으로 만들까요? minimal / standard / thorough / full"
   Persist chosen tier to `.samvil/project.config.json` field `samvil_tier`.
6. **Mode** — if `brownfield.is_brownfield` is true: jump to
   `samvil-analyze.md`. Otherwise proceed as greenfield.
7. Run MCP tool `write_chain_marker(project_root="${PWD}",
   host_name="codex_cli", current_skill="samvil")`.
8. Initialize `.samvil/` if needed:
   `mkdir -p .samvil` and create default `project.state.json`:
   `{"current_stage":"interview","completed_stages":[],"samvil_tier":"<chosen>"}`.
9. Print:
   ```
   [SAMVIL] Starting pipeline for: "<prompt>"
   [SAMVIL] Tier: <samvil_tier>  solution_type: <type>
   [SAMVIL] Next: samvil-interview
   ```

## Chain

After this stage, proceed to the instruction file for `samvil-interview`.
The path is listed in the AGENTS.md skill table under "Interview".
