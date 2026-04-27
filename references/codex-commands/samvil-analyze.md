# SAMVIL Analyze Stage (Codex CLI)

## Prerequisites

This is a standalone stage — no chain marker required.
Point at an existing project directory.

## Execution

1. Read the target project directory structure.
2. Scan manifest files (`package.json`, `pyproject.toml`, `prisma/schema.prisma`).
3. Run MCP tool `scan_manifest(project_path="${PWD}")` to extract framework, language, database facts.
4. Run MCP tool `analyze_brownfield_project(project_root="${PWD}")` for deep analysis.
5. Generate analysis report:
   - Tech stack identification
   - Architecture patterns detected
   - Code quality metrics (file count, LOC estimate)
   - Dependency analysis
   - Potential issues and improvements
6. Save analysis to `.samvil/analysis.json`.

## Chain

Standalone stage — no chain continuation.
Present results to the user.
