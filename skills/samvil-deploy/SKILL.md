---
name: samvil-deploy
description: "Deploy built app to Vercel/Railway/Coolify. Post-QA, pre-retro chain step."
---

# samvil-deploy (ultra-thin)

Deploy a QA-verified app. The QA gate, per-`solution_type` deploy-target
catalog (web-app / dashboard / game / mobile-app / automation), env-var
validation, and build-artifact checks are aggregated by
`mcp__samvil_mcp__evaluate_deploy_target`. Platform shell-out (`vercel`,
`railway`, `coolify`, `eas`, `gh-pages`, `crontab`) stays here — host-bound,
P8 graceful degradation. Full per-platform prose in `SKILL.legacy.md`.

## Boot Sequence (INV-1)

1. Read `project.state.json` + `project.seed.json` + `.env.example`.
2. **v3.2 Contract Layer — stage entry**: `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="deploy_started", stage="deploy", data="{}")`. Best-effort; auto-claims `evidence_posted subject="stage:deploy"`.

## Step 1 — Aggregate readiness

```
mcp__samvil_mcp__evaluate_deploy_target(project_root=".", platform="")
```

Returns: `qa_gate.{verdict,reason,next_action}`, `platforms[]`
`{id,label,command,config_files,notes,recommended?}`, `selected_platform`
(caller arg → seed `tech_stack.deploy` → catalog `recommended`),
`env_vars.{required_keys,placeholder_keys,exists}`, `build_artifact.{checked_paths,present}`,
plus `ready` + `blockers[]`. On `error`: report `⚠ MCP unreachable`, fall
back to manual deploy guidance from `SKILL.legacy.md` (P8).

## Step 2 — Branch on `ready`

**`ready: false`** — print blockers, stop:

- `qa_gate.verdict != "pass"` → refuse. Run `/samvil:samvil-qa` until PASS.
- `env_vars.placeholder_keys` non-empty → AskUserQuestion to fill values.
  Write `.env` / `.env.production`. Never hardcode secrets.
- `build_artifact.present == false` for non-`manual` → `npm run build > .samvil/build.log 2>&1`
  (INV-2), then re-call `evaluate_deploy_target`.

**`ready: true`** — confirm `selected_platform` (silent if seed-pinned).
For a different choice, re-call with `platform="<id>"` to recompute.

## Step 3 — Deploy (host-bound)

```bash
cd ~/dev/<seed.name>
<selected_platform.command>   # substitute <seed.name> in the template
```

Failures: report once, no auto-retry. Per-platform recovery hints
(Vercel cred, Railway nixpacks, Coolify Dockerfile, EAS keystore) live
in `SKILL.legacy.md`.

`automation` deploy is recipe-driven, not a shell binary:

- `cc-skill` → call CronCreate with `seed.core_flow.trigger`.
- `cron` → write `.samvil/crontab-template` (template in `SKILL.legacy.md`),
  tell user `crontab .samvil/crontab-template`.
- `serverless` → generate `serverless.yml` (Python AWS Lambda) or
  `vercel.json` (Node cron), then run the command.
- `manual` → print run command + `.env` reminder.

## Step 4 — Post-deploy

```bash
cat > .samvil/deploy-info.json <<EOF
{"platform":"<id>","url":"<URL or pending>","environment":"production",
 "deployed_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","deploy_time_seconds":<int>}
EOF
```

Edit `project.state.json`: `deploy_status: "deployed"` (or `"skipped"`)
plus URL. Print one report (per-`solution_type` template in
`SKILL.legacy.md`); minimum fields: platform, URL, environment, time.

## Chain (mandatory)

Whether deployed or skipped:

1. Append Deploy section to `.samvil/handoff.md`.
2. Best-effort `mcp__samvil_mcp__save_event(session_id="<session_id>", event_type="deploy_complete", stage="deploy", data='{"status":"<deployed|skipped>"}')`.
3. **Immediately** `Invoke the Skill tool with skill: samvil-retro` — no
   approval pause. Retro is read-only (no P10 irreversibility). Skipping
   breaks harness-feedback; v3.2 dogfood regressed here.

## Anti-Patterns

QA-blocked deploy (gate refuses) · hardcoded secrets in `.env`
(AskUserQuestion instead) · auto-retry on failure (report once, stop) ·
skipping `samvil-retro` chain.

## Legacy reference

Full per-platform Korean prose, EAS pre-deploy checklist, post-deploy
report templates per `solution_type` live in `SKILL.legacy.md`. Consult
only when deploy itself is failing or being extended.
