---
name: samvil-doctor
description: "Diagnose SAMVIL MCP, environment, and plugin health"
---

# SAMVIL Doctor — Thin Diagnostic Entry

One-shot environment + MCP health diagnostic. The MCP-side facts are
aggregated by `mcp__samvil_mcp__diagnose_environment`; the rest are
shell facts that must be collected from the host. Full historic check
list lives in `SKILL.legacy.md`.

## Plugin Root

Resolve the plugin root once so this works on any install:

```bash
SAMVIL_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$SAMVIL_ROOT" ]; then
  SAMVIL_ROOT=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
  SAMVIL_ROOT="${SAMVIL_ROOT%/}"
fi
echo "Plugin root: $SAMVIL_ROOT"
```

## Shell Checks (host-bound)

Collect facts that require a real shell. Each command may fail
gracefully (P8); annotate fails as `⚠` in the output.

```bash
node --version           # expect v18+
npm --version            # expect v9+
python3 --version        # expect 3.11+
ls "$SAMVIL_ROOT/mcp/.venv/bin/python3" 2>/dev/null \
  || echo "venv not installed — run /samvil:samvil-update"
bash "$SAMVIL_ROOT/hooks/validate-version-sync.sh"
cd "$SAMVIL_ROOT/mcp" && source .venv/bin/activate \
  && python -m pytest tests/ --tb=no -q
du -sh ~/.samvil 2>/dev/null || true
du -sh "$SAMVIL_ROOT/.samvil" 2>/dev/null || true
du -sh "$PWD/.samvil" 2>/dev/null || true
```

## MCP Gate

Aggregate MCP-side facts in one call:

```
mcp__samvil_mcp__diagnose_environment()
```

Also call `mcp__samvil_mcp__get_health_tier_summary(project_root="<cwd>")` — best-effort. Returns markdown with tier badge (✅/⚠️/🔴).

`diagnose_environment` returns JSON with three sections:

- `mcp_health` — counts + recent failures parsed from
  `~/.samvil/mcp-health.jsonl`. Missing log is treated as zero-state.
- `tool_inventory` — registered tool list + the v3 expected coverage
  set + any missing v3 tools.
- `model_recommendation` — per-stage model recommendation rows.

If the call itself errors, the doctor reports `⚠ MCP unreachable` and
falls back to the shell facts only (P8 graceful degradation).

## Output

Render one report with three sections (Shell / MCP / Models). Each
shell fact gets `✓` on success or `⚠` with the error + one-line fix.
Each MCP datum comes from the tool calls above:

- Tier badge from `get_health_tier_summary` — render as the **first line** of the MCP section.
- `tool_inventory.count` registered tools, v3 coverage
  `len(v3_present)`/`len(v3_expected)`, list `v3_missing` if any.
- `mcp_health.ok_count` ok, `fail_count` fail, last 1-3
  `recent_failures` (tool + truncated error).
- Render `model_recommendation.rows` as a markdown table; cite
  `model_recommendation.reference`.

End with `Summary: <X> checks passed, <Y> warnings`.

## Chain

One-shot. No chain.

## Legacy reference

Full per-section commentary, model-recommendation prose, and the
historic v3 tool heredoc live in `SKILL.legacy.md`. Consult it only
when the diagnostic itself is failing or being extended.
