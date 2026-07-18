#!/usr/bin/env bash
# SAMVIL Hook: block destructive Bash commands before execution.

set -u

TOOL_INPUT="${1:-}"
if [ -z "$TOOL_INPUT" ]; then
  TOOL_INPUT="{}"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[SAMVIL] 🛑 BLOCKED: Cannot inspect Bash command (python3 unavailable)."
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! REASON=$(TOOL_INPUT="$TOOL_INPUT" python3 "$HERE/guard_destructive.py"); then
  echo "[SAMVIL] 🛑 BLOCKED: Cannot inspect Bash command (analyzer failed)."
  exit 1
fi

if [ -n "$REASON" ]; then
  echo "[SAMVIL] 🛑 BLOCKED: Destructive command detected ($REASON)."
  echo "If you really need this, run it manually outside SAMVIL."
  exit 1
fi

exit 0
