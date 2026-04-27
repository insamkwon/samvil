# SAMVIL Analyze Stage (Codex CLI)

## Prerequisites

Point at an existing project directory.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to check for resume.
2. If marker exists and `next_skill` is not `samvil-analyze`, report expected stage and stop.
3. Read the target project directory structure.
4. Scan manifest files (`package.json`, `pyproject.toml`, `prisma/schema.prisma`).
5. Run MCP tool `scan_manifest(project_path="${PWD}")` to extract framework, language, database facts.
6. Run MCP tool `analyze_brownfield_project(project_root="${PWD}")` for deep analysis.
7. Generate analysis report:
   - Tech stack identification
   - Architecture patterns detected
   - Code quality metrics (file count, LOC estimate)
   - Dependency analysis
   - Potential issues and improvements
8. Save analysis to `.samvil/analysis.json`.
9. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-analyze")` on completion.

## Chain

Standalone stage — no chain continuation.
Present results to the user.
