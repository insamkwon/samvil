# SAMVIL QA Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-qa`, skip this stage.
Ensure build passes (`npm run build` succeeds).

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
2. Read `project.seed.json` for AC tree and acceptance criteria.
3. **Pass 1 — Mechanical**: Resolve the project test command with `resolve_mechanical_command(project_root=".", field="test", fallback="npm test")`, convert it to an argv JSON array without shell operators, and call `run_stage_verification(project_root=".", run_id=<run_id>, stage="samvil-qa", command_json=<argv JSON>)`. A non-`passed` result halts. Run any additional build, lint, and typecheck checks and record them separately.
4. **Pass 2 — Semantic**: For each AC leaf, verify implementation matches description.
   Use `grep`/`Read` to find file:line evidence. No evidence = FAIL.
5. **Pass 3 — Quality**: Check responsive design, accessibility basics, code structure.
6. Run MCP tool `build_checklist(ac_id=<id>, ac_description=<desc>, items_json=[...])` for each AC.
7. Call `finalize_qa_verdict(project_path=".", evidence_json=<passes 1-3>, pending_ac_claims_json=<pending claims or "[]">)` and read `finalize.next_skill_decision.suggested` (`samvil-qa`, `samvil-deploy`, `samvil-evolve`, or `samvil-retro`). This is a preview/finalizer response only; do not chain from it until synthesis is materialized.
8. Call `materialize_qa_synthesis(project_root=".", synthesis_json=<finalize.synthesis>)` to persist `qa-results.json`, `qa-report.md`, `events.jsonl`, and `project.state.json`.
9. Run the matching `gate_check` before chaining, always with `samvil_tier=<finalize.samvil_tier>` and `project_root="."`:
   - Deploy → `gate_name="qa_to_deploy"`, `metrics_json=<finalize.gate_input.metrics>`, `evidence_mode="mechanical"`.
   - Evolve → `gate_name="qa_to_evolve"`, `metrics_json=<finalize.gate_input.metrics>` (must include `three_pass_pass`, plus `zero_stubs` where required).
   - Retro → `gate_name="any_to_retro"`, `metrics_json='{"always_run":true}'`.
   - QA continue → no cross-stage gate or marker; apply the reported fixes and repeat the Ralph loop.
   Tool error or block halts; no marker is written.
10. Only after materialize + gate PASS, return `requested_next_skill=<finalize.next_skill_decision.suggested>` and the evidence to the native run driver. The driver owns `commit_stage_transition`; this stage instruction must not call `complete_stage` or write a marker directly. For `samvil-qa` continue, return the revision result without requesting a cross-stage commit.

## Chain

After the native driver commits, reread the durable envelope for the selected Deploy/Evolve/Retro route.
