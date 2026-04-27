---
name: samvil-scaffold
description: "CLI-based project scaffold. Supports Next.js, Vite+React, Astro, Phaser, Expo, python-script, node-script, cc-skill. No template folder dependency."
---

# samvil-scaffold (ultra-thin)

Adopt the **Scaffolder** role. Stand up a verified, buildable skeleton
via host CLIs (no template folder). Framework selection, CLI catalog,
dependency-matrix lookup, post-install checklist, sanity rules, and
build command per stack are aggregated by
`mcp__samvil_mcp__evaluate_scaffold_target`. Actual `npx`/`npm`/
`python3`/`pip` shell-out stays here — host-bound (P8). Per-framework
prose, literal Tailwind HSL v3 bodies, Phaser scenes, Expo `_layout`,
Python/Node `--dry-run` skeletons in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. Read `project.seed.json` + `project.state.json` + `project.config.json` + `project.blueprint.json` (if present; consume `key_libraries`, `component_structure`).
2. **v3.2 Contract Layer — stage entry**: `mcp__samvil_mcp__save_event(session_id="<sid>", event_type="scaffold_started", stage="scaffold", data="{}")`. Best-effort; auto-claims `evidence_posted subject="stage:scaffold"`.

## Step 1 — Aggregate

```
mcp__samvil_mcp__evaluate_scaffold_target(project_path="~/dev/<seed.name>", framework="", seed_json="", run_sanity_checks=false)
```

Returns `framework` + `framework_source`, `label`, `category` (`web`/
`game`/`mobile`/`automation`), `status` (`stable`/`planned`),
`fallback_framework`, `cli_command` (substituted), `post_install_steps[]`,
`sanity_checks[]` (`{path, required?, must_contain?}`), `build_command`,
`build_log_path`, `version_pins{}`, `env_vars_needed[]`,
`existing_project.{exists,signal,next_action}`, `notes[]`, `blockers[]`.
On `error`: `⚠ MCP unreachable`, fall back to `SKILL.legacy.md` Steps 1–2 (P8).

## Step 2 — Branch

- `existing_project.exists` true (signal: `package.json` / `requirements.txt` / `SKILL.md`): skip full scaffold; install only missing deps from `blueprint.key_libraries` (legacy Step 0 dedup snippet); `mkdir -p .samvil/`; jump to **Step 4**.
- `status == "planned"` (nuxt/sveltekit): print `[SAMVIL] <framework> scaffold is planned but not yet implemented. Falling back to <fallback_framework>.`, re-call with `framework="<fallback_framework>"`.
- Otherwise continue to Step 3.

## Step 3 — Run scaffold (host-bound)

```bash
cd ~/dev
<cli_command>
cd ~/dev/<seed.name>
```

Run each `post_install_steps` entry in order. Literal shadcn/Tailwind
config bodies (HSL v3 for Next.js, v4 native for Vite), Phaser scenes,
Expo `_layout.tsx`/`(tabs)`, Python/Node skeletons, CC-skill template
all in `SKILL.legacy.md` under matching `#### <framework>`. Use
verbatim; never invent file content.

**Tailwind overwrite guard (Next.js)**: `npx shadcn init` rewrites
`app/globals.css` and `tailwind.config.ts` to v4 oklch. After shadcn,
**always** re-write both to HSL v3 bodies (`SKILL.legacy.md` §"Next.js"
(3) and (2)). Step 5 enforces; skipping = QA "no colors" regression.

**Automation**: no `npx create-…`; run `mkdir -p` form, create `src/`
files from `SKILL.legacy.md`. Externalize model IDs through
`.env.example` per `seed.external_api_config.providers` (v3-025).
Hardcoding model literal = `game-asset-gen` runtime-404 regression.

**Pinned versions**: install only `version_pins`. Never `@latest`.

## Step 4 — Build (INV-2, Circuit Breaker)

```bash
cd ~/dev/<seed.name>
<build_command>          # logs to <build_log_path>
echo "Exit code: $?"
```

**Pre-build pin check** (when `version_pins` non-empty): assert each
pin matches `package.json`; on mismatch `npm install <pkg>@<exact>`
(legacy `node -e` snippet).

**PASS**: print `[SAMVIL] Stage 3/5: Scaffold ✓` with project path,
framework label, build status.

**FAIL — MAX_RETRIES=2**: `tail -30 <build_log_path>`, apply per-stack
recovery (`SKILL.legacy.md` §"Step 4"), append fix to `.samvil/fix-log.md`,
retry. Two failures → STOP, report user (P10).

## Step 5 — Sanity Check (Phase A.6, v3.1.0)

```
mcp__samvil_mcp__evaluate_scaffold_target(project_path="~/dev/<seed.name>", run_sanity_checks=true)
```

`sanity_result.all_passed` true: continue. Otherwise per
`sanity_result.failures[]`:
- `must_contain` failure (Tailwind overwrite) → re-write per `SKILL.legacy.md`, re-run Step 5.
- `missing` failure → re-create from `SKILL.legacy.md`.
Cap 2 attempts; second failure → AskUserQuestion (record in retro).

## Step 6 — Persist + Chain

1. Append Scaffold block to `.samvil/handoff.md` via Bash `cat >>` or Edit (never Write tool): include `framework`, `label`, `existing_project.signal`, build status.
2. Best-effort `mcp__samvil_mcp__save_event(event_type="scaffold_complete", stage="build", data='{"framework":"<framework>","build_passed":true}')`.
3. Print `[SAMVIL] Stage 4/5: Building core experience...`, then invoke the Skill tool with `samvil-build`. Codex CLI fallback: read `skills/samvil-build/SKILL.md`.

## Anti-Patterns

1. `@latest` for any package — only `version_pins` (matrix is SSOT).
2. Skipping Tailwind overwrite re-write after `shadcn init` (QA "no colors").
3. Hardcoding external-API model ID (`game-asset-gen` Gemini-404).
4. Business logic in scaffold — components/`src/` skeleton only.
5. Auto-retry past `MAX_RETRIES=2` (Circuit Breaker; P10).
6. Hard-coding next chain target — always invoke `samvil-build`.

## Legacy reference

Full per-framework Korean prose, literal Next.js HSL v3 config bodies,
Phaser/Expo file templates, Python/Node `--dry-run` skeletons, CC-skill
template, `.env.example` provider externalization recipe, build-log
recovery table, per-`solution_type` Output Format blocks in
`SKILL.legacy.md`. Consult when scaffold is failing or extended for a new framework.
