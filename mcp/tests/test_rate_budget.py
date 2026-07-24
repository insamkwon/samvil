"""Tests for v3.0.0 T3 shared rate budget."""

import json
import time
from contextlib import contextmanager
from pathlib import Path

from samvil_mcp.rate_budget import acquire, heartbeat, release, reset, stats


def test_acquire_below_max(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    r = acquire(str(p), "w1", max_concurrent=2)
    assert r["acquired"] is True
    assert r["current"] == 1


def test_acquire_blocked_at_max(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    acquire(str(p), "w1", max_concurrent=2)
    acquire(str(p), "w2", max_concurrent=2)
    r = acquire(str(p), "w3", max_concurrent=2)
    assert r["acquired"] is False
    assert r["current"] == 2


def test_expired_acquire_does_not_consume_slot(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    p.write_text(json.dumps({
        "ts": time.time() - (30 * 60 + 1),
        "worker_id": "crashed-worker",
        "kind": "acquire",
    }) + "\n")

    r = acquire(str(p), "replacement-worker", max_concurrent=1)

    assert r["acquired"] is True
    assert r["current"] == 1
    assert stats(str(p))["active_workers"] == ["replacement-worker"]


def test_recent_acquire_still_consumes_slot(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    p.write_text(json.dumps({
        "ts": time.time() - 60,
        "worker_id": "live-worker",
        "kind": "acquire",
    }) + "\n")

    r = acquire(str(p), "replacement-worker", max_concurrent=1)

    assert r["acquired"] is False
    assert r["current"] == 1


def test_heartbeat_renews_live_worker_past_original_acquire_ttl(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    now = time.time()
    p.write_text(
        "\n".join(
            [
                json.dumps({"ts": now - 1900, "worker_id": "live-worker", "kind": "acquire"}),
                json.dumps({"ts": now - 60, "worker_id": "live-worker", "kind": "heartbeat"}),
            ]
        )
        + "\n"
    )

    result = acquire(str(p), "replacement-worker", max_concurrent=1)

    assert result["acquired"] is False
    assert stats(str(p))["active_workers"] == ["live-worker"]


def test_heartbeat_does_not_resurrect_expired_worker(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    p.write_text(json.dumps({
        "ts": time.time() - (30 * 60 + 1),
        "worker_id": "expired-worker",
        "kind": "acquire",
    }) + "\n")

    result = heartbeat(str(p), "expired-worker")

    assert result["renewed"] is False


def test_malformed_acquire_timestamp_does_not_consume_slot(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    p.write_text(json.dumps({
        "ts": "not-a-timestamp",
        "worker_id": "malformed-worker",
        "kind": "acquire",
    }) + "\n")

    result = acquire(str(p), "replacement-worker", max_concurrent=1)

    assert result["acquired"] is True
    assert result["current"] == 1
    assert stats(str(p))["active_workers"] == ["replacement-worker"]


def test_release_opens_slot(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    acquire(str(p), "w1", max_concurrent=2)
    acquire(str(p), "w2", max_concurrent=2)
    rel = release(str(p), "w1")
    assert rel["released"] is True
    r = acquire(str(p), "w3", max_concurrent=2)
    assert r["acquired"] is True


def test_release_idempotent_for_unknown_worker(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    rel = release(str(p), "ghost")
    assert rel["released"] is False


def test_acquire_already_held_returns_true_without_double_event(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    acquire(str(p), "w1", max_concurrent=2)
    r = acquire(str(p), "w1", max_concurrent=2)
    assert r["acquired"] is True
    assert "already held" in r["note"]
    st = stats(str(p))
    assert st["total_acquired"] == 1


def test_stats_tracks_peak(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    acquire(str(p), "w1", max_concurrent=5)
    acquire(str(p), "w2", max_concurrent=5)
    acquire(str(p), "w3", max_concurrent=5)
    release(str(p), "w1")
    st = stats(str(p))
    assert st["peak"] == 3
    assert st["active"] == 2
    assert set(st["active_workers"]) == {"w2", "w3"}
    assert st["total_acquired"] == 3
    assert st["total_released"] == 1


def test_stats_empty_log(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    st = stats(str(p))
    assert st == {
        "active": 0,
        "peak": 0,
        "total_acquired": 0,
        "total_released": 0,
        "total_heartbeats": 0,
        "active_workers": [],
    }


def test_reset_wipes_log(tmp_path: Path):
    p = tmp_path / "rb.jsonl"
    acquire(str(p), "w1", max_concurrent=2)
    res = reset(str(p))
    assert res["reset"] is True
    assert res["previous"]["active"] == 1
    st = stats(str(p))
    assert st["active"] == 0


def test_reset_does_not_delete_worker_acquired_after_its_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from samvil_mcp import rate_budget

    p = tmp_path / "rb.jsonl"
    original_locked = rate_budget._locked
    completed_locks = 0

    @contextmanager
    def inject_acquire_after_first_lock(path):
        nonlocal completed_locks
        with original_locked(path):
            yield
        completed_locks += 1
        if completed_locks == 1:
            rate_budget._append_locked(path, "acquire", "late-worker")

    monkeypatch.setattr(rate_budget, "_locked", inject_acquire_after_first_lock)
    result = rate_budget.reset(str(p))
    monkeypatch.setattr(rate_budget, "_locked", original_locked)

    assert result["previous"]["active"] == 0
    assert rate_budget.stats(str(p))["active_workers"] == ["late-worker"]
