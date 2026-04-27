# SAMVIL Pipeline Orchestrator (Codex CLI)

## Boot

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
2. If marker exists, read `next_skill` and proceed to that stage.
3. If no marker, this is a fresh start. Ask the user what they want to build.
4. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil")`.
5. The marker's `next_skill` field tells you which command to run next.
6. Tell the user: "Pipeline started. Next step: interview. Run `samvil samvil-interview` or say continue."

## Chain

After completing this stage, the pipeline continues via the chain marker.
Read `.samvil/next-skill.json` to find the next stage.
Each command file reads the marker and continues automatically.
