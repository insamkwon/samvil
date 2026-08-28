#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLUGIN_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
export SAMVIL_PLUGIN_ROOT="$PLUGIN_ROOT"

exec uvx --from "$PLUGIN_ROOT/mcp" samvil-mcp
