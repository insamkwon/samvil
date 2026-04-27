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
