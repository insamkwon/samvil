# SAMVIL Council Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-council`, skip this stage.
Ensure `.samvil/project.seed.json` exists.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for the full seed.
3. **Round 1 — Research**: Analyze the seed for:
   - Technical feasibility (stack, dependencies, complexity)
   - Scope realism (feature count, AC coverage)
   - Risk identification (security, performance, UX)
4. **Round 2 — Review**: Based on research findings:
   - APPROVE or request changes for each area
   - Provide specific, actionable feedback
   - Flag any deal-breaker issues
5. Save council results to `.samvil/council-results.md`.
6. If council rejects, report issues to user for revision.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-council")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage (samvil-design).
Tell the user the next command to run.
