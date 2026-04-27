# SAMVIL Interview Stage (Codex CLI)

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-interview`, skip this stage.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `project.seed.json` if it exists for context.
3. Conduct a Socratic interview to clarify requirements:
   - What problem does this solve?
   - Who are the users?
   - What are the core features?
   - What constraints exist?
4. Save interview results to `.samvil/interview-summary.md`.
5. Run MCP tool `score_ambiguity(interview_state=<json>, tier="standard")`.
6. If `ambiguity_score > 0.05`, ask more questions. Repeat until threshold met.
7. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-interview")`.

## Chain

After completing: read `.samvil/next-skill.json` for the next stage.
Tell the user the next command to run.
