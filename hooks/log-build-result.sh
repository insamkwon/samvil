#!/bin/bash
# SAMVIL Hook: Log build results for retro analysis
# Triggers: PostToolCall on Bash tool (when npm run build is detected)
# Purpose: Accumulate build metrics for retro-analyst

COMMAND="$1"
EXIT_CODE="$2"

# Only track npm run build commands
if [[ "$COMMAND" == *"npm run build"* ]]; then
  # Find the project's .samvil directory
  PROJECT_DIR=$(pwd)
  SAMVIL_DIR="$PROJECT_DIR/.samvil"

  if [ -d "$SAMVIL_DIR" ]; then
    # Append build result to metrics log
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "{\"timestamp\":\"$TIMESTAMP\",\"command\":\"build\",\"exit_code\":$EXIT_CODE}" >> "$SAMVIL_DIR/build-metrics.jsonl"
  fi
fi

exit 0
