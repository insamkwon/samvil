# SAMVIL Evolve Stage (Codex CLI)

## Auto-Proceed Policy

This stage is **mechanical** when convergence succeeds on the first attempt.
Pause and ask the user ONLY when:

- Convergence fails after 2 full cycles (circuit breaker).
- QA regressions are detected (evolved seed scores lower than current seed).
- The user has explicitly asked to review the evolved seed before saving.

In all other cases, complete the stage and **immediately proceed** to
`samvil-retro` without asking for confirmation — the user has already
approved the pipeline continuation by starting it.

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-evolve`, skip this stage.
Ensure `.samvil/project.seed.json` exists and QA/deploy is complete.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for current seed.
3. Read `.samvil/qa-results.json` for QA findings and failures.
4. **Wonder phase**: Analyze what went wrong and what could improve:
   - Which ACs failed and why
   - What design assumptions were wrong
   - What edge cases were missed
5. **Reflect phase**: Propose concrete seed improvements:
   - New or refined ACs
   - Better constraints
   - Clarified requirements
6. Run MCP tool `compare_seeds(seed_a=<current>, seed_b=<evolved>)` to measure similarity.
7. If `similarity >= 0.95` and no regressions, convergence achieved.
8. Run MCP tool `check_convergence_gates(eval_result_json=<json>, history_json=<json>)` for 5-gate check.
9. Save evolved seed to `.samvil/project.seed.json`.
10. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-evolve")`.

## Chain

After completing: **immediately proceed to execute the `samvil-retro` stage**
without waiting for user input (see Auto-Proceed Policy above).
Do not print "next stage is retro" and stop — continue executing retro
in the same session unless a circuit-breaker or regression halts the chain.
