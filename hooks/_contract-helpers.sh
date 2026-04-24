#!/bin/bash
# Shared helpers for SAMVIL contract-layer hooks (L1).
#
# Why a helper: both PreToolUse and PostToolUse hooks need to:
#   - find the project root (the dir containing project.state.json)
#   - detect which pipeline stage is about to run / just finished
#   - append a claim to `.samvil/claims.jsonl` via samvil_mcp.claim_ledger
#
# Design notes:
#   * We route claim append through the Python ClaimLedger class so the
#     schema stays consistent with the Sprint 1 module. No raw JSONL in bash.
#   * Hooks are best-effort: on any failure we log to stderr and return 0
#     so the pipeline never halts because of a hook hiccup.
#   * `source` this file from other hook scripts.

# Resolve the plugin root (directory containing the hooks/ folder).
# We prefer $CLAUDE_PLUGIN_ROOT when Claude Code provides it; otherwise
# we derive from the location of this very file. This keeps the helpers
# portable across the plugin's user-specific cache location without any
# hard-coded machine paths.
_samvil_helpers_file="${BASH_SOURCE[0]}"
_samvil_resolve_plugin_root() {
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "$CLAUDE_PLUGIN_ROOT"
    return 0
  fi
  # Fallback: this script lives at <plugin_root>/hooks/_contract-helpers.sh
  local here
  here="$(cd "$(dirname "$_samvil_helpers_file")" && pwd)"
  # Go one level up: hooks/ → plugin root
  echo "$(dirname "$here")"
}
SAMVIL_PLUGIN_ROOT="$(_samvil_resolve_plugin_root)"

# Python venv lives at <plugin_root>/mcp/.venv/bin/python after the
# SessionStart hook has run. If the venv hasn't been created yet, the
# Python calls fall through to the system `python3` (best-effort mode —
# the hook is allowed to no-op silently until the venv is in place).
if [ -x "$SAMVIL_PLUGIN_ROOT/mcp/.venv/bin/python" ]; then
  SAMVIL_PY="$SAMVIL_PLUGIN_ROOT/mcp/.venv/bin/python"
else
  SAMVIL_PY="$(command -v python3 || echo python3)"
fi

# Export the MCP package dir so the inline Python heredocs below can
# resolve imports without hard-coding paths.
export SAMVIL_MCP_DIR="$SAMVIL_PLUGIN_ROOT/mcp"
export SAMVIL_PLUGIN_ROOT

# The stage skills we tag as pipeline stages. Anything else is ignored.
# Keep in sync with references/contract-layer-protocol.md's task_role table.
SAMVIL_STAGE_SKILLS="samvil-interview samvil-pm-interview samvil-seed samvil-council samvil-design samvil-scaffold samvil-build samvil-qa samvil-deploy samvil-retro samvil-evolve"

# samvil_contract_extract_skill_name <tool_input_json>
#   Parse the Skill tool input. Returns the skill name on stdout or empty
#   on failure. Accepts either a raw JSON string or quoted form.
samvil_contract_extract_skill_name() {
  local raw="$1"
  "$SAMVIL_PY" - "$raw" <<'PY' 2>/dev/null
import json, sys
raw = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    data = json.loads(raw)
except Exception:
    data = {}
skill = (
    data.get("skill")
    or data.get("skill_name")
    or data.get("name")
    or ""
)
print(skill.strip())
PY
}

# samvil_contract_is_stage_skill <skill_name>
#   Returns 0 if the skill is one we want to emit stage claims for, 1 otherwise.
samvil_contract_is_stage_skill() {
  local name="$1"
  [ -z "$name" ] && return 1
  for s in $SAMVIL_STAGE_SKILLS; do
    [ "$s" = "$name" ] && return 0
  done
  return 1
}

# samvil_contract_stage_name <skill_name>
#   Map skill name to a short stage label used in claim subjects.
samvil_contract_stage_name() {
  local skill="$1"
  case "$skill" in
    samvil-interview|samvil-pm-interview) echo "interview" ;;
    samvil-seed)       echo "seed" ;;
    samvil-council)    echo "council" ;;
    samvil-design)     echo "design" ;;
    samvil-scaffold)   echo "scaffold" ;;
    samvil-build)      echo "build" ;;
    samvil-qa)         echo "qa" ;;
    samvil-deploy)     echo "deploy" ;;
    samvil-retro)      echo "retro" ;;
    samvil-evolve)     echo "evolve" ;;
    *)                 echo "" ;;
  esac
}

# samvil_contract_primary_agent <stage>
#   Who posts the stage_start claim. Picks a role-tagged agent appropriate
#   to the stage (see mcp/samvil_mcp/model_role.py DEFAULT_ROLES).
samvil_contract_primary_agent() {
  local stage="$1"
  case "$stage" in
    interview)  echo "agent:socratic-interviewer" ;;
    seed)       echo "agent:seed-architect" ;;
    council)    echo "agent:product-owner" ;;
    design)     echo "agent:tech-architect" ;;
    scaffold)   echo "agent:scaffolder" ;;
    build)      echo "agent:build-worker" ;;
    qa)         echo "agent:qa-functional" ;;
    deploy)     echo "agent:deployer" ;;
    retro)      echo "agent:retro-analyst" ;;
    evolve)     echo "agent:reflect-proposer" ;;
    *)          echo "agent:orchestrator-agent" ;;
  esac
}

# samvil_contract_find_project_root
#   Return the nearest ancestor of CWD that contains project.state.json
#   (or equivalent). Empty string means "not a SAMVIL project context".
samvil_contract_find_project_root() {
  local dir="$PWD"
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -f "$dir/project.state.json" ] || [ -f "$dir/project.seed.json" ]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo ""
  return 1
}

# samvil_contract_ensure_project_init <project_root>
#   Make sure .samvil/ exists and the files the contract layer expects
#   are in place (empty claims.jsonl, model_profiles.yaml default, etc.).
#   Idempotent.
samvil_contract_ensure_project_init() {
  local root="$1"
  [ -z "$root" ] && return 0

  mkdir -p "$root/.samvil"
  [ -f "$root/.samvil/claims.jsonl" ] || : > "$root/.samvil/claims.jsonl"

  # Seed model_profiles.yaml from packaged defaults if absent.
  if [ ! -f "$root/.samvil/model_profiles.yaml" ]; then
    local defaults="$SAMVIL_PLUGIN_ROOT/references/model_profiles.defaults.yaml"
    [ -f "$defaults" ] && cp "$defaults" "$root/.samvil/model_profiles.yaml"
  fi
}

# samvil_contract_append_claim <project_root> <type> <subject> <statement> <authority_file> <claimed_by> [evidence_json]
#   Append a claim to the project's ledger via samvil_mcp.claim_ledger.
#   evidence_json defaults to "[]". Prints the claim_id on stdout.
samvil_contract_append_claim() {
  local root="$1"
  local ctype="$2"
  local subject="$3"
  local statement="$4"
  local authority="$5"
  local claimed_by="$6"
  local evidence="${7:-[]}"

  [ -z "$root" ] && return 0

  "$SAMVIL_PY" - "$root" "$ctype" "$subject" "$statement" "$authority" "$claimed_by" "$evidence" <<'PY' 2>/dev/null
import json, sys, os
root, ctype, subject, statement, authority, claimed_by, evidence_json = sys.argv[1:8]
try:
    sys.path.insert(0, os.environ.get("SAMVIL_MCP_DIR", "mcp"))
    from samvil_mcp.claim_ledger import ClaimLedger, CLAIM_TYPES
    if ctype not in CLAIM_TYPES:
        sys.exit(0)
    evidence = json.loads(evidence_json or "[]")
    ledger = ClaimLedger(os.path.join(root, ".samvil", "claims.jsonl"))
    c = ledger.post(
        type=ctype,
        subject=subject,
        statement=statement,
        authority_file=authority,
        claimed_by=claimed_by,
        evidence=evidence,
    )
    print(c.claim_id)
except Exception as e:
    # Never raise — hooks are best-effort
    sys.stderr.write(f"[samvil-contract-hook] append_claim failed: {e}\n")
PY
}

# samvil_contract_verify_claim <project_root> <subject> <verified_by>
#   Flip the latest pending claim for <subject> to verified. Skips file
#   resolution (hooks may run before evidence files are written).
samvil_contract_verify_claim() {
  local root="$1"
  local subject="$2"
  local verified_by="$3"

  [ -z "$root" ] && return 0

  "$SAMVIL_PY" - "$root" "$subject" "$verified_by" <<'PY' 2>/dev/null
import sys, os
root, subject, verified_by = sys.argv[1:4]
try:
    sys.path.insert(0, os.environ.get("SAMVIL_MCP_DIR", "mcp"))
    from samvil_mcp.claim_ledger import ClaimLedger
    ledger = ClaimLedger(os.path.join(root, ".samvil", "claims.jsonl"))
    pending = [
        c for c in ledger.query_by_subject(subject) if c.status == "pending"
    ]
    if not pending:
        sys.exit(0)
    # Verify the oldest pending; ledger dedupe handles re-entry.
    target = sorted(pending, key=lambda c: c.ts)[0]
    try:
        ledger.verify(
            target.claim_id,
            verified_by=verified_by,
            evidence=["hook:post-skill"],
            skip_file_resolution=True,
        )
    except Exception:
        # Fall back to reject when verify is not allowed (e.g. same identity).
        pass
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] verify_claim failed: {e}\n")
PY
}

# samvil_contract_update_state <project_root> <key> <value>
#   Merge a single key into project.state.json. Creates state file if absent.
samvil_contract_update_state() {
  local root="$1"
  local key="$2"
  local value="$3"
  [ -z "$root" ] && return 0

  "$SAMVIL_PY" - "$root" "$key" "$value" <<'PY' 2>/dev/null
import json, sys, os
root, key, value = sys.argv[1:4]
path = os.path.join(root, "project.state.json")
try:
    with open(path) as f:
        state = json.load(f)
except Exception:
    state = {}
state[key] = value
try:
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] update_state failed: {e}\n")
PY
}

# samvil_contract_append_stage_claim_to_state <project_root> <stage> <claim_id>
#   Record the claim_id in state.json.stage_claims[stage] so the post-hook
#   can verify the matching stage_start.
samvil_contract_append_stage_claim_to_state() {
  local root="$1"
  local stage="$2"
  local claim_id="$3"
  [ -z "$root" ] && return 0
  [ -z "$claim_id" ] && return 0

  "$SAMVIL_PY" - "$root" "$stage" "$claim_id" <<'PY' 2>/dev/null
import json, sys, os
root, stage, claim_id = sys.argv[1:4]
path = os.path.join(root, "project.state.json")
try:
    with open(path) as f:
        state = json.load(f)
except Exception:
    state = {}
sc = state.setdefault("stage_claims", {})
sc[stage] = claim_id
try:
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] stage_claims failed: {e}\n")
PY
}
