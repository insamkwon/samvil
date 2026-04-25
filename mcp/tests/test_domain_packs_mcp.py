"""MCP wrapper tests for Domain Packs."""

from samvil_mcp.server import (
    list_domain_packs,
    read_domain_pack,
    render_domain_context,
)


def test_list_domain_packs_tool_filters_solution_type():
    result = list_domain_packs(solution_type="mobile-app")

    assert result["status"] == "ok"
    ids = {pack["pack_id"] for pack in result["packs"]}
    assert ids == {"mobile-habit"}


def test_list_domain_packs_tool_filters_stage():
    result = list_domain_packs(stage="interview")

    assert result["status"] == "ok"
    assert result["count"] == 3


def test_read_domain_pack_tool_returns_missing():
    result = read_domain_pack("does-not-exist")

    assert result == {"status": "missing"}


def test_render_domain_context_tool_returns_stage_scoped_markdown():
    result = render_domain_context(solution_type="game", stage="qa")

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert "browser-game" in result["context"]
    assert "QA focus" in result["context"]
    assert "Interview probes" not in result["context"]
