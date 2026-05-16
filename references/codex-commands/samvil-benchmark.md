# SAMVIL Benchmark (Codex CLI)

Compare SAMVIL to external AI coding harnesses (Ouroboros, Devin,
OpenDevin, others) and log paradigm gaps to `harness-feedback.log`.
Quarterly run or on user request.

## Prerequisites (optional)

This skill is a *meta* skill — it does not consume a SAMVIL pipeline
chain marker. If invoked mid-pipeline, run `read_chain_marker(project_root="${PWD}")`
to confirm the current stage; if SAMVIL is in the middle of a build,
defer benchmark until pipeline completion.

## Why this exists

SAMVIL's `samvil-retro` only sees *internal* patterns (build failures,
stage durations). Paradigm gaps — what other systems do differently —
only surface from external comparison. This skill is the systematic
version of "the conversation that led to v4.20~v4.25". Without it,
SAMVIL plateaus in its own closed measurement loop.

## Comparison registry (defaults)

| Target | Why | URL |
|---|---|---|
| Ouroboros | Closest sibling architecture | `https://raw.githubusercontent.com/Q00/ouroboros/main/CHANGELOG.md` |
| Devin | Reference autopilot | `https://docs.devin.ai/changelog` |
| OpenDevin | Open competitor | `https://raw.githubusercontent.com/All-Hands-AI/OpenHands/main/CHANGELOG.md` |

User can add custom targets via `~/.samvil/benchmark-targets.json`
(schema: `[{name, url, why}, ...]`).

## Steps

### 1. Fetch latest changelogs

For each target, fetch the CHANGELOG file and extract the latest 3
release sections. Manual approach (Codex):

```bash
curl -s --max-time 5 <url> | head -200 > /tmp/<target>-changelog.md
```

For HTML targets (e.g. Devin), use a markdown extractor or just `curl`
the HTML and ignore tags.

### 2. Identify novel patterns

For each target's latest changes, classify each item:

1. **Already in SAMVIL** → skip (check `references/glossary.md`,
   recent `CHANGELOG.md` entries, `harness-feedback.log` resolved).
2. **Deliberately rejected** → skip (check
   `docs/samvil-v2-roadmap.md §10 Out-of-Scope` and Non-Goals).
3. **Paradigm gap** → log to harness-feedback.

Print comparison table to user before logging.

### 3. Append paradigm gaps to harness-feedback.log

For each item in category 3, append an entry:

```json
{
  "id": "benchmark-<timestamp>-<short_hash>",
  "priority": "BENEFIT",
  "component": "external:<target>",
  "name": "<short pattern name>",
  "problem": "SAMVIL is missing: <description>. cite: <target_changelog_url>",
  "fix": "<rough adaptation sketch>",
  "expected_impact": "<concrete user benefit>",
  "source": "samvil-benchmark"
}
```

`harness-feedback.log` path resolution: project-local → plugin root →
cache. Read-modify-write atomically (never overwrite).

### 4. Summary

Print: `[SAMVIL] Benchmark complete. <N> targets fetched, <M>
paradigm gaps logged.`

If M >= 3: ask the user via standard prompt mechanism whether to
discuss now or defer to next retro.

## Anti-Patterns

1. NEVER auto-implement competitor patterns — they're candidates only.
2. NEVER mark gaps as `CRITICAL` — they're enhancements (`BENEFIT`).
3. NEVER re-log patterns SAMVIL deliberately rejected.
4. Use the standard `ask_user` capability for any question — don't
   embed prompts inline as bash echo.

## Chain

Terminal skill — no chain. Output goes to `harness-feedback.log` for
samvil-retro to consume on the next pipeline run. **Do not call**
`write_chain_marker` for this skill — it lives outside the standard
pipeline flow (no next_skill exists).
