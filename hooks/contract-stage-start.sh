#!/bin/bash
# SAMVIL v3.2 L1 — PreToolUse hook for Skill invocations.
#
# Fires when Claude is about to call the Skill tool. If the target skill
# is a SAMVIL pipeline stage (interview / seed / build / qa / etc), we
# post a stage_start claim to .samvil/claims.jsonl deterministically,
# without relying on the skill body to remember.
#
# Args: $1 = $TOOL_INPUT (JSON string with "skill" field)
#
# Best-effort: never hard-fails. Pipeline runs even when this hook breaks.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_contract-helpers.sh
source "$HERE/_contract-helpers.sh"

TOOL_INPUT="${1:-}"

# Tool-name filter at the shell level. Claude Code's plugin.json
# matcher doesn't reliably match "Skill" (hook never fired in our
# v3.2 dogfood run), so we register this hook on all tools and
# filter here. $TOOL_NAME is injected by the plugin runtime.
case "${TOOL_NAME:-}" in
  Skill|Task|mcp__samvil*)
    ;;
  *)
    exit 0
    ;;
esac

# 1. Resolve skill name. No skill name → bail.
SKILL_NAME="$(samvil_contract_extract_skill_name "$TOOL_INPUT")"
[ -z "$SKILL_NAME" ] && exit 0

# 2. Only stage skills produce claims.
samvil_contract_is_stage_skill "$SKILL_NAME" || exit 0

# 3. Find the project root. No root → we're not in a SAMVIL project context.
PROJECT_ROOT="$(samvil_contract_find_project_root)"
[ -z "$PROJECT_ROOT" ] && exit 0

# 4. Ensure .samvil/ baseline is in place.
samvil_contract_ensure_project_init "$PROJECT_ROOT"

# 5. Derive the stage label + posting agent.
STAGE="$(samvil_contract_stage_name "$SKILL_NAME")"
AGENT="$(samvil_contract_primary_agent "$STAGE")"
SUBJECT="stage:$STAGE"
STATEMENT="entered $STAGE stage via hook"
AUTHORITY="project.state.json"

# 6. Append the stage_start claim, capture the claim_id, and bind it to
#    state.json.stage_claims so the post-hook can verify the match.
CLAIM_ID="$(samvil_contract_append_claim \
  "$PROJECT_ROOT" \
  "evidence_posted" \
  "$SUBJECT" \
  "$STATEMENT" \
  "$AUTHORITY" \
  "$AGENT" \
  '["project.state.json"]')"

if [ -n "$CLAIM_ID" ]; then
  samvil_contract_append_stage_claim_to_state "$PROJECT_ROOT" "$STAGE" "$CLAIM_ID"
  echo "[samvil-contract] pre-stage claim posted: $CLAIM_ID ($STAGE)" >&2
fi

exit 0
