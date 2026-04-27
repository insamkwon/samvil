# SAMVIL Scaffold Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-scaffold`, skip this stage.
Ensure `.samvil/project.seed.json` and `.samvil/blueprint.json` exist.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for tech stack configuration.
3. Read `.samvil/blueprint.json` for folder structure.
4. Create project skeleton using CLI commands:
   - Initialize with appropriate framework CLI (create-next-app, npm create vite, etc.)
   - Install dependencies (shadcn/ui, Tailwind, TypeScript)
   - Set up folder structure per blueprint
   - Create base layout and routing
5. Run `npm run build` to verify scaffold compiles.
6. Save scaffold results to `.samvil/scaffold-results.json`.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-scaffold")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-build).
Tell the user the next command to run.
