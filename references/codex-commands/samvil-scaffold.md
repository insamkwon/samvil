# SAMVIL Scaffold Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-scaffold`, skip this stage.
Ensure root `project.seed.json` and `project.blueprint.json` exist.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read root `project.seed.json` for tech stack configuration.
3. Read root `project.blueprint.json` for folder structure.
4. Create project skeleton using CLI commands:
   - Initialize with appropriate framework CLI (create-next-app, npm create vite, etc.)
   - Install dependencies (shadcn/ui, Tailwind, TypeScript)
   - Set up folder structure per blueprint
   - Create base layout and routing
5. Run `npm run build` to verify scaffold compiles.
6. For browser solution types (`web-app`, `dashboard`, `game`, `mobile-app`), run MCP tool
   `scaffold_test_harness(project_root="${PWD}", base_url="http://localhost:4173", base_path="/")`.
   The tool detects Expo/mobile dependencies, switches to `http://localhost:8081`, and
   wires Playwright plus the Expo web server; harness generation errors halt scaffold QA.
7. Save the successful result to `.samvil/scaffold-results.json` as a non-empty JSON object with `all_passed=true`.
8. Read `<sid>` from root `project.state.json`, then run MCP tool `complete_stage(session_id=<sid>, stage="scaffold", verdict="pass")`; any error halts.
9. Only after completion succeeds, run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-scaffold")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-build).
Tell the user the next command to run.
