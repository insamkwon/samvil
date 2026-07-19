# SAMVIL QA Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-qa`, skip this stage.
Ensure build passes (`npm run build` succeeds).

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")`.
2. Read `project.seed.json` for AC tree and acceptance criteria.
3. **Pass 1 — Mechanical**: Run `npm run build`, lint, typecheck. Record results.
4. **Pass 2 — Semantic**: For each AC leaf, verify implementation matches description.
   Use `grep`/`Read` to find file:line evidence. No evidence = FAIL.
5. **Pass 3 — Quality**: Check responsive design, accessibility basics, code structure.
6. Run MCP tool `build_checklist(ac_id=<id>, ac_description=<desc>, items_json=[...])` for each AC.
7. Call `finalize_qa_verdict(project_path=".", evidence_json=<passes 1-3>, pending_ac_claims_json=<pending claims or "[]">)` and read `finalize.next_skill_decision.suggested` (`samvil-deploy`, `samvil-evolve`, or `samvil-retro`).
8. Run the matching `gate_check` before chaining, always with `samvil_tier=<finalize.samvil_tier>` and `project_root="."`:
   - Deploy → `gate_name="qa_to_deploy"`, `metrics_json=<finalize.gate_input.metrics>`, `evidence_mode="mechanical"`.
   - Evolve → `gate_name="qa_to_evolve"`, `metrics_json=<finalize.gate_input.metrics>` (must include `three_pass_pass`, plus `zero_stubs` where required).
   - Retro → `gate_name="any_to_retro"`, `metrics_json='{"always_run":true}'`.
   Tool error or block halts; no marker is written.
9. Only after gate PASS, run `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-qa", next_skill="<finalize.next_skill_decision.suggested>")`.

## Chain

After completing: read `.samvil/next-skill.json` for the dynamic Deploy/Evolve/Retro route.
Tell the user the next command to run.
