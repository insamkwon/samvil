"""OS-backed supervisor for trusted verification command trees."""

from __future__ import annotations

import ctypes
import json
import os
import select
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path


def _linux_child_pids(parent_pid: int) -> set[int]:
    children: set[int] = set()
    task_root = Path(f"/proc/{parent_pid}/task")
    try:
        task_dirs = tuple(task_root.iterdir())
    except OSError:
        return set()
    for task_dir in task_dirs:
        try:
            values = (task_dir / "children").read_text(encoding="ascii").split()
        except OSError:
            continue
        for value in values:
            try:
                children.add(int(value))
            except ValueError:
                continue
    return children


def _linux_descendants(parent_pid: int) -> set[int]:
    descendants: set[int] = set()
    pending = list(_linux_child_pids(parent_pid))
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        pending.extend(_linux_child_pids(pid))
    return descendants


def _reap_children() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _cleanup_linux_children(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (PermissionError, ProcessLookupError):
        pass
    if process.poll() is None:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    quiet_rounds = 0
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        descendants = _linux_descendants(os.getpid())
        for pid in descendants:
            try:
                os.kill(pid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                pass
        _reap_children()
        if _linux_descendants(os.getpid()):
            quiet_rounds = 0
        else:
            quiet_rounds += 1
            if quiet_rounds >= 3:
                return
        time.sleep(0.01)
    raise RuntimeError("verification descendants survived Linux subreaper cleanup")


def _run_linux(timeout_seconds: float, command: list[str]) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise RuntimeError(
            f"cannot enable Linux verification subreaper: errno={ctypes.get_errno()}"
        )
    process = subprocess.Popen(command, start_new_session=True)
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(0.01)
    _cleanup_linux_children(process)
    if process.poll() is None:
        process.wait(timeout=2)
    if timed_out:
        os.write(1, b"\nverification timed out\n")
        return 124
    return int(process.returncode or 0)


def _run_darwin(
    root: Path,
    ready_path: Path,
    release_path: Path,
    result_path: Path,
    output_path: Path,
    timeout_seconds: float,
    environment: dict[str, str],
    command: list[str],
) -> int:
    ready_temporary = ready_path.with_suffix(".tmp")
    ready_temporary.write_text(str(os.getpid()), encoding="ascii")
    ready_temporary.replace(ready_path)
    release_deadline = time.monotonic() + 5
    while not release_path.exists():
        if time.monotonic() >= release_deadline:
            return 125
        time.sleep(0.005)
    maximum = 2_000_000
    chunks: deque[bytes] = deque()
    output_size = 0

    def append_output(chunk: bytes) -> None:
        nonlocal output_size
        chunks.append(chunk)
        output_size += len(chunk)
        while output_size > maximum and chunks:
            overflow = output_size - maximum
            first = chunks[0]
            if overflow >= len(first):
                output_size -= len(chunks.popleft())
            else:
                chunks[0] = first[overflow:]
                output_size -= overflow

    timed_out = False
    process = subprocess.Popen(
        command,
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=0,
    )
    if process.stdout is None:
        raise RuntimeError("verification output pipe is unavailable")
    output_fd = process.stdout.fileno()
    os.set_blocking(output_fd, False)

    def drain_output() -> bool:
        while True:
            try:
                chunk = os.read(output_fd, 65_536)
            except BlockingIOError:
                return False
            except OSError:
                return True
            if not chunk:
                return True
            append_output(chunk)

    deadline = time.monotonic() + timeout_seconds
    reached_eof = False
    while process.poll() is None:
        reached_eof = drain_output() or reached_eof
        if time.monotonic() >= deadline:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                pass
            process.wait()
            break
        select.select([output_fd], [], [], 0.01)
    reached_eof = drain_output() or reached_eof
    process.stdout.close()
    exit_code = 124 if timed_out else int(process.returncode or 0)
    if timed_out:
        append_output(b"\nverification timed out\n")
    output_path.write_bytes(b"".join(chunks))
    temporary = result_path.with_suffix(".tmp")
    temporary.write_text(str(exit_code), encoding="ascii")
    temporary.replace(result_path)
    return 0


def main() -> int:
    mode = sys.argv[1]
    if mode == "linux":
        return _run_linux(float(sys.argv[2]), json.loads(sys.argv[3]))
    if mode == "darwin":
        return _run_darwin(
            Path(sys.argv[2]),
            Path(sys.argv[3]),
            Path(sys.argv[4]),
            Path(sys.argv[5]),
            Path(sys.argv[6]),
            float(sys.argv[7]),
            json.loads(sys.argv[8]),
            json.loads(sys.argv[9]),
        )
    raise RuntimeError(f"unsupported verification supervisor mode: {mode}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        os.write(2, f"verification supervisor failed: {exc}\n".encode())
        raise SystemExit(125) from exc
