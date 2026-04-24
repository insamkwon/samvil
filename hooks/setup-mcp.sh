#!/usr/bin/env bash
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

# Determine installation state. We DON'T exit early when already installed —
# tool coverage check below must run on every SessionStart (that's the whole
# point of v3-012, to catch drift between expected and exposed tool sets).
NEEDS_INSTALL=1
if [ -f "$MCP_DIR/.venv/bin/python" ]; then
  if "$MCP_DIR/.venv/bin/python" -c "import samvil_mcp" 2>/dev/null; then
    NEEDS_INSTALL=0
  fi
fi

if [ "$NEEDS_INSTALL" = "1" ]; then
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

# v3.1.0 (v3-012) — Tool coverage check at SessionStart
# Compares expected MCP tool set against what the server currently exposes.
# Warn (not fail) if tools are missing so users catch broken installs before
# a skill fails mid-pipeline. Completely silent on match.
if [ -f "$MCP_DIR/.venv/bin/python" ]; then
  "$MCP_DIR/.venv/bin/python" - <<'PYEOF' 2>/dev/null
import sys
try:
    import asyncio
    from samvil_mcp.server import mcp
    tools = {t.name for t in asyncio.run(mcp.list_tools())}
except Exception as e:
    print(f"[SAMVIL] ⚠️ tool coverage check 실패 (import): {e}", file=sys.stderr)
    sys.exit(0)

expected = {
    # v3.0.0 tools
    "next_buildable_leaves", "tree_progress", "update_leaf_status",
    "migrate_seed", "migrate_seed_file",
    "analyze_ac_dependencies",
    "rate_budget_acquire", "rate_budget_release", "rate_budget_stats", "rate_budget_reset",
    "validate_pm_seed", "pm_seed_to_eng_seed",
    # v3.1.0 additions (Sprint 2 + Sprint 6)
    "heartbeat_state", "is_state_stalled",
    "build_reawake_message", "increment_stall_recovery_count",
    "suggest_ac_split",
}
missing = expected - tools
if missing:
    print(f"[SAMVIL] ⚠️ MCP tool coverage: 누락 {len(missing)}/{len(expected)}")
    for name in sorted(missing):
        print(f"  - {name}")
    print("  → /samvil:update 또는 uv pip install -e . 를 실행해 MCP를 최신으로 동기화하세요.")
PYEOF
fi

# ── v3.2 L1 — Contract Layer baseline init + bootstrap claim ────────
# Ensures the project's .samvil/ skeleton exists AND seeds a first
# claim so `.samvil/claims.jsonl` is never empty after /samvil runs.
# This removes the "file doesn't exist" failure mode we hit in the
# Sprint 6 dogfood even when the Pre/PostToolUse hooks don't fire.
# shellcheck source=_contract-helpers.sh
source "$PLUGIN_ROOT/hooks/_contract-helpers.sh" 2>/dev/null
if command -v samvil_contract_find_project_root >/dev/null 2>&1; then
  _samvil_project_root="$(samvil_contract_find_project_root)"
  if [ -n "$_samvil_project_root" ]; then
    samvil_contract_ensure_project_init "$_samvil_project_root"
    # Seed a `pipeline_start` marker only once per session so repeated
    # SessionStart firings don't spam. Idempotency key: ISO date + pid.
    _marker="$_samvil_project_root/.samvil/.session-bootstrap"
    _today="$(date -u +%Y-%m-%d)"
    if [ ! -f "$_marker" ] || ! grep -q "$_today" "$_marker" 2>/dev/null; then
      samvil_contract_append_claim \
        "$_samvil_project_root" \
        "policy_adoption" \
        "pipeline_session_start" \
        "SAMVIL session started on $_today via SessionStart hook" \
        "project.state.json" \
        "agent:orchestrator-agent" \
        '["project.state.json"]' >/dev/null 2>&1
      echo "$_today $$" > "$_marker"
      echo "[samvil-contract] session bootstrap claim seeded at $_samvil_project_root/.samvil/claims.jsonl" >&2
    fi
  fi
fi

exit 0
