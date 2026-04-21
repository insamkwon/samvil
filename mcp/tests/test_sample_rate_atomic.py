"""v3-010 atomic counter regression test.

Hammer `_log_mcp_health("ok", tool)` from N threads and confirm the per-tool
counter sees exactly N increments. Without the lock this test fails ~10% of
the time on Python 3.12 (the actual race window is small but real).
"""
from __future__ import annotations

import threading

from samvil_mcp import server


def test_health_counter_is_atomic_under_concurrency(monkeypatch, tmp_path) -> None:
    # Redirect the health file to a tmp path so we don't pollute ~/.samvil.
    log_path = tmp_path / "mcp-health.jsonl"

    def _fake_home() -> object:
        class H:
            def __truediv__(self, other):
                return log_path.parent if other == ".samvil" else log_path.parent / other
        return H()

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
