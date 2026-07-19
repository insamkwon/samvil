# SAMVIL Seed Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-seed`, skip this stage.
Ensure `.samvil/interview-summary.md` exists.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/interview-summary.md` and `project.config.json`; derive Council opt-in only from exact `"--council"` membership in `project.config.json.flags`.
3. Construct seed JSON from interview answers:
   - Map features from interview responses
   - Build AC tree with leaf-level acceptance criteria
   - Set solution_type, tech_stack, constraints
4. Run MCP tool `validate_seed(seed_json=<json>)` to validate seed structure.
5. If validation fails, fix errors and re-validate.
6. Save validated seed to root `project.seed.json` (canonical Seed SSOT).
7. Run MCP tool `save_seed_version(session_id=<id>, version=1, seed_json=<json>)` to record seed history.
8. Default: run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-seed", next_skill="samvil-design")`.
   Only when the user supplied exact `--council` on standard/thorough/full/deep, use `next_skill="samvil-council"` instead.

## Chain

After completing: read `.samvil/next-skill.json`; default next stage is `samvil-design`, while explicit `--council` on standard+ routes to `samvil-council`.
Tell the user the next command to run.
