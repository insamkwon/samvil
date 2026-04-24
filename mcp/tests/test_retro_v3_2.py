"""Unit tests for retro v3.2 (Sprint 5a, ⑧)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.retro_v3_2 import (
    AdoptedPolicy,
    ExperimentRun,
    ExperimentStage,
    Hypothesis,
    Observation,
    PolicyExperiment,
    RejectedPolicy,
    RetroReport,
    Severity,
    load_retro,
    promote,
    reject,
    save_retro,
)


def test_observation_defaults() -> None:
    o = Observation(id="o1", area="build", summary="build slow")
    assert o.severity == Severity.LOW.value
    assert o.ts  # populated


def test_policy_experiment_should_promote_requires_enough_runs() -> None:
    e = PolicyExperiment(id="e1", rule="threshold = 0.85")
    for _ in range(4):
        e.record_run(ExperimentRun(ts="x", verdict="pass"))
    assert not e.should_promote()
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    assert e.should_promote()


def test_policy_experiment_blocked_by_bad_verdict() -> None:
    e = PolicyExperiment(id="e1", rule="t")
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    e.record_run(ExperimentRun(ts="x", verdict="fail"))
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    # Five runs but one fail → blocked.
    assert not e.should_promote()


def test_promote_happy_path() -> None:
    report = RetroReport()
    e = PolicyExperiment(id="e1", rule="floor=0.85")
    for _ in range(5):
        e.record_run(ExperimentRun(ts="x", verdict="pass"))
    report.policy_experiments.append(e)
    adopted = promote(report, "e1")
    assert adopted is not None
    assert e.stage == ExperimentStage.ADOPTED.value
    assert adopted.promoted_from_experiment == "e1"


def test_promote_rejects_unknown_id() -> None:
    report = RetroReport()
    assert promote(report, "nope") is None


def test_promote_rejects_insufficient_runs() -> None:
    report = RetroReport()
    e = PolicyExperiment(id="e1", rule="floor=0.85")
    e.record_run(ExperimentRun(ts="x", verdict="pass"))
    report.policy_experiments.append(e)
    assert promote(report, "e1") is None


def test_reject_happy_path() -> None:
    report = RetroReport()
    e = PolicyExperiment(id="e1", rule="floor=0.5")
    report.policy_experiments.append(e)
    rejected = reject(report, "e1", reason="floor too low")
    assert rejected is not None
    assert e.stage == ExperimentStage.REJECTED.value


def test_supersession_recorded() -> None:
    report = RetroReport()
    e = PolicyExperiment(id="e2", rule="floor=0.90")
    for _ in range(5):
        e.record_run(ExperimentRun(ts="x", verdict="pass"))
    report.policy_experiments.append(e)
    adopted = promote(report, "e2", supersedes=["e1_adopted"])
    assert adopted is not None
    assert adopted.supersedes == ["e1_adopted"]


def test_round_trip_serialization_json(tmp_path: Path) -> None:
    report = RetroReport()
    report.observations.append(
        Observation(id="o1", area="qa", summary="evidence missing on AC-1", severity="high")
    )
    report.hypotheses.append(
        Hypothesis(id="h1", refs_observations=["o1"], statement="Judge is lax", confidence=0.7)
    )
    path = tmp_path / "retro-001.yaml"
    save_retro(report, path)
    loaded = load_retro(path)
    assert len(loaded.observations) == 1
    assert loaded.observations[0].severity == "high"
    assert loaded.hypotheses[0].confidence == 0.7


def test_load_retro_missing_path_returns_empty(tmp_path: Path) -> None:
    r = load_retro(tmp_path / "nope.yaml")
    assert r.observations == []
    assert r.policy_experiments == []
