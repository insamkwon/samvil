---
name: samvil
description: "AI vibe-coding harness. One-line prompt → full web app. Pipeline: Interview → Seed → Scaffold → Build → QA → Retro. gate_override is unavailable without a trusted host adapter; blocked gates halt and force_proceed is forbidden."
---

# samvil (ultra-thin orchestrator)

Adopt the **SAMVIL Orchestrator** role. Tier resolution, 3-layer
`solution_type` detection (L1 keyword + L2 context), PM-mode signal,
brownfield/resume detection from filesystem artifacts + `project.state.json`,
and first-skill selection are aggregated by
`mcp__samvil_mcp__aggregate_orchestrator_state`. Health Check shell calls,
AskUserQuestion checkpoints (unresolved mode + tier + low-confidence L3 + resume), and
chain dispatch via HostCapability stay here (host-bound + LLM judgement).
Existing MCP tools cover orchestration state / stage gating /
jurisdiction / chain strategy — the skill just wires them. Full Korean
prose, Health Check details, project init schema, and Gate A protocol in
`SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. Run these in parallel (best-effort, all non-fatal per P8):
   - `mcp__samvil_mcp__health_check()` → `samvil_version`, `tool_count`, `db_ok`, `python_version`, `hook_failures_24h`, `last_hook_failure`
   - `mcp__samvil_mcp__get_health_tier_summary(project_root="<cwd>")` → tier line
   - Bash: `node --version 2>/dev/null && echo OK || echo MISSING`
   - Bash: `uv --version 2>/dev/null || echo MISSING`
   - Bash: `gh --version 2>/dev/null | head -1 || echo MISSING`
   - Bash: `command -v python3 >/dev/null 2>&1 && echo HEALTHY || echo 'DEGRADED(no python)'` → Contract status

   Render as a table **before** asking any question:
   ```
   | 항목         | 상태                              |
   |--------------|-----------------------------------|
   | SAMVIL       | ✅ v<samvil_version>              |
   | Node.js      | ✅/❌ <version or MISSING>        |
   | Python       | ✅ <python_version>               |
   | uv           | ✅/⚠️ <version or MISSING>       |
   | gh           | ✅/⚠️ <version or MISSING>       |
   | MCP 도구     | ✅ <tool_count>개                 |
   | DB           | ✅/❌                             |
   | Hooks        | ✅ / ⚠️ <hook_failures_24h> fail(24h) |
   | Contract     | ✅ HEALTHY / ⚠️ DEGRADED(no python)  |
   | Health Tier  | ✅/⚠️/🔴 <HEALTHY/DEGRADED/CRITICAL> |
   ```
   `hook_failures_24h > 0` → table 아래에 `last_hook_failure.error` 한 줄 출력
   (claim ledger가 불완전할 수 있음을 사용자에게 알림).
   Node.js MISSING → halt with install instructions. All others degrade gracefully.
2. Files are SSOT — never trust conversation history for tier or stage. Inputs come from the aggregator, not memory.
3. `mcp__samvil_mcp__check_jurisdiction(action_description="SAMVIL pipeline start: <prompt> at tier=<tier>", command="", filenames_json='["project.seed.json","project.state.json","project.config.json"]', diff_text="")` — once at boot. `user` jurisdiction → confirm explicitly (`ㄱ`/`고`/`yes`); `external` → resolve dependency then `claim_post(type="evidence_posted")`; `ai` → continue silently.
4. `mcp__samvil_mcp__aggregate_orchestrator_state(project_root="<cwd or ~/dev/<slug>>", prompt="<one-line>", cli_tier="<--tier flag or empty>", mode_hint="<brownfield|greenfield|empty>", host_name="<claude_code|codex_cli|opencode|generic>", council_opt_in=<--council present>)` → returns `tier.{samvil_tier,source,aliased_from}`, `solution_type.{solution_type,layer,matched,confidence}`, `is_pm_mode`, `council_opt_in`, `brownfield.{is_brownfield,can_resume,artifacts,state_present,current_stage,completed_stages}`, `chain.{next_skill,reason,resume_point}`, `errors[]`. Persist explicit `--council` in `project.config.json.flags`; absent means default-off. On error: fall back to manual reads from `SKILL.legacy.md` (P8).

## Step 1 — Health Check + Project Mode

Render the Health Check table (Node / Python / uv / gh / SAMVIL version / MCP). Auto-install Node/Python/uv via `brew` when missing on macOS; Node failure halts (only true requirement). All other gaps degrade gracefully.

If no `--mode` flag and `errors[]` has no entry prefixed `"brownfield:"`, accept a decisive artifact scan: `brownfield.is_brownfield == true` → print `ℹ️ 기존 프로젝트 감지`; false with no resume artifacts → print `ℹ️ 새 프로젝트로 시작`. AskUserQuestion → "어떤 작업을 할까요?" only when the scan has errors or conflicting artifacts, with options `새 프로젝트` / `기존 프로젝트 개선` / `단일 단계만 실행`. Selection re-runs the aggregator with `mode_hint`.

## Step 2 — Tier Confirmation

If `tier.source == "default"` or the user passed no `--tier` flag, AskUserQuestion → "어떤 수준으로 만들까요?" with `minimal` / `standard` / `thorough` / `full` / `deep`. If `harness-feedback.log` has prior runs of the same `solution_type`, append the historical pass-rate per tier. Persist the chosen tier to `project.config.json` (`samvil_tier` + `selected_tier` for legacy compatibility).

## Step 3 — solution_type L3 Confirmation

If `solution_type.confidence == "high"`, print `ℹ️ 프로젝트 타입: <type> (감지 근거: <matched>)`, skip confirmation, and persist the detected type. 중·저신뢰(`medium|low`)에서만 AskUserQuestion: "이 프로젝트는 <type>인가요?" with the 5 canonical options, then persist the final answer to `project.state.json`.

## Step 4 — Brownfield + Resume Routing

- `brownfield.is_brownfield` true → invoke `samvil-analyze` (which owns reverse-seed + gap analysis + chain). Do not initialize a fresh state file.
- `brownfield.can_resume` true with `state_present` → render `completed_stages` and `current_stage`; AskUserQuestion: 이어서 진행 vs 처음부터 다시. On resume, do NOT overwrite `project.state.json`; jump directly to `chain.next_skill`.
- Neither → fresh greenfield: `mkdir -p ~/dev/<project_name>/.samvil`, write a default `project.state.json` (`session_id=null`, `current_stage="interview"`, `completed_stages=[]`, `samvil_tier=<chosen>`) and `project.config.json` (with `model_routing` defaults from `references/model_profiles.defaults.yaml`).

`mcp__samvil_mcp__create_session(project_name="<slug>", samvil_tier="<tier>", project_root="~/dev/<slug>")` — best-effort. Parse `session_id`, write back to `project.state.json`.

## Step 5 — Pipeline Tasks + Start Event

`TaskCreate` for each default pipeline stage so the user sees progress: Interview, Seed, Design, Scaffold, Build, QA, Deploy, Retro. Council is not a default task; explicit `--council` is routed by `samvil-seed`. Each downstream skill flips its task to `in_progress` / `completed`.

```
mcp__samvil_mcp__save_event(session_id="<sid>", event_type="stage_change", stage="interview", data='{"app":"<prompt>","tier":"<tier>","solution_type":"<type>"}')
```

Print:

```
[SAMVIL] Starting pipeline for: "<prompt>"
[SAMVIL] Project: ~/dev/<slug>/
[SAMVIL] Tier: <samvil_tier> (source=<source>)
[SAMVIL] solution_type: <type> (<confidence>)
[SAMVIL] Chain: <chain.next_skill> — <chain.reason>
```

## Step 6 — Chain Dispatch (HostCapability)

Resolve `mcp__samvil_mcp__resolve_host_capability(host_name="<host>")` + `mcp__samvil_mcp__host_chain_strategy(host_name="<host>")`.

- Default greenfield route is `samvil-interview`; PM-mode route is
  `samvil-pm-interview`; brownfield/resume modes use the returned
  `chain.next_skill` target such as `samvil-analyze`.
- `chain_via=skill_tool` → invoke `chain.next_skill` directly via the Skill tool.
- `chain_via=file_marker` → write `.samvil/next-skill.json` (`schema_version="1.0"`, `chain_via="file_marker"`, `host`, `next_skill=chain.next_skill`, `reason=chain.reason`, `from_stage="orchestrator"`, `created_by="samvil"`) and tell the user to invoke that skill manually.
- `chain_via=manual` → instruct the user to run the next skill explicitly.

`config.skip_stages` is honored by every downstream skill — orchestrator does not skip on its behalf.

## Contract Layer Protocol (v3.2)

This skill owns chain entry only. Per `references/contract-layer-protocol.md`, every stage skill runs its own `pre_stage` (task routing + `stage_start` claim) and `post_stage` (claim verify + `gate_check`). The orchestrator does not duplicate them.

## Anti-Patterns

1. Initializing a fresh `project.state.json` on top of a resume scenario (overwrites prior progress).
2. Skipping L3 confirmation at 중·저신뢰; high-confidence keyword classification is descriptive and uses an ℹ️ notice.
3. Hard-coding `chain.next_skill` instead of using the aggregator output (regresses brownfield + resume routing).
4. Calling Council/Design tools from the orchestrator — those belong to their own thin skills.
5. Mutating `samvil_tier` after Step 2 confirmation without re-asking the user.
6. **`AskUserQuestion` 호출 포맷**: `questions` 파라미터는 반드시 배열 — `questions=["<질문>"]`. 문자열 직접 전달 시 `InputValidationError` 발생.

## Legacy reference

Full Korean Health Check prose, project init JSON schemas, Resume scenarios (4-A / 4-B / 4-C), Tier-table descriptions with feedback-log lookup, Gate A 2-round structure, Plugin System hook map, and Error Recovery matrix in `SKILL.legacy.md`. Consult only when the orchestrator regresses or is extended.
