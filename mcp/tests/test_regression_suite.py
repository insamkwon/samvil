"""Tests for regression_suite module (Option B)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.regression_suite import (
    ACEntry,
    GenerationSnapshot,
    RegressionResult,
    CompareResult,
    _load_passing_acs,
    snapshot_generation,
    validate_against_snapshot,
    aggregate_regression_state,
    compare_generations,
)


# ── fixtures ────────────────────────────────────────────────────────────────

def _write_qa_results(project_dir: Path, acs: list[dict]) -> Path:
    """Write a minimal qa-results.json to project_dir/.samvil/."""
    results = {
        "pass1": {"status": "PASS"},
        "pass2": acs,
        "pass3": {"verdict": "PASS"},
    }
    path = project_dir / ".samvil" / "qa-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def _ac(id: str, verdict: str = "PASS", evidence: list[str] | None = None) -> dict:
    return {
        "id": id,
        "criterion": f"User can {id}",
        "verdict": verdict,
        "evidence": evidence or [f"app/{id}.tsx:10"],
    }


# ── ACEntry + GenerationSnapshot dataclass tests ──────────────────────────

class TestDataclasses:
    def test_ac_entry_to_dict(self):
        e = ACEntry(id="AC-1", criterion="Login", verdict="PASS", evidence=["page.tsx:10"])
        d = e.to_dict()
        assert d["id"] == "AC-1"
        assert d["verdict"] == "PASS"
        assert d["evidence"] == ["page.tsx:10"]

    def test_generation_snapshot_to_dict(self):
        snap = GenerationSnapshot(
            generation_id="gen-1",
            created_at="2026-01-01T00:00:00Z",
            passing_ac_count=2,
            total_ac_count=3,
            acs=[ACEntry(id="AC-1", criterion="X", verdict="PASS", evidence=["f:1"])],
        )
        d = snap.to_dict()
        assert d["generation_id"] == "gen-1"
        assert d["schema_version"] == "1.0"
        assert d["passing_ac_count"] == 2
        assert len(d["acs"]) == 1

    def test_regression_result_is_clean_when_no_regressions(self):
        r = RegressionResult(
            snapshot_id="gen-1",
            checked_at="2026-01-01T00:00:00Z",
            total_checked=3,
            passing=3,
            regressed=0,
            new_passes=0,
            regressed_ids=[],
        )
        assert r.status == "clean"

    def test_regression_result_is_regression_when_any_regressed(self):
        r = RegressionResult(
            snapshot_id="gen-1",
            checked_at="2026-01-01T00:00:00Z",
            total_checked=3,
            passing=2,
            regressed=1,
            new_passes=0,
            regressed_ids=["AC-2"],
        )
        assert r.status == "regression"

    def test_compare_result_to_dict(self):
        cr = CompareResult(gen_a="gen-1", gen_b="gen-2", added=["AC-3"], removed=[], changed=[])
        d = cr.to_dict()
        assert d["gen_a"] == "gen-1"
        assert d["added"] == ["AC-3"]


class TestLoadPassingAcs:
    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _load_passing_acs(str(tmp_path))
        assert result == []

    def test_loads_passing_acs_from_qa_results(self, tmp_path):
        _write_qa_results(tmp_path, [
            _ac("AC-1", verdict="PASS"),
            _ac("AC-2", verdict="FAIL"),
            _ac("AC-3", verdict="PASS"),
        ])
        result = _load_passing_acs(str(tmp_path))
        assert len(result) == 2
        assert all(a["verdict"] == "PASS" for a in result)

    def test_empty_pass2_returns_empty(self, tmp_path):
        _write_qa_results(tmp_path, [])
        result = _load_passing_acs(str(tmp_path))
        assert result == []

    def test_custom_path_override(self, tmp_path):
        custom = tmp_path / "custom-qa.json"
        custom.write_text(json.dumps({
            "pass2": [_ac("X-1", verdict="PASS")],
        }), encoding="utf-8")
        result = _load_passing_acs(str(tmp_path), qa_results_path=str(custom))
        assert len(result) == 1
        assert result[0]["id"] == "X-1"


class TestSnapshotGeneration:
    def test_creates_snapshot_file(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snap = snapshot_generation(str(tmp_path))
        snap_path = tmp_path / ".samvil" / "generations" / snap.generation_id / "snapshot.json"
        assert snap_path.exists()

    def test_first_snapshot_is_gen_1(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path))
        assert snap.generation_id == "gen-1"

    def test_second_snapshot_is_gen_2(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path))
        snap2 = snapshot_generation(str(tmp_path))
        assert snap2.generation_id == "gen-2"

    def test_explicit_generation_id(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path), generation_id="gen-5")
        assert snap.generation_id == "gen-5"
        assert (tmp_path / ".samvil" / "generations" / "gen-5" / "snapshot.json").exists()

    def test_only_passing_acs_in_snapshot(self, tmp_path):
        _write_qa_results(tmp_path, [
            _ac("AC-1", verdict="PASS"),
            _ac("AC-2", verdict="FAIL"),
            _ac("AC-3", verdict="PASS"),
        ])
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 2
        assert snap.total_ac_count == 3
        assert all(a.verdict == "PASS" for a in snap.acs)

    def test_snapshot_json_is_valid(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path))
        snap_path = tmp_path / ".samvil" / "generations" / snap.generation_id / "snapshot.json"
        loaded = json.loads(snap_path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert loaded["generation_id"] == snap.generation_id
        assert isinstance(loaded["acs"], list)

    def test_empty_qa_results_yields_zero_passing(self, tmp_path):
        _write_qa_results(tmp_path, [])
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 0
        assert snap.acs == []

    def test_missing_qa_results_yields_empty_snapshot(self, tmp_path):
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 0
        assert snap.total_ac_count == 0


class TestValidateAgainstSnapshot:
    def test_clean_when_no_regressions(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.status == "clean"
        assert result.regressed == 0
        assert result.regressed_ids == []

    def test_detects_regression(self, tmp_path):
        # gen-1: AC-1 PASS, AC-2 PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        # Now AC-2 regresses to FAIL
        _write_qa_results(tmp_path, [_ac("AC-1", "PASS"), _ac("AC-2", "FAIL")])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.status == "regression"
        assert result.regressed == 1
        assert "AC-2" in result.regressed_ids

    def test_new_passes_counted(self, tmp_path):
        # gen-1: only AC-1 PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2", "FAIL")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        # Now AC-2 also PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.new_passes == 1
        assert result.status == "clean"

    def test_missing_snapshot_returns_zero_result(self, tmp_path):
        result = validate_against_snapshot(str(tmp_path), "gen-99")
        assert result.total_checked == 0
        assert result.status == "clean"

    def test_result_to_dict_has_status(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        d = result.to_dict()
        assert "status" in d
        assert "snapshot_id" in d
        assert d["snapshot_id"] == "gen-1"

    def test_multiple_regressions(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [
            _ac("AC-1", "FAIL"), _ac("AC-2", "FAIL"), _ac("AC-3", "PASS"),
        ])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.regressed == 2
        assert set(result.regressed_ids) == {"AC-1", "AC-2"}


class TestAggregateRegressionState:
    def test_empty_state_when_no_generations(self, tmp_path):
        state = aggregate_regression_state(str(tmp_path))
        assert state["generation_count"] == 0
        assert state["generations"] == []
        assert state["latest_generation_id"] is None
        assert state["has_regression_history"] is False

    def test_counts_one_generation(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        state = aggregate_regression_state(str(tmp_path))
        assert state["generation_count"] == 1
        assert state["latest_generation_id"] == "gen-1"
        assert state["has_regression_history"] is False

    def test_has_regression_history_after_two_gens(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        state = aggregate_regression_state(str(tmp_path))
        assert state["has_regression_history"] is True
        assert state["generation_count"] == 2

    def test_generation_summaries_include_counts(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        state = aggregate_regression_state(str(tmp_path))
        gen = state["generations"][0]
        assert gen["passing_ac_count"] == 2
        assert gen["total_ac_count"] == 2


class TestCompareGenerations:
    def test_no_changes_when_same_acs(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert cr.added == []
        assert cr.removed == []
        assert cr.changed == []

    def test_detects_added_ac(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert "AC-2" in cr.added

    def test_detects_removed_ac(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert "AC-2" in cr.removed

    def test_missing_gen_a_returns_empty_result(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert cr.gen_a == "gen-1"

    def test_to_dict_contains_all_fields(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        d = compare_generations(str(tmp_path), "gen-1", "gen-2").to_dict()
        assert "gen_a" in d and "gen_b" in d
        assert "added" in d and "removed" in d and "changed" in d
