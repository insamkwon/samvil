"""Tests for v3.0.0 T3 shared rate budget."""

from pathlib import Path

from samvil_mcp.rate_budget import acquire, release, reset, stats


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
