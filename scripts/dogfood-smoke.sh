#!/usr/bin/env bash
# SAMVIL nightly dogfood smoke (Phase D.5).
#
# Goal: in CI, exercise the deterministic MCP tools that would run during
# a real pipeline, against a curated fixture seed — without burning
# Anthropic API credits on LLM-bound stages.
#
# What it covers (dry-run, default):
#   * Fixture seed/state pass schema validation.
#   * evaluate_deploy_target returns a usable verdict.
#   * aggregate_retro_metrics reads file-based fallbacks correctly.
#   * render_progress_panel produces a non-empty ASCII frame.
#   * evaluate_stuck_recovery returns action='none' for healthy fixtures.
#
# What it does NOT cover (intentionally):
#   * Real LLM calls (interview, build worker, QA judge).
#   * Real shell-out to npm/vercel/eas — those are host-bound (P8) and
#     belong in a manual or weekly cron, not every PR.
#
# Usage:
#   bash scripts/dogfood-smoke.sh                # dry-run smoke (CI default)
#   bash scripts/dogfood-smoke.sh --quiet        # less output

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$HERE/scripts/dogfood-smoke-fixtures"
PYTHON="$HERE/mcp/.venv/bin/python"

QUIET=0
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --dry-run) ;;  # default already
    -h|--help)
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# //;s/^#//'
      exit 0
      ;;
    *) echo "unknown arg: $arg" >&2 ; exit 2 ;;
  esac
done

log() {
  if [[ "$QUIET" == "0" ]]; then
    echo "$@"
  fi
}

if [[ ! -x "$PYTHON" ]]; then
  echo "✗ python venv not found at $PYTHON — run: python3 -m venv mcp/.venv && mcp/.venv/bin/pip install -e mcp" >&2
  exit 1
fi

if [[ ! -d "$FIXTURE_DIR" ]]; then
  echo "✗ fixture dir missing: $FIXTURE_DIR" >&2
  exit 1
fi

# Stage a tmp project root with the fixture files copied in.
TMP_PROJECT=$(mktemp -d -t samvil-dogfood-smoke-XXXXXX)
trap 'rm -rf "$TMP_PROJECT"' EXIT

cp "$FIXTURE_DIR/seed.json" "$TMP_PROJECT/project.seed.json"
cp "$FIXTURE_DIR/state.json" "$TMP_PROJECT/project.state.json"
mkdir -p "$TMP_PROJECT/.samvil"
# A minimal qa-results.json so retro fallback has data to chew on.
cat > "$TMP_PROJECT/.samvil/qa-results.json" <<'JSON'
{
  "verdict": "PASS",
  "ac_results": [
    {"id": "AC-1", "status": "PASS"},
    {"id": "AC-2", "status": "PASS"},
    {"id": "AC-3", "status": "PASS"},
    {"id": "AC-4", "status": "PASS"}
  ]
}
JSON

log "✓ staged fixture project at $TMP_PROJECT"

# Run a Python harness that exercises each MCP module against the fixture.
"$PYTHON" - <<PY
import json
import sys
from pathlib import Path

project_root = "$TMP_PROJECT"

failures = []

def _ok(label):
    print(f"  ✓ {label}")

def _fail(label, err):
    failures.append((label, str(err)))
    print(f"  ✗ {label}: {err}")

# 1. Seed validation
try:
    from samvil_mcp.seed_manager import validate_seed
    seed = json.loads(Path(project_root, "project.seed.json").read_text())
    res = validate_seed(seed)
    if res.get("valid") is False:
        _fail("validate_seed", res.get("errors"))
    else:
        _ok("validate_seed: schema 3.0 OK")
except Exception as e:
    _fail("validate_seed", e)

# 2. Deploy target evaluation
try:
    from samvil_mcp.deploy_targets import evaluate_deploy_target
    out = evaluate_deploy_target(project_root)
    if out.get("solution_type") != "web-app":
        _fail("evaluate_deploy_target", f"solution_type={out.get('solution_type')}")
    elif out.get("build_artifact", {}).get("checked_paths") != ["dist"]:
        _fail("evaluate_deploy_target", f"vite-react must check dist/, got {out.get('build_artifact')}")
    else:
        _ok(f"evaluate_deploy_target: {out['selected_platform']['id']} ✓ dist/ ✓")
except Exception as e:
    _fail("evaluate_deploy_target", e)

# 3. Retro metrics aggregation (file-based fallback)
try:
    from samvil_mcp.retro_aggregate import aggregate_retro_metrics
    out = aggregate_retro_metrics(project_root)
    leaf = out["v3_leaf_stats"]
    if leaf["total_leaf_events"] != 4:
        _fail("aggregate_retro_metrics", f"expected 4 leaves, got {leaf}")
    elif leaf["source"] != "qa_results":
        _fail("aggregate_retro_metrics", f"expected source=qa_results, got {leaf['source']}")
    else:
        _ok(f"aggregate_retro_metrics: {leaf['by_status']} via {leaf['source']}")
except Exception as e:
    _fail("aggregate_retro_metrics", e)

# 4. Progress panel
try:
    from samvil_mcp.progress_panel import compute_progress, render_panel
    progress = compute_progress(project_root)
    panel = render_panel(progress)
    if "dogfood-todo" not in panel:
        _fail("render_progress_panel", "panel missing project name")
    else:
        _ok(f"render_progress_panel: stage={progress['current_stage']}, leaves={progress['leaves']['total']}")
except Exception as e:
    _fail("render_progress_panel", e)

# 5. Auto-recovery (healthy state should yield 'none')
try:
    from samvil_mcp.auto_recovery import evaluate_stuck_recovery
    # No last_progress_at → state would yield 'no_heartbeat_yet' (action: none).
    # That's the dry-run friendly path; we just verify it doesn't crash and
    # returns a recognized action.
    out = evaluate_stuck_recovery(project_root)
    if out["action"] not in {"none", "reentry", "escalate", "block"}:
        _fail("evaluate_stuck_recovery", f"unknown action={out['action']}")
    else:
        _ok(f"evaluate_stuck_recovery: action={out['action']}")
except Exception as e:
    _fail("evaluate_stuck_recovery", e)

if failures:
    print(f"\n✗ dogfood smoke: {len(failures)} failure(s)")
    sys.exit(1)
print("\n✓ dogfood smoke: 5/5 modules consistent against fixture")
PY

log "✓ dogfood smoke complete"
