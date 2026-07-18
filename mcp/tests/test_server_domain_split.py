"""Regression checks for mechanical server.py domain extraction."""

from pathlib import Path

from samvil_mcp.server import mcp


PACKAGE = Path(__file__).resolve().parents[1] / "samvil_mcp"


def test_benchmark_tools_are_extracted_without_registry_drift() -> None:
    server_source = (PACKAGE / "server.py").read_text()
    benchmark_source = (PACKAGE / "tools_benchmark.py").read_text()
    tool_names = set(mcp._tool_manager._tools)

    expected = {
        "benchmark_fetch_target",
        "benchmark_classify_items",
        "benchmark_append_gap",
        "benchmark_load_targets",
    }
    assert expected <= tool_names
    assert len(tool_names) == 202
    assert "async def benchmark_" not in server_source
    assert "def register_benchmark_tools" in benchmark_source
    assert benchmark_source.count("@mcp.tool()") == 4
