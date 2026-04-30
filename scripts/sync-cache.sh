#!/usr/bin/env bash
# SAMVIL plugin cache sync — copy current working tree to the installed
# plugin cache directory so changes take effect immediately.
#
# Why: Claude Code reads SAMVIL files from a cache directory (not from
# the repo). After every code change, the cache must be re-synced or
# users see stale behavior. Doing this manually with `cp` for 7-8 files
# every time is the #1 daily toil for SAMVIL maintainers.
#
# Usage:
#   bash scripts/sync-cache.sh              # sync now
#   bash scripts/sync-cache.sh --dry-run    # preview without copying
#   bash scripts/sync-cache.sh --quiet      # less output
#
# Auto-mode: If the post-commit hook is installed (via
# scripts/install-git-hooks.sh), this script runs automatically after
# every successful commit.
#
# Behavior:
#   * Curated whitelist of source dirs/files (not blind tree copy).
#   * rsync without --delete (preserves cache-side files like
#     .mcp.json, .git-easy.json that aren't in the repo).
#   * Excludes __pycache__, .pytest_cache, .venv, .DS_Store.
#   * Graceful degradation: if cache dir doesn't exist, exit 0 with
#     an info message (plugin not installed).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${HOME}/.claude/plugins/cache/samvil/samvil"

DRY_RUN=0
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --quiet)   QUIET=1 ;;
    -h|--help)
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# //;s/^#//'
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

log() {
  if [[ "$QUIET" == "0" ]]; then
    echo "$@"
  fi
}

if [[ ! -d "$CACHE_DIR" ]]; then
  log "ℹ plugin cache not found: $CACHE_DIR"
  log "  (plugin may not be installed; nothing to sync)"
  exit 0
fi

# Curated whitelist — explicit so an accidental file (e.g., a 1GB log)
# never sneaks into the cache. Order doesn't matter; rsync is per-target.
SYNC_TARGETS=(
  ".claude-plugin"
  "agents"
  "hooks"
  "mcp/samvil_mcp"
  "mcp/tests"
  "mcp/pyproject.toml"
  "references"
  "scripts"
  "skills"
  "CHANGELOG.md"
  "CLAUDE.md"
  "README.md"
)

RSYNC_EXCLUDES=(
  "--exclude=__pycache__"
  "--exclude=.pytest_cache"
  "--exclude=.venv"
  "--exclude=.DS_Store"
  "--exclude=*.pyc"
  "--exclude=*.pyo"
)

count=0
skipped=0
for target in "${SYNC_TARGETS[@]}"; do
  src="$HERE/$target"
  dst="$CACHE_DIR/$target"
  if [[ ! -e "$src" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] would sync: $target"
    count=$((count + 1))
    continue
  fi
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$src/" "$dst/"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  fi
  count=$((count + 1))
done

if [[ "$DRY_RUN" == "1" ]]; then
  log "✓ dry-run: $count target(s) would be synced ($skipped missing)"
else
  log "✓ synced $count target(s) → $CACHE_DIR"
fi
