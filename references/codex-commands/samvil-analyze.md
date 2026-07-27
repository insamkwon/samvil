# SAMVIL Analyze Stage (Codex CLI)

## Prerequisites

Point at an existing project directory.

## Execution

1. Run `read_chain_marker(project_root="${PWD}")` for compatibility diagnostics,
   then confirm the active `get_stage_envelope` claim is `samvil-analyze`.
2. If the envelope points elsewhere, report the expected stage and stop.
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
    - `기능 추가/개선` → choose `samvil-interview` (Brownfield Mode)
    - `코드 품질 개선` or `QA 검증` → choose `samvil-qa`
    - `디자인 개선` → choose `samvil-design`
11. Return `verdict="PASS"`, file:line evidence for `.samvil/analysis.json`, and
    `requested_next_skill="<chosen>"` to the native run driver.
12. Do not call `complete_stage` or `write_chain_marker`; the native driver owns
    the fixed-ID transition and all receipt/event/claim/state/marker writes.

## Brownfield Interview Chain (기능 추가/개선)

When the user chooses 기능 추가/개선, Codex proceeds to `samvil-interview`
(see `references/codex-commands/samvil-interview.md`). The interview detects
Brownfield Mode from `project.state.json._analysis_source == "brownfield"`,
skips tech-stack questions, and focuses on improvement goals. After the interview,
`merge_brownfield_seed` merges the existing seed with interview findings.
