# SAMVIL Design Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-design`, skip this stage.
Ensure `.samvil/project.seed.json` and `.samvil/council-results.md` exist.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for the full seed.
3. Read `.samvil/council-results.md` for council feedback.
4. Generate blueprint covering:
   - Folder structure (components, pages, lib, hooks)
   - Data model (types, schemas, API contracts)
   - Component hierarchy (page → layout → component tree)
   - State management approach
   - API routes and endpoints
5. Run MCP tool `gate_check(gate_name="build_to_qa", samvil_tier="standard", metrics_json=<json>)` to verify readiness.
6. Save blueprint to `.samvil/blueprint.json`.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-design")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-scaffold).
Tell the user the next command to run.
