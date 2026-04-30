#!/usr/bin/env bash
# Wire up SAMVIL's tracked .githooks/ directory as the active git-hooks
# path for this clone. Run once after cloning; idempotent.
#
#   bash scripts/install-git-hooks.sh
#
# What it does:
#   * `git config core.hooksPath .githooks` → git starts reading hooks
#     from the tracked dir instead of .git/hooks/.
#   * chmod +x on every file in .githooks/ so they're executable.
#
# What it does NOT do:
#   * Force-install on a dirty working tree.
#   * Change anything outside the local repo's .git/config.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

if [ ! -d .githooks ]; then
  echo "✗ .githooks/ directory missing — wrong repo?" >&2
  exit 1
fi

git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

echo "✓ git hooks path set to .githooks/"
echo "  installed hooks:"
ls -1 .githooks/ | sed 's/^/    /'
echo ""
echo "pre-commit will now run scripts/pre-commit-check.sh before every commit."
echo "post-commit will now auto-sync the plugin cache (scripts/sync-cache.sh)."
echo "Bypass only in emergencies with: git commit --no-verify"
