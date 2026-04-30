#!/usr/bin/env bash
# SAMVIL pre-commit enforcement — MANDATORY gate before every commit.
#
# Runs the same checks that surfaced portability bugs during v3.2.0
# dogfood:
#   1. Hard-coded path scan (/Users/<name>/, /home/<name>/, personal
#      email fragments, API keys)
#   2. Version sync across plugin.json / __init__.py / README
#   3. Glossary CI (blocks banned v3.1 terms in new artifacts)
#   4. Full pytest suite
#   5. Skill wiring smoke (SKILL.md references still intact)
#   6. MCP server import smoke (broken syntax catches here, not at
#      plugin install time on someone else's machine)
#
# Exit 0 = all green, commit may proceed.
# Exit 1 = at least one check failed, commit is blocked.
#
# Install once per clone (tracked `.githooks/` takes effect):
#   git config core.hooksPath .githooks
#
# Or run manually:
#   bash scripts/pre-commit-check.sh

set -u  # fail on unbound var
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

FAILURES=0
_fail() {
  echo "  ✗ $1"
  FAILURES=$((FAILURES + 1))
}
_ok() {
  echo "  ✓ $1"
}
_section() {
  echo ""
  echo "━━━ $1 ━━━"
}

# Scope of scan: only files being committed (staged) if running as git
# hook; otherwise all tracked files. This keeps the hook fast on small
# commits while still validating new code paths.
if git rev-parse --verify HEAD >/dev/null 2>&1; then
  STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
else
  STAGED_FILES=""
fi
if [ -z "${STAGED_FILES:-}" ]; then
  # Run against all tracked files (manual invocation or initial commit).
  STAGED_FILES=$(git ls-files 2>/dev/null)
fi


# ── 1. Hard-coded path scan ─────────────────────────────────────────
_section "1. Hard-coded paths"

# Home-dir-style absolute paths. We scan every tracked text file but
# skip a small allowlist: the check script itself (it contains the
# patterns to scan for), the gitignore (documents what to ignore), the
# CHANGELOG (history of the very bug this check prevents), and the
# absorption handoff documents under ouroboros-absorb/.
_SELFTEST_SKIP='scripts/pre-commit-check\.sh$|\.gitignore$|CHANGELOG\.md$|ouroboros-absorb'
hits=$(echo "$STAGED_FILES" \
  | grep -E '\.(sh|py|md|json|yaml|yml|toml)$' \
  | xargs grep -l '/Users/kwondongho\|/home/kwondongho' 2>/dev/null \
  | grep -Ev "$_SELFTEST_SKIP" || true)
if [ -n "$hits" ]; then
  _fail "hard-coded home path detected in:"
  echo "$hits" | sed 's/^/      /'
else
  _ok "no /Users/<name>/ or /home/<name>/ leaks"
fi

# Author-specific email/handle (whitelist the ones that are legit).
# Self-test skip via the same allowlist.
hits=$(echo "$STAGED_FILES" \
  | grep -E '\.(sh|py|json|yaml|yml|toml)$' \
  | xargs grep -l 'gmlwjd0816' 2>/dev/null \
  | grep -Ev "$_SELFTEST_SKIP" || true)
if [ -n "$hits" ]; then
  _fail "personal email leaked: $hits"
else
  _ok "no author-specific email in code"
fi

# Obvious secret patterns
hits=$(echo "$STAGED_FILES" \
  | grep -E '\.(sh|py|json|yaml|yml|toml|md)$' \
  | grep -Ev "$_SELFTEST_SKIP" \
  | xargs grep -En 'sk-[a-zA-Z0-9]{20}|ANTHROPIC_AUTH_TOKEN=[^$]|GITHUB_TOKEN=[^$]' 2>/dev/null \
  | grep -v '\.env\.example\|glossary-allow\|# example\|example:' || true)
if [ -n "$hits" ]; then
  _fail "possible secret detected:"
  echo "$hits" | sed 's/^/      /' | head -5
else
  _ok "no obvious secret patterns"
fi


# ── 2. Version sync ─────────────────────────────────────────────────
_section "2. Version sync (plugin.json / __init__.py / README)"

if bash hooks/validate-version-sync.sh >/dev/null 2>&1; then
  v=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
  _ok "all three at $v"
else
  _fail "version mismatch — run hooks/validate-version-sync.sh"
fi


# ── 3. Glossary CI ──────────────────────────────────────────────────
_section "3. Glossary CI"

if bash scripts/check-glossary.sh >/dev/null 2>&1; then
  _ok "glossary check: green"
else
  _fail "banned v3.1 term detected — run scripts/check-glossary.sh for details"
fi


# ── 4. pytest ────────────────────────────────────────────────────────
_section "4. pytest (full suite)"

if [ -x mcp/.venv/bin/python ]; then
  if (cd mcp && .venv/bin/python -m pytest tests/ -q --tb=no >/tmp/samvil-pretest.log 2>&1); then
    count=$(grep -oE '[0-9]+ passed' /tmp/samvil-pretest.log | tail -1 || echo "?")
    _ok "pytest: $count"
  else
    _fail "pytest failed — see /tmp/samvil-pretest.log"
    tail -20 /tmp/samvil-pretest.log | sed 's/^/      /'
  fi
else
  _fail "mcp/.venv missing — run: cd mcp && uv venv .venv && uv pip install -e ."
fi


# ── 5. Skill wiring ─────────────────────────────────────────────────
_section "5. Skill wiring"

if python3 scripts/check-skill-wiring.py >/dev/null 2>&1; then
  _ok "skill wiring smoke: PASS"
else
  _fail "skill wiring smoke FAILED — run scripts/check-skill-wiring.py"
fi


# ── 6. Skill thinness ────────────────────────────────────────────────
_section "6. Skill thinness"

if python3 scripts/skill-thinness-report.py --migrated-only --fail-over 120 >/dev/null 2>&1; then
  _ok "migrated skills under 120 active lines"
else
  _fail "skill thinness FAILED — run scripts/skill-thinness-report.py --migrated-only --fail-over 120"
fi


# ── 7. Cross-host continuation ──────────────────────────────────────
_section "7. Cross-host continuation"

if python3 scripts/phase2-cross-host-smoke.py >/dev/null 2>&1; then
  _ok "phase2 cross-host replay: PASS"
else
  _fail "phase2 cross-host replay FAILED — run scripts/phase2-cross-host-smoke.py"
fi


# ── 8. MCP server import ────────────────────────────────────────────
_section "8. MCP server import smoke"

if [ -x mcp/.venv/bin/python ]; then
  out=$(mcp/.venv/bin/python -c "from samvil_mcp import server; print(len(list(server.mcp._tool_manager._tools)))" 2>&1)
  if echo "$out" | grep -Eq '^[0-9]+$'; then
    _ok "server imports clean ($out tools)"
  else
    _fail "server import failed:"
    echo "$out" | sed 's/^/      /'
  fi
else
  _fail "venv missing (see check 4)"
fi


# ── 9. Markdown reference integrity ─────────────────────────────────
_section "9. Markdown reference integrity"

if bash scripts/check-broken-references.sh >/tmp/samvil-mdrefs.log 2>&1; then
  summary=$(tail -1 /tmp/samvil-mdrefs.log | sed -E 's/^[[:space:]]*✓[[:space:]]*//')
  _ok "$summary"
else
  _fail "broken markdown reference(s):"
  cat /tmp/samvil-mdrefs.log | sed 's/^/      /'
fi


# ── 10. Host parity (CC ↔ Codex) ────────────────────────────────────
_section "10. Host parity (CC ↔ Codex)"

if python3 scripts/check-host-parity.py --strict >/tmp/samvil-hostparity.log 2>&1; then
  summary=$(tail -1 /tmp/samvil-hostparity.log | sed -E 's/^[[:space:]]*✓[[:space:]]*//')
  _ok "$summary"
else
  _fail "host parity drift:"
  cat /tmp/samvil-hostparity.log | sed 's/^/      /'
fi


# ── Summary ─────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "═══ pre-commit check: PASS ═══"
  exit 0
else
  echo "═══ pre-commit check: $FAILURES FAIL(s) — commit BLOCKED ═══"
  echo ""
  echo "Bypass only for true emergencies with: git commit --no-verify"
  echo "If you bypass, fix the failure in the very next commit."
  exit 1
fi
