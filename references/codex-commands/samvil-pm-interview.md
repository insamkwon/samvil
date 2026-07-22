# SAMVIL PM Interview Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-pm-interview`, skip this stage.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `project.seed.json` if it exists for context.
3. Conduct a PM-focused interview covering:
   - Product vision and target users
   - Key metrics for success
   - Epics and user stories
   - Task breakdown and prioritization
4. Save interview results to root `interview-summary.md`.
5. Run MCP tool `validate_pm_seed(pm_seed_json=<json>)` to validate PM seed structure.
6. Run MCP tool `pm_seed_to_eng_seed(pm_seed_json=<json>)` to convert to engineering seed.
7. Default: run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-pm-interview", next_skill="samvil-design")`.
   Only when the user supplied exact `--council` on standard/thorough/full/deep, use `next_skill="samvil-council"` instead.

## Chain

After completing: read `.samvil/next-skill.json`; default next stage is `samvil-design`, while explicit `--council` on standard+ routes to `samvil-council`.
Tell the user the next command to run.
