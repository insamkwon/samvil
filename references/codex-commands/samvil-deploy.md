# SAMVIL Deploy Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-deploy`, skip this stage.
Ensure QA has passed (all AC leaves PASS with evidence).

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read root `project.seed.json` for deployment configuration.
3. Read `.samvil/qa-results.json` to confirm all ACs passed.
4. Check for `.env.example` and verify required environment variables.
5. Prepare deployment:
   - Vercel: `vercel --prod` (if vercel CLI installed)
   - Railway: `railway up` (if railway CLI installed)
   - Coolify: manual deploy instructions
   - Manual: provide build artifact instructions
6. Run MCP tool `evaluate_deploy_target(project_root="${PWD}")` to assess options.
7. Inspect `ready` and `qa_gate.verdict`. If `ready=false`, the tool errors, or `qa_gate.verdict!="pass"`, print blockers and halt. Persisted QA PASS is diagnostic only; do not ask for a target, deploy, or write a continuation marker without a trusted runtime receipt.
8. Only when `ready=true`, ask which deploy target to use and require explicit confirmation.
9. After a successful or explicitly skipped deployment, run `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-deploy", next_skill="samvil-retro")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (`samvil-retro`).
Tell the user the next command to run.
