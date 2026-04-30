# SAMVIL Retro Stage (Codex CLI)

## Auto-Proceed Policy

This stage is **always mechanical** — it reads artifacts and writes a report.
There are no risky or irreversible decisions.

When invoked as part of a pipeline chain (e.g., after samvil-evolve):
- **Execute immediately without asking for user confirmation.**
- Do not stop and say "shall I continue?". Just run.

The only user-facing question in this stage is the optional evolve-cycle
prompt at the very end, which is a genuine decision point and should wait.

## Prerequisites

Read `.samvil/next-skill.json`. If `next_skill` is not `samvil-retro`, skip this stage.
Ensure the pipeline has completed at least one full cycle.

## Execution

1. Run MCP tool `read_chain_marker(project_root="${PWD}")` to confirm this is the expected stage.
2. Read `.samvil/project.seed.json` for final seed state.
3. Read `.samvil/qa-results.json` for QA outcomes.
4. Read `.samvil/events.jsonl` for pipeline event history.
5. Run MCP tool `aggregate_retro_metrics(project_root="${PWD}")` for file-based metrics.
   Use the returned metrics (including file-based fallbacks) to populate the report.
6. Generate retrospective covering:
   - What worked well (strengths to keep)
   - What didn't work (weaknesses to fix)
   - Observations with severity (CRITICAL/HIGH/MEDIUM/LOW)
   - Concrete suggestions (ISS-ID, target_file, reason, expected_impact)
7. Save retro to `.samvil/retro-results.md`.
8. Run MCP tool `write_chain_marker(project_root="${PWD}", host_name="codex_cli", current_skill="samvil-retro")` to record completion.
9. Run MCP tool `clear_chain_marker(project_root="${PWD}")` — pipeline complete.

## Chain

This is the final stage. No further chain marker needed.
Present the retro summary to the user, then ask if they want to start
an evolve cycle (this is the single genuine decision point in this stage).
