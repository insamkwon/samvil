#!/bin/bash
# SAMVIL Hook: Auto-setup MCP server on SessionStart
# Triggers: SessionStart
# Purpose: Automatically install and register MCP server if not already set up

# Find the plugin cache directory
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"
MCP_DIR="$PLUGIN_ROOT/mcp"

# Skip if MCP dir doesn't exist
if [ ! -d "$MCP_DIR" ]; then
  exit 0
fi

# Skip if already installed (venv exists and samvil_mcp is importable)
if [ -f "$MCP_DIR/.venv/bin/python" ]; then
  "$MCP_DIR/.venv/bin/python" -c "import samvil_mcp" 2>/dev/null && exit 0
fi

# Install uv if not available
if ! command -v uv &>/dev/null; then
  echo "[SAMVIL] uv 설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "[SAMVIL] ⚠️ uv 자동 설치 실패. MCP 없이 기본 모드로 진행합니다."
    exit 0
  fi
  echo "[SAMVIL] ✓ uv 설치 완료"
fi

# Install MCP
echo "[SAMVIL] MCP 서버 자동 설치 중..."
cd "$MCP_DIR"
uv venv .venv 2>/dev/null
source .venv/bin/activate 2>/dev/null
uv pip install -e . 2>/dev/null

if [ $? -eq 0 ]; then
  echo "[SAMVIL] ✓ MCP 서버 설치 완료"
else
  echo "[SAMVIL] ⚠️ MCP 설치 실패. 기본 모드로 진행합니다."
  exit 0
fi

# Register in settings.json if not already there
SETTINGS="$HOME/.claude/settings.json"
PYTHON_PATH="$MCP_DIR/.venv/bin/python"

if [ -f "$SETTINGS" ]; then
  if ! grep -q "samvil-mcp" "$SETTINGS" 2>/dev/null; then
    # Add samvil-mcp to mcpServers using python
    python3 -c "
import json, sys
try:
    with open('$SETTINGS') as f:
        settings = json.load(f)
    if 'mcpServers' not in settings:
        settings['mcpServers'] = {}
    settings['mcpServers']['samvil-mcp'] = {
        'command': '$PYTHON_PATH',
        'args': ['-m', 'samvil_mcp.server'],
        'cwd': '$MCP_DIR'
    }
    with open('$SETTINGS', 'w') as f:
        json.dump(settings, f, indent=2)
    print('[SAMVIL] ✓ MCP 서버가 settings.json에 등록되었습니다.')
    print('[SAMVIL]   다음 세션부터 MCP가 자동으로 활성화됩니다.')
except Exception as e:
    print(f'[SAMVIL] ⚠️ settings.json 등록 실패: {e}')
" 2>/dev/null
  fi
fi

exit 0
