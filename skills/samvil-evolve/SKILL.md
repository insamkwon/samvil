---
name: samvil-evolve
description: "Seed evolution loop. Wonder → Reflect → new seed version. Repeat until convergence or user stops."
---

# samvil-evolve (ultra-thin)

Adopt the **Evolve Driver** role. Auto-trigger detection, mode resolution,
cycle counter, and 4-dim baseline inputs are aggregated by
`mcp__samvil_mcp__aggregate_evolve_context`. Wonder/Reflect agent spawn,
4-dim scoring, AskUserQuestion checkpoint, and seed mutation stay here
(LLM judgement + host-bound). Existing MCP tools cover proposal/apply
plan/rebuild handoff/5-Gate validation/QA failure persistence — the skill
just wires them. Full Korean prose in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="evolve_gen", stage="evolve", data="{}")` — best-effort. Auto-claim posts `evidence_posted subject="stage:evolve"`.
2. Files are SSOT — read `project.seed.json`, `project.state.json`, `.samvil/qa-results.json`, `.samvil/qa-routing.json`, `decisions.log` (if present).
3. `mcp__samvil_mcp__materialize_evolve_context(project_root=".")` → writes `.samvil/evolve-context.json` (focus + routing + ground truth + seed_history).
4. `mcp__samvil_mcp__aggregate_evolve_context(project_root=".")` → returns `auto_trigger.{should_offer,triggers}`, `mode.{evolve_mode,evolve_max_cycles,max_total_builds,build_quota_reached}`, `cycle.{current_cycle,max_cycles,cap_reached,cycles_remaining}`, `four_dim_baseline.{core_problem_excerpt,seed_description,qa_verdict,ac_*_count}`, `errors[]`. On error: fall back to manual reads from `SKILL.legacy.md` (P8).

## Step 1 — Stop Conditions

- `mode.build_quota_reached` → stop, chain → retro.
- `cycle.cap_reached` → stop, chain → retro.
- Auto-invoked + `auto_trigger.should_offer` false + no explicit user request → confirm intent (P10).

## Step 2 — 4-Dimension Pre-Wonder Eval

Score 1–5 from `four_dim_baseline`: **Quality** (qa_verdict + AC counts) · **Intent** (core_problem_excerpt vs seed_description) · **Purpose** (description promise vs delivered) · **Beyond** (first-30s UX, retention, viral surface). Render block; flag dims ≤3/5 as focus. All ≥4/5 → likely converged but still run gates in Step 6.

## Step 3 — Wonder + Splits + Reflect

Cycle 1 = `config.model_routing.evolve` (default `opus`); cycle 2+ = `evolve_cycle` (default `sonnet`).

1. **Wonder** — spawn `wonder-analyst` (paste `agents/wonder-analyst.md`) with seed + `.samvil/evolve-context.json` + focus dims + prior failures: `mcp__samvil_mcp__load_failures_for_wonder(project_path=".")`. Wonder consumes `.samvil/build.log`, `.samvil/fix-log.md`, and `events.jsonl — structured build/QA event trail` to surface **repeated error signatures**, **repeated error categories**, reverted fixes, and **workaround patterns** that signal a spec issue rather than implementation.
2. **AC splits** — for each leaf in `seed.features[*].acceptance_criteria` (recursively): `mcp__samvil_mcp__suggest_ac_split(description=<leaf>)`. Collect `should_split=true`. Empty → skip mention.
3. **Reflect** — spawn `reflect-proposer` sequentially with wonder output + split candidates. Both ≤400 words.

## Step 4 — Proposal → Apply Plan → Apply

Prefer guarded apply over hand-edits:
```
mcp__samvil_mcp__materialize_evolve_proposal(project_root=".")
mcp__samvil_mcp__materialize_evolve_apply_plan(project_root=".")
mcp__samvil_mcp__apply_evolve_apply_plan(project_root=".")    # verifies hash, writes seed_history/v<N>.json
mcp__samvil_mcp__validate_evolved_seed(original_seed=<json>, evolved_seed=<json>)
```

**AC tree preservation (v3.0+)**: never collapse `acceptance_criteria[]` to flat strings; new ACs are leaves with fresh `id`, `children:[]`, `status:"pending"`, `evidence:[]`. Splits convert leaf→branch with children. Removals drop nodes. `schema_version` stays `"3.x"`.

## Step 5 — Persist + User Checkpoint

```
mcp__samvil_mcp__save_seed_version(session_id="<sid>", version=<N+1>, seed_json='<json>', change_summary="<brief>")
mcp__samvil_mcp__compare_seeds(seed_a='<prev>', seed_b='<new>')   # similarity + change list → seed_history/v<N>_v<N+1>_diff.md
```

Render diff block (Wonder findings · Proposed changes · Convergence trend) and ask `Apply this evolution? (yes / no / edit)`. **Autonomous mode** ("자율 진화", "알아서 해", "수렴할 때까지") skips checkpoint EXCEPT MAJOR changes (feature deletion, `core_experience` mutation) which always confirm.

## Step 6 — 5-Gate Convergence + Self-Correction Circuit

```
mcp__samvil_mcp__check_convergence_gates(eval_result_json=<curr>, history_json=<prior>)
mcp__samvil_mcp__check_convergence(seed_history='<JSON array>')   # legacy similarity
```

Gates: **eval** (score≥0.7 + final_approved) · **per_ac** (all PASS) · **regression** (no PASS→FAIL across cycles, P5) · **evolution** (≥1 mutation, no stagnant loop) · **validation** (not skipped/error). Any gate fails → render `verdict.blocked_by` + `verdict.reasons` + 4-choice menu (rollback / re-design failed AC / force converge [discouraged] / manual). **Anti-pattern: Blind convergence** — never override without user input.

For each failed AC this cycle:
```
mcp__samvil_mcp__record_qa_failure(project_path=".", ac_id=<id>, ac_description=<desc>, cycle=<N>, reason=<why>, suggestions_json='<array>')
```

## Step 7 — Chain (terminal or loop)

`save_event(event_type="evolve_converge", stage="evolve", data='{"final_version":<N+1>,"total_generations":<N>}')` if converged, else `event_type="stage_change"` with reason. Append Evolve section to `.samvil/handoff.md` via Bash `cat >>` or Edit (never Write tool).

- **Converged + spec-only** → `materialize_evolve_rebuild_handoff`, set `state.current_stage="build"`, invoke `samvil-build`.
- **Converged + full** → invoke `samvil-retro`.
- **User stop / max iter / quota** → invoke `samvil-retro`.
- **Not converged + cycles remain** → spec-only rebuilds changed features then re-QA; full continues. Loop back to Step 2.

## Anti-Patterns

1. >2 new features per cycle. 2. Modifying `name`/`mode`/`core_experience`. 3. Skipping checkpoint outside autonomous mode. 4. Collapsing AC tree leaves to flat strings. 5. Force-converging past failed gate without user opt-in.

## Legacy reference

Full Korean prose, dashboard examples, autonomous-mode policy, AC tree mutation rules, and verbose JSON schemas in `SKILL.legacy.md`. Consult only when evolve regresses or is extended.
