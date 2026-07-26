"""Regression checks for mechanical server.py domain extraction."""

from pathlib import Path
import asyncio
import json
import threading
import time

import pytest

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
    assert len(tool_names) == 206
    assert "async def benchmark_" not in server_source
    assert "def register_benchmark_tools" in benchmark_source
    assert benchmark_source.count("@mcp.tool()") == 4


@pytest.mark.asyncio
async def test_benchmark_fetch_runs_outside_event_loop_thread(monkeypatch) -> None:
    main_thread = threading.get_ident()

    def fake_fetch(*, url: str, timeout: float) -> dict:
        return {"ok": True, "thread_id": threading.get_ident()}

    monkeypatch.setattr(
        "samvil_mcp.benchmark.fetch_external_changelog",
        fake_fetch,
    )
    tool = mcp._tool_manager._tools["benchmark_fetch_target"]

    result = json.loads(await tool.fn("https://example.com/changelog", 1.0))

    assert result["thread_id"] != main_thread


@pytest.mark.asyncio
async def test_ac_verification_runs_outside_event_loop_thread(monkeypatch) -> None:
    from samvil_mcp import ac_verification
    from samvil_mcp.server import collect_ac_verification

    main_thread = threading.get_ident()

    def fake_run(*args, **kwargs) -> dict:
        time.sleep(0.1)
        return {
            "passed": True,
            "thread_id": threading.get_ident(),
        }

    monkeypatch.setattr(ac_verification, "run_ac_verification", fake_run)

    started = time.monotonic()
    verification = asyncio.create_task(
        collect_ac_verification(".", "AC-1", '{"command":"true"}')
    )
    await asyncio.sleep(0.01)
    ticker_elapsed = time.monotonic() - started
    result = json.loads(await verification)

    assert ticker_elapsed < 0.05
    assert result["thread_id"] != main_thread
