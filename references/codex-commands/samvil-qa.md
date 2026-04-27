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
7. Aggregate results. If all PASS, proceed. If any FAIL, report to user.
8. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-qa")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-deploy).
Tell the user the next command to run.
