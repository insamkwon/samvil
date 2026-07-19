# SAMVIL Design Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-design`, skip this stage.
Ensure root `project.seed.json` exists; Council output is optional and only present after exact opt-in.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read root `project.seed.json` for the full seed.
3. If `.samvil/council-results.md` exists from exact Council opt-in, read it; otherwise continue without Council feedback.
4. Generate blueprint covering:
   - Folder structure (components, pages, lib, hooks)
   - Data model (types, schemas, API contracts)
   - Component hierarchy (page → layout → component tree)
   - State management approach
   - API routes and endpoints
5. Run `gate_check(gate_name="design_to_scaffold", samvil_tier=<selected tier>, metrics_json='{"blueprint_valid":true,"stack_matrix_match":true}')`; any non-`pass` verdict halts.
6. Save blueprint to root `project.blueprint.json`.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-design")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-scaffold).
Tell the user the next command to run.
