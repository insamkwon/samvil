"""Convergence Gate — 5 independent `evolve_checks` (v2.5.0, Ouroboros #03).

Per v3.2 glossary: these are **evolve_checks**, not "gates". The word
``gate`` is reserved for the 8 stage gates in §3.⑥. The class is still
called `ConvergenceGate` for source-compat with v3.1 callers; the module
docstring, event log labels, and docs use the new name.

Prevents "blind convergence" in Evolve by requiring ALL 5 evolve_checks to pass:
  1. Eval check — overall score ≥ 0.7 AND final_approved
  2. Per-AC check — all ACs passing (mode='all') or majority (mode='majority')
  3. Regression check — no AC regressed from prior cycles
  4. Evolution check — at least one actual mutation occurred (evolved_count > 0)
  5. Validation check — validation not skipped/errored

Implements Manifesto v3 P5 Regression Intolerance + proof-of-progress philosophy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .regression_detector import detect_regressions, ACRegression


GateName = Literal["eval", "per_ac", "regression", "evolution", "validation"]
ACGateMode = Literal["all", "majority", "none"]


@dataclass(frozen=True)
class GateConfig:
    """Configuration for convergence gates."""
    eval_gate_enabled: bool = True
    eval_score_threshold: float = 0.7
    ac_gate_mode: ACGateMode = "all"
    regression_gate_enabled: bool = True
    evolution_gate_enabled: bool = True
    validation_gate_enabled: bool = True


@dataclass(frozen=True)
class ConvergenceVerdict:
    """Final verdict after running all gates."""
    converged: bool
    blocked_by: tuple[GateName, ...] = ()
    reasons: tuple[str, ...] = ()
    regressions: tuple[ACRegression, ...] = ()

    def to_dict(self) -> dict:
        return {
            "converged": self.converged,
            "blocked_by": list(self.blocked_by),
            "reasons": list(self.reasons),
            "regressions": [r.to_dict() for r in self.regressions],
        }


def check_eval_gate(eval_result: dict, config: GateConfig) -> dict:
    """Gate 1: Overall evaluation quality."""
    if not config.eval_gate_enabled:
        return {"passed": True, "reason": "Eval gate disabled"}

    score = float(eval_result.get("score", 0.0))
    final_approved = bool(eval_result.get("final_approved", False))

    if score < config.eval_score_threshold:
        return {
            "passed": False,
            "reason": f"Eval score {score} < threshold {config.eval_score_threshold}",
        }
    if not final_approved:
        return {
            "passed": False,
            "reason": "Not final_approved",
        }
    return {"passed": True, "reason": "Eval OK"}


def check_per_ac_gate(eval_result: dict, config: GateConfig) -> dict:
    """Gate 2: Per-AC pass requirement."""
    if config.ac_gate_mode == "none":
        return {"passed": True, "reason": "Per-AC gate disabled"}

    ac_states = eval_result.get("ac_states", {})
    if not ac_states:
        return {"passed": False, "reason": "No AC states provided"}

    failed = [ac_id for ac_id, verdict in ac_states.items() if verdict != "PASS"]
    total = len(ac_states)

    if config.ac_gate_mode == "all":
        if failed:
            return {
                "passed": False,
                "reason": f"{len(failed)}/{total} AC failing: {failed[:5]}",
                "failed_acs": failed,
            }
    elif config.ac_gate_mode == "majority":
        if len(failed) > total / 2:
            return {
                "passed": False,
                "reason": f"Majority failing ({len(failed)}/{total})",
                "failed_acs": failed,
            }

    return {"passed": True, "reason": f"{total - len(failed)}/{total} PASS"}


def check_regression_gate(
    eval_result: dict,
    history: list[dict],
    config: GateConfig,
) -> dict:
    """Gate 3: No AC should regress from previous cycles."""
    if not config.regression_gate_enabled:
        return {"passed": True, "reason": "Regression gate disabled"}

    current_states = eval_result.get("ac_states", {})
    regressions = detect_regressions(current_states, history)

    if regressions:
        return {
            "passed": False,
            "reason": f"{len(regressions)} AC regressed",
            "regressions": regressions,
        }
    return {"passed": True, "reason": "No regressions"}


def check_evolution_gate(history: list[dict], config: GateConfig) -> dict:
    """Gate 4: At least one actual mutation must have occurred."""
    if not config.evolution_gate_enabled:
        return {"passed": True, "reason": "Evolution gate disabled"}

    evolved_count = sum(1 for h in history if h.get("mutations"))

    if evolved_count == 0:
        return {
            "passed": False,
            "reason": "No mutations across any cycle — stagnant loop",
        }
    return {"passed": True, "reason": f"{evolved_count} cycles with mutations"}


def check_validation_gate(eval_result: dict, config: GateConfig) -> dict:
    """Gate 5: Validation was performed (not skipped)."""
    if not config.validation_gate_enabled:
        return {"passed": True, "reason": "Validation gate disabled"}

    status = eval_result.get("validation_status", "ok")
    if status in ("skipped", "error", "timeout"):
        return {
            "passed": False,
            "reason": f"Validation status: {status}",
        }
    return {"passed": True, "reason": "Validation OK"}


def check_all_gates(
    eval_result: dict,
    history: list[dict],
    config: GateConfig | None = None,
) -> ConvergenceVerdict:
    """Run all 5 evolve_checks. Return ConvergenceVerdict."""
    config = config or GateConfig()

    gates = [
        ("eval", check_eval_gate(eval_result, config)),
        ("per_ac", check_per_ac_gate(eval_result, config)),
        ("regression", check_regression_gate(eval_result, history, config)),
        ("evolution", check_evolution_gate(history, config)),
        ("validation", check_validation_gate(eval_result, config)),
    ]

    blocked_by = []
    reasons = []
    regressions = ()

    for name, result in gates:
        if not result["passed"]:
            blocked_by.append(name)
            reasons.append(f"[{name}] {result['reason']}")
            if name == "regression" and "regressions" in result:
                regressions = tuple(result["regressions"])

    return ConvergenceVerdict(
        converged=len(blocked_by) == 0,
        blocked_by=tuple(blocked_by),
        reasons=tuple(reasons),
        regressions=regressions,
    )
