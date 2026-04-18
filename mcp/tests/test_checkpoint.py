"""Tests for checkpoint.py (v2.6.0, #07)."""

import asyncio
import json

import pytest

from samvil_mcp.checkpoint import (
    CheckpointData,
    CheckpointStore,
    PeriodicCheckpointer,
    RecoveryManager,
)


def test_checkpoint_data_create_and_verify():
    cp = CheckpointData.create("s1", "build", {"x": 1})
    assert cp.verify()
    assert cp.seed_id == "s1"
    assert cp.phase == "build"


def test_checkpoint_data_tampered_fails():
    cp = CheckpointData.create("s1", "build", {"x": 1})
    bad = CheckpointData(
        seed_id=cp.seed_id,
        phase=cp.phase,
        state={"x": 2},
        timestamp=cp.timestamp,
        hash=cp.hash,
    )
    assert not bad.verify()


def test_store_save_load_roundtrip(tmp_path):
    store = CheckpointStore(tmp_path)
    cp = CheckpointData.create("s1", "build", {"x": 1})
    store.save(cp)
    loaded = store.load("s1")
    assert loaded is not None
    assert loaded.state == {"x": 1}
    assert loaded.verify()


def test_store_rotation(tmp_path):
    store = CheckpointStore(tmp_path)
    for i in range(5):
        cp = CheckpointData.create("s1", "build", {"i": i})
        store.save(cp)
    loaded = store.load("s1")
    assert loaded is not None
    assert loaded.state == {"i": 4}


def test_store_fallback_to_older(tmp_path):
    store = CheckpointStore(tmp_path)
    for i in range(3):
        cp = CheckpointData.create("s1", "build", {"i": i})
        store.save(cp)

    # Corrupt current
    (tmp_path / "checkpoint_s1.json").write_text("garbage")

    loaded = store.load("s1")
    assert loaded is not None
    assert loaded.state["i"] < 2


def test_sanitize_seed_id(tmp_path):
    store = CheckpointStore(tmp_path)
    cp = CheckpointData.create("../../etc/passwd", "build", {"x": 1})
    store.save(cp)
    assert not (tmp_path.parent / "etc").exists()
    loaded = store.load("../../etc/passwd")
    assert loaded is not None


def test_list_checkpoints(tmp_path):
    store = CheckpointStore(tmp_path)
    for sid in ["s1", "s2", "s3"]:
        cp = CheckpointData.create(sid, "build", {})
        store.save(cp)
    assert set(store.list_checkpoints()) == {"s1", "s2", "s3"}


def test_load_nonexistent(tmp_path):
    store = CheckpointStore(tmp_path)
    assert store.load("nonexistent") is None


def test_recovery_manager(tmp_path):
    store = CheckpointStore(tmp_path)
    cp = CheckpointData.create("s1", "qa", {"progress": 0.5})
    store.save(cp)
    rm = RecoveryManager(store)
    recovered = rm.recover("s1")
    assert recovered is not None
    assert recovered.phase == "qa"


@pytest.mark.asyncio
async def test_periodic_checkpointer(tmp_path):
    store = CheckpointStore(tmp_path)
    counter = {"val": 0}

    def cb():
        counter["val"] += 1
        return CheckpointData.create("s1", "build", {"n": counter["val"]})

    checkpointer = PeriodicCheckpointer(store, cb, interval_sec=0.1)
    await checkpointer.start()
    await asyncio.sleep(0.35)
    await checkpointer.stop(final_save=False)

    assert counter["val"] >= 3


@pytest.mark.asyncio
async def test_periodic_final_save(tmp_path):
    store = CheckpointStore(tmp_path)

    def cb():
        return CheckpointData.create("s1", "build", {"final": True})

    checkpointer = PeriodicCheckpointer(store, cb, interval_sec=10)
    await checkpointer.start()
    await checkpointer.stop(final_save=True)

    loaded = store.load("s1")
    assert loaded is not None
    assert loaded.state == {"final": True}
