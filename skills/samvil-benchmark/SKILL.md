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

## Step 1 — Fetch latest changelogs

For each target in the registry: `WebFetch(url, prompt="Extract the latest 3 release sections — version + date + bullet changes")`. Best-effort; failed fetches surface as `{target, error}` in summary but don't halt.

For Ouroboros specifically (which we recently absorbed v4.20~v4.25 from), also fetch their `skills/` directory listing to detect new skills since last benchmark.

## Step 2 — Identify novel patterns

For each target's latest changes, ask:

1. **Is this a pattern SAMVIL already has?** (search `references/glossary.md`, recent `CHANGELOG.md` entries, `harness-feedback.log` resolved items)
2. **Is this a pattern SAMVIL deliberately rejected?** (check `docs/samvil-v2-roadmap.md §10 Out-of-Scope` and Non-Goals sections — if so, no action)
3. **Is this a paradigm gap?** (new concept that SAMVIL has no equivalent for — e.g. "Refine Gate" was this when we first found it)

Render comparison table:
```
Target          New pattern                          SAMVIL status
─────────────── ──────────────────────────────────── ──────────────────────
ouroboros 0.39  publish-with-templates              gap (G5.1-extended candidate)
devin 1.x       browser-test-fleet                  off-scope (Non-Goal: cloud)
opendevin 0.1   multi-llm-routing                   have it (cost_tier)
```

## Step 3 — Append to harness-feedback.log

For each *paradigm gap* identified (Step 2 category 3), append an issue with:
- `id`: `benchmark-<timestamp>-<short_hash>`
- `priority`: `BENEFIT` (not CRITICAL — these are expansion candidates, not bug fixes)
- `component`: `external:<target>`
- `name`: short pattern name
- `problem`: what SAMVIL is missing (cite target's changelog reference)
- `fix`: rough adaptation sketch (do not commit to full design — that's for the next planning conversation)
- `expected_impact`: concrete user benefit
- `source`: `samvil-benchmark`

The `harness-feedback.log` path resolution follows the standard order: project-local `harness-feedback.log` → `${CLAUDE_PLUGIN_ROOT}/harness-feedback.log` → `~/.claude/plugins/cache/samvil/samvil/*/harness-feedback.log`.

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
