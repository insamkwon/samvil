#!/usr/bin/env bash
# SAMVIL — Codex / OpenCode / Gemini CLI Setup
#
# Installs the SAMVIL MCP server and writes a host-specific config snippet.
#
# Usage:
#   bash scripts/setup-codex.sh              # auto-detect host
#   bash scripts/setup-codex.sh codex        # Codex CLI
#   bash scripts/setup-codex.sh opencode     # OpenCode
#   bash scripts/setup-codex.sh gemini       # Gemini CLI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMVIL_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$SAMVIL_ROOT/mcp"
HOST="${1:-auto}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " SAMVIL MCP Setup"
echo " SAMVIL root : $SAMVIL_ROOT"
echo " Host target : $HOST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Ensure uv ────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "[1/4] uv 설치 중..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "❌ uv 자동 설치 실패. https://docs.astral.sh/uv/ 에서 수동으로 설치 후 재실행하세요."
    exit 1
  fi
  echo "   ✓ uv 설치 완료"
else
  echo "[1/4] uv 이미 설치됨 ($(uv --version))"
fi

# ── 2. Install MCP venv ─────────────────────────────────────────────────────
echo "[2/4] SAMVIL MCP 서버 설치 중..."
cd "$MCP_DIR"

if [ ! -d ".venv" ]; then
  uv venv .venv
fi

source .venv/bin/activate
uv pip install -e . --quiet

PYTHON_BIN="$MCP_DIR/.venv/bin/python"
if ! "$PYTHON_BIN" -c "import samvil_mcp" 2>/dev/null; then
  echo "❌ MCP 설치 실패. $MCP_DIR 에서 수동으로 'uv pip install -e .' 실행해주세요."
  exit 1
fi
echo "   ✓ samvil-mcp 설치 완료"

# ── 3. Verify smoke test ────────────────────────────────────────────────────
echo "[3/4] MCP 임포트 테스트 중..."
cd "$SAMVIL_ROOT"
if "$PYTHON_BIN" -c "
from samvil_mcp.chain_markers import write_chain_marker, read_chain_marker
from samvil_mcp.health_tiers import classify_health
print('OK')
" 2>/dev/null; then
  echo "   ✓ MCP 임포트 테스트 PASS"
else
  echo "   ⚠️  임포트 테스트 실패 — MCP 설치를 다시 확인하세요"
fi

# ── 4. Print host-specific config ───────────────────────────────────────────
echo ""
echo "[4/4] 호스트별 설정 안내"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Codex CLI ──────────────────────────────────────────────────────────────────
if [[ "$HOST" == "auto" || "$HOST" == "codex" ]]; then
  CODEX_CFG="$HOME/.codex/config.toml"
  echo ""
  echo "【Codex CLI】"
  echo ""
  echo "  ~/.codex/config.toml 에 아래 블록을 추가하세요:"
  echo ""
  cat <<TOML
  ┌─────────────────────────────────────────────────────────
  │ [mcp_servers.samvil-mcp]
  │ command = "$PYTHON_BIN"
  │ args    = ["-m", "samvil_mcp.server"]
  │ env     = {}
  └─────────────────────────────────────────────────────────
TOML

  # Auto-apply if config exists and doesn't have samvil-mcp yet
  if [ -f "$CODEX_CFG" ] && ! grep -q "samvil-mcp" "$CODEX_CFG" 2>/dev/null; then
    cat >> "$CODEX_CFG" <<TOML

[mcp_servers.samvil-mcp]
command = "$PYTHON_BIN"
args    = ["-m", "samvil_mcp.server"]
env     = {}
TOML
    echo "   ✓ $CODEX_CFG 에 자동 추가됨"
  elif [ -f "$CODEX_CFG" ] && grep -q "samvil-mcp" "$CODEX_CFG" 2>/dev/null; then
    echo "   ✓ 이미 설정되어 있음"
  else
    echo "   ℹ️  $CODEX_CFG 없음 — 위 내용으로 직접 파일을 만드세요."
    echo "      mkdir -p ~/.codex && cat >> ~/.codex/config.toml << 'EOF'"
    echo "      [mcp_servers.samvil-mcp]"
    echo "      command = \"$PYTHON_BIN\""
    echo "      args    = [\"-m\", \"samvil_mcp.server\"]"
    echo "      env     = {}"
    echo "      EOF"
  fi

  echo ""
  echo "  사용 방법:"
  echo "    cd <프로젝트 폴더>"
  echo "    codex \"SAMVIL로 할일 관리 앱 만들어줘\""
  echo "    (AGENTS.md 가 있으면 Codex가 자동으로 파이프라인을 시작합니다)"
fi

# OpenCode ───────────────────────────────────────────────────────────────────
if [[ "$HOST" == "auto" || "$HOST" == "opencode" ]]; then
  echo ""
  echo "【OpenCode】"
  echo ""
  echo "  .opencode/config.json (프로젝트 루트 또는 ~/) 에 추가:"
  echo ""
  cat <<JSON
  ┌─────────────────────────────────────────────────────────
  │ {
  │   "mcp": {
  │     "samvil-mcp": {
  │       "command": "$PYTHON_BIN",
  │       "args": ["-m", "samvil_mcp.server"]
  │     }
  │   }
  │ }
  └─────────────────────────────────────────────────────────
JSON
fi

# Gemini CLI ─────────────────────────────────────────────────────────────────
if [[ "$HOST" == "auto" || "$HOST" == "gemini" ]]; then
  echo ""
  echo "【Gemini CLI】"
  echo ""
  echo "  ~/.gemini/settings.json 에 추가:"
  echo ""
  cat <<JSON
  ┌─────────────────────────────────────────────────────────
  │ {
  │   "mcpServers": {
  │     "samvil-mcp": {
  │       "command": "$PYTHON_BIN",
  │       "args": ["-m", "samvil_mcp.server"]
  │     }
  │   }
  │ }
  └─────────────────────────────────────────────────────────
JSON
  echo ""
  echo "  TOML 커맨드 파일 위치: references/gemini-commands/*.toml"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 설치 완료!"
echo ""
echo " 다음 단계:"
echo "  1. 위 MCP 설정을 호스트 config에 추가 (이미 완료된 경우 스킵)"
echo "  2. 호스트를 재시작하거나 새 세션 열기"
echo "  3. 프로젝트 폴더에서 SAMVIL 파이프라인 시작"
echo ""
echo " 확인:"
echo "  python3 scripts/host-continuation-smoke.py <프로젝트 폴더>"
echo "  python3 scripts/phase2-cross-host-smoke.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
