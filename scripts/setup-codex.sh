#!/usr/bin/env bash
# SAMVIL — Codex / OpenCode / Gemini CLI 완전 자동 설치
#
# 한 번 실행으로 모든 설정 완료. 수동 작업 없음.
#
# Usage:
#   bash scripts/setup-codex.sh              # Codex CLI (기본)
#   bash scripts/setup-codex.sh opencode     # OpenCode
#   bash scripts/setup-codex.sh gemini       # Gemini CLI
#   bash scripts/setup-codex.sh all          # 전부

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMVIL_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$SAMVIL_ROOT/mcp"
HOST="${1:-codex}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " SAMVIL 자동 설치 (v$(grep -o '"version": "[^"]*"' "$SAMVIL_ROOT/.claude-plugin/plugin.json" | grep -o '[0-9][^"]*'))"
echo " 대상 호스트: $HOST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1. uv ──────────────────────────────────────────────────────────────
echo ""
echo "[1/5] Python 패키지 매니저(uv) 확인..."
if ! command -v uv &>/dev/null; then
  echo "      설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "❌ uv 자동 설치 실패."
    echo "   https://docs.astral.sh/uv/getting-started/installation/ 에서 수동 설치 후 재실행하세요."
    exit 1
  fi
fi
echo "      ✓ $(uv --version)"

# ── Step 2. MCP venv + package ──────────────────────────────────────────────
echo ""
echo "[2/5] SAMVIL MCP 서버 설치..."
cd "$MCP_DIR"
[ ! -d ".venv" ] && uv venv .venv --quiet
source .venv/bin/activate
uv pip install -e . --quiet

PYTHON_BIN="$MCP_DIR/.venv/bin/python"
if ! "$PYTHON_BIN" -c "import samvil_mcp" 2>/dev/null; then
  echo "❌ MCP 패키지 설치 실패."
  echo "   수동: cd $MCP_DIR && uv pip install -e ."
  exit 1
fi
echo "      ✓ samvil-mcp 패키지 설치 완료"
echo "      ✓ Python: $PYTHON_BIN"

# ── Step 3. Smoke test ───────────────────────────────────────────────────────
echo ""
echo "[3/5] MCP 동작 테스트..."
if "$PYTHON_BIN" -c "
from samvil_mcp.chain_markers import write_chain_marker, read_chain_marker
from samvil_mcp.health_tiers import classify_health
from samvil_mcp.regression_suite import snapshot_generation
" 2>/dev/null; then
  echo "      ✓ 핵심 도구 임포트 PASS"
else
  echo "      ⚠️  임포트 실패 — 설치 후 'samvil-doctor'로 진단하세요"
fi

# ── Step 4. AGENTS.md 전역 설치 ────────────────────────────────────────────
echo ""
echo "[4/5] AGENTS.md 전역 등록..."

_install_agents() {
  local dest_dir="$1"
  local dest="$dest_dir/AGENTS.md"
  mkdir -p "$dest_dir"
  cp "$SAMVIL_ROOT/AGENTS.md" "$dest"
  echo "      ✓ $dest"
}

if [[ "$HOST" == "codex" || "$HOST" == "all" ]]; then
  _install_agents "$HOME/.codex"
fi
if [[ "$HOST" == "opencode" || "$HOST" == "all" ]]; then
  _install_agents "$HOME/.opencode"
fi
if [[ "$HOST" == "gemini" || "$HOST" == "all" ]]; then
  _install_agents "$HOME/.gemini"
fi

# ── Step 5. MCP config 자동 등록 ────────────────────────────────────────────
echo ""
echo "[5/5] 호스트 MCP 설정 자동 등록..."

# ── Codex CLI ────────────────────────────────────────────────────────────────
_setup_codex() {
  local cfg="$HOME/.codex/config.toml"
  mkdir -p "$HOME/.codex"

  if [ -f "$cfg" ] && grep -q "samvil-mcp" "$cfg" 2>/dev/null; then
    echo "      ✓ Codex CLI: 이미 등록됨 ($cfg)"
    return
  fi

  # Append block (file may or may not exist)
  cat >> "$cfg" <<TOML

[mcp_servers.samvil-mcp]
command = "$PYTHON_BIN"
args    = ["-m", "samvil_mcp.server"]
env     = {}
TOML
  echo "      ✓ Codex CLI: $cfg 에 등록 완료"
}

# ── OpenCode ─────────────────────────────────────────────────────────────────
_setup_opencode() {
  local cfg="$HOME/.opencode/config.json"
  mkdir -p "$HOME/.opencode"

  if [ -f "$cfg" ] && grep -q "samvil-mcp" "$cfg" 2>/dev/null; then
    echo "      ✓ OpenCode: 이미 등록됨 ($cfg)"
    return
  fi

  # Write minimal config if file doesn't exist; otherwise use python to merge
  if [ ! -f "$cfg" ]; then
    cat > "$cfg" <<JSON
{
  "mcp": {
    "samvil-mcp": {
      "command": "$PYTHON_BIN",
      "args": ["-m", "samvil_mcp.server"]
    }
  }
}
JSON
  else
    # Merge into existing JSON
    "$PYTHON_BIN" - "$cfg" "$PYTHON_BIN" <<'PY'
import sys, json
cfg_path, python_bin = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    d = json.load(f)
d.setdefault("mcp", {})["samvil-mcp"] = {
    "command": python_bin,
    "args": ["-m", "samvil_mcp.server"]
}
with open(cfg_path, "w") as f:
    json.dump(d, f, indent=2)
PY
  fi
  echo "      ✓ OpenCode: $cfg 에 등록 완료"
}

# ── Gemini CLI ───────────────────────────────────────────────────────────────
_setup_gemini() {
  local cfg="$HOME/.gemini/settings.json"
  mkdir -p "$HOME/.gemini"

  if [ -f "$cfg" ] && grep -q "samvil-mcp" "$cfg" 2>/dev/null; then
    echo "      ✓ Gemini CLI: 이미 등록됨 ($cfg)"
    return
  fi

  if [ ! -f "$cfg" ]; then
    cat > "$cfg" <<JSON
{
  "mcpServers": {
    "samvil-mcp": {
      "command": "$PYTHON_BIN",
      "args": ["-m", "samvil_mcp.server"]
    }
  }
}
JSON
  else
    "$PYTHON_BIN" - "$cfg" "$PYTHON_BIN" <<'PY'
import sys, json
cfg_path, python_bin = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    d = json.load(f)
d.setdefault("mcpServers", {})["samvil-mcp"] = {
    "command": python_bin,
    "args": ["-m", "samvil_mcp.server"]
}
with open(cfg_path, "w") as f:
    json.dump(d, f, indent=2)
PY
  fi
  echo "      ✓ Gemini CLI: $cfg 에 등록 완료"
}

if [[ "$HOST" == "codex"    || "$HOST" == "all" ]]; then _setup_codex;    fi
if [[ "$HOST" == "opencode" || "$HOST" == "all" ]]; then _setup_opencode; fi
if [[ "$HOST" == "gemini"   || "$HOST" == "all" ]]; then _setup_gemini;   fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✅ 설치 완료! 수동 설정 필요 없음"
echo ""
echo " 사용 방법:"
echo "  1. 호스트를 재시작 (또는 새 세션)"
case "$HOST" in
  codex)
    echo "  2. cd ~/dev/my-app && codex \"SAMVIL로 할일 앱 만들어줘\""
    ;;
  opencode)
    echo "  2. cd ~/dev/my-app && opencode \"SAMVIL로 할일 앱 만들어줘\""
    ;;
  gemini)
    echo "  2. cd ~/dev/my-app && gemini \"SAMVIL로 할일 앱 만들어줘\""
    ;;
  all)
    echo "  2. 원하는 호스트에서 'SAMVIL로 할일 앱 만들어줘'"
    ;;
esac
echo ""
echo " 문제 발생 시:"
echo "  python3 $SAMVIL_ROOT/scripts/phase2-cross-host-smoke.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
