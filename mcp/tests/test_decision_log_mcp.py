"""Integration tests for decision-log MCP tool wrappers."""

from __future__ import annotations

import json

from samvil_mcp.decision_log import DecisionADR, write_adr


def test_write_and_read_decision_adr_impl(tmp_path):
    from samvil_mcp.server import (
        _read_decision_adr_impl,
        _write_decision_adr_impl,
    )

    adr = DecisionADR(
        adr_id="adr_mcp",
        title="MCP ADR",
        status="accepted",
        authors=["samvil-council"],
        decision="Expose decision ADRs through MCP.",
    )

    result = _write_decision_adr_impl(str(tmp_path), json.dumps(adr.to_dict()))

    assert result["status"] == "ok"
    assert result["adr_id"] == "adr_mcp"
    assert (tmp_path / ".samvil" / "decisions" / "adr_mcp.md").exists()

    read_result = _read_decision_adr_impl(str(tmp_path), "adr_mcp")
    assert read_result["status"] == "ok"
    assert read_result["adr"]["decision"] == "Expose decision ADRs through MCP."


def test_list_decision_adrs_impl_filters_status(tmp_path):
    from samvil_mcp.server import _list_decision_adrs_impl

    write_adr(
        DecisionADR(
            adr_id="adr_accepted",
            title="Accepted",
            status="accepted",
            authors=["samvil-council"],
        ),
        tmp_path,
    )
    write_adr(
        DecisionADR(adr_id="adr_proposed", title="Proposed", authors=["user"]),
        tmp_path,
    )

    result = _list_decision_adrs_impl(str(tmp_path), status="accepted")

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["adrs"][0]["id"] == "adr_accepted"


def test_read_decision_adr_impl_distinguishes_corrupted(tmp_path):
    from samvil_mcp.server import _read_decision_adr_impl

    path = tmp_path / ".samvil" / "decisions" / "adr_bad.md"
    path.parent.mkdir(parents=True)
    path.write_text("not an ADR", encoding="utf-8")

    result = _read_decision_adr_impl(str(tmp_path), "adr_bad")

    assert result["status"] == "corrupted"


def test_decision_adr_impls_validate_project_root(tmp_path):
    from samvil_mcp.server import _list_decision_adrs_impl

    result = _list_decision_adrs_impl(str(tmp_path / "missing"))

    assert result["status"] == "error"
    assert "not a directory" in result["error"]


def test_supersede_decision_adr_impl(tmp_path):
    from samvil_mcp.server import _supersede_decision_adr_impl

    write_adr(
        DecisionADR(adr_id="adr_old", title="Old", authors=["samvil-council"]),
        tmp_path,
    )
    write_adr(
        DecisionADR(adr_id="adr_new", title="New", authors=["samvil-council"]),
        tmp_path,
    )

    result = _supersede_decision_adr_impl(
        str(tmp_path),
        "adr_old",
        "adr_new",
        "New decision is clearer.",
    )

    assert result["status"] == "ok"
    assert result["adr"]["status"] == "superseded"
    assert result["adr"]["superseded_by"] == "adr_new"


def test_find_decision_adrs_referencing_impl(tmp_path):
    from samvil_mcp.server import _find_decision_adrs_referencing_impl

    write_adr(
        DecisionADR(
            adr_id="adr_server",
            title="Server",
            authors=["samvil-council"],
            evidence=["mcp/samvil_mcp/server.py:2925"],
        ),
        tmp_path,
    )

    result = _find_decision_adrs_referencing_impl(str(tmp_path), "server.py")

    assert result["status"] == "ok"
    assert result["adr_ids"] == ["adr_server"]


def test_promote_council_decision_impl_writes_adr(tmp_path):
    from samvil_mcp.server import _promote_council_decision_impl

    decision = {
        "id": "d001",
        "agent": "simplifier",
        "decision": "Remove dashboard from P1 features",
        "reason": "Scope is too large.",
        "binding": True,
        "applied": True,
        "dissenting": False,
        "consensus_score": 0.67,
    }

    result = _promote_council_decision_impl(str(tmp_path), json.dumps(decision))

    assert result["status"] == "ok"
    assert result["adr"]["id"] == "adr_council_d001"
    assert result["adr"]["status"] == "accepted"
    assert (tmp_path / ".samvil" / "decisions" / "adr_council_d001.md").exists()
