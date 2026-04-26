---
name: samvil-doctor-legacy
description: "Legacy SAMVIL doctor (T3.1 backup)"
---

> **Legacy version (T3.1 backup).** Preserved for rollback. The new ultra-thin
> entry is `SKILL.md`. If migration breaks behavior, this file documents the
> exact behavior to restore.

# SAMVIL Doctor

환경과 MCP 서버 건강 진단 one-shot. 실행 즉시 결과 출력.

## Process

### 1. Node.js + npm

```bash
node --version
npm --version
```

Expect: Node v18+, npm v9+.

### 2. Python + venv

First resolve the plugin root dynamically so this diagnostic works on
any install (local `directory:` source or `~/.claude/plugins/cache/...`):

```bash
# Try $CLAUDE_PLUGIN_ROOT first (set when hooks run); otherwise search cache.
SAMVIL_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$SAMVIL_ROOT" ]; then
  SAMVIL_ROOT=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
  SAMVIL_ROOT="${SAMVIL_ROOT%/}"
fi
echo "Plugin root: $SAMVIL_ROOT"

python3 --version
ls "$SAMVIL_ROOT/mcp/.venv/bin/python3" 2>/dev/null || echo "venv not installed — run /samvil:update or let SessionStart hook initialize"
```

Expect: Python 3.11+, venv exists.

### 3. SAMVIL version sync

```bash
bash "$SAMVIL_ROOT/hooks/validate-version-sync.sh"
```

Expect: All versions synchronized.

### 4. MCP tests

```bash
cd "$SAMVIL_ROOT/mcp"
source .venv/bin/activate
python -m pytest tests/ --tb=no -q
```

Expect: All tests pass.

### 5. MCP server responsiveness

Try calling any MCP tool:
```
mcp__samvil_mcp__session_status(session_id="doctor-check")
```

If returns valid JSON (even "not found") → server responsive.

### 6. Plugin cache

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
echo "Cache: $CACHE"
ls "$CACHE/mcp/samvil_mcp/"*.py 2>/dev/null | wc -l
ls "$CACHE/skills/" 2>/dev/null
```

Expect: Cache dir exists, .py files present.

### 7. Disk usage

```bash
du -sh ~/.samvil 2>/dev/null || echo "~/.samvil not found"
du -sh "$SAMVIL_ROOT/.samvil" 2>/dev/null || echo "plugin .samvil not found"
# User's current working project (where /samvil was invoked) — optional:
du -sh "$PWD/.samvil" 2>/dev/null || true
```

### 8. Recent MCP health log

```bash
tail -10 ~/.samvil/mcp-health.jsonl 2>/dev/null || echo "No mcp-health log"
```

### 9. v3.0.0 tool coverage

Verify every v3 tool is registered on the server (not just the 9 core
tools that older doctor versions checked):

```bash
cd "$SAMVIL_ROOT/mcp" && source .venv/bin/activate && python3 -c "
from samvil_mcp.server import mcp
import asyncio
tools = {t.name for t in asyncio.run(mcp.list_tools())}
expected = {
  'next_buildable_leaves','tree_progress','update_leaf_status',
  'migrate_seed','migrate_seed_file',
  'analyze_ac_dependencies',
  'rate_budget_acquire','rate_budget_release','rate_budget_stats','rate_budget_reset',
  'validate_pm_seed','pm_seed_to_eng_seed',
}
missing = expected - tools
print('v3 tools present:', len(expected - missing), '/', len(expected))
if missing: print('MISSING:', sorted(missing))
"
```

Expect: `v3 tools present: 12 / 12`, no `MISSING:` line.

### 10. Model recommendation (v3.1.0, v3-020 + v3-018)

Detect the main session model when possible and print per-stage guidance:

```
[SAMVIL Doctor] Model recommendation
  Main session: <detected or 'unknown'>

  Stage         | Recommended     | Cost tier | Notes
  ------------- | --------------- | --------- | ------------------------------
  Interview     | Opus / Sonnet   | high      | Or GLM-5.1 (cost-aware)
  Seed          | Sonnet          | med       | JSON schema precision
  Council R1    | Haiku 4.5       | low       | Research breadth
  Council R2    | Sonnet          | med       | Judgement
  Design        | Sonnet          | med       | ⚡ 6x+ faster than GLM
  Scaffold      | Sonnet / GLM    | low       | File generation
  Build worker  | Sonnet          | med       | AC leaf implementation
  QA            | Sonnet          | med       | Playwright integration
  Evolve c1     | Haiku           | low       | Wonder analysis
  Evolve c2+    | Sonnet          | med       | Reflect depth
  Retro         | Haiku           | low       | Aggregation

  ⚡ Measured: Sonnet completed Design in 4m 18s vs GLM 25m+ stall
     (vampire-survivors dogfood, 2026-04-19). See references/cost-aware-mode.md.

  For cost-aware setup (70% cheaper, ~same quality):
  see references/cost-aware-mode.md §2b.
```

If main session model is detected as something other than Claude, also print:

```
  ⚠ Untested-main-model warning: <model>
    Falling back to defensive patterns (v3-017).
    Known: heartbeat + reawake active to recover from stalls.
```

## Output Format

```
[SAMVIL Doctor v3.0.0]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Node.js v20.x.x
✓ npm v10.x.x
✓ Python 3.12.x
✓ venv OK
✓ Version sync: 3.0.0
✓ MCP tests: 340 passed
✓ MCP server responsive
✓ Plugin cache: <path> (<N> .py files)
✓ Disk: ~/.samvil <size>
✓ v3 tools: 12 / 12 registered
⚠ MCP errors: <count> in last 24h
  - <error details>

Summary: <N> checks passed, <M> warnings
```

If any check fails, report the specific error and suggest fix.
