# Contract Layer Protocol — v3.2 skill integration guide

Single source of truth for how v3.2 stage skills interact with the
contract layer (① Claim / ⑤ Role / ⑥ Gate / ⑦ Jurisdiction / ⑩
Stagnation / ⑨ Consensus).

**Design principle.** Sub-skills do not sprinkle MCP calls throughout
their bodies. Contract-layer interaction is concentrated at two
points per stage:

```
pre_stage  →  [stage body unchanged]  →  post_stage
```

Each skill references this protocol by name; the minimal per-stage
addition is the **domain-specific** call (e.g. `compute_seed_readiness`
at the end of interview because only interview has those dimensions).

## Protocol at a glance

| Point | What runs | Who provides | Skill action |
|-------|-----------|--------------|--------------|
| **pre_stage** | `check_jurisdiction` on the pending action + `route_task` with stage-role + `claim_post(type=seed_field_set \| gate_verdict \| evidence_posted, status=pending)` | skill | one MCP batch call at skill entry |
| **stage body** | existing v3.1 behavior | skill | unchanged |
| **post_stage** | `claim_verify` by the Judge identity (or `agent:user` / `agent:orchestrator-agent` for system-level stages) + `gate_check` for the next gate + `stagnation_evaluate` on failure | skill | one MCP batch call at skill exit |

Every claim posted during the stage acquires `claimed_by` = the role-tagged
agent that posted it. `verified_by` is filled at post_stage by a Judge
(or out-of-band verifier). This is how Generator ≠ Judge is enforced
through the ledger without scattering checks across the skill body.

## pre_stage wrapper

At the top of every stage skill, after reading seed/state but before
any heavy work:

```
1. Jurisdiction check
   mcp__samvil_mcp__check_jurisdiction(
     action_description="<stage-name> stage for project <name>",
     command="",              # empty unless the stage runs shell commands
     filenames_json="[...]",  # files this stage may touch
     diff_text=""              # empty at entry
   )
   → If jurisdiction=user: print pending confirmation, wait for user 'ㄱ'/approve.
   → If jurisdiction=external: proceed and emit an evidence_posted claim for whatever external lookup was required.
   → If jurisdiction=ai: proceed silently.

2. Task routing (Sprint 2)
   mcp__samvil_mcp__route_task(
     task_role="<role name for this stage>",
     project_root="."
   )
   → Record the chosen model_id in state.json.current_model.
   → Skip when the stage only drives file mutations (scaffold, retro).

3. Stage_start claim (best-effort)
   mcp__samvil_mcp__claim_post(
     project_root=".",
     claim_type="evidence_posted",
     subject="stage:<name>",
     statement="<stage> started on <ts> at tier=<samvil_tier>",
     authority_file="state.json",
     claimed_by="agent:<primary agent for this stage>",
     evidence_json='["<project.state.json path>"]'
   )
```

## post_stage wrapper

At the bottom of every stage skill, after the stage body completes but
before invoking the next skill via the chain pattern:

```
1. Verify the stage_start claim (best-effort)
   mcp__samvil_mcp__claim_verify(
     project_root=".",
     claim_id="<id from pre_stage>",
     verified_by="agent:product-owner"  # or another Judge
     # for system stages use verified_by="agent:user"
   )

2. Next-gate evaluation
   mcp__samvil_mcp__gate_check(
     gate_name="<next gate from §3.⑥>",
     samvil_tier="<from state.json>",
     metrics_json='{"<stage-specific metrics>": <values>}',
     project_root="."
   )
   → On verdict=block: halt chain. Write gate_verdict claim. Print the
     required_action and ask the user.
   → On verdict=escalate: re-spawn the stage with `route_task(attempts=1)`
     which bumps cost_tier. Cap via gate_should_force_user after 2 attempts.
   → On verdict=pass: record gate_verdict claim (verified by Judge) and
     proceed to chain invoke the next skill.
   → On verdict=skip: record skip in state.json.completed_stages, proceed.

3. Stagnation sniff (optional; do on any non-pass)
   mcp__samvil_mcp__stagnation_evaluate(
     input_json='{"error_history": [...], "current_error": "<if any>",
                  "qa_score_history": [<if qa stage>], "qa_iterations_window": 3}'
   )
   → severity=HIGH → lateral_propose and inject the lateral prompt into the stage retry.

4. Narrate (optional; only at pipeline end)
   Only the orchestrator (`samvil` skill) runs narrate at completion.
```

## Per-stage task_role

Used when calling `route_task`.

| Stage | task_role |
|-------|-----------|
| interview / pm-interview | socratic-interviewer (out-of-band; skip route_task) |
| seed | seed-architect |
| council | ceo-advisor / growth-advisor (reviewer role) |
| design | tech-architect |
| scaffold | scaffolder |
| build | build-worker |
| qa | qa-functional (Judge) |
| deploy | deployer |
| retro | retro-analyst |
| evolve | reflect-proposer |

## Per-stage next-gate mapping

Used when calling `gate_check` at post_stage.

| After stage | gate_name | Metrics the skill passes |
|-------------|-----------|--------------------------|
| interview | `interview_to_seed` | `{"seed_readiness": <float>, ...per-dim scores}` |
| seed | `seed_to_council` | `{"schema_valid": bool, "schema_version_min": "3.2"}` |
| council | `council_to_design` | `{"consensus_required": bool}` |
| design | `design_to_scaffold` | `{"blueprint_valid": bool, "stack_matrix_match": bool}` |
| scaffold | `scaffold_to_build` | `{"sanity_build_ok": bool, "env_vars_present": bool}` |
| build | `build_to_qa` | `{"implementation_rate": <float 0..1>}` |
| qa | `qa_to_deploy` | `{"three_pass_pass": bool, "zero_stubs": bool}` |
| * (end of chain) | `any_to_retro` | `{"always_run": true}` |

## What stays OUT of skills

- **Claim ledger append-only mechanics.** The ledger module handles
  duplicate-prevention and file rotation.
- **G ≠ J enforcement logic.** `claim_verify` rejects violations;
  skills do not reimplement the check.
- **Model profile resolution.** `route_task` reads the yaml. Skills
  just pass `task_role`.
- **Threshold arithmetic.** `gate_check` reads `gate_config.yaml` and
  applies per-tier floors.
- **Performance budget bookkeeping.** Sprint 6 `budget_status` tool
  consumes consumption numbers; skills pass their observed values and
  honor hard_stop.

## Failure / degradation

Per `references/graceful-degradation.md`, every MCP call is
**best-effort**. Skills write to local files first, then call MCP. When
a contract-layer call returns `{"error": ...}`:

- pre_stage errors → log to `.samvil/mcp-health.jsonl`, proceed (never
  hard-block on unreachable MCP).
- post_stage errors → log, proceed, but record an `evidence_posted`
  claim that the gate check was skipped due to degradation so retro
  can audit drift.

Never fake a `gate_verdict=pass` when the check couldn't run.

## Quick-reference checklist for skill authors

When adding a new stage skill:

- [ ] pre_stage MCP batch at skill entry
- [ ] post_stage MCP batch before chain invoke
- [ ] `task_role` picked from the mapping table
- [ ] `next_gate` and metrics match the mapping table
- [ ] Non-pass verdict branches: block / escalate / skip handled
- [ ] Failure paths wrapped in try/catch that logs to mcp-health.jsonl
- [ ] `scripts/check-skill-wiring.py` (grep-based smoke) stays green
