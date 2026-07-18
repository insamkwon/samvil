"""Shared pytest isolation for process-global SAMVIL artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_mcp_health_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep MCP health writes out of the user's global SAMVIL log."""
    path = tmp_path / "mcp-health.jsonl"
    monkeypatch.setenv("SAMVIL_MCP_HEALTH_PATH", str(path))
    return path
