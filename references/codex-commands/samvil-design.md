# SAMVIL Design Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-design`, skip this stage.
Ensure root `project.seed.json` exists; Council output is optional and only present after exact opt-in.
Read `project.config.json`; set `council_opt_in` from exact `"--council"` membership in `flags`.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read root `project.seed.json` for the full seed.
3. If `.samvil/council-results.md` exists from exact Council opt-in, read it; otherwise continue without Council feedback.
4. Run MCP tools `get_orchestration_state(session_id=<sid>, council_opt_in=<flags contains --council>)` and `stage_can_proceed(session_id=<sid>, target_stage="design", council_opt_in=<flags contains --council>)`; any blocker halts.
5. Generate blueprint covering:
   - Folder structure (components, pages, lib, hooks)
   - Data model (types, schemas, API contracts)
   - Component hierarchy (page → layout → component tree)
   - State management approach
   - API routes and endpoints
6. Run `gate_check(gate_name="design_to_scaffold", samvil_tier=<selected tier>, metrics_json='{"blueprint_valid":true,"stack_matrix_match":true}')`; any non-`pass` verdict halts.
7. Save blueprint to root `project.blueprint.json`.
8. Run MCP tool `complete_stage(session_id=<sid>, stage="design", verdict="pass", council_opt_in=<flags contains --council>)`.
9. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-design")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-scaffold).
Tell the user the next command to run.
