"""Tests for QA recovery routing."""

from __future__ import annotations

import json

from samvil_mcp.qa_routing import (
    build_qa_recovery_routing,
    materialize_qa_recovery_routing,
    qa_routing_summary,
    read_qa_recovery_routing,
)


def _results(issue_ids: list[str], *, convergence: str = "blocked") -> dict:
    return {
        "synthesis": {
            "verdict": "REVISE",
            "reason": "functional QA found unimplemented ACs",
            "next_action": "replace stubs or hardcoded paths with real implementation",
            "issue_ids": issue_ids,
        },
        "convergence": {
            "gate": "qa_convergence",
            "verdict": convergence,
            "reason": "identical QA issues persisted across two consecutive iterations",
            "next_action": "manual intervention: evolve seed, skip to retro, or fix manually",
            "issue_ids": issue_ids,
        },
    }


def test_functional_blocked_qa_uses_canonical_retro_default(tmp_path):
    routing = build_qa_recovery_routing(tmp_path, _results(["pass2:AC-1:UNIMPLEMENTED"]))

    assert routing["primary_route"]["next_skill"] == "samvil-retro"
    assert routing["primary_route"]["route_type"] == "retro"
    assert routing["next_skill_marker"]["next_skill"] == "samvil-retro"
    assert any(
        route["next_skill"] == "samvil-evolve"
        for route in routing["alternative_routes"]
    )
    assert routing["issue_families"]["pass2"] == 1


def test_quality_blocked_qa_uses_canonical_retro_default(tmp_path):
    routing = build_qa_recovery_routing(tmp_path, _results(["pass3:missing-focus-state"]))

    assert routing["primary_route"]["next_skill"] == "samvil-retro"
    assert routing["primary_route"]["route_type"] == "retro"
    assert any(route["next_skill"] == "samvil-build" for route in routing["alternative_routes"])
    assert any(route["next_skill"] == "samvil-evolve" for route in routing["alternative_routes"])


def test_materialize_qa_recovery_routing_writes_marker(tmp_path):
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "qa-results.json").write_text(
        json.dumps(_results(["pass2:AC-1:UNIMPLEMENTED"])),
        encoding="utf-8",
    )

    result = materialize_qa_recovery_routing(tmp_path)

    assert result["primary_route"]["next_skill"] == "samvil-retro"
    persisted = read_qa_recovery_routing(tmp_path)
    assert persisted["primary_route"]["next_skill"] == "samvil-retro"
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))
    assert marker["schema_version"] == "1.0"
    assert marker["chain_via"] == "file_marker"
    assert marker["next_skill"] == "samvil-retro"
    summary = qa_routing_summary(tmp_path)
    assert summary["present"] is True
    assert summary["next_skill"] == "samvil-retro"
