# SAMVIL PM Interview Stage (Codex CLI)

## Prerequisites

Use the active native run-driver envelope. If its stage is not
`samvil-pm-interview`, stop and report the expected stage.

## Execution

1. Run `read_chain_marker(project_root="${PWD}")` for compatibility diagnostics,
   then confirm the active `get_stage_envelope` claim is `samvil-pm-interview`.
2. Read `project.seed.json` if it exists for context.
3. Conduct a PM-focused interview covering:
   - Product vision and target users
   - Key metrics for success
   - Epics and user stories
   - Task breakdown and prioritization
4. Save interview results to root `interview-summary.md`.
5. Run MCP tool `validate_pm_seed(pm_seed_json=<json>)` to validate PM seed structure. On valid output, run `gate_check(gate_name="interview_to_seed", samvil_tier=<tier>, metrics_json='{"seed_readiness":<validate.seed_readiness>,"ambiguity_converged":<validate.ambiguity_converged>}', project_root=".")`, require exact pass, and `claim_post(... subject="interview_to_seed", evidence_json='["interview-summary.md"]')`.
6. Run MCP tool `pm_seed_to_eng_seed(pm_seed_json=<json>)` to convert to engineering seed and write root `project.seed.json`.
7. Return `verdict="PASS"`, file:line evidence for both `interview-summary.md`
   and `project.seed.json`, and `requested_next_skill="samvil-design"` to the
   native run driver. Only when the user supplied exact `--council` on
   standard/thorough/full/deep, return `requested_next_skill="samvil-council"`.
8. Do not call `complete_stage` or `write_chain_marker`; the native driver owns
   the fixed-ID transition, receipt, event, claim, state, and marker.

## Chain

After the native driver returns the committed receipt, continue from its next
envelope. Default is `samvil-design`; explicit `--council` on standard+ routes
to `samvil-council`.
