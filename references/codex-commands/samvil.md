# SAMVIL Pipeline Orchestrator (Codex CLI)

## Boot

1. Run MCP tool `health_check()` — log the result (version, MCP tool count).
2. Run MCP tool `get_health_tier_summary(project_root="${PWD}")` — report
   Healthy / Degraded / Critical. Degraded MCP is non-fatal; continue.
3. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
   - Marker exists → read `next_skill` and jump directly to that stage file.
   - No marker → fresh start; continue to step 4.
4. Run MCP tool `aggregate_orchestrator_state(project_root="${PWD}",
   prompt="<user's one-line idea>", host_name="codex_cli",
   council_opt_in=<exact --council flag present>)`.
   - Captures: `tier.samvil_tier`, `solution_type.solution_type`,
     `brownfield.is_brownfield`, `is_pm_mode`, `council_opt_in`,
     `chain.next_skill`.
   - Persist an explicit `--council` token in `project.config.json.flags`;
     absent means Council is default-off.
   - On MCP error: default to `samvil_tier="standard"`, ask user for
     `solution_type` manually (web/automation/game/mobile/dashboard).
5. **Tier selection** — if `tier.source == "default"` (user didn't pass `--tier`):
   Ask: "어떤 수준으로 만들까요? minimal / standard / thorough / full / deep"
   Persist chosen tier to root `project.config.json` fields `samvil_tier`
   and `selected_tier`.
6. **Mode** — if `brownfield.is_brownfield` is true: jump to
   `samvil-analyze.md`. PM-mode prompts route to `samvil-pm-interview`;
   default greenfield prompts route to `samvil-interview`.
7. Run MCP tool `write_chain_marker(project_root="${PWD}",
   host_name="codex_cli", current_skill="samvil",
   next_skill="<chain.next_skill>")`.
8. Initialize `.samvil/` if needed:
   `mkdir -p .samvil` and create default `project.state.json`:
   `{"current_stage":"<chain.state_stage>","completed_stages":[],"samvil_tier":"<chosen>"}`.
9. Print:
   ```
   [SAMVIL] Starting pipeline for: "<prompt>"
   [SAMVIL] Tier: <samvil_tier>  solution_type: <type>
   [SAMVIL] Next: <chain.next_skill>
   ```

## Chain

After this stage, proceed to the instruction file for `<chain.next_skill>`.
The valid targets are `samvil-interview`, `samvil-pm-interview`, and
`samvil-analyze`; choose the one returned by step 4 and persisted by step 7.
Their paths are listed in the AGENTS.md skill table.
