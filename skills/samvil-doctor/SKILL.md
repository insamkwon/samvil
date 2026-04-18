---
name: samvil-doctor
description: "Diagnose SAMVIL MCP, environment, and plugin health"
---

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

```bash
python3 --version
ls /Users/kwondongho/dev/samvil/mcp/.venv/bin/python3
```

Expect: Python 3.11+, venv exists.

### 3. SAMVIL version sync

```bash
cd /Users/kwondongho/dev/samvil
bash hooks/validate-version-sync.sh
```

Expect: All versions synchronized.

### 4. MCP tests

```bash
cd /Users/kwondongho/dev/samvil/mcp
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
du -sh /Users/kwondongho/dev/samvil/.samvil 2>/dev/null || echo "project .samvil not found"
```

### 8. Recent MCP health log

```bash
tail -10 ~/.samvil/mcp-health.jsonl 2>/dev/null || echo "No mcp-health log"
```

## Output Format

```
[SAMVIL Doctor v2.7.0]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Node.js v20.x.x
✓ npm v10.x.x
✓ Python 3.12.x
✓ venv OK
✓ Version sync: 2.7.0
✓ MCP tests: 254 passed
✓ MCP server responsive
✓ Plugin cache: <path> (<N> .py files)
✓ Disk: ~/.samvil <size>
⚠ MCP errors: <count> in last 24h
  - <error details>

Summary: <N> checks passed, <M> warnings
```

If any check fails, report the specific error and suggest fix.
