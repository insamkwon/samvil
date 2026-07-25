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
6. Run `npm run build > .samvil/build.log 2>&1; build_exit=$?; echo "SAMVIL_EXIT:${build_exit}" >> .samvil/build.log; test "$build_exit" -eq 0` to verify build passes and persist the receipt candidate.
7. Run MCP tool `collect_stage_evidence(project_root=".", stage="build")` and keep the returned artifact evidence for Phase Z diagnostics.
8. Run MCP tool `finalize_build_phase_z(project_path="${PWD}", rate_budget_stats_json=<stats JSON or "">, failed_features_json=<JSON array or "[]">, retries=<total retries>)`.
9. From the Phase Z result, post each `ac_verdict_claims[]` entry with `claim_post(**entry)` and verify `stage_claim_id` with `claim_verify(claim_id=<id>, verified_by="agent:user")` when present.
10. Run MCP tool `gate_check(gate_name="build_to_qa", samvil_tier=<phase_z.samvil_tier>, metrics_json=<phase_z.gate_input.metrics>, project_root=".", evidence_mode="mechanical")`. Any tool error or non-`pass` verdict halts; no marker is written. Current hosts fail closed unless trusted mechanical build evidence exists.
11. Only after gate PASS, read `<sid>` from root `project.state.json` and run MCP tool `complete_stage(session_id=<sid>, stage="build", verdict="pass")`; any error halts.
12. Only after completion succeeds, run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-build")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-qa).
Tell the user the next command to run.
