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
4. Save interview results to `.samvil/interview-summary.md`.
5. Run MCP tool `validate_pm_seed(pm_seed_json=<json>)` to validate PM seed structure.
6. Run MCP tool `pm_seed_to_eng_seed(pm_seed_json=<json>)` to convert to engineering seed.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-pm-interview")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-seed).
Tell the user the next command to run.
