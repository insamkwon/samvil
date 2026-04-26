---
name: samvil-interview
description: "Socratic interview with app presets, unknown-unknown probing, and zero-question mode. Korean language."
---

# samvil-interview (ultra-thin)

Adopt the **Socratic Interviewer** role. **All conversation is in Korean**;
code/technical terms only in English. Tier resolution, Zero-Question Mode
detection, preset matching (custom > built-in), and manifest scan are
aggregated by `mcp__samvil_mcp__aggregate_interview_state`. Phase 0–4
question loops, AskUserQuestion checkpoints, per-question PATH routing,
and summary verification stay here (host-bound, Korean-prompt heavy).
Existing MCP tools cover ambiguity / seed-readiness / gate / domain
context. Full Korean prose, per-`solution_type` question banks, Phase
2.x expansion templates, and tier-by-tier tables in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="interview_start", stage="interview", data="{}")` — best-effort. Auto-claim posts `evidence_posted subject="stage:interview"`.
2. Files are SSOT — read `project.state.json`, `project.config.json`, `references/app-presets.md`. Read `references/interview-frameworks.md` + `interview-question-bank.md` only when entering a Phase 2.x.
3. `mcp__samvil_mcp__aggregate_interview_state(project_root="<cwd or ~/dev/<slug>>", prompt="<one-line>")` → `tier.{samvil_tier,source,valid_tiers}` (5-valued: includes `deep`), `ambiguity_target`, `required_phases[]` (`core/scope/lifecycle/unknown/nonfunc/inversion/stakeholder/research/domain_deep`), `mode.{is_zero_question,matched_signals}`, `preset.{name,keywords,source,description?}`, `custom_presets_count`, `manifest`, `paths.{interview_summary,state_file,config_file,preset_dir}`, `errors[]`. On error: fall back to manual reads from `SKILL.legacy.md` (P8).
4. `mcp__samvil_mcp__render_domain_context(solution_type="<from orchestrator>", stage="interview")` — best-effort. `interview_probes` / `risk_checks` / `core_entities` are question candidates only; never override user input.

## Step 0 — Mode + Preset

- `mode.is_zero_question` true → render `[SAMVIL] Zero-Question Mode`. Skip Phase 2/3 loops, generate seed-level summary from `preset` defaults, jump to Step 4 (single review **mandatory**).
- `custom_presets_count > 0` and `preset.source == "builtin"` → AskUserQuestion: "저장된 커스텀 프리셋 중 사용하시겠어요?" with custom presets + "새로 만들게요". Re-run aggregator with the chosen preset's keywords on selection.
- `preset.name` non-empty → load that preset's "기본 기능"/"흔한 함정"/"Pre-mortem" rows from `references/app-presets.md`. Otherwise spawn `competitor-analyst` (full tier only) or proceed empty.

## Step 1 — PATH Routing + Rhythm Guard (per-question)

For every question issued in Step 2/3:

```
streak = state.get("ai_answer_streak", 0)
mcp__samvil_mcp__route_question(question="<text>", manifest_facts=<json from aggregate.manifest>, force_user=(streak >= 3))
# Path actions: auto_confirm / code_confirm / user / research / forced_user (full table in SKILL.legacy.md §0.7b)
source = mcp__samvil_mcp__extract_answer_source(answer="<reply>")
state["ai_answer_streak"] = mcp__samvil_mcp__update_answer_streak(streak, source)["new_streak"]
```

Track breadth: `mcp__samvil_mcp__manage_tracks(action="init"|"update"|"check"|"resolve", ...)`.

## Step 2 — Phase Loop (Korean, host-bound)

Run **only the phases listed in `aggregate.required_phases`**. **한 번에
하나씩** AskUserQuestion (객관식 + Other), preset-aware options. Adaptive
follow-up by answer length (short → expand, long → structure, vague →
choose). Framework names (AARRR/JTBD/HEART) **never** exposed to user.

Per-`solution_type` question bodies in `SKILL.legacy.md`:

| Phase id | Title | Trigger | Body location |
|---|---|---|---|
| `core` | Phase 1 Core Understanding | always | §"Phase 1" by `solution_type` |
| `scope` | Phase 2 Scope Definition | always | §"Phase 2" by `solution_type` |
| `unknown` | Phase 2.5 Unknown Unknowns | thorough+ or auto-detect | §"Phase 2.5" Pre-mortem + Inversion |
| `nonfunc` | Phase 2.6 Non-functional | thorough+ | `interview-question-bank.md` Common §1–7 |
| `inversion` | Phase 2.7 Inversion | thorough+ | §"Phase 2.7" failure paths + anti-req |
| `stakeholder` | Phase 2.8 Stakeholder/JTBD | full+ | §"Phase 2.8" primary user JTBD + payer |
| `lifecycle` | Phase 2.9 Customer Lifecycle | standard+ | §"Phase 2.9" 8 stages × 1–2Q |
| `research` | PATH 4 Research bundle | full+ | flush every TBD via Tavily |
| `domain_deep` | Domain pack 25–30Q | deep | `render_domain_context` probes |

## Step 3 — Convergence Check

Re-score after each Phase: `mcp__samvil_mcp__score_ambiguity(interview_state='<json>', tier="<aggregate.tier.samvil_tier>")`.
Render milestone (`INITIAL/PROGRESS/REFINED/READY`) + `floor_violations`
+ `missing_items`. Loop back to weakest Phase until **all 4 gates Y**
(Goal / Scope / AC / Constraints) **AND** `ambiguity ≤ aggregate.ambiguity_target`.
Cap 2 reprompts per phase, then force-progress with a recorded gap.

**AC Testability Gate (PHI-06)**: vague AC ("좋은", "빠른", "직관적인", "smooth"…) → AskUserQuestion to rewrite. Never accept vague AC silently.

## Step 4 — Summary + User Verification

Render `solution_type`-specific summary (template in `SKILL.legacy.md`
§"Phase 4: 요약 & 확인"). AskUserQuestion → `좋아 진행해` / `수정할 부분 있어`.
**Zero-Question Mode is no exception** — single review is mandatory.

If `preset.source == "none"` or user changed direction substantially:
AskUserQuestion → preset 저장 여부. On 저장 → write
`<aggregate.paths.preset_dir>/<name>.json` (schema in
`references/app-presets.md` Custom Presets §).

## Step 5 — Persist + Contract Layer (post_stage)

1. Write summary to `aggregate.paths.interview_summary` (Korean, sections per `SKILL.legacy.md` §"Output Format" by `solution_type`). Each section non-empty; constraints ≥1; success criteria ≥3.
2. `mcp__samvil_mcp__compute_seed_readiness(dimensions_json='{"intent_clarity":<f>,"constraint_clarity":<f>,"ac_testability":<f>,"lifecycle_coverage":<f>,"decision_boundary":<f>}', samvil_tier="<tier>")` — score each dim from recorded answers; flag estimates in summary.
3. `mcp__samvil_mcp__gate_check(gate_name="interview_to_seed", samvil_tier="<tier>", metrics_json='{"seed_readiness":<total>}', project_root=".")`.
   - `block` → loop back to failing dim's owning Phase (`required_action.type` ∈ `split_ac/run_research/stronger_model/ask_user`). Cap 2 escalations via `gate_should_force_user`.
   - `escalate` → bump `interview_level` one step (`normal→deep→max`) and re-run that Phase.
   - `pass` → continue.
4. `mcp__samvil_mcp__claim_post(project_root=".", claim_type="gate_verdict", subject="interview_to_seed", statement="verdict=<v>, seed_readiness=<total>", authority_file="state.json", claimed_by="agent:socratic-interviewer", evidence_json='["interview-summary.md"]', meta_json='<verdict dict>')`. Per `references/contract-layer-protocol.md`, the Judge here is `agent:user` or `agent:product-owner` invoked out-of-band during approval — do NOT self-verify.
5. `mcp__samvil_mcp__save_event(event_type="interview_complete", stage="seed", data='{"questions_asked":<N>,"preset_matched":"<preset.name>"}')`.
6. Append the Interview block to `.samvil/handoff.md` via Bash `cat >>` or Edit (never the Write tool).

## Step 6 — Chain

Invoke the Skill tool with `samvil-seed`. **NO COMPACT** — interview
context is needed verbatim. Codex CLI fallback: read `skills/samvil-seed/SKILL.md`.

## Anti-Patterns

1. Asking 2+ questions in a single AskUserQuestion. 2. Skipping summary verification (Zero-Question Mode included). 3. Accepting a vague AC without offering a rewrite (PHI-06). 4. Exposing framework names (AARRR/JTBD/HEART) to the user. 5. Self-verifying the `interview_to_seed` gate verdict (Generator ≠ Judge). 6. Hard-coding `chain.next_skill` instead of always invoking `samvil-seed`.

## Legacy reference

Full Korean Phase 1–4 question bodies per `solution_type`, Phase 2.x
expansion templates, 5-path routing decision tables, Tier-by-Tier rule
tables, summary templates, custom-preset JSON schema notes, and the
adaptive follow-up matrix in `SKILL.legacy.md`. Consult only when the
interview regresses or is extended.
