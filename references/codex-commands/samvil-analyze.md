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
9. Update `project.state.json`: set `_analysis_source: "brownfield"` and
   `_analysis_context: {framework, solution_type, existing_feature_names, warnings}`.
10. Ask user what they want to do:
    - `기능 추가/개선` → write chain marker to `samvil-interview` (Brownfield Mode)
    - `코드 품질 개선` or `QA 검증` → write chain marker to `samvil-qa`
    - `디자인 개선` → write chain marker to `samvil-design`
11. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-analyze", next_skill="<chosen>")`.

## Brownfield Interview Chain (기능 추가/개선)

When the user chooses 기능 추가/개선, Codex proceeds to `samvil-interview`
(see `references/codex-commands/samvil-interview.md`). The interview detects
Brownfield Mode from `project.state.json._analysis_source == "brownfield"`,
skips tech-stack questions, and focuses on improvement goals. After the interview,
`merge_brownfield_seed` merges the existing seed with interview findings.
