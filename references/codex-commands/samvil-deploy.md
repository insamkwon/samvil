# SAMVIL Deploy Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-deploy`, skip this stage.
Ensure QA has passed (all AC leaves PASS with evidence).

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for deployment configuration.
3. Read `.samvil/qa-results.json` to confirm all ACs passed.
4. Check for `.env.example` and verify required environment variables.
5. Prepare deployment:
   - Vercel: `vercel --prod` (if vercel CLI installed)
   - Railway: `railway up` (if railway CLI installed)
   - Coolify: manual deploy instructions
   - Manual: provide build artifact instructions
6. Run MCP tool `evaluate_deploy_target(project_root="${PWD}")` to assess options.
7. Ask user which deploy target to use. Do not deploy without explicit confirmation.
8. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-deploy")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-evolve).
Tell the user the next command to run.
