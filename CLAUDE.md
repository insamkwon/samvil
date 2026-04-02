# SAMVIL — AI Vibe-Coding Harness

> "Shape it on the anvil, root it like ginseng."

## What is this?

SAMVIL is a CC Plugin that generates full web applications from a one-line prompt.

```
/samvil "task management SaaS"
  → Interview → Seed → Scaffold → Build → QA → Retro
```

## Architectural Invariants

Every skill in this plugin MUST obey these 4 rules:

1. **INV-1: File is SSOT** — Read seed.json + state.json from disk before any work. Never rely on conversation context.
2. **INV-2: Build logs to files** — `npm run build > .samvil/build.log 2>&1`. Only read on error.
3. **INV-3: Interview to file** — Interview summary saved to `interview-summary.md`. Seed reads this file.
4. **INV-4: Chain pattern** — Each skill invokes the next via Skill tool. State.json enables recovery if chain breaks.

## Key Rules

1. **Seed is SSOT** — Every stage reads project.seed.json before acting
2. **Build must never break** — npm run build must pass after every change
3. **Circuit Breaker** — MAX_RETRIES=2 for build failures, then stop and report
4. **User Checkpoints** — No stage proceeds without user approval
5. **Context Kernel** — seed.json + state.json + blueprint.json + decisions.log

## Target Output

Next.js 14 + Tailwind CSS + TypeScript + App Router
