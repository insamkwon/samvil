#!/usr/bin/env python3
"""Verify an untrusted quarantine candidate from a pinned control checkout."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import NoReturn
import unicodedata


REQUIRED_CHECK_IDS = ("quarantine-tests", "quarantine-gate")
REQUIRED_DIGEST_PATHS = {
    "policy": "release/quarantine/v4322-policy.json",
    "plugin_manifest": ".claude-plugin/plugin.json",
    "marketplace_manifest": ".claude-plugin/marketplace.json",
    "mcp_manifest": ".mcp.json",
    "passive_surface_manifest": "release/quarantine/v4322-passive-surface-manifest.json",
    "gate": "scripts/pre-commit-check.sh",
    "validator": "scripts/quarantine-fuse.py",
    "focused_test": "mcp/tests/test_quarantine_fuse.py",
}
REQUIRED_DIGESTS = tuple(REQUIRED_DIGEST_PATHS)
REQUIRED_DIGEST_MODES = {
    **{name: "100644" for name in REQUIRED_DIGEST_PATHS},
    "gate": "100755",
    "validator": "100755",
}
MAX_AUTHORIZATION_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_BLOB_BYTES = 64 * 1024 * 1024
MAX_CANDIDATE_BLOB_COUNT = 10_000
MAX_CANDIDATE_INVENTORY_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_TOTAL_BLOB_BYTES = 256 * 1024 * 1024
MAX_CANDIDATE_OBJECT_STORE_ENTRIES = 50_000
MAX_CANDIDATE_GIT_CLOSURE_ENTRIES = 100_000
MAX_CANDIDATE_GIT_CLOSURE_FILE_BYTES = 256 * 1024 * 1024
MAX_CANDIDATE_GIT_CLOSURE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_CANDIDATE_GIT_CLOSURE_DEPTH = 32
MAX_CANDIDATE_GIT_CONFIG_BYTES = 64 * 1024
MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024
MAX_KEY_BYTES = 64 * 1024
MAX_LAUNCH_RECEIPT_BYTES = 1024 * 1024
MAX_SIGNATURE_BYTES = 64 * 1024
MAX_PYTHON_BYTES = 256 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_INTEGER_DIGITS = 128
CHECK_TIMEOUT_SECONDS = 30
GIT_TIMEOUT_SECONDS = 10
TRUSTED_PYTEST_CONFIG_SENTINEL = "__SAMVIL_TRUSTED_PYTEST_CONFIG__"
TRUSTED_PYTEST_CONFIG_NAME = ".samvil-trusted-pytest.ini"
TRUSTED_PYTEST_CONFIG_BYTES = b"[pytest]\n"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
BOOTSTRAP_PREFIX = "SAMVIL_BOOTSTRAP_"
CANDIDATE_PROFILE_CLASS = "release-candidate-network-zero"
REMOTE_TOKEN = re.compile(r"(?:^[^/\s]+@[^:\s]+:|^[a-z][a-z0-9+.-]*://)", re.I)
AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "nonce",
        "expected_control_commit",
        "trusted_python",
        "candidate",
        "required_commands",
    }
)
CANDIDATE_FIELDS = frozenset(
    {"commit", "tree", "inventory", "digests", "allowed_executable_paths"}
)
TRUSTED_PYTHON_FIELDS = frozenset({"path", "sha256"})
COMMAND_FIELDS = frozenset({"id", "argv"})
DIGEST_BINDING_FIELDS = frozenset({"path", "blob", "sha256"})
CHILD_ENVIRONMENT_KEYS = tuple(
    sorted(
        {
            "PATH",
            "LANG",
            "LC_ALL",
            "HOME",
            "CODEX_HOME",
            "CLAUDE_CONFIG_DIR",
            "GNUPGHOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "__CF_USER_TEXT_ENCODING",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "PYTHONNOUSERSITE",
            "PYTHONDONTWRITEBYTECODE",
            "PIP_CONFIG_FILE",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        }
    )
)
CONTROL_FILES = (
    "tools/release-control/inherited_context.py",
    "tools/release-control/run-isolated.py",
    "tools/release-control/verify-quarantine-candidate.py",
)
EXPECTED_CANDIDATE_BOUNDARY_EVIDENCE = {
    "applications_open_eperm": True,
    "dev_null_read": True,
    "ctypes_fork_eperm": True,
    "execution_root_read": True,
    "fork_eperm": True,
    "loopback_bind_eperm": True,
    "loopback_connect_eperm": True,
    "parent_signal_eperm": True,
    "posix_spawn_eperm": True,
    "protected_list_eperm": 2,
    "protected_open_eperm": 2,
    "protected_stat_eperm": 2,
    "protected_lstat_eperm": 2,
    "protected_access_false": 2,
    "protected_exists_false": 2,
    "protected_root_count": 2,
    "protected_write_eperm": 2,
    "setsid_eperm": True,
    "temp_roundtrip": True,
    "rlimit_fsize_bytes": 1 * 1024 * 1024,
    "rlimit_cpu_seconds": 15,
    "rlimit_nofile_count": 32,
    "resource_status": "within_limits",
}
EXPECTED_CANDIDATE_RESOURCE_LIMITS = {
    "fsize_bytes": 1 * 1024 * 1024,
    "cpu_seconds": 15,
    "nofile_count": 32,
    "capture_bytes": 1 * 1024 * 1024,
    "invocation_total_bytes": 32 * 1024 * 1024,
    "rss_bytes": 192 * 1024 * 1024,
}
CANDIDATE_GIT_OVERRIDES = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.excludesFile=/dev/null",
    "-c",
    "protocol.allow=never",
    "-c",
    "credential.helper=",
)
CANDIDATE_GIT_STRIPPED_ENV = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_REPLACE_REF_BASE",
        "GIT_WORK_TREE",
    }
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_strict_json(raw: bytes) -> object:
    def exact_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(value)

    def bounded_integer(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > MAX_JSON_INTEGER_DIGITS:
            raise ValueError("JSON integer exceeded bound")
        return int(value)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=exact_pairs,
            parse_constant=reject_constant,
            parse_float=reject_constant,
            parse_int=bounded_integer,
        )
        stack: list[tuple[object, int]] = [(value, 1)]
        while stack:
            current, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON nesting exceeded bound")
            if isinstance(current, dict):
                stack.extend((item, depth + 1) for item in current.values())
            elif isinstance(current, list):
                stack.extend((item, depth + 1) for item in current)
            elif isinstance(current, str) and any(
                "\ud800" <= character <= "\udfff" for character in current
            ):
                raise ValueError("JSON contains surrogate")
        return value
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
    ) as exc:
        raise ValueError("invalid strict JSON") from exc


def write_json(path: Path, payload: dict[str, object]) -> None:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o600)
        opened = os.fstat(descriptor)
        pathname_before = os.lstat(path)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            stat.S_IFMT(item.st_mode),
            item.st_nlink,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or identity(opened) != identity(pathname_before)
        ):
            raise OSError("unsafe receipt")
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("short receipt write")
            offset += written
        os.fsync(descriptor)
        final_fd = os.fstat(descriptor)
        pathname_after = os.lstat(path)
        if (
            identity(opened) != identity(final_fd)
            or identity(final_fd) != identity(pathname_after)
            or final_fd.st_size != len(raw)
            or pathname_after.st_size != len(raw)
        ):
            raise OSError("receipt identity changed")
    except OSError:
        print("VERIFIER_RECEIPT_WRITE_FAILED", file=sys.stderr)
        raise SystemExit(2) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def receipt(status: str, **extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "verdict": "PASS" if status == "PASS" else "BLOCKED",
        "promotable": status == "PASS",
        **extra,
    }


def stop(path: Path, status: str, code: int = 2, **extra: object) -> NoReturn:
    write_json(path, receipt(status, **extra))
    raise SystemExit(code)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_receipt_target(raw_tmpdir: str, path: Path) -> tuple[Path, Path]:
    if not raw_tmpdir or not os.path.isabs(raw_tmpdir) or not os.path.isabs(path):
        raise ValueError("invalid verifier receipt")
    tmpdir = Path(raw_tmpdir).resolve(strict=True)
    if str(tmpdir) != raw_tmpdir or not tmpdir.is_dir():
        raise ValueError("invalid verifier receipt")
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    if str(parent) != str(path.parent) or str(target) != str(path):
        raise ValueError("invalid verifier receipt")
    if not is_within(target, tmpdir) or target == tmpdir:
        raise ValueError("invalid verifier receipt")
    try:
        os.lstat(target)
    except OSError as exc:
        if exc.errno == getattr(os, "ENOENT", 2):
            return tmpdir, target
    raise ValueError("invalid verifier receipt")


def exact_object(
    value: object, fields: frozenset[str], receipt_path: Path, status: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        stop(receipt_path, status)
    return value


def regular_single_link_bytes(
    path: Path, receipt_path: Path, status: str, *, max_bytes: int
) -> bytes:
    try:
        raw = str(path)
        canonical = path.resolve(strict=True)
        before = os.lstat(path)
        if (
            raw != str(canonical)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > max_bytes
        ):
            stop(receipt_path, status)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(canonical, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_size > max_bytes
            ):
                raise OSError("unsafe trusted artifact")
            chunks: list[bytes] = []
            observed = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > max_bytes:
                    raise OSError("oversized trusted artifact")
                chunks.append(chunk)
            data = b"".join(chunks)
            after_fd = os.fstat(descriptor)
            after_path = os.lstat(path)
        finally:
            os.close(descriptor)
    except (OSError, RuntimeError, ValueError, MemoryError):
        stop(receipt_path, status)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        stat.S_IFMT(item.st_mode),
        item.st_nlink,
        item.st_size,
    )
    if (
        identity(before) != identity(opened)
        or identity(opened) != identity(after_fd)
        or identity(after_fd) != identity(after_path)
    ):
        stop(receipt_path, status)
    return data


def clean_env(temp_root: Path) -> dict[str, str]:
    home = temp_root / "outer-home"
    tmp = temp_root / "outer-tmp"
    home.mkdir()
    tmp.mkdir()
    git_config = temp_root / "outer-gitconfig"
    git_config.write_text(
        "[credential]\n\thelper =\n"
        "[core]\n\taskPass = /usr/bin/false\n"
        "[protocol]\n\tallow = never\n",
        encoding="utf-8",
    )
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": str(git_config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _git_bytes_bounded(
    repo: Path,
    env: dict[str, str],
    max_bytes: int,
    args: tuple[str, ...],
) -> bytes:
    try:
        process = subprocess.Popen(
            ["/usr/bin/git", "-C", str(repo), *args],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise ValueError("git verification failed") from exc
    if process.stdout is None:
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass
        raise ValueError("git verification failed")

    def terminate_group() -> bool:
        group_existed = False
        try:
            os.killpg(process.pid, signal.SIGKILL)
            group_existed = True
        except ProcessLookupError:
            pass
        except OSError as exc:
            raise ValueError("git verification failed") from exc
        if process.poll() is None:
            try:
                process.wait(timeout=2)
            except subprocess.SubprocessError as exc:
                raise ValueError("git verification failed") from exc
        if group_existed:
            cleanup_deadline = time.monotonic() + 1
            while True:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                except OSError as exc:
                    raise ValueError("git verification failed") from exc
                if time.monotonic() >= cleanup_deadline:
                    raise ValueError("git verification failed")
                time.sleep(0.01)
        return group_existed

    chunks: list[bytes] = []
    observed = 0
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("git verification timed out")
            ready, _, _ = select.select(
                [descriptor], [], [], min(0.1, remaining)
            )
            if not ready:
                continue
            try:
                chunk = os.read(
                    descriptor, min(1024 * 1024, max_bytes - observed + 1)
                )
            except BlockingIOError:
                continue
            if not chunk:
                break
            observed += len(chunk)
            if observed > max_bytes:
                raise ValueError("git verification output exceeded bound")
            chunks.append(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("git verification timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("git verification timed out") from exc
        surviving_group = terminate_group()
    except TimeoutError as exc:
        terminate_group()
        raise ValueError("git verification timed out") from exc
    except ValueError:
        terminate_group()
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        terminate_group()
        raise ValueError("git verification failed") from exc
    except BaseException:
        terminate_group()
        raise
    finally:
        process.stdout.close()
    if returncode != 0 or surviving_group:
        raise ValueError("git verification failed")
    return b"".join(chunks)


def git_bytes(repo: Path, env: dict[str, str], *args: str) -> bytes:
    return _git_bytes_bounded(
        repo,
        env,
        MAX_CANDIDATE_GIT_CLOSURE_TOTAL_BYTES,
        args,
    )


def git_text(repo: Path, env: dict[str, str], *args: str) -> str:
    return git_bytes(repo, env, *args).decode("utf-8").strip()


def candidate_git_bytes(repo: Path, env: dict[str, str], *args: str) -> bytes:
    candidate_env = {
        **{
            key: value
            for key, value in env.items()
            if key not in CANDIDATE_GIT_STRIPPED_ENV
            and not key.startswith("GIT_CONFIG_KEY_")
            and not key.startswith("GIT_CONFIG_VALUE_")
        },
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    return git_bytes(repo, candidate_env, *CANDIDATE_GIT_OVERRIDES, *args)


def candidate_git_bytes_bounded(
    repo: Path,
    env: dict[str, str],
    max_bytes: int,
    *args: str,
) -> bytes:
    if max_bytes < 0:
        raise ValueError("invalid Git output bound")
    candidate_env = {
        **{
            key: value
            for key, value in env.items()
            if key not in CANDIDATE_GIT_STRIPPED_ENV
            and not key.startswith("GIT_CONFIG_KEY_")
            and not key.startswith("GIT_CONFIG_VALUE_")
        },
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    return _git_bytes_bounded(
        repo,
        candidate_env,
        max_bytes,
        (*CANDIDATE_GIT_OVERRIDES, *args),
    )


def candidate_git_text(repo: Path, env: dict[str, str], *args: str) -> str:
    return candidate_git_bytes(repo, env, *args).decode("utf-8").strip()


def _closure_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_nlink,
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)),
        getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)),
    )


def snapshot_candidate_git_closure(
    candidate: Path,
    trusted_tmpdir: Path,
    receipt_path: Path,
) -> Path:
    source = candidate / ".git"
    flags_directory = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    flags_file = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        source_before = os.lstat(source)
        if not stat.S_ISDIR(source_before.st_mode) or stat.S_ISLNK(source_before.st_mode):
            raise OSError("candidate .git must be a directory")
        source_fd = os.open(source, flags_directory)
        source_opened = os.fstat(source_fd)
        if _closure_identity(source_before) != _closure_identity(source_opened):
            raise OSError("candidate .git identity changed")
        snapshot_parent = Path(
            tempfile.mkdtemp(prefix="candidate-git-", dir=trusted_tmpdir)
        )
        snapshot = snapshot_parent / "repo"
        snapshot.mkdir(mode=0o700)
        destination = snapshot / ".git"
        destination.mkdir(mode=0o700)
    except (OSError, RuntimeError, ValueError):
        stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CLOSURE")

    state = {"entries": 0, "total": 0}

    def bounded_directory_names(descriptor: int) -> list[str]:
        names: list[str] = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_CANDIDATE_GIT_CLOSURE_ENTRIES:
                    raise OSError("candidate Git directory entry bound exceeded")
        names.sort()
        return names

    def copy_directory(source_directory_fd: int, target: Path, depth: int) -> None:
        if depth > MAX_CANDIDATE_GIT_CLOSURE_DEPTH:
            raise OSError("candidate Git closure depth exceeded")
        directory_before = os.fstat(source_directory_fd)
        names = bounded_directory_names(source_directory_fd)
        for name in names:
            if not name or name in {".", ".."} or "/" in name or "\0" in name:
                raise OSError("invalid candidate Git closure name")
            state["entries"] += 1
            if state["entries"] > MAX_CANDIDATE_GIT_CLOSURE_ENTRIES:
                raise OSError("candidate Git closure entry bound exceeded")
            before = os.stat(name, dir_fd=source_directory_fd, follow_symlinks=False)
            target_path = target / name
            if stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode):
                child_fd = os.open(name, flags_directory, dir_fd=source_directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    if _closure_identity(before) != _closure_identity(opened):
                        raise OSError("candidate Git directory identity changed")
                    target_path.mkdir(mode=0o700)
                    copy_directory(child_fd, target_path, depth + 1)
                    after_fd = os.fstat(child_fd)
                    after_path = os.stat(
                        name, dir_fd=source_directory_fd, follow_symlinks=False
                    )
                    if (
                        _closure_identity(before) != _closure_identity(after_fd)
                        or _closure_identity(after_fd) != _closure_identity(after_path)
                    ):
                        raise OSError("candidate Git directory changed during copy")
                finally:
                    os.close(child_fd)
                continue
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > MAX_CANDIDATE_GIT_CLOSURE_FILE_BYTES
            ):
                raise OSError("unsafe candidate Git closure entry")
            source_file_fd = os.open(
                name, flags_file, dir_fd=source_directory_fd
            )
            try:
                opened = os.fstat(source_file_fd)
                if _closure_identity(before) != _closure_identity(opened):
                    raise OSError("candidate Git file identity changed")
                destination_fd = os.open(
                    target_path,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                )
                observed = 0
                try:
                    while True:
                        chunk = os.read(source_file_fd, 1024 * 1024)
                        if not chunk:
                            break
                        observed += len(chunk)
                        state["total"] += len(chunk)
                        if (
                            observed > MAX_CANDIDATE_GIT_CLOSURE_FILE_BYTES
                            or state["total"] > MAX_CANDIDATE_GIT_CLOSURE_TOTAL_BYTES
                        ):
                            raise OSError("candidate Git closure byte bound exceeded")
                        offset = 0
                        while offset < len(chunk):
                            written = os.write(destination_fd, chunk[offset:])
                            if written <= 0:
                                raise OSError("candidate Git closure short write")
                            offset += written
                    os.fsync(destination_fd)
                finally:
                    os.close(destination_fd)
                after_fd = os.fstat(source_file_fd)
                after_path = os.stat(
                    name, dir_fd=source_directory_fd, follow_symlinks=False
                )
                if (
                    observed != before.st_size
                    or _closure_identity(before) != _closure_identity(after_fd)
                    or _closure_identity(after_fd) != _closure_identity(after_path)
                ):
                    raise OSError("candidate Git file changed during copy")
            finally:
                os.close(source_file_fd)
        if names != bounded_directory_names(source_directory_fd):
            raise OSError("candidate Git directory entries changed")
        if _closure_identity(directory_before) != _closure_identity(
            os.fstat(source_directory_fd)
        ):
            raise OSError("candidate Git directory changed")

    try:
        copy_directory(source_fd, destination, 1)
        source_after = os.fstat(source_fd)
        source_path_after = os.lstat(source)
        if (
            _closure_identity(source_before) != _closure_identity(source_after)
            or _closure_identity(source_after) != _closure_identity(source_path_after)
        ):
            raise OSError("candidate .git changed during snapshot")
    except (OSError, RuntimeError, ValueError, MemoryError):
        stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CLOSURE")
    finally:
        os.close(source_fd)
    return snapshot


def trusted_git_closure_snapshot(repo: Path) -> dict[str, tuple[int, ...]]:
    git = repo / ".git"
    snapshot: dict[str, tuple[int, ...]] = {}
    for raw_root, directories, files in os.walk(git, followlinks=False):
        root = Path(raw_root)
        for name in (*directories, *files):
            path = root / name
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("trusted Git closure link")
            snapshot[path.relative_to(git).as_posix()] = _closure_identity(metadata)
    return snapshot


def verify_candidate_git_config(candidate: Path, receipt_path: Path) -> None:
    config = regular_single_link_bytes(
        candidate / ".git" / "config",
        receipt_path,
        "UNSAFE_CANDIDATE_GIT_CONFIG",
        max_bytes=MAX_CANDIDATE_GIT_CONFIG_BYTES,
    )
    try:
        text = config.decode("utf-8")
    except UnicodeDecodeError:
        stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
    allowed_core = {
        "repositoryformatversion": {"0"},
        "filemode": {"true", "false"},
        "bare": {"false"},
        "logallrefupdates": {"true", "false"},
        "ignorecase": {"true", "false"},
        "precomposeunicode": {"true", "false"},
    }
    seen: set[tuple[str, str]] = set()
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            if (
                not re.fullmatch(r"[A-Za-z0-9.-]+", section_name)
                or section_name.lower() not in {"core", "user"}
            ):
                stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
            section = section_name.lower()
            continue
        if section is None or "=" not in line:
            stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
        key_raw, value_raw = line.split("=", 1)
        key = key_raw.strip().lower()
        value = value_raw.strip()
        identity = (section, key)
        if identity in seen:
            stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
        seen.add(identity)
        if section == "core":
            if key not in allowed_core or value.lower() not in allowed_core[key]:
                stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
        elif section == "user":
            if key not in {"name", "email"} or not value or len(value) > 512:
                stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")
        else:
            stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CONFIG")


def candidate_object_store_snapshot(
    candidate: Path, receipt_path: Path
) -> dict[str, tuple[int, int, int, int, int]]:
    git = candidate / ".git"
    for forbidden in (
        git / "commondir",
        git / "modules",
        git / "worktrees",
        git / "shallow",
        git / "info" / "grafts",
        git / "refs" / "replace",
    ):
        try:
            os.lstat(forbidden)
        except OSError as exc:
            if exc.errno == getattr(os, "ENOENT", 2):
                continue
            stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
        stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    objects = git / "objects"
    try:
        root_metadata = os.lstat(objects)
    except OSError:
        stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    snapshot: dict[str, tuple[int, int, int, int, int]] = {}

    def remember(path: Path, metadata: os.stat_result) -> None:
        relative = path.relative_to(git).as_posix()
        snapshot[relative] = (
            metadata.st_dev,
            metadata.st_ino,
            stat.S_IFMT(metadata.st_mode),
            metadata.st_nlink,
            metadata.st_size,
        )
        if len(snapshot) > MAX_CANDIDATE_OBJECT_STORE_ENTRIES:
            stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")

    remember(objects, root_metadata)
    try:
        for raw_root, directories, files in os.walk(objects, followlinks=False):
            root = Path(raw_root)
            for name in tuple(directories):
                path = root / name
                metadata = os.lstat(path)
                if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                    stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
                remember(path, metadata)
            for name in files:
                path = root / name
                metadata = os.lstat(path)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_nlink != 1
                ):
                    stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
                remember(path, metadata)
    except OSError:
        stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    if any(
        name in snapshot
        for name in (
            "objects/info/alternates",
            "objects/info/http-alternates",
        )
    ):
        stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    return snapshot


def parse_inventory(raw: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    normalized_paths: set[str] = set()
    for row in raw.split(b"\0"):
        if not row:
            continue
        try:
            meta, path_raw = row.split(b"\t", 1)
            mode, kind, blob = meta.decode("ascii").split()
            path = path_raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("invalid inventory") from exc
        posix = PurePosixPath(path)
        if (
            not path
            or posix.is_absolute()
            or ".." in posix.parts
            or "." in posix.parts
            or "\\" in path
            or mode not in {"100644", "100755"}
            or kind != "blob"
            or not re.fullmatch(r"[0-9a-f]{40,64}", blob)
        ):
            raise ValueError("unsafe inventory")
        normalized = unicodedata.normalize("NFC", path).casefold()
        if normalized in normalized_paths:
            raise ValueError("unsafe inventory")
        normalized_paths.add(normalized)
        entries.append({"path": path, "mode": mode, "type": kind, "blob": blob})
        if len(entries) > MAX_CANDIDATE_BLOB_COUNT:
            raise ValueError("inventory entry bound exceeded")
    return entries


def git_sha1_blob_oid(content: bytes) -> str:
    header = b"blob " + str(len(content)).encode("ascii") + b"\0"
    return hashlib.sha1(header + content).hexdigest()


def read_verified_candidate_blobs(
    candidate: Path,
    env: dict[str, str],
    inventory: list[dict[str, str]],
) -> dict[str, bytes]:
    if candidate_git_text(candidate, env, "rev-parse", "--show-object-format") != "sha1":
        raise ValueError("unsupported candidate object format")
    blob_ids = {entry["blob"] for entry in inventory}
    if (
        len(inventory) > MAX_CANDIDATE_BLOB_COUNT
        or len(blob_ids) > MAX_CANDIDATE_BLOB_COUNT
        or any(re.fullmatch(r"[0-9a-f]{40}", blob) is None for blob in blob_ids)
    ):
        raise ValueError("candidate blob set invalid")
    verified: dict[str, bytes] = {}
    total = 0
    for blob in sorted(blob_ids):
        size_text = candidate_git_text(candidate, env, "cat-file", "-s", blob)
        if re.fullmatch(r"0|[1-9][0-9]*", size_text) is None:
            raise ValueError("candidate blob size invalid")
        size = int(size_text)
        if size > MAX_CANDIDATE_BLOB_BYTES:
            raise ValueError("candidate blob size bound exceeded")
        total += size
        if total > MAX_CANDIDATE_TOTAL_BLOB_BYTES:
            raise ValueError("candidate blob total bound exceeded")
        content = candidate_git_bytes_bounded(
            candidate, env, size, "cat-file", "blob", blob
        )
        if len(content) != size or git_sha1_blob_oid(content) != blob:
            raise ValueError("candidate blob identity mismatch")
        verified[blob] = content
    if set(verified) != blob_ids or len(verified) != len(blob_ids):
        raise ValueError("candidate blob map invalid")
    return verified


def verify_control(
    control: Path,
    expected: str,
    authorization: dict[str, object],
    env: dict[str, str],
    receipt_path: Path,
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected):
        stop(receipt_path, "CONTROL_COMMIT_MISMATCH")
    try:
        actual = git_text(control, env, "rev-parse", "HEAD^{commit}")
    except ValueError:
        stop(receipt_path, "CONTROL_COMMIT_MISMATCH")
    if actual != expected or authorization.get("expected_control_commit") != expected:
        stop(receipt_path, "CONTROL_COMMIT_MISMATCH")
    sibling = Path(__file__).resolve().parent
    for relative in CONTROL_FILES:
        try:
            committed = git_bytes(control, env, "show", f"{expected}:{relative}")
            live = (sibling / Path(relative).name).read_bytes()
            pinned_live = regular_single_link_bytes(
                control / relative,
                receipt_path,
                "CONTROL_FILE_MISMATCH",
                max_bytes=MAX_CONTROL_FILE_BYTES,
            )
        except (OSError, ValueError):
            stop(receipt_path, "CONTROL_FILE_MISMATCH")
        if committed != live or committed != pinned_live:
            stop(receipt_path, "CONTROL_FILE_MISMATCH")
    return control / "tools" / "release-control" / "run-isolated.py"


def verify_signature(
    policy: str,
    public_key: Path | None,
    signature: Path | None,
    expected_public_key_sha256: str | None,
    authorization_bytes: bytes,
    receipt_path: Path,
) -> str | None:
    if policy == "local-only":
        if public_key is not None or signature is not None:
            stop(receipt_path, "INVALID_SIGNATURE_POLICY")
        return None
    if public_key is None or signature is None:
        stop(receipt_path, "SIGNATURE_REQUIRED")
    public_bytes = regular_single_link_bytes(
        public_key,
        receipt_path,
        "PUBLIC_KEY_FILE_INVALID",
        max_bytes=MAX_KEY_BYTES,
    )
    signature_bytes = regular_single_link_bytes(
        signature,
        receipt_path,
        "SIGNATURE_FILE_INVALID",
        max_bytes=MAX_SIGNATURE_BYTES,
    )
    key_digest = sha256(public_bytes)
    if expected_public_key_sha256 != key_digest:
        stop(receipt_path, "UNTRUSTED_PUBLIC_KEY")
    try:
        modulus, exponent = parse_rsa_public_key(public_bytes)
        width = (modulus.bit_length() + 7) // 8
        if len(signature_bytes) != width:
            raise ValueError("signature width")
        signature_number = int.from_bytes(signature_bytes, "big")
        if signature_number >= modulus:
            raise ValueError("signature range")
        encoded = pow(signature_number, exponent, modulus).to_bytes(width, "big")
        digest_info = bytes.fromhex(
            "3031300d060960864801650304020105000420"
        ) + hashlib.sha256(authorization_bytes).digest()
        padding_length = width - len(digest_info) - 3
        expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
        if padding_length < 8 or encoded != expected:
            raise ValueError("invalid signature")
    except (OSError, ValueError):
        stop(receipt_path, "INVALID_SIGNATURE")
    return key_digest


def _der_value(data: bytes, offset: int, tag: int) -> tuple[bytes, int]:
    if offset >= len(data) or data[offset] != tag:
        raise ValueError("DER tag")
    offset += 1
    if offset >= len(data):
        raise ValueError("DER length")
    first = data[offset]
    offset += 1
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or offset + count > len(data):
            raise ValueError("DER length")
        length_bytes = data[offset : offset + count]
        if length_bytes[0] == 0:
            raise ValueError("DER non-minimal length")
        length = int.from_bytes(length_bytes, "big")
        if length < 128 or (length.bit_length() + 7) // 8 != count:
            raise ValueError("DER non-minimal length")
        offset += count
    else:
        length = first
    end = offset + length
    if end > len(data):
        raise ValueError("DER truncation")
    return data[offset:end], end


def _positive_der_integer(raw: bytes) -> int:
    if not raw or raw[0] & 0x80:
        raise ValueError("negative DER integer")
    if len(raw) > 1 and raw[0] == 0 and raw[1] & 0x80 == 0:
        raise ValueError("non-minimal DER integer")
    value = int.from_bytes(raw, "big", signed=False)
    if value <= 0:
        raise ValueError("non-positive DER integer")
    return value


def _validate_rsa_parameters(modulus: int, exponent: int) -> None:
    if not 2048 <= modulus.bit_length() <= 8192 or modulus % 2 == 0:
        raise ValueError("RSA modulus policy")
    if exponent < 3 or exponent > (1 << 32) - 1 or exponent % 2 == 0:
        raise ValueError("RSA exponent policy")


def parse_rsa_public_key(pem: bytes) -> tuple[int, int]:
    header = b"-----BEGIN PUBLIC KEY-----"
    footer = b"-----END PUBLIC KEY-----"
    lines = [line.strip() for line in pem.splitlines() if line.strip()]
    if len(lines) < 3 or lines[0] != header or lines[-1] != footer:
        raise ValueError("public key format")
    try:
        der = base64.b64decode(b"".join(lines[1:-1]), validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("public key encoding") from None
    outer, end = _der_value(der, 0, 0x30)
    if end != len(der):
        raise ValueError("public key trailing bytes")
    algorithm, cursor = _der_value(outer, 0, 0x30)
    if algorithm != bytes.fromhex("06092a864886f70d0101010500"):
        raise ValueError("public key algorithm")
    bit_string, cursor = _der_value(outer, cursor, 0x03)
    if cursor != len(outer) or not bit_string or bit_string[0] != 0:
        raise ValueError("public key bit string")
    rsa, end = _der_value(bit_string[1:], 0, 0x30)
    if end != len(bit_string) - 1:
        raise ValueError("public key RSA trailing bytes")
    modulus_raw, cursor = _der_value(rsa, 0, 0x02)
    exponent_raw, cursor = _der_value(rsa, cursor, 0x02)
    if cursor != len(rsa) or not modulus_raw or not exponent_raw:
        raise ValueError("public key integers")
    modulus = _positive_der_integer(modulus_raw)
    exponent = _positive_der_integer(exponent_raw)
    _validate_rsa_parameters(modulus, exponent)
    return modulus, exponent


def verify_candidate(
    candidate: Path,
    authorization: dict[str, object],
    env: dict[str, str],
    receipt_path: Path,
) -> tuple[str, str, list[dict[str, str]], dict[str, bytes]]:
    git_marker = candidate / ".git"
    try:
        git_metadata = os.lstat(git_marker)
    except OSError:
        stop(receipt_path, "REAL_REPOSITORY_TARGET_REJECTED")
    if not stat.S_ISDIR(git_metadata.st_mode) or stat.S_ISLNK(git_metadata.st_mode):
        stop(receipt_path, "REAL_REPOSITORY_TARGET_REJECTED")
    git_snapshot = snapshot_candidate_git_closure(
        candidate, Path(env["TMPDIR"]), receipt_path
    )
    verify_candidate_git_config(git_snapshot, receipt_path)
    object_store_snapshot = candidate_object_store_snapshot(
        git_snapshot, receipt_path
    )
    try:
        closure_snapshot = trusted_git_closure_snapshot(git_snapshot)
    except (OSError, ValueError):
        stop(receipt_path, "UNSAFE_CANDIDATE_GIT_CLOSURE")
    try:
        if candidate_git_text(git_snapshot, env, "remote"):
            stop(receipt_path, "REMOTE_TARGET_REJECTED")
        commit = candidate_git_text(git_snapshot, env, "rev-parse", "HEAD^{commit}")
        tree = candidate_git_text(git_snapshot, env, "rev-parse", "HEAD^{tree}")
        inventory = parse_inventory(
            candidate_git_bytes_bounded(
                git_snapshot,
                env,
                MAX_CANDIDATE_INVENTORY_BYTES,
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                "HEAD",
            )
        )
        verified_blobs = read_verified_candidate_blobs(
            git_snapshot, env, inventory
        )
        if (
            candidate_object_store_snapshot(git_snapshot, receipt_path)
            != object_store_snapshot
            or trusted_git_closure_snapshot(git_snapshot) != closure_snapshot
        ):
            stop(receipt_path, "UNSAFE_CANDIDATE_OBJECT_STORE")
    except ValueError:
        stop(receipt_path, "UNSAFE_GIT_ENTRY")
    expected = exact_object(
        authorization.get("candidate"),
        CANDIDATE_FIELDS,
        receipt_path,
        "AUTHORIZATION_SCHEMA_INVALID",
    )
    if expected.get("commit") != commit or expected.get("tree") != tree:
        stop(receipt_path, "CANDIDATE_IDENTITY_MISMATCH")
    if expected.get("inventory") != inventory:
        stop(receipt_path, "CANDIDATE_INVENTORY_MISMATCH")
    allowed_executables = expected.get("allowed_executable_paths")
    if (
        not isinstance(allowed_executables, list)
        or not all(isinstance(path, str) and path for path in allowed_executables)
        or len(set(allowed_executables)) != len(allowed_executables)
    ):
        stop(receipt_path, "AUTHORIZATION_SCHEMA_INVALID")
    executable_paths = {entry["path"] for entry in inventory if entry["mode"] == "100755"}
    if executable_paths != set(allowed_executables):
        stop(receipt_path, "UNEXPECTED_EXECUTABLE")
    digests = expected.get("digests")
    if not isinstance(digests, dict) or set(digests) != set(REQUIRED_DIGESTS):
        stop(receipt_path, "AUTHORIZATION_SCHEMA_INVALID")
    inventory_by_path = {entry["path"]: entry for entry in inventory}
    for name in REQUIRED_DIGESTS:
        binding = digests.get(name)
        binding = exact_object(
            binding,
            DIGEST_BINDING_FIELDS,
            receipt_path,
            "AUTHORIZATION_SCHEMA_INVALID",
        )
        path = binding.get("path")
        blob = binding.get("blob")
        expected_sha = binding.get("sha256")
        if (
            not isinstance(path, str)
            or path != REQUIRED_DIGEST_PATHS[name]
            or not isinstance(blob, str)
            or not isinstance(expected_sha, str)
        ):
            stop(receipt_path, "AUTHORIZATION_SCHEMA_INVALID")
        entry = inventory_by_path.get(path)
        if (
            entry is None
            or entry["blob"] != blob
            or entry["mode"] != REQUIRED_DIGEST_MODES[name]
        ):
            stop(receipt_path, "DIGEST_MISMATCH")
        content = verified_blobs.get(blob)
        if content is None:
            stop(receipt_path, "DIGEST_MISMATCH")
        if sha256(content) != expected_sha:
            stop(receipt_path, "DIGEST_MISMATCH")
    return commit, tree, inventory, verified_blobs


def verify_pinned_python(
    authorization: dict[str, object], receipt_path: Path
) -> Path:
    binding = exact_object(
        authorization.get("trusted_python"),
        TRUSTED_PYTHON_FIELDS,
        receipt_path,
        "AUTHORIZATION_SCHEMA_INVALID",
    )
    path = binding.get("path")
    expected_sha = binding.get("sha256")
    if (
        not isinstance(path, str)
        or not os.path.isabs(path)
        or not isinstance(expected_sha, str)
        or HEX64.fullmatch(expected_sha) is None
    ):
        stop(receipt_path, "PINNED_PYTHON_MISMATCH")
    python = Path(path)
    content = regular_single_link_bytes(
        python,
        receipt_path,
        "PINNED_PYTHON_MISMATCH",
        max_bytes=MAX_PYTHON_BYTES,
    )
    try:
        running = Path(sys.executable).resolve(strict=True)
    except (OSError, RuntimeError):
        stop(receipt_path, "PINNED_PYTHON_MISMATCH")
    if running != python or sha256(content) != expected_sha or not os.access(python, os.X_OK):
        stop(receipt_path, "PINNED_PYTHON_MISMATCH")
    return python


def required_commands(
    authorization: dict[str, object], pinned_python: Path, receipt_path: Path
) -> list[dict[str, object]]:
    commands = authorization.get("required_commands")
    if not isinstance(commands, list):
        stop(receipt_path, "MISSING_REQUIRED_CHECK")
    ids = [item.get("id") for item in commands if isinstance(item, dict)]
    if len(ids) != len(commands) or len(set(ids)) != len(ids):
        stop(receipt_path, "MISSING_REQUIRED_CHECK")
    if set(ids) != set(REQUIRED_CHECK_IDS):
        stop(receipt_path, "MISSING_REQUIRED_CHECK")
    ordered = {item["id"]: item for item in commands}
    result = []
    expected_argv = expected_command_argv(pinned_python)
    for check_id in REQUIRED_CHECK_IDS:
        item = exact_object(
            ordered[check_id],
            COMMAND_FIELDS,
            receipt_path,
            "INVALID_EXPECTED_COMMAND",
        )
        argv = item.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(token, str) and token for token in argv)
            or not os.path.isabs(argv[0])
            or any(REMOTE_TOKEN.search(token) for token in argv)
            or any("tools/release-control" in token for token in argv)
            or argv != expected_argv[check_id]
        ):
            stop(receipt_path, "INVALID_EXPECTED_COMMAND")
        result.append(item)
    return result


def expected_command_argv(pinned_python: Path) -> dict[str, list[str]]:
    return {
        "quarantine-tests": [
            str(pinned_python),
            "-I",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "-c",
            TRUSTED_PYTEST_CONFIG_SENTINEL,
            "--rootdir=.",
            "--import-mode=importlib",
            "mcp/tests/test_quarantine_fuse.py",
            "-q",
        ],
        "quarantine-gate": [
            str(pinned_python),
            "-I",
            "scripts/quarantine-fuse.py",
            "verify",
            "--policy",
            "release/quarantine/v4322-policy.json",
        ],
    }


def _snapshot_root_leaf_alias_key(
    snapshot: Path, leaf: str, *, prebound: bool
) -> tuple[int, int, str, str]:
    """Bind an APFS-conservative leaf alias to its stable namespace."""

    namespace = snapshot if prebound else snapshot.parent
    namespace_leaf = "" if prebound else snapshot.name
    try:
        canonical = namespace.resolve(strict=True)
        before = os.lstat(namespace)
        after = os.lstat(namespace)
    except (OSError, RuntimeError):
        raise ValueError("invalid snapshot namespace") from None
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        stat.S_IFMT(item.st_mode),
        item.st_nlink,
    )
    if (
        str(canonical) != str(namespace)
        or not stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or identity(before) != identity(after)
    ):
        raise ValueError("invalid snapshot namespace")
    return (
        before.st_dev,
        before.st_ino,
        unicodedata.normalize("NFD", namespace_leaf).casefold(),
        unicodedata.normalize("NFD", leaf).casefold(),
    )


def materialize_snapshot(
    snapshot: Path,
    inventory: list[dict[str, str]],
    verified_blobs: dict[str, bytes],
    nonce: str,
    *,
    prebound: bool = False,
) -> None:
    expected_blob_ids = {entry["blob"] for entry in inventory}
    if (
        len(inventory) > MAX_CANDIDATE_BLOB_COUNT
        or len(verified_blobs) != len(expected_blob_ids)
        or set(verified_blobs) != expected_blob_ids
        or any(not isinstance(content, bytes) for content in verified_blobs.values())
        or sum(len(content) for content in verified_blobs.values())
        > MAX_CANDIDATE_TOTAL_BLOB_BYTES
    ):
        raise ValueError("invalid preverified blob map")
    for blob, content in verified_blobs.items():
        if (
            len(content) > MAX_CANDIDATE_BLOB_BYTES
            or re.fullmatch(r"[0-9a-f]{40}", blob) is None
            or git_sha1_blob_oid(content) != blob
        ):
            raise ValueError("invalid preverified blob identity")
    materialized_total = 0
    for entry in inventory:
        materialized_total += len(verified_blobs[entry["blob"]])
        if materialized_total > MAX_CANDIDATE_TOTAL_BLOB_BYTES:
            raise ValueError("materialized snapshot exceeded bound")
    marker = snapshot / ".release-control-root.json"
    reserved_alias_keys = {
        _snapshot_root_leaf_alias_key(snapshot, name, prebound=prebound)
        for name in (marker.name, TRUSTED_PYTEST_CONFIG_NAME)
    }
    for entry in inventory:
        parts = PurePosixPath(entry["path"]).parts
        if parts and _snapshot_root_leaf_alias_key(
            snapshot, parts[0], prebound=prebound
        ) in reserved_alias_keys:
            raise ValueError("reserved trusted snapshot artifact alias")
    if prebound:
        try:
            entries = {path.name for path in snapshot.iterdir()}
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("invalid prebound snapshot") from None
        if entries != {marker.name} or marker_payload != {
            "kind": "snapshot",
            "nonce": nonce,
        }:
            raise ValueError("invalid prebound snapshot")
    else:
        snapshot.mkdir()
    if any(entry["path"] == marker.name for entry in inventory):
        raise ValueError("reserved snapshot marker")
    for entry in inventory:
        target = snapshot / entry["path"]
        if not is_within(target.resolve(strict=False), snapshot):
            raise ValueError("path escape")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(verified_blobs[entry["blob"]])
        target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
    if not prebound:
        marker.write_text(
            json.dumps({"kind": "snapshot", "nonce": nonce}), encoding="utf-8"
        )


def create_trusted_pytest_config(snapshot: Path) -> Path:
    path = snapshot / TRUSTED_PYTEST_CONFIG_NAME
    descriptor = -1
    try:
        canonical_snapshot = snapshot.resolve(strict=True)
        snapshot_metadata = os.lstat(snapshot)
        if (
            str(canonical_snapshot) != str(snapshot)
            or not stat.S_ISDIR(snapshot_metadata.st_mode)
            or stat.S_ISLNK(snapshot_metadata.st_mode)
        ):
            raise OSError("unsafe trusted pytest config parent")
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        opened = os.fstat(descriptor)
        pathname_before = os.lstat(path)
        offset = 0
        while offset < len(TRUSTED_PYTEST_CONFIG_BYTES):
            try:
                written = os.write(descriptor, TRUSTED_PYTEST_CONFIG_BYTES[offset:])
            except InterruptedError:
                continue
            if written <= 0:
                raise OSError("short trusted pytest config write")
            offset += written
        os.fsync(descriptor)
        final_fd = os.fstat(descriptor)
        pathname_after = os.lstat(path)
    except (OSError, RuntimeError):
        raise ValueError("invalid trusted pytest config") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        stat.S_IFMT(item.st_mode),
        item.st_nlink,
    )
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or identity(opened) != identity(pathname_before)
        or identity(pathname_before) != identity(final_fd)
        or identity(final_fd) != identity(pathname_after)
        or final_fd.st_size != len(TRUSTED_PYTEST_CONFIG_BYTES)
        or path.resolve(strict=True) != path
    ):
        raise ValueError("invalid trusted pytest config")
    return path


def execute_checks(
    runner: Path,
    snapshot: Path,
    commands: list[dict[str, object]],
    nonce: str,
    env: dict[str, str],
    pinned_python: Path,
    trusted_pytest_config: Path,
    receipt_path: Path,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    launcher_tmpdir = Path(env["TMPDIR"])
    trusted_config_bytes = regular_single_link_bytes(
        trusted_pytest_config,
        receipt_path,
        "TRUSTED_PYTEST_CONFIG_INVALID",
        max_bytes=len(TRUSTED_PYTEST_CONFIG_BYTES),
    )
    if trusted_config_bytes != TRUSTED_PYTEST_CONFIG_BYTES:
        stop(receipt_path, "TRUSTED_PYTEST_CONFIG_INVALID")
    for index, item in enumerate(commands):
        isolated_receipt = launcher_tmpdir / f"check-{index}.json"
        denial_log = launcher_tmpdir / f"check-{index}.denials"
        launcher_argv = [
                str(pinned_python),
                str(runner),
                "--root",
                str(snapshot),
                "--nonce",
                nonce,
                "--timeout",
                str(CHECK_TIMEOUT_SECONDS),
                "--receipt",
                str(isolated_receipt),
                "--denial-log",
                str(denial_log),
        ]
        launcher_argv.append("--")
        command_argv = list(item["argv"])
        sentinel_count = command_argv.count(TRUSTED_PYTEST_CONFIG_SENTINEL)
        if item["id"] == "quarantine-tests":
            if sentinel_count != 1:
                stop(receipt_path, "INVALID_EXPECTED_COMMAND")
            command_argv = [
                str(trusted_pytest_config)
                if token == TRUSTED_PYTEST_CONFIG_SENTINEL
                else token
                for token in command_argv
            ]
        elif sentinel_count != 0:
            stop(receipt_path, "INVALID_EXPECTED_COMMAND")
        launcher_argv.extend(command_argv)
        process = subprocess.run(
            launcher_argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            isolated_raw = regular_single_link_bytes(
                isolated_receipt,
                receipt_path,
                "LAUNCH_RECEIPT_INVALID",
                max_bytes=MAX_LAUNCH_RECEIPT_BYTES,
            )
            isolated = decode_strict_json(isolated_raw)
        except (OSError, ValueError):
            stop(receipt_path, "LAUNCH_RECEIPT_INVALID")
        if not isinstance(isolated, dict):
            stop(receipt_path, "LAUNCH_RECEIPT_INVALID")
        check_result = {
                "id": item["id"],
                "status": isolated.get("status"),
                "exit_code": isolated.get("exit_code"),
                "profile_class": isolated.get("profile_class"),
                "sandbox_invocations": isolated.get("sandbox_invocations"),
                "boundary_evidence": isolated.get("boundary_evidence"),
                "resource_limits": (
                    isolated.get("resource_evidence", {}).get("limits")
                    if isinstance(isolated.get("resource_evidence"), dict)
                    else None
                ),
                "resource_status": (
                    isolated.get("resource_evidence", {}).get("observed_status")
                    if isinstance(isolated.get("resource_evidence"), dict)
                    else None
                ),
            }
        if isinstance(isolated.get("evidence"), list):
            check_result["failure_evidence"] = isolated["evidence"]
        results.append(check_result)
        if process.returncode != 0 or isolated.get("status") != "PASS":
            stop(receipt_path, "CANDIDATE_CHECK_FAILED", checks=results)
        if isolated.get("child_cleanup_performed") is True:
            stop(receipt_path, "CANDIDATE_CHILD_SURVIVED", checks=results)
        if (
            isolated.get("schema") != "samvil.release-control.launch-receipt.v1"
            or isolated.get("profile_class") != CANDIDATE_PROFILE_CLASS
            or isolated.get("sandbox_exec_count") != 1
            or isolated.get("sandbox_invocations") != 1
            or isolated.get("boundary_evidence")
            != EXPECTED_CANDIDATE_BOUNDARY_EVIDENCE
            or not isinstance(isolated.get("resource_evidence"), dict)
            or isolated["resource_evidence"].get("limits")
            != EXPECTED_CANDIDATE_RESOURCE_LIMITS
            or isolated["resource_evidence"].get("observed_status")
            != "within_limits"
            or isolated.get("timed_out") is not False
            or isolated.get("exit_code") != 0
            or isolated.get("promotable") is not False
        ):
            stop(receipt_path, "LAUNCH_RECEIPT_INVALID", checks=results)
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--control-root", required=True, type=Path)
    parser.add_argument("--expected-control-commit", required=True)
    parser.add_argument("--signature-policy", required=True, choices=("required", "local-only"))
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--expected-public-key-sha256")
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args(argv)


def main() -> int:
    raw_argv = sys.argv[1:]
    if any(
        token == "--inherited-sandbox-context"
        or token.startswith("--inherited-sandbox-context=")
        for token in raw_argv
    ) or any(
        key.startswith(BOOTSTRAP_PREFIX) for key in os.environ
    ):
        print("INHERITED_CANDIDATE_MODE_REJECTED", file=sys.stderr)
        return 2
    args = parse_args(raw_argv)
    try:
        tmpdir, receipt_path = validate_receipt_target(
            os.environ.get("TMPDIR", ""), args.receipt
        )
    except (OSError, RuntimeError, ValueError):
        print("VERIFIER_RECEIPT_INVALID", file=sys.stderr)
        return 2
    args.receipt = receipt_path
    if not isinstance(args.nonce, str) or HEX64.fullmatch(args.nonce) is None:
        stop(args.receipt, "INVALID_NONCE")
    try:
        candidate = args.candidate.resolve(strict=True)
        authorization_path = args.authorization.resolve(strict=True)
        control = args.control_root.resolve(strict=True)
    except (OSError, RuntimeError):
        stop(args.receipt, "INVALID_LOCAL_INPUT")
    if (
        str(candidate) != str(args.candidate)
        or str(authorization_path) != str(args.authorization)
        or str(control) != str(args.control_root)
        or not candidate.is_dir()
        or not control.is_dir()
    ):
        stop(args.receipt, "INVALID_LOCAL_INPUT")
    if is_within(authorization_path, candidate):
        stop(args.receipt, "CANDIDATE_LOCAL_AUTHORIZATION")
    try:
        authorization_bytes = regular_single_link_bytes(
            authorization_path,
            args.receipt,
            "AUTHORIZATION_FILE_INVALID",
            max_bytes=MAX_AUTHORIZATION_BYTES,
        )
        authorization = decode_strict_json(authorization_bytes)
    except (OSError, ValueError):
        stop(args.receipt, "AUTHORIZATION_SCHEMA_INVALID")
    if isinstance(authorization, dict) and "nonce" not in authorization:
        stop(args.receipt, "INVALID_NONCE")
    authorization = exact_object(
        authorization,
        AUTHORIZATION_FIELDS,
        args.receipt,
        "AUTHORIZATION_SCHEMA_INVALID",
    )
    schema_version = authorization.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        stop(args.receipt, "AUTHORIZATION_SCHEMA_INVALID")
    authorization_nonce = authorization.get("nonce")
    if (
        not isinstance(authorization_nonce, str)
        or HEX64.fullmatch(authorization_nonce) is None
    ):
        stop(args.receipt, "INVALID_NONCE")
    if authorization_nonce != args.nonce:
        stop(args.receipt, "NONCE_MISMATCH")

    with tempfile.TemporaryDirectory(
        prefix="samvil-quarantine-verify-", dir=tmpdir
    ) as raw_temp:
        temp_root = Path(raw_temp).resolve()
        env = clean_env(temp_root)
        runner = verify_control(
            control,
            args.expected_control_commit,
            authorization,
            env,
            args.receipt,
        )
        launcher_env = env
        key_digest = verify_signature(
            args.signature_policy,
            args.public_key,
            args.signature,
            args.expected_public_key_sha256,
            authorization_bytes,
            args.receipt,
        )
        pinned_python = verify_pinned_python(authorization, args.receipt)
        commit, tree, inventory, verified_blobs = verify_candidate(
            candidate, authorization, env, args.receipt
        )
        commands = required_commands(authorization, pinned_python, args.receipt)
        if args.signature_policy == "local-only":
            write_json(
                args.receipt,
                receipt(
                    "BLOCKED_RELEASE_AUTHORIZATION",
                    candidate_commit=commit,
                    candidate_tree=tree,
                    authorization_sha256=sha256(authorization_bytes),
                    control_commit=args.expected_control_commit,
                    public_key_sha256=key_digest,
                ),
            )
            return 3
        snapshot = temp_root / "snapshot"
        try:
            materialize_snapshot(
                snapshot,
                inventory,
                verified_blobs,
                args.nonce,
                prebound=False,
            )
        except (OSError, ValueError):
            stop(args.receipt, "UNSAFE_GIT_ENTRY")
        try:
            trusted_pytest_config = create_trusted_pytest_config(snapshot)
        except ValueError:
            stop(args.receipt, "TRUSTED_PYTEST_CONFIG_INVALID")
        checks = execute_checks(
            runner,
            snapshot,
            commands,
            args.nonce,
            launcher_env,
            pinned_python,
            trusted_pytest_config,
            args.receipt,
        )
        common = {
            "candidate_commit": commit,
            "candidate_tree": tree,
            "inventory_sha256": sha256(
                json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
            "authorization_sha256": sha256(authorization_bytes),
            "control_commit": args.expected_control_commit,
            "public_key_sha256": key_digest,
            "checks": checks,
        }
        write_json(args.receipt, receipt("PASS", **common))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
