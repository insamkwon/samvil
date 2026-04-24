#!/usr/bin/env bash
# SAMVIL Hook: Block destructive commands in project directories
# Triggers: PreToolCall on Bash tool
# Purpose: Prevent accidental rm -rf, git reset --hard, etc.

COMMAND="$1"

# Destructive patterns to block
if [[ "$COMMAND" == *"rm -rf /"* ]] || \
   [[ "$COMMAND" == *"rm -rf ~"* ]] || \
   [[ "$COMMAND" == *"rm -rf ."* && "$COMMAND" != *".samvil"* && "$COMMAND" != *".next"* ]] || \
   [[ "$COMMAND" == *"git reset --hard"* ]] || \
   [[ "$COMMAND" == *"git clean -fd"* ]] || \
   [[ "$COMMAND" == *"DROP TABLE"* ]] || \
   [[ "$COMMAND" == *"DROP DATABASE"* ]]; then
  echo "[SAMVIL] 🛑 BLOCKED: Destructive command detected."
  echo "Command: $COMMAND"
  echo "If you really need this, run it manually outside SAMVIL."
  exit 1
fi

exit 0
