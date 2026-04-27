# SAMVIL Seed Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-seed`, skip this stage.
Ensure `.samvil/interview-summary.md` exists.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/interview-summary.md` for interview results.
3. Construct seed JSON from interview answers:
   - Map features from interview responses
   - Build AC tree with leaf-level acceptance criteria
   - Set solution_type, tech_stack, constraints
4. Run MCP tool `validate_seed(seed_json=<json>)` to validate seed structure.
5. If validation fails, fix errors and re-validate.
6. Save validated seed to `.samvil/project.seed.json`.
7. Run MCP tool `save_seed_version(session_id=<id>, version=1, seed_json=<json>)` to record seed history.
8. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-seed")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-council).
Tell the user the next command to run.
