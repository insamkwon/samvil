"""v3-010 atomic counter regression test.

Hammer `_log_mcp_health("ok", tool)` from N threads and confirm the per-tool
counter sees exactly N increments. Without the lock this test fails ~10% of
the time on Python 3.12 (the actual race window is small but real).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from samvil_mcp import server


def test_health_log_path_uses_test_override(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "isolated-health.jsonl"
    monkeypatch.setenv("SAMVIL_MCP_HEALTH_PATH", str(target))

    assert server._health_log_path() == target


def test_health_log_rotates_one_generation(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "mcp-health.jsonl"
    old_payload = b"x" * 129
    log_path.write_bytes(old_payload)
    monkeypatch.setattr(server, "_HEALTH_LOG_MAX_BYTES", 128)

    server._rotate_health_log(log_path)

    assert not log_path.exists()
    assert (tmp_path / "mcp-health.jsonl.1").read_bytes() == old_payload


def test_pytest_health_log_is_isolated_from_user_home() -> None:
    configured = Path(os.environ["SAMVIL_MCP_HEALTH_PATH"])
    assert configured.name == "mcp-health.jsonl"
    assert configured != Path.home() / ".samvil" / "mcp-health.jsonl"


def test_health_counter_is_atomic_under_concurrency(monkeypatch, tmp_path) -> None:
    # Reset counters
    server._HEALTH_OK_COUNTS.clear()

    N_THREADS = 40
    CALLS_PER_THREAD = 50
    TOTAL = N_THREADS * CALLS_PER_THREAD

    def worker() -> None:
        for _ in range(CALLS_PER_THREAD):
            server._log_mcp_health("ok", "atomic_test_tool")

    threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = server._HEALTH_OK_COUNTS.get("atomic_test_tool", 0)
    assert final == TOTAL, (
        f"Atomic counter lost increments under concurrency: "
        f"expected {TOTAL}, got {final} (missing {TOTAL - final})"
    )


def test_lock_exists() -> None:
    assert hasattr(server, "_HEALTH_OK_COUNTS_LOCK")
    assert isinstance(server._HEALTH_OK_COUNTS_LOCK, type(threading.Lock()))
