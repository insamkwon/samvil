#!/usr/bin/env bash
# check-broken-references.sh — Verify all markdown links in references/,
# docs/, and the repo root resolve to existing files.
#
# Scans every `.md` file in those locations for inline links of the form
#   [text](relative/path/to/file.md)
# or
#   [text](relative/path/to/file.md#anchor)
# and verifies the target exists on disk (relative to the linking file's
# directory). Skips http/https/mailto URLs and pure anchor refs (#foo).
#
# Exit 0 = all links resolve. Exit 1 = at least one broken link.
#
# Used by scripts/pre-commit-check.sh section 9.

set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Collect markdown files: references/**, docs/**, plus root-level *.md.
files=()
if [ -d references ]; then
  while IFS= read -r f; do files+=("$f"); done < <(find references -name '*.md' -type f 2>/dev/null)
fi
if [ -d docs ]; then
  while IFS= read -r f; do files+=("$f"); done < <(find docs -name '*.md' -type f 2>/dev/null)
fi
while IFS= read -r f; do files+=("$f"); done < <(find . -maxdepth 1 -name '*.md' -type f 2>/dev/null | sed 's|^\./||')

scanned=0
broken=0

for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  scanned=$((scanned + 1))

  # Extract the URL portion of every [text](url.md...) inline link.
  # Limit to links whose target ends in `.md` (optionally with `#anchor`
  # or `?query`). External and image-only refs are filtered above.
  while IFS= read -r link; do
    [ -z "$link" ] && continue
    # Strip optional anchor (#...) and query (?...).
    path="${link%%#*}"
    path="${path%%\?*}"
    # Skip pure-anchor links (no path).
    [ -z "$path" ] && continue
    # Skip URLs and home-dir references (external docs outside repo).
    case "$path" in
      http://*|https://*|mailto:*|//*) continue ;;
      \~/*|\$HOME/*) continue ;;
    esac
    # Skip absolute paths starting with / (treated as repo-root absolute,
    # not file-system absolute, but this hook doesn't enforce them yet).
    if [ "${path:0:1}" = "/" ]; then
      target="$repo_root$path"
    else
      target="$(dirname "$f")/$path"
    fi
    if [ ! -e "$target" ]; then
      echo "  ✗ $f → $link"
      broken=$((broken + 1))
    fi
  done < <(grep -oE '\[[^]]*\]\([^)]+\.md[^)]*\)' "$f" 2>/dev/null \
            | sed -E 's/^\[[^]]*\]\(([^)]+)\)$/\1/')
done

if [ "$broken" -gt 0 ]; then
  echo ""
  echo "  $broken broken markdown reference(s) across $scanned file(s)"
  exit 1
fi

echo "  ✓ all markdown references resolve ($scanned files scanned)"
exit 0
