"""Tests for evolve proposal materialization."""

from __future__ import annotations

import json

from samvil_mcp.evolve_proposal import (
    build_evolve_proposal,
    evolve_proposal_summary,
    materialize_evolve_proposal,
    read_evolve_proposal,
    render_evolve_proposal,
)


def _context() -> dict:
    return {
        "current_seed": {"name": "task-app", "version": 1},
        "qa": {
            "verdict": "REVISE",
            "reason": "functional QA found unimplemented ACs",
            "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"],
            "convergence": {"verdict": "blocked"},
        },
        "focus": {"area": "functional_spec", "issue_ids": ["pass2:AC-1:UNIMPLEMENTED"]},
        "routing": {"next_skill": "samvil-evolve", "route_type": "seed_evolve", "reason": "functional"},
    }


def test_build_evolve_proposal_from_context(tmp_path):
    proposal = build_evolve_proposal(tmp_path, _context())

    assert proposal["status"] == "ready"
    assert proposal["seed_name"] == "task-app"
    assert proposal["from_version"] == 1
    assert proposal["to_version"] == 2
    assert proposal["proposed_changes"][0]["type"] == "clarify_or_split_ac"
    assert proposal["next_action"] == "review/apply evolve proposal"


def test_materialize_evolve_proposal_writes_json_and_markdown(tmp_path):
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "evolve-context.json").write_text(json.dumps(_context()), encoding="utf-8")

    result = materialize_evolve_proposal(tmp_path)
    proposal = read_evolve_proposal(tmp_path)
    rendered = render_evolve_proposal(proposal)
    summary = evolve_proposal_summary(tmp_path)

    assert result["changes"] == 1
    assert proposal["proposed_changes"][0]["target"] == "AC-1"
    assert "# Evolve Proposal" in rendered
    assert (tmp_path / ".samvil" / "evolve-proposal.md").exists()
    assert summary["present"] is True
    assert summary["changes"] == 1
