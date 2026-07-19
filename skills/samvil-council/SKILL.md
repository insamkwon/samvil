---
name: samvil-council
description: "Multi-agent council debate. Spawns agents via CC Agent tool, synthesizes verdicts, writes binding decisions. gate_override is unavailable without a trusted host adapter; blocked gates halt and force_proceed is forbidden."
---

# samvil-council (ultra-thin)

Adopt the **Council Conductor** role. Parallel agent spawn (Round 1
research + Round 2 review) stays here — Agent tool calls are CC-only.
What moves to MCP is the BEFORE (Round-1 → Round-2 debate-point
extraction) and AFTER (per-section consensus aggregation, dissent
preservation, overall verdict) logic, via
`mcp__samvil_mcp__synthesize_council_verdicts`. Current status: default-off
compatibility stage behind the exact `--council` flag (see
`references/council-retirement-migration.md`). Full Korean prose,
verbose synthesis examples, decisions.log shapes in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. Read `project.config.json` → check for `--council` flag in `flags`. **If absent**: `mcp__samvil_mcp__council_deprecation_warning()`, print returned string with `[SAMVIL]` tag, mark `state.completed_stages` `council` as `skipped`, invoke `samvil-design`, return.
2. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="council_started", stage="council", data="{}")` — best-effort, auto-claim writes `evidence_posted subject="stage:council"`.
3. Files are SSOT — read `project.seed.json`, `project.state.json`, `project.config.json`, `interview-summary.md`. Synthesis rules: `references/council-protocol.md`, `references/tier-definitions.md`.

**Brownfield Delta Mode** (`state._brownfield_seed_merged == true`): Council reviews only `seed.features[]` where `status == "new"`. Existing features (`status == "existing"`) are already in production — skip. Print `[SAMVIL] Council: Brownfield mode — reviewing <N> new features only (skipping <M> existing).`

## Step 1 — Tier-Gated Agent Activation

Apply `selected_tier` (full matrix in `SKILL.legacy.md`):
- `minimal` → skip. Print `[SAMVIL] Council: skipped (minimal tier)`, invoke `samvil-design`, return.
- `standard` → R1 skipped. R2: `product-owner`, `simplifier`, `scope-guard`.
- `thorough` → R1: `business-analyst`. R2: above + `ceo-advisor`.
- `full` → R1: `competitor-analyst`, `business-analyst`, `user-interviewer`. R2: all 4.
- `deep` → same council roster as `full`; deeper rigor is enforced by the downstream gates and interview contract.

## Step 2 — Round 1 (Research, parallel spawn) — skip if tier < thorough

1. Print `[SAMVIL] Spawning N agents for Council Round 1 (Research) | MAX_PARALLEL=<N>` then `mcp__samvil_mcp__heartbeat_state(state_path="project.state.json")`.
2. Determine `MAX_PARALLEL`: `config.max_parallel` if set else the CPU/memory watermarks in `references/decision-boundaries.md` (`SKILL.legacy.md` Step 2b).
3. **Compose prompts (MCP-owned, W3.2)**: `mcp__samvil_mcp__compose_agent_prompt(agent_names_json='["<r1 names>"]', project_root=".", header="You are {name} for SAMVIL Council Gate A, Round 1.", context_files_json='["project.seed.json","interview-summary.md"]', task='Return JSON: {"agent":"<name>","topics":[{"topic":"<short>","stance":"<one-liner>","is_blind_spot":bool}]}\nUnder 500 words.')` → `prompts.<name>`. `missing_agents` 비어있지 않으면 해당 agent만 legacy 방식(`<paste agents/<name>.md>` 직접 조립)으로 폴백 (P8).
   Split agents into chunks of `MAX_PARALLEL`. **Spawn each chunk in ONE message** (Agent tool, parallel):
   ```
   Agent(description: "SAMVIL Council R1: <name>",
         model: config.model_routing.council_research || "haiku",
         prompt: <prompts.<name> from compose_agent_prompt>,
         subagent_type: "general-purpose")
   ```
4. Between chunks: `is_state_stalled` → if stalled, `increment_stall_recovery_count` + `build_reawake_message`, print, continue. Cap at `MAX_REAWAKES` from `references/decision-boundaries.md` (then surface skip/abort/retry AskUserQuestion).
5. Collect verdicts as `round1_verdicts` (list of `{agent, topics:[]}`).

## Step 3 — Synthesize Round 1 → Round 2 Injection

```
mcp__samvil_mcp__synthesize_council_verdicts(
  round1_verdicts_json='<JSON list>', round2_verdicts_json='')
```

Returned `round1_debate_points.{consensus,debate,blind_spots}` is structured truth; `round2_injection_md` is the ready-to-paste markdown block for Round 2 prompts. Print one-line summary per Round 1 agent.

## Step 4 — Round 2 (Review, parallel spawn)

Same MAX_PARALLEL chunked-parallel pattern as Step 2. Compose via `mcp__samvil_mcp__compose_agent_prompt(agent_names_json='["<r2 names>"]', header="You are {name} for SAMVIL Council Gate A, Round 2.", context_files_json='["project.seed.json","interview-summary.md"]', context_inline="<round2_injection_md from Step 3, if Round 1 ran>\n위 논쟁점/블라인드 스팟에 입장을 표명하세요.", task='Return JSON: {"agent":"<name>","sections":[{"section":"<name>","verdict":"approve|challenge|reject","severity":"minor|blocking","reasoning":"<one line>"}]}\nUnder 500 words.')` — `missing_agents`는 legacy paste로 폴백 (P8). For each Round 2 agent:
```
Agent(description: "SAMVIL Council R2: <name>",
      model: config.model_routing.council || "sonnet",
      prompt: <prompts.<name>>,
      subagent_type: "general-purpose")
```
Heartbeat + stall checks between chunks (same as Step 2). Collect as `round2_verdicts`.

## Step 5 — Final Synthesis

```
mcp__samvil_mcp__synthesize_council_verdicts(
  round1_verdicts_json='<JSON list>', round2_verdicts_json='<JSON list>')
```

Returns `sections[]` (per-section consensus_score + tier + dissenting + blocking), `blocking_objections[]`, `overall_verdict` ∈ {`PROCEED`, `PROCEED_WITH_CHANGES`, `HOLD`} + `overall_reasons`.

Render `[SAMVIL] Council 결과` block (per `SKILL.legacy.md` format): per-section `N/M APPROVE` line, agent reasoning blocks (2-3 lines each), Consensus Score, overall verdict, then `⚠️ 반대 의견 (Devil's Advocate)` listing every entry in any `sections[*].dissenting`.

## Step 6 — Handle Result

- `PROCEED` → continue to Step 7.
- `PROCEED_WITH_CHANGES` → AskUserQuestion: `Council recommends these changes. Apply them? (yes / no / I'll edit manually)`. yes → atomic-write `project.seed.json` with changes; no → keep original; edit → wait, re-read seed.
- `HOLD` → AskUserQuestion presenting `blocking_objections` + weak-consensus sections, wait for direction. Never auto-modify seed without user approval (P10).

## Step 7 — Persist Decisions

For each non-APPROVE verdict (CHALLENGE/REJECT, including `dissenting`), append a row to `<project>/decisions.log` (append-only JSON array): `{id:"d<NNN>", gate:"A", round:2, agent, decision, reason, severity, binding:<true if majority>, dissenting:<true if minority>, applied:<bool>, consensus_score, timestamp}`. Exact shapes in `SKILL.legacy.md`.

Then promote each row (best-effort):
```
mcp__samvil_mcp__promote_council_decision(
  project_root="<absolute>", decision_json='<one row>')
```
MCP fail → decisions.log is fallback truth (P8/INV-5); log warning, continue. Do not block handoff.

## Step 8 — Chain to Design (INV-4)

```
mcp__samvil_mcp__save_event(session_id="<sid>", event_type="council_verdict", stage="design", data='{"verdict":"<PROCEED|PROCEED_WITH_CHANGES|HOLD>","agents_count":<N>}')
```
Append Council section to `.samvil/handoff.md` via Bash `cat >>` or Edit (never Write tool): tier · consensus N/M (%) · verdict · changes applied · dissenting summary. Print `[SAMVIL] Gate A complete. Proceeding to design...` and invoke Skill tool with skill `samvil-design`.

## Anti-Patterns

1. Auto-modifying seed without user approval on PROCEED_WITH_CHANGES. 2. Spawning agents the tier doesn't include. 3. Skipping Step 3 (Round 1 synthesis) before Round 2 — R2 must see debate points. 4. Dropping dissenting opinions — `sections[*].dissenting` MUST appear in Devil's Advocate block and decisions.log. 5. Proceeding past `HOLD` without user input (P5 Blind convergence). 6. Using Write tool for handoff.md (Bash `cat >>` or Edit only). 7. Spawning agents serially when MAX_PARALLEL allows — chunk-parallel non-negotiable. 8. **`AskUserQuestion` 호출 포맷**: `questions` 파라미터는 반드시 배열 — `questions=["<질문>"]`. 문자열 직접 전달 시 `InputValidationError` 발생.

## Legacy reference

Full Korean prose (Round 1 debate-point markdown, per-tier activation matrix, MAX_PARALLEL heuristic, PROCEED / PROCEED_WITH_CHANGES dashboard examples, decisions.log JSON shapes, ADR promotion details, runtime-specific chain footers) in `SKILL.legacy.md`. Consult only when council regresses or is extended.
