#!/bin/bash
# SAMVIL Hook: Log build results for retro analysis
# Triggers: PostToolCall on Bash tool (when npm run build is detected)
# Purpose: Accumulate build metrics with timing, error categorization, and log path

COMMAND="$1"
EXIT_CODE="$2"
BUILD_OUTPUT="$3"  # Optional: piped build output for error analysis

# Only track npm run build commands
if [[ "$COMMAND" == *"npm run build"* ]]; then
  PROJECT_DIR=$(pwd)
  SAMVIL_DIR="$PROJECT_DIR/.samvil"

  if [ -d "$SAMVIL_DIR" ]; then
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    BUILD_LOG_PATH="$SAMVIL_DIR/build.log"

    # --- Build timing ---
    # Calculate duration from build.log if it exists and has start marker
    BUILD_START=""
    BUILD_END=""
    DURATION_SEC=0

    if [ -f "$SAMVIL_DIR/.build-start-time" ]; then
      BUILD_START=$(cat "$SAMVIL_DIR/.build-start-time" 2>/dev/null)
      BUILD_END="$TIMESTAMP"
      if command -v python3 &>/dev/null && [ -n "$BUILD_START" ]; then
        DURATION_SEC=$(python3 -c "
from datetime import datetime
try:
    s = datetime.fromisoformat('$BUILD_START'.replace('Z','+00:00'))
    e = datetime.fromisoformat('$BUILD_END'.replace('Z','+00:00'))
    print(int((e - s).total_seconds()))
except:
    print(0)
" 2>/dev/null || echo 0)
      fi
      rm -f "$SAMVIL_DIR/.build-start-time"
    fi

    # --- Error categorization ---
    ERROR_CATEGORY="none"
    ERROR_SUMMARY=""

    if [ "$EXIT_CODE" -ne 0 ]; then
      # Read build log for error classification
      LOG_CONTENT=""
      if [ -f "$BUILD_LOG_PATH" ]; then
        LOG_CONTENT=$(cat "$BUILD_LOG_PATH" 2>/dev/null)
      elif [ -n "$BUILD_OUTPUT" ]; then
        LOG_CONTENT="$BUILD_OUTPUT"
      fi

      if [ -n "$LOG_CONTENT" ]; then
        # Count error types
        TYPE_ERRORS=$(echo "$LOG_CONTENT" | grep -ciE "Type error|TS[0-9]{4}:|error TS" 2>/dev/null || echo 0)
        LINT_ERRORS=$(echo "$LOG_CONTENT" | grep -ciE "eslint|Linting|lint error" 2>/dev/null || echo 0)
        IMPORT_ERRORS=$(echo "$LOG_CONTENT" | grep -ciE "Cannot find module|Module not found|import.*error|Could not resolve" 2>/dev/null || echo 0)
        CONFIG_ERRORS=$(echo "$LOG_CONTENT" | grep -ciE "config|Configuration error|Invalid.*option|next\.config" 2>/dev/null || echo 0)

        # Determine primary error category (first match wins, ordered by specificity)
        if [ "$TYPE_ERRORS" -gt 0 ]; then
          ERROR_CATEGORY="type_error"
          ERROR_SUMMARY="${TYPE_ERRORS} type error(s)"
        elif [ "$IMPORT_ERRORS" -gt 0 ]; then
          ERROR_CATEGORY="import_error"
          ERROR_SUMMARY="${IMPORT_ERRORS} import error(s)"
        elif [ "$LINT_ERRORS" -gt 0 ]; then
          ERROR_CATEGORY="lint_error"
          ERROR_SUMMARY="${LINT_ERRORS} lint error(s)"
        elif [ "$CONFIG_ERRORS" -gt 0 ]; then
          ERROR_CATEGORY="config_error"
          ERROR_SUMMARY="${CONFIG_ERRORS} config error(s)"
        else
          ERROR_CATEGORY="other"
          ERROR_SUMMARY="unclassified error"
        fi
      else
        ERROR_CATEGORY="other"
        ERROR_SUMMARY="no log available"
      fi
    fi

    # --- Build JSON payload ---
    # Use printf for safe JSON construction (handles empty vars)
    BUILD_LOG_RELATIVE=""
    if [ -f "$BUILD_LOG_PATH" ]; then
      BUILD_LOG_RELATIVE=".samvil/build.log"
    fi

    printf '{"timestamp":"%s","command":"build","exit_code":%d,"duration_sec":%d,"error_category":"%s","error_summary":"%s","build_log":"%s"' \
      "$TIMESTAMP" "$EXIT_CODE" "$DURATION_SEC" "$ERROR_CATEGORY" "$ERROR_SUMMARY" "$BUILD_LOG_RELATIVE" \
      >> "$SAMVIL_DIR/build-metrics.jsonl"
    echo "" >> "$SAMVIL_DIR/build-metrics.jsonl"
  fi
fi

exit 0
