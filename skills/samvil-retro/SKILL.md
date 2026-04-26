---
name: samvil-retro
description: "Post-run retrospective. Analyze run metrics from files, suggest 3 harness improvements, append to feedback log."
---

# samvil-retro (ultra-thin)

Adopt the **Retro Analyst** role. Per-run metrics, recurring-pattern
detection across `harness-feedback.log`, bottleneck stages, flow
compliance, agent utilization, v3 leaf stats, MCP health, and next
suggestion-ID are aggregated by `mcp__samvil_mcp__aggregate_retro_metrics`.
Choosing the 3 final suggestions, AskUserQuestion preset accumulation, and
the `harness-feedback.log` append stay here (LLM judgement + host-bound).
Full Korean prose in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="retro_started", stage="retro", data="{}")` — best-effort. Auto-claim posts `evidence_posted subject="stage:retro"`.
2. If `.samvil/metrics.json` exists, set `stages.retro.started_at` (ISO now) and refresh `total_duration_ms` (now − pipeline start). Files are SSOT — never rely on conversation history.

## Step 1 — Aggregate

```
mcp__samvil_mcp__aggregate_retro_metrics(
  project_root=".", plugin_root="${CLAUDE_PLUGIN_ROOT:-}",
  suggestion_major=3
)
```

Returns: `metrics.{seed_name,features_*,build_retries,qa_*,interview_questions,
stage_durations_ms,total_duration_ms,bottleneck_stages,build_pass_rate,qa_pass_rate}`,
`recurring_patterns[].{keyword,count,runs}` (≥3 occurrences across history),
`flow_compliance.{planned,actual_sequence,deviations,skipped_stages,matched}`,
`agent_utilization.{tier,tier_total,used,utilization,underutilized}`,
`v3_leaf_stats.{total_leaf_events,by_status,feature_tree_complete}`,
`mcp_health.{exists,total,ok,fail,fail_rate,failed_tools,warning}`,
`next_suggestion_id` (e.g. `v3-031`), `feedback_entries_count`, `errors[]`.
On `error`: report `⚠ MCP unreachable`, fall back to manual file reads
from `SKILL.legacy.md` (P8). Continue — retro is best-effort.

## Step 2 — Render dashboard

Print one console block; skip empty sections:

- **Run summary** — `App / Features N/M passed / Build Retries / QA verdict / Flow Compliance / Agent Utilization`.
- **Bottleneck dashboard** — bar chart from `stage_durations_ms`; mark `bottleneck_stages` with `←`. Total + bottleneck %.
- **QA pass-rate trend** — compare `metrics.qa_verdict` against last 2 entries in `harness-feedback.log` (`feedback_entries_count` for sanity).
- **Recurring patterns** — for each `recurring_patterns[]`, print `keyword (Nx in run-001, run-003, ...)`. Primary input for Step 3.
- **MCP Health** — `Total / OK / Fail / Failed tools`; if `warning: true` (fail_rate > 20%), suggest `bash scripts/setup-mcp.sh`.
- **v3 metrics** (only if `metrics.schema_version` starts with `3.`) — leaf counts + feature_tree_complete rows. v3 seed with zero leaf events → flag REGRESSION (Phase B-Tree didn't fire).

## Step 3 — Generate exactly 3 suggestions

Pick 3 actionable harness improvements targeting `skills/`, `agents/`,
`references/`, or `mcp/`. Drive selection from `recurring_patterns`,
`bottleneck_stages`, `mcp_health.failed_tools`,
`agent_utilization.underutilized`, and v3 regressions.

Schema (`suggestions_v2`, dict only — never legacy string array):

| field | required | notes |
|---|---|---|
| `id` | ✅ | 1st = `next_suggestion_id`; 2nd/3rd = increment NNN |
| `priority` | ✅ | `CRITICAL` (halt) / `HIGH` (≥3-run pattern, ≥50% bottleneck) / `MEDIUM` / `LOW` / `BENEFIT` |
| `component` | ✅ | file path or `mcp:<module>` / `skills/<name>` / `agents/<name>.md` |
| `name`, `problem`, `fix`, `expected_impact` | ✅ | `problem` cites data (`pass_rate=0.6`, `2x QA iter`) |
| `source`, `sprint`, `risk_of_worse` | ⭕ | leave `sprint:""` for triage |

Anti-patterns: blame the user · vague `fix`/missing `component` · inventing IDs (always use `next_suggestion_id`) · writing to legacy `suggestions` (string array, frozen for entries 1-5).

## Step 4 — Append to harness-feedback.log

Locate the log via `feedback_log_path` from Step 1; if empty, fall back to `${CLAUDE_PLUGIN_ROOT}/harness-feedback.log` or `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`. Read, parse JSON array, append one entry:

```json
{"run_id":"samvil-YYYY-MM-DD-NNN","seed_name":"<name>","timestamp":"<ISO>",
 "stages":{"interview":{"questions":N},"build":{"features_attempted":N,
   "features_passed":N,"retries":N},"qa":{"verdict":"PASS|FAIL","iterations":N}},
 "metrics":{"stage_durations_ms":{...},"total_duration_ms":N,
   "build_pass_rate":F,"qa_pass_rate":F,"bottleneck_stages":[...]},
 "suggestions_v2":[ <3 dicts from Step 3> ]}
```

Read-modify-write atomically (never use the Write tool on an existing
log). If the file is missing, create with `[entry]`.

**Resolved cleanup**: for each older entry's `suggestions_v2[]`, if the
`component` file now contains the `fix` keyword (Grep), drop the item
and append `"resolved_in":"v<X.Y.Z> — <summary>"` to that entry. Never
mutate `metrics`, `stages`, `seed_name`, or `timestamp`.

## Step 5 — Pipeline-end Compressor narrate (v3.2 §6.1)

Best-effort one-page briefing. Skip silently on failure (log to `.samvil/mcp-health.jsonl`).

```
mcp__samvil_mcp__narrate_build_prompt(project_root=".", since="")
→ run prompt through current Compressor model (frugal cost_tier;
  route_task(task_role="compressor") picks the model)
mcp__samvil_mcp__narrate_parse(raw="<LLM response>")
→ print under "Pipeline summary" header
mcp__samvil_mcp__claim_post(project_root=".", claim_type="policy_adoption",
  subject="pipeline_end:<seed.name>", statement="run summary recorded",
  authority_file=".samvil/retro/retro-<run_id>.yaml",
  claimed_by="agent:retro-analyst",
  evidence_json='[".samvil/retro/retro-<run_id>.yaml",".samvil/events.jsonl"]')
```

## Chain (terminal)

1. `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="retro_complete", stage="complete", data='{"suggestions_count":3,"features_passed":<N>,"features_failed":<N>}')` — best-effort.
2. Append Retro section to `.samvil/handoff.md`.
3. Print final `[SAMVIL] ✓ Pipeline complete!` + run path. **No chain** — retro is terminal.

## Legacy reference

Full Korean prose, dashboard examples, preset auto-accumulation prompt template, and verbose JSON schema in `SKILL.legacy.md`. Consult only when retro regresses or is extended.
