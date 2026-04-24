"""Retro (⑧) — 4-stage policy evolution schema for v3.2.

Per HANDOFF-v3.2-DECISIONS.md §3.⑧, retro now has four lifecycle stages:

  observations    — what happened
  hypotheses      — what we think it means
  policy_experiments — candidate rules under observation (N runs)
  adopted_policies / rejected_policies — post-promotion state

Numbers-as-experiments: the bootstrap script
`scripts/seed-experiments.py` already walked the handoff and registered
every `(initial estimate)` as an `experimental_policy` with default
`N = 5`. After 5 recorded runs, retro decides: promote, adjust value, or
reject.

This module owns:
  * Retro dataclasses that serialize cleanly to `.samvil/retro/`.
  * `record_run` for attaching observations to an experiment.
  * `promote` / `reject` helpers.
  * Supersession chain builder.

Storage is YAML-first (v3.1 `scripts/view-retro.py` already reads YAML),
but any caller that prefers JSON can pass dicts directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExperimentStage(str, Enum):
    EXPERIMENTAL = "experimental"
    ADOPTED = "adopted"
    REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Observation:
    id: str
    area: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    severity: str = Severity.LOW.value
    category: str = ""  # e.g. "gate_vs_p8_boundary", "escalation_loop"
    ts: str = field(default_factory=_now)


@dataclass
class Hypothesis:
    id: str
    refs_observations: list[str]
    statement: str
    confidence: float = 0.5  # 0..1


@dataclass
class ExperimentRun:
    ts: str
    value_seen: Any = None
    verdict: str = ""
    note: str = ""
    source: str = ""  # "dogfood" | "synthetic" | "manual"


@dataclass
class PolicyExperiment:
    id: str
    rule: str
    refs_hypothesis: str | None = None
    valid_for: str = "5 runs"
    started_at: str = field(default_factory=_now)
    results: list[ExperimentRun] = field(default_factory=list)
    stage: str = ExperimentStage.EXPERIMENTAL.value

    def record_run(self, run: ExperimentRun) -> None:
        self.results.append(run)

    def should_promote(self, n_runs: int = 5) -> bool:
        """Ready for promotion iff it has ≥ n_runs and no run recorded
        a harmful verdict (we're strict here: any verdict != 'pass' or
        'bootstrap_pass' blocks promotion).
        """
        if len(self.results) < n_runs:
            return False
        bad = [r for r in self.results if r.verdict not in ("pass", "bootstrap_pass")]
        return not bad


@dataclass
class AdoptedPolicy:
    id: str
    rule: str
    promoted_from_experiment: str
    adopted_at: str = field(default_factory=_now)
    supersedes: list[str] = field(default_factory=list)


@dataclass
class RejectedPolicy:
    id: str
    rule: str
    reason: str
    rejected_at: str = field(default_factory=_now)


@dataclass
class RetroReport:
    retro_version: str = "3.2"
    observations: list[Observation] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    policy_experiments: list[PolicyExperiment] = field(default_factory=list)
    adopted_policies: list[AdoptedPolicy] = field(default_factory=list)
    rejected_policies: list[RejectedPolicy] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "retro_version": self.retro_version,
            "observations": [asdict(o) for o in self.observations],
            "hypotheses": [asdict(h) for h in self.hypotheses],
            "policy_experiments": [
                _exp_to_dict(e) for e in self.policy_experiments
            ],
            "adopted_policies": [asdict(a) for a in self.adopted_policies],
            "rejected_policies": [asdict(r) for r in self.rejected_policies],
        }


def _exp_to_dict(e: PolicyExperiment) -> dict:
    d = asdict(e)
    return d


# ── I/O ───────────────────────────────────────────────────────────────


def save_retro(report: RetroReport, path: str | Path) -> None:
    """Write YAML if PyYAML is available, JSON otherwise.

    The file path convention is `.samvil/retro/retro-{run_id}.yaml`.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = report.to_dict()
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    except Exception:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    p.write_text(text)


def load_retro(path: str | Path) -> RetroReport:
    p = Path(path)
    if not p.exists():
        return RetroReport()
    text = p.read_text()
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
    except Exception:
        try:
            data = json.loads(text)
        except Exception:
            return RetroReport()
    return _from_dict(data)


def _from_dict(data: dict) -> RetroReport:
    return RetroReport(
        retro_version=data.get("retro_version", "3.2"),
        observations=[Observation(**o) for o in data.get("observations", [])],
        hypotheses=[Hypothesis(**h) for h in data.get("hypotheses", [])],
        policy_experiments=[
            PolicyExperiment(
                id=e["id"],
                rule=e["rule"],
                refs_hypothesis=e.get("refs_hypothesis"),
                valid_for=e.get("valid_for", "5 runs"),
                started_at=e.get("started_at", _now()),
                results=[ExperimentRun(**r) for r in e.get("results", [])],
                stage=e.get("stage", ExperimentStage.EXPERIMENTAL.value),
            )
            for e in data.get("policy_experiments", [])
        ],
        adopted_policies=[AdoptedPolicy(**a) for a in data.get("adopted_policies", [])],
        rejected_policies=[RejectedPolicy(**r) for r in data.get("rejected_policies", [])],
    )


# ── Promotion / supersession ─────────────────────────────────────────


def promote(
    report: RetroReport,
    experiment_id: str,
    *,
    supersedes: list[str] | None = None,
) -> AdoptedPolicy | None:
    """Move an experiment from `experimental` → `adopted`.

    Returns the new AdoptedPolicy, or None when the experiment can't be
    promoted (not found, already adopted/rejected, not enough runs).
    """
    for e in report.policy_experiments:
        if e.id == experiment_id:
            break
    else:
        return None
    if e.stage != ExperimentStage.EXPERIMENTAL.value:
        return None
    if not e.should_promote():
        return None
    e.stage = ExperimentStage.ADOPTED.value
    policy = AdoptedPolicy(
        id=f"{experiment_id}_adopted",
        rule=e.rule,
        promoted_from_experiment=experiment_id,
        supersedes=list(supersedes or []),
    )
    report.adopted_policies.append(policy)
    return policy


def reject(
    report: RetroReport,
    experiment_id: str,
    *,
    reason: str,
) -> RejectedPolicy | None:
    for e in report.policy_experiments:
        if e.id == experiment_id:
            break
    else:
        return None
    if e.stage != ExperimentStage.EXPERIMENTAL.value:
        return None
    e.stage = ExperimentStage.REJECTED.value
    policy = RejectedPolicy(
        id=f"{experiment_id}_rejected",
        rule=e.rule,
        reason=reason,
    )
    report.rejected_policies.append(policy)
    return policy
