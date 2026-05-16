---
name: samvil-benchmark
description: "Compare SAMVIL to external AI coding harnesses (Ouroboros, Devin, others) — fetch their changelogs, identify paradigm gaps, append to harness-feedback.log. Manual or quarterly run."
---

# samvil-benchmark (ultra-thin)

Adopt the **Comparative Analyst** role. SAMVIL's retro can spot *internal* patterns (build failures, stage durations) but cannot detect *paradigm* gaps — those only surface from external comparison (W10 from `docs/samvil-v2-roadmap.md`). This skill is the systematic version of "the conversation that led to v4.20~v4.25" — instead of relying on the user noticing a competitor system, run this skill quarterly to detect drift.

## When to invoke

- Manually: `/samvil-benchmark` when the user spotted something interesting in a competitor system.
- Scheduled: every quarter (suggested) when SAMVIL feels stable.
- Triggered: when samvil-retro detects ≥ 3 consecutive runs with no new harness improvements — likely sign of internal-blindness plateau.

## Comparison targets (default registry)

| Target | Why | Fetch URL |
|---|---|---|
| Ouroboros | Closest sibling — same Skill/MCP architecture, different philosophy | `https://raw.githubusercontent.com/Q00/ouroboros/main/CHANGELOG.md` |
| Devin | Reference autopilot system — different audience but useful for execution-mode ideas | `https://docs.devin.ai/changelog` (HTML) |
| OpenDevin | Open competitor — what's the community converging on? | `https://raw.githubusercontent.com/All-Hands-AI/OpenHands/main/CHANGELOG.md` |

User can add custom targets via `~/.samvil/benchmark-targets.json` (schema: `[{name, url, why}, ...]`).

## Step 1 — Load targets + fetch changelogs

`mcp__samvil_mcp__benchmark_load_targets(config_path="")` → `{targets[]}` (defaults + `~/.samvil/benchmark-targets.json` overrides). For each target: `mcp__samvil_mcp__benchmark_fetch_target(url=<target.url>, timeout=5)` → `{ok, items[]}`. Failed fetches surface as `{target, error}` but don't halt — collect what works.

## Step 2 — Classify items

Build `already_have` token list from `references/glossary.md` canonical terms + recent CHANGELOG entries (e.g. `["refine gate", "epic claim", "ac tree", "evaluation principles", "pain capture"]`). Build `rejected` list from `docs/samvil-v2-roadmap.md §Non-Goals` and `§Out-of-Scope` (e.g. `["autopilot", "auto-implement", "AgentRegistry"]`).

For each target's items: `mcp__samvil_mcp__benchmark_classify_items(items_json=<JSON>, already_have_json=<JSON>, rejected_json=<JSON>)` → `{categorized: {already_have, rejected, gaps}, counts}`. Render the comparison table verbatim to user.

## Step 3 — Append paradigm gaps

For each item in `categorized.gaps`: `mcp__samvil_mcp__benchmark_append_gap(gap_json=<JSON>, target_name=<name>, target_url=<url>, feedback_log_path=<path>)`. The MCP wrapper renders the entry (priority=BENEFIT, source=samvil-benchmark, id=benchmark-<ts>-<hash>) and appends atomically with dedup-by-id.

`feedback_log_path` resolution: project-local `harness-feedback.log` → `${CLAUDE_PLUGIN_ROOT}/harness-feedback.log` → `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`.

## Step 4 — Summary + (optional) escalation

Print: `[SAMVIL] Benchmark complete. <N> targets fetched, <M> paradigm gaps logged.`

If `M >= 3`: AskUserQuestion `["3개 이상 paradigm gap 감지됨 — 다음 release 계획 토론?"]` with options `[지금 토론 / 다음 retro에서 / 무시]`. "지금 토론" → render the gap list verbatim for user discussion.

## Anti-Patterns

1. NEVER auto-implement competitor patterns — these are *candidates* for the next planning conversation, not automatic adoptions. Each gap requires user judgment (does it fit SAMVIL's solo-developer / Korean / file-SSOT identity?).
2. NEVER mark gaps as `CRITICAL` — they're enhancements, not bugs. Even if the competitor pattern is genuinely better, SAMVIL shipping without it is not broken.
3. NEVER append to `harness-feedback.log` for patterns SAMVIL deliberately rejected — see `docs/samvil-v2-roadmap.md §Non-Goals` and `§Out-of-Scope`. Re-litigating those wastes retro cycles.
4. **`AskUserQuestion` 호출 포맷**: `questions=["<질문>"]` 배열만 허용; 문자열 직접 전달 시 `InputValidationError`.

## Chain

This is a terminal skill — no chain. Output goes to `harness-feedback.log` for samvil-retro to consume on the next pipeline run.
