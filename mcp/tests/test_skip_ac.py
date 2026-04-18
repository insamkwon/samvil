"""Tests for skip_ac.py (v2.6.0, #08)."""

import json

import pytest

from samvil_mcp.skip_ac import (
    ExternalSatisfaction,
    load_analysis,
    mark_seed_with_external,
    match_ac_to_existing,
)


def test_fuzzy_match_exact():
    existing = [ExternalSatisfaction("User signup", "src/a.ts:1")]
    match = match_ac_to_existing("User signup", existing)
    assert match is not None
    assert match.evidence == "src/a.ts:1"


def test_fuzzy_match_partial():
    existing = [ExternalSatisfaction(
        "User can sign up with email", "src/a.ts:1",
    )]
    match = match_ac_to_existing("sign up with email", existing)
    assert match is not None


def test_no_match_different_feature():
    existing = [ExternalSatisfaction("User signup", "src/a.ts:1")]
    match = match_ac_to_existing("Product catalog browsing", existing)
    assert match is None


def test_no_match_below_threshold():
    existing = [ExternalSatisfaction("totally different thing", "src/a.ts:1")]
    match = match_ac_to_existing("completely unrelated", existing)
    assert match is None


def test_empty_ac_description():
    existing = [ExternalSatisfaction("User signup", "src/a.ts:1")]
    match = match_ac_to_existing("", existing)
    assert match is None


def test_load_analysis_missing_file(tmp_path):
    result = load_analysis(str(tmp_path))
    assert result == []


def test_load_analysis_valid(tmp_path):
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "analysis.json").write_text(json.dumps({
        "existing_features": [
            {
                "ac_match": "User signup flow",
                "evidence": "src/auth.ts:15",
                "commit": "abc123",
                "reason": "JWT auth existing",
                "detected_at": "2026-04-19T10:00:00Z",
            },
        ],
    }))
    result = load_analysis(str(tmp_path))
    assert len(result) == 1
    assert result[0].ac_description == "User signup flow"
    assert result[0].evidence == "src/auth.ts:15"


def test_load_analysis_corrupt_json(tmp_path):
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "analysis.json").write_text("{invalid json")
    result = load_analysis(str(tmp_path))
    assert result == []


def test_mark_seed_with_external(tmp_path):
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "analysis.json").write_text(json.dumps({
        "existing_features": [
            {"ac_match": "signup flow", "evidence": "src/a.ts:1"},
        ],
    }))
    seed = {"features": [{
        "acceptance_criteria": [
            {"description": "User signup flow"},
        ],
    }]}
    result = mark_seed_with_external(seed, str(tmp_path))
    ac = result["features"][0]["acceptance_criteria"][0]
    assert ac["external_satisfied"] is True
    assert ac["external_evidence"] == "src/a.ts:1"


def test_mark_seed_no_analysis(tmp_path):
    seed = {"features": [{
        "acceptance_criteria": [{"description": "User signup"}],
    }]}
    result = mark_seed_with_external(seed, str(tmp_path))
    ac = result["features"][0]["acceptance_criteria"][0]
    assert "external_satisfied" not in ac


def test_mark_seed_string_acs_ignored(tmp_path):
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "analysis.json").write_text(json.dumps({
        "existing_features": [
            {"ac_match": "test", "evidence": "a.ts:1"},
        ],
    }))
    seed = {"features": [{
        "acceptance_criteria": ["User signup"],  # string, not object
    }]}
    result = mark_seed_with_external(seed, str(tmp_path))
    # Should not crash, string ACs are skipped
    assert result["features"][0]["acceptance_criteria"] == ["User signup"]
