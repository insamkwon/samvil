# SAMVIL Build Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-build`, skip this stage.
Ensure `project.seed.json` exists and scaffold is complete.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
2. Read `project.seed.json` to get features and AC tree.
3. Run MCP tool `next_buildable_leaves(ac_tree_json=<tree>, completed_ids_json=<done>)`.
4. For each leaf, implement the feature:
   - Read the AC description carefully.
   - Write production code (no stubs, no mocks).
   - Each PASS must have file:line evidence.
5. After each leaf, run MCP tool `update_leaf_status(ac_tree_json=<tree>, leaf_id=<id>, status="pass", evidence_json=[...])`.
6. Run `npm run build` to verify build passes.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-build")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-qa).
Tell the user the next command to run.
