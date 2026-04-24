# Troubleshooting Codex on SAMVIL v3.2

Covers the "QA on Codex" path from the Sprint 2 exit gate. Because
SAMVIL itself does not make provider calls, most issues surface in the
Claude Code session executing the QA skill, not in SAMVIL core.

## Before you start

- [ ] Codex CLI installed (`codex --version`) or equivalent adapter
      (OpenRouter, direct API) configured in your shell.
- [ ] `OPENAI_API_KEY` (or your provider's key) is present in the
      environment that Claude Code spawns.
- [ ] `.samvil/model_profiles.yaml` lists a `cost_tier: frontier` entry
      with `provider: openai` and `model_id: gpt-5-codex` (or whatever
      id your installation uses).
- [ ] `role_overrides.qa-functional` is either unset (relies on default
      `frontier`) or explicitly set to `frontier`.

## Common failures

### "RoutingError: no profile matches cost_tier=frontier"

Your profiles file has no frontier entry. Either:

1. Copy the defaults:
   ```bash
   cp references/model_profiles.defaults.yaml .samvil/model_profiles.yaml
   ```
2. Or add just the Codex entry:
   ```yaml
   profiles:
     - provider: openai
       model_id: gpt-5-codex
       cost_tier: frontier
       nickname: codex
       max_tokens_out: 16000
   ```

### The QA skill still picks Opus, not Codex

Per the deterministic tie-break rule (routing.py), the **first** profile
in the chosen tier wins. If Opus is listed before Codex and both are
`frontier`, Opus wins.

To force Codex for QA, either:

- Put the Codex profile first under `profiles:` (affects all
  frontier-bound roles).
- Use a per-task override strategy — Sprint 3 will ship a
  `preferred_provider` field on `role_overrides`. In v3.2 the workaround
  is to split profile files per stage, which is documented in the
  Sprint 3 migration notes (to be written in that sprint).

### Codex returns empty / timeout / 503

1. SAMVIL's router only picks the model. The actual invocation happens
   in your skill execution environment. Check that environment's logs
   first (e.g., `~/.codex/logs/`).
2. If the task fails but the downstream gate expects a verdict, the
   failure is a **mechanical failure** per CLAUDE.md K3 — treat it as a
   bug, not a retro observation. Fix infrastructure first.
3. On two consecutive failures, escalation kicks in (already at
   `frontier`, so escalation is a no-op). The router will emit a
   decision with `escalation_depth=2`. The skill then forces a user
   decision per §3.⑥ escalation loop safety.

### "The QA verdict looks wrong even though Codex returned something"

This is a **semantic failure**. The code ran, the output was parsed, but
the content is off. Per K3, this is an observation for retro, not a bug.
Per ①, every verdict is a `claim` with `verified_by != claimed_by` — so
the failure is caught at ledger level before it becomes authoritative.
Investigate with:

```
python3 scripts/view-claims.py --type ac_verdict --subject AC-<id>
```

### Cost spike

Check `scripts/samvil-status.py` — the budget pane (ships fully in
Sprint 6) shows cumulative cost per run. If Codex usage spikes,
temporarily move `qa-functional` to `balanced`:

```yaml
role_overrides:
  qa-functional: balanced
```

Remove the override once you've identified whether the spike was a real
workload change or a runaway escalation loop.

## Sanity check

```bash
# 1. Validate your profiles file.
python3 - <<'PY'
from samvil_mcp.routing import load_profiles, validate_profiles
issues = validate_profiles(load_profiles(".samvil/model_profiles.yaml"))
print("issues:", issues or "none")
PY

# 2. Check what the router picks for build and QA.
python3 - <<'PY'
from samvil_mcp.routing import route_task
print("build:", route_task(task_role="build-worker").to_dict())
print("qa:   ", route_task(task_role="qa-functional").to_dict())
PY
```

If `build.model_id` is Opus and `qa.model_id` is Codex, the Sprint 2
exit-gate scenario is wired up correctly.
