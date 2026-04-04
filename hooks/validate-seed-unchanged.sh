#!/bin/bash
# SAMVIL Hook: Validate seed hasn't been modified during build/QA phases
# Triggers: PreToolCall on Write/Edit tools
# Purpose: Prevent accidental seed modification during build

# Get the file being written/edited from the tool input
FILE_PATH="$1"

# Only check if it's a seed file being modified
if [[ "$FILE_PATH" == *"project.seed.json"* ]]; then
  # Check if we're in build or QA phase
  STATE_FILE=$(dirname "$FILE_PATH")/project.state.json
  if [ -f "$STATE_FILE" ]; then
    STAGE=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['current_stage'])" 2>/dev/null)
    if [[ "$STAGE" == "build" || "$STAGE" == "qa" ]]; then
      echo "[SAMVIL] ⚠️ WARNING: Attempting to modify seed during $STAGE phase."
      echo "Seed is immutable during build/QA. If you need changes, run samvil:evolve after QA."
      exit 1
    fi
  fi
fi

exit 0
