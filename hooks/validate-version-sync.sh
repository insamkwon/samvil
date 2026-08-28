#!/usr/bin/env bash
# validate-version-sync.sh — Ensure all host version files are in sync before push
# Called manually or from CI: ./hooks/validate-version-sync.sh

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_JSON="$PLUGIN_ROOT/.claude-plugin/plugin.json"
CODEX_PLUGIN_JSON="$PLUGIN_ROOT/.codex-plugin/plugin.json"
MCP_INIT="$PLUGIN_ROOT/mcp/samvil_mcp/__init__.py"

# Extract versions
V_PLUGIN=$(python3 -c "import json; print(json.load(open('$PLUGIN_JSON'))['version'])" 2>/dev/null || echo "NOT_FOUND")
V_CODEX_PLUGIN=$(python3 -c "import json; print(json.load(open('$CODEX_PLUGIN_JSON'))['version'])" 2>/dev/null || echo "NOT_FOUND")
V_MCP=$(grep '__version__' "$MCP_INIT" | sed "s/.*=.*['\"]\(.*\)['\"].*/\1/" 2>/dev/null || echo "NOT_FOUND")

echo "=== SAMVIL Version Sync Check ==="
echo "  plugin.json:  $V_PLUGIN"
echo "  codex plugin: $V_CODEX_PLUGIN"
echo "  __init__.py:  $V_MCP"

if [ "$V_PLUGIN" != "$V_CODEX_PLUGIN" ] || [ "$V_PLUGIN" != "$V_MCP" ]; then
  echo ""
  echo "ERROR: Version mismatch!"
  echo "  Fix: synchronize both host manifests and __init__.py to $V_PLUGIN"
  exit 1
fi

# Check README version badge
README="$PLUGIN_ROOT/README.md"
if [ -f "$README" ]; then
  V_README=$(grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' "$README" | head -1 | sed 's/v//')
  if [ -n "$V_README" ] && [ "$V_PLUGIN" != "$V_README" ]; then
    echo ""
    echo "ERROR: README version ($V_README) != plugin.json ($V_PLUGIN)"
    echo "  Fix: Update README.md first version occurrence"
    exit 1
  fi
fi

echo "OK: All versions synchronized ($V_PLUGIN)"
exit 0
