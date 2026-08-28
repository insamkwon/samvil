from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


def _wait_for_path(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"lock process exited early: {process.returncode}\n{stdout}\n{stderr}"
            )
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def test_verification_execution_lock_serializes_across_processes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "cross-process.db"
    holder_entered = tmp_path / "holder-entered"
    contender_ready = tmp_path / "contender-ready"
    contender_entered = tmp_path / "contender-entered"
    release_holder = tmp_path / "release-holder"
    mcp_root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(mcp_root), os.environ.get("PYTHONPATH", "")))
        ),
    }
    holder_script = """
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from samvil_mcp.transition_lock import verification_execution_lock

async def main():
    store = SimpleNamespace(db_path=sys.argv[1])
    async with verification_execution_lock(store, "run-1", "samvil-build"):
        Path(sys.argv[2]).write_text("entered", encoding="utf-8")
        while not Path(sys.argv[3]).exists():
            await asyncio.sleep(0.01)

asyncio.run(main())
"""
    contender_script = """
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from samvil_mcp.transition_lock import verification_execution_lock

async def main():
    store = SimpleNamespace(db_path=sys.argv[1])
    Path(sys.argv[2]).write_text("ready", encoding="utf-8")
    async with verification_execution_lock(store, "run-1", "samvil-build"):
        Path(sys.argv[3]).write_text("entered", encoding="utf-8")

asyncio.run(main())
"""
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            holder_script,
            str(db_path),
            str(holder_entered),
            str(release_holder),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    contender: subprocess.Popen[str] | None = None
    try:
        _wait_for_path(holder_entered, holder)
        contender = subprocess.Popen(
            [
                sys.executable,
                "-c",
                contender_script,
                str(db_path),
                str(contender_ready),
                str(contender_entered),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _wait_for_path(contender_ready, contender)
        assert not contender_entered.exists()
        release_holder.write_text("release", encoding="utf-8")
        holder_stdout, holder_stderr = holder.communicate(timeout=5)
        contender_stdout, contender_stderr = contender.communicate(timeout=5)
        assert holder.returncode == 0, (holder_stdout, holder_stderr)
        assert contender.returncode == 0, (contender_stdout, contender_stderr)
        assert contender_entered.exists()
    finally:
        release_holder.write_text("release", encoding="utf-8")
        for process in (holder, contender):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


def test_cancelled_file_lock_waiter_releases_after_repeated_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.transition_lock as locks
    from types import SimpleNamespace

    entered = threading.Event()
    allow_acquisition = threading.Event()
    released = threading.Event()
    retained_contexts = []

    class ControlledContext:
        def __enter__(self):
            entered.set()
            assert allow_acquisition.wait(5)

        def __exit__(self, *_args):
            released.set()

    def controlled_lock(_path):
        context = ControlledContext()
        retained_contexts.append(context)
        return context

    monkeypatch.setattr(locks, "_file_locked", controlled_lock)
    store = SimpleNamespace(db_path=str(tmp_path / "cancelled-waiter.db"))

    async def cancel_waiter():
        async def wait_for_lock():
            async with locks.verification_execution_lock(
                store, "run-1", "samvil-build"
            ):
                pytest.fail("cancelled waiter must never enter the lock body")

        waiter = asyncio.create_task(wait_for_lock())
        assert await asyncio.to_thread(entered.wait, 2)
        waiter.cancel()
        await asyncio.sleep(0.05)
        waiter.cancel()
        await asyncio.sleep(0.05)
        allow_acquisition.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        for _ in range(100):
            if released.is_set():
                break
            await asyncio.sleep(0.01)

    asyncio.run(cancel_waiter())

    assert retained_contexts
    assert released.is_set()


def test_cancelled_file_lock_waiter_waits_for_release_before_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.transition_lock as locks
    from types import SimpleNamespace

    acquire_started = threading.Event()
    allow_acquisition = threading.Event()
    release_started = threading.Event()
    allow_release = threading.Event()
    released = threading.Event()

    class ControlledContext:
        def __enter__(self):
            acquire_started.set()
            assert allow_acquisition.wait(5)

        def __exit__(self, *_args):
            release_started.set()
            assert allow_release.wait(5)
            released.set()

    monkeypatch.setattr(locks, "_file_locked", lambda _path: ControlledContext())
    store = SimpleNamespace(db_path=str(tmp_path / "cancelled-release.db"))

    async def cancel_during_release():
        async def wait_for_lock():
            async with locks.verification_execution_lock(
                store, "run-1", "samvil-build"
            ):
                pytest.fail("cancelled waiter must never enter the lock body")

        waiter = asyncio.create_task(wait_for_lock())
        assert await asyncio.to_thread(acquire_started.wait, 2)
        waiter.cancel()
        allow_acquisition.set()
        assert await asyncio.to_thread(release_started.wait, 2)
        waiter.cancel()
        await asyncio.sleep(0.05)
        waiter.cancel()
        await asyncio.sleep(0.05)
        completed_before_release = waiter.done()
        allow_release.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        return completed_before_release

    completed_before_release = asyncio.run(cancel_during_release())

    assert completed_before_release is False
    assert released.is_set()


def test_cancelled_file_lock_waiter_propagates_cancellation_if_acquire_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import samvil_mcp.transition_lock as locks
    from types import SimpleNamespace

    entered = threading.Event()
    allow_failure = threading.Event()

    class FailingContext:
        def __enter__(self):
            entered.set()
            assert allow_failure.wait(5)
            raise RuntimeError("flock acquisition failed")

        def __exit__(self, *_args):
            pytest.fail("a lock that failed acquisition must not be released")

    monkeypatch.setattr(locks, "_file_locked", lambda _path: FailingContext())
    store = SimpleNamespace(db_path=str(tmp_path / "cancelled-failure.db"))

    async def cancel_waiter():
        async def wait_for_lock():
            async with locks.verification_execution_lock(
                store, "run-1", "samvil-build"
            ):
                pytest.fail("failed waiter must never enter the lock body")

        waiter = asyncio.create_task(wait_for_lock())
        assert await asyncio.to_thread(entered.wait, 2)
        waiter.cancel()
        await asyncio.sleep(0.05)
        waiter.cancel()
        allow_failure.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter

    asyncio.run(cancel_waiter())
