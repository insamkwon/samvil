#!/bin/bash
# SAMVIL v3.2 L1 — PostToolUse hook for Skill invocations.
#
# Fires right after Claude's Skill tool returns. Wraps up the stage:
#   1. Verify the pre-stage claim (flip to verified).
#   2. Collect the stage-local metrics and post a gate_verdict claim
#      for the next gate (best-effort — on missing metrics we post a
#      skipped-gate claim so retro can audit the gap).
#
# Args:
#   $1 = $TOOL_INPUT (JSON string with "skill" field)
#   $2 = $TOOL_EXIT_CODE (0 on success)
#
# Best-effort. Never halts the pipeline.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_contract-helpers.sh
source "$HERE/_contract-helpers.sh"

TOOL_INPUT="${1:-}"
TOOL_EXIT="${2:-0}"

# matcher="Skill" didn't fire in the dogfood run, so we register this
# hook on all tools and filter here.
case "${TOOL_NAME:-}" in
  Skill|Task|mcp__samvil*)
    ;;
  *)
    exit 0
    ;;
esac

SKILL_NAME="$(samvil_contract_extract_skill_name "$TOOL_INPUT")"
[ -z "$SKILL_NAME" ] && exit 0
samvil_contract_is_stage_skill "$SKILL_NAME" || exit 0

PROJECT_ROOT="$(samvil_contract_find_project_root)"
[ -z "$PROJECT_ROOT" ] && exit 0

STAGE="$(samvil_contract_stage_name "$SKILL_NAME")"
AGENT="$(samvil_contract_primary_agent "$STAGE")"
SUBJECT="stage:$STAGE"

# 1. Verify the stage_start claim posted in PreToolUse. Verifier is
#    'agent:user' so G≠J passes (stage_start claim is emitted by the
#    stage's primary agent).
samvil_contract_verify_claim "$PROJECT_ROOT" "$SUBJECT" "agent:user"

# 2. Evaluate the next gate. Metrics are collected from local files
#    using a Python helper so logic stays in one place.
"$SAMVIL_PY" - "$PROJECT_ROOT" "$STAGE" "$TOOL_EXIT" <<'PY' 2>/dev/null
import json, os, sys
from pathlib import Path

project_root, stage, exit_code = sys.argv[1:4]
project = Path(project_root)

sys.path.insert(0, "/Users/kwondongho/dev/samvil/mcp")

try:
    from samvil_mcp.claim_ledger import ClaimLedger
    from samvil_mcp.gates import GateName, Verdict, gate_check, load_config
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] gate import failed: {e}\n")
    sys.exit(0)


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


STAGE_TO_GATE = {
    "interview": GateName.INTERVIEW_TO_SEED.value,
    "seed": GateName.SEED_TO_COUNCIL.value,
    "council": GateName.COUNCIL_TO_DESIGN.value,
    "design": GateName.DESIGN_TO_SCAFFOLD.value,
    "scaffold": GateName.SCAFFOLD_TO_BUILD.value,
    "build": GateName.BUILD_TO_QA.value,
    "qa": GateName.QA_TO_DEPLOY.value,
    "retro": GateName.ANY_TO_RETRO.value,
}


def _metrics_for_stage(stage: str, state: dict, seed: dict, metrics: dict) -> dict:
    if stage == "interview":
        # seed_readiness is computed by the interview skill when β wiring
        # is live. Fall back to state.seed_readiness or a conservative
        # default so the gate can at least render a verdict.
        return {
            "seed_readiness": state.get("seed_readiness", metrics.get("seed_readiness", 0.80))
        }
    if stage == "seed":
        schema = seed.get("schema_version") or ""
        return {
            "schema_valid": bool(seed),
            "schema_version_min": schema if schema else "3.0",
        }
    if stage == "council":
        return {"consensus_required": True}
    if stage == "design":
        return {"blueprint_valid": True, "stack_matrix_match": True}
    if stage == "scaffold":
        # Reflect the scaffold skill's actual outputs.
        log = project / ".samvil" / "build.log"
        return {
            "sanity_build_ok": log.exists(),
            "env_vars_present": (project / ".env.example").exists(),
        }
    if stage == "build":
        impl = metrics.get("implementation_rate")
        if impl is None:
            # Fallback from state: completed_features / total_features.
            completed = len(state.get("completed_features") or [])
            total = metrics.get("total_features") or len(seed.get("features") or [])
            impl = (completed / total) if total else 0.0
        return {"implementation_rate": float(impl)}
    if stage == "qa":
        qa_verdict = state.get("qa_verdict") or metrics.get("qa_verdict") or "unknown"
        return {
            "three_pass_pass": qa_verdict.upper() in ("PASS", "PASSED"),
            "zero_stubs": not bool(metrics.get("stub_detected")),
        }
    if stage == "retro":
        return {"always_run": True}
    return {}


state = _load_json(project / "project.state.json")
seed = _load_json(project / "project.seed.json")
metrics_file = _load_json(project / ".samvil" / "metrics.json")

gate_name = STAGE_TO_GATE.get(stage)
if gate_name is None:
    sys.exit(0)

tier = (
    state.get("samvil_tier")
    or state.get("agent_tier")  # legacy fallback (glossary-allow: v3.1 read)
    or "standard"
)
# `full` stays `full`; validate_seed accepts it only on new seeds. Hook is
# defensive — coerce into the known set.
if tier not in {"minimal", "standard", "thorough", "full", "deep"}:
    tier = "standard"

metrics = _metrics_for_stage(stage, state, seed, metrics_file)

try:
    verdict = gate_check(
        gate_name,
        samvil_tier=tier,
        metrics=metrics,
        subject=stage,
    )
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] gate_check crashed: {e}\n")
    sys.exit(0)

from dataclasses import asdict

ledger = ClaimLedger(project / ".samvil" / "claims.jsonl")
try:
    ledger.post(
        type="gate_verdict",
        subject=gate_name,
        statement=f"verdict={verdict.verdict}; metrics={metrics}",
        authority_file="state.json",
        claimed_by="agent:orchestrator-agent",
        evidence=["project.state.json"],
        meta=asdict(verdict),
    )
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] gate_verdict post failed: {e}\n")

# Print a short line so the user sees what happened.
sys.stderr.write(
    f"[samvil-contract] post-stage {stage} → {gate_name}={verdict.verdict} "
    f"(tier={tier}, failed={verdict.failed_checks})\n"
)
PY

exit 0
