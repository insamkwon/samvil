"""v3 tree handling for skip_ac.mark_seed_with_external."""

import json
from pathlib import Path

from samvil_mcp.skip_ac import mark_seed_with_external


def _write_analysis(tmp_path: Path, ac_match: str, evidence: str = "components/auth/Login.tsx:12") -> Path:
    project = tmp_path / "proj"
    (project / ".samvil").mkdir(parents=True)
    (project / ".samvil" / "analysis.json").write_text(json.dumps({
        "existing_features": [{
            "ac_match": ac_match,
            "evidence": evidence,
            "reason": "Already implemented",
            "detected_at": "2026-04-19T00:00:00Z",
        }]
    }))
    return project


def test_v3_marks_matching_leaf_as_skipped(tmp_path: Path):
    project = _write_analysis(tmp_path, "user can log in")
    seed = {
        "schema_version": "3.0",
        "features": [{
            "name": "auth",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "user can sign up", "children": [], "status": "pending", "evidence": []},
                {"id": "AC-2", "description": "user can log in", "children": [], "status": "pending", "evidence": []},
            ]
        }]
    }
    out = mark_seed_with_external(seed, str(project))
    acs = out["features"][0]["acceptance_criteria"]
    assert acs[0]["status"] == "pending"  # not matched
    assert acs[1]["status"] == "skipped"
    assert acs[1]["external_reason"] == "Already implemented"
    assert "components/auth/Login.tsx:12" in acs[1]["evidence"]


def test_v3_walks_into_branch_children(tmp_path: Path):
    project = _write_analysis(tmp_path, "validate email format")
    seed = {
        "schema_version": "3.0",
        "features": [{
            "name": "auth",
            "acceptance_criteria": [{
                "id": "AC-1", "description": "user can sign up",
                "children": [
                    {"id": "AC-1.1", "description": "validate email format", "children": [], "status": "pending", "evidence": []},
                    {"id": "AC-1.2", "description": "hash the password", "children": [], "status": "pending", "evidence": []},
                ]
            }]
        }]
    }
    out = mark_seed_with_external(seed, str(project))
    children = out["features"][0]["acceptance_criteria"][0]["children"]
    assert children[0]["status"] == "skipped"  # matched
    assert children[1]["status"] == "pending"  # not matched
    # branch itself is not directly mutated (still has no `status` key)
    branch = out["features"][0]["acceptance_criteria"][0]
    assert "status" not in branch or branch.get("status") == "pending"


def test_v3_no_analysis_is_noop(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    seed = {
        "schema_version": "3.0",
        "features": [{
            "name": "auth",
            "acceptance_criteria": [
                {"id": "AC-1", "description": "x", "children": [], "status": "pending", "evidence": []}
            ]
        }]
    }
    out = mark_seed_with_external(seed, str(project))
    assert out["features"][0]["acceptance_criteria"][0]["status"] == "pending"


def test_v2_keeps_legacy_external_satisfied_flag(tmp_path: Path):
    project = _write_analysis(tmp_path, "user can log in")
    seed = {
        # no schema_version — v2 path
        "features": [{
            "name": "auth",
            "acceptance_criteria": [
                {"description": "user can log in"}
            ]
        }]
    }
    out = mark_seed_with_external(seed, str(project))
    ac = out["features"][0]["acceptance_criteria"][0]
    assert ac["external_satisfied"] is True
    assert ac["external_evidence"] == "components/auth/Login.tsx:12"
