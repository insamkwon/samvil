#!/usr/bin/env bash
# SAMVIL Pre-build Check
# Runs TypeScript type check and ESLint before full build
# Returns: 0 = pass, 1 = type errors, 2 = lint errors, 3 = both
# Output: .samvil/pre-build-result.json with detailed results

set -euo pipefail

PROJECT_DIR=$(pwd)
SAMVIL_DIR="$PROJECT_DIR/.samvil"
RESULT_FILE="$SAMVIL_DIR/pre-build-result.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Ensure .samvil directory exists
mkdir -p "$SAMVIL_DIR"

# --- TypeScript type check ---
TYPE_EXIT=0
TYPE_OUTPUT=""
TYPE_ERROR_COUNT=0

if [ -f "tsconfig.json" ]; then
  TYPE_OUTPUT=$(npx tsc --noEmit 2>&1) || TYPE_EXIT=$?
  if [ "$TYPE_EXIT" -ne 0 ]; then
    TYPE_ERROR_COUNT=$(echo "$TYPE_OUTPUT" | grep -cE "error TS[0-9]+" 2>/dev/null || echo 0)
    # Cap at reasonable count for JSON safety
    if [ "$TYPE_ERROR_COUNT" -gt 500 ]; then
      TYPE_ERROR_COUNT=500
    fi
  fi
else
  # No tsconfig — skip type check
  TYPE_EXIT=0
  TYPE_OUTPUT="skipped: no tsconfig.json"
fi

# --- ESLint check ---
LINT_EXIT=0
LINT_OUTPUT=""
LINT_ERROR_COUNT=0
LINT_WARNING_COUNT=0

if [ -f ".eslintrc" ] || [ -f ".eslintrc.js" ] || [ -f ".eslintrc.json" ] || [ -f ".eslintrc.mjs" ] || [ -f "eslint.config.js" ] || [ -f "eslint.config.mjs" ]; then
  LINT_OUTPUT=$(npx eslint . --max-warnings 0 2>&1) || LINT_EXIT=$?
  if [ "$LINT_EXIT" -ne 0 ]; then
    LINT_ERROR_COUNT=$(echo "$LINT_OUTPUT" | grep -cE "^[[:space:]]*[0-9]+:[0-9]+[[:space:]]+error" 2>/dev/null || echo 0)
    LINT_WARNING_COUNT=$(echo "$LINT_OUTPUT" | grep -cE "^[[:space:]]*[0-9]+:[0-9]+[[:space:]]+warning" 2>/dev/null || echo 0)
  fi
else
  # No eslint config — skip lint check
  LINT_EXIT=0
  LINT_OUTPUT="skipped: no eslint config"
fi

# --- Determine overall result ---
OVERALL_EXIT=0
if [ "$TYPE_EXIT" -ne 0 ] && [ "$LINT_EXIT" -ne 0 ]; then
  OVERALL_EXIT=3
elif [ "$TYPE_EXIT" -ne 0 ]; then
  OVERALL_EXIT=1
elif [ "$LINT_EXIT" -ne 0 ]; then
  OVERALL_EXIT=2
fi

# --- Determine status string ---
STATUS="pass"
if [ "$OVERALL_EXIT" -eq 1 ]; then
  STATUS="type_errors"
elif [ "$OVERALL_EXIT" -eq 2 ]; then
  STATUS="lint_errors"
elif [ "$OVERALL_EXIT" -eq 3 ]; then
  STATUS="type_and_lint_errors"
fi

# --- Extract error snippets (first 10 lines) for summary ---
TYPE_SUMMARY=""
if [ "$TYPE_EXIT" -ne 0 ]; then
  TYPE_SUMMARY=$(echo "$TYPE_OUTPUT" | grep -E "error TS[0-9]+" | head -10 | sed 's/"/\\"/g' | sed 's/$/\\n/' | tr -d '\n' | sed 's/\\n$//')
fi

LINT_SUMMARY=""
if [ "$LINT_EXIT" -ne 0 ]; then
  LINT_SUMMARY=$(echo "$LINT_OUTPUT" | grep -E "(error|warning)" | head -10 | sed 's/"/\\"/g' | sed 's/$/\\n/' | tr -d '\n' | sed 's/\\n$//')
fi

# --- Write result JSON ---
cat > "$RESULT_FILE" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "status": "$STATUS",
  "exit_code": $OVERALL_EXIT,
  "typecheck": {
    "passed": $([ "$TYPE_EXIT" -eq 0 ] && echo "true" || echo "false"),
    "error_count": $TYPE_ERROR_COUNT
  },
  "eslint": {
    "passed": $([ "$LINT_EXIT" -eq 0 ] && echo "true" || echo "false"),
    "error_count": $LINT_ERROR_COUNT,
    "warning_count": $LINT_WARNING_COUNT
  }
}
EOF

# --- Print human-readable summary ---
if [ "$OVERALL_EXIT" -eq 0 ]; then
  echo "Pre-build check PASSED"
else
  echo "Pre-build check FAILED (exit: $OVERALL_EXIT)"
  if [ "$TYPE_EXIT" -ne 0 ]; then
    echo "  TypeScript: $TYPE_ERROR_COUNT error(s)"
    echo "$TYPE_OUTPUT" | grep -E "error TS[0-9]+" | head -5 | while IFS= read -r line; do
      echo "    $line"
    done
  fi
  if [ "$LINT_EXIT" -ne 0 ]; then
    echo "  ESLint: $LINT_ERROR_COUNT error(s), $LINT_WARNING_COUNT warning(s)"
    echo "$LINT_OUTPUT" | grep -E "(error|warning)" | head -5 | while IFS= read -r line; do
      echo "    $line"
    done
  fi
  echo ""
  echo "Result saved to: .samvil/pre-build-result.json"
fi

exit $OVERALL_EXIT
