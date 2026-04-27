"""Stage gate framework (⑥) — Hard by default, Escalation for specific checks.

Per HANDOFF-v3.2-DECISIONS.md §3.⑥ and §6.3:

  * Every gate is Hard by default. `samvil_tier` adjusts thresholds.
  * Three checks may escalate instead of hard-blocking in standard+ tiers:
    ac_testability, lifecycle_coverage, decision_boundary_clarity.
  * Soft gates exist only when the user passes `--allow-warn`.
  * Judge role writes gate verdicts as claims of type `gate_verdict` (see ⑤).
  * The boundary between ⑥ and P8 Graceful Degradation: if the failure
    changes the truth of a claim, it's a gate failure. If it only slows down
    observation of a known-true claim, it's graceful degradation.
    (See references/gate-vs-degradation.md.)

This module is intentionally pure: no I/O except reading `gate_config.yaml`.
Skills import `gate_check(...)` and branch on the verdict.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # optional runtime dep; fall back to embedded defaults if missing
except Exception:  # pragma: no cover — yaml is in requirements but be defensive
    yaml = None  # type: ignore[assignment]


# ── Gate identifiers ──────────────────────────────────────────────────


class GateName(str, Enum):
    INTERVIEW_TO_SEED = "interview_to_seed"
    SEED_TO_COUNCIL = "seed_to_council"
    COUNCIL_TO_DESIGN = "council_to_design"
    DESIGN_TO_SCAFFOLD = "design_to_scaffold"
    SCAFFOLD_TO_BUILD = "scaffold_to_build"
    BUILD_TO_QA = "build_to_qa"
    QA_TO_EVOLVE = "qa_to_evolve"
    QA_TO_DEPLOY = "qa_to_deploy"
    ANY_TO_RETRO = "any_to_retro"


# samvil_tier: whole-pipeline rigor. The v3.2 naming is settled; don't reuse
# these names for model-cost or interview vocab.
TIERS: tuple[str, ...] = ("minimal", "standard", "thorough", "full", "deep")

# Checks that may escalate (rather than hard-block) in standard+ tiers.
ESCALATION_CHECKS: frozenset[str] = frozenset(
    {"ac_testability", "lifecycle_coverage", "decision_boundary_clarity"}
)


class Verdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    ESCALATE = "escalate"
    SKIP = "skip"


# ── Verdict shape ─────────────────────────────────────────────────────


@dataclass
class RequiredAction:
    """The machine-readable 'what to do next' attached to a non-pass verdict.

    `type` is one of the small set from §3.⑥. Keep this closed so skills can
    dispatch on it reliably.
    """

    type: str = ""  # split_ac | run_research | stronger_model | fix_schema | ask_user
    payload: dict = field(default_factory=dict)


@dataclass
class GateVerdict:
    gate: str
    verdict: str
    samvil_tier: str
    threshold: dict = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)
    reason: str = ""
    required_action: RequiredAction = field(default_factory=RequiredAction)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ── Config ────────────────────────────────────────────────────────────


# Defaults match §3.⑥ "(initial estimate)" numbers. They're also registered
# as experimental_policy entries by scripts/seed-experiments.py so Sprint 1
# dogfood can calibrate them.
DEFAULT_CONFIG: dict[str, Any] = {
    "gates": {
        "interview_to_seed": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"seed_readiness": 0.80},
                "standard": {"seed_readiness": 0.88},
                "thorough": {"seed_readiness": 0.93},
                "full": {"seed_readiness": 0.96},
                "deep": {"seed_readiness": 0.985},
            },
        },
        "seed_to_council": {
            "policy": "hard",
            "thresholds": {
                # Schema-based gate — thresholds here are booleans at runtime.
                "minimal": {"schema_valid": True, "schema_version_min": "3.2"},
                "standard": {"schema_valid": True, "schema_version_min": "3.2"},
                "thorough": {"schema_valid": True, "schema_version_min": "3.2"},
                "full": {"schema_valid": True, "schema_version_min": "3.2"},
                "deep": {"schema_valid": True, "schema_version_min": "3.2"},
            },
        },
        "council_to_design": {
            # Only tier that can skip this gate is `minimal`.
            "policy": "hard",
            "thresholds": {
                "minimal": {"skip": True},
                "standard": {"consensus_required": True},
                "thorough": {"consensus_required": True},
                "full": {"consensus_required": True},
                "deep": {"consensus_required": True},
            },
        },
        "design_to_scaffold": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"blueprint_valid": True, "stack_matrix_match": True},
                "standard": {"blueprint_valid": True, "stack_matrix_match": True},
                "thorough": {"blueprint_valid": True, "stack_matrix_match": True},
                "full": {"blueprint_valid": True, "stack_matrix_match": True},
                "deep": {"blueprint_valid": True, "stack_matrix_match": True},
            },
        },
        "scaffold_to_build": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"sanity_build_ok": True, "env_vars_present": True},
                "standard": {"sanity_build_ok": True, "env_vars_present": True},
                "thorough": {"sanity_build_ok": True, "env_vars_present": True},
                "full": {"sanity_build_ok": True, "env_vars_present": True},
                "deep": {"sanity_build_ok": True, "env_vars_present": True},
            },
        },
        "build_to_qa": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"implementation_rate": 0.70},
                "standard": {"implementation_rate": 0.85},
                "thorough": {"implementation_rate": 0.95},
                "full": {"implementation_rate": 0.98},
                "deep": {"implementation_rate": 0.98},
            },
        },
        "qa_to_deploy": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"three_pass_pass": True, "zero_stubs": True},
                "standard": {"three_pass_pass": True, "zero_stubs": True},
                "thorough": {"three_pass_pass": True, "zero_stubs": True},
                "full": {"three_pass_pass": True, "zero_stubs": True},
                "deep": {"three_pass_pass": True, "zero_stubs": True},
            },
        },
        "qa_to_evolve": {
            "policy": "hard",
            "thresholds": {
                "minimal": {"three_pass_pass": True},
                "standard": {"three_pass_pass": True},
                "thorough": {"three_pass_pass": True, "zero_stubs": True},
                "full": {"three_pass_pass": True, "zero_stubs": True},
                "deep": {"three_pass_pass": True, "zero_stubs": True},
            },
        },
        "any_to_retro": {
            # Cannot skip — feeds ⑧ policy evolution.
            "policy": "hard",
            "thresholds": {t: {"always_run": True} for t in TIERS},
        },
    },
    "escalation": {
        "policy": "same_check_twice_forces_user",
        "checks": sorted(ESCALATION_CHECKS),
    },
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load gate_config.yaml if present, otherwise return DEFAULT_CONFIG.

    Missing keys are filled in from defaults so user overrides can be sparse.
    """
    if path is None:
        return _deep_copy(DEFAULT_CONFIG)

    p = Path(path)
    if not p.exists() or yaml is None:
        return _deep_copy(DEFAULT_CONFIG)

    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except Exception:
        return _deep_copy(DEFAULT_CONFIG)

    merged = _deep_copy(DEFAULT_CONFIG)
    _deep_merge(merged, raw)
    return merged


def _deep_copy(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _deep_copy(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_deep_copy(v) for v in d]
    return d


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ── Core gate_check ───────────────────────────────────────────────────


def gate_check(
    name: str,
    *,
    samvil_tier: str,
    metrics: dict[str, Any],
    subject: str = "",
    config: dict[str, Any] | None = None,
    allow_warn: bool = False,
) -> GateVerdict:
    """Evaluate a gate against supplied runtime metrics.

    Pure function. Callers gather the metrics beforehand (e.g., seed
    readiness score from interview_engine, implementation_rate from
    build_stage_complete event).

    `allow_warn` demotes block → pass-with-warning. Only user-flag path.
    """
    if samvil_tier not in TIERS:
        raise ValueError(
            f"samvil_tier {samvil_tier!r} not in {TIERS}. Use the v3.2 names."
        )
    cfg = config or load_config()
    gate_cfg = cfg.get("gates", {}).get(name)
    if gate_cfg is None:
        raise ValueError(f"gate {name!r} not configured.")

    thresholds_for_tier: dict[str, Any] = gate_cfg.get("thresholds", {}).get(
        samvil_tier, {}
    )

    # `skip: true` short-circuit (e.g., council_to_design.minimal).
    if thresholds_for_tier.get("skip"):
        return GateVerdict(
            gate=name,
            verdict=Verdict.SKIP.value,
            samvil_tier=samvil_tier,
            threshold=thresholds_for_tier,
            reason="tier policy: skip",
        )

    failed: list[str] = []
    escalate_only: list[str] = []
    reasons: list[str] = []

    for key, required in thresholds_for_tier.items():
        actual = metrics.get(key)
        ok, why = _check_single(key, required, actual)
        if ok:
            continue
        if key in ESCALATION_CHECKS and samvil_tier != "minimal":
            escalate_only.append(key)
        else:
            failed.append(key)
        reasons.append(why)

    if failed:
        if allow_warn:
            return GateVerdict(
                gate=name,
                verdict=Verdict.PASS.value,
                samvil_tier=samvil_tier,
                threshold=thresholds_for_tier,
                failed_checks=failed + escalate_only,
                reason="allow_warn: downgraded block → pass " + "; ".join(reasons),
            )
        return GateVerdict(
            gate=name,
            verdict=Verdict.BLOCK.value,
            samvil_tier=samvil_tier,
            threshold=thresholds_for_tier,
            failed_checks=failed + escalate_only,
            reason="; ".join(reasons),
            required_action=_required_action_for(failed + escalate_only, metrics),
        )

    if escalate_only:
        return GateVerdict(
            gate=name,
            verdict=Verdict.ESCALATE.value,
            samvil_tier=samvil_tier,
            threshold=thresholds_for_tier,
            failed_checks=escalate_only,
            reason="; ".join(reasons),
            required_action=_required_action_for(escalate_only, metrics),
        )

    return GateVerdict(
        gate=name,
        verdict=Verdict.PASS.value,
        samvil_tier=samvil_tier,
        threshold=thresholds_for_tier,
    )


def _check_single(key: str, required: Any, actual: Any) -> tuple[bool, str]:
    """Evaluate one threshold entry.

    Rules:
      * `required=True` → actual must be truthy.
      * numeric required → actual >= required.
      * string required (schema_version_min) → version compare lex-wise on
        (major, minor, patch). Good enough for "3.2" vs "3.1".
      * None actual is always a miss.
    """
    if actual is None:
        return False, f"{key}: missing"

    if isinstance(required, bool):
        if bool(actual) != required:
            return (
                False,
                f"{key}: required={required}, actual={actual}",
            )
        return True, ""

    if isinstance(required, (int, float)) and isinstance(actual, (int, float)):
        if actual < required:
            return (
                False,
                f"{key}: floor={required}, actual={actual}",
            )
        return True, ""

    if isinstance(required, str) and key == "schema_version_min":
        if _version_ge(str(actual), required):
            return True, ""
        return False, f"{key}: floor={required}, actual={actual}"

    # Default: equality.
    if actual == required:
        return True, ""
    return False, f"{key}: required={required}, actual={actual}"


def _version_ge(actual: str, floor: str) -> bool:
    def parts(s: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in s.strip().split("."))
        except ValueError:
            return (0,)

    a = parts(actual)
    b = parts(floor)
    # pad to same length
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a >= b


def _required_action_for(
    failed_checks: Iterable[str], metrics: dict[str, Any]
) -> RequiredAction:
    """Heuristic mapping from failed checks to a next step.

    Conservative: we return a RequiredAction only when we're confident. When
    unsure, default to `ask_user` so the human can decide rather than the
    harness guessing.
    """
    failed = list(failed_checks)
    if not failed:
        return RequiredAction()

    if "ac_testability" in failed:
        return RequiredAction(
            type="split_ac",
            payload={"reason": "AC testability below floor", "checks": failed},
        )
    if "lifecycle_coverage" in failed:
        return RequiredAction(
            type="run_research",
            payload={"reason": "Lifecycle coverage below floor", "checks": failed},
        )
    if "decision_boundary_clarity" in failed:
        return RequiredAction(
            type="stronger_model",
            payload={"reason": "Decision boundary vague", "checks": failed},
        )
    if "schema_valid" in failed or "schema_version_min" in failed:
        return RequiredAction(
            type="fix_schema",
            payload={"reason": "Seed/blueprint schema invalid", "checks": failed},
        )
    return RequiredAction(
        type="ask_user",
        payload={"checks": failed, "metrics_snapshot": dict(metrics)},
    )


# ── Escalation safety ─────────────────────────────────────────────────


def should_force_user_decision(
    *, gate: str, subject: str, failed_check: str, history: list[dict]
) -> bool:
    """Escalation loop safety: same check escalating twice for the same
    subject forces a user decision (no infinite loop).

    `history` is a list of prior verdicts (dicts) for the same subject.
    """
    count = 0
    for h in history:
        if h.get("gate") != gate:
            continue
        if h.get("subject") != subject:
            continue
        if failed_check in (h.get("failed_checks") or []):
            if h.get("verdict") == Verdict.ESCALATE.value:
                count += 1
    return count >= 2
