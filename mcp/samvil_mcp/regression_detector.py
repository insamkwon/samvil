"""Regression Detector (v2.5.0, Ouroboros #03/#P5).

Detects ACs that regressed across Evolve cycles (PASS → FAIL).
Used by convergence_gate to enforce P5 Regression Intolerance.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ACRegression:
    """A regressed AC across cycles."""
    ac_id: str
    ac_description: str
    last_pass_cycle: int
    failing_cycle: int
    passing_evidence: tuple[str, ...]  # Evidence that existed when it passed
    failure_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "ac_id": self.ac_id,
            "ac_description": self.ac_description,
            "last_pass_cycle": self.last_pass_cycle,
            "failing_cycle": self.failing_cycle,
            "passing_evidence": list(self.passing_evidence),
            "failure_reason": self.failure_reason,
        }


def detect_regressions(
    current_ac_states: dict[str, str],
    history: list[dict],
) -> list[ACRegression]:
    """Detect ACs that used to pass but now fail.

    Args:
        current_ac_states: {ac_id: "PASS" | "PARTIAL" | "FAIL"} current cycle
        history: list of dicts [{cycle: int, ac_states: {ac_id: verdict}, evidence?: {...}}]

    Returns:
        List of ACRegression. Empty = no regressions.
    """
    regressions = []

    for ac_id, current_verdict in current_ac_states.items():
        if current_verdict == "PASS":
            continue  # no regression possible

        # Walk history backwards to find last PASS
        last_pass_cycle = None
        passing_evidence: tuple[str, ...] = ()
        for entry in reversed(history):
            prev_verdict = entry.get("ac_states", {}).get(ac_id)
            if prev_verdict == "PASS":
                last_pass_cycle = entry.get("cycle", 0)
                passing_evidence = tuple(
                    entry.get("evidence", {}).get(ac_id, [])
                )
                break

        if last_pass_cycle is not None:
            regressions.append(ACRegression(
                ac_id=ac_id,
                ac_description=current_ac_states.get(f"{ac_id}_description", ac_id),
                last_pass_cycle=last_pass_cycle,
                failing_cycle=len(history),
                passing_evidence=passing_evidence,
                failure_reason=f"PASS → {current_verdict}",
            ))

    return regressions


def has_regressions(regressions: list[ACRegression]) -> bool:
    return len(regressions) > 0


def format_regression_message(regressions: list[ACRegression]) -> str:
    """Human-readable message for user."""
    if not regressions:
        return "✓ No regressions detected."
    lines = [f"🛡 {len(regressions)}개 AC 퇴화 감지:"]
    for r in regressions:
        lines.append(
            f"  - {r.ac_id} ({r.ac_description}): "
            f"Cycle {r.last_pass_cycle} PASS → Cycle {r.failing_cycle} FAIL"
        )
    return "\n".join(lines)
