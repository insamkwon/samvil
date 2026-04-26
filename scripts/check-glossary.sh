#!/usr/bin/env bash
# SAMVIL v3.2 glossary enforcement (⑪).
#
# Scans the repo for banned term usages listed in references/glossary.md.
# Fails CI if any occurrence is found outside of allowlisted contexts.
#
# Contexts where a banned term is tolerated:
#   - references/glossary.md itself (the source of truth)
#   - references/migration-v3.1-to-v3.2.md (rename history)
#   - HANDOFF-v3.2-*.md (design-phase decision records)
#   - ~/docs/ouroboros-absorb/* (reference handoff material)
#   - lines annotated with "glossary-allow"
#   - historical changelog entries in CLAUDE.md / README.md
#     (they describe v3.1; new content must use the new name)
#   - upstream MCP SDK classes (ToolManager._tools etc.) — not our code
#
# Exit code: 0 green, 1 violation found.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Banned pattern → friendly message + replacement hint.
declare -a CHECKS=(
  "\\bmodel_tier\\b|collides with samvil_tier — use cost_tier"
  "\\binterview_depth\\b|renamed to interview_level"
  "L2[[:space:]]+Standard|use interview_level.normal"
  "\\bagent_tier\\b|split into cost_tier (model) vs samvil_tier (pipeline)"
  "\\bevidence[[:space:]]+claim\\b|reserve 'claim' for ledger entries"
)

# Evolve "5 gates" has historical entries in CLAUDE.md/README.md (v3.1
# changelog). We flag it only in NEW artifacts: skills/, agents/, mcp/,
# references/ (excluding explicit allow-list).
EVOLVE_GATE_PATHS=("mcp/" "skills/" "agents/")
EVOLVE_GATE_ALLOW_REGEX='(convergence_check.py|evolve-protocol.md|glossary.md)'

VIOLATIONS=0

scan() {
  local pattern="$1"
  local hint="$2"
  # Use --include / --exclude-dir to avoid scanning caches, venvs, and the
  # design handoffs.
  local hits
  hits=$(grep -RInE "$pattern" . \
      --include='*.py' --include='*.md' --include='*.sh' \
      --include='*.json' --include='*.yaml' --include='*.yml' \
      --exclude-dir='.git' --exclude-dir='.venv' \
      --exclude-dir='node_modules' --exclude-dir='__pycache__' \
      --exclude-dir='.samvil' \
      2>/dev/null \
      | grep -v 'glossary-allow' \
      | grep -v 'references/glossary.md' \
      | grep -v 'references/migration-v3.1-to-v3.2.md' \
      | grep -v 'HANDOFF-v3' \
      || true)
  if [[ -n "$hits" ]]; then
    echo "✗ banned: $pattern — $hint" >&2
    echo "$hits" >&2
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
}

for entry in "${CHECKS[@]}"; do
  pat="${entry%%|*}"
  hint="${entry#*|}"
  scan "$pat" "$hint"
done

# "5 gates" / "five gates" in Evolve context → only scan new artifact dirs.
evolve_hits=""
for p in "${EVOLVE_GATE_PATHS[@]}"; do
  if [[ -d "$p" ]]; then
    found=$(grep -RInE '\b(5|five)[[:space:]]+gates\b' "$p" \
      --include='*.py' --include='*.md' --include='*.json' \
      --include='*.yaml' --include='*.yml' \
      2>/dev/null \
      | grep -vE "$EVOLVE_GATE_ALLOW_REGEX" \
      | grep -v 'glossary-allow' \
      || true)
    if [[ -n "$found" ]]; then
      evolve_hits+="$found"$'\n'
    fi
  fi
done
if [[ -n "$evolve_hits" ]]; then
  echo "✗ banned: '5 gates' in new artifacts — say 'evolve_checks' instead" >&2
  echo "$evolve_hits" >&2
  VIOLATIONS=$((VIOLATIONS + 1))
fi

if [[ "$VIOLATIONS" -gt 0 ]]; then
  echo "" >&2
  echo "glossary check: $VIOLATIONS violation(s)" >&2
  echo "see references/glossary.md for canonical names" >&2
  exit 1
fi

echo "glossary check: green"
