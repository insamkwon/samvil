#!/bin/bash
# SAMVIL Hook: Validate seed hasn't been modified during build/QA/deploy phases
# Triggers: PreToolCall on Write/Edit tools
# Purpose: Prevent accidental seed modification once the build pipeline has started
# v3: also protects "deploy" stage (samvil-deploy must not mutate seed)

# Get the file being written/edited from the tool input
FILE_PATH="$1"

# Only check if it's a seed file being modified
if [[ "$FILE_PATH" == *"project.seed.json"* ]]; then
  # Check if we're in a stage where the seed is immutable
  STATE_FILE=$(dirname "$FILE_PATH")/project.state.json
  if [ -f "$STATE_FILE" ]; then
    STAGE=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['current_stage'])" 2>/dev/null)
    if [[ "$STAGE" == "build" || "$STAGE" == "qa" || "$STAGE" == "deploy" ]]; then
      echo "[SAMVIL] ⚠️ WARNING: Attempting to modify seed during $STAGE phase."
      echo "Seed is immutable during build/QA/deploy. If you need changes, run samvil:evolve after QA."
      exit 1
    fi
  fi

  # v2: Validate solution_type if present (warn on unknown types, don't block)
  if command -v python3 &>/dev/null; then
    SOLUTION_TYPE=$(python3 -c "
import json, sys
try:
    seed = json.load(open('$FILE_PATH'))
    print(seed.get('solution_type', 'web-app'))
except: sys.exit(1)
" 2>/dev/null)
    if [[ -n "$SOLUTION_TYPE" ]]; then
      VALID_TYPES="web-app automation game mobile-app dashboard"
      if ! echo "$VALID_TYPES" | grep -qw "$SOLUTION_TYPE"; then
        echo "[SAMVIL] ⚠️ WARNING: Unknown solution_type '$SOLUTION_TYPE'. Valid: $VALID_TYPES"
      fi
    fi
  fi
fi

exit 0
