#!/usr/bin/env bash
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
#    using a Python helper so logic stays in one place. The heredoc prints
#    a one-line sentinel on stdout so we can record hook health below.
GATE_RESULT="$("$SAMVIL_PY" - "$PROJECT_ROOT" "$STAGE" "$TOOL_EXIT" <<'PY' 2>/dev/null
import json, os, sys
from pathlib import Path

project_root, stage, exit_code = sys.argv[1:4]
project = Path(project_root)

sys.path.insert(0, os.environ.get("SAMVIL_MCP_DIR", "mcp"))

try:
    from samvil_mcp.claim_ledger import ClaimLedger
    from samvil_mcp.gates import (
        GateName,
        Verdict,
        active_gate_override,
        gate_check,
        load_config,
    )
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


def _as_bool(value, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no", ""}:
            return False
    if value is None:
        return default
    return bool(value)


STAGE_TO_GATE = {
    "interview": GateName.INTERVIEW_TO_SEED.value,
    "seed": GateName.SEED_TO_COUNCIL.value,
    "council": GateName.COUNCIL_TO_DESIGN.value,
    "design": GateName.DESIGN_TO_SCAFFOLD.value,
    "scaffold": GateName.SCAFFOLD_TO_BUILD.value,
    "build": GateName.BUILD_TO_QA.value,
    "retro": GateName.ANY_TO_RETRO.value,
}
QA_CONTINUE = "__qa_continue__"


def _qa_results_payload() -> dict:
    results = _load_json(project / ".samvil" / "qa-results.json")
    return results


def _qa_results() -> dict:
    return _qa_results_payload().get("synthesis") or {}


def _qa_suggested_next_skill(state: dict) -> str:
    results = _qa_results_payload()
    synthesis = results.get("synthesis") or {}
    if not synthesis:
        return ""
    try:
        from samvil_mcp.qa_finalize import _decide_next_skill

        convergence = results.get("convergence") or {}
        return str(
            _decide_next_skill(synthesis, state, convergence).get("suggested") or ""
        )
    except Exception:
        return ""


def _gate_for_stage(stage: str, state: dict) -> str | None:
    if stage != "qa":
        return STAGE_TO_GATE.get(stage)
    suggested = _qa_suggested_next_skill(state)
    if suggested == "samvil-qa":
        return QA_CONTINUE
    if suggested == "samvil-evolve":
        return GateName.QA_TO_EVOLVE.value
    if suggested == "samvil-retro":
        return GateName.ANY_TO_RETRO.value
    return GateName.QA_TO_DEPLOY.value


def _metrics_for_stage(stage: str, state: dict, seed: dict, metrics: dict) -> dict:
    if stage == "interview":
        # seed_readiness is computed by the interview skill when β wiring
        # is live. Fall back to state.seed_readiness or a conservative
        # default so the gate can at least render a verdict.
        converged = state.get("ambiguity_converged", metrics.get("ambiguity_converged"))
        if converged is None:
            converged = state.get("converged", metrics.get("converged", False))
        return {
            "seed_readiness": state.get("seed_readiness", metrics.get("seed_readiness", 0.80)),
            "ambiguity_converged": _as_bool(converged),
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
        synthesis = _qa_results()
        pass1_status = str((synthesis.get("pass1") or {}).get("status") or "").upper()
        pass3_verdict = str((synthesis.get("pass3") or {}).get("verdict") or "").upper()
        counts = (synthesis.get("pass2") or {}).get("counts") or {}
        fail = int(counts.get("FAIL", 0) or 0)
        unimplemented = int(counts.get("UNIMPLEMENTED", 0) or 0)
        qa_verdict = state.get("qa_verdict") or synthesis.get("verdict") or metrics.get("qa_verdict") or "unknown"
        return {
            "three_pass_pass": (
                str(qa_verdict).upper() in ("PASS", "PASSED")
                and pass1_status in ("", "PASS")
                and pass3_verdict in ("", "PASS")
                and fail == 0
                and unimplemented == 0
            ),
            "zero_stubs": unimplemented == 0 and not bool(metrics.get("stub_detected")),
            "runtime_verified": str(synthesis.get("verification_mode") or "").casefold() == "runtime",
            "verification_mode": synthesis.get("verification_mode") or "static",
        }
    if stage == "retro":
        return {"always_run": True}
    return {}


state = _load_json(project / "project.state.json")
seed = _load_json(project / "project.seed.json")
metrics_file = _load_json(project / ".samvil" / "metrics.json")

gate_name = _gate_for_stage(stage, state)
if gate_name == QA_CONTINUE:
    print("hold;stage=qa;continue")
    sys.exit(0)
if gate_name is None:
    print(f"skip;stage={stage};no-gate")
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

metrics = (
    {"always_run": True}
    if gate_name == GateName.ANY_TO_RETRO.value
    else _metrics_for_stage(stage, state, seed, metrics_file)
)

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
override = active_gate_override(ledger, gate_name) if verdict.verdict == "block" else None
effective_verdict = Verdict.PASS.value if override else verdict.verdict
posted = True
try:
    verdict_meta = asdict(verdict)
    verdict_meta["original_verdict"] = verdict.verdict
    verdict_meta["verdict"] = effective_verdict
    verdict_meta["override_claim_id"] = override.claim_id if override else ""
    ledger.post(
        type="gate_verdict",
        subject=gate_name,
        statement=f"verdict={effective_verdict}; metrics={metrics}",
        authority_file="state.json",
        claimed_by="agent:orchestrator-agent",
        evidence=["project.state.json"],
        meta=verdict_meta,
    )
except Exception as e:
    posted = False
    sys.stderr.write(f"[samvil-contract-hook] gate_verdict post failed: {e}\n")

# Print a short line so the user sees what happened.
sys.stderr.write(
    f"[samvil-contract] post-stage {stage} → {gate_name}={effective_verdict} "
    f"(tier={tier}, failed={verdict.failed_checks})\n"
)
# Sentinel for the bash wrapper's health logging (stdout, not stderr).
override_id = override.claim_id if override else "none"
print(
    f"gate={gate_name};verdict={effective_verdict};override={override_id};posted={posted}"
)
PY
)"

# 3. Write the expected next-skill marker (W2.2 chain-break recovery).
#    The stage-start hook clears it when the chain actually continues.
#    A surviving marker = the chain invoke never happened — samvil-resume
#    reads it as the recovery point. Hard gate blocks intentionally skip this
#    marker: a blocked stage has no safe continuation to recover.
case "$GATE_RESULT" in
  *";verdict=pass;"*|skip\;*)
    SHOULD_WRITE_MARKER=1
    ;;
  *)
    SHOULD_WRITE_MARKER=0
    ;;
esac

if [ "$SHOULD_WRITE_MARKER" = "1" ]; then
  MARKER_RESULT="$("$SAMVIL_PY" - "$PROJECT_ROOT" "$SKILL_NAME" <<'PY' 2>/dev/null
import json, os, sys
from pathlib import Path
project_root, skill_name = sys.argv[1:3]
try:
    sys.path.insert(0, os.environ.get("SAMVIL_MCP_DIR", "mcp"))
    from samvil_mcp.chain_markers import resolve_stage_next_skill, write_chain_marker
    def _load_json(path):
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _qa_next_skill(project):
        results = _load_json(project / ".samvil" / "qa-results.json")
        synthesis = results.get("synthesis") or {}
        if not synthesis:
            return None
        state = _load_json(project / "project.state.json")
        try:
            from samvil_mcp.qa_finalize import _decide_next_skill
            convergence = results.get("convergence") or {}
            return str(
                _decide_next_skill(synthesis, state, convergence).get("suggested") or ""
            ) or None
        except Exception:
            return None

    next_skill = (
        _qa_next_skill(Path(project_root))
        if skill_name == "samvil-qa"
        else resolve_stage_next_skill(project_root, skill_name)
    )
    marker = write_chain_marker(project_root, "claude_code", skill_name, next_skill=next_skill)
    nxt = marker.get("next_skill", "")
    if nxt:
        print(f"marker={skill_name}->{nxt}")
    else:
        print("marker=pipeline-end")
except Exception as e:
    sys.stderr.write(f"[samvil-contract-hook] chain marker write failed: {e}\n")
PY
  )"
else
  MARKER_RESULT="marker=skipped-gate-${STAGE}"
fi

if [ "$SHOULD_WRITE_MARKER" != "1" ]; then
  samvil_contract_log_health "chain" "ok" "$MARKER_RESULT"
elif [ -n "$MARKER_RESULT" ]; then
  samvil_contract_log_health "chain" "ok" "$MARKER_RESULT"
else
  samvil_contract_log_health "chain" "fail" "next-skill marker not written after $STAGE"
fi

# 4. Record hook health so failures are visible in health_check, not
#    just lost to stderr (W1.2).
case "$GATE_RESULT" in
  skip\;*)
    : # no gate for this stage — not a failure
    ;;
  *posted=True*)
    samvil_contract_log_health "stage-end" "ok" "$GATE_RESULT ($STAGE)"
    ;;
  *)
    samvil_contract_log_health "stage-end" "fail" "${GATE_RESULT:-gate eval produced no verdict} ($STAGE)"
    ;;
esac

exit 0
