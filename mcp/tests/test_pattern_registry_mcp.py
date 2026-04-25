"""MCP wrapper tests for Pattern Registry."""

from samvil_mcp.server import list_patterns, read_pattern, render_pattern_context


def test_list_patterns_tool_filters_solution_type():
    result = list_patterns(solution_type="dashboard")

    assert result["status"] == "ok"
    ids = {p["pattern_id"] for p in result["patterns"]}
    assert "dashboard-recharts" in ids


def test_read_pattern_tool_returns_missing():
    result = read_pattern("does-not-exist")

    assert result == {"status": "missing"}


def test_render_pattern_context_tool_returns_markdown():
    result = render_pattern_context(framework="phaser")

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert "phaser-game" in result["context"]
