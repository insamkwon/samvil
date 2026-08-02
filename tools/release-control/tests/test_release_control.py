#!/usr/bin/env python3
"""Adversarial tests for the trusted release-control boundary."""

from __future__ import annotations

import ast
import base64
import contextlib
import ctypes
import dataclasses
from dataclasses import asdict, dataclass
import errno
import hashlib
import importlib.util
import inspect
import io
import json
import math
import mmap
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import stat
import tarfile
import tempfile
import textwrap
import time
import unicodedata
import unittest
from unittest import mock


TOOLS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_ROOT))

import inherited_context as inherited

_launcher_spec = importlib.util.spec_from_file_location(
    "samvil_release_control_launcher", TOOLS_ROOT / "run-isolated.py"
)
if _launcher_spec is None or _launcher_spec.loader is None:
    raise RuntimeError("release-control launcher cannot be imported")
launcher = importlib.util.module_from_spec(_launcher_spec)
sys.modules[_launcher_spec.name] = launcher
_launcher_spec.loader.exec_module(launcher)

_verifier_spec = importlib.util.spec_from_file_location(
    "samvil_release_control_verifier", TOOLS_ROOT / "verify-quarantine-candidate.py"
)
if _verifier_spec is None or _verifier_spec.loader is None:
    raise RuntimeError("release-control verifier cannot be imported")
verifier = importlib.util.module_from_spec(_verifier_spec)
sys.modules[_verifier_spec.name] = verifier
_verifier_spec.loader.exec_module(verifier)

_full_gate_spec = importlib.util.spec_from_file_location(
    "samvil_release_control_full_gate", TOOLS_ROOT / "run-full-gate-isolated.py"
)
if _full_gate_spec is None or _full_gate_spec.loader is None:
    raise RuntimeError("release-control full-gate runner cannot be imported")
full_gate = importlib.util.module_from_spec(_full_gate_spec)
sys.modules[_full_gate_spec.name] = full_gate
_full_gate_spec.loader.exec_module(full_gate)


RUNNER = TOOLS_ROOT / "run-isolated.py"
FULL_GATE_RUNNER = TOOLS_ROOT / "run-full-gate-isolated.py"
VERIFIER = TOOLS_ROOT / "verify-quarantine-candidate.py"
SYSTEM_PYTHON = Path(sys.executable)
PINNED_RUNTIME_SOURCE_ENV = "SAMVIL_PINNED_RUNTIME_SOURCE"
REQUIRE_COMPLETE_RELEASE_CONTROL_ENV = "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL"
ENABLE_REAL_SEATBELT_TESTS_ENV = "SAMVIL_ENABLE_REAL_SEATBELT_TESTS"
ENABLE_DARWIN_COPIED_RUNTIME_TESTS_ENV = (
    "SAMVIL_ENABLE_DARWIN_COPIED_RUNTIME_TESTS"
)
ENABLE_REAL_LINUX_PROC_TESTS_ENV = "SAMVIL_ENABLE_REAL_LINUX_PROC_TESTS"
PINNED_PYTEST_COMPONENTS = (
    "_pytest",
    "iniconfig",
    "iniconfig-2.3.0.dist-info",
    "packaging",
    "packaging-26.2.dist-info",
    "pluggy",
    "pluggy-1.6.0.dist-info",
    "py.py",
    "pygments",
    "pygments-2.20.0.dist-info",
    "pytest",
    "pytest-9.1.1.dist-info",
    "pytest_asyncio",
    "pytest_asyncio-1.4.0.dist-info",
    "typing_extensions.py",
    "typing_extensions-4.16.0.dist-info",
)
PINNED_PYTEST_IMPORTS = (
    "_pytest",
    "iniconfig",
    "packaging",
    "pluggy",
    "py",
    "pygments",
    "pytest",
    "pytest_asyncio",
    "typing_extensions",
)
COPIED_RUNTIME_PROBE_SOURCE = r'''
import importlib
import json
import pathlib
import sys

module_names = (
    "_pytest",
    "iniconfig",
    "packaging",
    "pluggy",
    "py",
    "pygments",
    "pytest",
    "pytest_asyncio",
    "typing_extensions",
)
module_paths = {}
for name in module_names:
    module = importlib.import_module(name)
    module_paths[name] = getattr(module, "__file__", None)

mapped_files = []
maps = pathlib.Path("/proc/self/maps")
if sys.platform.startswith("linux") and maps.is_file():
    for line in maps.read_text(encoding="utf-8", errors="strict").splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[5].startswith("/"):
            mapped_files.append(fields[5])

payload = {
    "schema": "samvil.copied-runtime-probe.v1",
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "sys_path": sys.path,
    "module_paths": module_paths,
    "mapped_files": sorted(set(mapped_files)),
}
sys.stdout.buffer.write(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
)
'''.strip()


class ReleaseControlConfigurationError(RuntimeError):
    def __init__(self, status: str, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status


class ReleaseControlHarnessError(RuntimeError):
    def __init__(
        self, status: str, detail: str = "", *, primary_status: str | None = None
    ) -> None:
        super().__init__(f"{status}: {detail}" if detail else status)
        self.status = status
        self.primary_status = primary_status


@dataclass(frozen=True)
class RealSeatbeltContext:
    sandbox_executable: Path
    pinned_runtime_source: Path
    invocation_tmpdir: Path


@dataclass(frozen=True)
class RealSeatbeltOptInContext:
    sandbox_executable: Path
    invocation_tmpdir: Path


@dataclass(frozen=True)
class CopiedRuntimeExecutionContext:
    pinned_runtime_source: Path
    invocation_tmpdir: Path


def _strict_opt_in(
    environment: dict[str, str] | os._Environ[str], name: str
) -> bool:
    raw = environment.get(name)
    if raw is None:
        return False
    if raw == "1":
        return True
    raise ReleaseControlConfigurationError(
        "RELEASE_CONTROL_FLAG_INVALID", f"{name} must be exactly 1 or unset"
    )


def _configuration_error_or_skip(
    environment: dict[str, str] | os._Environ[str], status: str, detail: str
) -> None:
    if _strict_opt_in(environment, REQUIRE_COMPLETE_RELEASE_CONTROL_ENV):
        raise ReleaseControlConfigurationError(status, detail)
    raise unittest.SkipTest(f"{status}: {detail}")


def resolve_pinned_runtime_source(
    environment: dict[str, str] | os._Environ[str],
) -> Path | None:
    raw = environment.get(PINNED_RUNTIME_SOURCE_ENV)
    if raw is None or not raw.strip():
        return None
    runtime = Path(raw)
    if not runtime.is_absolute():
        raise ValueError(f"{PINNED_RUNTIME_SOURCE_ENV} must be an absolute path")
    resolved = runtime.resolve(strict=True)
    if not (resolved / "bin/python3.12").is_file():
        raise ValueError(
            f"{PINNED_RUNTIME_SOURCE_ENV} must contain bin/python3.12"
        )
    if (resolved / "pyvenv.cfg").exists():
        raise ValueError(
            f"{PINNED_RUNTIME_SOURCE_ENV} must reference a base Python installation, not a virtual environment"
        )
    return resolved


def require_pinned_runtime_source(
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> Path:
    try:
        source = resolve_pinned_runtime_source(environment)
    except (OSError, RuntimeError, ValueError) as exc:
        _configuration_error_or_skip(
            environment, "PINNED_RUNTIME_INVALID", str(exc)
        )
    if source is None:
        _configuration_error_or_skip(
            environment,
            "PINNED_RUNTIME_REQUIRED",
            f"set {PINNED_RUNTIME_SOURCE_ENV} to an approved Python 3.12 runtime",
        )
    return source


def require_invocation_tmpdir(
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> Path:
    raw = environment.get("TMPDIR")
    if raw is None or not raw.strip():
        _configuration_error_or_skip(
            environment,
            "INVOCATION_TMPDIR_INVALID",
            "trusted bootstrap must provide an invocation-owned TMPDIR",
        )
    candidate = Path(raw)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _configuration_error_or_skip(
            environment, "INVOCATION_TMPDIR_INVALID", str(exc)
        )
    if not candidate.is_absolute() or not resolved.is_dir():
        _configuration_error_or_skip(
            environment,
            "INVOCATION_TMPDIR_INVALID",
            "TMPDIR must be an existing absolute directory",
        )
    return resolved


def require_copied_runtime_execution(
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> CopiedRuntimeExecutionContext:
    runtime_source = require_pinned_runtime_source(environment)
    tmpdir = require_invocation_tmpdir(environment)
    if platform.system() == "Darwin" and not _strict_opt_in(
        environment, ENABLE_DARWIN_COPIED_RUNTIME_TESTS_ENV
    ):
        _configuration_error_or_skip(
            environment,
            "DARWIN_COPIED_RUNTIME_OPT_IN_REQUIRED",
            f"set {ENABLE_DARWIN_COPIED_RUNTIME_TESTS_ENV}=1 after host restart and validation",
        )
    return CopiedRuntimeExecutionContext(
        pinned_runtime_source=runtime_source,
        invocation_tmpdir=tmpdir,
    )


def require_real_seatbelt_opt_in(
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> RealSeatbeltOptInContext:
    if not _strict_opt_in(environment, ENABLE_REAL_SEATBELT_TESTS_ENV):
        raise unittest.SkipTest(
            f"REAL_SEATBELT_OPT_IN_REQUIRED: set {ENABLE_REAL_SEATBELT_TESTS_ENV}=1"
        )
    if platform.system() != "Darwin" or platform.machine().lower() != "arm64":
        raise ReleaseControlConfigurationError(
            "REAL_SEATBELT_UNSUPPORTED",
            "real Seatbelt tests require a supported Darwin arm64 host",
        )
    sandbox_executable = Path("/usr/bin/sandbox-exec")
    try:
        resolved_sandbox = sandbox_executable.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseControlConfigurationError(
            "REAL_SEATBELT_UNSUPPORTED", str(exc)
        ) from None
    if (
        resolved_sandbox != sandbox_executable
        or not resolved_sandbox.is_file()
        or not os.access(resolved_sandbox, os.X_OK)
    ):
        raise ReleaseControlConfigurationError(
            "REAL_SEATBELT_UNSUPPORTED",
            "canonical /usr/bin/sandbox-exec is unavailable",
        )
    return RealSeatbeltOptInContext(
        sandbox_executable=resolved_sandbox,
        invocation_tmpdir=require_invocation_tmpdir(environment),
    )


def require_real_seatbelt_context(
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> RealSeatbeltContext:
    host_context = require_real_seatbelt_opt_in(environment)
    runtime_context = require_copied_runtime_execution(environment)
    runtime_source = runtime_context.pinned_runtime_source
    executable = runtime_source / "bin/python3.12"
    try:
        slices = full_gate._macho_slices(executable.read_bytes())
    except (OSError, full_gate.FullGateError):
        raise ReleaseControlConfigurationError(
            "REAL_SEATBELT_UNSUPPORTED",
            "pinned Python must be a supported Mach-O runtime",
        ) from None
    if "arm64" not in slices and "arm64e" not in slices:
        raise ReleaseControlConfigurationError(
            "REAL_SEATBELT_UNSUPPORTED",
            "pinned Python must contain an arm64 slice",
        )
    return RealSeatbeltContext(
        sandbox_executable=host_context.sandbox_executable,
        pinned_runtime_source=runtime_source,
        invocation_tmpdir=host_context.invocation_tmpdir,
    )


def copy_pinned_runtime(
    destination: Path,
    *,
    environment: dict[str, str] | os._Environ[str] = os.environ,
    runtime_source: Path | None = None,
    pytest_source: Path | None = None,
) -> None:
    source_runtime = runtime_source or require_pinned_runtime_source(environment)

    def ignore_broken_links(directory: str, names: list[str]) -> set[str]:
        root = Path(directory)
        ignored = {
            name
            for name in names
            if (root / name).is_symlink() and not (root / name).exists()
        }
        if (
            root.resolve(strict=True)
            == source_runtime / "lib/python3.12"
        ):
            ignored.add("site-packages")
        return ignored

    shutil.copytree(
        source_runtime,
        destination,
        symlinks=False,
        ignore=ignore_broken_links,
    )
    fixture_site_packages = pytest_source or (
        TOOLS_ROOT.parents[1] / "mcp/.venv/lib/python3.12/site-packages"
    )
    destination_site_packages = destination / "lib/python3.12/site-packages"
    destination_site_packages.mkdir()
    for name in PINNED_PYTEST_COMPONENTS:
        source = fixture_site_packages / name
        if not source.exists():
            _configuration_error_or_skip(
                environment,
                "PINNED_PYTEST_COMPONENT_MISSING",
                f"pinned pytest fixture component missing: {name}",
            )
        target = destination_site_packages / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            shutil.copy2(source, target)


def _harness_process_group_exists(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise ReleaseControlHarnessError(
            "HARNESS_CLEANUP_FAILED", str(exc)
        ) from None
    return True


def _terminate_harness_process_group(
    process: subprocess.Popen[bytes], *, primary_status: str
) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        try:
            process.communicate(timeout=2)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise ReleaseControlHarnessError(
                "HARNESS_CLEANUP_FAILED",
                str(exc),
                primary_status=primary_status,
            ) from None
        return
    except (OSError, ValueError) as exc:
        raise ReleaseControlHarnessError(
            "HARNESS_CLEANUP_FAILED", str(exc), primary_status=primary_status
        ) from None
    try:
        process.communicate(timeout=0.25)
    except subprocess.TimeoutExpired:
        pass
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReleaseControlHarnessError(
            "HARNESS_CLEANUP_FAILED", str(exc), primary_status=primary_status
        ) from None
    else:
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            if not _harness_process_group_exists(process):
                return
            time.sleep(0.01)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except (OSError, ValueError) as exc:
        raise ReleaseControlHarnessError(
            "HARNESS_CLEANUP_FAILED", str(exc), primary_status=primary_status
        ) from None
    try:
        process.communicate(timeout=2)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReleaseControlHarnessError(
            "HARNESS_CLEANUP_FAILED", str(exc), primary_status=primary_status
        ) from None
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            if not _harness_process_group_exists(process):
                return
        except ReleaseControlHarnessError as exc:
            raise ReleaseControlHarnessError(
                "HARNESS_CLEANUP_FAILED",
                str(exc),
                primary_status=primary_status,
            ) from None
        time.sleep(0.01)
    raise ReleaseControlHarnessError(
        "HARNESS_CLEANUP_FAILED",
        "process group survived SIGKILL",
        primary_status=primary_status,
    )

def _close_owned_harness_fds(
    descriptors: tuple[int, ...], *, primary_exception: BaseException | None
) -> None:
    first_error: OSError | None = None
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        primary_status = (
            getattr(
                primary_exception,
                "status",
                type(primary_exception).__name__,
            )
            if primary_exception is not None
            else None
        )
        blocker = ReleaseControlHarnessError(
            "HARNESS_FD_CLOSE_FAILED",
            str(first_error),
            primary_status=primary_status,
        )
        if primary_exception is None:
            raise blocker from None
        raise blocker from primary_exception


def _close_owned_harness_fd(
    descriptor: int, *, primary_exception: BaseException | None
) -> None:
    _close_owned_harness_fds(
        (descriptor,), primary_exception=primary_exception
    )


def _close_owned_harness_owners(
    owners: tuple[full_gate._OwnedDescriptor, ...],
    *,
    primary_exception: BaseException | None,
) -> None:
    first_error: BaseException | None = None
    for owner in owners:
        error = full_gate._close_owned_descriptor_with_retry(owner)
        if first_error is None and error is not None:
            first_error = error
    if first_error is None:
        return
    if not isinstance(first_error, OSError):
        raise first_error
    primary_status = (
        getattr(
            primary_exception,
            "status",
            type(primary_exception).__name__,
        )
        if primary_exception is not None
        else None
    )
    blocker = ReleaseControlHarnessError(
        "HARNESS_FD_CLOSE_FAILED",
        str(first_error),
        primary_status=primary_status,
    )
    if primary_exception is None:
        raise blocker from None
    raise blocker from primary_exception


def _close_owned_harness_owner(
    owner: full_gate._OwnedDescriptor,
    *,
    primary_exception: BaseException | None,
) -> None:
    _close_owned_harness_owners(
        (owner,), primary_exception=primary_exception
    )


def run_bounded_harness_process(
    argv: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    tmpdir: Path,
    timeout: float,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[bytes]:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ReleaseControlHarnessError("HARNESS_TIMEOUT_INVALID")
    with tempfile.TemporaryFile(mode="w+b", dir=tmpdir) as stdout_handle, tempfile.TemporaryFile(
        mode="w+b", dir=tmpdir
    ) as stderr_handle:
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                close_fds=True,
                pass_fds=pass_fds,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise ReleaseControlHarnessError(
                "HARNESS_SPAWN_FAILED", str(exc)
            ) from None
        try:
            outcome = full_gate.supervise_process(
                process,
                timeout=timeout,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            )
        except BaseException as primary:
            try:
                if _harness_process_group_exists(process):
                    _terminate_harness_process_group(
                        process,
                        primary_status=getattr(
                            primary, "status", "HARNESS_INTERRUPTED"
                        ),
                    )
                else:
                    process.communicate(timeout=2)
            except BaseException as cleanup_error:
                raise cleanup_error from primary
            if isinstance(primary, full_gate.FullGateError):
                raise ReleaseControlHarnessError(
                    "HARNESS_SUPERVISION_FAILED", primary.status
                ) from primary
            raise
        if outcome.timed_out:
            raise ReleaseControlHarnessError("HARNESS_TIMEOUT")
        if outcome.resource_status is not None:
            raise ReleaseControlHarnessError(
                "HARNESS_RESOURCE_LIMIT", outcome.resource_status
            )
        if outcome.cleanup_performed:
            raise ReleaseControlHarnessError(
                "HARNESS_DESCENDANT_CLEANUP_REQUIRED"
            )
        return subprocess.CompletedProcess(
            argv, outcome.returncode, outcome.stdout, outcome.stderr
        )


def probe_copied_runtime_pytest(
    pinned_python: Path,
    environment: dict[str, str] | os._Environ[str] = os.environ,
    *,
    execution_context: CopiedRuntimeExecutionContext | None = None,
) -> None:
    context = execution_context or require_copied_runtime_execution(environment)
    tmpdir = context.invocation_tmpdir
    try:
        runtime_root = pinned_python.parent.parent.resolve(strict=True)
        expected_python = pinned_python.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _configuration_error_or_skip(
            environment, "COPIED_RUNTIME_NOT_HERMETIC", str(exc)
        )
    probe_environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmpdir),
        "CODEX_HOME": str(tmpdir),
        "TMPDIR": str(tmpdir),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    argv = [
        str(pinned_python),
        "-I",
        "-B",
        "-c",
        COPIED_RUNTIME_PROBE_SOURCE,
    ]
    try:
        probe = run_bounded_harness_process(
            argv,
            cwd=tmpdir,
            environment=probe_environment,
            tmpdir=tmpdir,
            timeout=10,
        )
    except ReleaseControlHarnessError as exc:
        _configuration_error_or_skip(
            environment, "COPIED_RUNTIME_PYTEST_UNAVAILABLE", str(exc)
        )
    if probe.returncode != 0:
        _configuration_error_or_skip(
            environment,
            "COPIED_RUNTIME_PYTEST_UNAVAILABLE",
            "copied pinned Python lacks isolated pytest",
        )
    if probe.stderr:
        _configuration_error_or_skip(
            environment,
            "COPIED_RUNTIME_NOT_HERMETIC",
            "copied runtime probe wrote stderr",
        )
    try:
        decoded = full_gate.decode_canonical_json_bytes(
            probe.stdout,
            status="COPIED_RUNTIME_NOT_HERMETIC",
            max_bytes=1024 * 1024,
        )
    except full_gate.FullGateError as exc:
        _configuration_error_or_skip(environment, exc.status, str(exc))
    expected_fields = {
        "schema",
        "executable",
        "prefix",
        "base_prefix",
        "sys_path",
        "module_paths",
        "mapped_files",
    }
    if not isinstance(decoded, dict) or set(decoded) != expected_fields:
        _configuration_error_or_skip(
            environment,
            "COPIED_RUNTIME_NOT_HERMETIC",
            "copied runtime probe schema is invalid",
        )

    def resolved_path(value: object, *, must_exist: bool) -> Path:
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise ValueError("probe path must be a non-empty absolute path")
        return Path(value).resolve(strict=must_exist)

    def require_within_runtime(value: object, *, must_exist: bool) -> Path:
        resolved = resolved_path(value, must_exist=must_exist)
        try:
            resolved.relative_to(runtime_root)
        except ValueError:
            raise ValueError(f"path escapes copied runtime: {resolved}") from None
        return resolved

    try:
        if decoded["schema"] != "samvil.copied-runtime-probe.v1":
            raise ValueError("copied runtime probe schema version mismatch")
        if require_within_runtime(decoded["executable"], must_exist=True) != expected_python:
            raise ValueError("copied runtime executable identity mismatch")
        if require_within_runtime(decoded["prefix"], must_exist=True) != runtime_root:
            raise ValueError("copied runtime prefix mismatch")
        if require_within_runtime(decoded["base_prefix"], must_exist=True) != runtime_root:
            raise ValueError("copied runtime base_prefix mismatch")
        sys_path = decoded["sys_path"]
        if not isinstance(sys_path, list) or not sys_path:
            raise ValueError("copied runtime sys.path is invalid")
        for entry in sys_path:
            require_within_runtime(entry, must_exist=False)
        module_paths = decoded["module_paths"]
        if not isinstance(module_paths, dict) or set(module_paths) != set(
            PINNED_PYTEST_IMPORTS
        ):
            raise ValueError("copied runtime module closure is incomplete")
        for entry in module_paths.values():
            require_within_runtime(entry, must_exist=True)
        mapped_files = decoded["mapped_files"]
        if not isinstance(mapped_files, list):
            raise ValueError("copied runtime mapped-file closure is invalid")
        system_roots = tuple(
            Path(path).resolve(strict=True)
            for path in ("/lib", "/usr/lib")
            if Path(path).exists()
        )
        for entry in mapped_files:
            resolved = resolved_path(entry, must_exist=True)
            if resolved.is_relative_to(runtime_root):
                continue
            if any(resolved.is_relative_to(root) for root in system_roots):
                continue
            raise ValueError(f"mapped file escapes copied runtime: {resolved}")
    except (OSError, RuntimeError, ValueError) as exc:
        _configuration_error_or_skip(
            environment, "COPIED_RUNTIME_NOT_HERMETIC", str(exc)
        )
OPENSSL = Path("/usr/bin/openssl")
BOOTSTRAP_NONCE_ENV = "SAMVIL_BOOTSTRAP_NONCE"
BOOTSTRAP_CONTEXT_DIGEST_ENV = "SAMVIL_BOOTSTRAP_CONTEXT_SHA256"
FOCUSED_BOUNDARY_CHILD_ENV = "SAMVIL_FOCUSED_BOUNDARY_CHILD"
FOCUSED_CONTEXT_ENV = "SAMVIL_FOCUSED_CONTEXT_PATH"
FOCUSED_EXECUTION_ROOT_ENV = "SAMVIL_FOCUSED_EXECUTION_ROOT"
FOCUSED_CLI_NONCE_ENV = "SAMVIL_FOCUSED_CLI_NONCE"
FOCUSED_RECEIPT_ENV = "SAMVIL_FOCUSED_RECEIPT_PATH"
FOCUSED_DENIAL_ENV = "SAMVIL_FOCUSED_DENIAL_PATH"
FOCUSED_ENVIRONMENT_KEYS_ENV = "SAMVIL_FOCUSED_ENVIRONMENT_KEYS_JSON"
FOCUSED_PROFILE_SHA256_ENV = "SAMVIL_FOCUSED_PROFILE_SHA256"
SAFE_COMMAND_ENVIRONMENT_KEYS = sorted(
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
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "PYTHONNOUSERSITE",
        "PYTHONDONTWRITEBYTECODE",
        "PIP_CONFIG_FILE",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "__CF_USER_TEXT_ENCODING",
    }
)
INDEPENDENT_PROFILE_CLASS = "release-control-network-zero"
CANDIDATE_PROFILE_CLASS = "release-candidate-network-zero"
INDEPENDENT_PROFILE_DECISIONS = (
    "execution_root_read=allow",
    "invocation_root_write=allow",
    "network=deny",
    "protected_read=deny",
    "protected_write=deny",
    "process_group=allow",
    "signal_children=allow",
    "signal_external=deny",
    "sysctl_read=deny",
    "mach_lookup=deny",
    "ipc_posix_shm=deny",
)
INDEPENDENT_SLOT_TOKENS = {
    "protected_root_one": b"{{PROTECTED_ROOT_ONE}}",
    "protected_root_two": b"{{PROTECTED_ROOT_TWO}}",
    "pinned_python_root": b"{{PINNED_PYTHON_ROOT}}",
    "execution_root": b"{{EXECUTION_ROOT}}",
    "invocation_root": b"{{INVOCATION_ROOT}}",
}
INDEPENDENT_PROFILE_PARTS: tuple[bytes | str, ...] = (
    b'(version 1)\n(import "system.sb")\n(deny default)\n(deny network*)\n'
    b"(deny system-socket)\n(allow process*)\n"
    b"(allow signal (target children))\n"
    b"(deny file-read-metadata file-test-existence (require-any (literal ",
    "protected_root_one",
    b") (subpath ",
    "protected_root_one",
    b") (literal ",
    "protected_root_two",
    b") (subpath ",
    "protected_root_two",
    b")))\n",
    b"(allow file-read-metadata file-test-existence)\n"
    b'(allow file-read* (subpath "/System") (subpath "/usr") '
    b'(subpath "/bin") (subpath "/sbin") (subpath "/Library/Apple") '
    b'(subpath "/Library/Developer/CommandLineTools") '
    b'(subpath "/private/var/db/dyld") (subpath ',
    "pinned_python_root",
    b") (subpath ",
    "execution_root",
    b") (subpath ",
    "invocation_root",
    b"))\n(allow file-write* (subpath ",
    "invocation_root",
    b"))",
)


def independent_profile_source() -> bytes:
    return b"".join(
        part if isinstance(part, bytes) else INDEPENDENT_SLOT_TOKENS[part]
        for part in INDEPENDENT_PROFILE_PARTS
    )


def independent_render_profile(
    execution_root: Path,
    invocation_root: Path,
    *,
    pinned_python_root: Path | None = None,
    protected_roots: tuple[Path, Path] | None = None,
) -> tuple[bytes, str, str]:
    if protected_roots is None:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
        protected_roots = (home, (home / ".codex").resolve(strict=True))
    values = {
        "protected_root_one": str(protected_roots[0]),
        "protected_root_two": str(protected_roots[1]),
        "pinned_python_root": str((pinned_python_root or Path(sys.prefix)).resolve()),
        "execution_root": str(execution_root),
        "invocation_root": str(invocation_root),
    }
    sentinels = {
        "protected_root_one": "<PROTECTED_ROOT_ONE>",
        "protected_root_two": "<PROTECTED_ROOT_TWO>",
        "pinned_python_root": "<PINNED_PYTHON_ROOT>",
        "execution_root": "<EXECUTION_ROOT>",
        "invocation_root": "<INVOCATION_ROOT>",
    }

    def render(replacements: dict[str, str]) -> bytes:
        return b"".join(
            part
            if isinstance(part, bytes)
            else json.dumps(replacements[part]).encode("utf-8")
            for part in INDEPENDENT_PROFILE_PARTS
        )

    profile = render(values)
    return profile, sha256(independent_profile_source()), sha256(render(sentinels))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def quota_authority_fixture() -> full_gate.InvocationStorageQuotaAuthority:
    return full_gate._make_invocation_storage_quota_authority(
        quota_bytes=full_gate.DEFAULT_RESOURCE_LIMITS["aggregate_bytes"],
        filesystem_identity_sha256="f" * 64,
    )


def canonical_codesign_channel_fixture(
    target: str, identifier: str
) -> dict[str, object]:
    slices = ["arm64e", "x86_64"]
    cdhash = "1" * 40
    cdhash_full = cdhash + "2" * 24
    verify_lines = [
        f"{target}: valid on disk",
        f"{target}: satisfies its Designated Requirement",
        f"{target}: explicit requirement satisfied",
    ]
    metadata_lines = [
        f"Executable={target}",
        f"Identifier={identifier}",
        "Format=Mach-O universal (arm64e x86_64)",
        "CodeDirectory v=20400 size=463 flags=0x0(none) hashes=9+2 location=embedded",
        "Platform identifier=16",
        "VersionPlatform=1",
        "VersionMin=984832",
        "VersionSDK=984832",
        "Hash type=sha256 size=32",
        f"CandidateCDHash sha256={cdhash}",
        f"CandidateCDHashFull sha256={cdhash_full}",
        "Hash choices=sha256",
        f"CMSDigest={cdhash_full}",
        "CMSDigestType=2",
        "Executable Segment base=0",
        "Executable Segment limit=16384",
        "Executable Segment flags=0x1",
        "Page size=4096",
        f"CDHash={cdhash}",
        "Signature size=4442",
        "Authority=Software Signing",
        "Authority=Apple Code Signing Certification Authority",
        "Authority=Apple Root CA",
        "Signed Time=Jan 1, 2026 at 00:00:00",
        "Info.plist=not bound",
        "TeamIdentifier=not set",
        "Sealed Resources=none",
    ]
    requirement = f'anchor apple and identifier "{identifier}"'
    return {
        "target_path": target,
        "signing_identifier": identifier,
        "expected_slices": slices,
        "verify_argv": [
            "/usr/bin/codesign",
            "--verify",
            "--strict",
            "--verbose=2",
            f"-R={requirement}",
            target,
        ],
        "verify_returncode": 0,
        "verify_stdout": b"",
        "verify_stderr": ("\n".join(verify_lines) + "\n").encode(),
        "display_argv": [
            "/usr/bin/codesign",
            "-d",
            "--verbose=4",
            "-r-",
            target,
        ],
        "display_returncode": 0,
        "display_stdout": (
            f'designated => identifier "{identifier}" and anchor apple\n'
        ).encode(),
        "display_stderr": ("\n".join(metadata_lines) + "\n").encode(),
    }


def real_canonical_platform_rows(scratch: Path) -> list[dict[str, object]]:
    codesign = Path("/usr/bin/codesign")
    sandbox_exec = Path("/usr/bin/sandbox-exec")

    def metadata(path: Path) -> dict[str, object]:
        observed = os.lstat(path)
        content = path.read_bytes()
        filesystem = os.statvfs(path)
        flags = []
        if getattr(observed, "st_flags", 0) & 0x00080000:
            flags.append("restricted")
        loads = subprocess.run(
            ["/usr/bin/otool", "-L", str(path)],
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=True,
        ).stdout.decode("utf-8", "strict")
        return {
            "path": str(path),
            "uid": observed.st_uid,
            "mode": f"{observed.st_mode:o}",
            "nlink": observed.st_nlink,
            "size": observed.st_size,
            "filesystem_flags": flags,
            "read_only_filesystem": bool(
                filesystem.f_flag & getattr(os, "ST_RDONLY", 1)
            ),
            "device": str(observed.st_dev),
            "inode": str(observed.st_ino),
            "sha256": sha256(content),
            "slices": list(full_gate._macho_slices(content)),
            "load_closure": [
                line.strip().split(" (", 1)[0]
                for line in loads.splitlines()[1:]
                if line.strip()
            ],
            "apple_anchor": True,
            "platform_identifier": 16,
        }

    legacy_codesign = full_gate.apple_platform_tcb_binding()["codesign_result"]
    sandbox_codesign = full_gate.parse_canonical_codesign_result(
        target_path=str(sandbox_exec),
        signing_identifier="com.apple.sandbox-exec",
        expected_slices=list(full_gate._macho_slices(sandbox_exec.read_bytes())),
        verify_argv=legacy_codesign["verify"]["argv"],
        verify_returncode=legacy_codesign["verify"]["returncode"],
        verify_stdout=legacy_codesign["verify"]["stdout"].encode("utf-8"),
        verify_stderr=legacy_codesign["verify"]["stderr"].encode("utf-8"),
        display_argv=legacy_codesign["display"]["argv"],
        display_returncode=legacy_codesign["display"]["returncode"],
        display_stdout=legacy_codesign["display"]["stdout"].encode("utf-8"),
        display_stderr=legacy_codesign["display"]["stderr"].encode("utf-8"),
    )
    codesign_display = subprocess.run(
        [str(codesign), "-d", "--verbose=4", "-r-", str(codesign)],
        cwd=scratch,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(scratch / "home-unavailable"),
            "CODEX_HOME": str(scratch / "codex-home-unavailable"),
            "TMPDIR": str(scratch),
            "LANG": "C",
            "LC_ALL": "C",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if codesign_display.returncode != 0:
        raise AssertionError("real codesign metadata probe failed")
    codesign_fields: dict[str, list[str]] = {}
    for line in codesign_display.stderr.decode("utf-8", "strict").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            codesign_fields.setdefault(key, []).append(value)
    codesign_identifier = codesign_fields["Identifier"][0]
    codesign_cdhash = codesign_fields["CDHash"][0]
    codesign_requirement = codesign_display.stdout.decode("utf-8", "strict").strip()

    behavior_argv = [
        str(sandbox_exec),
        "-p",
        "(version 1) (allow default)",
        "/usr/bin/true",
    ]
    behavior = subprocess.run(
        behavior_argv,
        cwd=scratch,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(scratch / "home-unavailable"),
            "CODEX_HOME": str(scratch / "codex-home-unavailable"),
            "TMPDIR": str(scratch),
            "LANG": "C",
            "LC_ALL": "C",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    behavior_payload = {
        "schema": "samvil.host-tool-behavior-result.v1",
        "target_path": str(sandbox_exec),
        "argv": behavior_argv,
        "returncode": behavior.returncode,
        "stdout_sha256": sha256(behavior.stdout),
        "stderr_sha256": sha256(behavior.stderr),
        "status": "GREEN",
    }
    return [
        {
            **metadata(codesign),
            "role": "codesign",
            "signing_identifier": codesign_identifier,
            "designated_requirement": codesign_requirement,
            "cdhash": codesign_cdhash,
            "behavior_probe": {
                "schema": "samvil.codesign-verifier-behavior.v1",
                "first_non_self_role": "sandbox-exec",
                "result_sha256": sandbox_codesign["result_sha256"],
            },
            "admission_state": "PLATFORM_VERIFIER_PINNED",
        },
        {
            **metadata(sandbox_exec),
            "role": "sandbox-exec",
            "signing_identifier": "com.apple.sandbox-exec",
            "designated_requirement": sandbox_codesign["designated_requirement"],
            "cdhash": sandbox_codesign["cdhash"],
            "behavior_probe": {
                "schema": "samvil.host-tool-behavior.v1",
                "argv": behavior_argv,
                "returncode": behavior.returncode,
                "stdout_sha256": sha256(behavior.stdout),
                "stderr_sha256": sha256(behavior.stderr),
                "result_sha256": sha256(
                    full_gate.canonical_json_bytes(behavior_payload)
                ),
            },
            "admission_state": "STATIC_ADMITTED",
        },
    ]


@dataclass(frozen=True)
class OuterAbsenceEvidence:
    absent: bool
    file_type: str | None
    mode: int | None
    device: int | None
    inode: int | None
    nlink: int | None
    size: int | None
    error_errno: str | None = None


class OuterArtifactBlocker(RuntimeError):
    def __init__(self, status: str, evidence: OuterAbsenceEvidence) -> None:
        super().__init__(status)
        self.status = status
        self.evidence = evidence


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character"
    if stat.S_ISBLK(mode):
        return "block"
    return "other"


def capture_outer_absence(path: Path, status: str) -> OuterAbsenceEvidence:
    error_errno: str | None = None
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return OuterAbsenceEvidence(True, None, None, None, None, None, None)
        error_errno = errno.errorcode.get(exc.errno, str(exc.errno))
    if error_errno is not None:
        raise OuterArtifactBlocker(
            status,
            OuterAbsenceEvidence(
                False,
                "lstat-error",
                None,
                None,
                None,
                None,
                None,
                error_errno,
            ),
        ) from None
    evidence = OuterAbsenceEvidence(
        absent=False,
        file_type=_file_type(metadata.st_mode),
        mode=stat.S_IMODE(metadata.st_mode),
        device=metadata.st_dev,
        inode=metadata.st_ino,
        nlink=metadata.st_nlink,
        size=metadata.st_size,
    )
    raise OuterArtifactBlocker(status, evidence)


class PinnedRuntimeFixtureResolutionTest(unittest.TestCase):
    def test_pinned_pytest_fixture_contains_explicit_async_plugin_closure(self) -> None:
        self.assertEqual(
            set(PINNED_PYTEST_COMPONENTS),
            {
                "_pytest",
                "iniconfig",
                "iniconfig-2.3.0.dist-info",
                "packaging",
                "packaging-26.2.dist-info",
                "pluggy",
                "pluggy-1.6.0.dist-info",
                "py.py",
                "pygments",
                "pygments-2.20.0.dist-info",
                "pytest",
                "pytest-9.1.1.dist-info",
                "pytest_asyncio",
                "pytest_asyncio-1.4.0.dist-info",
                "typing_extensions.py",
                "typing_extensions-4.16.0.dist-info",
            },
        )
        self.assertEqual(
            set(PINNED_PYTEST_IMPORTS),
            {
                "_pytest",
                "iniconfig",
                "packaging",
                "pluggy",
                "py",
                "pygments",
                "pytest",
                "pytest_asyncio",
                "typing_extensions",
            },
        )
        for module_name in PINNED_PYTEST_IMPORTS:
            self.assertIn(f'"{module_name}"', COPIED_RUNTIME_PROBE_SOURCE)

    def test_linux_portable_orchestration_fixture_owns_platform_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"portable-python")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            context = CopiedRuntimeExecutionContext(
                pinned_runtime_source=runtime,
                invocation_tmpdir=tmpdir,
            )
            case = PortableFullGateOrchestrationTest(
                "test_cleanup_failure_overrides_a_pass_and_writes_typed_blocker"
            )
            with mock.patch.object(
                platform, "system", return_value="Linux"
            ), mock.patch(
                f"{__name__}.require_copied_runtime_execution",
                return_value=context,
            ):
                case.setUp()
            try:
                control_identity = FullGateManifestProtocolTest().manifest()["control"]
                with mock.patch.object(
                    full_gate,
                    "apple_platform_tcb_binding",
                    side_effect=AssertionError(
                        "portable E2E fixture reached real Apple binding"
                    ),
                ), mock.patch(
                    f"{__name__}.real_canonical_platform_rows",
                    side_effect=AssertionError(
                        "portable E2E fixture reached real canonical tools"
                    ),
                ):
                    legacy = case.manifest_fixture("original", control_identity)
                    approved = case.approved_manifest_fixture(
                        "original", control_identity
                    )

                authority = full_gate.acquire_apple_platform_tcb(
                    legacy["apple_platform_tcb"], case.base
                )
                self.assertEqual(
                    authority.complete()["schema"],
                    "samvil.apple-platform-evidence.v1",
                )
                authority.close()

                parser_inputs = approved["host_tool_identity_parser"]["inputs"]
                self.assertTrue(parser_inputs)
                self.assertTrue(
                    all(
                        Path(entry["path"]).is_relative_to(case.base)
                        for entry in parser_inputs
                    )
                )

                copied_runtime = case.base / "portable-materialized-runtime"
                full_gate.materialize_closure_archive(
                    b"portable-fixture",
                    b"portable-fixture",
                    copied_runtime,
                    expected_role="python",
                )
                self.assertEqual(
                    (copied_runtime / "bin/python3.12").read_bytes(),
                    b"portable-python",
                )
            finally:
                case.tearDown()

    def test_linux_portable_orchestration_cases_execute_without_skips(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"portable-python")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            context = CopiedRuntimeExecutionContext(
                pinned_runtime_source=runtime,
                invocation_tmpdir=tmpdir,
            )
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(
                PortableFullGateOrchestrationTest
            )
            result = unittest.TestResult()
            with mock.patch.object(
                platform, "system", return_value="Linux"
            ), mock.patch(
                f"{__name__}.require_copied_runtime_execution",
                return_value=context,
            ):
                suite.run(result)
        self.assertEqual(result.testsRun, 4)
        self.assertFalse(result.skipped)
        self.assertFalse(result.failures)
        self.assertFalse(result.errors)

    def test_runtime_fixture_is_resolved_from_explicit_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            runtime = Path(raw_temp) / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            resolved = resolve_pinned_runtime_source(
                {"SAMVIL_PINNED_RUNTIME_SOURCE": str(runtime)}
            )
            self.assertEqual(resolved, runtime.resolve(strict=True))

    def test_runtime_fixture_is_unavailable_without_explicit_environment(self) -> None:
        self.assertIsNone(resolve_pinned_runtime_source({}))

    def test_runtime_fixture_rejects_virtual_environment_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            runtime = Path(raw_temp).resolve(strict=True)
            (runtime / "bin").mkdir()
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            (runtime / "pyvenv.cfg").write_text(
                "home = /outside/base-python\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                resolve_pinned_runtime_source(
                    {PINNED_RUNTIME_SOURCE_ENV: str(runtime)}
                )

    def test_complete_mode_missing_runtime_is_typed_configuration_error(self) -> None:
        self.assertIn(
            "require_pinned_runtime_source",
            globals(),
            "complete-mode pinned-runtime preflight is not implemented",
        )
        with self.assertRaises(ReleaseControlConfigurationError) as raised:
            require_pinned_runtime_source(
                {"SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1"}
            )
        self.assertEqual(raised.exception.status, "PINNED_RUNTIME_REQUIRED")

    def test_normal_mode_missing_runtime_remains_an_individual_typed_skip(self) -> None:
        self.assertIn(
            "require_pinned_runtime_source",
            globals(),
            "local pinned-runtime skip helper is not implemented",
        )
        with self.assertRaises(unittest.SkipTest) as raised:
            require_pinned_runtime_source({})
        self.assertIn("PINNED_RUNTIME_REQUIRED", str(raised.exception))

    def test_complete_mode_tmpdir_preflight_fails_before_any_subprocess(self) -> None:
        self.assertIn(
            "require_invocation_tmpdir",
            globals(),
            "complete-mode TMPDIR preflight is not implemented",
        )
        environments = (
            {"SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1"},
            {
                "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1",
                "TMPDIR": "relative",
            },
            {
                "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1",
                "TMPDIR": "/definitely/missing/samvil-release-control",
            },
        )
        for environment in environments:
            with self.subTest(environment=environment), mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("TMPDIR preflight reached Popen"),
            ), mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("TMPDIR preflight reached run"),
            ), self.assertRaises(ReleaseControlConfigurationError) as raised:
                require_invocation_tmpdir(environment)
            self.assertEqual(raised.exception.status, "INVOCATION_TMPDIR_INVALID")

    def test_real_seatbelt_preflight_is_opt_in_before_platform_or_subprocess(self) -> None:
        self.assertIn(
            "require_real_seatbelt_context",
            globals(),
            "real Seatbelt opt-in preflight is not implemented",
        )
        with mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("Seatbelt preflight reached Popen"),
        ), mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("Seatbelt preflight reached run"),
        ), self.assertRaises(unittest.SkipTest) as raised:
            require_real_seatbelt_context({})
        self.assertIn("REAL_SEATBELT_OPT_IN_REQUIRED", str(raised.exception))

    def test_opted_in_unsupported_seatbelt_host_is_typed_configuration_error(self) -> None:
        self.assertIn(
            "require_real_seatbelt_context",
            globals(),
            "real Seatbelt platform preflight is not implemented",
        )
        environment = {
            "SAMVIL_ENABLE_REAL_SEATBELT_TESTS": "1",
            "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1",
        }
        with mock.patch("platform.system", return_value="Linux"), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("unsupported Seatbelt host reached Popen"),
        ), mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("unsupported Seatbelt host reached run"),
        ), self.assertRaises(ReleaseControlConfigurationError) as raised:
            require_real_seatbelt_context(environment)
        self.assertEqual(raised.exception.status, "REAL_SEATBELT_UNSUPPORTED")

    def test_complete_mode_copied_pytest_probe_failure_is_typed(self) -> None:
        self.assertIn(
            "probe_copied_runtime_pytest",
            globals(),
            "copied-runtime pytest probe is not implemented",
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            python = root / "python3.12"
            python.write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            environment = {
                "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1",
                "TMPDIR": str(tmpdir),
            }
            failed = subprocess.CompletedProcess(
                [str(python), "-I", "-B", "-m", "pytest", "--version"],
                1,
                b"",
                b"probe failed",
            )
            with mock.patch(
                f"{__name__}.run_bounded_harness_process", return_value=failed
            ) as run:
                with self.assertRaises(ReleaseControlConfigurationError) as raised:
                    probe_copied_runtime_pytest(
                        python,
                        environment,
                        execution_context=CopiedRuntimeExecutionContext(
                            pinned_runtime_source=root,
                            invocation_tmpdir=tmpdir,
                        ),
                    )
            self.assertEqual(
                raised.exception.status, "COPIED_RUNTIME_PYTEST_UNAVAILABLE"
            )
            self.assertEqual(
                run.call_args.args[0],
                [str(python), "-I", "-B", "-c", COPIED_RUNTIME_PROBE_SOURCE],
            )

    def test_complete_mode_copied_runtime_outside_root_is_typed(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            python = runtime / "bin/python3.12"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            runtime_lib = runtime / "lib/python3.12"
            site_packages = runtime_lib / "site-packages"
            site_packages.mkdir(parents=True)
            module_paths: dict[str, str] = {}
            for name in PINNED_PYTEST_IMPORTS:
                module_path = site_packages / f"{name}.py"
                module_path.write_bytes(b"fixture")
                module_paths[name] = str(module_path)
            mapped_library = runtime / "lib/libpython3.12.so"
            mapped_library.write_bytes(b"fixture")
            outside = root / "outside-runtime"
            outside.mkdir()
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            probe_payload = {
                "schema": "samvil.copied-runtime-probe.v1",
                "executable": str(python),
                "prefix": str(runtime),
                "base_prefix": str(runtime),
                "sys_path": [str(runtime_lib), str(outside)],
                "module_paths": module_paths,
                "mapped_files": [str(mapped_library)],
            }
            completed = subprocess.CompletedProcess(
                [str(python), "-I", "-B", "-c", "probe"],
                0,
                full_gate.canonical_json_bytes(probe_payload),
                b"",
            )
            environment = {
                REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1",
                "TMPDIR": str(tmpdir),
            }
            with mock.patch(
                f"{__name__}.run_bounded_harness_process",
                return_value=completed,
            ), self.assertRaises(ReleaseControlConfigurationError) as raised:
                probe_copied_runtime_pytest(
                    python,
                    environment,
                    execution_context=CopiedRuntimeExecutionContext(
                        pinned_runtime_source=runtime,
                        invocation_tmpdir=tmpdir,
                    ),
                )
        self.assertEqual(
            raised.exception.status, "COPIED_RUNTIME_NOT_HERMETIC"
        )

    def test_complete_mode_copied_runtime_contained_closure_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            python = runtime / "bin/python3.12"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            runtime_lib = runtime / "lib/python3.12"
            site_packages = runtime_lib / "site-packages"
            site_packages.mkdir(parents=True)
            module_paths: dict[str, str] = {}
            for name in PINNED_PYTEST_IMPORTS:
                module_path = site_packages / f"{name}.py"
                module_path.write_bytes(b"fixture")
                module_paths[name] = str(module_path)
            mapped_library = runtime / "lib/libpython3.12.so"
            mapped_library.write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            probe_payload = {
                "schema": "samvil.copied-runtime-probe.v1",
                "executable": str(python),
                "prefix": str(runtime),
                "base_prefix": str(runtime),
                "sys_path": [str(runtime_lib), str(site_packages)],
                "module_paths": module_paths,
                "mapped_files": [str(mapped_library)],
            }
            completed = subprocess.CompletedProcess(
                [str(python), "-I", "-B", "-c", "probe"],
                0,
                full_gate.canonical_json_bytes(probe_payload),
                b"",
            )
            with mock.patch(
                f"{__name__}.run_bounded_harness_process",
                return_value=completed,
            ):
                probe_copied_runtime_pytest(
                    python,
                    {
                        REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1",
                        "TMPDIR": str(tmpdir),
                    },
                    execution_context=CopiedRuntimeExecutionContext(
                        pinned_runtime_source=runtime,
                        invocation_tmpdir=tmpdir,
                    ),
                )

    def test_complete_mode_missing_pytest_component_is_typed(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp)
            runtime = root / "runtime-source"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            (runtime / "lib/python3.12").mkdir(parents=True)
            pytest_source = root / "pytest-source"
            pytest_source.mkdir()
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            with self.assertRaises(ReleaseControlConfigurationError) as raised:
                copy_pinned_runtime(
                    root / "copied",
                    environment={
                        "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1",
                        "TMPDIR": str(tmpdir),
                    },
                    runtime_source=runtime,
                    pytest_source=pytest_source,
                )
            self.assertEqual(
                raised.exception.status, "PINNED_PYTEST_COMPONENT_MISSING"
            )

    def test_missing_runtime_is_accounted_per_release_control_test(self) -> None:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseControlTest)
        result = unittest.TestResult()
        with mock.patch.dict(os.environ, {}, clear=True):
            suite.run(result)
        self.assertEqual(result.testsRun, suite.countTestCases())
        self.assertEqual(len(result.skipped), suite.countTestCases())
        self.assertFalse(result.errors)

    def test_complete_mode_runtime_setup_io_failure_is_accounted_per_test(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            context = CopiedRuntimeExecutionContext(
                pinned_runtime_source=runtime,
                invocation_tmpdir=tmpdir,
            )
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(
                ReleaseControlTest
            )
            expected = suite.countTestCases()
            with mock.patch.dict(
                os.environ,
                {
                    REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1",
                    "TMPDIR": str(tmpdir),
                },
                clear=True,
            ), mock.patch(
                f"{__name__}.require_copied_runtime_execution",
                return_value=context,
            ), mock.patch(
                f"{__name__}.copy_pinned_runtime",
                side_effect=OSError(errno.EIO, "injected runtime copy failure"),
            ):
                result = unittest.TestResult()
                suite.run(result)
        self.assertEqual(result.testsRun, expected)
        self.assertEqual(len(result.errors), expected)
        self.assertFalse(result.skipped)
        self.assertTrue(
            all("PINNED_RUNTIME_SETUP_FAILED" in detail for _test, detail in result.errors)
        )

    def test_complete_mode_turns_all_pinned_test_skips_into_errors(self) -> None:
        suites = [
            unittest.defaultTestLoader.loadTestsFromName(
                "FullGateMaterializationAndRuntimeTest."
                "test_real_copied_macho_python_identity_and_import_closure_are_exact",
                module=sys.modules[__name__],
            ),
            unittest.TestSuite(
                unittest.defaultTestLoader.loadTestsFromName(
                    f"FullGateTrustedWrapperDirectIntegrationTest.{name}",
                    module=sys.modules[__name__],
                )
                for name in (
                    "test_candidate_observation_and_frame_spoof_cannot_reach_authority_fd",
                    "test_candidate_toctou_mutation_prevents_complete_pass_frame",
                    "test_real_profile_denies_snapshot_mutation_and_still_runs_fixed_probes",
                )
            ),
            unittest.defaultTestLoader.loadTestsFromTestCase(
                PortableFullGateOrchestrationTest
            ),
        ]
        suite = unittest.TestSuite(suites)
        result = unittest.TestResult()
        with mock.patch.object(
            platform, "system", return_value="Linux"
        ), mock.patch.dict(
            os.environ,
            {"SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": "1"},
            clear=True,
        ):
            suite.run(result)
        self.assertEqual(suite.countTestCases(), 8)
        self.assertEqual(result.testsRun, 8)
        self.assertEqual(len(result.errors), 8)
        self.assertFalse(result.skipped)

    def test_complete_mode_without_real_seatbelt_opt_in_is_still_a_typed_skip(
        self,
    ) -> None:
        with mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("Seatbelt skip reached Popen"),
        ), mock.patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("Seatbelt skip reached run"),
        ), self.assertRaises(unittest.SkipTest) as raised:
            require_real_seatbelt_context(
                {REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1"}
            )
        self.assertIn("REAL_SEATBELT_OPT_IN_REQUIRED", str(raised.exception))

    def test_strict_opt_in_rejects_false_like_spellings(self) -> None:
        for value in ("", "0", "true"):
            with self.subTest(value=value), self.assertRaises(
                ReleaseControlConfigurationError
            ) as raised:
                _strict_opt_in(
                    {"SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL": value},
                    "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL",
                )
            self.assertEqual(raised.exception.status, "RELEASE_CONTROL_FLAG_INVALID")

    def test_darwin_pinned_runtime_alone_skips_before_subprocess(self) -> None:
        self.assertIn(
            "require_copied_runtime_execution",
            globals(),
            "Darwin copied-runtime execution preflight is not implemented",
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            environment = {
                PINNED_RUNTIME_SOURCE_ENV: str(runtime),
                "TMPDIR": str(tmpdir),
            }
            with mock.patch.object(
                platform, "system", return_value="Darwin"
            ), mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("Darwin runtime preflight reached Popen"),
            ), mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("Darwin runtime preflight reached run"),
            ), self.assertRaises(unittest.SkipTest) as raised:
                require_copied_runtime_execution(environment)
        self.assertIn("DARWIN_COPIED_RUNTIME_OPT_IN_REQUIRED", str(raised.exception))

    def test_complete_mode_darwin_runtime_without_opt_in_is_configuration_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            environment = {
                PINNED_RUNTIME_SOURCE_ENV: str(runtime),
                REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1",
                "TMPDIR": str(tmpdir),
            }
            with mock.patch.object(
                platform, "system", return_value="Darwin"
            ), mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("Darwin runtime preflight reached Popen"),
            ), mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("Darwin runtime preflight reached run"),
            ), self.assertRaises(ReleaseControlConfigurationError) as raised:
                require_copied_runtime_execution(environment)
        self.assertEqual(
            raised.exception.status, "DARWIN_COPIED_RUNTIME_OPT_IN_REQUIRED"
        )

    def test_linux_copied_runtime_remains_portable_without_darwin_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"ELF fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            environment = {
                PINNED_RUNTIME_SOURCE_ENV: str(runtime),
                REQUIRE_COMPLETE_RELEASE_CONTROL_ENV: "1",
                "TMPDIR": str(tmpdir),
            }
            with mock.patch.object(platform, "system", return_value="Linux"):
                context = require_copied_runtime_execution(environment)
        self.assertEqual(context.pinned_runtime_source, runtime)
        self.assertEqual(context.invocation_tmpdir, tmpdir)

    def test_darwin_copied_runtime_gate_precedes_all_pinned_execution_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            runtime = root / "runtime"
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin/python3.12").write_bytes(b"fixture")
            tmpdir = root / "tmp"
            tmpdir.mkdir()
            environment = {
                PINNED_RUNTIME_SOURCE_ENV: str(runtime),
                "TMPDIR": str(tmpdir),
            }
            suites = [
                unittest.defaultTestLoader.loadTestsFromName(
                    "FullGateMaterializationAndRuntimeTest."
                    "test_real_copied_macho_python_identity_and_import_closure_are_exact",
                    module=sys.modules[__name__],
                ),
                unittest.defaultTestLoader.loadTestsFromTestCase(
                    FullGateTrustedWrapperDirectIntegrationTest
                ),
                unittest.defaultTestLoader.loadTestsFromTestCase(
                    PortableFullGateOrchestrationTest
                ),
                unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseControlTest),
            ]
            suite = unittest.TestSuite(suites)
            expected = suite.countTestCases()
            pure_mock_tests = len(
                (
                    "test_parent_authority_close_interruption_cleans_spawned_group",
                    "test_sandboxed_wrapper_is_opt_in_before_copy_or_spawn",
                    "test_wrapper_supervisor_cleanup_required_is_typed",
                    "test_wrapper_supervisor_timeout_is_typed_without_blocking_pipe_reads",
                )
            )
            result = unittest.TestResult()
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
                platform, "system", return_value="Darwin"
            ), mock.patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("Darwin copied runtime gate reached Popen"),
            ), mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("Darwin copied runtime gate reached run"),
            ):
                suite.run(result)
        self.assertEqual(result.testsRun, expected)
        self.assertEqual(len(result.skipped), expected - pure_mock_tests)
        self.assertFalse(result.errors)
        self.assertFalse(result.failures)


class ReleaseControlHarnessSupervisionTest(unittest.TestCase):
    class FakeProcess:
        def __init__(self, communicate_results: list[object]) -> None:
            self.pid = 424242
            self.returncode = 0
            self._communicate_results = iter(communicate_results)

        def communicate(self, timeout: float | None = None) -> tuple[None, None]:
            result = next(self._communicate_results)
            if isinstance(result, BaseException):
                raise result
            return (None, None)

    def test_bounded_process_uses_tempfile_captures_and_new_session(self) -> None:
        self.assertIn(
            "run_bounded_harness_process",
            globals(),
            "bounded harness process helper is not implemented",
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            fake = self.FakeProcess([None])
            clean_outcome = full_gate.GateOutcome(
                0, False, False, None, b"", b""
            )
            with mock.patch.object(
                subprocess, "Popen", return_value=fake
            ) as popen, mock.patch.object(
                full_gate, "supervise_process", return_value=clean_outcome
            ) as supervise:
                completed = run_bounded_harness_process(
                    ["/approved/python", "-I", "-B", "-c", "pass"],
                    cwd=root,
                    environment={"TMPDIR": str(root)},
                    tmpdir=root,
                    timeout=1,
                )
        self.assertEqual(completed.returncode, 0)
        kwargs = popen.call_args.kwargs
        self.assertTrue(kwargs["start_new_session"])
        self.assertIsNot(kwargs["stdout"], subprocess.PIPE)
        self.assertIsNot(kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        supervise.assert_called_once()

    def test_bounded_process_rejects_resource_and_cleanup_outcomes(self) -> None:
        cases = (
            (
                full_gate.GateOutcome(
                    0,
                    False,
                    True,
                    None,
                    b"",
                    b"",
                ),
                "HARNESS_DESCENDANT_CLEANUP_REQUIRED",
            ),
            (
                full_gate.GateOutcome(
                    -signal.SIGTERM,
                    False,
                    True,
                    "GATE_STDOUT_BYTES_EXCEEDED",
                    b"",
                    b"",
                ),
                "HARNESS_RESOURCE_LIMIT",
            ),
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            for outcome, expected in cases:
                with self.subTest(expected=expected):
                    fake = self.FakeProcess([None])
                    with mock.patch.object(
                        subprocess, "Popen", return_value=fake
                    ), mock.patch.object(
                        full_gate, "supervise_process", return_value=outcome
                    ), mock.patch.object(
                        os, "killpg", side_effect=ProcessLookupError
                    ), self.assertRaises(ReleaseControlHarnessError) as raised:
                        run_bounded_harness_process(
                            ["/approved/python", "-I", "-B", "-c", "pass"],
                            cwd=root,
                            environment={"TMPDIR": str(root)},
                            tmpdir=root,
                            timeout=1,
                        )
                self.assertEqual(raised.exception.status, expected)

    def test_timeout_escalates_term_to_kill_and_preserves_timeout_status(self) -> None:
        self.assertIn(
            "run_bounded_harness_process",
            globals(),
            "bounded harness timeout cleanup is not implemented",
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            timeout = subprocess.TimeoutExpired(("/approved/python",), 0.01)
            fake = self.FakeProcess([timeout, None])
            signals: list[int] = []
            killed = False

            def observe_cleanup(_pid: int, sig: int) -> None:
                nonlocal killed
                if sig == 0 and killed:
                    raise ProcessLookupError
                if sig != 0:
                    signals.append(sig)
                if sig == signal.SIGKILL:
                    killed = True

            with mock.patch.object(
                os, "killpg", side_effect=observe_cleanup
            ):
                _terminate_harness_process_group(
                    fake, primary_status="HARNESS_TIMEOUT"
                )
        self.assertEqual(signals, [signal.SIGTERM, signal.SIGKILL])

    def test_spawn_failure_is_typed(self) -> None:
        self.assertIn(
            "run_bounded_harness_process",
            globals(),
            "bounded harness spawn typing is not implemented",
        )
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            with mock.patch.object(
                subprocess, "Popen", side_effect=OSError(errno.ENOEXEC, "injected")
            ), self.assertRaises(ReleaseControlHarnessError) as raised:
                run_bounded_harness_process(
                    ["/approved/python"],
                    cwd=root,
                    environment={"TMPDIR": str(root)},
                    tmpdir=root,
                    timeout=1,
                )
        self.assertEqual(raised.exception.status, "HARNESS_SPAWN_FAILED")

    def test_interruption_still_cleans_the_spawned_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            fake = self.FakeProcess([None])
            with mock.patch.object(
                subprocess, "Popen", return_value=fake
            ), mock.patch.object(
                full_gate, "supervise_process", side_effect=KeyboardInterrupt
            ), mock.patch(
                f"{__name__}._harness_process_group_exists", return_value=True
            ), mock.patch(
                f"{__name__}._terminate_harness_process_group"
            ) as terminate, self.assertRaises(KeyboardInterrupt):
                run_bounded_harness_process(
                    ["/approved/python"],
                    cwd=root,
                    environment={"TMPDIR": str(root)},
                    tmpdir=root,
                    timeout=1,
                )
        terminate.assert_called_once_with(
            fake, primary_status="HARNESS_INTERRUPTED"
        )

    def test_nonfinite_timeout_is_rejected_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            for timeout in (float("nan"), float("inf")):
                with self.subTest(timeout=timeout), mock.patch.object(
                    subprocess,
                    "Popen",
                    side_effect=AssertionError("invalid timeout reached Popen"),
                ), self.assertRaises(ReleaseControlHarnessError) as raised:
                    run_bounded_harness_process(
                        ["/approved/python"],
                        cwd=root,
                        environment={"TMPDIR": str(root)},
                        tmpdir=root,
                        timeout=timeout,
                    )
                self.assertEqual(raised.exception.status, "HARNESS_TIMEOUT_INVALID")

    def test_timeout_cleanup_fails_if_group_survives_sigkill(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            root = Path(raw_temp).resolve(strict=True)
            timeout = subprocess.TimeoutExpired(("/approved/python",), 0.01)
            fake = self.FakeProcess([timeout, None])

            def persistent_group(_pid: int, _sig: int) -> None:
                return None

            with mock.patch.object(
                os, "killpg", side_effect=persistent_group
            ), mock.patch.object(
                time, "monotonic", side_effect=(0.0, 2.0)
            ), self.assertRaises(ReleaseControlHarnessError) as raised:
                _terminate_harness_process_group(
                    fake, primary_status="HARNESS_TIMEOUT"
                )
        self.assertEqual(raised.exception.status, "HARNESS_CLEANUP_FAILED")
        self.assertEqual(raised.exception.primary_status, "HARNESS_TIMEOUT")

    def test_wrapper_direct_runner_uses_supervisor_without_pipe_backpressure(self) -> None:
        source = inspect.getsource(
            FullGateTrustedWrapperDirectIntegrationTest.run_wrapper
        )
        self.assertNotIn("stdout=subprocess.PIPE", source)
        self.assertNotIn("stderr=subprocess.PIPE", source)
        self.assertNotIn("os.read(", source)
        self.assertIn("full_gate.supervise_process", source)
        self.assertIn("start_new_session=True", source)

    def test_copied_pytest_probe_uses_bounded_group_supervision(self) -> None:
        source = inspect.getsource(probe_copied_runtime_pytest)
        self.assertIn("run_bounded_harness_process", source)
        self.assertNotIn("subprocess.run", source)
        self.assertIn('"-I"', source)
        self.assertIn('"-B"', source)

    def test_real_seatbelt_integrations_are_runtime_opt_in_not_decorated(self) -> None:
        for test_class in (
            LauncherDirectC3Test,
            InheritedLauncherIntegrationFixture,
            LauncherSupervisionC5Test,
        ):
            with self.subTest(test_class=test_class.__name__):
                self.assertFalse(
                    getattr(test_class, "__unittest_skip__", False),
                    f"{test_class.__name__} is still import-time sandbox gated",
                )
                self.assertIn(
                    "require_real_seatbelt_opt_in",
                    inspect.getsource(test_class.setUp),
                )
        for method in (
            ReleaseControlTest.test_signed_candidate_passes_external_direct_candidate_profile,
            ReleaseControlTest.test_historical_pytest_and_script_shadow_surfaces_are_unreachable,
        ):
            with self.subTest(method=method.__name__):
                self.assertFalse(getattr(method, "__unittest_skip__", False))
                self.assertIn(
                    "require_real_seatbelt_opt_in", inspect.getsource(method)
                )
        release_setup = inspect.getsource(ReleaseControlTest.setUpClass)
        self.assertIn("require_copied_runtime_execution", release_setup)
        self.assertNotIn("require_real_seatbelt_context", release_setup)

    def test_fd_close_failure_replaces_and_preserves_active_primary(self) -> None:
        self.assertIn(
            "_close_owned_harness_fd",
            globals(),
            "owned harness FD close helper is not implemented",
        )
        primary = ReleaseControlHarnessError("PRIMARY_FAILURE")
        with mock.patch.object(
            os, "close", side_effect=OSError(errno.EIO, "injected")
        ), self.assertRaises(ReleaseControlHarnessError) as raised:
            _close_owned_harness_fd(7, primary_exception=primary)
        self.assertEqual(raised.exception.status, "HARNESS_FD_CLOSE_FAILED")
        self.assertEqual(raised.exception.primary_status, "PRIMARY_FAILURE")
        self.assertIs(raised.exception.__cause__, primary)

    def test_fd_close_failure_without_primary_is_typed(self) -> None:
        self.assertIn(
            "_close_owned_harness_fd",
            globals(),
            "owned harness FD close helper is not implemented",
        )
        with mock.patch.object(
            os, "close", side_effect=OSError(errno.EIO, "injected")
        ), self.assertRaises(ReleaseControlHarnessError) as raised:
            _close_owned_harness_fd(7, primary_exception=None)
        self.assertEqual(raised.exception.status, "HARNESS_FD_CLOSE_FAILED")

    def test_fd_batch_closes_each_owned_descriptor_exactly_once(self) -> None:
        self.assertIn(
            "_close_owned_harness_fds",
            globals(),
            "owned harness FD batch close helper is not implemented",
        )
        closed: list[int] = []

        def close_with_first_failure(descriptor: int) -> None:
            closed.append(descriptor)
            if descriptor == 7:
                raise OSError(errno.EIO, "injected")

        with mock.patch.object(
            os, "close", side_effect=close_with_first_failure
        ), self.assertRaises(ReleaseControlHarnessError) as raised:
            _close_owned_harness_fds((7, 8), primary_exception=None)
        self.assertEqual(raised.exception.status, "HARNESS_FD_CLOSE_FAILED")
        self.assertEqual(closed, [7, 8])


class FullGateRunnerGrammarTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-grammar-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": str(self.base),
        }
        self.manifest = self.base / "manifest.json"
        self.manifest.write_text("{}", encoding="utf-8")
        self.receipt = self.base / "receipt.json"
        self.denial = self.base / "denial.log"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_runner(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SYSTEM_PYTHON), str(FULL_GATE_RUNNER), *argv],
            cwd=self.base,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_reordered_unknown_and_command_tail_are_typed_no_write_blockers(self) -> None:
        exact = [
            "--manifest",
            str(self.manifest),
            "--nonce",
            "a" * 64,
            "--timeout",
            "10",
            "--receipt",
            str(self.receipt),
            "--denial-log",
            str(self.denial),
        ]
        variants = (
            exact[2:4] + exact[0:2] + exact[4:],
            exact + ["--profile-class", "pinned-full-gate-loopback-only"],
            exact + ["--", "bash", "scripts/pre-commit-check.sh"],
        )

        for argv in variants:
            with self.subTest(argv=argv):
                result = self.run_runner(argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("FULL_GATE_USAGE", result.stderr)
                self.assertFalse(self.receipt.exists())
                self.assertFalse(self.denial.exists())

    def test_environment_authority_is_rejected_before_manifest_or_outputs(self) -> None:
        exact = [
            "--manifest",
            str(self.manifest),
            "--nonce",
            "a" * 64,
            "--timeout",
            "10",
            "--receipt",
            str(self.receipt),
            "--denial-log",
            str(self.denial),
        ]
        for key in (
            "PROFILE_CLASS",
            "SAMVIL_PROFILE_CLASS",
            "SAMVIL_FULL_GATE_ROOT",
            "SAMVIL_FULL_GATE_PROFILE_CLASS",
        ):
            with self.subTest(key=key):
                environment = dict(self.env, **{key: "candidate-selected"})
                result = self.run_runner_with_env(exact, environment)
                self.assertEqual(result.returncode, 2)
                self.assertIn("FULL_GATE_ENV_AUTHORITY_REJECTED", result.stderr)
                self.assertFalse(self.receipt.exists())
                self.assertFalse(self.denial.exists())

    def run_runner_with_env(
        self, argv: list[str], environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SYSTEM_PYTHON), str(FULL_GATE_RUNNER), *argv],
            cwd=self.base,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_cli_loads_canonical_manifest_and_binds_prior_before_artifacts(self) -> None:
        exact_tail = [
            "--nonce",
            "a" * 64,
            "--timeout",
            "10",
            "--receipt",
            str(self.receipt),
            "--denial-log",
            str(self.denial),
        ]
        for kind, extra, status in (
            ("candidate_postcommit", [], "PRIOR_RECEIPT_REQUIRED"),
            (
                "candidate_precommit",
                ["--prior-receipt", str(self.base / "prior.json")],
                "PRIOR_RECEIPT_FORBIDDEN",
            ),
        ):
            manifest = FullGateManifestProtocolTest().manifest(kind)
            self.manifest.write_bytes(full_gate.canonical_json_bytes(manifest))
            argv = ["--manifest", str(self.manifest), *extra, *exact_tail]
            result = self.run_runner(argv)
            with self.subTest(kind=kind):
                self.assertEqual(result.returncode, 2)
                self.assertIn(status, result.stderr)
                self.assertFalse(self.receipt.exists())
                self.assertFalse(self.denial.exists())


class FullGateManifestProtocolTest(unittest.TestCase):
    def artifact(self, path: str = "artifact.json") -> dict[str, str]:
        return {"path": f"/trusted/{path}", "sha256": "d" * 64}

    def inventory(self, path: str) -> dict[str, str]:
        manifest = {
            "path": path,
            "mode": "100644",
            "blob": "b" * 40,
            "sha256": "c" * 64,
        }
        return manifest

    def legacy_apple_platform_tcb(self) -> dict[str, object]:
        def tool(
            classification: str, path: str, digest: str, size: int, inode: int
        ) -> dict[str, object]:
            return {
                "schema": "samvil.apple-platform-tool.v1",
                "classification": classification,
                "path": path,
                "uid": 0,
                "gid": 0,
                "mode": "100755",
                "nlink": 1,
                "size": size,
                "sha256": digest,
                "slices": ["x86_64", "arm64e"],
                "path_identity": {
                    "device": 1,
                    "inode": inode,
                    "mode": stat.S_IFREG | 0o755,
                    "nlink": 1,
                    "size": size,
                    "mtime_ns": 1,
                    "ctime_ns": 1,
                    "uid": 0,
                    "gid": 0,
                },
            }

        sandbox = tool(
            "apple_platform_tool", "/usr/bin/sandbox-exec", "a" * 64, 102560, 1
        )
        codesign = tool(
            "apple_platform_identity_verifier",
            "/usr/bin/codesign",
            "b" * 64,
            378144,
            2,
        )
        cdhash = "1" * 40
        cdhash_full = cdhash + "2" * 24
        metadata_lines = [
            "Executable=/usr/bin/sandbox-exec",
            "Identifier=com.apple.sandbox-exec",
            "Format=Mach-O universal (x86_64 arm64e)",
            "CodeDirectory v=20400 size=463 flags=0x0(none) hashes=9+2 location=embedded",
            "Platform identifier=16",
            "VersionPlatform=1",
            "VersionMin=984832",
            "VersionSDK=984832",
            "Hash type=sha256 size=32",
            f"CandidateCDHash sha256={cdhash}",
            f"CandidateCDHashFull sha256={cdhash_full}",
            "Hash choices=sha256",
            f"CMSDigest={cdhash_full}",
            "CMSDigestType=2",
            "Executable Segment base=0",
            "Executable Segment limit=16384",
            "Executable Segment flags=0x1",
            "Page size=4096",
            f"CDHash={cdhash}",
            "Signature size=4442",
            "Authority=Software Signing",
            "Authority=Apple Code Signing Certification Authority",
            "Authority=Apple Root CA",
            "Signed Time=Jan 1, 2026 at 00:00:00",
            "Info.plist=not bound",
            "TeamIdentifier=not set",
            "Sealed Resources=none",
        ]
        verify_statements = [
            "/usr/bin/sandbox-exec: valid on disk",
            "/usr/bin/sandbox-exec: satisfies its Designated Requirement",
            "/usr/bin/sandbox-exec: explicit requirement satisfied",
        ]
        parsed_payload = {
            "requirement": 'anchor apple and identifier "com.apple.sandbox-exec"',
            "designated_requirement": 'designated => identifier "com.apple.sandbox-exec" and anchor apple',
            "identifier": "com.apple.sandbox-exec",
            "format": "Mach-O universal (x86_64 arm64e)",
            "platform_identifier": 16,
            "slices": ["x86_64", "arm64e"],
            "cdhash": cdhash,
            "cdhash_full": cdhash_full,
            "authorities": [
                "Software Signing",
                "Apple Code Signing Certification Authority",
                "Apple Root CA",
            ],
            "metadata_lines": metadata_lines,
            "verify_statements": verify_statements,
        }
        parsed = {
            **parsed_payload,
            "result_sha256": sha256(full_gate.canonical_json_bytes(parsed_payload)),
        }
        verify = {
            "argv": [
                "/usr/bin/codesign",
                "--verify",
                "--strict",
                "--verbose=2",
                '-R=anchor apple and identifier "com.apple.sandbox-exec"',
                "/usr/bin/sandbox-exec",
            ],
            "returncode": 0,
            "stdout": "",
            "stderr": "\n".join(verify_statements) + "\n",
        }
        display = {
            "argv": [
                "/usr/bin/codesign",
                "-d",
                "--verbose=4",
                "-r-",
                "/usr/bin/sandbox-exec",
            ],
            "returncode": 0,
            "stdout": 'designated => identifier "com.apple.sandbox-exec" and anchor apple\n',
            "stderr": "\n".join(metadata_lines) + "\n",
        }
        result_payload = {
            "verify": verify,
            "display": display,
            "parsed": parsed,
            "verifier_identity_sha256": sha256(
                full_gate.canonical_json_bytes(codesign)
            ),
        }
        return {
            "schema": "samvil.apple-platform-tcb.v1",
            "sandbox_exec": sandbox,
            "codesign": codesign,
            "codesign_result": {
                **result_payload,
                "result_sha256": sha256(
                    full_gate.canonical_json_bytes(result_payload)
                ),
            },
        }

    def canonical_host_row(
        self,
        role: str,
        path: str,
        admission_state: str,
        *,
        inode: int,
    ) -> dict[str, object]:
        behavior_payload = {
            "schema": "samvil.host-tool-behavior-result.v1",
            "target_path": path,
            "argv": [path, "--samvil-probe"],
            "returncode": 0,
            "stdout_sha256": sha256(b""),
            "stderr_sha256": sha256(b""),
            "status": "GREEN",
        }
        return {
            "role": role,
            "path": path,
            "uid": 0,
            "mode": "100755",
            "nlink": 1,
            "size": 4096,
            "filesystem_flags": ["restricted"],
            "read_only_filesystem": True,
            "device": 1,
            "inode": inode,
            "sha256": f"{inode:x}" * 64,
            "slices": ["arm64e", "x86_64"],
            "load_closure": [],
            "apple_anchor": True,
            "signing_identifier": f"com.apple.{role}",
            "platform_identifier": 16,
            "designated_requirement": f'anchor apple and identifier "com.apple.{role}"',
            "cdhash": f"{inode:x}" * 40,
            "behavior_probe": (
                {
                    "schema": "samvil.codesign-verifier-behavior.v1",
                    "first_non_self_role": "env",
                    "result_sha256": "f" * 64,
                }
                if role == "codesign"
                else {
                    "schema": "samvil.host-tool-behavior.v1",
                    "argv": behavior_payload["argv"],
                    "returncode": behavior_payload["returncode"],
                    "stdout_sha256": behavior_payload["stdout_sha256"],
                    "stderr_sha256": behavior_payload["stderr_sha256"],
                    "result_sha256": sha256(
                        full_gate.canonical_json_bytes(behavior_payload)
                    ),
                }
            ),
            "admission_state": admission_state,
        }

    def host_tool_identity_parser_fixture(self) -> dict[str, object]:
        source_sha256 = "a" * 64
        result_sha256 = "c" * 64
        return {
            "schema": "host-tool-identity-parser.v1",
            "authority": "task-2-external-controller",
            "staged_runner_authority": False,
            "source_sha256": source_sha256,
            "source_artifact": {
                "path": "/trusted/host-tool-identity-parser.py",
                "sha256": source_sha256,
            },
            "materialized": {
                "content_sha256": source_sha256,
                "mode": "100500",
                "interpreter": {
                    "classification": "copied_application_runtime",
                    "relative_path": "bin/python3.12",
                    "sha256": "b" * 64,
                },
            },
            "supported_schemas": ["code-directory.v1", "mach-o.v1"],
            "limits": {
                "file_bytes": 8 * 1024 * 1024,
                "aggregate_bytes": 32 * 1024 * 1024,
                "depth": 32,
                "load_commands": 4096,
            },
            "inputs": [
                {
                    "role": "codesign",
                    "path": "/trusted/codesign.fixture",
                    "device": 1,
                    "inode": 1,
                    "size": 378144,
                    "sha256": "d" * 64,
                },
                {
                    "role": "sandbox-exec",
                    "path": "/trusted/sandbox-exec.fixture",
                    "device": 1,
                    "inode": 2,
                    "size": 102560,
                    "sha256": "e" * 64,
                },
            ],
            "result_sha256": result_sha256,
            "staged_runner_comparison": {
                "source_sha256": "f" * 64,
                "result_sha256": result_sha256,
                "byte_identical": True,
                "authority": False,
            },
        }

    def copied_application_runtime_fixture(self) -> dict[str, object]:
        role_paths = {
            "git": (
                "/Library/Developer/CommandLineTools/usr/bin/git",
                "tools/usr/bin/git",
            ),
            "git-shell": (
                "/Library/Developer/CommandLineTools/usr/bin/git-shell",
                "tools/usr/bin/git-shell",
            ),
            "lipo": (
                "/Library/Developer/CommandLineTools/usr/bin/lipo",
                "tools/usr/bin/lipo",
            ),
            "otool": (
                "/Library/Developer/CommandLineTools/usr/bin/otool",
                "tools/usr/bin/otool",
            ),
            "scalar": (
                "/Library/Developer/CommandLineTools/usr/bin/scalar",
                "tools/usr/bin/scalar",
            ),
        }
        rows: list[dict[str, object]] = []
        for index, role in enumerate(sorted(role_paths), 1):
            source_path, destination_path = role_paths[role]
            rows.append(
                {
                    "role": role,
                    "source_path": source_path,
                    "destination_path": destination_path,
                    "platform_identifier": 0,
                    "filesystem_flags": [],
                    "mode": "100755",
                    "nlink": 1,
                    "size": 4096 + index,
                    "sha256": f"{index:x}" * 64,
                    "slices": ["arm64e", "x86_64"],
                    "load_closure": ["/usr/lib/libSystem.B.dylib"],
                    "exec_closure": {
                        "executables": (
                            [
                                "tools/usr/bin/git",
                                "tools/usr/libexec/git-core/git",
                                "tools/usr/libexec/git-core/git-commit",
                            ]
                            if role == "git"
                            else [destination_path]
                        ),
                        "git_core_root": (
                            "tools/usr/libexec/git-core" if role == "git" else None
                        ),
                        "topology_sha256": "6" * 64 if role == "git" else None,
                        "internal_symlink_count": 2 if role == "git" else 0,
                    },
                    "behavior_probe": {
                        "argv": [destination_path, "--version"],
                        "stdout_sha256": f"{index + 5:x}" * 64,
                    },
                    "admission_state": "STATIC_ADMITTED",
                }
            )
        allowlist = sorted(
            {
                *(row["destination_path"] for row in rows),
                "tools/usr/libexec/git-core/git",
                "tools/usr/libexec/git-core/git-commit",
                "tools/facade/bin/mktemp",
                "tools/facade/bin/python",
                "tools/facade/bin/python3",
                "tools/facade/bin/python3.12",
                "node/bin/node",
                "node/bin/npm",
                "node/bin/pnpm",
            }
        )
        return {
            "schema": "samvil.copied-application-runtime.v1",
            "portable_tools": rows,
            "exec_allowlist": allowlist,
            "path_order": [
                "tools/facade/bin",
                "tools/usr/bin",
                "node/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ],
        }

    def approved_host_tool_manifest(
        self, rows: list[dict[str, object]]
    ) -> dict[str, object]:
        manifest = self.manifest()
        manifest.pop("apple_platform_tcb")
        manifest["host_tool_identity_parser"] = (
            self.host_tool_identity_parser_fixture()
        )
        manifest["copied_application_runtime"] = (
            self.copied_application_runtime_fixture()
        )
        manifest["canonical_host_tools"] = {
            "schema": "samvil.canonical-host-tools.v1",
            "rows": rows,
        }
        manifest["command"] = ["/bin/bash", "scripts/pre-commit-check.sh"]
        return manifest

    def test_approved_manifest_requires_the_sandbox_executable_row(self) -> None:
        rows = [
            row
            for row in FullGateApprovedHostToolAuthorityDispatcherTest().canonical_rows()
            if row["role"] != "sandbox-exec"
        ]
        self.assertFalse(any(row["role"] == "sandbox-exec" for row in rows))
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(self.approved_host_tool_manifest(rows))
        self.assertEqual(raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN")

    def manifest(self, kind: str = "original") -> dict[str, object]:
        control_commit = "1" * 40
        control_tree = "2" * 40
        if kind == "original":
            target: dict[str, object] = {
                "kind": "original",
                "source_commit": "3" * 40,
                "tree": "4" * 40,
            }
        elif kind == "candidate_precommit":
            target = {
                "kind": "candidate_precommit",
                "tree": "4" * 40,
                "expected_parent": "3" * 40,
                "authorization_sha256": "5" * 64,
                "final_commit": None,
            }
        elif kind == "candidate_postcommit":
            target = {
                "kind": "candidate_postcommit",
                "final_commit": "6" * 40,
                "tree": "4" * 40,
                "expected_parent": "3" * 40,
                "precommit_tree": "4" * 40,
                "authorization_sha256": "5" * 64,
                "expected_precommit_nonce": "a" * 64,
                "expected_precommit_control_commit": control_commit,
                "expected_precommit_control_tree": control_tree,
                "expected_precommit_manifest_sha256": "7" * 64,
                "prior_receipt_sha256": "8" * 64,
            }
        else:
            raise AssertionError(kind)
        control_paths = (
            "tools/release-control/inherited_context.py",
            "tools/release-control/run-isolated.py",
            "tools/release-control/run-full-gate-isolated.py",
            "tools/release-control/verify-quarantine-candidate.py",
            "tools/release-control/tests/test_release_control.py",
        )
        runtime_roles = (
            "python_archive",
            "python_manifest",
            "dependency_archive",
            "dependency_manifest",
            "tool_archive",
            "tool_manifest",
            "facade_manifest",
        )
        manifest = {
            "schema": "samvil.full-gate-manifest.v1",
            "nonce": "a" * 64,
            "control": {
                "commit": control_commit,
                "tree": control_tree,
                "files": [self.inventory(path) for path in control_paths],
            },
            "target": target,
            "object_pack": self.artifact("objects.json"),
            "inventory": [
                self.inventory("scripts/pre-commit-check.sh"),
                self.inventory("scripts/phase6-real-runtime-dogfood.py"),
                self.inventory("mcp/tests/test_phase6_real_runtime_dogfood.py"),
                self.inventory("mcp/tests/test_example.py"),
            ],
            "trusted_wrapper": full_gate.trusted_wrapper_binding(),
            "probes": full_gate.trusted_probe_manifest(),
            "apple_platform_tcb": self.legacy_apple_platform_tcb(),
            "command": ["bash", "scripts/pre-commit-check.sh"],
            "gate_inventory": [self.inventory("scripts/pre-commit-check.sh")],
            "phase6_inventory": [
                self.inventory("scripts/phase6-real-runtime-dogfood.py"),
                self.inventory("mcp/tests/test_phase6_real_runtime_dogfood.py"),
            ],
            "collected_mcp_tests": [
                self.inventory("mcp/tests/test_example.py"),
                self.inventory("mcp/tests/test_phase6_real_runtime_dogfood.py"),
            ],
            "import_manifest": {
                "allowlist": ["samvil_mcp"],
                "sha256": "9" * 64,
            },
            "runtime": {
                "python_version": "3.12.13",
                "python_identity": {
                    "schema": "samvil.full-gate-python-identity.v1",
                    "major_minor": "3.12",
                    "version": "3.12.13",
                    "architecture": "arm64",
                    "slices": ["arm64"],
                    "executable_sha256": "e" * 64,
                    "file_description": "Mach-O 64-bit executable arm64",
                    "load_commands": ["/usr/lib/libSystem.B.dylib"],
                    "rpaths": ["@loader_path/../lib"],
                    "load_closure": [
                        {"load": "/usr/lib/libSystem.B.dylib", "kind": "system"}
                    ],
                    "runtime_probe": {
                        "version": "3.12.13",
                        "architecture": "arm64",
                        "executable": "bin/python3.12",
                        "prefix": ".",
                        "base_prefix": ".",
                        "sys_path": ["lib/python3.12"],
                        "modules": {},
                    },
                },
                **{role: self.artifact(f"{role}.json") for role in runtime_roles},
            },
            "fixed_logs": [
                "/tmp/samvil-pretest.log",
                "/tmp/samvil-mdrefs.log",
                "/tmp/samvil-hostparity.log",
                "/tmp/samvil-forward.log",
                "/tmp/samvil-agent-inventory.log",
            ],
            "semantic_counters": {
                "pytest_passed": 1,
                "mcp_tools": 1,
                "markdown_references": 1,
                "host_untested": 0,
                "forward_registered_tools": 1,
                "forward_cited_tools": 1,
                "agent_inventory_entries": 1,
            },
            "resource_limits": dict(full_gate.DEFAULT_RESOURCE_LIMITS),
            "receipt_fields": list(full_gate.RECEIPT_FIELDS),
        }
        manifest["import_manifest"]["sha256"] = sha256(
            full_gate.canonical_json_bytes(
                {
                    "allowlist": manifest["import_manifest"]["allowlist"],
                    "collected_mcp_tests": manifest["collected_mcp_tests"],
                }
            )
        )
        return manifest

    def prior_receipt(self) -> dict[str, object]:
        import_sha256 = sha256(
            full_gate.canonical_json_bytes(
                {
                    "allowlist": ["samvil_mcp"],
                    "collected_mcp_tests": [
                        self.inventory("mcp/tests/test_example.py"),
                        self.inventory("mcp/tests/test_phase6_real_runtime_dogfood.py"),
                    ],
                }
            )
        )
        return {
            "schema": "samvil.full-gate-receipt.v1",
            "status": "PASS",
            "verdict": "PASS",
            "nonce": "a" * 64,
            "control_commit": "1" * 40,
            "control_tree": "2" * 40,
            "target_kind": "candidate_precommit",
            "source_commit": None,
            "candidate_tree": "4" * 40,
            "final_commit": None,
            "expected_parent": "3" * 40,
            "authorization_sha256": "5" * 64,
            "manifest_sha256": "7" * 64,
            "prior_receipt_sha256": None,
            "command_sha256": "1" * 64,
            "content_sha256": "2" * 64,
            "profile_class": "pinned-full-gate-loopback-only",
            "profile_sha256": "3" * 64,
            "import_manifest_sha256": import_sha256,
            "identity_sha256": "4" * 64,
            "tree_sha256": "5" * 64,
            "runtime_sha256": "6" * 64,
            "storage_quota_evidence_sha256": "8" * 64,
            "semantic_counters": {
                "pytest_passed": 1,
                "mcp_tools": 1,
                "markdown_references": 1,
                "host_untested": 0,
                "forward_registered_tools": 1,
                "forward_cited_tools": 1,
                "agent_inventory_entries": 1,
            },
            "promotion_limitations": [
                "LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED",
                "DETACHED_DESCENDANT_NOT_OS_ISOLATED",
            ],
        }

    def test_manifest_schema_is_exact_and_profile_selection_is_forbidden(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "validate_manifest_object"),
            "full-gate manifest validation is not implemented",
        )
        manifest = self.manifest()
        validated = full_gate.validate_manifest_object(manifest)
        self.assertEqual(validated.target_kind, "original")

        for key in ("profile_class", "root", "candidate_root"):
            forged = dict(manifest)
            forged[key] = "candidate-selected"
            with self.subTest(key=key), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.validate_manifest_object(forged)
            self.assertEqual(raised.exception.status, "MANIFEST_FIELDS_INVALID")

        forged_import = self.manifest()
        forged_import["import_manifest"] = dict(
            forged_import["import_manifest"], sha256="f" * 64
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(forged_import)
        self.assertEqual(raised.exception.status, "IMPORT_MANIFEST_INVALID")

        for key, status in (
            ("trusted_wrapper", "TRUSTED_WRAPPER_MANIFEST_INVALID"),
            ("probes", "TRUSTED_PROBE_MANIFEST_INVALID"),
            ("apple_platform_tcb", "UNSUPPORTED_HERMETIC_RUNTIME"),
            ("resource_limits", "RESOURCE_LIMIT_MANIFEST_INVALID"),
        ):
            forged = self.manifest()
            if key == "trusted_wrapper":
                forged[key] = dict(forged[key], content_sha256="f" * 64)
            elif key == "probes":
                forged[key] = list(reversed(forged[key]))
            elif key == "apple_platform_tcb":
                forged[key] = dict(forged[key], schema="forged")
            else:
                forged[key] = dict(forged[key], stdout_bytes=0)
            with self.subTest(key=key), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.validate_manifest_object(forged)
            self.assertEqual(raised.exception.status, status)

    def test_production_storage_quota_boundary_is_fail_closed(self) -> None:
        self.assertFalse(full_gate._invocation_storage_quota_supported())

    def test_copied_platform_binary_is_typed_rejected_at_static_manifest_boundary(self) -> None:
        with mock.patch.object(
            full_gate, "apple_platform_tcb_binding", return_value={}
        ):
            manifest = self.manifest()
        manifest.pop("apple_platform_tcb")
        manifest["host_tool_identity_parser"] = (
            self.host_tool_identity_parser_fixture()
        )
        manifest["copied_application_runtime"] = (
            self.copied_application_runtime_fixture()
        )
        manifest["copied_application_runtime"]["portable_tools"][0][
            "platform_identifier"
        ] = 16
        manifest["copied_application_runtime"]["portable_tools"][0][
            "filesystem_flags"
        ] = ["restricted"]
        manifest["canonical_host_tools"] = {
            "schema": "samvil.canonical-host-tools.v1",
            "rows": [],
        }
        manifest["command"] = ["/bin/bash", "scripts/pre-commit-check.sh"]

        with mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=AssertionError("platform binary reached materialization"),
        ), mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("platform binary reached execution"),
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(manifest)
        self.assertEqual(raised.exception.status, "UNSUPPORTED_HERMETIC_RUNTIME")

    def test_canonical_host_tool_admission_starts_with_one_pinned_codesign_verifier(self) -> None:
        codesign = self.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = self.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        cases = {
            "empty": [],
            "verifier_missing": [env],
            "verifier_duplicate": [codesign, dict(codesign, inode=3)],
            "verifier_after_non_codesign": [env, codesign],
            "codesign_already_accepted": [
                dict(codesign, admission_state="ACCEPTED_ROW"),
                env,
            ],
            "non_codesign_claims_verifier_state": [
                codesign,
                dict(env, admission_state="PLATFORM_VERIFIER_PINNED"),
            ],
        }
        for name, rows in cases.items():
            manifest = self.approved_host_tool_manifest(rows)
            with self.subTest(name=name), mock.patch.object(
                full_gate,
                "materialize_closure_archive",
                side_effect=AssertionError("invalid host row reached materialization"),
            ), mock.patch.object(
                full_gate.subprocess,
                "run",
                side_effect=AssertionError("invalid host row reached execution"),
            ):
                try:
                    full_gate.validate_manifest_object(manifest)
                except full_gate.FullGateError as raised:
                    self.assertEqual(
                        raised.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                    )
                else:
                    self.fail("invalid canonical host-tool order was accepted")

    def test_canonical_behavior_probe_requires_exact_absolute_argv_and_channels(self) -> None:
        codesign = self.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = self.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        sandbox = self.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=3
        )
        full_gate.validate_manifest_object(
            self.approved_host_tool_manifest([codesign, env, sandbox])
        )
        forged = json.loads(json.dumps(env))
        forged["behavior_probe"]["argv"][0] = "env"
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(
                self.approved_host_tool_manifest([codesign, forged, sandbox])
            )
        self.assertEqual(
            raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
        )

    def test_host_tool_identity_parser_trust_root_is_exact_and_non_authoritative(self) -> None:
        codesign = self.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = self.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        sandbox = self.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=3
        )
        valid = self.host_tool_identity_parser_fixture()

        def clone() -> dict[str, object]:
            return json.loads(json.dumps(valid))

        cases: dict[str, tuple[dict[str, object], bool]] = {
            "valid_expanded_contract": (valid, True),
            "old_shallow_object": (
                {
                    "schema": "host-tool-identity-parser.v1",
                    "authority": "task-2-external-controller",
                    "staged_runner_authority": False,
                    "source_sha256": "a" * 64,
                    "result_sha256": "c" * 64,
                },
                False,
            ),
        }

        def forged(name: str, mutate: object) -> None:
            candidate = clone()
            mutate(candidate)
            cases[name] = (candidate, False)

        forged("wrong_authority", lambda value: value.__setitem__("authority", "staged-runner"))
        forged(
            "staged_runner_authority_true",
            lambda value: value.__setitem__("staged_runner_authority", True),
        )
        forged(
            "materialized_source_mismatch",
            lambda value: value["materialized"].__setitem__("content_sha256", "0" * 64),
        )
        forged(
            "materialized_mode_writable",
            lambda value: value["materialized"].__setitem__("mode", "100700"),
        )
        forged(
            "materialized_mode_not_executable",
            lambda value: value["materialized"].__setitem__("mode", "100400"),
        )
        forged(
            "interpreter_path_escape",
            lambda value: value["materialized"]["interpreter"].__setitem__(
                "relative_path", "../bin/python3.12"
            ),
        )
        forged(
            "interpreter_path_absolute",
            lambda value: value["materialized"]["interpreter"].__setitem__(
                "relative_path", "/bin/python3.12"
            ),
        )
        forged(
            "schema_missing",
            lambda value: value.__setitem__("supported_schemas", ["mach-o.v1"]),
        )
        forged(
            "schema_extra",
            lambda value: value.__setitem__(
                "supported_schemas",
                ["code-directory.v1", "future.v2", "mach-o.v1"],
            ),
        )
        forged(
            "limit_zero",
            lambda value: value["limits"].__setitem__("file_bytes", 0),
        )
        forged(
            "limit_excessive",
            lambda value: value["limits"].__setitem__("depth", 2**63),
        )
        forged(
            "limit_incoherent",
            lambda value: value["limits"].__setitem__("aggregate_bytes", 1),
        )
        forged(
            "inputs_duplicate_identity",
            lambda value: value["inputs"].__setitem__(
                1, dict(value["inputs"][1], device=1, inode=1)
            ),
        )
        forged(
            "inputs_unsorted",
            lambda value: value.__setitem__("inputs", list(reversed(value["inputs"]))),
        )
        forged(
            "source_hash_invalid",
            lambda value: value.__setitem__("source_sha256", "not-a-hash"),
        )
        forged(
            "bool_is_not_limit_int",
            lambda value: value["limits"].__setitem__("file_bytes", True),
        )
        forged(
            "comparison_result_mismatch",
            lambda value: value["staged_runner_comparison"].__setitem__(
                "result_sha256", "0" * 64
            ),
        )
        forged(
            "comparison_not_byte_identical",
            lambda value: value["staged_runner_comparison"].__setitem__(
                "byte_identical", False
            ),
        )
        forged(
            "comparison_claims_authority",
            lambda value: value["staged_runner_comparison"].__setitem__(
                "authority", True
            ),
        )

        for name, (parser, accepted) in cases.items():
            manifest = self.approved_host_tool_manifest([codesign, env, sandbox])
            manifest["host_tool_identity_parser"] = parser
            with self.subTest(name=name), mock.patch.object(
                full_gate,
                "materialize_closure_archive",
                side_effect=AssertionError("invalid parser reached materialization"),
            ), mock.patch.object(
                full_gate.subprocess,
                "run",
                side_effect=AssertionError("invalid parser reached execution"),
            ):
                if accepted:
                    full_gate.validate_manifest_object(manifest)
                    continue
                try:
                    full_gate.validate_manifest_object(manifest)
                except full_gate.FullGateError as raised:
                    self.assertEqual(
                        raised.status, "HOST_TOOL_IDENTITY_PARSER_INVALID"
                    )
                else:
                    self.fail("invalid parser trust root was accepted")

    def test_approved_parser_source_and_corpus_are_held_external_references(self) -> None:
        codesign = self.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = self.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        sandbox = self.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=3
        )
        try:
            validated = full_gate.validate_manifest_object(
                self.approved_host_tool_manifest([codesign, env, sandbox])
            )
        except full_gate.FullGateError as exc:
            self.fail(f"approved parser artifact references were rejected: {exc.status}")
        references = dict(full_gate._external_references(validated))
        parser = validated.raw["host_tool_identity_parser"]
        self.assertEqual(
            references["host_tool_identity_parser_source"],
            parser["source_artifact"],
        )
        for entry in parser["inputs"]:
            self.assertEqual(
                references[f"host_tool_identity_parser_input:{entry['role']}"],
                {"path": entry["path"], "sha256": entry["sha256"]},
            )

    def test_collected_mcp_tests_must_cover_the_complete_target_inventory(self) -> None:
        manifest = self.manifest()
        unlisted = self.inventory("mcp/tests/test_unlisted.py")
        manifest["inventory"] = sorted(
            [*manifest["inventory"], unlisted], key=lambda entry: entry["path"]
        )
        manifest["import_manifest"]["sha256"] = sha256(
            full_gate.canonical_json_bytes(
                {
                    "allowlist": manifest["import_manifest"]["allowlist"],
                    "collected_mcp_tests": manifest["collected_mcp_tests"],
                }
            )
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(manifest)
        self.assertEqual(raised.exception.status, "COLLECTED_TESTS_INCOMPLETE")

    def test_discriminated_target_identity_and_prior_receipt_binding_are_exact(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "validate_prior_receipt_object"),
            "full-gate prior-receipt validation is not implemented",
        )
        original = full_gate.validate_manifest_object(self.manifest("original"))
        precommit_manifest = self.manifest("candidate_precommit")
        precommit = full_gate.validate_manifest_object(precommit_manifest)
        post_manifest = self.manifest("candidate_postcommit")
        postcommit = full_gate.validate_manifest_object(post_manifest)
        self.assertEqual(
            (original.target_kind, precommit.target_kind, postcommit.target_kind),
            ("original", "candidate_precommit", "candidate_postcommit"),
        )

        forged_precommit = self.manifest("candidate_precommit")
        forged_precommit["target"] = dict(forged_precommit["target"], final_commit="6" * 40)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_manifest_object(forged_precommit)
        self.assertEqual(raised.exception.status, "TARGET_IDENTITY_INVALID")

        base_args = full_gate.FullGateArguments(
            manifest="/trusted/manifest.json",
            prior_receipt=None,
            nonce="a" * 64,
            timeout=10.0,
            receipt="/trusted/receipt.json",
            denial_log="/trusted/denial.log",
        )
        full_gate.validate_cli_target_binding(base_args, original)
        full_gate.validate_cli_target_binding(base_args, precommit)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_cli_target_binding(base_args, postcommit)
        self.assertEqual(raised.exception.status, "PRIOR_RECEIPT_REQUIRED")

        prior_args = dataclasses.replace(base_args, prior_receipt="/trusted/prior.json")
        for target in (original, precommit):
            with self.subTest(kind=target.target_kind), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate.validate_cli_target_binding(prior_args, target)
            self.assertEqual(raised.exception.status, "PRIOR_RECEIPT_FORBIDDEN")
        full_gate.validate_cli_target_binding(prior_args, postcommit)

        prior = self.prior_receipt()
        prior_bytes = full_gate.canonical_json_bytes(prior)
        post_manifest["target"] = dict(
            post_manifest["target"], prior_receipt_sha256=sha256(prior_bytes)
        )
        postcommit = full_gate.validate_manifest_object(post_manifest)
        self.assertEqual(
            full_gate.validate_prior_receipt_object(postcommit, prior, prior_bytes),
            sha256(prior_bytes),
        )

        for field, value, status in (
            ("status", "FAIL", "PRIOR_RECEIPT_NOT_PASS"),
            ("nonce", "b" * 64, "PRIOR_RECEIPT_MISMATCH"),
            ("authorization_sha256", "6" * 64, "PRIOR_RECEIPT_MISMATCH"),
            ("manifest_sha256", "8" * 64, "PRIOR_RECEIPT_MISMATCH"),
        ):
            forged_prior = dict(prior)
            forged_prior[field] = value
            forged_bytes = full_gate.canonical_json_bytes(forged_prior)
            forged_manifest = self.manifest("candidate_postcommit")
            forged_manifest["target"] = dict(
                forged_manifest["target"], prior_receipt_sha256=sha256(forged_bytes)
            )
            validated = full_gate.validate_manifest_object(forged_manifest)
            with self.subTest(field=field), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate.validate_prior_receipt_object(
                    validated, forged_prior, forged_bytes
                )
            self.assertEqual(raised.exception.status, status)


class FullGateGitObjectPackTest(unittest.TestCase):
    def git_object(self, kind: str, content: bytes) -> str:
        return hashlib.sha1(
            f"{kind} {len(content)}\0".encode("ascii") + content
        ).hexdigest()

    def build_tree(
        self, files: dict[str, tuple[str, bytes]]
    ) -> tuple[str, dict[str, tuple[str, bytes]]]:
        objects: dict[str, tuple[str, bytes]] = {}
        root: dict[str, object] = {}
        for path, (mode, content) in files.items():
            node = root
            parts = path.split("/")
            for part in parts[:-1]:
                node = node.setdefault(part, {})  # type: ignore[assignment]
            node[parts[-1]] = (mode, content)

        def emit(node: dict[str, object]) -> str:
            rows: list[tuple[bytes, bytes]] = []
            for name, value in node.items():
                if isinstance(value, dict):
                    oid = emit(value)
                    mode = "40000"
                else:
                    mode, content = value  # type: ignore[misc]
                    oid = self.git_object("blob", content)
                    objects[oid] = ("blob", content)
                rows.append(
                    (
                        name.encode("utf-8"),
                        f"{mode} {name}".encode("utf-8")
                        + b"\0"
                        + bytes.fromhex(oid),
                    )
                )
            tree = b"".join(row for _, row in sorted(rows, key=lambda item: item[0]))
            oid = self.git_object("tree", tree)
            objects[oid] = ("tree", tree)
            return oid

        return emit(root), objects

    def commit_object(self, tree: str, parent: str | None, message: str) -> tuple[str, bytes]:
        lines = [f"tree {tree}"]
        if parent is not None:
            lines.append(f"parent {parent}")
        lines.extend(
            (
                "author Release Control <release@example.invalid> 0 +0000",
                "committer Release Control <release@example.invalid> 0 +0000",
                "",
                message,
                "",
            )
        )
        content = "\n".join(lines).encode("utf-8")
        return self.git_object("commit", content), content

    def fixture(
        self, kind: str
    ) -> tuple[dict[str, object], bytes, dict[str, bytes]]:
        files = {
            "scripts/pre-commit-check.sh": ("100755", b"#!/bin/bash\nexit 0\n"),
            "scripts/phase6-real-runtime-dogfood.py": ("100644", b"print('phase6')\n"),
            "mcp/tests/test_phase6_real_runtime_dogfood.py": (
                "100644",
                b"def test_phase6(): pass\n",
            ),
            "mcp/tests/test_example.py": ("100644", b"def test_example(): pass\n"),
            "mcp/samvil_mcp/__init__.py": ("100644", b"# package\n"),
            "mcp/samvil_mcp/server.py": (
                "100644",
                b"class Manager:\n    _tools = {'probe': object()}\n"
                b"class MCP:\n    _tool_manager = Manager()\n"
                b"mcp = MCP()\n",
            ),
        }
        tree, tree_objects = self.build_tree(files)
        parent, parent_bytes = self.commit_object(tree, None, "parent")
        objects = dict(tree_objects)
        objects[parent] = ("commit", parent_bytes)
        final_commit: str | None = None
        if kind in {"original", "candidate_postcommit"}:
            final_commit, final_bytes = self.commit_object(
                tree, parent if kind == "candidate_postcommit" else None, kind
            )
            objects[final_commit] = ("commit", final_bytes)
            if kind == "original":
                objects.pop(parent)

        manifest = FullGateManifestProtocolTest().manifest(kind)
        manifest["inventory"] = [
            {
                "path": path,
                "mode": mode,
                "blob": self.git_object("blob", content),
                "sha256": sha256(content),
            }
            for path, (mode, content) in sorted(files.items())
        ]
        by_path = {entry["path"]: entry for entry in manifest["inventory"]}
        manifest["gate_inventory"] = [by_path["scripts/pre-commit-check.sh"]]
        manifest["phase6_inventory"] = [
            by_path["scripts/phase6-real-runtime-dogfood.py"],
            by_path["mcp/tests/test_phase6_real_runtime_dogfood.py"],
        ]
        manifest["collected_mcp_tests"] = [
            by_path["mcp/tests/test_example.py"],
            by_path["mcp/tests/test_phase6_real_runtime_dogfood.py"],
        ]
        manifest["import_manifest"]["sha256"] = sha256(
            full_gate.canonical_json_bytes(
                {
                    "allowlist": manifest["import_manifest"]["allowlist"],
                    "collected_mcp_tests": manifest["collected_mcp_tests"],
                }
            )
        )
        if kind == "original":
            manifest["target"] = {
                "kind": kind,
                "source_commit": final_commit,
                "tree": tree,
            }
        elif kind == "candidate_precommit":
            manifest["target"] = {
                "kind": kind,
                "tree": tree,
                "expected_parent": parent,
                "authorization_sha256": "5" * 64,
                "final_commit": None,
            }
        else:
            target = dict(manifest["target"])
            target.update(
                final_commit=final_commit,
                tree=tree,
                expected_parent=parent,
                precommit_tree=tree,
            )
            manifest["target"] = target
        pack = {
            "schema": "samvil.git-object-pack.v1",
            "objects": [
                {
                    "oid": oid,
                    "type": object_kind,
                    "size": len(content),
                    "sha256": sha256(content),
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
                for oid, (object_kind, content) in sorted(objects.items())
            ],
        }
        blob_bytes = {
            path: content for path, (_mode, content) in files.items()
        }
        return manifest, full_gate.canonical_json_bytes(pack), blob_bytes

    def test_original_precommit_and_postcommit_use_independent_git_object_identity(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "verify_git_object_pack"),
            "verified Git object closure is not implemented",
        )
        for kind in ("original", "candidate_precommit", "candidate_postcommit"):
            with self.subTest(kind=kind):
                manifest, pack, expected = self.fixture(kind)
                validated = full_gate.validate_manifest_object(manifest)
                verified = full_gate.verify_git_object_pack(validated, pack)
                self.assertEqual(dict(verified.files), expected)
                self.assertEqual(verified.tree, validated.candidate_tree)

    def test_object_hash_inventory_and_commit_parent_drift_fail_closed(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "verify_git_object_pack"),
            "verified Git object closure is not implemented",
        )
        manifest, pack, _ = self.fixture("candidate_postcommit")
        validated = full_gate.validate_manifest_object(manifest)
        decoded = json.loads(pack)

        forged_pack = json.loads(pack)
        forged_pack["objects"][0]["sha256"] = "f" * 64
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.verify_git_object_pack(
                validated, full_gate.canonical_json_bytes(forged_pack)
            )
        self.assertEqual(raised.exception.status, "GIT_OBJECT_HASH_MISMATCH")

        forged_manifest = json.loads(json.dumps(manifest))
        forged_path = forged_manifest["inventory"][0]["path"]
        forged_manifest["inventory"][0]["sha256"] = "f" * 64
        for role in ("gate_inventory", "phase6_inventory", "collected_mcp_tests"):
            for entry in forged_manifest[role]:
                if entry["path"] == forged_path:
                    entry["sha256"] = "f" * 64
        forged_manifest["import_manifest"]["sha256"] = sha256(
            full_gate.canonical_json_bytes(
                {
                    "allowlist": forged_manifest["import_manifest"]["allowlist"],
                    "collected_mcp_tests": forged_manifest["collected_mcp_tests"],
                }
            )
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.verify_git_object_pack(
                full_gate.validate_manifest_object(forged_manifest), pack
            )
        self.assertEqual(raised.exception.status, "TARGET_INVENTORY_MISMATCH")

        target = dict(manifest["target"])
        target["expected_parent"] = "e" * 40
        forged_manifest = dict(manifest)
        forged_manifest["target"] = target
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.verify_git_object_pack(
                full_gate.validate_manifest_object(forged_manifest), pack
            )
        self.assertEqual(raised.exception.status, "TARGET_COMMIT_IDENTITY_MISMATCH")

        self.assertEqual(decoded["schema"], "samvil.git-object-pack.v1")

    def test_parent_history_tree_does_not_pollute_target_materialization(self) -> None:
        manifest, pack, expected = self.fixture("candidate_precommit")
        decoded = json.loads(pack)
        old_parent = manifest["target"]["expected_parent"]
        decoded["objects"] = [
            entry for entry in decoded["objects"] if entry["oid"] != old_parent
        ]

        parent_files = {
            "scripts/pre-commit-check.sh": (
                "100755",
                b"#!/bin/bash\necho old-parent\nexit 0\n",
            ),
            "scripts/phase6-real-runtime-dogfood.py": (
                "100644",
                b"print('phase6')\n",
            ),
            "mcp/tests/test_phase6_real_runtime_dogfood.py": (
                "100644",
                b"def test_phase6(): pass\n",
            ),
            "mcp/tests/test_deleted_in_target.py": (
                "100644",
                b"def test_deleted(): pass\n",
            ),
        }
        parent_tree, parent_objects = self.build_tree(parent_files)
        parent_commit, parent_content = self.commit_object(
            parent_tree, None, "different parent tree"
        )
        parent_objects[parent_commit] = ("commit", parent_content)
        decoded["objects"].extend(
            {
                "oid": oid,
                "type": kind,
                "size": len(content),
                "sha256": sha256(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
            for oid, (kind, content) in sorted(parent_objects.items())
            if not any(entry["oid"] == oid for entry in decoded["objects"])
        )
        decoded["objects"].sort(key=lambda entry: entry["oid"])
        manifest["target"] = dict(
            manifest["target"], expected_parent=parent_commit
        )

        verified = full_gate.verify_git_object_pack(
            full_gate.validate_manifest_object(manifest),
            full_gate.canonical_json_bytes(decoded),
        )
        self.assertEqual(dict(verified.files), expected)
        self.assertNotIn("mcp/tests/test_deleted_in_target.py", verified.files)
        self.assertEqual(
            verified.files["scripts/pre-commit-check.sh"],
            b"#!/bin/bash\nexit 0\n",
        )


class FullGateArtifactAndControlIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-artifact-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.base / "home"),
            "TMPDIR": str(self.base),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
        Path(self.env["HOME"]).mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def git(self, repo: Path, *args: str) -> str:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(repo), *args],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()

    def test_external_artifacts_are_canonical_held_single_link_descriptors(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "open_external_artifact"),
            "held external artifact validation is not implemented",
        )
        artifact = self.base / "artifact.json"
        artifact.write_bytes(b"{}")
        held = full_gate.open_external_artifact(
            str(artifact), sha256(b"{}"), max_bytes=1024, status="ARTIFACT_INVALID"
        )
        self.addCleanup(held.close)
        self.assertEqual(held.data, b"{}")
        held.assert_stable()

        linked = self.base / "linked.json"
        os.link(artifact, linked)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.open_external_artifact(
                str(linked), sha256(b"{}"), max_bytes=1024, status="ARTIFACT_INVALID"
            )
        self.assertEqual(raised.exception.status, "ARTIFACT_INVALID")
        linked.unlink()

        replacement = self.base / "replacement.json"
        artifact.rename(replacement)
        artifact.write_bytes(b"{}")
        with self.assertRaises(full_gate.FullGateError) as raised:
            held.assert_stable()
        self.assertEqual(raised.exception.status, "EXTERNAL_ARTIFACT_REPLACED")

    def test_control_commit_tree_inventory_and_working_bytes_are_exact(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "validate_control_identity"),
            "control Git identity validation is not implemented",
        )
        control = self.base / "control"
        control.mkdir()
        self.git(control, "init", "-q")
        self.git(control, "config", "user.name", "Release Control Test")
        self.git(control, "config", "user.email", "release@example.invalid")
        for path in full_gate.CONTROL_PATHS:
            target = control / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TOOLS_ROOT / path.removeprefix("tools/release-control/"), target)
        self.git(control, "add", "--", *full_gate.CONTROL_PATHS)
        self.git(control, "commit", "-q", "-m", "control")
        commit = self.git(control, "rev-parse", "HEAD^{commit}")
        tree = self.git(control, "rev-parse", "HEAD^{tree}")
        inventory = []
        for path in full_gate.CONTROL_PATHS:
            mode, kind, blob = self.git(control, "ls-tree", "HEAD", "--", path).split()[:3]
            self.assertEqual(kind, "blob")
            inventory.append(
                {
                    "path": path,
                    "mode": mode,
                    "blob": blob,
                    "sha256": sha256((control / path).read_bytes()),
                }
            )
        manifest = FullGateManifestProtocolTest().manifest()
        manifest["control"] = {"commit": commit, "tree": tree, "files": inventory}
        validated = full_gate.validate_manifest_object(manifest)
        digest = full_gate.validate_control_identity(control, validated, self.env)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

        runner = control / "tools/release-control/run-full-gate-isolated.py"
        runner.write_bytes(runner.read_bytes() + b"\n# drift\n")
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_control_identity(control, validated, self.env)
        self.assertEqual(raised.exception.status, "CONTROL_FILE_DRIFT")


class FullGateMaterializationAndRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = require_invocation_tmpdir()
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-materialize-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_runtime_python_facade_and_gate_allowlist_close_bare_python_exec(self) -> None:
        invocation = self.base / "invocation"
        runtime = invocation / "runtime"
        tools = invocation / "tools"
        snapshot = invocation / "snapshot"
        wrapper = invocation / "wrapper/trusted-wrapper.py"
        for path in (runtime / "bin", tools / "bin", snapshot, wrapper.parent):
            path.mkdir(parents=True, exist_ok=True)
        (runtime / "bin/python3.12").write_bytes(
            b"#!/bin/sh\nexec /usr/bin/python3 \"$@\"\n"
        )
        (runtime / "bin/python3.12").chmod(0o755)
        facade = full_gate.materialize_runtime_python_facade(
            invocation, runtime, tools
        )
        self.assertEqual(facade, tools / "bin/python3")
        self.assertEqual(stat.S_IMODE(facade.stat().st_mode), 0o755)
        dirname = full_gate.materialize_runtime_dirname_facade(
            invocation, runtime, tools
        )
        self.assertEqual(dirname, tools / "bin/dirname")
        self.assertEqual(stat.S_IMODE(dirname.stat().st_mode), 0o755)
        self.assertIn(b"python", dirname.read_bytes())
        result = subprocess.run(
            [str(dirname), "scripts/pre-commit-check.sh"],
            cwd=invocation,
            env={"PATH": str(tools / "bin")},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(result.stdout, b"scripts\n")
        allowlist = full_gate.build_gate_executable_allowlist(
            snapshot=snapshot,
            runtime=runtime,
            tools=tools,
            wrapper=wrapper,
        )
        self.assertIn("/bin/sh", allowlist)
        self.assertIn(str(facade), allowlist)
        self.assertIn(str(dirname), allowlist)

    def test_gate_shell_scripts_resolve_dirname_from_trusted_facade(self) -> None:
        repository = TOOLS_ROOT.parents[1]
        for relative in (
            "scripts/pre-commit-check.sh",
            "hooks/validate-version-sync.sh",
            "scripts/check-glossary.sh",
            "scripts/check-broken-references.sh",
        ):
            with self.subTest(path=relative):
                self.assertIn(b"dirname", (repository / relative).read_bytes())

    def tar_bytes(
        self,
        files: dict[str, tuple[int, bytes]],
        *,
        symlink: tuple[str, str] | None = None,
    ) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for path, (mode, content) in sorted(files.items()):
                info = tarfile.TarInfo(path)
                info.mode = mode
                info.size = len(content)
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
            if symlink is not None:
                info = tarfile.TarInfo(symlink[0])
                info.type = tarfile.SYMTYPE
                info.linkname = symlink[1]
                info.mtime = 0
                archive.addfile(info)
        return buffer.getvalue()

    def closure_manifest(
        self, role: str, files: dict[str, tuple[int, bytes]]
    ) -> bytes:
        return full_gate.canonical_json_bytes(
            {
                "schema": "samvil.full-gate-closure-manifest.v1",
                "role": role,
                "files": [
                    {
                        "path": path,
                        "mode": f"{mode:06o}",
                        "size": len(content),
                        "sha256": sha256(content),
                    }
                    for path, (mode, content) in sorted(files.items())
                ],
            }
        )

    def test_snapshot_materializes_verified_objects_without_real_repo_recursion(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "materialize_verified_snapshot"),
            "verified snapshot materialization is not implemented",
        )
        manifest, pack_bytes, expected = FullGateGitObjectPackTest().fixture(
            "candidate_precommit"
        )
        verified = full_gate.verify_git_object_pack(
            full_gate.validate_manifest_object(manifest), pack_bytes
        )
        snapshot = self.base / "snapshot"
        real_repo = self.base / "real-repo"
        (real_repo / "$CODEX_HOME").mkdir(parents=True)
        (real_repo / "$CODEX_HOME" / "user-owned").write_text(
            "never-read", encoding="utf-8"
        )
        with mock.patch("os.walk", side_effect=AssertionError("recursive read forbidden")):
            digest = full_gate.materialize_verified_snapshot(verified, snapshot)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            {
                path: (snapshot / path).read_bytes()
                for path in sorted(expected)
            },
            expected,
        )
        self.assertFalse((snapshot / "$CODEX_HOME").exists())

    def test_shell_exit_zero_runtime_and_tool_stubs_are_rejected(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "materialize_closure_archive"),
            "hermetic closure materialization is not implemented",
        )
        runtime_files = {
            "bin/python3.12": (0o100755, b"#!/bin/sh\nexit 0\n"),
            "lib/python3.12/os.py": (0o100644, b"# pinned\n"),
        }
        tools_files = {
            f"bin/{name}": (0o100755, b"#!/bin/sh\nexit 0\n")
            for name in full_gate.REQUIRED_TOOL_NAMES
        }
        runtime = self.base / "runtime"
        tools = self.base / "tools"
        for role, files, destination in (
            ("python", runtime_files, runtime),
            ("tools", tools_files, tools),
        ):
            with self.subTest(role=role), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.materialize_closure_archive(
                    self.tar_bytes(files),
                    self.closure_manifest(role, files),
                    destination,
                    expected_role=role,
                )
            self.assertEqual(raised.exception.status, "UNSUPPORTED_HERMETIC_RUNTIME")

        snapshot = self.base / "snapshot"
        snapshot.mkdir()
        facade = {
            "schema": "samvil.full-gate-facade.v1",
            "entries": [
                {
                    "path": f"mcp/.venv/bin/{name}",
                    "mode": "100755",
                    "content_base64": base64.b64encode(
                        full_gate.FACADE_PYTHON_WRAPPER
                    ).decode("ascii"),
                    "sha256": sha256(
                        full_gate.FACADE_PYTHON_WRAPPER
                    ),
                }
                for name in ("python", "python3", "python3.12")
            ]
            + [
                {
                    "path": "mcp/.venv/pyvenv.cfg",
                    "mode": "100644",
                    "content_base64": base64.b64encode(
                        b"include-system-site-packages = false\nversion = 3.12\n"
                    ).decode("ascii"),
                    "sha256": sha256(
                        b"include-system-site-packages = false\nversion = 3.12\n"
                    ),
                }
            ],
        }
        facade_digest = full_gate.materialize_facade(
            full_gate.canonical_json_bytes(facade), snapshot, self.base
        )
        self.assertRegex(facade_digest, r"^[0-9a-f]{64}$")
        self.assertTrue((snapshot / "mcp/.venv/bin/python").is_file())

        malicious = self.tar_bytes(
            {"bin/python3.12": (0o100755, b"python")},
            symlink=("lib/escape", "/usr/lib"),
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.materialize_closure_archive(
                malicious,
                self.closure_manifest(
                    "python", {"bin/python3.12": (0o100755, b"python")}
                ),
                self.base / "malicious",
                expected_role="python",
            )
        self.assertEqual(raised.exception.status, "CLOSURE_ARCHIVE_INVALID")

        dependency_files = {
            "lib/python3.12/site-packages/editable.pth": (0o100644, b"/outside\n")
        }
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.materialize_closure_archive(
                self.tar_bytes(dependency_files),
                self.closure_manifest("dependencies", dependency_files),
                self.base / "dependencies",
                expected_role="dependencies",
            )
        self.assertEqual(raised.exception.status, "DEPENDENCY_CLOSURE_INVALID")

    def test_real_copied_macho_python_identity_and_import_closure_are_exact(self) -> None:
        execution_context = require_copied_runtime_execution()
        runtime_source = execution_context.pinned_runtime_source
        if platform.system() != "Darwin":
            self.skipTest("DARWIN_MACHO_RUNTIME_REQUIRED: real Mach-O test is Darwin-only")
        runtime = self.base / "real-runtime"
        copy_pinned_runtime(runtime, runtime_source=runtime_source)
        expected = full_gate.capture_hermetic_runtime_identity(runtime)
        self.assertEqual(expected["major_minor"], "3.12")
        self.assertEqual(expected["version"].split(".")[:2], ["3", "12"])
        self.assertIn("arm64", expected["slices"])
        self.assertEqual(expected["architecture"], "arm64")
        self.assertTrue(expected["executable_sha256"])
        observed = full_gate.validate_hermetic_runtime(runtime, expected)
        self.assertEqual(observed, expected)
        self.assertTrue(
            all(
                not Path(entry).is_absolute() and ".." not in Path(entry).parts
                for entry in observed["runtime_probe"]["sys_path"]
            )
        )

        for field, value in (
            ("version", "3.12.0"),
            ("architecture", "x86_64"),
            ("executable_sha256", "f" * 64),
        ):
            forged = dict(expected, **{field: value})
            with self.subTest(field=field), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.validate_hermetic_runtime(runtime, forged)
            self.assertEqual(raised.exception.status, "UNSUPPORTED_HERMETIC_RUNTIME")

    def test_non_macho_python_is_typed_unsupported_before_execution(self) -> None:
        runtime = self.base / "stub-runtime"
        (runtime / "bin").mkdir(parents=True)
        executable = runtime / "bin/python3.12"
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.capture_hermetic_runtime_identity(runtime)
        self.assertEqual(raised.exception.status, "UNSUPPORTED_HERMETIC_RUNTIME")

    def test_portable_tool_manifest_is_closed_and_platform_shims_are_unreachable(self) -> None:
        role_paths = {
            "git": (
                "/Library/Developer/CommandLineTools/usr/bin/git",
                "tools/usr/bin/git",
            ),
            "git-shell": (
                "/Library/Developer/CommandLineTools/usr/bin/git-shell",
                "tools/usr/bin/git-shell",
            ),
            "lipo": (
                "/Library/Developer/CommandLineTools/usr/bin/lipo",
                "tools/usr/bin/lipo",
            ),
            "otool": (
                "/Library/Developer/CommandLineTools/usr/bin/otool",
                "tools/usr/bin/otool",
            ),
            "scalar": (
                "/Library/Developer/CommandLineTools/usr/bin/scalar",
                "tools/usr/bin/scalar",
            ),
        }

        def row(role: str, index: int) -> dict[str, object]:
            source_path, destination_path = role_paths[role]
            git_executables = [
                "tools/usr/bin/git",
                "tools/usr/libexec/git-core/git",
                "tools/usr/libexec/git-core/git-commit",
            ]
            return {
                "role": role,
                "source_path": source_path,
                "destination_path": destination_path,
                "platform_identifier": 0,
                "filesystem_flags": [],
                "mode": "100755",
                "nlink": 1,
                "size": 4096 + index,
                "sha256": f"{index:x}" * 64,
                "slices": ["arm64e", "x86_64"],
                "load_closure": ["/usr/lib/libSystem.B.dylib"],
                "exec_closure": {
                    "executables": (
                        git_executables if role == "git" else [destination_path]
                    ),
                    "git_core_root": (
                        "tools/usr/libexec/git-core" if role == "git" else None
                    ),
                    "topology_sha256": "6" * 64 if role == "git" else None,
                    "internal_symlink_count": 2 if role == "git" else 0,
                },
                "behavior_probe": {
                    "argv": [destination_path, "--version"],
                    "stdout_sha256": f"{index + 5:x}" * 64,
                },
                "admission_state": "STATIC_ADMITTED",
            }

        rows = [row(role, index) for index, role in enumerate(sorted(role_paths), 1)]
        allowlist = sorted(
            {
                *(item["destination_path"] for item in rows),
                "tools/usr/libexec/git-core/git",
                "tools/usr/libexec/git-core/git-commit",
                "tools/facade/bin/mktemp",
                "tools/facade/bin/python",
                "tools/facade/bin/python3",
                "tools/facade/bin/python3.12",
                "node/bin/node",
                "node/bin/npm",
                "node/bin/pnpm",
            }
        )
        valid = {
            "schema": "samvil.copied-application-runtime.v1",
            "portable_tools": rows,
            "exec_allowlist": allowlist,
            "path_order": [
                "tools/facade/bin",
                "tools/usr/bin",
                "node/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ],
        }

        def clone() -> dict[str, object]:
            return json.loads(json.dumps(valid))

        cases: dict[str, tuple[dict[str, object], bool, str | None]] = {
            "valid_expanded_closure": (valid, True, None),
            "old_shallow_schema": (
                {
                    "schema": "samvil.copied-application-runtime.v1",
                    "portable_tools": [],
                },
                False,
                "COPIED_APPLICATION_RUNTIME_INVALID",
            ),
        }

        def forged(name: str, status: str, mutate: object) -> None:
            candidate = clone()
            mutate(candidate)
            cases[name] = (candidate, False, status)

        forged(
            "missing_role",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"].pop(),
        )
        forged(
            "extra_role",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"].append(
                dict(value["portable_tools"][0], role="nm")
            ),
        )
        forged(
            "duplicate_role",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"].append(value["portable_tools"][0]),
        )
        forged(
            "platform_identifier_16",
            "UNSUPPORTED_HERMETIC_RUNTIME",
            lambda value: value["portable_tools"][0].__setitem__(
                "platform_identifier", 16
            ),
        )
        forged(
            "restricted_source",
            "UNSUPPORTED_HERMETIC_RUNTIME",
            lambda value: value["portable_tools"][0].__setitem__(
                "filesystem_flags", ["restricted"]
            ),
        )
        forged(
            "usr_bin_git_shim",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "source_path", "/usr/bin/git"
            ),
        )
        forged(
            "usr_bin_lipo_shim",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: next(
                item for item in value["portable_tools"] if item["role"] == "lipo"
            ).__setitem__("source_path", "/usr/bin/lipo"),
        )
        forged(
            "destination_escape",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "destination_path", "../git"
            ),
        )
        forged(
            "mode_not_executable",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__("mode", "100644"),
        )
        forged(
            "hash_invalid",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "sha256", "not-a-hash"
            ),
        )
        forged(
            "bool_is_not_platform_int",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "platform_identifier", False
            ),
        )
        forged(
            "external_load_closure",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "load_closure", ["/tmp/evil.dylib"]
            ),
        )
        forged(
            "relative_load_escape",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0].__setitem__(
                "load_closure", ["../evil.dylib"]
            ),
        )
        forged(
            "xcrun_exec_fallback",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: next(
                item for item in value["portable_tools"] if item["role"] == "lipo"
            )["exec_closure"]["executables"].append("xcrun"),
        )
        forged(
            "usr_bin_otool_exec_fallback",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: next(
                item for item in value["portable_tools"] if item["role"] == "otool"
            )["exec_closure"]["executables"].append("/usr/bin/otool"),
        )
        forged(
            "missing_git_topology",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value["portable_tools"][0]["exec_closure"].__setitem__(
                "topology_sha256", None
            ),
        )
        forged(
            "bad_path_order",
            "COPIED_APPLICATION_RUNTIME_INVALID",
            lambda value: value.__setitem__(
                "path_order", [value["path_order"][1], value["path_order"][0], *value["path_order"][2:]]
            ),
        )
        for name, forbidden in (
            ("allowlist_usr_bin_git", "/usr/bin/git"),
            ("allowlist_usr_bin_lipo", "/usr/bin/lipo"),
            ("allowlist_usr_bin_otool", "/usr/bin/otool"),
            ("allowlist_usr_bin_mktemp", "/usr/bin/mktemp"),
            ("allowlist_xcrun", "xcrun"),
            ("allowlist_directory_wildcard", "tools/usr/bin/*"),
        ):
            forged(
                name,
                "COPIED_APPLICATION_RUNTIME_INVALID",
                lambda value, forbidden=forbidden: value["exec_allowlist"].append(
                    forbidden
                ),
            )

        protocol = FullGateManifestProtocolTest()
        codesign = protocol.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = protocol.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        sandbox = protocol.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=3
        )
        for name, (runtime, accepted, expected_status) in cases.items():
            manifest = protocol.approved_host_tool_manifest([codesign, env, sandbox])
            manifest["copied_application_runtime"] = runtime
            with self.subTest(name=name), mock.patch.object(
                full_gate,
                "materialize_closure_archive",
                side_effect=AssertionError("portable closure reached materialization"),
            ), mock.patch.object(
                full_gate.subprocess,
                "run",
                side_effect=AssertionError("portable closure reached execution"),
            ):
                try:
                    full_gate.validate_manifest_object(manifest)
                except full_gate.FullGateError as raised:
                    if accepted:
                        raise
                    self.assertEqual(raised.status, expected_status)
                else:
                    if not accepted:
                        self.fail("invalid portable tool closure was accepted")


@unittest.skipUnless(
    Path("/usr/bin/sandbox-exec").is_file()
    and Path("/usr/bin/codesign").is_file(),
    "macOS Apple platform tools required",
)
class FullGateApplePlatformTCBTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-apple-platform-tcb-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_real_platform_binding_round_trips_through_bounded_canonical_json(
        self,
    ) -> None:
        binding = full_gate.apple_platform_tcb_binding()
        raw = full_gate.canonical_json_bytes(binding)

        decoded = full_gate.decode_canonical_json_bytes(
            raw,
            status="MANIFEST_JSON_INVALID",
            max_bytes=1024 * 1024,
        )

        self.assertEqual(decoded, binding)
        for role in ("codesign", "sandbox_exec"):
            identity = binding[role]["path_identity"]
            self.assertIsInstance(identity["device"], str)
            self.assertIsInstance(identity["inode"], str)
            self.assertIsInstance(identity["mtime_ns"], str)
            self.assertIsInstance(identity["ctime_ns"], str)

    def test_real_manifest_pinned_platform_identity_and_behavior_are_exact(self) -> None:
        binding = full_gate.apple_platform_tcb_binding()
        evidence = full_gate.validate_apple_platform_tcb(binding, self.base)
        sandbox = binding["sandbox_exec"]
        verifier = binding["codesign"]
        self.assertEqual(sandbox["path"], "/usr/bin/sandbox-exec")
        self.assertEqual(sandbox["classification"], "apple_platform_tool")
        self.assertEqual(verifier["path"], "/usr/bin/codesign")
        self.assertEqual(
            verifier["classification"], "apple_platform_identity_verifier"
        )
        self.assertEqual(sandbox["uid"], 0)
        self.assertEqual(verifier["uid"], 0)
        self.assertEqual(sandbox["mode"], "100755")
        self.assertEqual(verifier["mode"], "100755")
        self.assertEqual(sandbox["nlink"], 1)
        self.assertEqual(verifier["nlink"], 1)
        self.assertEqual(evidence["schema"], "samvil.apple-platform-evidence.v1")
        self.assertEqual(evidence["behavior"]["returncode"], 0)
        self.assertRegex(evidence["result_sha256"], r"^[0-9a-f]{64}$")

    def test_codesign_channels_are_strict_and_malformed_security_output_fails(self) -> None:
        binding = full_gate.apple_platform_tcb_binding()
        verify = binding["codesign_result"]["verify"]
        display = binding["codesign_result"]["display"]
        self.assertEqual(
            verify["argv"],
            [
                "/usr/bin/codesign",
                "--verify",
                "--strict",
                "--verbose=2",
                '-R=anchor apple and identifier "com.apple.sandbox-exec"',
                "/usr/bin/sandbox-exec",
            ],
        )
        self.assertEqual(
            display["argv"],
            [
                "/usr/bin/codesign",
                "-d",
                "--verbose=4",
                "-r-",
                "/usr/bin/sandbox-exec",
            ],
        )
        for field, forged_value in (
            ("verify_stderr", verify["stderr"] + verify["stderr"].splitlines(True)[0]),
            ("display_stdout", display["stdout"] + "unexpected\n"),
            ("display_stderr", display["stderr"] + "UnknownSecurityField=value\n"),
        ):
            forged_verify_stdout = verify["stdout"]
            forged_verify_stderr = verify["stderr"]
            forged_display_stdout = display["stdout"]
            forged_display_stderr = display["stderr"]
            if field == "verify_stderr":
                forged_verify_stderr = forged_value
            elif field == "display_stdout":
                forged_display_stdout = forged_value
            else:
                forged_display_stderr = forged_value
            with self.subTest(field=field), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate.parse_apple_codesign_results(
                    verify_stdout=forged_verify_stdout,
                    verify_stderr=forged_verify_stderr,
                    display_stdout=forged_display_stdout,
                    display_stderr=forged_display_stderr,
                    sandbox_slices=tuple(binding["sandbox_exec"]["slices"]),
                )
            self.assertEqual(raised.exception.status, "UNSUPPORTED_HERMETIC_RUNTIME")


class FullGateExternalParserAuthorityTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-external-parser-authority-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.scratch = self.base / "scratch"
        self.scratch.mkdir()
        self.interpreter = Path(sys.executable).resolve(strict=True)
        self.runtime = self.interpreter.parent
        self.interpreter_relative = self.interpreter.name

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write_and_hold(self, name: str, data: bytes) -> full_gate.HeldArtifact:
        path = self.base / name
        path.write_bytes(data)
        return full_gate.open_external_artifact(
            str(path),
            sha256(data),
            max_bytes=1024 * 1024,
            status="HOST_TOOL_IDENTITY_PARSER_INVALID",
        )

    def _authority_fixture(
        self,
        parser_source: bytes | None = None,
    ) -> tuple[
        dict[str, object],
        full_gate.HeldArtifact,
        dict[str, full_gate.HeldArtifact],
        bytes,
        bytes,
    ]:
        if parser_source is None:
            parser_source = b'''from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
items = []
for entry in request["inputs"]:
    data = Path(entry["path"]).read_bytes()
    items.append({
        "role": entry["role"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    })
payload = {"schema": "host-tool-identity-corpus-result.v1", "items": items}
sys.stdout.buffer.write(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
)
'''
        parser_artifact = self._write_and_hold("external-parser.py", parser_source)
        corpus_data = {
            "codesign": b"valid-code-directory-fixture",
            "sandbox-exec": b"valid-mach-o-fixture",
        }
        corpus = {
            role: self._write_and_hold(f"{role}.fixture", data)
            for role, data in corpus_data.items()
        }
        staged_result = full_gate.canonical_json_bytes(
            {
                "schema": "host-tool-identity-corpus-result.v1",
                "items": [
                    {
                        "role": role,
                        "sha256": sha256(data),
                        "size": len(data),
                    }
                    for role, data in sorted(corpus_data.items())
                ],
            }
        )
        parser_manifest = FullGateManifestProtocolTest().host_tool_identity_parser_fixture()
        parser_manifest["source_sha256"] = sha256(parser_source)
        parser_manifest["source_artifact"] = {
            "path": str(parser_artifact.path),
            "sha256": sha256(parser_source),
        }
        parser_manifest["materialized"]["content_sha256"] = sha256(parser_source)
        parser_manifest["materialized"]["interpreter"] = {
            "classification": "copied_application_runtime",
            "relative_path": self.interpreter_relative,
            "sha256": sha256(self.interpreter.read_bytes()),
        }
        parser_manifest["inputs"] = [
            {
                "role": role,
                "path": str(held.path),
                "device": held.identity.device,
                "inode": held.identity.inode,
                "size": held.identity.size,
                "sha256": sha256(held.data),
            }
            for role, held in sorted(corpus.items())
        ]
        parser_manifest["result_sha256"] = sha256(staged_result)
        parser_manifest["staged_runner_comparison"]["result_sha256"] = sha256(
            staged_result
        )
        return (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            parser_source,
        )

    def _close_fixture(
        self,
        parser_artifact: full_gate.HeldArtifact,
        corpus: Mapping[str, full_gate.HeldArtifact],
    ) -> None:
        for held in reversed(tuple(corpus.values())):
            held.close()
        parser_artifact.close()

    def test_external_parser_kills_descendants_that_hold_capture_pipes(self) -> None:
        parser_source = b'''from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import time

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
child = os.fork()
if child == 0:
    time.sleep(1)
    os._exit(0)
items = []
for entry in request["inputs"]:
    data = Path(entry["path"]).read_bytes()
    items.append({
        "role": entry["role"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    })
payload = {"schema": "host-tool-identity-corpus-result.v1", "items": items}
sys.stdout.buffer.write(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
)
'''
        (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            _parser_source,
        ) = self._authority_fixture(parser_source)
        started = time.monotonic()
        try:
            with mock.patch.object(
                full_gate,
                "HOST_TOOL_IDENTITY_PARSER_TIMEOUT_SECONDS",
                0.2,
                create=True,
            ), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.verify_external_host_tool_identity_parser(
                    parser_manifest,
                    parser_artifact,
                    corpus,
                    runtime_root=self.runtime,
                    scratch_root=self.scratch,
                    staged_result=staged_result,
                )
        finally:
            self._close_fixture(parser_artifact, corpus)
        self.assertEqual(
            raised.exception.status, "HOST_TOOL_IDENTITY_PARSER_EXECUTION_FAILED"
        )
        self.assertLess(time.monotonic() - started, 0.8)

    def test_external_parser_uses_held_bytes_and_matches_staged_corpus_result(self) -> None:
        (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            parser_source,
        ) = self._authority_fixture()

        verifier = getattr(
            full_gate, "verify_external_host_tool_identity_parser", None
        )
        self.assertTrue(
            callable(verifier),
            "external parser bytes are not held, materialized, and executed",
        )
        try:
            evidence = verifier(
                parser_manifest,
                parser_artifact,
                corpus,
                runtime_root=self.runtime,
                scratch_root=self.scratch,
                staged_result=staged_result,
            )
        finally:
            self._close_fixture(parser_artifact, corpus)

        materialized = self.scratch / "external-parser/host-tool-identity-parser.py"
        self.assertEqual(materialized.read_bytes(), parser_source)
        self.assertEqual(stat.S_IMODE(materialized.stat().st_mode), 0o500)
        self.assertEqual(
            evidence["schema"], "samvil.host-tool-identity-parser-evidence.v1"
        )
        self.assertEqual(evidence["source_sha256"], sha256(parser_source))
        self.assertEqual(evidence["result_sha256"], sha256(staged_result))
        self.assertTrue(evidence["byte_identical"])

    def test_staged_runner_builds_canonical_result_from_the_same_held_corpus(
        self,
    ) -> None:
        (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            _parser_source,
        ) = self._authority_fixture()
        builder = getattr(
            full_gate, "build_staged_host_tool_identity_corpus_result", None
        )
        self.assertTrue(
            callable(builder),
            "staged runner does not process the held external corpus",
        )
        try:
            observed = builder(parser_manifest, corpus)
        finally:
            self._close_fixture(parser_artifact, corpus)
        self.assertEqual(observed, staged_result)

    def test_approved_parser_preparation_derives_exact_held_artifact_roles(self) -> None:
        (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            _parser_source,
        ) = self._authority_fixture()
        artifacts = {
            "host_tool_identity_parser_source": parser_artifact,
            **{
                f"host_tool_identity_parser_input:{role}": held
                for role, held in corpus.items()
            },
        }
        prepare = getattr(
            full_gate, "prepare_approved_host_tool_parser", None
        )
        self.assertTrue(
            callable(prepare),
            "approved execution has no external parser preparation path",
        )
        try:
            evidence = prepare(
                parser_manifest,
                artifacts,
                runtime_root=self.runtime,
                scratch_root=self.scratch,
            )
        finally:
            self._close_fixture(parser_artifact, corpus)
        self.assertEqual(evidence["result_sha256"], sha256(staged_result))
        self.assertTrue(evidence["byte_identical"])

    def test_external_parser_rejects_claimed_byte_identity_when_staged_bytes_differ(
        self,
    ) -> None:
        (
            parser_manifest,
            parser_artifact,
            corpus,
            staged_result,
            _parser_source,
        ) = self._authority_fixture()
        staged_payload = json.loads(staged_result)
        staged_payload["staged_runner_authority"] = False
        forged_staged_result = full_gate.canonical_json_bytes(staged_payload)
        try:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.verify_external_host_tool_identity_parser(
                    parser_manifest,
                    parser_artifact,
                    corpus,
                    runtime_root=self.runtime,
                    scratch_root=self.scratch,
                    staged_result=forged_staged_result,
                )
        finally:
            self._close_fixture(parser_artifact, corpus)
        self.assertEqual(
            raised.exception.status,
            "HOST_TOOL_IDENTITY_PARSER_COMPARISON_FAILED",
        )

    def test_external_parser_rejects_source_path_replacement_during_execution(
        self,
    ) -> None:
        source_path = self.base / "replace-parser.py"
        parser_source = f'''from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
items = []
for entry in request["inputs"]:
    data = Path(entry["path"]).read_bytes()
    items.append({{
        "role": entry["role"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }})
replacement = Path({str(source_path)!r} + ".replacement")
replacement.write_bytes(b"replaced")
os.replace(replacement, {str(source_path)!r})
payload = {{"schema": "host-tool-identity-corpus-result.v1", "items": items}}
sys.stdout.buffer.write(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
)
'''.encode("utf-8")
        parser_artifact = self._write_and_hold(source_path.name, parser_source)
        corpus_data = {
            "codesign": b"valid-code-directory-fixture",
            "sandbox-exec": b"valid-mach-o-fixture",
        }
        corpus = {
            role: self._write_and_hold(f"replace-{role}.fixture", data)
            for role, data in corpus_data.items()
        }
        staged_result = full_gate.canonical_json_bytes(
            {
                "schema": "host-tool-identity-corpus-result.v1",
                "items": [
                    {
                        "role": role,
                        "sha256": sha256(data),
                        "size": len(data),
                    }
                    for role, data in sorted(corpus_data.items())
                ],
            }
        )
        parser_manifest = FullGateManifestProtocolTest().host_tool_identity_parser_fixture()
        parser_manifest["source_sha256"] = sha256(parser_source)
        parser_manifest["source_artifact"] = {
            "path": str(parser_artifact.path),
            "sha256": sha256(parser_source),
        }
        parser_manifest["materialized"]["content_sha256"] = sha256(parser_source)
        parser_manifest["materialized"]["interpreter"] = {
            "classification": "copied_application_runtime",
            "relative_path": self.interpreter_relative,
            "sha256": sha256(self.interpreter.read_bytes()),
        }
        parser_manifest["inputs"] = [
            {
                "role": role,
                "path": str(held.path),
                "device": held.identity.device,
                "inode": held.identity.inode,
                "size": held.identity.size,
                "sha256": sha256(held.data),
            }
            for role, held in sorted(corpus.items())
        ]
        parser_manifest["result_sha256"] = sha256(staged_result)
        parser_manifest["staged_runner_comparison"]["result_sha256"] = sha256(
            staged_result
        )
        try:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.verify_external_host_tool_identity_parser(
                    parser_manifest,
                    parser_artifact,
                    corpus,
                    runtime_root=self.runtime,
                    scratch_root=self.scratch,
                    staged_result=staged_result,
                )
        finally:
            self._close_fixture(parser_artifact, corpus)
        self.assertEqual(raised.exception.status, "EXTERNAL_ARTIFACT_REPLACED")


class FullGateCanonicalCodesignParserTest(unittest.TestCase):
    @unittest.skipUnless(
        Path("/usr/bin/codesign").is_file()
        and Path("/usr/bin/sandbox-exec").is_file(),
        "macOS canonical platform tools required",
    )
    def test_real_platform_slice_order_is_preserved_without_sorting(self) -> None:
        binding = full_gate.apple_platform_tcb_binding()
        raw = binding["codesign_result"]

        parsed = full_gate.parse_canonical_codesign_result(
            target_path="/usr/bin/sandbox-exec",
            signing_identifier="com.apple.sandbox-exec",
            expected_slices=list(binding["sandbox_exec"]["slices"]),
            verify_argv=raw["verify"]["argv"],
            verify_returncode=raw["verify"]["returncode"],
            verify_stdout=raw["verify"]["stdout"].encode("utf-8"),
            verify_stderr=raw["verify"]["stderr"].encode("utf-8"),
            display_argv=raw["display"]["argv"],
            display_returncode=raw["display"]["returncode"],
            display_stdout=raw["display"]["stdout"].encode("utf-8"),
            display_stderr=raw["display"]["stderr"].encode("utf-8"),
        )

        self.assertEqual(parsed["slices"], ["x86_64", "arm64e"])

    def test_non_self_canonical_codesign_result_has_exact_generic_grammar(self) -> None:
        target = "/usr/bin/env"
        identifier = "com.apple.env"
        slices = ["arm64e", "x86_64"]
        cdhash = "1" * 40
        cdhash_full = cdhash + "2" * 24
        verify_argv = [
            "/usr/bin/codesign",
            "--verify",
            "--strict",
            "--verbose=2",
            '-R=anchor apple and identifier "com.apple.env"',
            target,
        ]
        display_argv = [
            "/usr/bin/codesign",
            "-d",
            "--verbose=4",
            "-r-",
            target,
        ]
        verify_lines = [
            f"{target}: valid on disk",
            f"{target}: satisfies its Designated Requirement",
            f"{target}: explicit requirement satisfied",
        ]
        display_requirement = (
            'designated => identifier "com.apple.env" and anchor apple\n'
        )
        metadata_lines = [
            f"Executable={target}",
            f"Identifier={identifier}",
            "Format=Mach-O universal (arm64e x86_64)",
            "CodeDirectory v=20400 size=463 flags=0x0(none) hashes=9+2 location=embedded",
            "Platform identifier=16",
            "VersionPlatform=1",
            "VersionMin=984832",
            "VersionSDK=984832",
            "Hash type=sha256 size=32",
            f"CandidateCDHash sha256={cdhash}",
            f"CandidateCDHashFull sha256={cdhash_full}",
            "Hash choices=sha256",
            f"CMSDigest={cdhash_full}",
            "CMSDigestType=2",
            "Executable Segment base=0",
            "Executable Segment limit=16384",
            "Executable Segment flags=0x1",
            "Page size=4096",
            f"CDHash={cdhash}",
            "Signature size=4442",
            "Authority=Software Signing",
            "Authority=Apple Code Signing Certification Authority",
            "Authority=Apple Root CA",
            "Signed Time=Jan 1, 2026 at 00:00:00",
            "Info.plist=not bound",
            "TeamIdentifier=not set",
            "Sealed Resources=none",
        ]
        valid: dict[str, object] = {
            "target_path": target,
            "signing_identifier": identifier,
            "expected_slices": slices,
            "verify_argv": verify_argv,
            "verify_returncode": 0,
            "verify_stdout": b"",
            "verify_stderr": ("\n".join(verify_lines) + "\n").encode(),
            "display_argv": display_argv,
            "display_returncode": 0,
            "display_stdout": display_requirement.encode(),
            "display_stderr": ("\n".join(metadata_lines) + "\n").encode(),
        }

        def args(**updates: object) -> dict[str, object]:
            return {**valid, **updates}

        metadata = valid["display_stderr"].decode()
        adversarial = {
            "self_codesign_target": args(target_path="/usr/bin/codesign"),
            "wrong_codesign_path": args(
                verify_argv=["/tmp/codesign", *verify_argv[1:]]
            ),
            "path_lookup_spelling": args(verify_argv=["codesign", *verify_argv[1:]]),
            "verify_option_order": args(
                verify_argv=[
                    "/usr/bin/codesign",
                    "--strict",
                    "--verify",
                    "--verbose=2",
                    verify_argv[4],
                    target,
                ]
            ),
            "verify_extra_arg": args(verify_argv=[*verify_argv, "--extra"]),
            "verify_wrong_target": args(
                verify_argv=[*verify_argv[:-1], "/usr/bin/false"]
            ),
            "display_option_order": args(
                display_argv=[
                    "/usr/bin/codesign",
                    "--verbose=4",
                    "-d",
                    "-r-",
                    target,
                ]
            ),
            "display_extra_arg": args(display_argv=[*display_argv, "--extra"]),
            "verify_nonzero": args(verify_returncode=1),
            "display_nonzero": args(display_returncode=1),
            "verify_stdout_nonempty": args(verify_stdout=b"diagnostic\n"),
            "verify_statement_missing": args(
                verify_stderr=("\n".join(verify_lines[:-1]) + "\n").encode()
            ),
            "verify_statement_duplicate": args(
                verify_stderr=("\n".join([*verify_lines, verify_lines[0]]) + "\n").encode()
            ),
            "verify_statement_unknown": args(
                verify_stderr=("\n".join([*verify_lines, f"{target}: unknown"]) + "\n").encode()
            ),
            "verify_statement_wrong_target": args(
                verify_stderr=valid["verify_stderr"].replace(
                    target.encode(), b"/usr/bin/false", 1
                )
            ),
            "display_requirement_missing": args(display_stdout=b""),
            "display_requirement_duplicate": args(
                display_stdout=(display_requirement * 2).encode()
            ),
            "display_requirement_wrong_identifier": args(
                display_stdout=display_requirement.replace(identifier, "com.apple.false").encode()
            ),
            "metadata_duplicate": args(
                display_stderr=(metadata + metadata_lines[1] + "\n").encode()
            ),
            "metadata_missing": args(
                display_stderr=("\n".join(metadata_lines[:-1]) + "\n").encode()
            ),
            "metadata_unknown": args(
                display_stderr=(metadata + "UnknownSecurityField=value\n").encode()
            ),
            "metadata_wrong_identifier": args(
                display_stderr=metadata.replace(
                    f"Identifier={identifier}", "Identifier=com.apple.false"
                ).encode()
            ),
            "metadata_wrong_platform": args(
                display_stderr=metadata.replace(
                    "Platform identifier=16", "Platform identifier=0"
                ).encode()
            ),
            "metadata_wrong_slices": args(
                display_stderr=metadata.replace(
                    "Mach-O universal (arm64e x86_64)", "Mach-O universal (arm64e)"
                ).encode()
            ),
            "metadata_wrong_cdhash": args(
                display_stderr=metadata.replace(
                    f"CDHash={cdhash}\n", f"CDHash={'3' * 40}\n"
                ).encode()
            ),
            "oversized_channel": args(verify_stderr=b"x" * (64 * 1024 + 1)),
            "non_utf8_channel": args(display_stderr=b"\xff"),
        }

        parser = getattr(full_gate, "parse_canonical_codesign_result", None)
        self.assertTrue(callable(parser), "generic canonical codesign parser is missing")
        with mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=AssertionError("codesign parser reached materialization"),
        ), mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("codesign parser reached execution"),
        ):
            observed = parser(**valid)
            self.assertEqual(observed["target_path"], target)
            self.assertEqual(observed["signing_identifier"], identifier)
            self.assertEqual(observed["slices"], slices)
            self.assertRegex(observed["result_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(observed, parser(**valid))
            for name, forged in adversarial.items():
                with self.subTest(name=name), self.assertRaises(
                    full_gate.FullGateError
                ) as raised:
                    parser(**forged)
                self.assertEqual(
                    raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                )


class FullGateMktempFacadeTest(unittest.TestCase):
    def test_mktemp_facade_is_direct_bounded_and_helper_free(self) -> None:
        runtime_python = "/private/tmp/samvil-full-gate-fixture/runtime/bin/python3.12"
        renderer = getattr(full_gate, "mktemp_facade_source", None)
        self.assertTrue(callable(renderer), "trusted mktemp facade API is missing")

        with mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("mktemp facade attempted subprocess"),
        ):
            source = renderer(runtime_python)
        self.assertIsInstance(source, bytes)
        self.assertTrue(source.startswith(f"#!{runtime_python}\n".encode()))
        for forbidden in (b"/usr/bin/mktemp", b"/usr/bin/env", b"shell=True"):
            self.assertNotIn(forbidden, source)

        tree = ast.parse(source.decode("utf-8"), filename="trusted-mktemp-facade.py")
        forbidden_imports = {"subprocess", "tempfile"}
        forbidden_calls = {
            "mkstemp",
            "mkdtemp",
            "system",
            "popen",
            "open",
            "unlink",
            "remove",
            "rmdir",
            "link",
            "symlink",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(
                    forbidden_imports.isdisjoint(alias.name for alias in node.names)
                )
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module, forbidden_imports)
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                call_name = ""
            self.assertNotIn(call_name, forbidden_calls)
            self.assertFalse(call_name.startswith("exec"))

        mains = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        ]
        self.assertEqual(len(mains), 1)
        main_node = mains[0]
        self.assertEqual(
            [argument.arg for argument in main_node.args.args],
            ["argv", "environment", "mkdir", "token_source"],
        )
        mkdir_calls = [
            node
            for node in ast.walk(main_node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "mkdir"
        ]
        self.assertEqual(len(mkdir_calls), 1)
        self.assertEqual(len(mkdir_calls[0].args), 2)
        self.assertIsInstance(mkdir_calls[0].args[0], ast.Name)
        self.assertEqual(mkdir_calls[0].args[0].id, "candidate")
        self.assertIsInstance(mkdir_calls[0].args[1], ast.Constant)
        self.assertEqual(mkdir_calls[0].args[1].value, 0o700)
        self.assertTrue(
            any(
                isinstance(node, ast.If)
                and "__name__" in ast.unparse(node.test)
                and "__main__" in ast.unparse(node.test)
                for node in tree.body
            )
        )

        namespace: dict[str, object] = {"__name__": "trusted_mktemp_facade_test"}
        exec(compile(tree, "trusted-mktemp-facade.py", "exec"), namespace)
        main = namespace["main"]
        signature = inspect.signature(main)
        self.assertEqual(
            list(signature.parameters),
            ["argv", "environment", "mkdir", "token_source"],
        )
        self.assertIs(signature.parameters["mkdir"].default, os.mkdir)

        tmpdir = "/private/tmp/samvil-full-gate-fixture/tmp"
        exact_argv = ["-d", "-t", "samvil-dogfood-smoke-XXXXXX"]

        def invoke(
            argv: list[str],
            environment: dict[str, str],
            mkdir: object,
            tokens: list[str],
        ) -> tuple[int, str]:
            iterator = iter(tokens)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(
                    argv,
                    environment,
                    mkdir=mkdir,
                    token_source=lambda: next(iterator),
                )
            self.assertIs(type(result), int)
            return result, stdout.getvalue()

        observed: list[tuple[str, int]] = []

        def collide_once(candidate: str, mode: int) -> None:
            observed.append((candidate, mode))
            if len(observed) == 1:
                raise FileExistsError(candidate)

        result, stdout = invoke(
            exact_argv,
            {"TMPDIR": tmpdir},
            collide_once,
            ["a" * 12, "b" * 12],
        )
        self.assertEqual(result, 0)
        self.assertEqual(observed, [
            (f"{tmpdir}/samvil-dogfood-smoke-{'a' * 12}", 0o700),
            (f"{tmpdir}/samvil-dogfood-smoke-{'b' * 12}", 0o700),
        ])
        self.assertEqual(stdout, observed[-1][0] + "\n")

        denied: list[tuple[str, int]] = []

        def permission_denied(candidate: str, mode: int) -> None:
            denied.append((candidate, mode))
            raise PermissionError(candidate)

        result, stdout = invoke(
            exact_argv,
            {"TMPDIR": tmpdir},
            permission_denied,
            ["c" * 12],
        )
        self.assertNotEqual(result, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(len(denied), 1)

        collisions: list[tuple[str, int]] = []

        def always_exists(candidate: str, mode: int) -> None:
            collisions.append((candidate, mode))
            raise FileExistsError(candidate)

        result, stdout = invoke(
            exact_argv,
            {"TMPDIR": tmpdir},
            always_exists,
            [f"{index:012x}" for index in range(16)],
        )
        self.assertNotEqual(result, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(len(collisions), 16)
        self.assertTrue(all(mode == 0o700 for _candidate, mode in collisions))

        invalid_cases = {
            "missing_args": ([], {"TMPDIR": tmpdir}, "a" * 12),
            "missing_template": (["-d", "-t"], {"TMPDIR": tmpdir}, "a" * 12),
            "unknown_arg": (["--directory"], {"TMPDIR": tmpdir}, "a" * 12),
            "extra_arg": ([*exact_argv, "extra"], {"TMPDIR": tmpdir}, "a" * 12),
            "bad_template": (["-d", "-t", "other-XXXXXX"], {"TMPDIR": tmpdir}, "a" * 12),
            "missing_tmpdir": (exact_argv, {}, "a" * 12),
            "relative_tmpdir": (exact_argv, {"TMPDIR": "relative"}, "a" * 12),
            "noncanonical_tmpdir": (exact_argv, {"TMPDIR": f"{tmpdir}/../tmp"}, "a" * 12),
            "uppercase_token": (exact_argv, {"TMPDIR": tmpdir}, "A" * 12),
            "short_token": (exact_argv, {"TMPDIR": tmpdir}, "a" * 11),
            "nonhex_token": (exact_argv, {"TMPDIR": tmpdir}, "g" * 12),
        }
        for name, (argv, environment, token) in invalid_cases.items():
            invalid_mkdir_calls: list[tuple[str, int]] = []
            with self.subTest(name=name):
                result, stdout = invoke(
                    argv,
                    environment,
                    lambda candidate, mode: invalid_mkdir_calls.append(
                        (candidate, mode)
                    ),
                    [token],
                )
                self.assertNotEqual(result, 0)
                self.assertEqual(stdout, "")
                self.assertEqual(invalid_mkdir_calls, [])


class FullGateCanonicalAdmissionOrchestrationTest(unittest.TestCase):
    @unittest.skipUnless(
        Path("/usr/bin/codesign").is_file()
        and Path("/usr/bin/sandbox-exec").is_file(),
        "macOS canonical platform tools required",
    )
    def test_real_macos_tools_are_descriptor_held_and_admitted(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        with tempfile.TemporaryDirectory(
            prefix="samvil-real-canonical-admission-", dir=temp_parent
        ) as raw:
            scratch = Path(raw).resolve(strict=True)
            rows = real_canonical_platform_rows(scratch)
            opened: list[full_gate.HeldCanonicalHostTool] = []

            def open_tool(
                row: Mapping[str, object],
            ) -> full_gate.HeldCanonicalHostTool:
                held = full_gate.open_canonical_host_tool(row)
                opened.append(held)
                return held

            authority = full_gate.acquire_canonical_host_tools(
                rows,
                open_tool=open_tool,
                run_codesign=lambda row, held: full_gate.run_canonical_codesign(
                    row,
                    held,
                    opened[0],
                    scratch_root=scratch,
                ),
                run_behavior=lambda row, held: full_gate.run_canonical_host_behavior(
                    row,
                    held,
                    scratch_root=scratch,
                ),
            )
            try:
                evidence = authority.complete()
            finally:
                authority.close()

        self.assertEqual(
            [row["role"] for row in evidence["rows"]],
            ["codesign", "sandbox-exec"],
        )
        self.assertEqual(
            evidence["rows"][1]["admission_state"], "ACCEPTED_ROW"
        )

    def test_real_canonical_tool_handle_binds_bytes_and_detects_identity_drift(
        self,
    ) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        with tempfile.TemporaryDirectory(
            prefix="samvil-canonical-tool-handle-", dir=temp_parent
        ) as raw:
            path = Path(raw).resolve(strict=True) / "tool"
            content = b"#!/bin/sh\nexit 0\n"
            path.write_bytes(content)
            path.chmod(0o755)
            metadata = path.stat()
            row = {
                "role": "fixture",
                "path": str(path),
                "uid": metadata.st_uid,
                "mode": "100755",
                "nlink": metadata.st_nlink,
                "size": metadata.st_size,
                "filesystem_flags": [],
                "read_only_filesystem": False,
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "sha256": sha256(content),
                "slices": ["arm64"],
                "load_closure": [],
                "apple_anchor": False,
                "signing_identifier": "fixture",
                "platform_identifier": 0,
                "designated_requirement": "fixture",
                "cdhash": "0" * 40,
                "behavior_probe": {
                    "schema": "samvil.host-tool-behavior.v1",
                    "result_sha256": "0" * 64,
                },
                "admission_state": "STATIC_ADMITTED",
            }
            opener = getattr(full_gate, "open_canonical_host_tool", None)
            self.assertTrue(
                callable(opener), "canonical host tools are not descriptor-held"
            )
            held = opener(row)
            try:
                self.assertEqual(dict(held.binding), row)
                held.assert_stable()
                path.chmod(0o700)
                with self.assertRaises(full_gate.FullGateError) as raised:
                    held.assert_stable()
                self.assertEqual(
                    raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                )
            finally:
                held.close()

    def test_real_canonical_behavior_probe_executes_exact_manifest_command(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        with tempfile.TemporaryDirectory(
            prefix="samvil-canonical-behavior-", dir=temp_parent
        ) as raw:
            scratch = Path(raw).resolve(strict=True)
            path = scratch / "probe-tool"
            content = b"#!/bin/sh\nprintf 'probe-out'\nprintf 'probe-err' >&2\nexit 7\n"
            path.write_bytes(content)
            path.chmod(0o755)
            metadata = path.stat()
            result_payload = {
                "schema": "samvil.host-tool-behavior-result.v1",
                "target_path": str(path),
                "argv": [str(path)],
                "returncode": 7,
                "stdout_sha256": sha256(b"probe-out"),
                "stderr_sha256": sha256(b"probe-err"),
                "status": "GREEN",
            }
            row = {
                "role": "fixture",
                "path": str(path),
                "uid": metadata.st_uid,
                "mode": "100755",
                "nlink": metadata.st_nlink,
                "size": metadata.st_size,
                "filesystem_flags": [],
                "read_only_filesystem": False,
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "sha256": sha256(content),
                "slices": ["arm64"],
                "load_closure": [],
                "apple_anchor": False,
                "signing_identifier": "fixture",
                "platform_identifier": 0,
                "designated_requirement": "fixture",
                "cdhash": "0" * 40,
                "behavior_probe": {
                    "schema": "samvil.host-tool-behavior.v1",
                    "argv": result_payload["argv"],
                    "returncode": result_payload["returncode"],
                    "stdout_sha256": result_payload["stdout_sha256"],
                    "stderr_sha256": result_payload["stderr_sha256"],
                    "result_sha256": sha256(
                        full_gate.canonical_json_bytes(result_payload)
                    ),
                },
                "admission_state": "STATIC_ADMITTED",
            }
            held = full_gate.open_canonical_host_tool(row)
            runner = getattr(full_gate, "run_canonical_host_behavior", None)
            self.assertTrue(
                callable(runner), "canonical behavior probe executor is missing"
            )
            try:
                observed = runner(row, held, scratch_root=scratch)
            finally:
                held.close()
            self.assertEqual(
                observed,
                {
                    "schema": "samvil.host-tool-behavior-result.v1",
                    "target_path": str(path),
                    "status": "GREEN",
                    "result_sha256": sha256(
                        full_gate.canonical_json_bytes(result_payload)
                    ),
                },
            )

    def test_canonical_codesign_runner_uses_pinned_verifier_and_exact_argv(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        with tempfile.TemporaryDirectory(
            prefix="samvil-canonical-codesign-runner-", dir=temp_parent
        ) as raw:
            scratch = Path(raw).resolve(strict=True)
            row = FullGateManifestProtocolTest().canonical_host_row(
                "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
            )
            fixture = canonical_codesign_channel_fixture(
                row["path"], row["signing_identifier"]
            )

            class FakeHeld:
                def __init__(self, binding: Mapping[str, object]) -> None:
                    self.binding = binding
                    self.stable_calls = 0

                def assert_stable(self) -> None:
                    self.stable_calls += 1

            target = FakeHeld(row)
            verifier = FakeHeld(
                {"role": "codesign", "path": "/usr/bin/codesign"}
            )
            completed = (
                subprocess.CompletedProcess(
                    fixture["verify_argv"],
                    fixture["verify_returncode"],
                    fixture["verify_stdout"],
                    fixture["verify_stderr"],
                ),
                subprocess.CompletedProcess(
                    fixture["display_argv"],
                    fixture["display_returncode"],
                    fixture["display_stdout"],
                    fixture["display_stderr"],
                ),
            )
            runner = getattr(full_gate, "run_canonical_codesign", None)
            self.assertTrue(callable(runner), "canonical codesign runner is missing")
            with mock.patch.object(
                full_gate.subprocess, "run", side_effect=completed
            ) as run:
                observed = runner(
                    row,
                    target,
                    verifier,
                    scratch_root=scratch,
                )
            self.assertEqual(observed, fixture)
            self.assertEqual(
                [call.args[0] for call in run.call_args_list],
                [fixture["verify_argv"], fixture["display_argv"]],
            )
            self.assertGreaterEqual(target.stable_calls, 2)
            self.assertGreaterEqual(verifier.stable_calls, 2)

    def test_canonical_rows_are_admitted_in_order_without_self_verification(self) -> None:
        protocol = FullGateManifestProtocolTest()
        codesign = protocol.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = protocol.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        bash = protocol.canonical_host_row(
            "bash", "/bin/bash", "STATIC_ADMITTED", inode=3
        )
        sandbox = protocol.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=4
        )
        env_codesign = full_gate.parse_canonical_codesign_result(
            **canonical_codesign_channel_fixture(
                env["path"], env["signing_identifier"]
            )
        )
        codesign["behavior_probe"] = {
            "schema": "samvil.codesign-verifier-behavior.v1",
            "first_non_self_role": "env",
            "result_sha256": env_codesign["result_sha256"],
        }

        class FakeHeld:
            def __init__(self, row: dict[str, object]) -> None:
                self.binding = json.loads(json.dumps(row))
                self.stable_calls = 0
                self.close_calls = 0

            def assert_stable(self) -> None:
                self.stable_calls += 1

            def close(self) -> None:
                self.close_calls += 1

        orchestrator = getattr(full_gate, "admit_canonical_host_tools", None)
        self.assertTrue(
            callable(orchestrator), "canonical host-tool admission API is missing"
        )

        def run_case(
            rows: list[dict[str, object]],
            *,
            mutate_after_probe_role: str | None = None,
            codesign_mode: str = "valid",
            tracker: dict[str, object],
        ) -> dict[str, object]:
            handles = tracker["handles"]
            calls = tracker["calls"]
            self.assertIsInstance(handles, list)
            self.assertIsInstance(calls, list)

            def open_tool(row: dict[str, object]) -> FakeHeld:
                held = FakeHeld(row)
                handles.append(held)
                return held

            def run_codesign(
                row: dict[str, object], held: FakeHeld
            ) -> dict[str, object]:
                calls.append(f"codesign:{row['role']}")
                if codesign_mode == "forged_full_gate" and row["role"] == "env":
                    raise full_gate.FullGateError("FORGED_PASS")
                return canonical_codesign_channel_fixture(
                    row["path"], row["signing_identifier"]
                )

            def run_behavior(
                row: dict[str, object], held: FakeHeld
            ) -> object:
                calls.append(f"behavior:{row['role']}")
                expected_digest = row["behavior_probe"]["result_sha256"]
                result: object = {
                    "schema": "samvil.host-tool-behavior-result.v1",
                    "target_path": row["path"],
                    "status": "GREEN",
                    "result_sha256": expected_digest,
                }
                if row["role"] == mutate_after_probe_role:
                    held.binding["sha256"] = "0" * 64
                return result

            return orchestrator(
                rows,
                open_tool=open_tool,
                run_codesign=run_codesign,
                run_behavior=run_behavior,
            )

        base_rows = [codesign, env, bash, sandbox]

        def cloned_rows(verifier_probe_mode: str = "valid") -> list[dict[str, object]]:
            rows = json.loads(json.dumps(base_rows))
            verifier_probe = rows[0]["behavior_probe"]
            if verifier_probe_mode == "wrong_digest":
                verifier_probe["result_sha256"] = "0" * 64
            return rows

        happy_calls = [
            "codesign:env",
            "behavior:env",
            "codesign:bash",
            "behavior:bash",
            "codesign:sandbox-exec",
            "behavior:sandbox-exec",
        ]

        with mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=AssertionError("canonical admission reached materialization"),
        ), mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("canonical admission reached subprocess"),
        ):
            happy_tracker: dict[str, object] = {"handles": [], "calls": []}
            evidence = run_case(
                cloned_rows(),
                tracker=happy_tracker,
            )
            with self.subTest(name="happy"):
                self.assertEqual(happy_tracker["calls"], happy_calls)
                self.assertNotIn("codesign:codesign", happy_tracker["calls"])
                self.assertEqual(
                    evidence["schema"], "samvil.canonical-host-admission.v1"
                )
                self.assertEqual(
                    evidence["rows"][0],
                    {
                        "role": "codesign",
                        "path": "/usr/bin/codesign",
                        "admission_state": "PLATFORM_VERIFIER_PINNED",
                        "self_verified": False,
                        "first_non_self_target": "/usr/bin/env",
                        "verifier_behavior_result_sha256": env_codesign[
                            "result_sha256"
                        ],
                        "identity_pre_post": "stable",
                    },
                )
                for row, admitted in zip(
                    (env, bash, sandbox), evidence["rows"][1:]
                ):
                    parsed = full_gate.parse_canonical_codesign_result(
                        **canonical_codesign_channel_fixture(
                            row["path"], row["signing_identifier"]
                        )
                    )
                    self.assertEqual(admitted["role"], row["role"])
                    self.assertEqual(admitted["path"], row["path"])
                    self.assertEqual(admitted["admission_state"], "ACCEPTED_ROW")
                    self.assertEqual(
                        admitted["codesign_result_sha256"], parsed["result_sha256"]
                    )
                    self.assertEqual(
                        admitted["behavior_result_sha256"],
                        row["behavior_probe"]["result_sha256"],
                    )
                    self.assertEqual(admitted["identity_pre_post"], "stable")
                digest_payload = dict(evidence)
                digest = digest_payload.pop("result_sha256")
                self.assertEqual(
                    digest, sha256(full_gate.canonical_json_bytes(digest_payload))
                )
                self.assertTrue(
                    all(
                        held.stable_calls >= 2 and held.close_calls == 1
                        for held in happy_tracker["handles"]
                    )
                )

            adversarial_cases = (
                {
                    "name": "verifier_behavior_wrong_digest",
                    "verifier_probe_mode": "wrong_digest",
                    "expected_calls": ["codesign:env"],
                },
                {
                    "name": "post_probe_binding_mutation",
                    "mutate_after_probe_role": "env",
                    "expected_calls": ["codesign:env", "behavior:env"],
                },
                {
                    "name": "callback_forged_full_gate_error",
                    "codesign_mode": "forged_full_gate",
                    "expected_calls": ["codesign:env"],
                },
            )
            control_keys = {"name", "verifier_probe_mode", "expected_calls"}
            for case in adversarial_cases:
                tracker: dict[str, object] = {"handles": [], "calls": []}
                verifier_probe_mode = case.get("verifier_probe_mode", "valid")
                kwargs = {
                    key: value for key, value in case.items() if key not in control_keys
                }
                raised: full_gate.FullGateError | None = None
                with self.subTest(name=case["name"]):
                    try:
                        run_case(
                            cloned_rows(verifier_probe_mode),
                            tracker=tracker,
                            **kwargs,
                        )
                    except full_gate.FullGateError as exc:
                        raised = exc
                    self.assertTrue(
                        all(
                            held.close_calls == 1 for held in tracker["handles"]
                        ),
                        "every opened handle must close exactly once",
                    )
                    self.assertIsNotNone(
                        raised, "adversarial canonical admission was accepted"
                    )
                    self.assertEqual(
                        raised.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                    )
                    self.assertEqual(tracker["calls"], case["expected_calls"])


class FullGateApprovedHostToolAuthorityDispatcherTest(unittest.TestCase):
    def canonical_rows(self) -> list[dict[str, object]]:
        protocol = FullGateManifestProtocolTest()
        codesign = protocol.canonical_host_row(
            "codesign",
            "/usr/bin/codesign",
            "PLATFORM_VERIFIER_PINNED",
            inode=1,
        )
        env = protocol.canonical_host_row(
            "env", "/usr/bin/env", "STATIC_ADMITTED", inode=2
        )
        bash = protocol.canonical_host_row(
            "bash", "/bin/bash", "STATIC_ADMITTED", inode=3
        )
        sandbox = protocol.canonical_host_row(
            "sandbox-exec", "/usr/bin/sandbox-exec", "STATIC_ADMITTED", inode=4
        )
        env_codesign = full_gate.parse_canonical_codesign_result(
            **canonical_codesign_channel_fixture(
                env["path"], env["signing_identifier"]
            )
        )
        codesign["behavior_probe"] = {
            "schema": "samvil.codesign-verifier-behavior.v1",
            "first_non_self_role": "env",
            "result_sha256": env_codesign["result_sha256"],
        }
        return [codesign, env, bash, sandbox]

    def test_canonical_authority_stays_held_until_completion_and_close(self) -> None:
        rows = self.canonical_rows()
        acquire = getattr(full_gate, "acquire_canonical_host_tools", None)
        self.assertTrue(
            callable(acquire), "held canonical host-tool acquisition API is missing"
        )

        class FakeHeld:
            def __init__(
                self,
                row: dict[str, object],
                close_order: list[str],
            ) -> None:
                self.role = row["role"]
                self.binding = json.loads(json.dumps(row))
                self.stable_calls = 0
                self.close_calls = 0
                self.close_order = close_order

            def assert_stable(self) -> None:
                self.stable_calls += 1

            def close(self) -> None:
                self.close_calls += 1
                self.close_order.append(self.role)

        def acquire_case(
            *, fail_codesign: bool = False
        ) -> tuple[object, list[FakeHeld], list[str], list[str]]:
            handles: list[FakeHeld] = []
            calls: list[str] = []
            close_order: list[str] = []

            def open_tool(row: dict[str, object]) -> FakeHeld:
                held = FakeHeld(row, close_order)
                handles.append(held)
                return held

            def run_codesign(
                row: dict[str, object], held: FakeHeld
            ) -> dict[str, object]:
                calls.append(f"codesign:{row['role']}")
                if fail_codesign and row["role"] == "env":
                    raise RuntimeError("injected codesign failure")
                return canonical_codesign_channel_fixture(
                    row["path"], row["signing_identifier"]
                )

            def run_behavior(
                row: dict[str, object], held: FakeHeld
            ) -> dict[str, object]:
                calls.append(f"behavior:{row['role']}")
                return {
                    "schema": "samvil.host-tool-behavior-result.v1",
                    "target_path": row["path"],
                    "status": "GREEN",
                    "result_sha256": row["behavior_probe"]["result_sha256"],
                }

            authority = acquire(
                rows,
                open_tool=open_tool,
                run_codesign=run_codesign,
                run_behavior=run_behavior,
            )
            return authority, handles, calls, close_order

        with mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("canonical authority reached subprocess"),
        ):
            with self.subTest(name="held_until_complete_then_reverse_close"):
                authority, handles, calls, close_order = acquire_case()
                self.assertEqual(
                    calls,
                    [
                        "codesign:env",
                        "behavior:env",
                        "codesign:bash",
                        "behavior:bash",
                        "codesign:sandbox-exec",
                        "behavior:sandbox-exec",
                    ],
                )
                self.assertEqual(
                    authority.executable_path("sandbox-exec"),
                    Path("/usr/bin/sandbox-exec"),
                )
                self.assertTrue(all(held.close_calls == 0 for held in handles))
                stable_after_acquire = [held.stable_calls for held in handles]
                evidence = authority.complete()
                expected_payload = {
                    "schema": "samvil.canonical-host-admission.v1",
                    "rows": evidence["rows"],
                }
                self.assertEqual(
                    evidence,
                    {
                        **expected_payload,
                        "result_sha256": sha256(
                            full_gate.canonical_json_bytes(expected_payload)
                        ),
                    },
                )
                self.assertEqual(
                    [held.stable_calls for held in handles],
                    [count + 1 for count in stable_after_acquire],
                )
                self.assertTrue(all(held.close_calls == 0 for held in handles))
                authority.close()
                self.assertEqual(
                    close_order, ["sandbox-exec", "bash", "env", "codesign"]
                )
                self.assertTrue(all(held.close_calls == 1 for held in handles))

            with self.subTest(name="post_acquire_binding_drift"):
                authority, handles, _calls, close_order = acquire_case()
                handles[1].binding["path"] = "/usr/bin/false"
                try:
                    with self.assertRaises(full_gate.FullGateError) as raised:
                        authority.complete()
                    self.assertEqual(
                        raised.exception.status,
                        "UNSUPPORTED_CANONICAL_TOOLCHAIN",
                    )
                finally:
                    authority.close()
                self.assertEqual(
                    close_order, ["sandbox-exec", "bash", "env", "codesign"]
                )
                self.assertTrue(all(held.close_calls == 1 for held in handles))

            with self.subTest(name="close_before_complete"):
                authority, handles, _calls, close_order = acquire_case()
                authority.close()
                with self.assertRaises(full_gate.FullGateError) as raised:
                    authority.complete()
                self.assertEqual(
                    raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                )
                self.assertEqual(
                    close_order, ["sandbox-exec", "bash", "env", "codesign"]
                )
                self.assertTrue(all(held.close_calls == 1 for held in handles))

            with self.subTest(name="acquisition_failure_closes_immediately"):
                failed_handles: list[FakeHeld] = []
                failed_close_order: list[str] = []

                def failing_open(row: dict[str, object]) -> FakeHeld:
                    held = FakeHeld(row, failed_close_order)
                    failed_handles.append(held)
                    return held

                with self.assertRaises(full_gate.FullGateError) as raised:
                    acquire(
                        rows,
                        open_tool=failing_open,
                        run_codesign=lambda _row, _held: (_ for _ in ()).throw(
                            RuntimeError("injected codesign failure")
                        ),
                        run_behavior=lambda _row, _held: self.fail(
                            "behavior ran after codesign failure"
                        ),
                    )
                self.assertEqual(
                    raised.exception.status, "UNSUPPORTED_CANONICAL_TOOLCHAIN"
                )
                self.assertEqual(
                    failed_close_order, ["sandbox-exec", "bash", "env", "codesign"]
                )
                self.assertTrue(
                    all(held.close_calls == 1 for held in failed_handles)
                )

    def test_approved_manifest_dispatches_to_held_canonical_authority(self) -> None:
        protocol = FullGateManifestProtocolTest()
        rows = self.canonical_rows()
        validated = full_gate.validate_manifest_object(
            protocol.approved_host_tool_manifest(rows)
        )
        dispatcher = getattr(
            full_gate, "acquire_manifest_host_tool_authority", None
        )
        self.assertTrue(
            callable(dispatcher),
            "approved host-tool authority dispatcher is missing",
        )

        scratch = Path("/pure-test/canonical-host-tool-scratch")
        open_tool = mock.Mock(name="open_tool")
        run_codesign = mock.Mock(name="run_codesign")
        run_behavior = mock.Mock(name="run_behavior")
        expected_authority = object()
        with mock.patch.object(
            full_gate,
            "acquire_canonical_host_tools",
            create=True,
            return_value=expected_authority,
        ) as canonical_acquire, mock.patch.object(
            full_gate,
            "admit_canonical_host_tools",
            return_value={"legacy": "immediate-evidence"},
        ) as immediate_admit, mock.patch.object(
            full_gate,
            "acquire_apple_platform_tcb",
            side_effect=AssertionError("approved manifest reached legacy Apple TCB"),
        ) as legacy_acquire, mock.patch.object(
            full_gate.subprocess,
            "run",
            side_effect=AssertionError("authority dispatch reached subprocess"),
        ):
            authority = dispatcher(
                validated,
                scratch,
                open_tool=open_tool,
                run_codesign=run_codesign,
                run_behavior=run_behavior,
            )

        with self.subTest(name="returns_held_authority"):
            self.assertIs(authority, expected_authority)
        with self.subTest(name="canonical_acquire_once"):
            canonical_acquire.assert_called_once_with(
                validated.raw["canonical_host_tools"]["rows"],
                open_tool=open_tool,
                run_codesign=run_codesign,
                run_behavior=run_behavior,
            )
        with self.subTest(name="no_immediate_admission"):
            immediate_admit.assert_not_called()
        with self.subTest(name="no_legacy_acquire"):
            legacy_acquire.assert_not_called()

    def test_runtime_adapter_binds_external_parser_evidence_to_real_callbacks(self) -> None:
        protocol = FullGateManifestProtocolTest()
        rows = self.canonical_rows()
        validated = full_gate.validate_manifest_object(
            protocol.approved_host_tool_manifest(rows)
        )
        parser_evidence = {
            "schema": "samvil.host-tool-identity-parser-evidence.v1",
            "source_sha256": validated.raw["host_tool_identity_parser"][
                "source_sha256"
            ],
            "interpreter_sha256": validated.raw["host_tool_identity_parser"][
                "materialized"
            ]["interpreter"]["sha256"],
            "input_count": len(
                validated.raw["host_tool_identity_parser"]["inputs"]
            ),
            "result_sha256": validated.raw["host_tool_identity_parser"][
                "result_sha256"
            ],
            "byte_identical": True,
            "staged_runner_authority": False,
        }
        parser_evidence["evidence_sha256"] = sha256(
            full_gate.canonical_json_bytes(parser_evidence)
        )
        scratch = Path("/pure-test/canonical-runtime-scratch")
        events: list[str] = []

        class FakeHeld:
            def __init__(self, row: Mapping[str, object]) -> None:
                self.binding = dict(row)

            def assert_stable(self) -> None:
                return None

            def close(self) -> None:
                return None

        handles = {row["role"]: FakeHeld(row) for row in rows}
        expected_authority = object()

        def acquire(
            manifest: full_gate.ValidatedManifest,
            scratch_root: Path,
            *,
            open_tool: object,
            run_codesign: object,
            run_behavior: object,
        ) -> object:
            self.assertIs(manifest, validated)
            self.assertEqual(scratch_root, scratch)
            codesign = open_tool(rows[0])
            env = open_tool(rows[1])
            run_codesign(rows[1], env)
            run_behavior(rows[1], env)
            self.assertIs(codesign, handles["codesign"])
            return expected_authority

        adapter = getattr(
            full_gate, "acquire_runtime_manifest_host_tool_authority", None
        )
        self.assertTrue(
            callable(adapter), "approved runtime authority adapter is missing"
        )
        with mock.patch.object(
            full_gate,
            "acquire_manifest_host_tool_authority",
            side_effect=acquire,
        ), mock.patch.object(
            full_gate,
            "open_canonical_host_tool",
            side_effect=lambda row: events.append(f"open:{row['role']}")
            or handles[row["role"]],
        ), mock.patch.object(
            full_gate,
            "run_canonical_codesign",
            side_effect=lambda row, _held, verifier, **_kwargs: events.append(
                f"codesign:{row['role']}:{verifier.binding['role']}"
            )
            or canonical_codesign_channel_fixture(
                row["path"], row["signing_identifier"]
            ),
        ), mock.patch.object(
            full_gate,
            "run_canonical_host_behavior",
            side_effect=lambda row, _held, **_kwargs: events.append(
                f"behavior:{row['role']}"
            )
            or {
                "schema": "samvil.host-tool-behavior-result.v1",
                "target_path": row["path"],
                "status": "GREEN",
                "result_sha256": row["behavior_probe"]["result_sha256"],
            },
        ):
            authority = adapter(
                validated,
                scratch,
                parser_evidence=parser_evidence,
            )
        self.assertIs(authority, expected_authority)
        self.assertEqual(
            events,
            ["open:codesign", "open:env", "codesign:env:codesign", "behavior:env"],
        )


class FullGateLoopbackProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-profile-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.invocation = self.base / "invocation"
        self.snapshot = self.invocation / "snapshot"
        self.runtime = self.invocation / "runtime"
        self.tools = self.invocation / "tools"
        self.protected_home = self.base / "protected-home"
        self.protected_codex = self.protected_home / ".codex"
        self.executable_allowlist = sorted(
            (
                str(SYSTEM_PYTHON),
                str(SYSTEM_PYTHON.resolve(strict=True)),
                str(
                    Path(sys.base_prefix)
                    / "Resources/Python.app/Contents/MacOS/Python"
                ),
                str(self.runtime / "bin/python3.12"),
                str(self.tools / "facade/bin/python3.12"),
            )
        )
        for path in (
            self.snapshot,
            self.runtime,
            self.tools,
            self.protected_codex,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (self.protected_home / "sentinel").write_text("secret", encoding="utf-8")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_profile_is_fixed_loopback_tcp_only_and_denies_protected_roots(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "render_loopback_profile"),
            "fixed loopback-only profile is not implemented",
        )
        signature = inspect.signature(full_gate.render_loopback_profile)
        self.assertIn(
            "executable_allowlist",
            signature.parameters,
            "profile renderer does not require an executable allowlist",
        )
        self.assertIs(
            signature.parameters["executable_allowlist"].default,
            inspect.Parameter.empty,
        )
        profile, source_digest, rendered_digest = full_gate.render_loopback_profile(
            self.invocation,
            self.snapshot,
            self.runtime,
            self.tools,
            protected_roots=(self.protected_home, self.protected_codex),
            executable_allowlist=self.executable_allowlist,
        )
        self.assertRegex(source_digest + rendered_digest, r"^[0-9a-f]{128}$")
        self.assertIn(b"(deny default)", profile)
        self.assertIn(b"(deny network*)", profile)
        self.assertNotIn(b"(allow network*)", profile)
        self.assertEqual(profile.count(b"allow network-inbound"), 1)
        self.assertEqual(profile.count(b"allow network-outbound"), 1)
        self.assertIn(b'(local tcp "localhost:*")', profile)
        self.assertIn(b'(remote tcp "localhost:*")', profile)
        self.assertNotIn(b"udp", profile.lower())
        self.assertNotIn(b"unix", profile.lower())
        self.assertNotIn(b"192.0.2.1", profile)
        protected_metadata = profile.index(b"deny file-read-metadata file-test-existence")
        global_metadata = profile.index(b"allow file-read-metadata file-test-existence")
        self.assertLess(protected_metadata, global_metadata)
        self.assertIn(b"deny file-read*", profile)
        self.assertIn(b"deny file-write*", profile)
        self.assertEqual(profile.count(b"(deny file-write-xattr)"), 1)
        self.assertLess(
            profile.index(b"(deny file-write-xattr)"),
            profile.index(b"(allow file-write*"),
        )
        self.assertEqual(profile.count(b"(allow process-fork)"), 1)
        self.assertNotIn(b"(allow process*)", profile)
        process_exec_lines = [
            line
            for line in profile.splitlines()
            if line.startswith(b"(allow process-exec ")
        ]
        self.assertEqual(len(process_exec_lines), 1)
        expected_exec_line = (
            b"(allow process-exec (require-any "
            + b" ".join(
                b"(literal "
                + json.dumps(path, ensure_ascii=True).encode("ascii")
                + b")"
                for path in self.executable_allowlist
            )
            + b"))"
        )
        self.assertEqual(process_exec_lines[0], expected_exec_line)
        self.assertNotIn(b"(subpath ", process_exec_lines[0])
        self.assertNotIn(b"(regex ", process_exec_lines[0])
        self.assertNotIn(b"*", process_exec_lines[0])
        self.assertEqual(full_gate.PROFILE_CLASS, "pinned-full-gate-loopback-only")

    def test_profile_exec_allowlist_rejects_noncanonical_values_before_render(self) -> None:
        signature = inspect.signature(full_gate.render_loopback_profile)
        self.assertIn(
            "executable_allowlist",
            signature.parameters,
            "profile renderer does not accept an executable allowlist",
        )
        first, second = self.executable_allowlist[:2]
        invalid_cases = {
            "empty": [],
            "unsorted": [second, first],
            "duplicate": [first, first],
            "relative": ["bin/python3.12"],
            "dot_segment": ["/pure-test/./python3.12"],
            "parent_segment": ["/pure-test/../python3.12"],
            "nul": ["/pure-test/python3.12\x00suffix"],
            "backslash": ["/pure-test/python\\3.12"],
            "wildcard": ["/pure-test/*/python3.12"],
        }
        for name, allowlist in invalid_cases.items():
            with self.subTest(name=name), mock.patch.object(
                full_gate,
                "_profile_literal",
                side_effect=AssertionError(
                    "invalid executable allowlist reached profile rendering"
                ),
            ), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.render_loopback_profile(
                    self.invocation,
                    self.snapshot,
                    self.runtime,
                    self.tools,
                    protected_roots=(self.protected_home, self.protected_codex),
                    executable_allowlist=allowlist,
                )
            self.assertEqual(
                raised.exception.status, "PROFILE_EXEC_ALLOWLIST_INVALID"
            )

    def test_profile_source_digest_is_bound_to_exact_exec_allowlist(self) -> None:
        signature = inspect.signature(full_gate.render_loopback_profile)
        self.assertIn(
            "executable_allowlist",
            signature.parameters,
            "profile renderer does not bind an executable allowlist",
        )

        def render(allowlist: list[str]) -> tuple[bytes, str, str]:
            return full_gate.render_loopback_profile(
                self.invocation,
                self.snapshot,
                self.runtime,
                self.tools,
                protected_roots=(self.protected_home, self.protected_codex),
                executable_allowlist=allowlist,
            )

        first = render(self.executable_allowlist)
        repeated = render(list(self.executable_allowlist))
        changed_allowlist = sorted(
            [*self.executable_allowlist, str(self.snapshot / "bin/pytest")]
        )
        changed = render(changed_allowlist)
        self.assertEqual(first, repeated)
        self.assertNotEqual(first[1], changed[1])
        self.assertNotEqual(first[2], changed[2])

    def test_hermetic_environment_owns_all_home_tmp_xdg_and_git_state(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "build_hermetic_environment"),
            "hermetic full-gate environment is not implemented",
        )
        hostile = {
            "HOME": "/owner/home",
            "CODEX_HOME": "/owner/codex",
            "PROFILE_CLASS": "release-control-network-zero",
            "SAMVIL_FULL_GATE_ROOT": "/candidate",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "GIT_CONFIG_GLOBAL": "/owner/gitconfig",
            "PYTHONPATH": "/candidate/imports",
        }
        environment = full_gate.build_hermetic_environment(
            self.invocation, self.runtime, self.tools, source_environment=hostile
        )
        self.assertEqual(set(environment), set(full_gate.HERMETIC_ENVIRONMENT_KEYS))
        for key in (
            "HOME",
            "CODEX_HOME",
            "CLAUDE_CONFIG_DIR",
            "GNUPGHOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "GIT_CONFIG_GLOBAL",
            "PIP_CONFIG_FILE",
        ):
            path = Path(environment[key]).resolve(strict=True)
            self.assertTrue(path.is_relative_to(self.invocation))
        self.assertNotIn("PROFILE_CLASS", environment)
        self.assertNotIn("SAMVIL_FULL_GATE_ROOT", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        self.assertTrue(Path(environment["GIT_CONFIG_GLOBAL"]).is_file())

    def test_real_profile_preflight_skips_before_spawn_without_opt_in(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("non-opted-in real profile reached Popen"),
        ), self.assertRaises(unittest.SkipTest) as raised:
            self.test_real_profile_allows_loopback_tcp_and_denies_other_authority()
        self.assertIn("REAL_SEATBELT_OPT_IN_REQUIRED", str(raised.exception))

    def test_real_profile_uses_copied_python_hermetic_env_and_bounded_runner(
        self,
    ) -> None:
        runtime_source = self.base / "approved-source"
        (runtime_source / "bin").mkdir(parents=True)
        (runtime_source / "bin/python3.12").write_bytes(b"approved")
        context = RealSeatbeltContext(
            sandbox_executable=Path("/usr/bin/sandbox-exec"),
            pinned_runtime_source=runtime_source,
            invocation_tmpdir=self.base,
        )

        def fake_copy(destination: Path, **_kwargs: object) -> None:
            (destination / "bin").mkdir(parents=True)
            executable = destination / "bin/python3.12"
            executable.write_bytes(b"copied")
            executable.chmod(0o755)

        payload = {
            "loopback_tcp": True,
            "external_tcp": errno.EPERM,
            "udp": errno.EPERM,
            "unix": errno.EPERM,
            "stat": errno.EPERM,
            "lstat": errno.EPERM,
            "read": errno.EPERM,
            "write": errno.EPERM,
            "access": False,
            "exists": False,
        }
        completed = subprocess.CompletedProcess(
            [], 0, json.dumps(payload).encode("utf-8"), b""
        )
        with mock.patch(
            f"{__name__}.require_real_seatbelt_context", return_value=context
        ), mock.patch(
            f"{__name__}.copy_pinned_runtime", side_effect=fake_copy
        ), mock.patch(
            f"{__name__}.run_bounded_harness_process", return_value=completed
        ) as run:
            self.test_real_profile_allows_loopback_tcp_and_denies_other_authority()

        argv = run.call_args.args[0]
        environment = run.call_args.kwargs["environment"]
        self.assertEqual(argv[0], "/usr/bin/sandbox-exec")
        copied_python = str(self.invocation / "seatbelt-runtime/bin/python3.12")
        self.assertIn(copied_python, argv)
        self.assertNotIn(str(SYSTEM_PYTHON), argv)
        profile_text = argv[argv.index("-p") + 1]
        self.assertIn(copied_python, profile_text)
        self.assertNotIn(str(SYSTEM_PYTHON), profile_text)
        python_index = argv.index(copied_python)
        self.assertEqual(argv[python_index + 1 : python_index + 3], ["-I", "-B"])
        probe_source = argv[argv.index("-c") + 1]
        for timeout_statement in (
            "listener.settimeout(1.0)",
            "client.settimeout(1.0)",
            "accepted.settimeout(1.0)",
        ):
            self.assertIn(timeout_statement, probe_source)
        self.assertEqual(set(environment), set(full_gate.HERMETIC_ENVIRONMENT_KEYS))
        socket_path = Path(argv[-1])
        self.assertTrue(socket_path.is_relative_to(Path(environment["TMPDIR"])))
        self.assertIsNone(run.call_args.kwargs.get("pass_fds"))
        source = inspect.getsource(
            FullGateLoopbackProfileTest.test_real_profile_allows_loopback_tcp_and_denies_other_authority
        )
        self.assertGreaterEqual(source.count(".settimeout("), 4)
        self.assertIn("run_bounded_harness_process", source)
        self.assertNotIn("subprocess.run", source)

    def test_real_profile_allows_loopback_tcp_and_denies_other_authority(self) -> None:
        context = require_real_seatbelt_context()
        runtime = self.invocation / "seatbelt-runtime"
        copy_pinned_runtime(
            runtime,
            runtime_source=context.pinned_runtime_source,
        )
        pinned_python = runtime / "bin/python3.12"
        executable_allowlist = [str(pinned_python)]
        profile, _source_digest, _rendered_digest = full_gate.render_loopback_profile(
            self.invocation,
            self.snapshot,
            runtime,
            self.tools,
            protected_roots=(self.protected_home, self.protected_codex),
            executable_allowlist=executable_allowlist,
        )
        environment = full_gate.build_hermetic_environment(
            self.invocation, runtime, self.tools
        )
        probe = r'''
import errno, json, os, socket, sys
protected_home, protected_codex, socket_path = sys.argv[1:]
results = {}

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.settimeout(1.0)
listener.bind(("127.0.0.1", 0))
listener.listen(1)
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.settimeout(1.0)
client.connect(("127.0.0.1", listener.getsockname()[1]))
accepted, _ = listener.accept()
accepted.settimeout(1.0)
accepted.close(); client.close(); listener.close()
results["loopback_tcp"] = True

def expect_eperm(name, operation):
    try:
        operation()
    except OSError as exc:
        results[name] = exc.errno
    else:
        results[name] = "allowed"

def external_tcp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.2)
        sock.connect(("192.0.2.1", 9))
    finally:
        sock.close()

def udp_send():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"x", ("127.0.0.1", 9))
    finally:
        sock.close()

def unix_bind():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(socket_path)
    finally:
        sock.close()

expect_eperm("external_tcp", external_tcp)
expect_eperm("udp", udp_send)
expect_eperm("unix", unix_bind)
expect_eperm("stat", lambda: os.stat(protected_home))
expect_eperm("lstat", lambda: os.lstat(protected_codex))
expect_eperm("read", lambda: open(os.path.join(protected_home, "sentinel"), "rb"))
expect_eperm("write", lambda: open(os.path.join(protected_codex, "created"), "wb"))
results["access"] = os.access(protected_home, os.F_OK)
results["exists"] = os.path.exists(protected_codex)
print(json.dumps(results, sort_keys=True, separators=(",", ":")))
'''
        socket_path = Path(environment["TMPDIR"]) / "seatbelt-denied.sock"
        result = run_bounded_harness_process(
            [
                str(context.sandbox_executable),
                "-p",
                profile.decode("utf-8"),
                str(pinned_python),
                "-I",
                "-B",
                "-c",
                probe,
                str(self.protected_home),
                str(self.protected_codex),
                str(socket_path),
            ],
            cwd=self.invocation,
            environment=environment,
            tmpdir=Path(environment["TMPDIR"]),
            timeout=10,
        )
        self.assertEqual(
            result.returncode, 0, result.stderr.decode("utf-8", "replace")
        )
        payload = json.loads(result.stdout.decode("utf-8", "strict"))
        self.assertTrue(payload["loopback_tcp"])
        for key in ("external_tcp", "udp", "unix", "stat", "lstat", "read", "write"):
            self.assertEqual(
                payload[key],
                errno.EPERM,
                (key, payload, result.stderr.decode("utf-8", "replace")),
            )
        self.assertFalse(payload["access"])
        self.assertFalse(payload["exists"])


class FullGateOutputAndFixedLogProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-output-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.receipt = self.base / "receipt.json"
        self.denial = self.base / "denial.log"
        self.lock = self.base / "full-gate.lock"
        self.logs = tuple(self.base / Path(path).name for path in full_gate.FIXED_LOG_PATHS)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_outputs_are_exclusive_held_descriptors_and_detect_replacement(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "create_output_files"),
            "held output protocol is not implemented",
        )
        outputs = full_gate.create_output_files(
            str(self.receipt), str(self.denial), reserved_paths=()
        )
        self.addCleanup(outputs.close)
        payload = full_gate.canonical_json_bytes({"status": "PASS"})
        full_gate.write_output(outputs.receipt, payload)
        self.assertEqual(self.receipt.read_bytes(), payload)

        detached = self.base / "detached.json"
        self.receipt.rename(detached)
        self.receipt.write_bytes(b"owner")
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.write_output(outputs.receipt, payload)
        self.assertEqual(raised.exception.status, "OUTPUT_IDENTITY_MISMATCH")
        self.assertEqual(self.receipt.read_bytes(), b"owner")

    def test_preexisting_outputs_lock_contention_and_log_failures_are_closed(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "acquire_fixed_log_protocol"),
            "fixed log lock protocol is not implemented",
        )
        self.receipt.write_text("owner", encoding="utf-8")
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.create_output_files(
                str(self.receipt), str(self.denial), reserved_paths=()
            )
        self.assertEqual(raised.exception.status, "OUTPUT_PREEXISTS")
        self.assertEqual(self.receipt.read_text(encoding="utf-8"), "owner")
        self.receipt.unlink()

        with mock.patch.object(full_gate, "FULL_GATE_LOCK_PATH", self.lock), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ):
            protocol = full_gate.acquire_fixed_log_protocol()
            self.addCleanup(protocol.close)
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.acquire_fixed_log_protocol()
            self.assertEqual(raised.exception.status, "FULL_GATE_LOCK_CONTENDED")

            for index, path in enumerate(self.logs):
                path.write_text(f"log-{index}\n", encoding="utf-8")
            moved = full_gate.capture_fixed_logs(protocol, self.base / "captured")
            self.assertEqual(len(moved), 5)
            self.assertTrue(all(not path.exists() for path in self.logs))
            self.assertTrue(all((self.base / "captured" / path.name).is_file() for path in self.logs))

        self.lock.unlink()
        with mock.patch.object(full_gate, "FULL_GATE_LOCK_PATH", self.lock), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ):
            protocol = full_gate.acquire_fixed_log_protocol()
            self.addCleanup(protocol.close)
            for path in self.logs[:-1]:
                path.write_text("log\n", encoding="utf-8")
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.capture_fixed_logs(protocol, self.base / "missing")
            self.assertEqual(raised.exception.status, "FIXED_LOG_MISSING")

        for path in self.logs:
            path.unlink(missing_ok=True)
        self.lock.unlink(missing_ok=True)
        with mock.patch.object(full_gate, "FULL_GATE_LOCK_PATH", self.lock), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ):
            protocol = full_gate.acquire_fixed_log_protocol()
            self.addCleanup(protocol.close)
            for path in self.logs:
                path.write_text("log\n", encoding="utf-8")
            with mock.patch.object(full_gate.os, "rename", side_effect=OSError("race")):
                with self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate.capture_fixed_logs(protocol, self.base / "move-failure")
            self.assertEqual(raised.exception.status, "FIXED_LOG_MOVE_FAILED")

    def test_two_phase_finalization_never_leaves_pass_after_write_fsync_or_close_failure(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "finalize_outputs"),
            "two-phase output finalization is not implemented",
        )
        pass_receipt = full_gate.canonical_json_bytes(
            {"schema": "test", "status": "PASS", "verdict": "PASS"}
        )

        def assert_not_pass(path: Path) -> None:
            if not path.exists() or path.stat().st_size == 0:
                return
            try:
                payload = json.loads(path.read_bytes())
            except json.JSONDecodeError:
                return
            self.assertNotEqual(payload.get("status"), "PASS", payload)
            self.assertNotEqual(payload.get("verdict"), "PASS", payload)

        for failure_kind in ("write", "fsync", "close"):
            with self.subTest(failure_kind=failure_kind):
                receipt = self.base / f"{failure_kind}-receipt.json"
                denial = self.base / f"{failure_kind}-denial.log"
                outputs = full_gate.create_output_files(
                    str(receipt), str(denial), reserved_paths=()
                )
                real_write = os.write
                real_fsync = os.fsync
                real_close = full_gate.HeldOutput.close
                injected = False

                def write_once(descriptor: int, data: object) -> int:
                    nonlocal injected
                    raw = bytes(data)
                    if failure_kind == "write" and not injected and b'"status":"PASS"' in raw:
                        injected = True
                        raise OSError("injected PASS write failure")
                    return real_write(descriptor, raw)

                def fsync_once(descriptor: int) -> None:
                    nonlocal injected
                    current = os.pread(descriptor, 1024, 0)
                    if (
                        failure_kind == "fsync"
                        and not injected
                        and descriptor == outputs.receipt.descriptor
                        and b'"status":"PASS"' in current
                    ):
                        injected = True
                        raise OSError("injected PASS fsync failure")
                    real_fsync(descriptor)

                def close_once(output: full_gate.HeldOutput) -> None:
                    nonlocal injected
                    if (
                        failure_kind == "close"
                        and not injected
                        and output is outputs.receipt
                        and b'"status":"PASS"' in os.pread(output.descriptor, 1024, 0)
                    ):
                        injected = True
                        raise full_gate.FullGateError("OUTPUT_CLOSE_FAILED")
                    real_close(output)

                with mock.patch.object(full_gate.os, "write", side_effect=write_once), mock.patch.object(
                    full_gate.os, "fsync", side_effect=fsync_once
                ), mock.patch.object(full_gate.HeldOutput, "close", autospec=True, side_effect=close_once):
                    with self.assertRaises(full_gate.FullGateError) as raised:
                        full_gate.finalize_outputs(
                            outputs,
                            denial_bytes=b"diagnostic\n",
                            receipt_bytes=pass_receipt,
                            nonce="a" * 64,
                        )
                self.assertTrue(injected)
                self.assertEqual(raised.exception.status, "OUTPUT_FINALIZATION_FAILED")
                assert_not_pass(receipt)

    def test_finalization_invalidates_pass_after_pre_close_base_exception(
        self,
    ) -> None:
        outputs = full_gate.create_output_files(
            str(self.receipt), str(self.denial), reserved_paths=()
        )
        pass_receipt = full_gate.canonical_json_bytes(
            {"schema": "test", "status": "PASS", "verdict": "PASS"}
        )
        receipt_descriptor = outputs.receipt.descriptor
        denial_descriptor = outputs.denial_log.descriptor
        real_close = os.close
        injected = False
        close_calls = 0

        def interrupt_receipt_close(descriptor: int) -> None:
            nonlocal injected, close_calls
            close_calls += 1
            if (
                descriptor == receipt_descriptor
                and not injected
                and b'"status":"PASS"' in os.pread(descriptor, 1024, 0)
            ):
                injected = True
                raise KeyboardInterrupt("injected pre-close interrupt")
            real_close(descriptor)

        with mock.patch.object(
            full_gate.os,
            "close",
            side_effect=interrupt_receipt_close,
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.finalize_outputs(
                outputs,
                denial_bytes=b"diagnostic\n",
                receipt_bytes=pass_receipt,
                nonce="a" * 64,
            )

        self.assertTrue(injected)
        self.assertGreaterEqual(close_calls, 3)
        self.assertEqual(raised.exception.status, "OUTPUT_FINALIZATION_FAILED")
        self.assertEqual(raised.exception.primary_status, "OUTPUT_CLOSE_FAILED")
        self.assertTrue(outputs.closed)
        self.assertTrue(outputs.receipt.closed)
        self.assertTrue(outputs.denial_log.closed)
        payload = json.loads(self.receipt.read_bytes())
        self.assertNotEqual(payload.get("status"), "PASS")
        self.assertNotEqual(payload.get("verdict"), "PASS")
        for descriptor in (receipt_descriptor, denial_descriptor):
            with self.assertRaises(OSError):
                os.fstat(descriptor)


class FullGateExecutionAndReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-execution-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.sandbox_executable = self.base / "sandbox-exec"
        self.sandbox_executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.sandbox_executable.chmod(0o555)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def semantic_fixture(self) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        stdout = (
            b"  \xe2\x9c\x93 pytest: 123 passed\n"
            b"  \xe2\x9c\x93 server imports clean (203 tools)\n"
            b"  \xe2\x9c\x93 all mcp__samvil_mcp__ refs resolve (203 registered / 134 cited)\n"
            b"  ! UNTESTED: 4 host execution surface(s); see scripts/check-host-parity.py\n"
            b"\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90 pre-commit check: PASS \xe2\x95\x90\xe2\x95\x90\xe2\x95\x90\n"
        )
        logs = {
            "samvil-pretest.log": b"123 passed in 1.23s\n",
            "samvil-mdrefs.log": b"  \xe2\x9c\x93 all markdown references resolve (127 files scanned)\n",
            "samvil-hostparity.log": b"UNTESTED: 3 pairs\nUNTESTED: codex native\n",
            "samvil-forward.log": (
                b"  Registered @mcp.tool() functions: 203\n"
                b"  Distinct tool refs in skill files: 134\n"
            ),
            "samvil-agent-inventory.log": (
                b"Agent inventory consistent: 41 persona files, 2 inline identities\n"
            ),
        }
        counters = {
            "pytest_passed": 123,
            "mcp_tools": 203,
            "markdown_references": 127,
            "host_untested": 4,
            "forward_registered_tools": 203,
            "forward_cited_tools": 134,
            "agent_inventory_entries": 43,
        }
        return stdout, logs, counters

    def execution_evidence(self) -> full_gate.ExecutionEvidence:
        return full_gate.ExecutionEvidence(
            digest="e" * 64,
            import_manifest_sha256="d" * 64,
            facade_roles=("pytest", "server_import"),
            pytest_passed=123,
            mcp_tools=203,
        )

    def test_real_forward_integrity_output_satisfies_gate_contract(self) -> None:
        repository = TOOLS_ROOT.parents[1]
        result = subprocess.run(
            [str(SYSTEM_PYTHON), "scripts/check-skill-forward-integrity.py"],
            cwd=repository,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        registered = re.search(
            rb"^  Registered @mcp\.tool\(\) functions: ([0-9]+)$",
            result.stdout,
            flags=re.MULTILINE,
        )
        cited = re.search(
            rb"^  Distinct tool refs in skill files: ([0-9]+)$",
            result.stdout,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(registered)
        self.assertIsNotNone(cited)
        assert registered is not None and cited is not None
        stdout, logs, counters = self.semantic_fixture()
        logs["samvil-forward.log"] = result.stdout
        counters["forward_registered_tools"] = int(registered.group(1))
        counters["forward_cited_tools"] = int(cited.group(1))
        evidence = dataclasses.replace(
            self.execution_evidence(), mcp_tools=int(registered.group(1))
        )
        outcome = full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=False,
            resource_status=None,
            stdout=stdout,
            stderr=b"",
            wrapper_pid=101,
            wrapper_start_identity="linux-proc-start:1",
        )
        observed = full_gate.validate_gate_outcome(
            outcome,
            logs,
            counters,
            execution_evidence=evidence,
        )
        self.assertEqual(observed, counters)

    def test_forged_pass_and_zero_exit_require_independent_execution_evidence(self) -> None:
        self.assertIn(
            "execution_evidence",
            inspect.signature(full_gate.validate_gate_outcome).parameters,
            "gate validation does not require runner-observed execution evidence",
        )
        stdout, logs, counters = self.semantic_fixture()
        outcome = full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=False,
            resource_status=None,
            stdout=stdout,
            stderr=b"",
            wrapper_pid=101,
            wrapper_start_identity="linux-proc-start:1",
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_gate_outcome(
                outcome,
                logs,
                counters,
                execution_evidence=None,
            )
        self.assertEqual(raised.exception.status, "EXECUTION_EVIDENCE_MISSING")

    def test_nominal_completion_cleanup_requirement_is_never_pass(self) -> None:
        stdout, logs, counters = self.semantic_fixture()
        outcome = full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=True,
            resource_status=None,
            stdout=stdout,
            stderr=b"",
            wrapper_pid=101,
            wrapper_start_identity="linux-proc-start:1",
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_gate_outcome(
                outcome,
                logs,
                counters,
                execution_evidence=self.execution_evidence(),
            )
        self.assertEqual(
            raised.exception.status, "GATE_DESCENDANT_CLEANUP_REQUIRED"
        )

    def test_runtime_facade_and_authority_frames_are_recomputed_after_execution(self) -> None:
        self.assertIn(
            "expected_execution_digest",
            inspect.signature(full_gate.observe_execution_evidence).parameters,
            "post-execution evidence is not bound to a pre-execution observation",
        )
        manifest, pack, _files = FullGateGitObjectPackTest().fixture("original")
        validated = full_gate.validate_manifest_object(manifest)
        verified = full_gate.verify_git_object_pack(validated, pack)
        snapshot = self.base / "snapshot"
        full_gate.materialize_verified_snapshot(verified, snapshot)
        runtime = self.base / "runtime"
        (runtime / "bin").mkdir(parents=True)
        runtime_python = runtime / "bin/python3.12"
        runtime_python.write_bytes(b"#!/bin/sh\nexit 0\n")
        runtime_python.chmod(0o755)
        facade = {
            "schema": "samvil.full-gate-facade.v1",
            "entries": [
                {
                    "path": path,
                    "mode": "100644" if path == full_gate.FACADE_PATHS[3] else "100755",
                    "content_base64": base64.b64encode(
                        full_gate.FACADE_PYVENV_CONFIG
                        if path == full_gate.FACADE_PATHS[3]
                        else full_gate.FACADE_PYTHON_WRAPPER
                    ).decode("ascii"),
                    "sha256": sha256(
                        full_gate.FACADE_PYVENV_CONFIG
                        if path == full_gate.FACADE_PATHS[3]
                        else full_gate.FACADE_PYTHON_WRAPPER
                    ),
                }
                for path in full_gate.FACADE_PATHS
            ],
        }
        facade_digest = full_gate.materialize_facade(
            full_gate.canonical_json_bytes(facade), snapshot, self.base
        )
        for root in (snapshot, runtime):
            full_gate.make_tree_readonly(root)
        expected = full_gate.measure_materialized_execution(
            snapshot, runtime, facade_digest
        )
        frames = tuple(
            {
                "schema": "samvil.full-gate-authority-frame.v1",
                "nonce": "a" * 64,
                "sequence": index,
                "phase": phase,
                "status": "PASS",
                "evidence": (
                    {"pytest_passed": 1}
                    if phase == "pytest"
                    else {"tool_count": 1}
                    if phase == "server_import"
                    else {}
                ),
            }
            for index, phase in enumerate(full_gate.AUTHORITY_PHASES)
        )
        evidence = full_gate.observe_execution_evidence(
            validated,
            verified,
            snapshot,
            runtime,
            facade_digest,
            frames,
            expected_execution_digest=expected,
        )
        self.assertEqual(evidence.import_manifest_sha256, manifest["import_manifest"]["sha256"])

        os.chmod(runtime_python, 0o755)
        runtime_python.write_bytes(b"#!/bin/sh\nexit 7\n")
        runtime_python.chmod(0o555)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.observe_execution_evidence(
                validated,
                verified,
                snapshot,
                runtime,
                facade_digest,
                frames,
                expected_execution_digest=expected,
            )
        self.assertEqual(raised.exception.status, "EXECUTION_EVIDENCE_CHANGED")

    def test_semantic_counters_and_nonzero_exit_ignore_forged_pass_authority(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "validate_gate_outcome"),
            "trusted gate outcome validation is not implemented",
        )
        stdout, logs, counters = self.semantic_fixture()
        outcome = full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=False,
            resource_status=None,
            stdout=stdout,
            stderr=b"",
            wrapper_pid=101,
            wrapper_start_identity="linux-proc-start:1",
        )
        self.assertEqual(
            full_gate.validate_gate_outcome(
                outcome,
                logs,
                counters,
                execution_evidence=self.execution_evidence(),
            ),
            counters,
        )

        forged = dataclasses.replace(outcome, returncode=1, stdout=b"PASS\n" + stdout)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_gate_outcome(
                forged,
                logs,
                counters,
                execution_evidence=self.execution_evidence(),
            )
        self.assertEqual(raised.exception.status, "GATE_EXIT_NONZERO")

        altered = dict(counters, pytest_passed=124)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.validate_gate_outcome(
                outcome,
                logs,
                altered,
                execution_evidence=self.execution_evidence(),
            )
        self.assertEqual(raised.exception.status, "SEMANTIC_COUNTER_MISMATCH")

    def test_sandbox_argv_is_one_fixed_command_and_receipt_is_deterministic_path_free(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "build_sandbox_argv"),
            "fixed sandbox command construction is not implemented",
        )
        invocation = self.base / "invocation"
        snapshot = invocation / "snapshot"
        runtime = invocation / "runtime"
        dependencies = invocation / "dependencies"
        tools = invocation / "tools"
        scratch = invocation / "scratch"
        for path in (snapshot, runtime / "bin", dependencies, tools / "bin", scratch):
            path.mkdir(parents=True, exist_ok=True)
        wrapper, _binding = full_gate.materialize_trusted_wrapper(
            invocation, full_gate.trusted_wrapper_binding()
        )
        contract = invocation / "control/contract.json"
        contract.write_bytes(b"{}")
        environment = {"A": "1", "B": "2"}
        argv = full_gate.build_sandbox_argv(
            b"(version 1)\n(deny default)\n",
            snapshot,
            runtime,
            dependencies,
            tools,
            wrapper,
            contract,
            "a" * 64,
            scratch,
            environment,
            sandbox_executable=self.sandbox_executable,
            authority_fd=17,
            nonce="b" * 64,
        )
        self.assertEqual(argv[0], str(self.sandbox_executable))
        self.assertEqual(argv.count(str(self.sandbox_executable)), 1)
        self.assertEqual(argv[0], str(self.sandbox_executable))
        self.assertEqual(argv[1], "-p")
        self.assertNotIn("/usr/bin/env", argv)
        self.assertNotIn("-i", argv)
        self.assertEqual(argv[3], str(runtime / "bin/python3.12"))
        self.assertFalse(any(item.startswith(("A=", "B=")) for item in argv))
        self.assertEqual(argv[-1], str(scratch))
        self.assertIn(str(runtime / "bin/python3.12"), argv)
        self.assertIn(str(wrapper), argv)
        self.assertNotIn("scripts/pre-commit-check.sh", argv)

        manifest = full_gate.validate_manifest_object(
            FullGateManifestProtocolTest().manifest("candidate_precommit")
        )
        _stdout, _logs, counters = self.semantic_fixture()
        digests = full_gate.ReceiptDigests(
            command="1" * 64,
            content="2" * 64,
            profile="3" * 64,
            imports=manifest.raw["import_manifest"]["sha256"],
            identity="4" * 64,
            tree="5" * 64,
            runtime="6" * 64,
        )
        quota_authority = quota_authority_fixture()
        first = full_gate.build_pass_receipt(
            manifest,
            counters,
            digests,
            storage_quota_authority=quota_authority,
        )
        second = full_gate.build_pass_receipt(
            manifest,
            counters,
            digests,
            storage_quota_authority=quota_authority,
        )
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(
            payload["promotion_limitations"],
            [
                "LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED",
                "DETACHED_DESCENDANT_NOT_OS_ISOLATED",
            ],
        )
        self.assertEqual(
            payload["storage_quota_evidence_sha256"],
            quota_authority.evidence_sha256,
        )
        self.assertNotIn("path", first.decode("utf-8").lower())
        self.assertNotIn("stdout", payload)
        self.assertNotIn("stderr", payload)
        self.assertNotIn("attempt", first.decode("utf-8").lower())
        self.assertNotIn("exact_port", first.decode("utf-8").lower())

    def test_pass_receipt_requires_verified_storage_quota_authority(self) -> None:
        manifest = full_gate.validate_manifest_object(
            FullGateManifestProtocolTest().manifest("candidate_precommit")
        )
        _stdout, _logs, counters = self.semantic_fixture()
        digests = full_gate.ReceiptDigests(
            command="1" * 64,
            content="2" * 64,
            profile="3" * 64,
            imports=manifest.raw["import_manifest"]["sha256"],
            identity="4" * 64,
            tree="5" * 64,
            runtime="6" * 64,
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.build_pass_receipt(manifest, counters, digests)
        self.assertEqual(
            raised.exception.status,
            full_gate.INVOCATION_STORAGE_QUOTA_BLOCKER,
        )

        authority = quota_authority_fixture()
        forged = dataclasses.replace(authority, evidence_sha256="0" * 64)
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.build_pass_receipt(
                manifest,
                counters,
                digests,
                storage_quota_authority=forged,
            )
        self.assertEqual(
            raised.exception.status,
            full_gate.INVOCATION_STORAGE_QUOTA_BLOCKER,
        )

    def test_timeout_supervision_kills_the_process_group(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "supervise_process"),
            "bounded child supervision is not implemented",
        )
        stdout = self.base / "stdout.capture"
        stderr = self.base / "stderr.capture"
        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            process = subprocess.Popen(
                ["/bin/sh", "-c", "sleep 30 & wait"],
                cwd=self.base,
                env={"PATH": "/usr/bin:/bin"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            outcome = full_gate.supervise_process(
                process,
                timeout=0.1,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                invocation_root=self.base,
            )
        self.assertTrue(outcome.timed_out)
        self.assertTrue(outcome.cleanup_performed)
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)

    def test_process_inventory_failure_still_terminates_the_process_group(self) -> None:
        stdout = self.base / "inventory-failure.stdout"
        stderr = self.base / "inventory-failure.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            process = subprocess.Popen(
                ["/bin/sh", "-c", "sleep 30 & wait"],
                cwd=self.base,
                env={"PATH": "/usr/bin:/bin"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            real_terminate = full_gate._terminate_process_group
            try:
                with mock.patch.object(
                    full_gate,
                    "_process_snapshot",
                    side_effect=full_gate.FullGateError("PROCESS_INVENTORY_FAILED"),
                ), mock.patch.object(
                    full_gate,
                    "_terminate_process_group",
                    wraps=real_terminate,
                ) as terminate, self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate.supervise_process(
                        process,
                        timeout=5,
                        stdout_handle=stdout_handle,
                        stderr_handle=stderr_handle,
                    )
                self.assertEqual(raised.exception.status, "PROCESS_INVENTORY_FAILED")
                self.assertGreaterEqual(terminate.call_count, 1)
            finally:
                if process.poll() is None:
                    real_terminate(process.pid)
                process.wait(timeout=2)
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)

    def test_linux_group_inventory_distinguishes_live_members_from_zombies(self) -> None:
        live = subprocess.CompletedProcess(
            args=(), returncode=0, stdout=b"4201 4242 S 1\n", stderr=b""
        )
        zombie = subprocess.CompletedProcess(
            args=(), returncode=0, stdout=b"4201 4242 Z 1\n", stderr=b""
        )
        with mock.patch.object(
            full_gate.subprocess, "run", side_effect=(live, zombie)
        ):
            self.assertIsNone(full_gate._linux_quiescent_process_group_snapshot(4242))
            self.assertEqual(
                full_gate._linux_quiescent_process_group_snapshot(4242),
                (4201,),
            )

    def test_linux_group_inventory_uses_nlwp_for_zombie_leader_workers(self) -> None:
        zombie_leader_with_worker = subprocess.CompletedProcess(
            args=(), returncode=0, stdout=b"4201 4242 Z 2\n", stderr=b""
        )
        with mock.patch.object(
            full_gate.subprocess, "run", return_value=zombie_leader_with_worker
        ) as run:
            self.assertIsNone(full_gate._linux_quiescent_process_group_snapshot(4242))

        self.assertEqual(
            run.call_args.args[0],
            ["/bin/ps", "-axo", "pid=,pgid=,stat=,nlwp="],
        )

    def test_linux_group_cleanup_requires_sigkill_before_accepting_zombies(self) -> None:
        pgid = 4242
        zombie = subprocess.CompletedProcess(
            args=(), returncode=0, stdout=b"4201 4242 Z 1\n", stderr=b""
        )
        observed_signals: list[int] = []

        def observe_signal(_pgid: int, sig: int) -> None:
            self.assertEqual(_pgid, pgid)
            observed_signals.append(sig)

        with mock.patch.object(
            full_gate.sys, "platform", "linux"
        ), mock.patch.object(
            full_gate.subprocess, "run", return_value=zombie
        ) as inventory, mock.patch.object(
            full_gate.os, "killpg", side_effect=observe_signal
        ), mock.patch.object(
            full_gate.time,
            "monotonic",
            side_effect=(0.0, 0.1, 0.3, 0.3, 0.4, 0.5),
        ), mock.patch.object(full_gate.time, "sleep"):
            cleaned = full_gate._terminate_process_group(pgid)

        self.assertTrue(cleaned)
        self.assertEqual(inventory.call_count, 2)
        self.assertEqual(
            observed_signals,
            [
                signal.SIGTERM,
                0,
                signal.SIGKILL,
                0,
                signal.SIGKILL,
                0,
                0,
            ],
        )

    def test_linux_group_cleanup_rejects_zombie_then_live_snapshot(self) -> None:
        snapshots = (
            subprocess.CompletedProcess(
                args=(), returncode=0, stdout=b"4201 4242 Z 1\n", stderr=b""
            ),
            subprocess.CompletedProcess(
                args=(), returncode=0, stdout=b"4201 4242 S 1\n", stderr=b""
            ),
        )
        with mock.patch.object(
            full_gate.sys, "platform", "linux"
        ), mock.patch.object(
            full_gate.subprocess, "run", side_effect=snapshots
        ), mock.patch.object(
            full_gate.os, "killpg"
        ), mock.patch.object(
            full_gate.time,
            "monotonic",
            side_effect=(0.0, 0.3, 0.3, 0.4, 0.5, 1.4),
        ), mock.patch.object(full_gate.time, "sleep"), self.assertRaises(
            full_gate.FullGateError
        ) as raised:
            full_gate._terminate_process_group(4242)

        self.assertEqual(raised.exception.status, "CHILD_CLEANUP_FAILED")

    def test_linux_group_cleanup_requires_stable_target_pid_set(self) -> None:
        snapshots = tuple(
            subprocess.CompletedProcess(
                args=(), returncode=0, stdout=payload, stderr=b""
            )
            for payload in (
                b"4201 4242 Z 1\n",
                b"4202 4242 Z 1\n",
                b"4202 4242 Z 1\n",
            )
        )
        with mock.patch.object(
            full_gate.sys, "platform", "linux"
        ), mock.patch.object(
            full_gate.subprocess, "run", side_effect=snapshots
        ) as inventory, mock.patch.object(
            full_gate.os, "killpg"
        ), mock.patch.object(
            full_gate.time,
            "monotonic",
            side_effect=(0.0, 0.3, 0.3, 0.4, 0.5, 0.6),
        ), mock.patch.object(full_gate.time, "sleep"):
            cleaned = full_gate._terminate_process_group(4242)

        self.assertTrue(cleaned)
        self.assertEqual(inventory.call_count, 3)

    def test_process_group_probe_permission_error_fails_closed(self) -> None:
        cases = (
            ("term", (0.0, 0.1), [signal.SIGTERM, 0]),
            ("kill", (0.0, 0.3, 0.3, 0.4), [signal.SIGTERM, signal.SIGKILL, 0]),
        )
        for phase, monotonic_values, expected_signals in cases:
            observed_signals: list[int] = []

            def reject_probe(_pgid: int, sig: int) -> None:
                self.assertEqual(_pgid, 4242)
                observed_signals.append(sig)
                if sig == 0:
                    raise PermissionError

            with self.subTest(phase=phase):
                with mock.patch.object(
                    full_gate.os,
                    "killpg",
                    side_effect=reject_probe,
                ), mock.patch.object(
                    full_gate.sys,
                    "platform",
                    "linux",
                ), mock.patch.object(
                    full_gate.time,
                    "monotonic",
                    side_effect=monotonic_values,
                ), mock.patch.object(
                    full_gate.time,
                    "sleep",
                ), self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate._terminate_process_group(4242)

                self.assertEqual(raised.exception.status, "CHILD_CLEANUP_FAILED")
                self.assertEqual(observed_signals, expected_signals)

    def test_linux_group_inventory_omission_remains_fail_closed(self) -> None:
        empty = subprocess.CompletedProcess(
            args=(), returncode=0, stdout=b"", stderr=b""
        )
        with mock.patch.object(
            full_gate.subprocess, "run", return_value=empty
        ):
            self.assertIsNone(full_gate._linux_quiescent_process_group_snapshot(4242))

    def test_linux_group_inventory_rejects_malformed_or_duplicate_rows(self) -> None:
        payloads = (
            b"4201 4242 Z\n",
            b"4201 4242 Z 0\n",
            b"4201 4242 Z nope\n",
            b"4201 4242 Z 1\n4202 nope S 1\n",
            b"4201 4242 Z 1\n4201 4243 Z 1\n",
        )
        for payload in payloads:
            with self.subTest(payload=payload), mock.patch.object(
                full_gate.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=(), returncode=0, stdout=payload, stderr=b""
                ),
            ), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate._linux_quiescent_process_group_snapshot(4242)
            self.assertEqual(raised.exception.status, "CHILD_CLEANUP_FAILED")

    def test_process_snapshot_binds_ps_rows_to_strong_native_birth_identity(
        self,
    ) -> None:
        ps_result = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout=b"101 10 3 4\n102 20 5 6\n103 30 7 8\n",
            stderr=b"",
        )
        identities = {
            101: (10, "darwin-proc-start:100:7"),
            102: (999, "darwin-proc-start:101:8"),
            103: None,
        }
        with mock.patch.object(
            full_gate.subprocess, "run", return_value=ps_result
        ) as run, mock.patch.object(
            full_gate,
            "_process_birth_identity",
            side_effect=lambda pid: identities[pid],
        ):
            table = full_gate._process_snapshot()

        self.assertEqual(
            table,
            {
                101: (10, 3 * 1024, 4 * 1024, "darwin-proc-start:100:7"),
                102: (
                    20,
                    5 * 1024,
                    6 * 1024,
                    full_gate.PROCESS_IDENTITY_UNAVAILABLE_SENTINEL,
                ),
                103: (
                    30,
                    7 * 1024,
                    8 * 1024,
                    full_gate.PROCESS_IDENTITY_UNAVAILABLE_SENTINEL,
                ),
            },
        )
        self.assertNotIn("lstart=", run.call_args.args[0])

    def test_live_wrapper_missing_or_weak_birth_identity_fails_closed(self) -> None:
        class RunningProcess:
            pid = 999_974
            returncode = -signal.SIGTERM

            def poll(self) -> None:
                return None

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        stdout = self.base / "missing-birth.stdout"
        stderr = self.base / "missing-birth.stderr"
        for name, table in (
            ("missing", {}),
            ("weak", {RunningProcess.pid: (1, 0, 0, "second-resolution")}),
        ):
            with self.subTest(name=name), stdout.open("w+b") as stdout_handle, stderr.open(
                "w+b"
            ) as stderr_handle, mock.patch.object(
                full_gate, "_process_snapshot", return_value=table
            ), mock.patch.object(
                full_gate, "_terminate_process_group", return_value=True
            ) as terminate, self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.supervise_process(
                    RunningProcess(),
                    timeout=1,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                )
            self.assertEqual(raised.exception.status, "PROCESS_INVENTORY_FAILED")
            terminate.assert_called()

    def test_gate_outcome_cannot_pass_without_strong_wrapper_identity(self) -> None:
        for name, wrapper_pid, identity in (
            ("missing", None, None),
            ("weak", 101, "second-resolution"),
        ):
            with self.subTest(name=name), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate.validate_gate_process_outcome(
                    full_gate.GateOutcome(
                        returncode=0,
                        timed_out=False,
                        cleanup_performed=False,
                        resource_status=None,
                        stdout=b"",
                        stderr=b"",
                        wrapper_pid=wrapper_pid,
                        wrapper_start_identity=identity,
                    )
                )
            self.assertEqual(raised.exception.status, "PROCESS_INVENTORY_FAILED")

    def test_descendant_with_unavailable_birth_identity_blocks_before_inspection(
        self,
    ) -> None:
        class RunningProcess:
            pid = 999_973
            returncode = -signal.SIGTERM

            def poll(self) -> None:
                return None

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        table = {
            RunningProcess.pid: (1, 0, 0, "linux-proc-start:1"),
            999_972: (
                RunningProcess.pid,
                0,
                0,
                full_gate.PROCESS_IDENTITY_UNAVAILABLE_SENTINEL,
            ),
        }
        stdout = self.base / "missing-descendant-birth.stdout"
        stderr = self.base / "missing-descendant-birth.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate, "_process_snapshot", return_value=table
        ), mock.patch.object(
            full_gate, "_terminate_process_group", return_value=True
        ) as terminate, mock.patch.object(
            full_gate, "_inspect_open_regular_files"
        ) as inspect_open:
            outcome = full_gate.supervise_process(
                RunningProcess(),
                timeout=1,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                invocation_root=self.base,
            )

        self.assertEqual(outcome.resource_status, "PROCESS_INVENTORY_FAILED")
        terminate.assert_called()
        inspect_open.assert_not_called()

    def test_detached_signal_refuses_weak_or_non_atomic_identity(self) -> None:
        identity = "darwin-proc-start:100:7"
        alive = {101: (1, 0, 0, identity)}
        for name, identities in (
            ("weak_identity", ((101, "Mon Jan 1 00:00:00 2026"),)),
            ("darwin_has_no_atomic_pid_handle", ((101, identity),)),
        ):
            with self.subTest(name=name), mock.patch.object(
                full_gate, "_process_snapshot", return_value=alive
            ), mock.patch.object(
                full_gate.sys, "platform", "darwin"
            ), mock.patch.object(
                full_gate.os, "kill"
            ) as raw_kill, self.assertRaises(full_gate.FullGateError) as raised:
                full_gate._kill_tracked_descendants(identities)
            self.assertEqual(
                raised.exception.status,
                full_gate.DETACHED_PROCESS_SIGNAL_UNAVAILABLE,
            )
            raw_kill.assert_not_called()

    def test_linux_detached_signal_uses_identity_bound_pidfd_only(self) -> None:
        identity = "linux-proc-start:123456"
        alive = {101: (1, 0, 0, identity)}
        with mock.patch.object(
            full_gate.sys, "platform", "linux"
        ), mock.patch.object(
            full_gate, "_process_snapshot", side_effect=(alive, {})
        ), mock.patch.object(
            full_gate,
            "_process_birth_identity",
            side_effect=((1, identity), (1, identity)),
        ), mock.patch.object(
            full_gate.os, "pidfd_open", create=True, return_value=700
        ) as pidfd_open, mock.patch.object(
            full_gate.signal, "pidfd_send_signal", create=True
        ) as pidfd_signal, mock.patch.object(
            full_gate, "_close_raw_descriptor_with_retry", return_value=None
        ) as close_descriptor, mock.patch.object(
            full_gate.os, "kill"
        ) as raw_kill:
            cleaned = full_gate._kill_tracked_descendants(((101, identity),))

        self.assertTrue(cleaned)
        pidfd_open.assert_called_once_with(101, 0)
        pidfd_signal.assert_called_once_with(700, signal.SIGTERM, None, 0)
        close_descriptor.assert_called_once_with(700)
        raw_kill.assert_not_called()

    def test_pidfd_open_identity_drift_closes_handle_without_signaling(self) -> None:
        expected = "linux-proc-start:123456"
        replacement = "linux-proc-start:123457"
        with mock.patch.object(
            full_gate.sys, "platform", "linux"
        ), mock.patch.object(
            full_gate,
            "_process_birth_identity",
            side_effect=((1, expected), (1, replacement)),
        ), mock.patch.object(
            full_gate.os, "pidfd_open", create=True, return_value=700
        ), mock.patch.object(
            full_gate.signal, "pidfd_send_signal", create=True
        ) as pidfd_signal, mock.patch.object(
            full_gate, "_close_raw_descriptor_with_retry", return_value=None
        ) as close_descriptor:
            descriptor = full_gate._open_identity_bound_pidfd(101, expected)

        self.assertIsNone(descriptor)
        close_descriptor.assert_called_once_with(700)
        pidfd_signal.assert_not_called()

    def test_authority_final_drain_requires_eof_and_rejects_leaked_writer(
        self,
    ) -> None:
        self.assertTrue(
            hasattr(full_gate, "_drain_authority_pipe_to_eof"),
            "post-wrapper authority EOF verification is not implemented",
        )
        authority = bytearray()
        with mock.patch.object(
            full_gate.os,
            "read",
            side_effect=(
                b"buffered-frame",
                BlockingIOError(errno.EAGAIN, "writer still open"),
                BlockingIOError(errno.EAGAIN, "writer still open"),
            ),
        ), mock.patch.object(
            full_gate.time,
            "monotonic",
            side_effect=(0.0, 0.1, 0.3),
        ), mock.patch.object(
            full_gate.time,
            "sleep",
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate._drain_authority_pipe_to_eof(
                701,
                authority,
                max_bytes=1024,
                timeout=0.25,
            )
        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_WRITER_LEAK")
        self.assertEqual(authority, b"buffered-frame")

        authority = bytearray()
        with mock.patch.object(
            full_gate.os,
            "read",
            side_effect=(b"buffered-frame", b""),
        ):
            full_gate._drain_authority_pipe_to_eof(
                701,
                authority,
                max_bytes=1024,
                timeout=0.25,
            )
        self.assertEqual(authority, b"buffered-frame")
        supervision_source = inspect.getsource(full_gate.supervise_process)
        self.assertIn("_drain_authority_pipe_to_eof", supervision_source)
        self.assertIn("writer_leak_observed", supervision_source)
        self.assertIn("post_exit_bytes=", supervision_source)

    def test_supervision_sticky_rejects_writer_open_at_wrapper_exit(self) -> None:
        class FinishedProcess:
            pid = 999_980
            returncode = 0

            def poll(self) -> int:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        stdout = self.base / "authority-leak.stdout"
        stderr = self.base / "authority-leak.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate.fcntl, "fcntl", return_value=0
        ), mock.patch.object(
            full_gate, "_process_snapshot", return_value={}
        ), mock.patch.object(
            full_gate, "_terminate_process_group", return_value=False
        ), mock.patch.object(
            full_gate.os,
            "read",
            side_effect=(
                BlockingIOError(errno.EAGAIN, "writer open at exit"),
                b"",
            ),
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.supervise_process(
                FinishedProcess(),
                timeout=1,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                authority_read_fd=701,
                nonce="a" * 64,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            )
        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_WRITER_LEAK")

    def test_supervision_accepts_buffered_final_transcript_followed_by_eof(
        self,
    ) -> None:
        class FinishedProcess:
            pid = 999_979
            returncode = 0

            def poll(self) -> int:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        transcript = FullGateAuthorityFrameProtocolTest().transcript()
        stdout = self.base / "authority-buffered.stdout"
        stderr = self.base / "authority-buffered.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate.fcntl, "fcntl", return_value=0
        ), mock.patch.object(
            full_gate, "_process_snapshot", return_value={}
        ), mock.patch.object(
            full_gate, "_terminate_process_group", return_value=False
        ), mock.patch.object(
            full_gate.os, "read", side_effect=(transcript, b"")
        ):
            outcome = full_gate.supervise_process(
                FinishedProcess(),
                timeout=1,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                authority_read_fd=701,
                nonce="a" * 64,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            )
        self.assertFalse(outcome.cleanup_performed)
        self.assertEqual(
            tuple(frame["phase"] for frame in outcome.authority_frames),
            full_gate.AUTHORITY_PHASES,
        )

    def test_stdout_and_address_space_overflow_are_typed_blockers(self) -> None:
        cases = (
            (
                [str(SYSTEM_PYTHON), "-c", "import sys,time;sys.stdout.write('x'*1048576);sys.stdout.flush();time.sleep(30)"],
                "stdout_bytes",
                1024,
                "GATE_STDOUT_BYTES_EXCEEDED",
            ),
            (
                [str(SYSTEM_PYTHON), "-c", "import time;time.sleep(30)"],
                "address_space_bytes",
                1024,
                "GATE_ADDRESS_SPACE_BYTES_EXCEEDED",
            ),
        )
        for argv, key, value, expected in cases:
            with self.subTest(key=key):
                stdout = self.base / f"{key}.stdout"
                stderr = self.base / f"{key}.stderr"
                limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
                limits[key] = value
                with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
                    process = subprocess.Popen(
                        argv,
                        cwd=self.base,
                        env={"PATH": "/usr/bin:/bin"},
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        start_new_session=True,
                    )
                    outcome = full_gate.supervise_process(
                        process,
                        timeout=5,
                        stdout_handle=stdout_handle,
                        stderr_handle=stderr_handle,
                        limits=limits,
                    )
                self.assertEqual(outcome.resource_status, expected)
                self.assertTrue(outcome.cleanup_performed)

    def test_fast_exit_capture_caps_use_signed_limits_with_stdout_precedence(
        self,
    ) -> None:
        class FinishedProcess:
            pid = 999_978
            returncode = 0

            def poll(self) -> int:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        cases = (
            (b"x" * 2048, b"y" * 2048, "GATE_STDOUT_BYTES_EXCEEDED"),
            (b"", b"y" * 2048, "GATE_STDERR_BYTES_EXCEEDED"),
            (b"x" * 1024, b"", None),
        )
        for index, (stdout_raw, stderr_raw, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
                limits["stdout_bytes"] = 1024
                limits["stderr_bytes"] = 1024
                stdout = self.base / f"fast-exit-{index}.stdout"
                stderr = self.base / f"fast-exit-{index}.stderr"
                with stdout.open("w+b") as stdout_handle, stderr.open(
                    "w+b"
                ) as stderr_handle:
                    stdout_handle.write(stdout_raw)
                    stderr_handle.write(stderr_raw)
                    stdout_handle.flush()
                    stderr_handle.flush()
                    with mock.patch.object(
                        full_gate, "_process_snapshot", return_value={}
                    ), mock.patch.object(
                        full_gate, "_terminate_process_group", return_value=False
                    ):
                        outcome = full_gate.supervise_process(
                            FinishedProcess(),
                            timeout=1,
                            stdout_handle=stdout_handle,
                            stderr_handle=stderr_handle,
                            limits=limits,
                        )
                self.assertEqual(outcome.resource_status, expected)
                self.assertEqual(outcome.stdout, stdout_raw if expected is None else b"")
                self.assertEqual(outcome.stderr, stderr_raw if expected is None else b"")

    def test_setsid_survivor_fails_closed_without_identity_bound_signal(
        self,
    ) -> None:
        class ExitedAfterOneInventory:
            pid = 999_976
            returncode = 0

            def __init__(self) -> None:
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                return None if self.polls == 1 else self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        root_identity = "darwin-proc-start:100:1"
        child_identity = "darwin-proc-start:101:2"
        table = {
            ExitedAfterOneInventory.pid: (1, 0, 0, root_identity),
            999_975: (ExitedAfterOneInventory.pid, 0, 0, child_identity),
        }
        stdout = self.base / "double-fork.stdout"
        stderr = self.base / "double-fork.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate, "_process_snapshot", return_value=table
        ), mock.patch.object(
            full_gate, "_terminate_process_group", return_value=False
        ), mock.patch.object(
            full_gate.sys, "platform", "darwin"
        ), mock.patch.object(
            full_gate.os, "kill"
        ) as raw_kill, self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.supervise_process(
                ExitedAfterOneInventory(),
                timeout=3,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
            )
        self.assertEqual(
            raised.exception.status,
            full_gate.DETACHED_PROCESS_SIGNAL_UNAVAILABLE,
        )
        raw_kill.assert_not_called()

    def test_supervision_prunes_dead_descendant_churn_from_retained_state(
        self,
    ) -> None:
        class ChurningProcess:
            pid = 999_977
            returncode = 0

            def __init__(self) -> None:
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                return None if self.polls <= 500 else self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        snapshots = 0

        def churning_snapshot() -> dict[int, tuple[int, int, int, str]]:
            nonlocal snapshots
            snapshots += 1
            child_pid = 100_000 + snapshots
            return {
                ChurningProcess.pid: (1, 1, 1, "linux-proc-start:1"),
                child_pid: (
                    ChurningProcess.pid,
                    1,
                    1,
                    f"linux-proc-start:{1_000 + snapshots}",
                ),
            }

        stdout = self.base / "descendant-churn.stdout"
        stderr = self.base / "descendant-churn.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate, "_process_snapshot", side_effect=churning_snapshot
        ), mock.patch.object(
            full_gate, "_terminate_process_group", return_value=False
        ), mock.patch.object(
            full_gate, "_kill_tracked_descendants", return_value=False
        ), mock.patch.object(
            full_gate.time, "sleep"
        ):
            outcome = full_gate.supervise_process(
                ChurningProcess(),
                timeout=30,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            )

        self.assertGreater(snapshots, 500)
        self.assertLessEqual(len(outcome.observed_descendants), 1)

    def test_invocation_per_file_and_aggregate_byte_overflow_are_typed(self) -> None:
        root = self.base / "usage"
        root.mkdir()
        (root / "one").write_bytes(b"a" * 8)
        (root / "two").write_bytes(b"b" * 8)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["per_file_bytes"] = 4
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)
        self.assertEqual(raised.exception.status, "GATE_PER_FILE_BYTES_EXCEEDED")
        limits["per_file_bytes"] = 16
        limits["file_size_bytes"] = 8
        limits["nofile"] = 1
        limits["aggregate_bytes"] = 12
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)
        self.assertEqual(raised.exception.status, "GATE_AGGREGATE_BYTES_EXCEEDED")

    def test_invocation_entry_limit_streams_and_stops_before_third_stat(self) -> None:
        root = self.base / "entry-limit"
        root.mkdir()
        for name in ("one", "two", "three", "four"):
            (root / name).write_bytes(b"")
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        self.assertEqual(limits["invocation_entries"], 20_000)
        self.assertEqual(limits["invocation_depth"], 32)
        limits["invocation_entries"] = 2
        limits["invocation_depth"] = 2
        real_scandir = full_gate.os.scandir
        real_stat = full_gate.os.stat
        yielded = 0
        entry_stats = 0

        class CountingScandir:
            def __init__(self, descriptor: int) -> None:
                self._inner = real_scandir(descriptor)

            def __iter__(self) -> CountingScandir:
                return self

            def __next__(self) -> os.DirEntry[str]:
                nonlocal yielded
                yielded += 1
                return next(self._inner)

            def close(self) -> None:
                self._inner.close()

        def counted_stat(
            path: object,
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            nonlocal entry_stats
            if dir_fd is not None:
                entry_stats += 1
            return real_stat(
                path,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with mock.patch.object(
            full_gate.os, "scandir", side_effect=CountingScandir
        ), mock.patch.object(
            full_gate.os, "stat", side_effect=counted_stat
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)

        self.assertEqual(
            raised.exception.status, "GATE_INVOCATION_ENTRY_LIMIT_EXCEEDED"
        )
        self.assertEqual(yielded, 3)
        self.assertEqual(entry_stats, 2)

    def test_invocation_usage_counts_directories_and_files(self) -> None:
        root = self.base / "entry-count"
        nested = root / "directory"
        nested.mkdir(parents=True)
        (root / "root-file").write_bytes(b"a")
        (nested / "nested-file").write_bytes(b"b")

        usage = full_gate.scan_invocation_usage(
            root, full_gate.DEFAULT_RESOURCE_LIMITS
        )

        self.assertEqual(usage, {"entries": 3, "bytes": 2})

    def test_invocation_depth_limit_rejects_before_opening_too_deep_child(self) -> None:
        root = self.base / "depth-limit"
        deepest = root / "one" / "two" / "three"
        deepest.mkdir(parents=True)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["invocation_depth"] = 2
        real_open = full_gate.os.open
        opened: list[object] = []

        def tracked_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            opened.append(path)
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(
            full_gate.os, "open", side_effect=tracked_open
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)

        self.assertEqual(
            raised.exception.status, "GATE_INVOCATION_DEPTH_LIMIT_EXCEEDED"
        )
        self.assertNotIn("three", opened)

    def test_streaming_scan_closes_every_frame_and_preserves_primary_on_close_error(
        self,
    ) -> None:
        root = self.base / "scan-close-failure"
        (root / "one" / "two").mkdir(parents=True)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["invocation_entries"] = 1
        limits["invocation_depth"] = 1
        real_open = full_gate.os.open
        real_close = full_gate.os.close
        opened_descriptors: list[int] = []
        close_attempts: dict[int, int] = {}
        injected = False

        def tracked_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            descriptor = (
                real_open(path, flags, mode)
                if dir_fd is None
                else real_open(path, flags, mode, dir_fd=dir_fd)
            )
            if flags & os.O_DIRECTORY:
                opened_descriptors.append(descriptor)
            return descriptor

        def fail_first_directory_close(descriptor: int) -> None:
            nonlocal injected
            if descriptor in opened_descriptors:
                close_attempts[descriptor] = close_attempts.get(descriptor, 0) + 1
                if not injected:
                    injected = True
                    raise OSError(errno.EIO, "injected directory close failure")
            real_close(descriptor)

        with mock.patch.object(
            full_gate.os, "open", side_effect=tracked_open
        ), mock.patch.object(
            full_gate.os, "close", side_effect=fail_first_directory_close
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)

        self.assertEqual(raised.exception.status, "GATE_INVOCATION_ENTRY_INVALID")
        self.assertEqual(
            raised.exception.primary_status,
            "GATE_INVOCATION_ENTRY_LIMIT_EXCEEDED",
        )
        self.assertGreaterEqual(len(opened_descriptors), 2)
        self.assertTrue(injected)
        self.assertIn(2, close_attempts.values())
        for descriptor in opened_descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_streaming_scan_retries_iterator_close_after_base_exception(
        self,
    ) -> None:
        root = self.base / "scan-iterator-close-interrupt"
        (root / "one" / "two").mkdir(parents=True)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["invocation_entries"] = 1
        limits["invocation_depth"] = 1
        real_open = full_gate.os.open
        real_scandir = full_gate.os.scandir
        opened_descriptors: list[int] = []
        wrappers: list[InterruptingScandir] = []
        injected = False

        class InterruptingScandir:
            def __init__(self, descriptor: int) -> None:
                self._inner = real_scandir(descriptor)
                self.close_calls = 0
                self.closed = False
                wrappers.append(self)

            def __iter__(self) -> InterruptingScandir:
                return self

            def __next__(self) -> os.DirEntry[str]:
                return next(self._inner)

            def close(self) -> None:
                nonlocal injected
                self.close_calls += 1
                if not injected:
                    injected = True
                    raise KeyboardInterrupt("injected pre-close interrupt")
                self._inner.close()
                self.closed = True

        def tracked_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            descriptor = (
                real_open(path, flags, mode)
                if dir_fd is None
                else real_open(path, flags, mode, dir_fd=dir_fd)
            )
            if flags & os.O_DIRECTORY:
                opened_descriptors.append(descriptor)
            return descriptor

        with mock.patch.object(
            full_gate.os, "open", side_effect=tracked_open
        ), mock.patch.object(
            full_gate.os, "scandir", side_effect=InterruptingScandir
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_invocation_usage(root, limits)

        self.assertEqual(raised.exception.status, "GATE_INVOCATION_ENTRY_INVALID")
        self.assertEqual(
            raised.exception.primary_status,
            "GATE_INVOCATION_ENTRY_LIMIT_EXCEEDED",
        )
        self.assertTrue(injected)
        self.assertTrue(any(wrapper.close_calls == 2 for wrapper in wrappers))
        self.assertTrue(all(wrapper.closed for wrapper in wrappers))
        for descriptor in opened_descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_resource_manifest_rejects_invalid_entry_and_depth_limits(self) -> None:
        mutations = (
            lambda value: value.pop("invocation_entries"),
            lambda value: value.__setitem__("unexpected_limit", 1),
            lambda value: value.__setitem__("invocation_entries", 0),
            lambda value: value.__setitem__("invocation_depth", 0),
            lambda value: value.__setitem__(
                "invocation_depth", value["invocation_entries"] + 1
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
                mutate(limits)
                with self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate._validated_resource_limits(limits)
                self.assertEqual(
                    raised.exception.status, "RESOURCE_LIMIT_MANIFEST_INVALID"
                )

    def test_resource_manifest_cannot_raise_any_host_hard_cap(self) -> None:
        self.assertEqual(
            full_gate.MAX_RESOURCE_LIMITS,
            full_gate.DEFAULT_RESOURCE_LIMITS,
        )
        for key, cap in full_gate.MAX_RESOURCE_LIMITS.items():
            with self.subTest(key=key):
                limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
                limits[key] = cap + 1
                with self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate._validated_resource_limits(limits)
                self.assertEqual(
                    raised.exception.status, "RESOURCE_LIMIT_MANIFEST_INVALID"
                )

    def test_cli_timeout_is_bounded_by_signed_wall_limit(self) -> None:
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        self.assertEqual(full_gate._bounded_wall_timeout(10, limits), 10.0)
        self.assertEqual(
            full_gate._bounded_wall_timeout(10**9, limits),
            float(limits["wall_seconds"]),
        )
        for invalid in (0, -1, math.inf, math.nan, True):
            with self.subTest(invalid=invalid), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate._bounded_wall_timeout(invalid, limits)
            self.assertEqual(raised.exception.status, "FULL_GATE_USAGE")

    def test_invocation_cleanup_handles_deep_tree_without_recursion(self) -> None:
        root = self.base / "deep-cleanup"
        root.mkdir()
        current = root
        for _index in range(80):
            current = current / "d"
            current.mkdir()
        (current / "leaf").write_bytes(b"x")

        full_gate._remove_invocation_tree(root, "INVOCATION_CLEANUP_FAILED")

        self.assertFalse(root.exists())

    def test_default_limits_fit_static_host_caps(self) -> None:
        limits = full_gate.DEFAULT_RESOURCE_LIMITS
        self.assertEqual(limits["vm_regions"], 65_536)
        self.assertEqual(limits, full_gate.MAX_RESOURCE_LIMITS)

    def test_manifest_rejects_per_process_open_file_budget_gap(self) -> None:
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["aggregate_bytes"] = (
            limits["file_size_bytes"] * limits["nofile"] - 1
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate._validated_resource_limits(limits)
        self.assertEqual(raised.exception.status, "RESOURCE_LIMIT_MANIFEST_INVALID")

    def test_unlinked_read_only_fd_and_mapped_vnodes_are_accounted_once(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "MappedRegularFile"),
            "mapped regular-file inventory is not implemented",
        )
        root = self.base / "mapped-usage"
        root.mkdir()
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 2
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 16
        read_only_unlinked = full_gate.OpenRegularFile(
            device=99,
            inode=1,
            size=8,
            links=0,
            writable=False,
        )
        read_only_linked = full_gate.OpenRegularFile(
            device=99,
            inode=3,
            size=8,
            links=1,
            writable=False,
        )
        mappings = (
            full_gate.MappedRegularFile(
                device=99,
                inode=1,
                size=8,
                links=0,
            ),
            full_gate.MappedRegularFile(
                device=99,
                inode=2,
                size=8,
                links=0,
            ),
        )

        usage = full_gate.scan_live_invocation_usage(
            root,
            (100,),
            limits,
            inspect_open_files=lambda _pid: (
                read_only_unlinked,
                read_only_linked,
            ),
            inspect_mapped_files=lambda _pid, _max_regions: mappings,
        )

        self.assertEqual(
            usage,
            {
                "entries": 2,
                "bytes": 16,
                "open_unlinked_entries": 1,
                "open_unlinked_bytes": 8,
                "mapped_unlinked_entries": 2,
                "mapped_unlinked_bytes": 16,
            },
        )

    def test_mapped_vnodes_enforce_aggregate_and_entry_limits(self) -> None:
        root = self.base / "mapped-overflow"
        root.mkdir()
        records = (
            full_gate.MappedRegularFile(99, 1, 9, 0),
            full_gate.MappedRegularFile(99, 2, 8, 0),
        )
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 2
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 16
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_live_invocation_usage(
                root,
                (100,),
                limits,
                inspect_open_files=lambda _pid: (),
                inspect_mapped_files=lambda _pid, _max_regions: records,
            )
        self.assertEqual(raised.exception.status, "GATE_AGGREGATE_BYTES_EXCEEDED")

        limits["aggregate_bytes"] = 17
        limits["invocation_entries"] = 1
        limits["invocation_depth"] = 1
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_live_invocation_usage(
                root,
                (100,),
                limits,
                inspect_open_files=lambda _pid: (),
                inspect_mapped_files=lambda _pid, _max_regions: records,
            )
        self.assertEqual(
            raised.exception.status, "GATE_INVOCATION_ENTRY_LIMIT_EXCEEDED"
        )

    def test_live_mapping_inventory_shares_one_aggregate_region_budget(self) -> None:
        identities = tuple(
            (100 + index, f"linux-proc-start:{index + 1}")
            for index in range(4)
        )
        observed_caps: list[int] = []

        def inspect_mapped(_pid: int, max_regions: int) -> tuple[object, ...]:
            observed_caps.append(max_regions)
            return ()

        refreshed = {
            pid: (1, 0, 0, start_identity)
            for pid, start_identity in identities
        }
        _open, _mapped, table = full_gate._inspect_identity_live_storage(
            identities,
            inspect_open_files=lambda _pid: (),
            inspect_mapped_files=inspect_mapped,
            max_regions=8,
            process_snapshot=lambda: refreshed,
        )
        self.assertEqual(table, refreshed)
        self.assertEqual(observed_caps, [2, 2, 2, 2])

        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate._inspect_identity_live_storage(
                (
                    *identities,
                    *((200 + index, f"linux-proc-start:{index + 10}") for index in range(5)),
                ),
                inspect_open_files=lambda _pid: (),
                inspect_mapped_files=inspect_mapped,
                max_regions=8,
                process_snapshot=lambda: {},
            )
        self.assertEqual(
            raised.exception.status, "GATE_MAPPED_FILE_INVENTORY_FAILED"
        )

    def test_linux_mapping_inventory_uses_kernel_identity_and_nlink(self) -> None:
        inspect_mappings = getattr(
            full_gate, "_inspect_unlinked_regular_mappings_linux", None
        )
        self.assertTrue(callable(inspect_mappings))
        payload = (
            b"1000-2000 rw-s 00000000 00:2a 123 /tmp/hidden (deleted)\n"
            b"2000-3000 r--p 00000000 00:2a 124 /tmp/literal (deleted)\n"
        )
        metadata = {
            "1000-2000": os.stat_result(
                (stat.S_IFREG | 0o600, 123, os.makedev(0, 0x2A), 0, 0, 0, 8, 0, 0, 0)
            ),
            "2000-3000": os.stat_result(
                (stat.S_IFREG | 0o600, 124, os.makedev(0, 0x2A), 1, 0, 0, 8, 0, 0, 0)
            ),
        }

        observed = inspect_mappings(
            100,
            8,
            read_maps=lambda _path: payload,
            stat_mapping=lambda path: metadata[path.name],
        )

        self.assertEqual(
            observed,
            (full_gate.MappedRegularFile(os.makedev(0, 0x2A), 123, 8, 0),),
        )

    def test_linux_mapping_inventory_rejects_malformed_or_unbounded_maps(self) -> None:
        inspect_mappings = getattr(
            full_gate, "_inspect_unlinked_regular_mappings_linux", None
        )
        self.assertTrue(callable(inspect_mappings))
        for payload, maximum, expected in (
            (b"not-a-proc-map-line\n", 8, "GATE_MAPPED_FILE_INVENTORY_FAILED"),
            (
                b"1000-2000 rw-s 00000000 00:2a 123 /tmp/a (deleted)\n"
                b"2000-3000 rw-s 00000000 00:2a 124 /tmp/b (deleted)\n",
                1,
                "GATE_VM_REGION_LIMIT_EXCEEDED",
            ),
        ):
            with self.subTest(expected=expected), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                inspect_mappings(
                    100,
                    maximum,
                    read_maps=lambda _path, value=payload: value,
                    stat_mapping=lambda _path: os.stat_result(
                        (
                            stat.S_IFREG | 0o600,
                            123,
                            os.makedev(0, 0x2A),
                            0,
                            0,
                            0,
                            8,
                            0,
                            0,
                            0,
                        )
                    ),
                )
            self.assertEqual(raised.exception.status, expected)

    def test_macos_mapping_inventory_uses_region_vnode_identity(self) -> None:
        inspect_mappings = getattr(
            full_gate, "_inspect_unlinked_regular_mappings_macos", None
        )
        self.assertTrue(callable(inspect_mappings))
        calls: list[tuple[int, int]] = []

        def fake_pidinfo(
            pid: int,
            flavor: int,
            address: int,
            buffer: object,
            size: int,
        ) -> int:
            self.assertEqual(pid, 100)
            self.assertEqual(flavor, full_gate.DARWIN_PROC_PIDREGIONPATHINFO)
            self.assertEqual(size, ctypes.sizeof(full_gate._ProcRegionWithPathInfo))
            calls.append((flavor, address))
            if address >= 0x3000:
                return 0
            info = ctypes.cast(
                buffer, ctypes.POINTER(full_gate._ProcRegionWithPathInfo)
            ).contents
            info.prp_prinfo.pri_address = 0x1000 if address == 0 else 0x2000
            info.prp_prinfo.pri_size = 0x1000
            metadata = info.prp_vip.vip_vi.vi_stat
            metadata.vst_mode = stat.S_IFREG | 0o600
            metadata.vst_dev = 99
            metadata.vst_ino = 123 if address == 0 else 124
            metadata.vst_size = 8
            metadata.vst_nlink = 0 if address == 0 else 1
            return ctypes.sizeof(info)

        observed = inspect_mappings(
            100, 8, pidinfo_function=fake_pidinfo
        )

        self.assertEqual(
            observed,
            (full_gate.MappedRegularFile(99, 123, 8, 0),),
        )
        self.assertEqual(calls, [(8, 0), (8, 0x2000), (8, 0x3000)])

    def test_platform_mapping_inventory_observes_raw_mmap_after_unlink_and_close(
        self,
    ) -> None:
        if sys.platform.startswith("linux") and not _strict_opt_in(
            os.environ, ENABLE_REAL_LINUX_PROC_TESTS_ENV
        ):
            self.skipTest(
                "REAL_LINUX_PROC_OPT_IN_REQUIRED: set "
                f"{ENABLE_REAL_LINUX_PROC_TESTS_ENV}=1"
            )
        inspect_mappings = getattr(
            full_gate, "_inspect_unlinked_regular_mappings", None
        )
        self.assertTrue(callable(inspect_mappings))
        libc = ctypes.CDLL(None, use_errno=True)
        mmap_fn = libc.mmap
        mmap_fn.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_longlong,
        ]
        mmap_fn.restype = ctypes.c_void_p
        munmap_fn = libc.munmap
        munmap_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        munmap_fn.restype = ctypes.c_int
        page_size = mmap.PAGESIZE
        mapped: list[int] = []
        expected: set[tuple[int, int]] = set()
        try:
            for index, (protection, flags) in enumerate(
                (
                    (mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_SHARED),
                    (mmap.PROT_READ, mmap.MAP_PRIVATE),
                )
            ):
                path = self.base / f"raw-mapping-{index}"
                descriptor = os.open(
                    path,
                    os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_CLOEXEC,
                    0o600,
                )
                try:
                    os.ftruncate(descriptor, page_size)
                    metadata = os.fstat(descriptor)
                    address = mmap_fn(
                        None,
                        page_size,
                        protection,
                        flags,
                        descriptor,
                        0,
                    )
                    if address == ctypes.c_void_p(-1).value:
                        self.fail(f"raw mmap failed: errno={ctypes.get_errno()}")
                    mapped.append(int(address))
                    expected.add((int(metadata.st_dev), int(metadata.st_ino)))
                    os.unlink(path)
                finally:
                    os.close(descriptor)

            observed = inspect_mappings(
                os.getpid(), full_gate.DEFAULT_RESOURCE_LIMITS["vm_regions"]
            )
            observed_identities = {
                (record.device, record.inode) for record in observed
            }
            self.assertTrue(expected.issubset(observed_identities))
        finally:
            for address in mapped:
                self.assertEqual(munmap_fn(address, page_size), 0)

    def test_supervision_terminates_on_unlinked_mapping_overflow(self) -> None:
        root = self.base / "supervised-mapped-usage"
        root.mkdir()
        stdout = self.base / "mapped-overflow.stdout"
        stderr = self.base / "mapped-overflow.stderr"
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 4
        limits["nofile"] = 2
        limits["per_file_bytes"] = 8
        limits["aggregate_bytes"] = 8
        records = (
            full_gate.MappedRegularFile(99, 1, 5, 0),
            full_gate.MappedRegularFile(99, 2, 5, 0),
        )
        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            process = subprocess.Popen(
                [str(SYSTEM_PYTHON), "-c", "import time;time.sleep(30)"],
                cwd=self.base,
                env={"PATH": "/usr/bin:/bin"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            with mock.patch.object(
                full_gate, "_inspect_open_regular_files", return_value=()
            ), mock.patch.object(
                full_gate,
                "_inspect_unlinked_regular_mappings",
                return_value=records,
            ):
                outcome = full_gate.supervise_process(
                    process,
                    timeout=5,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                    limits=limits,
                    invocation_root=root,
                )
        self.assertEqual(
            outcome.resource_status, "GATE_AGGREGATE_BYTES_EXCEEDED"
        )
        self.assertTrue(outcome.cleanup_performed)

    def test_live_open_regular_files_close_descendant_amplification_gap(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "OpenRegularFile")
            and hasattr(full_gate, "scan_live_invocation_usage"),
            "tree-wide live regular-file accounting is not implemented",
        )
        root = self.base / "live-usage"
        root.mkdir()
        linked = root / "linked"
        linked.write_bytes(b"a" * 8)
        linked_metadata = linked.stat()
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 3
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 24
        records = {
            100: (
                full_gate.OpenRegularFile(
                    device=linked_metadata.st_dev,
                    inode=linked_metadata.st_ino,
                    size=8,
                    links=1,
                    writable=True,
                ),
                full_gate.OpenRegularFile(
                    device=99,
                    inode=1,
                    size=8,
                    links=0,
                    writable=True,
                ),
            ),
            101: (
                full_gate.OpenRegularFile(
                    device=99,
                    inode=1,
                    size=8,
                    links=0,
                    writable=True,
                ),
            ),
            102: (
                full_gate.OpenRegularFile(
                    device=99,
                    inode=2,
                    size=8,
                    links=0,
                    writable=True,
                ),
            ),
        }

        usage = full_gate.scan_live_invocation_usage(
            root,
            (100, 101, 102),
            limits,
            inspect_open_files=lambda pid: records[pid],
            inspect_mapped_files=lambda _pid, _max_regions: (),
        )

        self.assertEqual(
            usage,
            {
                "entries": 3,
                "bytes": 24,
                "open_unlinked_entries": 2,
                "open_unlinked_bytes": 16,
                "mapped_unlinked_entries": 0,
                "mapped_unlinked_bytes": 0,
            },
        )
        records[102] = (
            full_gate.OpenRegularFile(
                device=99,
                inode=2,
                size=8,
                links=0,
                writable=True,
            ),
            full_gate.OpenRegularFile(
                device=99,
                inode=3,
                size=1,
                links=0,
                writable=True,
            ),
        )
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_live_invocation_usage(
                root,
                (100, 101, 102),
                limits,
                inspect_open_files=lambda pid: records[pid],
                inspect_mapped_files=lambda _pid, _max_regions: (),
            )
        self.assertEqual(raised.exception.status, "GATE_AGGREGATE_BYTES_EXCEEDED")

    def test_live_usage_adds_static_baseline_and_external_fixed_logs(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "scan_live_invocation_usage"),
            "tree-wide live regular-file accounting is not implemented",
        )
        parameters = inspect.signature(
            full_gate.scan_live_invocation_usage
        ).parameters
        self.assertIn("baseline_usage", parameters)
        self.assertIn("linked_paths", parameters)
        root = self.base / "live-writable-root"
        root.mkdir()
        fixed_log = self.base / "fixed.log"
        fixed_log.write_bytes(b"f" * 8)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 3
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 24
        record = full_gate.OpenRegularFile(
            device=99,
            inode=1,
            size=8,
            links=0,
            writable=True,
        )

        usage = full_gate.scan_live_invocation_usage(
            root,
            (100,),
            limits,
            inspect_open_files=lambda _pid: (record,),
            inspect_mapped_files=lambda _pid, _max_regions: (),
            baseline_usage={"entries": 1, "bytes": 8},
            linked_paths=(fixed_log,),
        )

        self.assertEqual(
            usage,
            {
                "entries": 3,
                "bytes": 24,
                "open_unlinked_entries": 1,
                "open_unlinked_bytes": 8,
                "mapped_unlinked_entries": 0,
                "mapped_unlinked_bytes": 0,
            },
        )

    def test_static_baseline_excludes_initial_writable_scratch_entries(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "scan_invocation_baseline"),
            "disjoint static invocation baseline is not implemented",
        )
        invocation = self.base / "baseline-invocation"
        scratch = invocation / "scratch"
        scratch.mkdir(parents=True)
        (invocation / "static").write_bytes(b"s" * 8)
        (scratch / "initial").write_bytes(b"w" * 8)
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 2
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 24

        baseline = full_gate.scan_invocation_baseline(
            invocation, scratch, limits
        )
        usage = full_gate.scan_live_invocation_usage(
            scratch,
            (),
            limits,
            inspect_open_files=lambda _pid: (),
            baseline_usage=baseline,
        )

        self.assertEqual(baseline, {"entries": 2, "bytes": 8})
        self.assertEqual(usage["entries"], 3)
        self.assertEqual(usage["bytes"], 16)

    def test_live_scan_tolerates_entries_that_close_and_disappear(self) -> None:
        self.assertIn(
            "allow_disappeared",
            inspect.signature(full_gate._scan_invocation_usage).parameters,
            "live scratch scan does not handle normal unlink races",
        )
        root = self.base / "live-disappearing-entry"
        root.mkdir()
        (root / "gone").write_bytes(b"transient")
        real_stat = full_gate.os.stat

        def disappearing_stat(
            path: object,
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            if path == "gone" and dir_fd is not None:
                self.assertFalse(follow_symlinks)
                raise FileNotFoundError(errno.ENOENT, "entry disappeared")
            return real_stat(
                path,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with mock.patch.object(full_gate.os, "stat", side_effect=disappearing_stat):
            usage = full_gate.scan_live_invocation_usage(
                root,
                (),
                full_gate.DEFAULT_RESOURCE_LIMITS,
                inspect_open_files=lambda _pid: (),
            )

        self.assertEqual(usage["entries"], 0)
        self.assertEqual(usage["bytes"], 0)

    def test_live_scan_rejects_stat_to_symlink_directory_replacement(self) -> None:
        root = self.base / "live-directory-race"
        child = root / "child"
        moved = root / "moved-child"
        outside = self.base / "outside-directory"
        child.mkdir(parents=True)
        outside.mkdir()
        (child / "inside").write_bytes(b"i")
        (outside / "payload").write_bytes(b"o" * 64)
        real_open = full_gate.os.open
        replaced = False

        def racing_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal replaced
            if path == "child" and dir_fd is not None and not replaced:
                child.rename(moved)
                child.symlink_to(outside, target_is_directory=True)
                replaced = True
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(full_gate.os, "open", side_effect=racing_open):
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.scan_live_invocation_usage(
                    root,
                    (),
                    full_gate.DEFAULT_RESOURCE_LIMITS,
                    inspect_open_files=lambda _pid: (),
                )

        self.assertTrue(replaced)
        self.assertEqual(
            raised.exception.status, "GATE_INVOCATION_ENTRY_INVALID"
        )

    def test_live_open_regular_file_inventory_failure_is_typed(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "OpenRegularFile")
            and hasattr(full_gate, "scan_live_invocation_usage"),
            "tree-wide live regular-file accounting is not implemented",
        )
        root = self.base / "live-inventory-failure"
        root.mkdir()

        def fail_inventory(_pid: int) -> tuple[full_gate.OpenRegularFile, ...]:
            raise OSError("process inspection failed")

        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.scan_live_invocation_usage(
                root,
                (100,),
                full_gate.DEFAULT_RESOURCE_LIMITS,
                inspect_open_files=fail_inventory,
            )
        self.assertEqual(
            raised.exception.status, "GATE_OPEN_FILE_INVENTORY_FAILED"
        )

    def test_darwin_open_flags_require_kernel_fwrite(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "_darwin_file_flags_writable"),
            "Darwin FREAD/FWRITE classification is not implemented",
        )
        self.assertFalse(full_gate._darwin_file_flags_writable(0x0))
        self.assertFalse(full_gate._darwin_file_flags_writable(0x1))
        self.assertTrue(full_gate._darwin_file_flags_writable(0x2))
        self.assertTrue(full_gate._darwin_file_flags_writable(0x3))

    def test_linux_fdinfo_requires_stable_exact_identity_and_flags(self) -> None:
        inspect_descriptor = getattr(
            full_gate, "_inspect_linux_open_regular_file", None
        )
        self.assertTrue(
            callable(inspect_descriptor),
            "stable bounded Linux fdinfo inspection is not implemented",
        )
        metadata = os.stat_result(
            (stat.S_IFREG | 0o600, 123, 99, 0, 0, 0, 8, 0, 0, 0)
        )
        stable_cases = (
            (b"flags:\t0100000\nmnt_id:\t42\nino:\t123\npos:\t0\n", False),
            (b"flags:\t0100001\nmnt_id:\t42\nino:\t123\npos:\t99\n", True),
        )
        for fdinfo, writable in stable_cases:
            with self.subTest(writable=writable):
                reads = mock.Mock(side_effect=(fdinfo, fdinfo))
                record = inspect_descriptor(
                    100,
                    "7",
                    read_fdinfo=reads,
                    stat_descriptor=lambda _path: metadata,
                )
                self.assertEqual(
                    record,
                    full_gate.OpenRegularFile(
                        device=99,
                        inode=123,
                        size=8,
                        links=0,
                        writable=writable,
                    ),
                )
                self.assertEqual(reads.call_count, 2)

    def test_linux_fdinfo_reuse_race_fails_closed_after_fixed_retries(self) -> None:
        inspect_descriptor = getattr(
            full_gate, "_inspect_linux_open_regular_file", None
        )
        self.assertTrue(
            callable(inspect_descriptor),
            "stable bounded Linux fdinfo inspection is not implemented",
        )
        metadata = os.stat_result(
            (stat.S_IFREG | 0o600, 456, 99, 1, 0, 0, 8, 0, 0, 0)
        )
        old = b"flags:\t0100000\nmnt_id:\t42\nino:\t123\n"
        reused = b"flags:\t0100001\nmnt_id:\t43\nino:\t456\n"
        reads = mock.Mock(side_effect=(old, reused) * 3)

        with self.assertRaises(OSError):
            inspect_descriptor(
                100,
                "7",
                read_fdinfo=reads,
                stat_descriptor=lambda _path: metadata,
            )

        self.assertEqual(reads.call_count, 6)

    def test_linux_fdinfo_rejects_missing_duplicate_and_malformed_fields(self) -> None:
        inspect_descriptor = getattr(
            full_gate, "_inspect_linux_open_regular_file", None
        )
        self.assertTrue(
            callable(inspect_descriptor),
            "stable bounded Linux fdinfo inspection is not implemented",
        )
        metadata = os.stat_result(
            (stat.S_IFREG | 0o600, 123, 99, 1, 0, 0, 8, 0, 0, 0)
        )
        invalid_payloads = (
            b"flags:\t0100000\nino:\t123\n",
            b"flags:\t0100000\nflags:\t0100001\nmnt_id:\t42\nino:\t123\n",
            b"flags:\t0100000\nmnt_id:\t42\nino:\tnot-an-inode\n",
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(OSError):
                inspect_descriptor(
                    100,
                    "7",
                    read_fdinfo=lambda _path, value=payload: value,
                    stat_descriptor=lambda _path: metadata,
                )

    def test_linux_fdinfo_reader_rejects_payload_over_four_kibibytes(self) -> None:
        fdinfo = self.base / "oversized-fdinfo"
        fdinfo.write_bytes(b"x" * (4 * 1024 + 1))

        with self.assertRaises(OSError) as raised:
            full_gate._read_linux_fdinfo(fdinfo)

        self.assertEqual(raised.exception.errno, errno.EOVERFLOW)

    def test_open_file_inventory_skips_confirmed_exit_and_identity_reuse(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "_inspect_identity_open_regular_files"),
            "identity-safe open-file inventory is not implemented",
        )

        def exited(_pid: int) -> tuple[full_gate.OpenRegularFile, ...]:
            raise ProcessLookupError(errno.ESRCH, "process exited")

        observed, refreshed = full_gate._inspect_identity_open_regular_files(
            ((100, "linux-proc-start:1"), (101, "linux-proc-start:2")),
            inspect_open_files=exited,
            process_snapshot=lambda: {
                101: (1, 0, 0, "linux-proc-start:3"),
            },
        )

        self.assertEqual(observed, {})
        self.assertEqual(
            refreshed, {101: (1, 0, 0, "linux-proc-start:3")}
        )

    def test_open_file_inventory_recheck_fails_closed_for_same_identity(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "_inspect_identity_open_regular_files"),
            "identity-safe open-file inventory is not implemented",
        )

        def exited(_pid: int) -> tuple[full_gate.OpenRegularFile, ...]:
            raise ProcessLookupError(errno.ESRCH, "process exited")

        def unavailable() -> dict[int, tuple[int, int, int, str]]:
            raise full_gate.FullGateError("PROCESS_INVENTORY_FAILED")

        for name, snapshot in (
            (
                "same_identity",
                lambda: {100: (1, 0, 0, "linux-proc-start:1")},
            ),
            ("recheck_unavailable", unavailable),
        ):
            with self.subTest(name=name), self.assertRaises(
                full_gate.FullGateError
            ) as raised:
                full_gate._inspect_identity_open_regular_files(
                    ((100, "linux-proc-start:1"),),
                    inspect_open_files=exited,
                    process_snapshot=snapshot,
                )
            self.assertEqual(
                raised.exception.status, "GATE_OPEN_FILE_INVENTORY_FAILED"
            )

    def test_open_file_inventory_rechecks_successful_reads_for_pid_reuse(self) -> None:
        record = full_gate.OpenRegularFile(
            device=99,
            inode=1,
            size=8,
            links=0,
            writable=True,
        )
        for name, start_identity, expected in (
            ("same_identity", "linux-proc-start:1", {100: (record,)}),
            ("identity_drift", "linux-proc-start:2", {}),
            ("process_exited", None, {}),
        ):
            snapshot = (
                {}
                if start_identity is None
                else {100: (1, 0, 0, start_identity)}
            )
            with self.subTest(name=name):
                observed, refreshed = full_gate._inspect_identity_open_regular_files(
                    ((100, "linux-proc-start:1"),),
                    inspect_open_files=lambda _pid: (record,),
                    process_snapshot=lambda: snapshot,
                )
                self.assertEqual(observed, expected)
                self.assertEqual(refreshed, snapshot)

    def test_supervision_terminates_on_live_unlinked_aggregate_overflow(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "OpenRegularFile")
            and hasattr(full_gate, "_inspect_open_regular_files"),
            "supervised live regular-file inventory is not implemented",
        )
        root = self.base / "supervised-live-usage"
        root.mkdir()
        stdout = self.base / "live-overflow.stdout"
        stderr = self.base / "live-overflow.stderr"
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 8
        limits["nofile"] = 1
        limits["per_file_bytes"] = 16
        limits["aggregate_bytes"] = 8
        records = (
            full_gate.OpenRegularFile(
                device=99,
                inode=1,
                size=5,
                links=0,
                writable=True,
            ),
            full_gate.OpenRegularFile(
                device=99,
                inode=2,
                size=5,
                links=0,
                writable=True,
            ),
        )
        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            process = subprocess.Popen(
                [str(SYSTEM_PYTHON), "-c", "import time;time.sleep(30)"],
                cwd=self.base,
                env={"PATH": "/usr/bin:/bin"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            with mock.patch.object(
                full_gate,
                "_inspect_open_regular_files",
                return_value=records,
            ):
                outcome = full_gate.supervise_process(
                    process,
                    timeout=5,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                    limits=limits,
                    invocation_root=root,
                )
        self.assertEqual(
            outcome.resource_status, "GATE_AGGREGATE_BYTES_EXCEEDED"
        )
        self.assertTrue(outcome.cleanup_performed)

    def test_supervision_keeps_reparented_observed_descendant_in_live_budget(
        self,
    ) -> None:
        root = self.base / "reparented-live-usage"
        root.mkdir()
        stdout = self.base / "reparented-overflow.stdout"
        stderr = self.base / "reparented-overflow.stderr"
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["file_size_bytes"] = 5
        limits["nofile"] = 1
        limits["per_file_bytes"] = 8
        limits["aggregate_bytes"] = 5
        root_record = full_gate.OpenRegularFile(
            device=99,
            inode=1,
            size=5,
            links=0,
            writable=True,
        )
        child_record = full_gate.OpenRegularFile(
            device=99,
            inode=2,
            size=5,
            links=0,
            writable=True,
        )
        child_inspections = 0
        process_holder: dict[str, subprocess.Popen[bytes]] = {}
        snapshot_calls = 0

        def inspect_open_files(pid: int) -> tuple[full_gate.OpenRegularFile, ...]:
            nonlocal child_inspections
            if pid == process_holder["process"].pid:
                return (root_record,)
            if pid == 999_991:
                child_inspections += 1
                return () if child_inspections == 1 else (child_record,)
            return ()

        def process_snapshot() -> dict[int, tuple[int, int, int, str]]:
            nonlocal snapshot_calls
            process = process_holder["process"]
            if process.poll() is not None:
                return {}
            snapshot_calls += 1
            child_parent = process.pid if snapshot_calls == 1 else 1
            return {
                process.pid: (1, 0, 0, "linux-proc-start:1"),
                999_991: (child_parent, 0, 0, "linux-proc-start:2"),
            }

        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            process = subprocess.Popen(
                [str(SYSTEM_PYTHON), "-c", "import time;time.sleep(30)"],
                cwd=self.base,
                env={"PATH": "/usr/bin:/bin"},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            process_holder["process"] = process
            with mock.patch.object(
                full_gate,
                "_process_snapshot",
                side_effect=process_snapshot,
            ), mock.patch.object(
                full_gate,
                "_inspect_open_regular_files",
                side_effect=inspect_open_files,
            ), mock.patch.object(
                full_gate,
                "_inspect_unlinked_regular_mappings",
                return_value=(),
            ):
                outcome = full_gate.supervise_process(
                    process,
                    timeout=0.1,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                    limits=limits,
                    invocation_root=root,
                )

        self.assertGreaterEqual(child_inspections, 2)
        self.assertEqual(
            outcome.resource_status, "GATE_AGGREGATE_BYTES_EXCEEDED"
        )
        self.assertTrue(outcome.cleanup_performed)

    def test_descendant_cap_precedes_all_live_storage_inventory(self) -> None:
        class RunningProcess:
            pid = 999_977
            returncode = -signal.SIGTERM

            def poll(self) -> None:
                return None

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        process = RunningProcess()
        table = {
            process.pid: (1, 0, 0, "linux-proc-start:1"),
            999_976: (process.pid, 0, 0, "linux-proc-start:2"),
            999_975: (process.pid, 0, 0, "linux-proc-start:3"),
        }
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["descendants"] = 1
        root = self.base / "descendant-precheck"
        root.mkdir()
        stdout = self.base / "descendant-precheck.stdout"
        stderr = self.base / "descendant-precheck.stderr"
        with stdout.open("w+b") as stdout_handle, stderr.open(
            "w+b"
        ) as stderr_handle, mock.patch.object(
            full_gate, "_process_snapshot", return_value=table
        ), mock.patch.object(
            full_gate, "_inspect_open_regular_files"
        ) as inspect_open, mock.patch.object(
            full_gate, "_inspect_unlinked_regular_mappings"
        ) as inspect_mapped, mock.patch.object(
            full_gate, "_terminate_process_group", return_value=True
        ), mock.patch.object(
            full_gate, "_kill_tracked_descendants", return_value=True
        ):
            outcome = full_gate.supervise_process(
                process,
                timeout=1,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                invocation_root=root,
                limits=limits,
            )
        self.assertEqual(
            outcome.resource_status, "GATE_DESCENDANT_LIMIT_EXCEEDED"
        )
        inspect_open.assert_not_called()
        inspect_mapped.assert_not_called()

    def test_descendant_cleanup_snapshots_are_bounded_independent_of_pid_count(
        self,
    ) -> None:
        identities = tuple(
            (900_000 + index, f"linux-proc-start:{index + 1}")
            for index in range(32)
        )
        alive = {
            pid: (1, 0, 0, start_identity)
            for pid, start_identity in identities
        }
        with mock.patch.object(
            full_gate, "_process_snapshot", side_effect=(alive, {})
        ) as snapshots, mock.patch.object(
            full_gate,
            "_open_identity_bound_pidfd",
            side_effect=range(700, 732),
        ), mock.patch.object(
            full_gate, "_signal_identity_bound_pidfd", return_value=True
        ) as signal_pidfd, mock.patch.object(
            full_gate, "_close_raw_descriptor_with_retry", return_value=None
        ):
            cleaned = full_gate._kill_tracked_descendants(identities)
        self.assertTrue(cleaned)
        self.assertEqual(snapshots.call_count, 2)
        self.assertEqual(signal_pidfd.call_count, len(identities))
        self.assertTrue(
            all(call.args[1] == signal.SIGTERM for call in signal_pidfd.call_args_list)
        )

    def test_supervision_uses_one_initial_snapshot_plus_one_per_accounting_iteration(
        self,
    ) -> None:
        root = self.base / "single-snapshot-accounting"
        root.mkdir()
        stdout = self.base / "single-snapshot.stdout"
        stderr = self.base / "single-snapshot.stderr"
        iterations = 3
        snapshot_calls = 0

        class FinishedAfterIterations:
            pid = 999_989
            returncode = 0

            def __init__(self) -> None:
                self.poll_calls = 0

            def poll(self) -> int | None:
                if self.poll_calls < iterations:
                    self.poll_calls += 1
                    return None
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        process = FinishedAfterIterations()

        def process_snapshot() -> dict[int, tuple[int, int, int, str]]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return {
                process.pid: (1, 0, 0, "linux-proc-start:1"),
            }

        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            with mock.patch.object(
                full_gate,
                "_process_snapshot",
                side_effect=process_snapshot,
            ), mock.patch.object(
                full_gate,
                "_inspect_open_regular_files",
                return_value=(),
            ), mock.patch.object(
                full_gate,
                "_inspect_unlinked_regular_mappings",
                return_value=(),
            ), mock.patch.object(
                full_gate,
                "_terminate_process_group",
                return_value=False,
            ), mock.patch.object(full_gate.time, "sleep"):
                outcome = full_gate.supervise_process(
                    process,
                    timeout=5,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                    invocation_root=root,
                )

        self.assertEqual(outcome.returncode, 0)
        self.assertEqual(snapshot_calls, 1 + iterations)

    def test_supervision_refreshes_without_live_fd_scan_and_detects_pid_drift(
        self,
    ) -> None:
        stdout = self.base / "no-live-fd-drift.stdout"
        stderr = self.base / "no-live-fd-drift.stderr"
        snapshots = iter(
            (
                {999_987: (1, 0, 0, "linux-proc-start:1")},
                {999_987: (1, 0, 0, "linux-proc-start:2")},
            )
        )
        snapshot_calls = 0

        class RunningProcess:
            pid = 999_987
            returncode = -signal.SIGTERM

            def poll(self) -> None:
                return None

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode

        def process_snapshot() -> dict[int, tuple[int, int, int, str]]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return next(snapshots)

        with stdout.open("w+b") as stdout_handle, stderr.open("w+b") as stderr_handle:
            with mock.patch.object(
                full_gate,
                "_process_snapshot",
                side_effect=process_snapshot,
            ), mock.patch.object(
                full_gate,
                "_terminate_process_group",
                return_value=True,
            ):
                outcome = full_gate.supervise_process(
                    RunningProcess(),
                    timeout=5,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                )

        self.assertEqual(outcome.resource_status, "WRAPPER_IDENTITY_DRIFT")
        self.assertEqual(snapshot_calls, 2)

    def _minimal_run_gate_fixture(self) -> dict[str, object]:
        invocation = self.base / "pipe-ownership-invocation"
        paths = {
            "snapshot": invocation / "snapshot",
            "runtime": invocation / "runtime",
            "dependencies": invocation / "dependencies",
            "tools": invocation / "tools",
            "wrapper": invocation / "wrapper.py",
            "contract": invocation / "contract.json",
            "scratch": invocation / "scratch",
            "tmpdir": invocation / "tmp",
        }
        for key, path in paths.items():
            if key not in {"wrapper", "contract"}:
                path.mkdir(parents=True, exist_ok=True)
        return paths

    def test_run_gate_computes_baseline_before_creating_authority_pipe(self) -> None:
        paths = self._minimal_run_gate_fixture()
        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            side_effect=full_gate.FullGateError("GATE_INVOCATION_ENTRY_INVALID"),
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ) as create_pipe, mock.patch.object(full_gate.os, "close"):
            with self.assertRaises(full_gate.FullGateError):
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )
        create_pipe.assert_not_called()

    def test_owned_descriptor_retries_pre_close_interrupt_and_avoids_reused_fd(
        self,
    ) -> None:
        real_close = os.close

        read_fd, write_fd = os.pipe()
        before_owner = full_gate._OwnedDescriptor.take(write_fd)
        os.write(write_fd, b"buffered-before-close")
        before_calls = 0

        def interrupt_before_close(descriptor: int) -> None:
            nonlocal before_calls
            self.assertEqual(descriptor, write_fd)
            before_calls += 1
            if before_calls == 1:
                raise KeyboardInterrupt()
            real_close(descriptor)

        try:
            with mock.patch.object(
                full_gate.os, "close", side_effect=interrupt_before_close
            ):
                with self.assertRaises(KeyboardInterrupt):
                    before_owner.close()
                self.assertEqual(before_owner.fileno(), write_fd)
                before_owner.close()
            self.assertEqual(before_calls, 2)
            with self.assertRaises(OSError):
                os.fstat(write_fd)
        finally:
            real_close(read_fd)

        read_fd, write_fd = os.pipe()
        after_owner = full_gate._OwnedDescriptor.take(write_fd)
        replacement: dict[str, int] = {}

        def interrupt_after_close(descriptor: int) -> None:
            self.assertEqual(descriptor, write_fd)
            real_close(descriptor)
            replacement_fd = os.open("/dev/null", os.O_RDONLY)
            if replacement_fd != descriptor:
                os.dup2(replacement_fd, descriptor)
                real_close(replacement_fd)
            replacement["fd"] = descriptor
            raise KeyboardInterrupt()

        try:
            with mock.patch.object(
                full_gate.os, "close", side_effect=interrupt_after_close
            ):
                with self.assertRaises(KeyboardInterrupt):
                    after_owner.close()
                after_owner.close()
            self.assertEqual(after_owner.descriptor, -1)
            self.assertTrue(stat.S_ISCHR(os.fstat(replacement["fd"]).st_mode))
        finally:
            real_close(replacement.get("fd", write_fd))
            real_close(read_fd)

    def test_create_cloexec_pipe_closes_both_fds_on_set_or_get_failure(
        self,
    ) -> None:
        real_pipe = os.pipe
        real_set_inheritable = os.set_inheritable
        for stage in ("set", "get"):
            with self.subTest(stage=stage):
                created: tuple[int, int] | None = None

                def tracked_pipe() -> tuple[int, int]:
                    nonlocal created
                    created = real_pipe()
                    return created

                def set_inheritable(descriptor: int, inheritable: bool) -> None:
                    if stage == "set":
                        raise OSError(errno.EIO, "injected set failure")
                    real_set_inheritable(descriptor, inheritable)

                def get_inheritable(_descriptor: int) -> bool:
                    if stage == "get":
                        raise OSError(errno.EIO, "injected get failure")
                    return False

                with mock.patch.object(
                    full_gate.os, "pipe", side_effect=tracked_pipe
                ), mock.patch.object(
                    full_gate.os, "set_inheritable", side_effect=set_inheritable
                ), mock.patch.object(
                    full_gate.os, "get_inheritable", side_effect=get_inheritable
                ), self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate.create_cloexec_pipe()

                self.assertEqual(
                    raised.exception.status,
                    "AUTHORITY_PIPE_CREATE_FAILED",
                )
                self.assertIsNotNone(created)
                for descriptor in created or ():
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)

    def test_create_cloexec_pipe_retries_pre_close_interrupt_for_both_fds(
        self,
    ) -> None:
        real_pipe = os.pipe
        real_close = os.close
        created: tuple[int, int] | None = None
        close_calls: list[int] = []

        def tracked_pipe() -> tuple[int, int]:
            nonlocal created
            created = real_pipe()
            return created

        def interrupt_first_close(descriptor: int) -> None:
            close_calls.append(descriptor)
            if len(close_calls) == 1:
                raise KeyboardInterrupt("injected pre-close interrupt")
            real_close(descriptor)

        with mock.patch.object(
            full_gate.os, "pipe", side_effect=tracked_pipe
        ), mock.patch.object(
            full_gate.os, "get_inheritable", return_value=True
        ), mock.patch.object(
            full_gate.os, "close", side_effect=interrupt_first_close
        ), self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.create_cloexec_pipe()

        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_CREATE_FAILED")
        self.assertEqual(
            raised.exception.primary_status,
            "AUTHORITY_PIPE_CLOSE_FAILED",
        )
        self.assertIsNotNone(created)
        self.assertEqual(len(close_calls), 3)
        self.assertEqual(close_calls[0], close_calls[1])
        self.assertNotEqual(close_calls[1], close_calls[2])
        for descriptor in created or ():
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_run_gate_closes_owned_pipe_fds_on_pre_spawn_failure(self) -> None:
        paths = self._minimal_run_gate_fixture()
        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec",),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(full_gate.os, "close") as close_fd:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )
        self.assertEqual(raised.exception.status, "GATE_SPAWN_FAILED")
        self.assertEqual(close_fd.call_count, 2)
        close_fd.assert_any_call(701)
        close_fd.assert_any_call(702)

    def test_run_gate_closes_owned_pipe_fds_on_spawn_failure_and_success(self) -> None:
        paths = self._minimal_run_gate_fixture()

        class FinishedProcess:
            pid = 999_988
            returncode = 0

        for name, popen_result, supervise_result, expected_error in (
            (
                "spawn_failure",
                OSError("spawn failed"),
                full_gate.GateOutcome(0, False, False, None, b"", b""),
                "GATE_SPAWN_FAILED",
            ),
            (
                "supervision_failure",
                FinishedProcess(),
                full_gate.FullGateError("PROCESS_INVENTORY_FAILED"),
                "PROCESS_INVENTORY_FAILED",
            ),
            (
                "success",
                FinishedProcess(),
                full_gate.GateOutcome(0, False, False, None, b"", b""),
                None,
            ),
        ):
            with self.subTest(name=name):
                with mock.patch.object(
                    full_gate,
                    "build_sandbox_argv",
                    return_value=("sandbox-exec", "--authority-fd", "3"),
                ), mock.patch.object(
                    full_gate,
                    "scan_invocation_baseline",
                    return_value={"entries": 0, "bytes": 0},
                ), mock.patch.object(
                    full_gate,
                    "create_cloexec_pipe",
                    return_value=(701, 702),
                ), mock.patch.object(
                    full_gate.subprocess,
                    "Popen",
                    side_effect=popen_result if isinstance(popen_result, OSError) else None,
                    return_value=None if isinstance(popen_result, OSError) else popen_result,
                ), mock.patch.object(
                    full_gate,
                    "supervise_process",
                    side_effect=(
                        supervise_result
                        if isinstance(supervise_result, full_gate.FullGateError)
                        else None
                    ),
                    return_value=(
                        None
                        if isinstance(supervise_result, full_gate.FullGateError)
                        else supervise_result
                    ),
                ), mock.patch.object(
                    full_gate,
                    "_cleanup_spawn_after_authority_pipe_close_failure",
                ) as cleanup, mock.patch.object(
                    full_gate.os, "close"
                ) as close_fd:
                    if expected_error is None:
                        outcome = full_gate.run_gate_once(
                            b"profile",
                            paths["snapshot"],
                            paths["runtime"],
                            paths["dependencies"],
                            paths["tools"],
                            paths["wrapper"],
                            paths["contract"],
                            "a" * 64,
                            paths["scratch"],
                            {"TMPDIR": str(paths["tmpdir"])},
                            sandbox_executable=Path("/usr/bin/sandbox-exec"),
                            timeout=10,
                            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                            nonce="b" * 64,
                        )
                        self.assertEqual(outcome.returncode, 0)
                    else:
                        with self.assertRaises(full_gate.FullGateError) as raised:
                            full_gate.run_gate_once(
                                b"profile",
                                paths["snapshot"],
                                paths["runtime"],
                                paths["dependencies"],
                                paths["tools"],
                                paths["wrapper"],
                                paths["contract"],
                                "a" * 64,
                                paths["scratch"],
                                {"TMPDIR": str(paths["tmpdir"])},
                                sandbox_executable=Path("/usr/bin/sandbox-exec"),
                                timeout=10,
                                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                                nonce="b" * 64,
                            )
                        self.assertEqual(raised.exception.status, expected_error)
                if name == "supervision_failure":
                    cleanup.assert_called_once_with(popen_result)
                else:
                    cleanup.assert_not_called()
                self.assertEqual(close_fd.call_count, 2)
                close_fd.assert_any_call(701)
                close_fd.assert_any_call(702)

    def test_run_gate_cleans_spawned_process_on_supervision_interruption(
        self,
    ) -> None:
        paths = self._minimal_run_gate_fixture()
        process = mock.Mock(pid=999_987, returncode=None)
        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(
            full_gate.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            full_gate,
            "supervise_process",
            side_effect=KeyboardInterrupt,
        ), mock.patch.object(
            full_gate,
            "_cleanup_spawn_after_authority_pipe_close_failure",
        ) as cleanup, mock.patch.object(
            full_gate.os,
            "close",
        ) as close_fd, self.assertRaises(KeyboardInterrupt):
            full_gate.run_gate_once(
                b"profile",
                paths["snapshot"],
                paths["runtime"],
                paths["dependencies"],
                paths["tools"],
                paths["wrapper"],
                paths["contract"],
                "a" * 64,
                paths["scratch"],
                {"TMPDIR": str(paths["tmpdir"])},
                sandbox_executable=self.sandbox_executable,
                timeout=10,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                nonce="b" * 64,
            )
        cleanup.assert_called_once_with(process)
        self.assertEqual(close_fd.call_args_list, [mock.call(702), mock.call(701)])

    def test_run_gate_cleans_spawned_process_when_parent_write_close_fails(
        self,
    ) -> None:
        paths = self._minimal_run_gate_fixture()
        process = mock.Mock(pid=999_986, returncode=-signal.SIGTERM)
        process.wait.return_value = process.returncode

        def close_fd(descriptor: int) -> None:
            if descriptor == 702:
                raise OSError(errno.EIO, "parent write close failed")

        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(
            full_gate.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            full_gate,
            "supervise_process",
        ) as supervise, mock.patch.object(
            full_gate,
            "_terminate_process_group",
            return_value=True,
        ) as terminate, mock.patch.object(
            full_gate.os,
            "close",
            side_effect=close_fd,
        ) as close:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )

        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_CLOSE_FAILED")
        supervise.assert_not_called()
        terminate.assert_called_once_with(process.pid)
        process.wait.assert_called_once_with(timeout=2)
        self.assertEqual(close.call_args_list, [mock.call(702), mock.call(701)])

    def test_run_gate_final_owned_fd_close_failure_is_typed_and_not_retried(
        self,
    ) -> None:
        paths = self._minimal_run_gate_fixture()

        class FinishedProcess:
            pid = 999_985
            returncode = 0

        def close_fd(descriptor: int) -> None:
            if descriptor == 701:
                raise OSError(errno.EIO, "parent read close failed")

        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(
            full_gate.subprocess,
            "Popen",
            return_value=FinishedProcess(),
        ), mock.patch.object(
            full_gate,
            "supervise_process",
            return_value=full_gate.GateOutcome(0, False, False, None, b"", b""),
        ), mock.patch.object(
            full_gate,
            "_cleanup_spawn_after_authority_pipe_close_failure",
        ) as cleanup, mock.patch.object(
            full_gate.os, "close", side_effect=close_fd
        ) as close:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )

        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_CLOSE_FAILED")
        cleanup.assert_called_once()
        self.assertEqual(close.call_args_list, [mock.call(702), mock.call(701)])

    def test_run_gate_read_close_failure_replaces_and_preserves_child_wait_failure(
        self,
    ) -> None:
        paths = self._minimal_run_gate_fixture()
        process = mock.Mock(pid=999_984, returncode=None)
        process.wait.side_effect = (
            subprocess.TimeoutExpired(("sandbox-exec",), 2),
            subprocess.TimeoutExpired(("sandbox-exec",), 2),
        )

        def close_fd(descriptor: int) -> None:
            if descriptor in {701, 702}:
                raise OSError(errno.EIO, "authority close failed")

        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(
            full_gate.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            full_gate,
            "supervise_process",
        ) as supervise, mock.patch.object(
            full_gate,
            "_terminate_process_group",
            return_value=True,
        ) as terminate, mock.patch.object(
            full_gate.os,
            "close",
            side_effect=close_fd,
        ) as close:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )

        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_CLOSE_FAILED")
        self.assertEqual(raised.exception.primary_status, "CHILD_WAIT_FAILED")
        self.assertIsInstance(raised.exception.__cause__, full_gate.FullGateError)
        self.assertEqual(raised.exception.__cause__.status, "CHILD_WAIT_FAILED")
        supervise.assert_not_called()
        self.assertEqual(terminate.call_count, 2)
        self.assertEqual(process.wait.call_count, 2)
        self.assertEqual(close.call_args_list, [mock.call(702), mock.call(701)])

    def test_run_gate_read_close_failure_replaces_and_preserves_supervision_blocker(
        self,
    ) -> None:
        paths = self._minimal_run_gate_fixture()

        class FinishedProcess:
            pid = 999_983
            returncode = 1

        def close_fd(descriptor: int) -> None:
            if descriptor == 701:
                raise OSError(errno.EIO, "parent read close failed")

        with mock.patch.object(
            full_gate,
            "build_sandbox_argv",
            return_value=("sandbox-exec", "--authority-fd", "3"),
        ), mock.patch.object(
            full_gate,
            "scan_invocation_baseline",
            return_value={"entries": 0, "bytes": 0},
        ), mock.patch.object(
            full_gate,
            "create_cloexec_pipe",
            return_value=(701, 702),
        ), mock.patch.object(
            full_gate.subprocess,
            "Popen",
            return_value=FinishedProcess(),
        ), mock.patch.object(
            full_gate,
            "supervise_process",
            side_effect=full_gate.FullGateError("GATE_AGGREGATE_BYTES_EXCEEDED"),
        ), mock.patch.object(
            full_gate,
            "_cleanup_spawn_after_authority_pipe_close_failure",
        ) as cleanup, mock.patch.object(
            full_gate.os, "close", side_effect=close_fd
        ) as close:
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.run_gate_once(
                    b"profile",
                    paths["snapshot"],
                    paths["runtime"],
                    paths["dependencies"],
                    paths["tools"],
                    paths["wrapper"],
                    paths["contract"],
                    "a" * 64,
                    paths["scratch"],
                    {"TMPDIR": str(paths["tmpdir"])},
                    sandbox_executable=Path("/usr/bin/sandbox-exec"),
                    timeout=10,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    nonce="b" * 64,
                )

        self.assertEqual(raised.exception.status, "AUTHORITY_PIPE_CLOSE_FAILED")
        self.assertEqual(
            raised.exception.primary_status, "GATE_AGGREGATE_BYTES_EXCEEDED"
        )
        self.assertIsInstance(raised.exception.__cause__, full_gate.FullGateError)
        self.assertEqual(
            raised.exception.__cause__.status,
            "GATE_AGGREGATE_BYTES_EXCEEDED",
        )
        cleanup.assert_called_once()
        self.assertEqual(close.call_args_list, [mock.call(702), mock.call(701)])

    def test_run_gate_spawns_exactly_one_sandbox_with_no_inherited_environment(self) -> None:
        self.assertTrue(
            hasattr(full_gate, "run_gate_once"),
            "exact one-sandbox gate execution is not implemented",
        )
        invocation = self.base / "invocation"
        snapshot = invocation / "snapshot"
        runtime = invocation / "runtime"
        dependencies = invocation / "dependencies"
        tools = invocation / "tools"
        scratch = invocation / "scratch"
        tmpdir = invocation / "tmp"
        for path in (
            snapshot,
            runtime / "bin",
            dependencies,
            tools / "bin",
            scratch,
            tmpdir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (runtime / "bin/python3.12").write_bytes(b"python")
        wrapper, _binding = full_gate.materialize_trusted_wrapper(
            invocation, full_gate.trusted_wrapper_binding()
        )
        contract = invocation / "control/contract.json"
        contract.write_bytes(b"{}")
        environment = {"A": "1", "TMPDIR": str(tmpdir)}

        class FinishedProcess:
            pid = 999999
            returncode = 0

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with mock.patch.object(
            full_gate.subprocess, "Popen", return_value=FinishedProcess()
        ) as popen, mock.patch.object(
            full_gate,
            "supervise_process",
            return_value=full_gate.GateOutcome(
                0, False, False, None, b"", b""
            ),
        ) as supervise:
            outcome = full_gate.run_gate_once(
                b"(version 1)\n(deny default)\n",
                snapshot,
                runtime,
                dependencies,
                tools,
                wrapper,
                contract,
                "a" * 64,
                scratch,
                environment,
                sandbox_executable=self.sandbox_executable,
                timeout=10,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                nonce="b" * 64,
            )
        self.assertEqual(outcome.returncode, 0)
        self.assertEqual(popen.call_count, 1)
        call = popen.call_args
        self.assertEqual(call.kwargs["cwd"], snapshot)
        self.assertEqual(call.kwargs["env"], environment)
        self.assertTrue(call.kwargs["start_new_session"])
        self.assertTrue(call.kwargs["close_fds"])
        self.assertEqual(len(call.kwargs["pass_fds"]), 1)
        self.assertEqual(supervise.call_count, 1)
        self.assertEqual(call.args[0].count(str(self.sandbox_executable)), 1)


class FullGateTrustedWrapperProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-wrapper-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.invocation = self.base / "invocation"
        self.snapshot = self.invocation / "snapshot"
        self.runtime = self.invocation / "runtime"
        self.dependencies = self.invocation / "dependencies"
        self.tools = self.invocation / "tools"
        self.scratch = self.invocation / "scratch"
        for path in (
            self.snapshot,
            self.runtime / "bin",
            self.dependencies,
            self.tools / "bin",
            self.scratch,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (self.runtime / "bin/python3.12").write_bytes(b"python")
        (self.runtime / "bin/python3.12").chmod(0o555)
        self.sandbox_executable = self.base / "sandbox-exec"
        self.sandbox_executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.sandbox_executable.chmod(0o555)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_canonical_wrapper_is_materialized_and_digest_bound(self) -> None:
        binding = full_gate.trusted_wrapper_binding()
        self.assertEqual(binding["schema"], "samvil.full-gate-wrapper.v1")
        self.assertEqual(binding["mode"], "100555")
        self.assertEqual(binding["interpreter"], "runtime/bin/python3.12")
        self.assertEqual(binding["source_sha256"], sha256(full_gate.TRUSTED_WRAPPER_SOURCE))
        self.assertEqual(binding["content_sha256"], binding["source_sha256"])

        wrapper, observed = full_gate.materialize_trusted_wrapper(
            self.invocation, binding
        )
        self.assertEqual(wrapper.read_bytes(), full_gate.TRUSTED_WRAPPER_SOURCE)
        self.assertEqual(stat.S_IMODE(os.lstat(wrapper).st_mode), 0o555)
        self.assertEqual(observed, binding)
        self.assertFalse(wrapper.is_symlink())

    def test_trusted_pytest_probe_explicitly_loads_the_async_plugin(self) -> None:
        pytest_command = dict(full_gate.TRUSTED_PROBE_COMMANDS)["pytest"]
        inventory_index = pytest_command.index("<VERIFIED_TEST_INVENTORY>")
        self.assertEqual(
            pytest_command[5:inventory_index],
            (
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "no:cacheprovider",
            ),
        )
        wrapper_source = full_gate.TRUSTED_WRAPPER_SOURCE.decode("utf-8")
        explicit_plugin = '"-p", "pytest_asyncio.plugin"'
        verified_inventory = "*test_paths"
        self.assertIn(explicit_plugin, wrapper_source)
        self.assertLess(
            wrapper_source.index(explicit_plugin),
            wrapper_source.index(verified_inventory),
        )

    def test_exact_one_sandbox_final_argv_is_copied_python_plus_wrapper(self) -> None:
        binding = full_gate.trusted_wrapper_binding()
        wrapper, _observed = full_gate.materialize_trusted_wrapper(
            self.invocation, binding
        )
        contract = self.invocation / "control/wrapper-contract.json"
        contract.write_bytes(b"{}")
        environment = {"LANG": "C", "LC_ALL": "C"}
        argv = full_gate.build_sandbox_argv(
            b"(version 1)\n(deny default)\n",
            self.snapshot,
            self.runtime,
            self.dependencies,
            self.tools,
            wrapper,
            contract,
            "b" * 64,
            self.scratch,
            environment,
            sandbox_executable=self.sandbox_executable,
            authority_fd=17,
            nonce="a" * 64,
        )
        self.assertEqual(argv.count(str(self.sandbox_executable)), 1)
        self.assertEqual(
            argv[-22:],
            (
                str(self.runtime / "bin/python3.12"),
                str(wrapper),
                "--authority-fd",
                "17",
                "--nonce",
                "a" * 64,
                "--snapshot",
                str(self.snapshot),
                "--runtime",
                str(self.runtime),
                "--dependencies",
                str(self.dependencies),
                "--tools",
                str(self.tools),
                "--wrapper",
                str(wrapper),
                "--contract",
                str(contract),
                "--contract-sha256",
                "b" * 64,
                "--scratch",
                str(self.scratch),
            ),
        )
        self.assertNotIn("scripts/pre-commit-check.sh", argv)

    def test_candidate_environment_has_no_observation_or_authority_key(self) -> None:
        environment = full_gate.build_hermetic_environment(
            self.invocation,
            self.runtime,
            self.tools,
            source_environment={
                "SAMVIL_FULL_GATE_OBSERVATION_LOG": "/candidate/forged",
                "SAMVIL_AUTHORITY_FD": "17",
            },
        )
        self.assertFalse(
            any("OBSERVATION" in key or "AUTHORITY" in key for key in environment)
        )
        self.assertNotIn("/candidate/forged", environment.values())


class FullGateAuthorityFrameProtocolTest(unittest.TestCase):
    def frame(
        self,
        sequence: int,
        phase: str,
        *,
        nonce: str = "a" * 64,
        status: str = "PASS",
    ) -> bytes:
        return full_gate.encode_authority_frame(
            {
                "schema": "samvil.full-gate-authority-frame.v1",
                "nonce": nonce,
                "sequence": sequence,
                "phase": phase,
                "status": status,
                "evidence": {"sha256": sha256(phase.encode("ascii"))},
            },
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
        )

    def transcript(self) -> bytes:
        return b"".join(
            self.frame(index, phase)
            for index, phase in enumerate(full_gate.AUTHORITY_PHASES)
        )

    def test_ordered_prefix_ending_in_fail_is_a_valid_gate_failure_transcript(self) -> None:
        transcript = self.frame(0, "runtime_identity") + self.frame(
            1, "pytest", status="FAIL"
        )
        parsed = full_gate.decode_authority_frames(
            transcript,
            nonce="a" * 64,
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            wrapper_exited=True,
        )
        self.assertEqual(
            tuple((frame["phase"], frame["status"]) for frame in parsed),
            (("runtime_identity", "PASS"), ("pytest", "FAIL")),
        )

    def test_canonical_bounded_frames_require_exact_nonce_order_and_completion(self) -> None:
        parsed = full_gate.decode_authority_frames(
            self.transcript(),
            nonce="a" * 64,
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            wrapper_exited=True,
        )
        self.assertEqual(tuple(frame["phase"] for frame in parsed), full_gate.AUTHORITY_PHASES)
        self.assertEqual(parsed[-1]["status"], "PASS")

        attacks = {
            "wrong_nonce": self.frame(0, full_gate.AUTHORITY_PHASES[0], nonce="b" * 64),
            "duplicate": self.transcript() + self.frame(4, "complete"),
            "reordered": self.frame(0, "pytest") + b"".join(
                self.frame(index + 1, phase)
                for index, phase in enumerate(full_gate.AUTHORITY_PHASES[1:])
            ),
            "malformed": b"\x00\x00\x00\x05abcde",
            "truncated": self.transcript()[:-1],
        }
        for name, raw in attacks.items():
            with self.subTest(name=name), self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.decode_authority_frames(
                    raw,
                    nonce="a" * 64,
                    limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    wrapper_exited=True,
                )
            self.assertIn(
                raised.exception.status,
                {"AUTHORITY_FRAME_INVALID", "AUTHORITY_FRAME_ORDER_INVALID"},
            )

    def test_frame_count_size_aggregate_and_post_exit_bytes_are_blockers(self) -> None:
        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["authority_frame_bytes"] = 96
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.encode_authority_frame(
                {
                    "schema": "samvil.full-gate-authority-frame.v1",
                    "nonce": "a" * 64,
                    "sequence": 0,
                    "phase": "runtime_identity",
                    "status": "PASS",
                    "evidence": {"padding": "x" * 512},
                },
                limits=limits,
            )
        self.assertEqual(raised.exception.status, "AUTHORITY_FRAME_BYTES_EXCEEDED")

        limits = dict(full_gate.DEFAULT_RESOURCE_LIMITS)
        limits["authority_frame_count"] = len(full_gate.AUTHORITY_PHASES) - 1
        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.decode_authority_frames(
                self.transcript(),
                nonce="a" * 64,
                limits=limits,
                wrapper_exited=True,
            )
        self.assertEqual(raised.exception.status, "AUTHORITY_FRAME_COUNT_EXCEEDED")

        with self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.decode_authority_frames(
                self.transcript(),
                nonce="a" * 64,
                limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                wrapper_exited=True,
                post_exit_bytes=b"x",
            )
        self.assertEqual(raised.exception.status, "AUTHORITY_POST_EXIT_BYTES")


class FullGateTrustedWrapperDirectIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = require_invocation_tmpdir()
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-wrapper-direct-",
            dir=temp_parent,
        )
        self.base = Path(self._temp.name).resolve(strict=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_wrapper(
        self,
        gate_source: bytes,
        *,
        sandboxed: bool = False,
        timeout: float = 120,
    ) -> tuple[subprocess.CompletedProcess[bytes], bytes, Path]:
        seatbelt_context = require_real_seatbelt_context() if sandboxed else None
        execution_context = (
            None if seatbelt_context is not None else require_copied_runtime_execution()
        )
        invocation = self.base / sha256(gate_source)[:12]
        invocation.mkdir()
        runtime = invocation / "runtime"
        copy_pinned_runtime(
            runtime,
            runtime_source=(
                seatbelt_context.pinned_runtime_source
                if seatbelt_context is not None
                else execution_context.pinned_runtime_source
            ),
        )
        dependencies = invocation / "dependencies"
        tools = invocation / "tools"
        scratch = invocation / "scratch"
        snapshot = invocation / "snapshot"
        for path in (
            dependencies,
            tools / "bin",
            scratch / "candidate",
            scratch / "runtime",
            scratch / "pytest",
            scratch / "server",
        ):
            path.mkdir(parents=True)
        manifest_raw, pack, _files = FullGateGitObjectPackTest().fixture("original")
        manifest = full_gate.validate_manifest_object(manifest_raw)
        verified = full_gate.verify_git_object_pack(manifest, pack)
        altered_files = dict(verified.files)
        altered_files["scripts/pre-commit-check.sh"] = gate_source
        altered = dataclasses.replace(verified, files=altered_files)
        full_gate.materialize_verified_snapshot(altered, snapshot)
        wrapper, _binding = full_gate.materialize_trusted_wrapper(
            invocation, full_gate.trusted_wrapper_binding()
        )
        if sandboxed:
            for root in (snapshot, runtime, dependencies, tools):
                full_gate.make_tree_readonly(root)
        contract, contract_sha256 = full_gate.materialize_wrapper_contract(
            invocation,
            manifest,
            snapshot=snapshot,
            runtime=runtime,
            dependencies=dependencies,
            tools=tools,
            wrapper=wrapper,
            scratch=scratch,
        )
        environment = full_gate.build_hermetic_environment(
            invocation, runtime, tools
        )
        raw_read_fd: int | None = None
        raw_write_fd: int | None = None
        read_owner: full_gate._OwnedDescriptor | None = None
        write_owner: full_gate._OwnedDescriptor | None = None
        with tempfile.TemporaryFile(
            mode="w+b", dir=Path(environment["TMPDIR"])
        ) as stdout_handle, tempfile.TemporaryFile(
            mode="w+b", dir=Path(environment["TMPDIR"])
        ) as stderr_handle:
            try:
                raw_read_fd, raw_write_fd = full_gate.create_cloexec_pipe()
                read_owner = full_gate._OwnedDescriptor.take(raw_read_fd)
                raw_read_fd = None
                write_owner = full_gate._OwnedDescriptor.take(raw_write_fd)
                raw_write_fd = None
                read_fd = read_owner.fileno()
                write_fd = write_owner.fileno()
                argv = [
                    str(runtime / "bin/python3.12"),
                    str(wrapper),
                    "--authority-fd",
                    str(write_fd),
                    "--nonce",
                    "a" * 64,
                    "--snapshot",
                    str(snapshot),
                    "--runtime",
                    str(runtime),
                    "--dependencies",
                    str(dependencies),
                    "--tools",
                    str(tools),
                    "--wrapper",
                    str(wrapper),
                    "--contract",
                    str(contract),
                    "--contract-sha256",
                    contract_sha256,
                    "--scratch",
                    str(scratch),
                ]
                if sandboxed:
                    assert seatbelt_context is not None
                    profile, _source_sha256, _rendered_sha256 = (
                        full_gate.render_loopback_profile(
                            invocation,
                            snapshot,
                            runtime,
                            tools,
                            protected_roots=(
                                self.base / "protected-home",
                                self.base / "protected-codex",
                            ),
                            executable_allowlist=sorted(
                                [
                                    "/bin/bash",
                                    str(runtime / "bin/python3.12"),
                                    str(wrapper),
                                ]
                            ),
                            writable_roots=tuple(
                                Path(environment[key])
                                for key in (
                                    "HOME",
                                    "CODEX_HOME",
                                    "CLAUDE_CONFIG_DIR",
                                    "GNUPGHOME",
                                    "TMPDIR",
                                    "XDG_CACHE_HOME",
                                    "XDG_CONFIG_HOME",
                                    "XDG_DATA_HOME",
                                    "XDG_STATE_HOME",
                                )
                            )
                            + (scratch,),
                        )
                    )
                    argv = list(
                        full_gate.build_sandbox_argv(
                            profile,
                            snapshot,
                            runtime,
                            dependencies,
                            tools,
                            wrapper,
                            contract,
                            contract_sha256,
                            scratch,
                            environment,
                            sandbox_executable=seatbelt_context.sandbox_executable,
                            authority_fd=write_fd,
                            nonce="a" * 64,
                        )
                    )
                try:
                    process = subprocess.Popen(
                        argv,
                        cwd=snapshot,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        start_new_session=True,
                        close_fds=True,
                        pass_fds=(write_fd,),
                    )
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    raise ReleaseControlHarnessError(
                        "HARNESS_SPAWN_FAILED", str(exc)
                    ) from None
                try:
                    _close_owned_harness_owner(
                        write_owner, primary_exception=None
                    )
                    outcome = full_gate.supervise_process(
                        process,
                        timeout=timeout,
                        stdout_handle=stdout_handle,
                        stderr_handle=stderr_handle,
                        invocation_root=scratch,
                        authority_read_fd=read_fd,
                        nonce="a" * 64,
                        limits=full_gate.DEFAULT_RESOURCE_LIMITS,
                    )
                except BaseException as primary:
                    try:
                        if _harness_process_group_exists(process):
                            _terminate_harness_process_group(
                                process,
                                primary_status=getattr(
                                    primary, "status", "HARNESS_INTERRUPTED"
                                ),
                            )
                        else:
                            process.communicate(timeout=2)
                    except BaseException as cleanup_error:
                        raise cleanup_error from primary
                    raise
                if outcome.timed_out:
                    raise ReleaseControlHarnessError("HARNESS_TIMEOUT")
                if outcome.resource_status is not None:
                    raise ReleaseControlHarnessError(
                        "HARNESS_RESOURCE_LIMIT", outcome.resource_status
                    )
                if outcome.cleanup_performed:
                    raise ReleaseControlHarnessError(
                        "HARNESS_DESCENDANT_CLEANUP_REQUIRED"
                    )
                transcript = b"".join(
                    full_gate.encode_authority_frame(
                        frame, limits=full_gate.DEFAULT_RESOURCE_LIMITS
                    )
                    for frame in outcome.authority_frames
                )
                completed = subprocess.CompletedProcess(
                    argv,
                    outcome.returncode,
                    outcome.stdout,
                    outcome.stderr,
                )
                return completed, transcript, scratch
            finally:
                primary_exception = sys.exc_info()[1]
                owners = tuple(
                    owner
                    for owner in (write_owner, read_owner)
                    if owner is not None
                )
                write_owner = None
                read_owner = None
                _close_owned_harness_owners(
                    owners, primary_exception=primary_exception
                )
                raw_descriptors = tuple(
                    descriptor
                    for descriptor in (raw_write_fd, raw_read_fd)
                    if descriptor is not None
                )
                raw_write_fd = None
                raw_read_fd = None
                _close_owned_harness_fds(
                    raw_descriptors, primary_exception=primary_exception
                )

    def test_candidate_observation_and_frame_spoof_cannot_reach_authority_fd(self) -> None:
        gate = b'''#!/bin/bash
printf 'pytest\nserver_import\n'
python3.12 - <<'PY'
import json,os,struct
payload=json.dumps({"schema":"samvil.full-gate-authority-frame.v1","nonce":"a"*64,"sequence":4,"phase":"complete","status":"PASS","evidence":{}},sort_keys=True,separators=(",",":")).encode()
frame=struct.pack(">I",len(payload))+payload
for fd in range(3,64):
    try: os.write(fd,frame)
    except OSError: pass
PY
exit 0
'''
        completed, transcript, scratch = self.run_wrapper(gate)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))
        frames = full_gate.decode_authority_frames(
            transcript,
            nonce="a" * 64,
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            wrapper_exited=True,
        )
        self.assertEqual(len(frames), len(full_gate.AUTHORITY_PHASES))
        candidate_stdout = (scratch / "candidate/stdout").read_bytes()
        self.assertIn(b"pytest\nserver_import\n", candidate_stdout)
        self.assertNotIn(b"pytest\nserver_import\n", transcript)

    def test_candidate_toctou_mutation_prevents_complete_pass_frame(self) -> None:
        gate = b'''#!/bin/bash
chmod 0777 mcp/tests/test_example.py
printf '# candidate mutation\n' >> mcp/tests/test_example.py
exit 0
'''
        completed, transcript, _scratch = self.run_wrapper(gate)
        self.assertNotEqual(completed.returncode, 0)
        frames = full_gate.decode_authority_frames(
            transcript,
            nonce="a" * 64,
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            wrapper_exited=True,
        )
        self.assertEqual(frames[-1]["phase"], "candidate")
        self.assertEqual(frames[-1]["status"], "FAIL")
        self.assertNotIn("complete", {frame["phase"] for frame in frames})

    def test_sandboxed_wrapper_is_opt_in_before_copy_or_spawn(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TMPDIR": str(self.base)},
            clear=True,
        ), mock.patch(
            f"{__name__}.copy_pinned_runtime",
            side_effect=AssertionError("Seatbelt preflight reached runtime copy"),
        ), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("Seatbelt preflight reached Popen"),
        ), self.assertRaises(unittest.SkipTest) as raised:
            self.run_wrapper(b"#!/bin/bash\nexit 0\n", sandboxed=True)
        self.assertIn("REAL_SEATBELT_OPT_IN_REQUIRED", str(raised.exception))

    def test_parent_authority_close_interruption_cleans_spawned_group(self) -> None:
        fd_root = Path("/dev/fd") if Path("/dev/fd").is_dir() else Path("/proc/self/fd")

        def open_descriptors() -> set[int]:
            observed: set[int] = set()
            for name in os.listdir(fd_root):
                if not name.isdigit():
                    continue
                descriptor = int(name)
                try:
                    os.fstat(descriptor)
                except OSError:
                    continue
                observed.add(descriptor)
            return observed

        def fake_copy(destination: Path, **_kwargs: object) -> None:
            (destination / "bin").mkdir(parents=True)
            executable = destination / "bin/python3.12"
            executable.write_bytes(b"fixture")
            executable.chmod(0o755)

        execution_context = CopiedRuntimeExecutionContext(
            pinned_runtime_source=self.base / "approved-runtime-source",
            invocation_tmpdir=self.base,
        )
        for index, primary in enumerate((KeyboardInterrupt(), SystemExit(17))):
            with self.subTest(primary=type(primary).__name__):
                before_descriptors = open_descriptors()
                fake_process = mock.Mock(pid=424250 + index, returncode=None)
                with mock.patch(
                    f"{__name__}.require_copied_runtime_execution",
                    return_value=execution_context,
                ), mock.patch(
                    f"{__name__}.copy_pinned_runtime", side_effect=fake_copy
                ), mock.patch.object(
                    subprocess, "Popen", return_value=fake_process
                ), mock.patch(
                    f"{__name__}._close_owned_harness_owner",
                    side_effect=primary,
                ), mock.patch(
                    f"{__name__}._harness_process_group_exists",
                    return_value=True,
                ), mock.patch(
                    f"{__name__}._terminate_harness_process_group"
                ) as terminate, mock.patch.object(
                    full_gate,
                    "supervise_process",
                    side_effect=AssertionError(
                        "supervision ran after parent authority close failure"
                    ),
                ) as supervise, self.assertRaises(type(primary)) as raised:
                    self.run_wrapper(
                        f"#!/bin/bash\n# case-{index}\nexit 0\n".encode()
                    )
                self.assertIs(raised.exception, primary)
                terminate.assert_called_once_with(
                    fake_process, primary_status="HARNESS_INTERRUPTED"
                )
                supervise.assert_not_called()
                self.assertEqual(open_descriptors(), before_descriptors)

    def test_wrapper_supervisor_timeout_is_typed_without_blocking_pipe_reads(
        self,
    ) -> None:
        def fake_copy(destination: Path, **_kwargs: object) -> None:
            (destination / "bin").mkdir(parents=True)
            executable = destination / "bin/python3.12"
            executable.write_bytes(b"fixture")
            executable.chmod(0o755)

        fake_process = mock.Mock(pid=424242, returncode=-signal.SIGTERM)
        timeout_outcome = full_gate.GateOutcome(
            returncode=-signal.SIGTERM,
            timed_out=True,
            cleanup_performed=True,
            resource_status=None,
            stdout=b"",
            stderr=b"",
        )
        execution_context = CopiedRuntimeExecutionContext(
            pinned_runtime_source=self.base / "approved-runtime-source",
            invocation_tmpdir=self.base,
        )
        with mock.patch(
            f"{__name__}.require_copied_runtime_execution",
            return_value=execution_context,
        ), mock.patch(
            f"{__name__}.copy_pinned_runtime", side_effect=fake_copy
        ), mock.patch.object(
            subprocess, "Popen", return_value=fake_process
        ) as popen, mock.patch.object(
            full_gate, "supervise_process", return_value=timeout_outcome
        ) as supervise, self.assertRaises(ReleaseControlHarnessError) as raised:
            self.run_wrapper(b"#!/bin/bash\nsleep 30\n", timeout=0.05)
        self.assertEqual(raised.exception.status, "HARNESS_TIMEOUT")
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertIsNot(popen.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertIsNot(popen.call_args.kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(supervise.call_args.kwargs["timeout"], 0.05)

    def test_wrapper_supervisor_cleanup_required_is_typed(self) -> None:
        def fake_copy(destination: Path, **_kwargs: object) -> None:
            (destination / "bin").mkdir(parents=True)
            executable = destination / "bin/python3.12"
            executable.write_bytes(b"fixture")
            executable.chmod(0o755)

        fake_process = mock.Mock(pid=424243, returncode=0)
        cleanup_outcome = full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=True,
            resource_status=None,
            stdout=b"",
            stderr=b"",
        )
        execution_context = CopiedRuntimeExecutionContext(
            pinned_runtime_source=self.base / "approved-runtime-source",
            invocation_tmpdir=self.base,
        )
        with mock.patch(
            f"{__name__}.require_copied_runtime_execution",
            return_value=execution_context,
        ), mock.patch(
            f"{__name__}.copy_pinned_runtime", side_effect=fake_copy
        ), mock.patch.object(
            subprocess, "Popen", return_value=fake_process
        ), mock.patch.object(
            full_gate, "supervise_process", return_value=cleanup_outcome
        ), self.assertRaises(ReleaseControlHarnessError) as raised:
            self.run_wrapper(b"#!/bin/bash\nexit 0\n")
        self.assertEqual(
            raised.exception.status,
            "HARNESS_DESCENDANT_CLEANUP_REQUIRED",
        )

    def test_real_profile_denies_snapshot_mutation_and_still_runs_fixed_probes(self) -> None:
        gate = b'''#!/bin/bash
chmod 0777 mcp/tests/test_example.py 2>/dev/null && exit 91
printf '# forbidden\n' >> mcp/tests/test_example.py 2>/dev/null && exit 92
printf 'pytest\nserver_import\n'
exit 0
'''
        completed, transcript, _scratch = self.run_wrapper(gate, sandboxed=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))
        frames = full_gate.decode_authority_frames(
            transcript,
            nonce="a" * 64,
            limits=full_gate.DEFAULT_RESOURCE_LIMITS,
            wrapper_exited=True,
        )
        self.assertEqual(tuple(frame["status"] for frame in frames), ("PASS",) * 5)


class FullGateCompleteExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-complete-execution-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_approved_wrapper_contract_uses_the_validated_absolute_command(self) -> None:
        protocol = FullGateManifestProtocolTest()
        rows = FullGateApprovedHostToolAuthorityDispatcherTest().canonical_rows()
        manifest = full_gate.validate_manifest_object(
            protocol.approved_host_tool_manifest(rows)
        )
        invocation = self.base / "approved-wrapper-contract"
        snapshot = invocation / "snapshot"
        runtime = invocation / "runtime"
        dependencies = invocation / "dependencies"
        tools = invocation / "tools"
        wrapper = invocation / "wrapper/trusted-wrapper.py"
        scratch = invocation / "scratch"
        for directory in (
            snapshot,
            runtime / "bin",
            dependencies,
            tools,
            wrapper.parent,
            scratch,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        (runtime / "bin/python3.12").write_bytes(b"runtime")
        wrapper.write_bytes(b"wrapper")
        critical_snapshot_paths = {
            "scripts/pre-commit-check.sh",
            *(
                entry["path"]
                for entry in manifest.raw["collected_mcp_tests"]
            ),
        }
        for relative in critical_snapshot_paths:
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(relative.encode("utf-8"))

        contract_path, _digest = full_gate.materialize_wrapper_contract(
            invocation,
            manifest,
            snapshot=snapshot,
            runtime=runtime,
            dependencies=dependencies,
            tools=tools,
            wrapper=wrapper,
            scratch=scratch,
        )

        contract = json.loads(contract_path.read_bytes())
        self.assertEqual(
            contract["candidate_command"],
            ["/bin/bash", "scripts/pre-commit-check.sh"],
        )

    def test_approved_execution_uses_held_canonical_authority_lifecycle(self) -> None:
        protocol = FullGateManifestProtocolTest()
        rows = FullGateApprovedHostToolAuthorityDispatcherTest().canonical_rows()
        raw_manifest = protocol.approved_host_tool_manifest(rows)
        manifest_bytes = full_gate.canonical_json_bytes(raw_manifest)
        invocation = self.base / "invocation"
        invocation.mkdir()
        control = self.base / "control"
        control.mkdir()
        events: list[str] = []

        class FakeArtifact:
            def __init__(self, name: str, data: bytes, index: int) -> None:
                self.path = self_base / name
                self.data = data
                self.identity = full_gate.FileIdentity(
                    device=1,
                    inode=index,
                    mode=stat.S_IFREG | 0o400,
                    nlink=1,
                    size=len(data),
                    mtime_ns=1,
                    ctime_ns=1,
                )
                self.close_calls = 0

            def assert_stable(self) -> None:
                return None

            def close(self) -> None:
                self.close_calls += 1

        class FakeAuthority:
            def __init__(self) -> None:
                self.close_calls = 0

            def complete(self) -> dict[str, object]:
                events.append("complete")
                return {
                    "schema": "samvil.canonical-host-admission.v1",
                    "rows": [],
                    "result_sha256": "a" * 64,
                }

            def executable_path(self, role: str) -> Path:
                if role != "sandbox-exec":
                    raise AssertionError("unexpected canonical executable role")
                return Path("/usr/bin/sandbox-exec")

            def close(self) -> None:
                self.close_calls += 1
                events.append("close")

        class FakeProtocol:
            log_paths: tuple[Path, ...] = ()

            def close(self) -> None:
                events.append("protocol-close")

        self_base = self.base
        manifest_artifact = FakeArtifact("approved-manifest.json", manifest_bytes, 1)
        artifact_index = 1

        def open_artifact(
            path: str, digest: str, **_kwargs: object
        ) -> FakeArtifact:
            nonlocal artifact_index
            artifact_index += 1
            return FakeArtifact(Path(path).name, digest.encode("ascii"), artifact_index)

        authority = FakeAuthority()
        parser_evidence = {
            "schema": "samvil.host-tool-identity-parser-evidence.v1",
            "result_sha256": "c" * 64,
            "byte_identical": True,
        }

        def acquire_authority(
            manifest: full_gate.ValidatedManifest,
            scratch: Path,
            *,
            parser_evidence: Mapping[str, object],
        ) -> FakeAuthority:
            self.assertNotIn("apple_platform_tcb", manifest.raw)
            self.assertIn("canonical_host_tools", manifest.raw)
            self.assertTrue(scratch.is_absolute())
            self.assertIs(parser_evidence, parser_evidence_value)
            events.append("acquire")
            return authority

        def prepare_parser(
            parser_manifest: Mapping[str, object],
            artifacts: Mapping[str, FakeArtifact],
            *,
            runtime_root: Path,
            scratch_root: Path,
        ) -> dict[str, object]:
            self.assertEqual(
                parser_manifest["source_artifact"]["sha256"],
                raw_manifest["host_tool_identity_parser"]["source_sha256"],
            )
            self.assertIn("host_tool_identity_parser_source", artifacts)
            self.assertIn("host_tool_identity_parser_input:codesign", artifacts)
            self.assertIn("host_tool_identity_parser_input:sandbox-exec", artifacts)
            self.assertEqual(runtime_root, invocation / "runtime")
            self.assertEqual(scratch_root, invocation / "host-tool-parser")
            events.append("parser")
            return parser_evidence_value

        parser_evidence_value = parser_evidence

        def run_gate(*_args: object, **_kwargs: object) -> full_gate.GateOutcome:
            events.append("gate")
            return full_gate.GateOutcome(
                returncode=0,
                timed_out=False,
                cleanup_performed=False,
                resource_status=None,
                stdout=b"",
                stderr=b"",
            )

        def stop_after_complete(*_args: object, **_kwargs: object) -> bytes:
            events.append("post-complete-stop")
            raise full_gate.FullGateError("STOP_AFTER_CANONICAL_COMPLETE")

        environment = {
            key: str(invocation / "environment" / key.lower())
            for key in full_gate.HERMETIC_ENVIRONMENT_KEYS
        }
        verified_pack = full_gate.VerifiedGitObjectPack(
            tree="1" * 40,
            files={},
            modes={},
            blobs={},
            closure_sha256="b" * 64,
        )
        arguments = full_gate.FullGateArguments(
            manifest=str(manifest_artifact.path),
            prior_receipt=None,
            nonce="a" * 64,
            timeout=1,
            receipt=str(self.base / "receipt.json"),
            denial_log=str(self.base / "denial.log"),
        )

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(full_gate, "_reject_environment_authority")
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_acquire_invocation_storage_quota_authority",
                    return_value=quota_authority_fixture(),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_detached_process_signal_supported",
                    return_value=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "open_external_control_artifact",
                    return_value=manifest_artifact,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "open_external_artifact", side_effect=open_artifact
                )
            )
            stack.enter_context(
                mock.patch.object(full_gate, "validate_cli_target_binding")
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_preflight_absent_output",
                    side_effect=lambda raw, _status: Path(raw),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_output_collision_key",
                    side_effect=lambda path: str(path),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "_validated_temp_parent", return_value=self.base
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate.tempfile, "mkdtemp", return_value=str(invocation)
                )
            )
            dispatcher = stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "acquire_runtime_manifest_host_tool_authority",
                    side_effect=acquire_authority,
                )
            )
            parser_verifier = stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "prepare_approved_host_tool_parser",
                    side_effect=prepare_parser,
                )
            )
            legacy = stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "acquire_apple_platform_tcb",
                    side_effect=AssertionError(
                        "approved execution reached legacy Apple TCB"
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_closure_archive",
                    side_effect=lambda *_args, expected_role, **_kwargs: (
                        f"{expected_role}-digest"
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "validate_tool_closure", return_value={}
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_runtime_python_facade",
                    return_value=invocation / "tools/bin/python3",
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_runtime_dirname_facade",
                    return_value=invocation / "tools/bin/dirname",
                )
            )
            stack.enter_context(
                mock.patch.object(full_gate, "_remove_invocation_tree")
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "build_hermetic_environment",
                    return_value=environment,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "validate_control_identity", return_value="c" * 64
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "verify_git_object_pack", return_value=verified_pack
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_verified_snapshot",
                    return_value="d" * 64,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "materialize_facade", return_value="e" * 64
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_trusted_wrapper",
                    return_value=(
                        invocation / "control/trusted-wrapper.py",
                        {"schema": "test-wrapper"},
                    ),
                )
            )
            stack.enter_context(mock.patch.object(full_gate, "make_tree_readonly"))
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "validate_hermetic_runtime",
                    return_value=raw_manifest["runtime"]["python_identity"],
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_wrapper_contract",
                    return_value=(invocation / "contract.json", "f" * 64),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "measure_materialized_execution",
                    return_value="1" * 64,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "render_loopback_profile",
                    return_value=(b"profile", "2" * 64, "3" * 64),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "acquire_fixed_log_protocol",
                    return_value=FakeProtocol(),
                )
            )
            stack.enter_context(
                mock.patch.object(full_gate, "create_output_files", return_value=object())
            )
            stack.enter_context(
                mock.patch.object(full_gate, "run_gate_once", side_effect=run_gate)
            )
            stack.enter_context(
                mock.patch.object(
                    full_gate, "_bounded_internal_file", side_effect=stop_after_complete
                )
            )
            stack.enter_context(
                mock.patch.object(full_gate, "_cleanup_owned_fixed_logs")
            )
            stack.enter_context(mock.patch.object(full_gate, "finalize_outputs"))
            stack.enter_context(
                mock.patch.object(
                    full_gate.subprocess,
                    "run",
                    side_effect=AssertionError("complete execution reached subprocess"),
                )
            )

            try:
                full_gate.execute_full_gate(
                    arguments,
                    source_environment={"TMPDIR": str(self.base)},
                    control_root=control,
                )
            except KeyError as exc:
                self.fail(f"approved execution read legacy manifest key: {exc}")
            except AssertionError as exc:
                self.fail(str(exc))
            except full_gate.FullGateError as exc:
                self.assertEqual(exc.status, "STOP_AFTER_CANONICAL_COMPLETE")
            else:
                self.fail("complete execution did not reach the post-complete stop")

        dispatcher.assert_called_once()
        parser_verifier.assert_called_once()
        legacy.assert_not_called()
        self.assertEqual(
            [
                event
                for event in events
                if event in {"parser", "acquire", "gate", "complete", "close"}
            ],
            ["parser", "acquire", "gate", "complete", "close"],
        )
        self.assertEqual(authority.close_calls, 1)


class FullGateStorageQuotaBlockerTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = require_invocation_tmpdir()
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-quota-blocker-",
            dir=temp_parent,
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.control = (self.base / "control").resolve()
        self.control.mkdir()
        self.manifest = self.base / "manifest.json"
        self.manifest.write_bytes(full_gate.canonical_json_bytes({}))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_missing_quota_is_deterministic_path_free_and_pre_materialization(
        self,
    ) -> None:
        class ValidatedQuotaFixture:
            raw: dict[str, object] = {}
            prior_receipt_sha256: str | None = None

        receipts: list[bytes] = []
        output_paths: list[Path] = []
        with mock.patch.object(
            full_gate,
            "validate_manifest_object",
            return_value=ValidatedQuotaFixture(),
        ), mock.patch.object(
            full_gate, "validate_cli_target_binding"
        ), mock.patch.object(
            full_gate, "_external_references", return_value=()
        ), mock.patch.object(
            full_gate.tempfile,
            "mkdtemp",
            side_effect=AssertionError("quota blocker reached invocation creation"),
        ) as create_invocation, mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=AssertionError("quota blocker reached materialization"),
        ) as materialize, mock.patch.object(
            full_gate.subprocess,
            "Popen",
            side_effect=AssertionError("quota blocker reached candidate spawn"),
        ) as spawn:
            for attempt in range(2):
                receipt = self.base / f"receipt-{attempt}.json"
                denial = self.base / f"denial-{attempt}.log"
                output_paths.extend((receipt, denial))
                with self.assertRaises(full_gate.FullGateError) as raised:
                    full_gate.execute_full_gate(
                        full_gate.FullGateArguments(
                            manifest=str(self.manifest),
                            prior_receipt=None,
                            nonce="a" * 64,
                            timeout=10,
                            receipt=str(receipt),
                            denial_log=str(denial),
                        ),
                        source_environment={},
                        control_root=self.control,
                    )
                self.assertEqual(
                    raised.exception.status,
                    full_gate.INVOCATION_STORAGE_QUOTA_BLOCKER,
                )
                receipts.append(receipt.read_bytes())
                self.assertEqual(denial.read_bytes(), b"")

        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(
            json.loads(receipts[0]),
            {
                "schema": "samvil.full-gate-failure.v1",
                "status": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
                "verdict": "BLOCKED",
                "nonce": "a" * 64,
            },
        )
        for path in (self.manifest, self.control, *output_paths):
            self.assertNotIn(str(path).encode("utf-8"), receipts[0])
        create_invocation.assert_not_called()
        materialize.assert_not_called()
        spawn.assert_not_called()

    def test_quota_blocker_maps_to_environment_terminal(self) -> None:
        self.assertEqual(
            full_gate._terminal_status(full_gate.INVOCATION_STORAGE_QUOTA_BLOCKER),
            "BLOCKED_ENVIRONMENT",
        )
        self.assertEqual(
            full_gate._terminal_status(
                full_gate.DETACHED_PROCESS_SIGNAL_UNAVAILABLE
            ),
            "BLOCKED_ENVIRONMENT",
        )
        self.assertEqual(
            full_gate._terminal_status("MANIFEST_JSON_INVALID"),
            "MANIFEST_JSON_INVALID",
        )

    def test_missing_identity_bound_signal_blocks_before_materialization(
        self,
    ) -> None:
        class ValidatedQuotaFixture:
            raw: dict[str, object] = {}
            prior_receipt_sha256: str | None = None

        receipt = self.base / "signal-receipt.json"
        denial = self.base / "signal-denial.log"
        with mock.patch.object(
            full_gate,
            "validate_manifest_object",
            return_value=ValidatedQuotaFixture(),
        ), mock.patch.object(
            full_gate, "validate_cli_target_binding"
        ), mock.patch.object(
            full_gate, "_external_references", return_value=()
        ), mock.patch.object(
            full_gate,
            "_acquire_invocation_storage_quota_authority",
            return_value=quota_authority_fixture(),
        ) as acquire_quota, mock.patch.object(
            full_gate,
            "_detached_process_signal_supported",
            return_value=False,
        ) as signal_supported, mock.patch.object(
            full_gate.tempfile,
            "mkdtemp",
            side_effect=AssertionError("signal blocker reached invocation creation"),
        ) as create_invocation, mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=AssertionError("signal blocker reached materialization"),
        ) as materialize, mock.patch.object(
            full_gate.subprocess,
            "Popen",
            side_effect=AssertionError("signal blocker reached candidate spawn"),
        ) as spawn, self.assertRaises(full_gate.FullGateError) as raised:
            full_gate.execute_full_gate(
                full_gate.FullGateArguments(
                    manifest=str(self.manifest),
                    prior_receipt=None,
                    nonce="b" * 64,
                    timeout=10,
                    receipt=str(receipt),
                    denial_log=str(denial),
                ),
                source_environment={},
                control_root=self.control,
            )

        self.assertEqual(
            raised.exception.status,
            full_gate.DETACHED_PROCESS_SIGNAL_UNAVAILABLE,
        )
        self.assertEqual(
            json.loads(receipt.read_bytes()),
            {
                "schema": "samvil.full-gate-failure.v1",
                "status": "DETACHED_PROCESS_SIGNAL_UNAVAILABLE",
                "verdict": "BLOCKED",
                "nonce": "b" * 64,
            },
        )
        self.assertEqual(denial.read_bytes(), b"")
        acquire_quota.assert_called_once_with()
        signal_supported.assert_called_once_with()
        create_invocation.assert_not_called()
        materialize.assert_not_called()
        spawn.assert_not_called()


class PortableFullGatePlatformAuthority:
    def __init__(self, kind: str) -> None:
        if kind not in {"apple", "canonical"}:
            raise ValueError("unsupported portable platform authority kind")
        self.kind = kind
        self.closed = False

    def complete(self) -> dict[str, object]:
        if self.closed:
            raise AssertionError("portable platform authority is already closed")
        if self.kind == "apple":
            payload: dict[str, object] = {
                "schema": "samvil.apple-platform-evidence.v1",
                "platform": "portable-test-double",
                "pre_post_identity": "stable",
            }
        else:
            payload = {
                "schema": "samvil.canonical-host-admission.v1",
                "rows": [
                    {
                        "role": "sandbox-exec",
                        "path": "/usr/bin/sandbox-exec",
                        "admission_state": "PORTABLE_TEST_DOUBLE",
                    }
                ],
            }
        return {
            **payload,
            "result_sha256": sha256(full_gate.canonical_json_bytes(payload)),
        }

    def executable_path(self, role: str) -> Path:
        if self.closed or self.kind != "canonical" or role != "sandbox-exec":
            raise AssertionError("invalid portable platform executable request")
        return Path("/usr/bin/sandbox-exec")

    def close(self) -> None:
        self.closed = True


class PortableFullGateOrchestrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._portable_stack = contextlib.ExitStack()
        self.portable_platform = platform.system() != "Darwin"
        if not self.portable_platform:
            self.skipTest(full_gate.INVOCATION_STORAGE_QUOTA_BLOCKER)
        execution_context = require_copied_runtime_execution()
        self.runtime_source = execution_context.pinned_runtime_source
        temp_parent = execution_context.invocation_tmpdir
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-full-gate-e2e-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.caller_tmp = self.base / "caller-tmp"
        self.caller_tmp.mkdir()
        self.env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "TMPDIR": str(self.caller_tmp),
            "LANG": "C",
            "LC_ALL": "C",
        }
        self.lock = self.base / "full-gate.lock"
        self.logs = tuple(self.base / Path(path).name for path in full_gate.FIXED_LOG_PATHS)
        if self.portable_platform:
            self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_detached_process_signal_supported",
                    return_value=True,
                )
            )
            self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "_acquire_invocation_storage_quota_authority",
                    return_value=quota_authority_fixture(),
                )
            )
            self._native_materialize_closure = full_gate.materialize_closure_archive
            self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "materialize_closure_archive",
                    side_effect=self._portable_materialize_closure,
                )
            )
            self.portable_apple_acquire = self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "acquire_apple_platform_tcb",
                    side_effect=lambda *_args, **_kwargs: PortableFullGatePlatformAuthority(
                        "apple"
                    ),
                )
            )
            self.portable_parser_prepare = self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "prepare_approved_host_tool_parser",
                    side_effect=self._portable_parser_evidence,
                )
            )
            self.portable_canonical_acquire = self._portable_stack.enter_context(
                mock.patch.object(
                    full_gate,
                    "acquire_runtime_manifest_host_tool_authority",
                    side_effect=lambda *_args, **_kwargs: PortableFullGatePlatformAuthority(
                        "canonical"
                    ),
                )
            )

    def tearDown(self) -> None:
        try:
            self._portable_stack.close()
        finally:
            self._temp.cleanup()

    def _portable_materialize_closure(
        self,
        archive_raw: bytes,
        manifest_raw: bytes,
        destination: Path,
        *,
        expected_role: str,
    ) -> str:
        if expected_role != "python":
            return self._native_materialize_closure(
                archive_raw,
                manifest_raw,
                destination,
                expected_role=expected_role,
            )
        destination.mkdir(mode=0o700)
        executable = destination / "bin/python3.12"
        executable.parent.mkdir()
        source = self.runtime_source / "bin/python3.12"
        shutil.copyfile(source, executable)
        executable.chmod(0o755)
        stdlib = destination / "lib/python3.12"
        stdlib.mkdir(parents=True)
        (stdlib / "os.py").write_bytes(b"# portable E2E fixture\n")
        payload = {
            "schema": "samvil.portable-e2e-python-materialization.v1",
            "archive_sha256": sha256(archive_raw),
            "manifest_sha256": sha256(manifest_raw),
            "executable_sha256": sha256(executable.read_bytes()),
        }
        return sha256(full_gate.canonical_json_bytes(payload))

    def _portable_parser_evidence(
        self,
        parser_manifest: Mapping[str, object],
        _artifacts: Mapping[str, object],
        **_kwargs: object,
    ) -> dict[str, object]:
        payload = {
            "schema": "samvil.host-tool-identity-parser-evidence.v1",
            "source_sha256": parser_manifest["source_sha256"],
            "interpreter_sha256": parser_manifest["materialized"]["interpreter"][
                "sha256"
            ],
            "input_count": len(parser_manifest["inputs"]),
            "result_sha256": parser_manifest["result_sha256"],
            "byte_identical": True,
            "staged_runner_authority": False,
        }
        return {
            **payload,
            "evidence_sha256": sha256(full_gate.canonical_json_bytes(payload)),
        }

    def write_artifact(self, name: str, data: bytes) -> dict[str, str]:
        path = self.base / name
        path.write_bytes(data)
        return {"path": str(path), "sha256": sha256(data)}

    def git(self, repo: Path, *args: str) -> str:
        environment = dict(
            self.env,
            HOME=str(self.base / "git-home"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )
        Path(environment["HOME"]).mkdir(exist_ok=True)
        return subprocess.run(
            ["/usr/bin/git", "-C", str(repo), *args],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()

    def control_identity(self) -> tuple[Path, dict[str, object]]:
        control = self.base / "control"
        control.mkdir()
        self.git(control, "init", "-q")
        self.git(control, "config", "user.name", "Release Control Test")
        self.git(control, "config", "user.email", "release@example.invalid")
        for path in full_gate.CONTROL_PATHS:
            target = control / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TOOLS_ROOT / path.removeprefix("tools/release-control/"), target)
        self.git(control, "add", "--", *full_gate.CONTROL_PATHS)
        self.git(control, "commit", "-q", "-m", "control")
        files = []
        for path in full_gate.CONTROL_PATHS:
            mode, kind, blob = self.git(control, "ls-tree", "HEAD", "--", path).split()[:3]
            self.assertEqual(kind, "blob")
            files.append(
                {
                    "path": path,
                    "mode": mode,
                    "blob": blob,
                    "sha256": sha256((control / path).read_bytes()),
                }
            )
        return control, {
            "commit": self.git(control, "rev-parse", "HEAD^{commit}"),
            "tree": self.git(control, "rev-parse", "HEAD^{tree}"),
            "files": files,
        }

    def runtime_artifacts(self) -> dict[str, object]:
        helper = FullGateMaterializationAndRuntimeTest()
        python_files = {
            "bin/python3.12": (
                0o100755,
                (self.runtime_source / "bin/python3.12").read_bytes(),
            ),
            "lib/python3.12/os.py": (0o100644, b"# pinned\n"),
        }
        dependency_files = {
            "lib/python3.12/site-packages/dep.py": (0o100644, b"VALUE = 1\n")
        }
        tool_files = {
            f"bin/{name}": (
                0o100755,
                b"#!/bin/sh\nexec /usr/bin/true \"$@\"\n",
            )
            for name in full_gate.REQUIRED_TOOL_NAMES
        }
        facade = {
            "schema": "samvil.full-gate-facade.v1",
            "entries": [
                {
                    "path": path,
                    "mode": "100755" if path != full_gate.FACADE_PATHS[3] else "100644",
                    "content_base64": base64.b64encode(
                        full_gate.FACADE_PYTHON_WRAPPER
                        if path != full_gate.FACADE_PATHS[3]
                        else full_gate.FACADE_PYVENV_CONFIG
                    ).decode("ascii"),
                    "sha256": sha256(
                        full_gate.FACADE_PYTHON_WRAPPER
                        if path != full_gate.FACADE_PATHS[3]
                        else full_gate.FACADE_PYVENV_CONFIG
                    ),
                }
                for path in full_gate.FACADE_PATHS
            ],
        }
        return {
            "python_version": "3.12.13",
            "python_identity": FullGateManifestProtocolTest().manifest()["runtime"][
                "python_identity"
            ],
            "python_archive": self.write_artifact(
                "python.tar", helper.tar_bytes(python_files)
            ),
            "python_manifest": self.write_artifact(
                "python-manifest.json", helper.closure_manifest("python", python_files)
            ),
            "dependency_archive": self.write_artifact(
                "dependencies.tar", helper.tar_bytes(dependency_files)
            ),
            "dependency_manifest": self.write_artifact(
                "dependencies-manifest.json",
                helper.closure_manifest("dependencies", dependency_files),
            ),
            "tool_archive": self.write_artifact(
                "tools.tar", helper.tar_bytes(tool_files)
            ),
            "tool_manifest": self.write_artifact(
                "tools-manifest.json", helper.closure_manifest("tools", tool_files)
            ),
            "facade_manifest": self.write_artifact(
                "facade.json", full_gate.canonical_json_bytes(facade)
            ),
        }

    def manifest_fixture(
        self, kind: str, control_identity: dict[str, object]
    ) -> dict[str, object]:
        manifest, pack, _files = FullGateGitObjectPackTest().fixture(kind)
        manifest["control"] = control_identity
        if "apple_platform_tcb" in manifest:
            manifest["apple_platform_tcb"] = (
                FullGateManifestProtocolTest().legacy_apple_platform_tcb()
                if self.portable_platform
                else full_gate.apple_platform_tcb_binding()
            )
        manifest["object_pack"] = self.write_artifact(f"{kind}-objects.json", pack)
        manifest["runtime"] = self.runtime_artifacts()
        _stdout, _logs, counters = FullGateExecutionAndReceiptTest().semantic_fixture()
        manifest["semantic_counters"] = counters
        return manifest

    def approved_manifest_fixture(
        self, kind: str, control_identity: dict[str, object]
    ) -> dict[str, object]:
        manifest = self.manifest_fixture(kind, control_identity)
        manifest.pop("apple_platform_tcb")
        parser_source = b'''from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
items = []
for entry in request["inputs"]:
    data = Path(entry["path"]).read_bytes()
    items.append({
        "role": entry["role"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    })
payload = {"schema": "host-tool-identity-corpus-result.v1", "items": items}
sys.stdout.buffer.write(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
)
'''
        parser_artifact = self.write_artifact(
            f"{kind}-host-tool-identity-parser.py", parser_source
        )
        input_rows = []
        result_items = []
        if self.portable_platform:
            input_paths = (
                (
                    "codesign",
                    self.base / f"{kind}-portable-codesign.fixture",
                    b"portable codesign fixture\n",
                ),
                (
                    "sandbox-exec",
                    self.base / f"{kind}-portable-sandbox-exec.fixture",
                    b"portable sandbox-exec fixture\n",
                ),
            )
            for _role, path, content in input_paths:
                path.write_bytes(content)
        else:
            input_paths = (
                ("codesign", Path("/usr/bin/codesign"), None),
                ("sandbox-exec", Path("/usr/bin/sandbox-exec"), None),
            )
        for role, path, _content in input_paths:
            metadata = os.lstat(path)
            content = path.read_bytes()
            input_rows.append(
                {
                    "role": role,
                    "path": str(path),
                    "device": str(metadata.st_dev),
                    "inode": str(metadata.st_ino),
                    "size": metadata.st_size,
                    "sha256": sha256(content),
                }
            )
            result_items.append(
                {"role": role, "sha256": sha256(content), "size": len(content)}
            )
        staged_result = full_gate.canonical_json_bytes(
            {
                "schema": "host-tool-identity-corpus-result.v1",
                "items": result_items,
            }
        )
        parser_manifest = FullGateManifestProtocolTest().host_tool_identity_parser_fixture()
        parser_manifest.update(
            source_sha256=sha256(parser_source),
            source_artifact=parser_artifact,
            inputs=input_rows,
            result_sha256=sha256(staged_result),
        )
        parser_manifest["materialized"] = {
            "content_sha256": sha256(parser_source),
            "mode": "100500",
            "interpreter": {
                "classification": "copied_application_runtime",
                "relative_path": "bin/python3.12",
                "sha256": sha256(
                    (self.runtime_source / "bin/python3.12").read_bytes()
                ),
            },
        }
        parser_manifest["staged_runner_comparison"] = {
            "source_sha256": sha256(parser_source),
            "result_sha256": sha256(staged_result),
            "byte_identical": True,
            "authority": False,
        }
        manifest["host_tool_identity_parser"] = parser_manifest
        manifest["copied_application_runtime"] = (
            FullGateManifestProtocolTest().copied_application_runtime_fixture()
        )
        manifest["canonical_host_tools"] = {
            "schema": "samvil.canonical-host-tools.v1",
            "rows": (
                FullGateApprovedHostToolAuthorityDispatcherTest().canonical_rows()
                if self.portable_platform
                else real_canonical_platform_rows(self.base)
            ),
        }
        manifest["command"] = ["/bin/bash", "scripts/pre-commit-check.sh"]
        return manifest

    def emit_gate_logs(
        self,
        environment: Mapping[str, str],
        scratch: Path,
        *,
        volatile_token: bytes = b"1.23",
    ) -> full_gate.GateOutcome:
        stdout, logs, counters = FullGateExecutionAndReceiptTest().semantic_fixture()
        logs = dict(logs)
        logs["samvil-pretest.log"] = logs["samvil-pretest.log"].replace(
            b"1.23", volatile_token
        )
        logs["samvil-mdrefs.log"] += b"elapsed=" + volatile_token + b"\n"
        for path in self.logs:
            path.write_bytes(logs[path.name])
        (scratch / "candidate/stdout").write_bytes(stdout)
        (scratch / "candidate/stderr").write_bytes(b"diagnostic-only\n")
        frames = tuple(
            {
                "schema": "samvil.full-gate-authority-frame.v1",
                "nonce": "a" * 64,
                "sequence": index,
                "phase": phase,
                "status": "PASS",
                "evidence": (
                    {"pytest_passed": counters["pytest_passed"]}
                    if phase == "pytest"
                    else {"tool_count": counters["mcp_tools"]}
                    if phase == "server_import"
                    else {}
                ),
            }
            for index, phase in enumerate(full_gate.AUTHORITY_PHASES)
        )
        return full_gate.GateOutcome(
            returncode=0,
            timed_out=False,
            cleanup_performed=False,
            resource_status=None,
            stdout=b"",
            stderr=b"",
            authority_frames=frames,
            wrapper_pid=4242,
            wrapper_start_identity="linux-proc-start:1",
        )

    def test_original_and_precommit_portable_orchestration_is_deterministic_and_clean(
        self,
    ) -> None:
        self.assertTrue(
            hasattr(full_gate, "execute_full_gate"),
            "full-gate orchestration is not implemented",
        )
        control, identity = self.control_identity()
        for kind in ("original", "candidate_precommit"):
            with self.subTest(kind=kind), mock.patch.object(
                full_gate, "FULL_GATE_LOCK_PATH", self.lock
            ), mock.patch.object(
                full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
            ), mock.patch.object(
                full_gate,
                "validate_hermetic_runtime",
                return_value=FullGateManifestProtocolTest().manifest()["runtime"][
                    "python_identity"
                ],
            ), mock.patch.object(
                full_gate,
                "validate_tool_closure",
                return_value={"schema": "test-tool-evidence"},
            ), mock.patch.object(
                full_gate,
                "run_gate_once",
                side_effect=lambda *args, **kwargs: self.emit_gate_logs(
                    args[9],
                    Path(args[8]),
                    volatile_token=(
                        b"1.23" if run_gate.call_count == 1 else b"9.87"
                    ),
                ),
            ) as run_gate:
                manifest = self.manifest_fixture(kind, identity)
                manifest_path = self.base / f"{kind}-manifest.json"
                manifest_path.write_bytes(full_gate.canonical_json_bytes(manifest))
                receipts = []
                for attempt in range(2):
                    receipt = self.base / f"{kind}-receipt-{attempt}.json"
                    denial = self.base / f"{kind}-denial-{attempt}.log"
                    arguments = full_gate.FullGateArguments(
                        manifest=str(manifest_path),
                        prior_receipt=None,
                        nonce="a" * 64,
                        timeout=10,
                        receipt=str(receipt),
                        denial_log=str(denial),
                    )
                    result = full_gate.execute_full_gate(
                        arguments,
                        source_environment=self.env,
                        control_root=control,
                    )
                    self.assertEqual(result, 0)
                    receipts.append(receipt.read_bytes())
                    self.assertEqual(denial.read_bytes(), b"diagnostic-only\n")
                self.assertEqual(receipts[0], receipts[1])
                self.assertEqual(run_gate.call_count, 2)
                leftovers = list(self.caller_tmp.iterdir())
                self.assertFalse(leftovers, leftovers)

    def test_approved_portable_authority_contract_uses_fixture_parser_and_tools(
        self,
    ) -> None:
        control, identity = self.control_identity()
        materialize_closure = full_gate.materialize_closure_archive

        def materialize_with_runnable_parser_runtime(
            archive_raw: bytes,
            manifest_raw: bytes,
            destination: Path,
            *,
            expected_role: str,
        ) -> str:
            if expected_role != "python" or self.portable_platform:
                return materialize_closure(
                    archive_raw,
                    manifest_raw,
                    destination,
                    expected_role=expected_role,
                )
            (destination / "bin").mkdir(parents=True)
            (destination / "lib").mkdir()
            shutil.copyfile(
                self.runtime_source / "bin/python3.12",
                destination / "bin/python3.12",
            )
            (destination / "bin/python3.12").chmod(0o755)
            shutil.copyfile(
                self.runtime_source / "lib/libpython3.12.dylib",
                destination / "lib/libpython3.12.dylib",
            )
            shutil.copytree(
                self.runtime_source / "lib/python3.12",
                destination / "lib/python3.12",
                ignore=shutil.ignore_patterns("site-packages", "__pycache__"),
            )
            return "approved-parser-runtime"

        with mock.patch.object(
            full_gate, "FULL_GATE_LOCK_PATH", self.lock
        ), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ), mock.patch.object(
            full_gate,
            "validate_hermetic_runtime",
            return_value=FullGateManifestProtocolTest().manifest()["runtime"][
                "python_identity"
            ],
        ), mock.patch.object(
            full_gate,
            "validate_tool_closure",
            return_value={"schema": "test-tool-evidence"},
        ), mock.patch.object(
            full_gate,
            "materialize_closure_archive",
            side_effect=materialize_with_runnable_parser_runtime,
        ), mock.patch.object(
            full_gate,
            "run_gate_once",
            side_effect=lambda *args, **kwargs: self.emit_gate_logs(
                args[9], Path(args[8])
            ),
        ) as run_gate:
            manifest = self.approved_manifest_fixture("original", identity)
            manifest_path = self.base / "approved-original-manifest.json"
            manifest_path.write_bytes(full_gate.canonical_json_bytes(manifest))
            receipt_bytes = []
            for attempt in range(2):
                receipt = self.base / f"approved-original-receipt-{attempt}.json"
                denial = self.base / f"approved-original-denial-{attempt}.log"
                result = full_gate.execute_full_gate(
                    full_gate.FullGateArguments(
                        manifest=str(manifest_path),
                        prior_receipt=None,
                        nonce="a" * 64,
                        timeout=10,
                        receipt=str(receipt),
                        denial_log=str(denial),
                    ),
                    source_environment=self.env,
                    control_root=control,
                )
                self.assertEqual(result, 0)
                self.assertEqual(denial.read_bytes(), b"diagnostic-only\n")
                receipt_bytes.append(receipt.read_bytes())

        self.assertEqual(run_gate.call_count, 2)
        self.assertEqual(receipt_bytes[0], receipt_bytes[1])
        payload = json.loads(receipt_bytes[0])
        self.assertEqual(payload["verdict"], "PASS")
        self.assertFalse(list(self.caller_tmp.iterdir()))

    def test_postcommit_binds_the_accepted_precommit_receipt(self) -> None:
        control, identity = self.control_identity()
        with mock.patch.object(
            full_gate, "FULL_GATE_LOCK_PATH", self.lock
        ), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ), mock.patch.object(
            full_gate,
            "validate_hermetic_runtime",
            return_value=FullGateManifestProtocolTest().manifest()["runtime"][
                "python_identity"
            ],
        ), mock.patch.object(
            full_gate,
            "validate_tool_closure",
            return_value={"schema": "test-tool-evidence"},
        ), mock.patch.object(
            full_gate,
            "run_gate_once",
            side_effect=lambda *args, **kwargs: self.emit_gate_logs(
                args[9], Path(args[8])
            ),
        ) as run_gate:
            precommit = self.manifest_fixture("candidate_precommit", identity)
            precommit_bytes = full_gate.canonical_json_bytes(precommit)
            precommit_manifest = self.base / "precommit-manifest.json"
            precommit_manifest.write_bytes(precommit_bytes)
            precommit_receipt = self.base / "precommit-receipt.json"
            self.assertEqual(
                full_gate.execute_full_gate(
                    full_gate.FullGateArguments(
                        manifest=str(precommit_manifest),
                        prior_receipt=None,
                        nonce="a" * 64,
                        timeout=10,
                        receipt=str(precommit_receipt),
                        denial_log=str(self.base / "precommit-denial.log"),
                    ),
                    source_environment=self.env,
                    control_root=control,
                ),
                0,
            )

            postcommit = self.manifest_fixture("candidate_postcommit", identity)
            post_target = dict(postcommit["target"])
            post_target.update(
                precommit_tree=precommit["target"]["tree"],
                authorization_sha256=precommit["target"]["authorization_sha256"],
                expected_precommit_nonce=precommit["nonce"],
                expected_precommit_control_commit=identity["commit"],
                expected_precommit_control_tree=identity["tree"],
                expected_precommit_manifest_sha256=sha256(precommit_bytes),
                prior_receipt_sha256=sha256(precommit_receipt.read_bytes()),
            )
            postcommit["target"] = post_target
            postcommit_manifest = self.base / "postcommit-manifest.json"
            postcommit_manifest.write_bytes(full_gate.canonical_json_bytes(postcommit))
            postcommit_receipt = self.base / "postcommit-receipt.json"
            self.assertEqual(
                full_gate.execute_full_gate(
                    full_gate.FullGateArguments(
                        manifest=str(postcommit_manifest),
                        prior_receipt=str(precommit_receipt),
                        nonce="a" * 64,
                        timeout=10,
                        receipt=str(postcommit_receipt),
                        denial_log=str(self.base / "postcommit-denial.log"),
                    ),
                    source_environment=self.env,
                    control_root=control,
                ),
                0,
            )
            payload = json.loads(postcommit_receipt.read_bytes())
            self.assertEqual(
                payload["prior_receipt_sha256"], sha256(precommit_receipt.read_bytes())
            )
            self.assertEqual(payload["final_commit"], post_target["final_commit"])
            self.assertEqual(payload["candidate_tree"], post_target["precommit_tree"])
            self.assertEqual(run_gate.call_count, 2)
            self.assertFalse(list(self.caller_tmp.iterdir()))

    def test_cleanup_failure_overrides_a_pass_and_writes_typed_blocker(self) -> None:
        control, identity = self.control_identity()
        manifest = self.manifest_fixture("original", identity)
        manifest_path = self.base / "cleanup-manifest.json"
        manifest_path.write_bytes(full_gate.canonical_json_bytes(manifest))
        receipt = self.base / "cleanup-receipt.json"
        denial = self.base / "cleanup-denial.log"
        remove_invocation_tree = full_gate._remove_invocation_tree

        def fail_only_final_invocation_cleanup(root: Path, status: str) -> None:
            if status == "INVOCATION_CLEANUP_FAILED":
                raise full_gate.FullGateError(status)
            remove_invocation_tree(root, status)

        with mock.patch.object(
            full_gate, "FULL_GATE_LOCK_PATH", self.lock
        ), mock.patch.object(
            full_gate, "FIXED_LOG_PATHS", tuple(str(path) for path in self.logs)
        ), mock.patch.object(
            full_gate,
            "validate_hermetic_runtime",
            return_value=FullGateManifestProtocolTest().manifest()["runtime"][
                "python_identity"
            ],
        ), mock.patch.object(
            full_gate,
            "validate_tool_closure",
            return_value={"schema": "test-tool-evidence"},
        ), mock.patch.object(
            full_gate,
            "run_gate_once",
            side_effect=lambda *args, **kwargs: self.emit_gate_logs(
                args[9], Path(args[8])
            ),
        ), mock.patch.object(
            full_gate,
            "_remove_invocation_tree",
            side_effect=fail_only_final_invocation_cleanup,
        ):
            with self.assertRaises(full_gate.FullGateError) as raised:
                full_gate.execute_full_gate(
                    full_gate.FullGateArguments(
                        manifest=str(manifest_path),
                        prior_receipt=None,
                        nonce="a" * 64,
                        timeout=10,
                        receipt=str(receipt),
                        denial_log=str(denial),
                    ),
                    source_environment=self.env,
                    control_root=control,
                )
        self.assertEqual(raised.exception.status, "INVOCATION_CLEANUP_FAILED")
        payload = json.loads(receipt.read_bytes())
        self.assertEqual(payload["status"], "INVOCATION_CLEANUP_FAILED")
        self.assertEqual(payload["verdict"], "BLOCKED")


class InheritedContextProtocolTest(unittest.TestCase):
    def test_inherited_wrapper_reports_only_the_observed_rlimit_fact(self) -> None:
        self.assertNotIn(
            '"descendant_creation":"kernel_denied"',
            launcher.INHERITED_EXEC_WRAPPER,
        )
        self.assertIn(
            '"descendant_creation":"rlimit_configured"',
            launcher.INHERITED_EXEC_WRAPPER,
        )

    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-inherited-context-test-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.invocation = self.base / "invocation"
        self.execution = self.invocation / "execution"
        self.tmpdir = self.invocation / "tmp"
        self.control = self.invocation / "control"
        self.protected_roots = (
            self.invocation / "protected-home",
            self.invocation / "protected-codex",
        )
        for path in (
            self.invocation,
            self.execution,
            self.tmpdir,
            self.control,
            *self.protected_roots,
        ):
            path.mkdir(exist_ok=True)
        self.nonce = "a" * 64
        self.environment_keys = ("HOME", "PATH", "TMPDIR")
        self.subprocess_env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.invocation),
            "TMPDIR": str(self.tmpdir),
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write_protocol(
        self,
        *,
        suffix: str = "",
        context_changes: dict[str, object] | None = None,
        receipt_changes: dict[str, object] | None = None,
        context_remove: str | None = None,
        receipt_remove: str | None = None,
        profile_bytes: bytes = b"(version 1)\n(deny network*)\n",
    ) -> tuple[Path, dict[str, str], Path, Path, dict[str, object]]:
        profile = self.control / f"network-zero{suffix}.sb"
        profile.write_bytes(profile_bytes)
        profile_digest = sha256(profile_bytes)
        protected_writes = tuple(
            root / f".samvil-write-probe{suffix}" for root in self.protected_roots
        )
        outer_receipt = self.control / f"outer-receipt{suffix}.json"
        receipt_payload: dict[str, object] = {
            "schema": inherited.OUTER_RECEIPT_SCHEMA,
            "status": "PASS",
            "nonce": self.nonce,
            "profile_class": inherited.INHERITED_PROFILE_CLASS,
            "profile_sha256": profile_digest,
            "protected_roots_sha256": sha256(
                inherited.canonical_json_bytes(
                    [str(path) for path in self.protected_roots]
                )
            ),
            "environment_keys": list(self.environment_keys),
        }
        if receipt_changes:
            receipt_payload.update(receipt_changes)
        if receipt_remove:
            del receipt_payload[receipt_remove]
        receipt_canonical = inherited.canonical_json_bytes(receipt_payload)
        outer_receipt.write_bytes(receipt_canonical + b"\n")
        context = self.control / f"inherited-context{suffix}.json"
        context_payload: dict[str, object] = {
            "schema": inherited.CONTEXT_SCHEMA,
            "nonce": self.nonce,
            "profile_class": inherited.INHERITED_PROFILE_CLASS,
            "profile_path": str(profile),
            "profile_sha256": profile_digest,
            "outer_receipt_path": str(outer_receipt),
            "outer_receipt_sha256": sha256(receipt_canonical),
            "invocation_root": str(self.invocation),
            "execution_root": str(self.execution),
            "protected_read_roots": [str(path) for path in self.protected_roots],
            "protected_write_paths": [str(path) for path in protected_writes],
            "temp_probe_path": str(self.tmpdir / f"probe{suffix}"),
        }
        if context_changes:
            context_payload.update(context_changes)
        if context_remove:
            del context_payload[context_remove]
        canonical = inherited.canonical_json_bytes(context_payload)
        context.write_bytes(canonical + b"\n")
        environment = {
            "TMPDIR": str(self.tmpdir),
            inherited.BOOTSTRAP_NONCE_ENV: self.nonce,
            inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: sha256(canonical),
        }
        receipt_path = self.tmpdir / f"runner-receipt{suffix}.json"
        denial_path = self.tmpdir / f"runner-denials{suffix}.log"
        return context, environment, receipt_path, denial_path, context_payload

    def _validate(
        self,
        context: Path | None,
        environment: dict[str, str],
        receipt_path: Path,
        denial_path: Path,
        *,
        cli_root: str | None = None,
        cli_nonce: str | None = None,
    ) -> inherited.ValidatedInheritedContext:
        return inherited.validate_inherited_request(
            context_path=None if context is None else str(context),
            cli_root=cli_root or str(self.execution),
            cli_nonce=cli_nonce or self.nonce,
            environment=environment,
            expected_environment_keys=self.environment_keys,
            receipt_path=str(receipt_path),
            denial_log_path=str(denial_path),
        )

    def _validate_in_subprocess(
        self,
        context: Path,
        environment: dict[str, str],
        receipt_path: Path,
        denial_path: Path,
        *,
        timeout: float = 1.0,
    ) -> subprocess.CompletedProcess[str]:
        arguments = {
            "context_path": str(context),
            "cli_root": str(self.execution),
            "cli_nonce": self.nonce,
            "environment": environment,
            "expected_environment_keys": list(self.environment_keys),
            "receipt_path": str(receipt_path),
            "denial_log_path": str(denial_path),
        }
        source = """
import json
import sys
sys.path.insert(0, sys.argv[1])
import inherited_context as inherited
arguments = json.loads(sys.argv[2])
try:
    inherited.validate_inherited_request(**arguments)
except inherited.ProtocolError as exc:
    print(exc.status)
    raise SystemExit(0)
except BaseException as exc:
    print(type(exc).__name__)
    raise SystemExit(3)
print("VALIDATION_UNEXPECTEDLY_SUCCEEDED")
raise SystemExit(4)
"""
        try:
            return subprocess.run(
                [
                    str(SYSTEM_PYTHON),
                    "-c",
                    source,
                    str(TOOLS_ROOT),
                    json.dumps(arguments, sort_keys=True, separators=(",", ":")),
                ],
                cwd=self.base,
                env=self.subprocess_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(f"validation blocked on an unsafe control artifact: {exc}")

    def assert_protocol_error(self, expected: str, callback: object) -> None:
        with self.assertRaises(inherited.ProtocolError) as raised:
            callback()
        self.assertEqual(raised.exception.status, expected)

    def assert_no_runtime_artifacts(
        self,
        payload: dict[str, object],
        receipt_path: Path,
        denial_path: Path,
    ) -> None:
        self.assertFalse(receipt_path.exists())
        self.assertFalse(denial_path.exists())
        self.assertFalse(Path(str(payload["temp_probe_path"])).exists())
        for value in payload["protected_write_paths"]:
            raw = str(value)
            if "\x00" not in raw and os.path.basename(raw) not in {".", "..", ""}:
                self.assertFalse(Path(raw).exists())

    def _validated_for_boundary_failure(self) -> inherited.ValidatedInheritedContext:
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-boundary-failure"
        )
        return self._validate(context, environment, receipt_path, denial_path)

    def _assert_probe_error(
        self, expected: str, callback: object, expected_operation: str
    ) -> inherited.ProtocolError:
        metadata_denied = PermissionError(errno.EPERM, "denied")
        with mock.patch.object(
            inherited.os, "stat", side_effect=metadata_denied
        ), mock.patch.object(
            inherited.os, "lstat", side_effect=metadata_denied
        ), mock.patch.object(
            inherited.os, "access", return_value=False
        ), mock.patch.object(
            inherited.os.path, "exists", return_value=False
        ), self.assertRaises(inherited.ProtocolError) as raised:
            callback()
        self.assertEqual(raised.exception.status, expected)
        evidence = getattr(raised.exception, "evidence", ())
        self.assertIn(f"operation={expected_operation}", evidence)
        self.assertTrue(all("/" not in item for item in evidence))
        return raised.exception

    @contextlib.contextmanager
    def _patched_successful_pre_network_probes(
        self, validated: inherited.ValidatedInheritedContext
    ) -> object:
        real_open = os.open
        real_listdir = os.listdir

        def open_boundaries(path: object, flags: int, mode: int = 0o777) -> int:
            candidate = Path(path)
            if candidate in validated.protected_read_roots:
                raise PermissionError(errno.EPERM, "denied")
            if candidate in validated.protected_write_paths:
                raise PermissionError(errno.EPERM, "denied")
            return real_open(path, flags, mode)

        def list_boundaries(path: object) -> list[str]:
            if isinstance(path, int):
                return real_listdir(path)
            raise PermissionError(errno.EPERM, "denied")

        with mock.patch.object(
            inherited.os, "listdir", side_effect=list_boundaries
        ), mock.patch.object(
            inherited.os, "open", side_effect=open_boundaries
        ), mock.patch.object(
            inherited.os, "stat", side_effect=PermissionError(errno.EPERM, "denied")
        ), mock.patch.object(
            inherited.os, "lstat", side_effect=PermissionError(errno.EPERM, "denied")
        ), mock.patch.object(
            inherited.os, "access", return_value=False
        ), mock.patch.object(
            inherited.os.path, "exists", return_value=False
        ):
            yield

    def test_valid_protocol_binds_canonical_hashes_paths_and_environment(self) -> None:
        context, environment, receipt_path, denial_path, _ = self._write_protocol()

        validated = self._validate(context, environment, receipt_path, denial_path)

        self.assertEqual(validated.context_path, context)
        self.assertEqual(validated.execution_root, self.execution)
        self.assertEqual(validated.invocation_root, self.invocation)
        self.assertEqual(validated.protected_read_roots, self.protected_roots)
        self.assertEqual(validated.environment_keys, self.environment_keys)
        self.assertEqual(
            validated.context_sha256,
            environment[inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV],
        )
        self.assertFalse(receipt_path.exists())
        self.assertFalse(denial_path.exists())
        self.assertFalse(validated.temp_probe_path.exists())
        self.assertTrue(all(not path.exists() for path in validated.protected_write_paths))

    def test_real_network_zero_boundary_probes_are_path_free_and_exact(self) -> None:
        focused = os.environ.get(FOCUSED_BOUNDARY_CHILD_ENV)
        if focused is None:
            self.skipTest("external focused boundary controller was not requested")
        self.assertEqual(focused, "1")
        required = (
            FOCUSED_CONTEXT_ENV,
            FOCUSED_EXECUTION_ROOT_ENV,
            FOCUSED_CLI_NONCE_ENV,
            FOCUSED_RECEIPT_ENV,
            FOCUSED_DENIAL_ENV,
            FOCUSED_ENVIRONMENT_KEYS_ENV,
            FOCUSED_PROFILE_SHA256_ENV,
            inherited.BOOTSTRAP_NONCE_ENV,
            inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV,
            "TMPDIR",
        )
        missing = [key for key in required if not os.environ.get(key)]
        self.assertEqual(missing, [], f"missing focused child inputs: {missing}")
        try:
            environment_keys = json.loads(os.environ[FOCUSED_ENVIRONMENT_KEYS_ENV])
        except (json.JSONDecodeError, TypeError) as exc:
            self.fail(f"invalid focused environment key input: {exc}")
        self.assertIsInstance(environment_keys, list)

        try:
            validated = inherited.validate_inherited_request(
                context_path=os.environ[FOCUSED_CONTEXT_ENV],
                cli_root=os.environ[FOCUSED_EXECUTION_ROOT_ENV],
                cli_nonce=os.environ[FOCUSED_CLI_NONCE_ENV],
                environment=dict(os.environ),
                expected_environment_keys=environment_keys,
                receipt_path=os.environ[FOCUSED_RECEIPT_ENV],
                denial_log_path=os.environ[FOCUSED_DENIAL_ENV],
            )
        except inherited.ProtocolError as exc:
            self.fail(f"focused inherited validation failed: {exc.status}")
        self.assertEqual(
            validated.profile_sha256,
            os.environ[FOCUSED_PROFILE_SHA256_ENV],
        )
        evidence = inherited.run_boundary_probes(validated)
        payload = asdict(evidence)
        self.assertEqual(
            payload,
            {
                "execution_root_read": True,
                "loopback_bind_eperm": True,
                "loopback_connect_eperm": True,
                "protected_list_eperm": 2,
                "protected_open_eperm": 2,
                "protected_stat_eperm": 2,
                "protected_lstat_eperm": 2,
                "protected_access_false": 2,
                "protected_exists_false": 2,
                "protected_root_count": 2,
                "protected_write_eperm": 2,
                "temp_roundtrip": True,
            },
        )
        self.assertTrue(
            all(
                not isinstance(value, str) or not value.startswith("/")
                for value in payload.values()
            )
        )
        print(
            "SAMVIL_BOUNDARY_CHILD_EVIDENCE="
            + json.dumps(
                {
                    "evidence": payload,
                    "profile_sha256": validated.profile_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def test_real_boundary_child_has_no_outer_controller_authority(self) -> None:
        source = inspect.getsource(
            type(self).test_real_network_zero_boundary_probes_are_path_free_and_exact
        )
        for forbidden in (
            "sandbox-exec",
            "subprocess.run",
            "profile_bytes",
            "profile_digest",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_real_boundary_child_skips_without_explicit_focus(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(
            unittest.SkipTest
        ) as raised:
            self.test_real_network_zero_boundary_probes_are_path_free_and_exact()
        self.assertIn("external focused boundary controller", str(raised.exception))

    def test_real_boundary_child_fails_when_explicit_inputs_are_missing(self) -> None:
        with mock.patch.dict(
            os.environ,
            {FOCUSED_BOUNDARY_CHILD_ENV: "1"},
            clear=True,
        ), self.assertRaises(AssertionError) as raised:
            self.test_real_network_zero_boundary_probes_are_path_free_and_exact()
        self.assertIn("missing focused child inputs", str(raised.exception))

    def test_real_boundary_child_fails_on_bootstrap_digest_mismatch(self) -> None:
        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-focused-mismatch"
        )
        focused_environment = {
            FOCUSED_BOUNDARY_CHILD_ENV: "1",
            FOCUSED_CONTEXT_ENV: str(context),
            FOCUSED_EXECUTION_ROOT_ENV: str(self.execution),
            FOCUSED_CLI_NONCE_ENV: self.nonce,
            FOCUSED_RECEIPT_ENV: str(receipt_path),
            FOCUSED_DENIAL_ENV: str(denial_path),
            FOCUSED_ENVIRONMENT_KEYS_ENV: json.dumps(list(self.environment_keys)),
            FOCUSED_PROFILE_SHA256_ENV: str(payload["profile_sha256"]),
            inherited.BOOTSTRAP_NONCE_ENV: environment[
                inherited.BOOTSTRAP_NONCE_ENV
            ],
            inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "0" * 64,
            "TMPDIR": str(self.tmpdir),
        }
        with mock.patch.dict(
            os.environ, focused_environment, clear=True
        ), self.assertRaises(AssertionError) as raised:
            self.test_real_network_zero_boundary_probes_are_path_free_and_exact()
        self.assertIn(
            "focused inherited validation failed: INHERITED_CONTEXT_DIGEST_MISMATCH",
            str(raised.exception),
        )

    def test_outer_absence_evidence_is_path_free_for_absent_target(self) -> None:
        target = self.tmpdir / "outer-absent-probe"

        evidence = capture_outer_absence(target, "OUTER_ARTIFACT_PRESENT")

        self.assertEqual(
            evidence,
            OuterAbsenceEvidence(
                absent=True,
                file_type=None,
                mode=None,
                device=None,
                inode=None,
                nlink=None,
                size=None,
            ),
        )
        self.assertNotIn(str(target), repr(evidence))

    def test_outer_absence_evidence_blocks_existing_temp_artifact_without_deleting_it(self) -> None:
        target = self.tmpdir / "fake-child-temp-artifact"
        target.write_bytes(b"left-behind")

        with self.assertRaises(OuterArtifactBlocker) as raised:
            capture_outer_absence(target, "OUTER_TEMP_ARTIFACT_PRESENT")

        evidence = raised.exception.evidence
        self.assertEqual(raised.exception.status, "OUTER_TEMP_ARTIFACT_PRESENT")
        self.assertFalse(evidence.absent)
        self.assertEqual(evidence.file_type, "regular")
        self.assertEqual(evidence.size, len(b"left-behind"))
        self.assertNotIn(str(target), repr(evidence))
        self.assertTrue(target.exists())

    def test_outer_absence_lstat_error_drops_sensitive_exception_graph(self) -> None:
        sensitive = "/sensitive/outer-artifact"
        denied = PermissionError(errno.EACCES, "denied", sensitive)

        with mock.patch.object(os, "lstat", side_effect=denied), self.assertRaises(
            OuterArtifactBlocker
        ) as raised:
            capture_outer_absence(Path(sensitive), "OUTER_LSTAT_FAILED")

        blocker = raised.exception
        self.assertEqual(blocker.status, "OUTER_LSTAT_FAILED")
        self.assertEqual(blocker.evidence.file_type, "lstat-error")
        self.assertEqual(blocker.evidence.error_errno, "EACCES")
        self.assertIsNone(blocker.__cause__)
        self.assertIsNone(blocker.__context__)
        rendered = " ".join(
            (str(blocker), repr(blocker), repr(blocker.evidence))
        )
        self.assertNotIn(sensitive, rendered)

    def test_boundary_probe_rejects_protected_list_success_and_wrong_errno(self) -> None:
        validated = self._validated_for_boundary_failure()
        for outcome, effect in (
            ("success", []),
            ("eacces", PermissionError(errno.EACCES, "denied")),
            ("enoent", FileNotFoundError(errno.ENOENT, "missing")),
            ("eisdir", IsADirectoryError(errno.EISDIR, "directory")),
            ("other", OSError(errno.EIO, "io")),
        ):
            with self.subTest(outcome=outcome), mock.patch.object(
                inherited.os,
                "listdir",
                side_effect=effect if isinstance(effect, BaseException) else None,
                return_value=(
                    effect if not isinstance(effect, BaseException) else None
                ),
            ):
                self._assert_probe_error(
                    "INHERITED_PROTECTED_LIST_NOT_DENIED",
                    lambda: inherited.run_boundary_probes(validated),
                    "protected_list",
                )

    def test_boundary_probe_rejects_protected_open_success_and_wrong_errno(self) -> None:
        validated = self._validated_for_boundary_failure()
        for outcome, open_effect in (
            ("success", 71),
            ("eacces", PermissionError(errno.EACCES, "denied")),
            ("enoent", FileNotFoundError(errno.ENOENT, "missing")),
            ("eisdir", IsADirectoryError(errno.EISDIR, "directory")),
            ("other", OSError(errno.EIO, "io")),
        ):
            with self.subTest(outcome=outcome), mock.patch.object(
                inherited.os,
                "listdir",
                side_effect=PermissionError(errno.EPERM, "denied"),
            ), mock.patch.object(
                inherited.os,
                "open",
                side_effect=(
                    open_effect if isinstance(open_effect, BaseException) else None
                ),
                return_value=(
                    open_effect
                    if not isinstance(open_effect, BaseException)
                    else None
                ),
            ), mock.patch.object(inherited.os, "close") as close:
                self._assert_probe_error(
                    "INHERITED_PROTECTED_OPEN_NOT_DENIED",
                    lambda: inherited.run_boundary_probes(validated),
                    "protected_open",
                )
                if outcome == "success":
                    close.assert_called_once_with(71)
                else:
                    close.assert_not_called()

    def test_boundary_probe_rejects_protected_write_success_and_wrong_errno(self) -> None:
        validated = self._validated_for_boundary_failure()
        for outcome, write_effect in (
            ("success", 72),
            ("eacces", PermissionError(errno.EACCES, "denied")),
            ("enoent", FileNotFoundError(errno.ENOENT, "missing")),
            ("eisdir", IsADirectoryError(errno.EISDIR, "directory")),
            ("other", OSError(errno.EIO, "io")),
        ):
            def open_effect(path: object, flags: int, mode: int = 0o777) -> int:
                candidate = Path(path)
                if candidate in validated.protected_read_roots:
                    raise PermissionError(errno.EPERM, "denied")
                if candidate == validated.protected_write_paths[0]:
                    if outcome == "success":
                        return write_effect
                    raise write_effect
                self.fail("probe continued after the first protected write failure")

            with self.subTest(outcome=outcome), mock.patch.object(
                inherited.os,
                "listdir",
                side_effect=PermissionError(errno.EPERM, "denied"),
            ), mock.patch.object(
                inherited.os, "open", side_effect=open_effect
            ), mock.patch.object(
                inherited.os, "close",
            ) as close:
                self._assert_probe_error(
                    "INHERITED_PROTECTED_WRITE_NOT_DENIED",
                    lambda: inherited.run_boundary_probes(validated),
                    "protected_write",
                )
                if outcome == "success":
                    close.assert_called_once_with(72)
                else:
                    close.assert_not_called()
                self.assertFalse(validated.protected_write_paths[0].exists())

    def test_boundary_probe_rejects_temp_and_execution_read_failures(self) -> None:
        validated = self._validated_for_boundary_failure()
        real_open = os.open
        real_listdir = os.listdir

        def denied_boundaries(path: object, flags: int, mode: int = 0o777) -> int:
            candidate = Path(path)
            if candidate in validated.protected_read_roots:
                raise PermissionError(errno.EPERM, "denied")
            if candidate in validated.protected_write_paths:
                raise PermissionError(errno.EPERM, "denied")
            if candidate == validated.temp_probe_path:
                raise PermissionError(errno.EACCES, "denied")
            return real_open(path, flags, mode)

        with mock.patch.object(
            inherited.os,
            "listdir",
            side_effect=PermissionError(errno.EPERM, "denied"),
        ), mock.patch.object(inherited.os, "open", side_effect=denied_boundaries):
            self._assert_probe_error(
                "INHERITED_TEMP_PROBE_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "temp_roundtrip",
            )

        def execution_denied(path: object, flags: int, mode: int = 0o777) -> int:
            candidate = Path(path)
            if candidate in validated.protected_read_roots:
                raise PermissionError(errno.EPERM, "denied")
            if candidate in validated.protected_write_paths:
                raise PermissionError(errno.EPERM, "denied")
            if candidate == validated.execution_root:
                raise PermissionError(errno.EACCES, "denied")
            return real_open(path, flags, mode)

        def list_boundaries(path: object) -> list[str]:
            if isinstance(path, int):
                return real_listdir(path)
            raise PermissionError(errno.EPERM, "denied")

        with mock.patch.object(
            inherited.os, "listdir", side_effect=list_boundaries
        ), mock.patch.object(
            inherited.os, "open", side_effect=execution_denied
        ):
            self._assert_probe_error(
                "INHERITED_EXECUTION_ROOT_UNREADABLE",
                lambda: inherited.run_boundary_probes(validated),
                "execution_root_read",
            )
        self.assertFalse(validated.temp_probe_path.exists())

    def test_boundary_probe_rejects_loopback_wrong_errno_and_success(self) -> None:
        validated = self._validated_for_boundary_failure()
        real_open = os.open
        real_listdir = os.listdir

        def open_boundaries(path: object, flags: int, mode: int = 0o777) -> int:
            candidate = Path(path)
            if candidate in validated.protected_read_roots:
                raise PermissionError(errno.EPERM, "denied")
            if candidate in validated.protected_write_paths:
                raise PermissionError(errno.EPERM, "denied")
            return real_open(path, flags, mode)

        def list_boundaries(path: object) -> list[str]:
            if isinstance(path, int):
                return real_listdir(path)
            raise PermissionError(errno.EPERM, "denied")

        for outcome, bind_effect in (
            ("success", None),
            ("wrong-errno", PermissionError(errno.EACCES, "denied")),
        ):
            bind_socket = mock.MagicMock()
            bind_socket.bind.side_effect = bind_effect
            with self.subTest(operation="bind", outcome=outcome), mock.patch.object(
                inherited.os, "listdir", side_effect=list_boundaries
            ), mock.patch.object(
                inherited.os, "open", side_effect=open_boundaries
            ), mock.patch.object(
                inherited.socket, "socket", return_value=bind_socket
            ):
                self._assert_probe_error(
                    "INHERITED_LOOPBACK_BIND_NOT_DENIED",
                    lambda: inherited.run_boundary_probes(validated),
                    "loopback_bind",
                )

        for outcome, connect_effect in (
            ("success", None),
            ("wrong-errno", ConnectionRefusedError(errno.ECONNREFUSED, "refused")),
        ):
            bind_denied = mock.MagicMock()
            bind_denied.bind.side_effect = PermissionError(errno.EPERM, "denied")
            connect_socket = mock.MagicMock()
            connect_socket.connect.side_effect = connect_effect
            with self.subTest(
                operation="connect", outcome=outcome
            ), mock.patch.object(
                inherited.os, "listdir", side_effect=list_boundaries
            ), mock.patch.object(
                inherited.os, "open", side_effect=open_boundaries
            ), mock.patch.object(
                inherited.socket,
                "socket",
                side_effect=(bind_denied, connect_socket),
            ):
                self._assert_probe_error(
                    "INHERITED_LOOPBACK_CONNECT_NOT_DENIED",
                    lambda: inherited.run_boundary_probes(validated),
                    "loopback_connect",
                )
        self.assertFalse(hasattr(inherited, "run_candidate"))
        self.assertFalse(hasattr(inherited, "subprocess"))

    def test_boundary_probe_types_loopback_timeout_setup_failure(self) -> None:
        validated = self._validated_for_boundary_failure()
        sock = mock.MagicMock()
        sock.settimeout.side_effect = OSError(errno.EIO, "timeout setup failed")

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.socket, "socket", return_value=sock
        ):
            error = self._assert_probe_error(
                "INHERITED_LOOPBACK_TIMEOUT_SETUP_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "loopback_bind_timeout",
            )

        self.assertNotIsInstance(error, OSError)
        sock.close.assert_called_once_with()

    def test_boundary_probe_types_loopback_cleanup_failure_after_expected_eperm(self) -> None:
        validated = self._validated_for_boundary_failure()
        sock = mock.MagicMock()
        sock.bind.side_effect = PermissionError(errno.EPERM, "denied")
        sock.close.side_effect = OSError(errno.EIO, "close failed")

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.socket, "socket", return_value=sock
        ):
            error = self._assert_probe_error(
                "INHERITED_LOOPBACK_CLEANUP_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "loopback_bind_cleanup",
            )

        self.assertNotIsInstance(error, OSError)

    def test_boundary_probe_preserves_primary_loopback_blocker_when_cleanup_fails(self) -> None:
        validated = self._validated_for_boundary_failure()
        sock = mock.MagicMock()
        sock.bind.side_effect = PermissionError(errno.EACCES, "wrong denial")
        sock.close.side_effect = OSError(errno.EIO, "close failed")

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.socket, "socket", return_value=sock
        ):
            error = self._assert_probe_error(
                "INHERITED_LOOPBACK_BIND_NOT_DENIED",
                lambda: inherited.run_boundary_probes(validated),
                "loopback_bind",
            )

        self.assertNotIsInstance(error, OSError)

    def test_boundary_probe_types_temp_write_descriptor_close_failure(self) -> None:
        validated = self._validated_for_boundary_failure()

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.os,
            "close",
            side_effect=OSError(errno.EIO, "temp write close failed"),
        ):
            error = self._assert_probe_error(
                "INHERITED_TEMP_WRITE_CLEANUP_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "temp_write_cleanup",
            )

        self.assertNotIsInstance(error, OSError)

    def test_boundary_probe_types_temp_read_descriptor_close_failure(self) -> None:
        validated = self._validated_for_boundary_failure()
        real_close = os.close
        calls = 0

        def close_effect(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError(errno.EIO, "temp read close failed")
            real_close(descriptor)

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.os, "close", side_effect=close_effect
        ):
            error = self._assert_probe_error(
                "INHERITED_TEMP_READ_CLEANUP_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "temp_read_cleanup",
            )

        self.assertNotIsInstance(error, OSError)

    def test_boundary_probe_types_execution_root_descriptor_close_failure(self) -> None:
        validated = self._validated_for_boundary_failure()
        real_close = os.close
        calls = 0

        def close_effect(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError(errno.EIO, "execution close failed")
            real_close(descriptor)

        with self._patched_successful_pre_network_probes(validated), mock.patch.object(
            inherited.os, "close", side_effect=close_effect
        ):
            error = self._assert_probe_error(
                "INHERITED_EXECUTION_ROOT_CLEANUP_FAILED",
                lambda: inherited.run_boundary_probes(validated),
                "execution_root_cleanup",
            )

        self.assertNotIsInstance(error, OSError)

    def test_boundary_probe_preserves_execution_primary_when_descriptor_close_fails(self) -> None:
        validated = self._validated_for_boundary_failure()
        real_open = os.open
        real_close = os.close
        close_calls = 0

        def open_boundaries(path: object, flags: int, mode: int = 0o777) -> int:
            candidate = Path(path)
            if candidate in validated.protected_read_roots:
                raise PermissionError(errno.EPERM, "denied")
            if candidate in validated.protected_write_paths:
                raise PermissionError(errno.EPERM, "denied")
            return real_open(path, flags, mode)

        def list_boundaries(path: object) -> list[str]:
            if isinstance(path, int):
                raise PermissionError(errno.EACCES, "execution read denied")
            raise PermissionError(errno.EPERM, "denied")

        def close_effect(descriptor: int) -> None:
            nonlocal close_calls
            close_calls += 1
            if close_calls == 3:
                raise OSError(errno.EIO, "execution close failed")
            real_close(descriptor)

        with mock.patch.object(
            inherited.os, "listdir", side_effect=list_boundaries
        ), mock.patch.object(
            inherited.os, "open", side_effect=open_boundaries
        ), mock.patch.object(inherited.os, "close", side_effect=close_effect):
            error = self._assert_probe_error(
                "INHERITED_EXECUTION_ROOT_UNREADABLE",
                lambda: inherited.run_boundary_probes(validated),
                "execution_root_read",
            )

        self.assertNotIsInstance(error, OSError)

    def test_task_a_control_artifact_close_failure_is_typed(self) -> None:
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-context-close-failure"
        )

        with mock.patch.object(
            inherited.os,
            "close",
            side_effect=OSError(errno.EIO, "context close failed"),
        ):
            self.assert_protocol_error(
                "INHERITED_CONTEXT_CLOSE_FAILED",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )

    def test_protected_write_leaf_validation_does_not_lstat_the_target(self) -> None:
        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-protected-lstat-denied"
        )
        protected_targets = {
            Path(value) for value in payload["protected_write_paths"]
        }
        real_lstat = os.lstat

        def deny_only_protected_targets(path: object, *args: object, **kwargs: object) -> os.stat_result:
            candidate = Path(path)
            if candidate in protected_targets:
                raise PermissionError(errno.EPERM, "sandbox denied protected target")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(os, "lstat", side_effect=deny_only_protected_targets):
            validated = self._validate(
                context, environment, receipt_path, denial_path
            )

        self.assertEqual(set(validated.protected_write_paths), protected_targets)
        self.assertFalse(receipt_path.exists())
        self.assertFalse(denial_path.exists())

    def test_canonical_json_hash_and_environment_key_helpers_are_exact(self) -> None:
        self.assertEqual(
            inherited.canonical_json_bytes({"z": "한글", "a": [2, 1]}),
            '{"a":[2,1],"z":"한글"}'.encode("utf-8"),
        )
        self.assertEqual(
            inherited.protected_roots_sha256(self.protected_roots),
            sha256(
                inherited.canonical_json_bytes(
                    [str(path) for path in self.protected_roots]
                )
            ),
        )
        self.assertEqual(
            inherited.environment_keys_sha256(self.environment_keys),
            sha256(inherited.canonical_json_bytes(list(self.environment_keys))),
        )
        for keys in (
            ("TMPDIR", "PATH"),
            ("PATH", "PATH"),
            ("PATH", inherited.BOOTSTRAP_NONCE_ENV),
        ):
            with self.subTest(keys=keys):
                self.assert_protocol_error(
                    "INHERITED_ENVIRONMENT_KEYS_INVALID",
                    lambda: inherited.sanitized_environment_keys(keys),
                )
        self.assert_protocol_error(
            "INHERITED_JSON_INVALID",
            lambda: inherited.canonical_json_bytes({"bad": float("nan")}),
        )

    def test_cli_and_environment_authority_fail_closed(self) -> None:
        context, environment, receipt_path, denial_path, _ = self._write_protocol()
        cases = (
            (
                "INHERITED_ENVIRONMENT_ONLY",
                lambda: self._validate(None, environment, receipt_path, denial_path),
            ),
            (
                "INHERITED_CLI_ONLY",
                lambda: self._validate(context, {"TMPDIR": str(self.tmpdir)}, receipt_path, denial_path),
            ),
            (
                "INVALID_BOOTSTRAP_NONCE",
                lambda: self._validate(
                    context,
                    {**environment, inherited.BOOTSTRAP_NONCE_ENV: "b" * 64},
                    receipt_path,
                    denial_path,
                ),
            ),
            (
                "INVALID_BOOTSTRAP_NONCE",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                    cli_nonce="A" * 64,
                ),
            ),
            (
                "INHERITED_CONTEXT_DIGEST_MISMATCH",
                lambda: self._validate(
                    context,
                    {**environment, inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "0" * 64},
                    receipt_path,
                    denial_path,
                ),
            ),
            (
                "INHERITED_EXECUTION_ROOT_MISMATCH",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                    cli_root=f"{self.execution}/../execution",
                ),
            ),
        )
        for expected, callback in cases:
            with self.subTest(expected=expected):
                self.assert_protocol_error(expected, callback)
                self.assertFalse(receipt_path.exists())
                self.assertFalse(denial_path.exists())

    def test_context_and_receipt_exact_fields_and_evidence_are_required(self) -> None:
        context_cases = (
            ({"unexpected": True}, "INHERITED_CONTEXT_SCHEMA_INVALID"),
            ({"schema": "wrong"}, "INHERITED_CONTEXT_SCHEMA_INVALID"),
            ({"profile_class": "pinned-full-gate-loopback-only"}, "INHERITED_PROFILE_CLASS_REJECTED"),
            ({"nonce": "A" * 64}, "INVALID_BOOTSTRAP_NONCE"),
            ({"nonce": "a" * 63}, "INVALID_BOOTSTRAP_NONCE"),
            ({"profile_sha256": "0" * 64}, "INHERITED_PROFILE_MISMATCH"),
            ({"profile_sha256": "0" * 63}, "INHERITED_PROFILE_MISMATCH"),
            ({"outer_receipt_sha256": "0" * 64}, "INHERITED_RECEIPT_MISMATCH"),
            ({"outer_receipt_sha256": "0" * 65}, "INHERITED_RECEIPT_MISMATCH"),
        )
        for index, (changes, expected) in enumerate(context_cases):
            with self.subTest(expected=expected):
                context, environment, receipt_path, denial_path, _ = self._write_protocol(
                    suffix=f"-context-{index}", context_changes=changes
                )
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(context, environment, receipt_path, denial_path),
                )

        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-missing", context_remove="temp_probe_path"
        )
        self.assert_protocol_error(
            "INHERITED_CONTEXT_SCHEMA_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        receipt_cases = (
            ({"unexpected": True}, "INHERITED_RECEIPT_SCHEMA_INVALID"),
            ({"schema": "wrong"}, "INHERITED_RECEIPT_SCHEMA_INVALID"),
            ({"status": "FAIL"}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
            ({"nonce": "b" * 64}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
            ({"profile_class": "pinned-full-gate-loopback-only"}, "INHERITED_PROFILE_CLASS_REJECTED"),
            ({"profile_sha256": "0" * 64}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
            ({"protected_roots_sha256": "0" * 64}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
            ({"protected_roots_sha256": "0" * 63}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
            ({"environment_keys": ["PATH", "TMPDIR"]}, "INHERITED_RECEIPT_EVIDENCE_MISMATCH"),
        )
        for index, (changes, expected) in enumerate(receipt_cases):
            with self.subTest(expected=expected):
                context, environment, receipt_path, denial_path, _ = self._write_protocol(
                    suffix=f"-receipt-{index}", receipt_changes=changes
                )
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(context, environment, receipt_path, denial_path),
                )

        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-receipt-missing", receipt_remove="status"
        )
        self.assert_protocol_error(
            "INHERITED_RECEIPT_SCHEMA_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-duplicate-json-key"
        )
        duplicate = context.read_bytes().rstrip(b"\n")[:-1] + b',"schema":"duplicate"}'
        context.write_bytes(duplicate + b"\n")
        environment[inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV] = sha256(duplicate)
        self.assert_protocol_error(
            "INHERITED_CONTEXT_SCHEMA_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

    def test_outer_receipt_loopback_class_has_dedicated_blocker(self) -> None:
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-receipt-loopback-class",
            receipt_changes={
                "profile_class": inherited.LOOPBACK_PROFILE_CLASS,
            },
        )

        self.assert_protocol_error(
            "INHERITED_PROFILE_CLASS_REJECTED",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )
        self.assertFalse(receipt_path.exists())
        self.assertFalse(denial_path.exists())

    def test_roots_tmpdir_and_protected_writes_must_be_canonical_and_safe(self) -> None:
        file_root = self.invocation / "not-a-directory"
        file_root.write_text("x", encoding="utf-8")
        symlink_root = self.invocation / "protected-link"
        symlink_root.symlink_to(self.protected_roots[0], target_is_directory=True)
        outside = self.base / "outside"
        outside.mkdir()
        missing = self.invocation / "missing"
        tmp_link = self.invocation / "tmp-link"
        tmp_link.symlink_to(self.tmpdir, target_is_directory=True)
        cases: list[tuple[dict[str, object], dict[str, str], str]] = [
            ({"protected_read_roots": [str(self.protected_roots[0])]}, {}, "INHERITED_PROTECTED_ROOTS_INVALID"),
            ({"protected_read_roots": [str(missing), str(self.protected_roots[1])]}, {}, "INHERITED_PROTECTED_WRITES_INVALID"),
            ({"protected_read_roots": [str(file_root), str(self.protected_roots[1])]}, {}, "INHERITED_PROTECTED_WRITES_INVALID"),
            ({"protected_read_roots": [str(symlink_root), str(self.protected_roots[1])]}, {}, "INHERITED_PROTECTED_WRITES_INVALID"),
            ({"protected_read_roots": [f"{self.protected_roots[0]}/../protected-home", str(self.protected_roots[1])]}, {}, "INHERITED_PROTECTED_ROOTS_INVALID"),
            ({"protected_write_paths": [str(self.protected_roots[0] / "nested" / "probe"), str(self.protected_roots[1] / "probe")]}, {}, "INHERITED_PROTECTED_WRITES_INVALID"),
            ({"protected_write_paths": [str(self.protected_roots[1] / "wrong-parent"), str(self.protected_roots[0] / "wrong-parent")]}, {}, "INHERITED_PROTECTED_WRITES_INVALID"),
            ({"temp_probe_path": str(outside / "probe")}, {}, "INHERITED_TEMP_PROBE_INVALID"),
            ({}, {"TMPDIR": str(outside)}, "INHERITED_TMPDIR_INVALID"),
            ({}, {"TMPDIR": str(self.execution)}, "INHERITED_TMPDIR_INVALID"),
            ({}, {"TMPDIR": f"{self.tmpdir}/../tmp"}, "INHERITED_TMPDIR_INVALID"),
            ({}, {"TMPDIR": str(missing)}, "INHERITED_TMPDIR_INVALID"),
            ({}, {"TMPDIR": str(file_root)}, "INHERITED_TMPDIR_INVALID"),
            ({}, {"TMPDIR": str(tmp_link)}, "INHERITED_TMPDIR_INVALID"),
        ]
        for index, (context_changes, environment_changes, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-path-{index}", context_changes=context_changes
                )
                environment.update(environment_changes)
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(context, environment, receipt_path, denial_path),
                )
                self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_protected_write_cardinality_and_unsafe_leaf_names_are_rejected(self) -> None:
        cases = (
            (
                [str(self.protected_roots[0] / "only-one")],
                "INHERITED_PROTECTED_WRITES_INVALID",
            ),
            (
                [
                    f"{self.protected_roots[0]}/.",
                    str(self.protected_roots[1] / "safe-leaf"),
                ],
                "INHERITED_PROTECTED_WRITES_INVALID",
            ),
            (
                [
                    f"{self.protected_roots[0]}/bad\x00leaf",
                    str(self.protected_roots[1] / "safe-leaf"),
                ],
                "INHERITED_PROTECTED_WRITES_INVALID",
            ),
        )
        for index, (protected_writes, expected) in enumerate(cases):
            with self.subTest(index=index):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-unsafe-write-{index}",
                    context_changes={"protected_write_paths": protected_writes},
                )
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(context, environment, receipt_path, denial_path),
                )
                self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_invocation_and_context_execution_roots_are_strict(self) -> None:
        root_file = self.base / "root-file"
        root_file.write_text("not a directory", encoding="utf-8")
        invocation_link = self.base / "invocation-link"
        invocation_link.symlink_to(self.invocation, target_is_directory=True)
        execution_link = self.invocation / "execution-link"
        execution_link.symlink_to(self.execution, target_is_directory=True)
        missing = self.base / "missing-root"
        cases = (
            ({"invocation_root": str(missing)}, "INHERITED_INVOCATION_ROOT_INVALID"),
            ({"invocation_root": str(root_file)}, "INHERITED_INVOCATION_ROOT_INVALID"),
            ({"invocation_root": str(invocation_link)}, "INHERITED_INVOCATION_ROOT_INVALID"),
            ({"invocation_root": f"{self.invocation}/../invocation"}, "INHERITED_INVOCATION_ROOT_INVALID"),
            ({"execution_root": str(missing)}, "INHERITED_EXECUTION_ROOT_INVALID"),
            ({"execution_root": str(root_file)}, "INHERITED_EXECUTION_ROOT_INVALID"),
            ({"execution_root": str(execution_link)}, "INHERITED_EXECUTION_ROOT_INVALID"),
            ({"execution_root": f"{self.execution}/../execution"}, "INHERITED_EXECUTION_ROOT_INVALID"),
        )
        for index, (changes, expected) in enumerate(cases):
            with self.subTest(index=index, expected=expected):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-strict-root-{index}", context_changes=changes
                )
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(context, environment, receipt_path, denial_path),
                )
                self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_distinct_canonical_cli_root_does_not_match_context(self) -> None:
        other_execution = self.invocation / "other-execution"
        other_execution.mkdir()
        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-different-cli-root"
        )

        self.assert_protocol_error(
            "INHERITED_EXECUTION_ROOT_MISMATCH",
            lambda: self._validate(
                context,
                environment,
                receipt_path,
                denial_path,
                cli_root=str(other_execution),
            ),
        )
        self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_regular_single_link_control_files_and_containment_are_required(self) -> None:
        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-hardlink"
        )
        profile = Path(str(payload["profile_path"]))
        hardlink = self.control / "profile-hardlink.sb"
        os.link(profile, hardlink)
        self.assert_protocol_error(
            "INHERITED_PROFILE_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-context-hardlink"
        )
        os.link(context, self.control / "context-hardlink.json")
        self.assert_protocol_error(
            "INHERITED_CONTEXT_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-receipt-hardlink"
        )
        outer_receipt = Path(str(payload["outer_receipt_path"]))
        os.link(outer_receipt, self.control / "receipt-hardlink.json")
        self.assert_protocol_error(
            "INHERITED_RECEIPT_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )
        self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

        outside_profile = self.base / "outside-profile.sb"
        outside_profile.write_bytes(b"profile")
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-outside-profile",
            context_changes={
                "profile_path": str(outside_profile),
                "profile_sha256": sha256(outside_profile.read_bytes()),
            },
        )
        self.assert_protocol_error(
            "INHERITED_PROFILE_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        inside_execution = self.execution / "outer-receipt.json"
        inside_execution.write_text("{}", encoding="utf-8")
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-receipt-inside-execution",
            context_changes={
                "outer_receipt_path": str(inside_execution),
                "outer_receipt_sha256": sha256(inside_execution.read_bytes()),
            },
        )
        self.assert_protocol_error(
            "INHERITED_RECEIPT_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

    def test_validated_profile_bytes_remain_authoritative_after_path_replacement(self) -> None:
        original_profile = b"(version 1)\n(deny network*)\n"
        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-profile-replacement", profile_bytes=original_profile
        )
        validated = self._validate(
            context, environment, receipt_path, denial_path
        )
        replacement = self.control / "replacement-profile.sb"
        weaker_profile = b"(version 1)\n(allow network*)\n"
        replacement.write_bytes(weaker_profile)
        os.replace(replacement, Path(str(payload["profile_path"])))

        self.assertFalse(hasattr(inherited, "revalidate_profile_path"))
        self.assertEqual(validated.profile_bytes, original_profile)
        self.assertEqual(sha256(validated.profile_bytes), validated.profile_sha256)
        self.assertNotEqual(validated.profile_bytes, weaker_profile)

    def test_fifo_control_artifacts_fail_promptly_without_blocking(self) -> None:
        cases = (
            ("context", "INHERITED_CONTEXT_INVALID"),
            ("profile", "INHERITED_PROFILE_INVALID"),
            ("receipt", "INHERITED_RECEIPT_INVALID"),
        )
        for index, (artifact, expected) in enumerate(cases):
            with self.subTest(artifact=artifact):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-fifo-{index}"
                )
                target = {
                    "context": context,
                    "profile": Path(str(payload["profile_path"])),
                    "receipt": Path(str(payload["outer_receipt_path"])),
                }[artifact]
                target.unlink()
                os.mkfifo(target, 0o600)

                result = self._validate_in_subprocess(
                    context, environment, receipt_path, denial_path
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_oversize_control_artifacts_use_artifact_specific_blockers(self) -> None:
        limits = {
            "context": 64 * 1024,
            "receipt": 32 * 1024,
            "profile": 256 * 1024,
        }
        expected_status = {
            "context": "INHERITED_CONTEXT_INVALID",
            "receipt": "INHERITED_RECEIPT_INVALID",
            "profile": "INHERITED_PROFILE_INVALID",
        }
        for index, artifact in enumerate(("context", "receipt", "profile")):
            with self.subTest(artifact=artifact):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-oversize-{index}"
                )
                target = {
                    "context": context,
                    "receipt": Path(str(payload["outer_receipt_path"])),
                    "profile": Path(str(payload["profile_path"])),
                }[artifact]
                target.write_bytes(b"x" * (limits[artifact] + 1))

                self.assert_protocol_error(
                    expected_status[artifact],
                    lambda: self._validate(
                        context, environment, receipt_path, denial_path
                    ),
                )

    def test_deep_json_returns_typed_schema_blockers(self) -> None:
        cases = (
            ("context", "INHERITED_CONTEXT_SCHEMA_INVALID"),
            ("receipt", "INHERITED_RECEIPT_SCHEMA_INVALID"),
        )
        deeply_nested = b"[" * 1100 + b"0" + b"]" * 1100
        for index, (artifact, expected) in enumerate(cases):
            with self.subTest(artifact=artifact):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-deep-json-{index}"
                )
                target = (
                    context
                    if artifact == "context"
                    else Path(str(payload["outer_receipt_path"]))
                )
                target.write_bytes(deeply_nested)
                if artifact == "context":
                    environment[inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV] = sha256(
                        deeply_nested
                    )

                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(
                        context, environment, receipt_path, denial_path
                    ),
                )

    def test_json_depth_limit_is_enforced_after_successful_parse(self) -> None:
        nested: object = "leaf"
        for _ in range(40):
            nested = [nested]
        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-parsed-depth",
            context_changes={"protected_read_roots": nested},
        )

        self.assert_protocol_error(
            "INHERITED_CONTEXT_SCHEMA_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

    def test_hostile_integer_parser_value_errors_are_schema_specific(self) -> None:
        huge_integer = "9" * 4301
        original_loads = inherited.json.loads

        def loads_with_modern_integer_limit(value: object, *args: object, **kwargs: object) -> object:
            text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
            if huge_integer in text:
                raise ValueError("integer string conversion limit exceeded")
            return original_loads(value, *args, **kwargs)

        try:
            original_loads(huge_integer)
        except ValueError:
            parser_requires_shim = False
        else:
            parser_requires_shim = True

        cases = (
            ("context", "INHERITED_CONTEXT_SCHEMA_INVALID"),
            ("receipt", "INHERITED_RECEIPT_SCHEMA_INVALID"),
        )
        for index, (artifact, expected) in enumerate(cases):
            with self.subTest(artifact=artifact):
                context, environment, receipt_path, denial_path, payload = self._write_protocol(
                    suffix=f"-hostile-integer-{index}"
                )
                target = (
                    context
                    if artifact == "context"
                    else Path(str(payload["outer_receipt_path"]))
                )
                target.write_bytes(
                    (f'{{"schema":{huge_integer}}}\n').encode("ascii")
                )

                parser_limit = (
                    mock.patch.object(
                        inherited.json,
                        "loads",
                        side_effect=loads_with_modern_integer_limit,
                    )
                    if parser_requires_shim
                    else contextlib.nullcontext()
                )
                with parser_limit:
                    self.assert_protocol_error(
                        expected,
                        lambda: self._validate(
                            context, environment, receipt_path, denial_path
                        ),
                    )

    def test_lone_surrogates_never_escape_as_unicode_errors(self) -> None:
        surrogate = "\ud800"
        self.assert_protocol_error(
            "INHERITED_JSON_INVALID",
            lambda: inherited.canonical_json_bytes({"forged": surrogate}),
        )

        context, environment, receipt_path, denial_path, _ = self._write_protocol(
            suffix="-context-surrogate"
        )
        context_payload = json.loads(context.read_text(encoding="utf-8"))
        context_payload["profile_class"] = surrogate
        context_raw = json.dumps(
            context_payload, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        context.write_bytes(context_raw + b"\n")
        environment[inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV] = sha256(context_raw)
        self.assert_protocol_error(
            "INHERITED_JSON_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

        context, environment, receipt_path, denial_path, payload = self._write_protocol(
            suffix="-receipt-surrogate"
        )
        outer_receipt = Path(str(payload["outer_receipt_path"]))
        receipt_payload = json.loads(outer_receipt.read_text(encoding="utf-8"))
        receipt_payload["profile_class"] = surrogate
        receipt_raw = json.dumps(
            receipt_payload, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        outer_receipt.write_bytes(receipt_raw + b"\n")
        self.assert_protocol_error(
            "INHERITED_JSON_INVALID",
            lambda: self._validate(context, environment, receipt_path, denial_path),
        )

    def test_output_preflight_rejects_aliases_existing_targets_and_collisions(self) -> None:
        context, environment, receipt_path, denial_path, payload = self._write_protocol()
        temp_probe = Path(str(payload["temp_probe_path"]))
        protected_write = Path(str(payload["protected_write_paths"][0]))
        cases = (
            (receipt_path, receipt_path, "INHERITED_OUTPUT_COLLISION"),
            (temp_probe, denial_path, "INHERITED_OUTPUT_COLLISION"),
            (receipt_path, protected_write, "INHERITED_OUTPUT_COLLISION"),
            (Path(f"{self.tmpdir}/../tmp/aliased.json"), denial_path, "INHERITED_OUTPUT_INVALID"),
            (self.base / "outside-output.json", denial_path, "INHERITED_OUTPUT_INVALID"),
        )
        for candidate_receipt, candidate_denial, expected in cases:
            with self.subTest(expected=expected):
                self.assert_protocol_error(
                    expected,
                    lambda: self._validate(
                        context, environment, candidate_receipt, candidate_denial
                    ),
                )
                self.assertFalse(receipt_path.exists())
                self.assertFalse(denial_path.exists())
                self.assertFalse(temp_probe.exists())
                self.assertFalse(protected_write.exists())
                self.assertFalse(candidate_receipt.exists())
                self.assertFalse(candidate_denial.exists())

        existing = self.tmpdir / "existing.json"
        existing.write_text("occupied", encoding="utf-8")
        self.assert_protocol_error(
            "INHERITED_OUTPUT_INVALID",
            lambda: self._validate(context, environment, existing, denial_path),
        )
        self.assertEqual(existing.read_text(encoding="utf-8"), "occupied")
        self.assertFalse(denial_path.exists())
        self.assertFalse(temp_probe.exists())
        self.assertFalse(protected_write.exists())

        occupied_directory = self.tmpdir / "occupied-directory"
        occupied_directory.mkdir()
        self.assert_protocol_error(
            "INHERITED_OUTPUT_INVALID",
            lambda: self._validate(context, environment, occupied_directory, denial_path),
        )
        self.assertFalse(denial_path.exists())
        self.assertFalse(temp_probe.exists())
        self.assertFalse(protected_write.exists())

        output_link = self.tmpdir / "output-link"
        output_link.symlink_to(existing)
        self.assert_protocol_error(
            "INHERITED_OUTPUT_INVALID",
            lambda: self._validate(context, environment, output_link, denial_path),
        )
        self.assertFalse(denial_path.exists())
        self.assertFalse(temp_probe.exists())
        self.assertFalse(protected_write.exists())

    def test_output_protected_write_collision_precedes_target_lstat(self) -> None:
        context, environment, receipt_path, _, payload = self._write_protocol(
            suffix="-output-protected-lstat-denied"
        )
        denial_path = Path(str(payload["protected_write_paths"][0]))
        real_lstat = os.lstat

        def deny_only_colliding_target(path: object, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path) == denial_path:
                raise PermissionError(errno.EPERM, "sandbox denied protected target")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(os, "lstat", side_effect=deny_only_colliding_target):
            self.assert_protocol_error(
                "INHERITED_OUTPUT_COLLISION",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )

        self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_output_collision_rejects_ascii_case_alias_before_target_lstat(self) -> None:
        context, environment, _, _, payload = self._write_protocol(
            suffix="-ascii-case-collision"
        )
        receipt_path = self.tmpdir / "Boundary-Receipt.json"
        denial_path = self.tmpdir / "boundary-receipt.JSON"
        targets = {receipt_path, denial_path, Path(str(payload["temp_probe_path"]))}
        real_lstat = os.lstat

        def reject_target_lstat(path: object, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path) in targets:
                self.fail("target lstat occurred before collision rejection")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(inherited.os, "lstat", side_effect=reject_target_lstat):
            self.assert_protocol_error(
                "INHERITED_OUTPUT_COLLISION",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )
        self.assertTrue(all(not path.exists() for path in targets))

    def test_output_collision_rejects_nfc_nfd_alias_before_target_lstat(self) -> None:
        context, environment, _, _, payload = self._write_protocol(
            suffix="-unicode-collision"
        )
        receipt_path = self.tmpdir / "évidence.json"
        denial_path = self.tmpdir / "e\u0301vidence.json"
        targets = {receipt_path, denial_path, Path(str(payload["temp_probe_path"]))}
        real_lstat = os.lstat

        def reject_target_lstat(path: object, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path) in targets:
                self.fail("target lstat occurred before collision rejection")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(inherited.os, "lstat", side_effect=reject_target_lstat):
            self.assert_protocol_error(
                "INHERITED_OUTPUT_COLLISION",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )
        self.assertTrue(all(not path.exists() for path in targets))

    def test_output_temp_alias_collision_precedes_all_target_lstat(self) -> None:
        temp_probe = self.tmpdir / "Boundary-Probe"
        context, environment, _, denial_path, payload = self._write_protocol(
            suffix="-temp-alias-collision",
            context_changes={"temp_probe_path": str(temp_probe)},
        )
        receipt_path = self.tmpdir / "boundary-probe"
        targets = {receipt_path, denial_path, temp_probe}
        real_lstat = os.lstat

        def reject_target_lstat(path: object, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path) in targets:
                self.fail("target lstat occurred before collision rejection")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(inherited.os, "lstat", side_effect=reject_target_lstat):
            self.assert_protocol_error(
                "INHERITED_OUTPUT_COLLISION",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )
        self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)

    def test_output_protected_alias_collision_precedes_all_target_lstat(self) -> None:
        protected_roots = (self.tmpdir, self.protected_roots[1])
        protected_write = self.tmpdir / "évidence.json"
        protected_writes = (
            protected_write,
            protected_roots[1] / ".samvil-protected-alias-write",
        )
        roots_digest = inherited.protected_roots_sha256(protected_roots)
        context, environment, _, denial_path, payload = self._write_protocol(
            suffix="-protected-alias-collision",
            context_changes={
                "protected_read_roots": [str(path) for path in protected_roots],
                "protected_write_paths": [str(path) for path in protected_writes],
            },
            receipt_changes={"protected_roots_sha256": roots_digest},
        )
        receipt_path = self.tmpdir / "e\u0301vidence.json"
        temp_probe = Path(str(payload["temp_probe_path"]))
        targets = {receipt_path, denial_path, temp_probe, *protected_writes}
        real_lstat = os.lstat

        def reject_target_lstat(path: object, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path) in targets:
                self.fail("target lstat occurred before collision rejection")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(inherited.os, "lstat", side_effect=reject_target_lstat):
            self.assert_protocol_error(
                "INHERITED_OUTPUT_COLLISION",
                lambda: self._validate(
                    context,
                    environment,
                    receipt_path,
                    denial_path,
                ),
            )
        self.assert_no_runtime_artifacts(payload, receipt_path, denial_path)


class LauncherContractC1Test(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        temp_parent = Path(raw_temp_parent).resolve(strict=True)
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-launcher-c1-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        protected_home = self.base / "protected-home"
        protected_codex = protected_home / ".codex"
        protected_codex.mkdir(parents=True)
        self.protected_roots = (protected_home, protected_codex)
        self.root = self.base / "snapshot"
        self.root.mkdir()
        self.nonce = "c" * 64
        (self.root / ".release-control-root.json").write_text(
            json.dumps({"kind": "snapshot", "nonce": self.nonce}),
            encoding="utf-8",
        )
        self.caller_tmpdir = self.base / "caller-tmp"
        self.caller_tmpdir.mkdir()
        self.environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": str(self.caller_tmpdir),
        }

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _paths(self, suffix: str) -> tuple[Path, Path]:
        return (
            self.caller_tmpdir / f"receipt-{suffix}.json",
            self.caller_tmpdir / f"denial-{suffix}.log",
        )

    def _invoke(
        self,
        launcher_args: list[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SYSTEM_PYTHON), str(RUNNER), *launcher_args],
            cwd=self.base,
            env=environment or self.environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _valid_prefix(self, receipt: Path, denial: Path) -> list[str]:
        return [
            "--root",
            str(self.root),
            "--nonce",
            self.nonce,
            "--timeout",
            "1",
            "--receipt",
            str(receipt),
            "--denial-log",
            str(denial),
        ]

    def test_exact_flag_order_duplicates_and_separator_fail_without_outputs(self) -> None:
        cases: list[tuple[str, list[str]]] = []
        receipt, denial = self._paths("reordered")
        cases.append(
            (
                "reordered",
                [
                    "--nonce",
                    self.nonce,
                    "--root",
                    str(self.root),
                    "--timeout",
                    "1",
                    "--receipt",
                    str(receipt),
                    "--denial-log",
                    str(denial),
                    "--",
                    "/usr/bin/true",
                ],
            )
        )
        receipt, denial = self._paths("duplicate")
        cases.append(
            (
                "duplicate",
                [
                    *self._valid_prefix(receipt, denial),
                    "--nonce",
                    self.nonce,
                    "--",
                    "/usr/bin/true",
                ],
            )
        )
        receipt, denial = self._paths("missing-separator")
        cases.append(
            (
                "missing-separator",
                [*self._valid_prefix(receipt, denial), "/usr/bin/true"],
            )
        )

        for suffix, argv in cases:
            with self.subTest(suffix=suffix):
                receipt, denial = self._paths(suffix)
                result = self._invoke(argv)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("LAUNCHER_GRAMMAR_INVALID", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())

    def test_inherited_flag_duplicate_or_reordered_is_grammar_error(self) -> None:
        context = self.caller_tmpdir / "context.json"
        cases = (
            (
                "duplicate",
                [
                    *self._valid_prefix(*self._paths("inherited-duplicate")),
                    "--inherited-sandbox-context",
                    str(context),
                    "--inherited-sandbox-context",
                    str(context),
                    "--",
                    "/usr/bin/true",
                ],
            ),
            (
                "reordered",
                [
                    "--root",
                    str(self.root),
                    "--nonce",
                    self.nonce,
                    "--timeout",
                    "1",
                    "--receipt",
                    str(self._paths("inherited-reordered")[0]),
                    "--inherited-sandbox-context",
                    str(context),
                    "--denial-log",
                    str(self._paths("inherited-reordered")[1]),
                    "--",
                    "/usr/bin/true",
                ],
            ),
        )
        for suffix, argv in cases:
            with self.subTest(suffix=suffix):
                receipt, denial = self._paths(f"inherited-{suffix}")
                result = self._invoke(argv)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("LAUNCHER_GRAMMAR_INVALID", result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())

    def test_separator_makes_all_remaining_command_arguments_opaque(self) -> None:
        receipt, denial = self._paths("opaque-parser")
        command = (
            "/usr/bin/true",
            "--",
            "--inherited-sandbox-context",
            "literal-context",
        )
        try:
            parsed = launcher.parse_exact_argv(
                [*self._valid_prefix(receipt, denial), "--", *command]
            )
        except launcher.LaunchError as exc:
            self.fail(f"separator command was reinterpreted: {exc.status}")
        self.assertEqual(parsed.command, command)

    def test_command_digest_uses_structured_exact_path_boundary_tokens(self) -> None:
        root_text = str(self.root)
        records = (
            (root_text,),
            ("<EXECUTION_ROOT>",),
            (f"prefix-{root_text}-suffix",),
            (str(self.root / "nested" / "child.py"),),
        )
        digests = {
            launcher._normalized_command_digest(command, self.root)
            for command in records
        }
        self.assertEqual(len(digests), len(records))

        other_root = self.base / "other-snapshot"
        other_root.mkdir()
        self.assertEqual(
            launcher._normalized_command_digest(
                (str(self.root / "nested" / "child.py"),), self.root
            ),
            launcher._normalized_command_digest(
                (str(other_root / "nested" / "child.py"),), other_root
            ),
        )

    def test_unlinked_capture_fd_retries_pre_close_interrupt_without_leaking(self) -> None:
        capture_path = self.caller_tmpdir / "interrupted-unlinked.capture"
        real_close = os.close
        captured_descriptor: int | None = None
        close_calls = 0

        def fail_after_unlink(
            descriptor: int,
            _mode: str,
            *,
            closefd: bool,
        ) -> object:
            nonlocal captured_descriptor
            self.assertTrue(closefd)
            self.assertFalse(capture_path.exists())
            captured_descriptor = descriptor
            raise RuntimeError("injected fdopen failure after unlink")

        def interrupt_first_close(descriptor: int) -> None:
            nonlocal close_calls
            self.assertEqual(descriptor, captured_descriptor)
            close_calls += 1
            if close_calls == 1:
                raise KeyboardInterrupt()
            real_close(descriptor)

        try:
            with mock.patch.object(
                launcher.os,
                "fdopen",
                side_effect=fail_after_unlink,
            ), mock.patch.object(
                launcher.os,
                "close",
                side_effect=interrupt_first_close,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected fdopen failure after unlink",
                ):
                    launcher._capture_file(
                        self.caller_tmpdir,
                        capture_path.name,
                    )

            self.assertEqual(close_calls, 2)
            self.assertIsNotNone(captured_descriptor)
            with self.assertRaises(OSError):
                os.fstat(captured_descriptor)
        finally:
            if captured_descriptor is not None:
                try:
                    real_close(captured_descriptor)
                except OSError:
                    pass

    def test_output_files_close_retries_interrupt_and_closes_both_descriptors(
        self,
    ) -> None:
        receipt, denial = self._paths("output-close-interrupt")
        outputs = launcher.create_outputs(receipt, denial)
        receipt_descriptor = outputs.receipt_fd
        denial_descriptor = outputs.denial_fd
        real_close = os.close
        close_calls: list[int] = []

        def interrupt_first_receipt_close(descriptor: int) -> None:
            close_calls.append(descriptor)
            if descriptor == receipt_descriptor and close_calls.count(descriptor) == 1:
                raise KeyboardInterrupt("injected pre-close interrupt")
            real_close(descriptor)

        try:
            with mock.patch.object(
                launcher.os,
                "close",
                side_effect=interrupt_first_receipt_close,
            ), self.assertRaises(launcher.LaunchError) as raised:
                outputs.close()

            self.assertEqual(raised.exception.status, "OUTPUT_CLOSE_FAILED")
            self.assertEqual(close_calls.count(receipt_descriptor), 2)
            self.assertIn(denial_descriptor, close_calls)
            self.assertEqual(outputs.receipt_fd, -1)
            self.assertEqual(outputs.denial_fd, -1)
            for descriptor in (receipt_descriptor, denial_descriptor):
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        finally:
            for descriptor in (outputs.receipt_fd, outputs.denial_fd):
                if descriptor >= 0:
                    try:
                        real_close(descriptor)
                    except OSError:
                        pass

    def test_main_converts_output_close_failure_to_typed_exit(self) -> None:
        receipt, denial = self._paths("main-output-close")
        stderr = io.StringIO()
        real_output_close = launcher.OutputFiles.close
        close_attempts = 0

        def fail_once(outputs: launcher.OutputFiles) -> None:
            nonlocal close_attempts
            close_attempts += 1
            if close_attempts == 1:
                raise launcher.LaunchError("OUTPUT_CLOSE_FAILED")
            real_output_close(outputs)

        with mock.patch.dict(
            launcher.os.environ,
            self.environment,
            clear=True,
        ), mock.patch.object(
            launcher.OutputFiles,
            "close",
            autospec=True,
            side_effect=fail_once,
        ) as close_outputs, contextlib.redirect_stderr(stderr):
            result = launcher.main(
                [
                    *self._valid_prefix(receipt, denial),
                    "--",
                    "/usr/bin/true",
                ]
            )

        self.assertEqual(result, 2)
        self.assertEqual(close_outputs.call_count, 2)
        self.assertIn("OUTPUT_CLOSE_FAILED", stderr.getvalue())

    def test_direct_quota_blocker_precedes_invocation_materialization_and_spawn(
        self,
    ) -> None:
        receipts: list[bytes] = []
        with mock.patch.object(
            launcher,
            "_create_direct_invocation_root",
            side_effect=AssertionError("quota blocker reached invocation creation"),
        ) as create_invocation, mock.patch.object(
            launcher,
            "build_direct_environment",
            side_effect=AssertionError("quota blocker reached environment materialization"),
        ) as materialize, mock.patch.object(
            launcher,
            "_run_direct_child",
            side_effect=AssertionError("quota blocker reached candidate child"),
        ) as run_child, mock.patch.object(
            launcher.subprocess,
            "Popen",
            side_effect=AssertionError("quota blocker reached candidate spawn"),
        ) as spawn:
            for attempt in range(2):
                receipt, denial = self._paths(f"quota-direct-{attempt}")
                stderr = io.StringIO()
                with mock.patch.dict(
                    launcher.os.environ,
                    self.environment,
                    clear=True,
                ), contextlib.redirect_stderr(stderr):
                    result = launcher.main(
                        [
                            *self._valid_prefix(receipt, denial),
                            "--",
                            "/usr/bin/true",
                        ]
                    )
                self.assertEqual(result, 2)
                self.assertEqual(stderr.getvalue(), "")
                receipts.append(receipt.read_bytes())
                self.assertEqual(denial.read_bytes(), b"")

        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(
            json.loads(receipts[0]),
            {
                "schema": "samvil.release-control.launch-receipt.v1",
                "status": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
                "profile_class": CANDIDATE_PROFILE_CLASS,
                "promotable": False,
                "terminal_state": "BLOCKED_ENVIRONMENT",
                "exit_code": 2,
            },
        )
        create_invocation.assert_not_called()
        materialize.assert_not_called()
        run_child.assert_not_called()
        spawn.assert_not_called()

    def test_inherited_quota_blocker_precedes_boundary_probe_and_spawn(self) -> None:
        receipt, denial = self._paths("quota-inherited")
        invocation_root = self.base / "inherited-invocation"
        invocation_root.mkdir()
        inherited_tmpdir = invocation_root / "tmp"
        inherited_tmpdir.mkdir()
        policy = launcher.render_trusted_policy(
            self.root,
            invocation_root,
            self.protected_roots,
        )
        validated = mock.Mock(
            execution_root=self.root,
            invocation_root=invocation_root,
            protected_read_roots=self.protected_roots,
            profile_class=policy.profile_class,
            profile_bytes=policy.profile_bytes,
            environment_keys=launcher.CHILD_ENVIRONMENT_KEYS,
            receipt_path=receipt,
            denial_log_path=denial,
            tmpdir=inherited_tmpdir,
        )
        context = self.caller_tmpdir / "quota-inherited-context.json"
        with mock.patch.object(
            launcher,
            "sanitize_inherited_environment",
            return_value={},
        ), mock.patch.object(
            launcher.inherited,
            "validate_inherited_request",
            return_value=validated,
        ), mock.patch.object(
            launcher.inherited,
            "run_boundary_probes",
            side_effect=AssertionError("quota blocker reached boundary probes"),
        ) as probes, mock.patch.object(
            launcher,
            "_run_inherited_child",
            side_effect=AssertionError("quota blocker reached inherited child"),
        ) as run_child, mock.patch.object(
            launcher.subprocess,
            "Popen",
            side_effect=AssertionError("quota blocker reached inherited spawn"),
        ) as spawn, mock.patch.dict(
            launcher.os.environ,
            self.environment,
            clear=True,
        ):
            result = launcher.main(
                [
                    *self._valid_prefix(receipt, denial),
                    "--inherited-sandbox-context",
                    str(context),
                    "--",
                    "/usr/bin/true",
                ]
            )

        self.assertEqual(result, 2)
        self.assertEqual(
            json.loads(receipt.read_bytes()),
            {
                "schema": "samvil.release-control.launch-receipt.v1",
                "status": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
                "profile_class": launcher.CONTROL_PROFILE_CLASS,
                "promotable": False,
                "terminal_state": "BLOCKED_ENVIRONMENT",
                "exit_code": 2,
            },
        )
        self.assertEqual(denial.read_bytes(), b"")
        probes.assert_not_called()
        run_child.assert_not_called()
        spawn.assert_not_called()

    def test_verifier_quota_blocker_precedes_candidate_resolution_and_materialization(
        self,
    ) -> None:
        receipt = self.caller_tmpdir / "quota-verifier-receipt.json"
        argv = [
            str(VERIFIER),
            "--candidate",
            str(self.base / "missing-candidate"),
            "--authorization",
            str(self.base / "missing-authorization.json"),
            "--control-root",
            str(self.base / "missing-control"),
            "--expected-control-commit",
            "d" * 40,
            "--signature-policy",
            "required",
            "--nonce",
            self.nonce,
            "--receipt",
            str(receipt),
        ]
        with mock.patch.object(
            verifier.tempfile,
            "TemporaryDirectory",
            side_effect=AssertionError("quota blocker reached temp materialization"),
        ) as create_temp, mock.patch.object(
            verifier,
            "verify_candidate",
            side_effect=AssertionError("quota blocker reached candidate verification"),
        ) as verify_candidate, mock.patch.object(
            verifier,
            "materialize_snapshot",
            side_effect=AssertionError("quota blocker reached snapshot materialization"),
        ) as materialize, mock.patch.object(
            verifier,
            "execute_checks",
            side_effect=AssertionError("quota blocker reached candidate checks"),
        ) as execute, mock.patch.object(
            verifier.subprocess,
            "Popen",
            side_effect=AssertionError("quota blocker reached candidate spawn"),
        ) as spawn, mock.patch.object(
            verifier.sys,
            "argv",
            argv,
        ), mock.patch.dict(
            verifier.os.environ,
            {"TMPDIR": str(self.caller_tmpdir)},
            clear=True,
        ):
            with self.assertRaises(SystemExit) as raised:
                verifier.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(
            json.loads(receipt.read_bytes()),
            {
                "schema_version": 1,
                "status": "BLOCKED_ENVIRONMENT",
                "verdict": "BLOCKED",
                "promotable": False,
                "blocker": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
            },
        )
        create_temp.assert_not_called()
        verify_candidate.assert_not_called()
        materialize.assert_not_called()
        execute.assert_not_called()
        spawn.assert_not_called()

    def test_non_executable_regular_argv0_fails_before_outputs(self) -> None:
        command = self.root / "not-executable"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o600)
        receipt, denial = self._paths("not-executable")
        result = self._invoke(
            [*self._valid_prefix(receipt, denial), "--", str(command)]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID_COMMAND", result.stderr)
        self.assertFalse(receipt.exists())
        self.assertFalse(denial.exists())

    def test_receipt_partial_then_oserror_replaces_bytes_with_typed_blocker(self) -> None:
        receipt, denial = self._paths("partial-write")
        outputs = launcher.create_outputs(receipt, denial)
        real_write = os.write
        calls = 0

        def partial_then_fail(descriptor: int, data: bytes) -> int:
            nonlocal calls
            if descriptor != outputs.receipt_fd:
                return real_write(descriptor, data)
            calls += 1
            if calls == 1:
                return real_write(descriptor, data[:7])
            if calls == 2:
                raise OSError(errno.EIO, "injected receipt write failure")
            return real_write(descriptor, data)

        try:
            with mock.patch.object(launcher.os, "write", side_effect=partial_then_fail):
                try:
                    launcher.write_receipt(
                        outputs,
                        {
                            "schema": "samvil.release-control.launch-receipt.v1",
                            "status": "PASS",
                            "promotable": False,
                        },
                    )
                except Exception as exc:
                    self.assertIsInstance(exc, launcher.LaunchError)
                    self.assertEqual(exc.status, "OUTPUT_WRITE_FAILED")
                else:
                    self.fail("a replaced blocker receipt must preserve terminal failure")
        finally:
            outputs.close()

        raw = receipt.read_bytes()
        self.assertEqual(raw.count(b"\n"), 1)
        payload = json.loads(raw)
        self.assertEqual(payload["status"], "OUTPUT_WRITE_FAILED")
        self.assertEqual(payload["primary_status"], "PASS")
        self.assertFalse(payload["promotable"])
        self.assertNotIn(str(self.base), raw.decode("utf-8"))

    def test_receipt_initial_oserror_replaces_empty_file_with_typed_blocker(self) -> None:
        receipt, denial = self._paths("initial-write")
        outputs = launcher.create_outputs(receipt, denial)
        real_write = os.write
        failed = False

        def fail_once(descriptor: int, data: bytes) -> int:
            nonlocal failed
            if descriptor == outputs.receipt_fd and not failed:
                failed = True
                raise OSError(errno.EIO, "injected initial receipt write failure")
            return real_write(descriptor, data)

        try:
            with mock.patch.object(launcher.os, "write", side_effect=fail_once):
                try:
                    launcher.write_receipt(
                        outputs,
                        {
                            "schema": "samvil.release-control.launch-receipt.v1",
                            "status": "TIMEOUT",
                            "promotable": False,
                        },
                    )
                except Exception as exc:
                    self.assertIsInstance(exc, launcher.LaunchError)
                    self.assertEqual(exc.status, "OUTPUT_WRITE_FAILED")
                else:
                    self.fail("a replaced blocker receipt must preserve terminal failure")
        finally:
            outputs.close()

        payload = json.loads(receipt.read_bytes())
        self.assertEqual(payload["status"], "OUTPUT_WRITE_FAILED")
        self.assertEqual(payload["primary_status"], "TIMEOUT")
        self.assertFalse(payload["promotable"])

    def test_root_command_nonce_and_timeout_are_exact_before_any_write(self) -> None:
        receipt, denial = self._paths("validation")
        cases = (
            ("relative-root", "INVALID_EXECUTION_ROOT", [
                "--root", "snapshot", "--nonce", self.nonce,
                "--timeout", "1", "--receipt", str(receipt),
                "--denial-log", str(denial), "--", "/usr/bin/true",
            ]),
            ("noncanonical-root", "INVALID_EXECUTION_ROOT", [
                "--root", str(self.root / ".." / self.root.name),
                "--nonce", self.nonce, "--timeout", "1",
                "--receipt", str(receipt), "--denial-log", str(denial),
                "--", "/usr/bin/true",
            ]),
            ("relative-command", "INVALID_COMMAND", [
                *self._valid_prefix(receipt, denial), "--", "bin/true",
            ]),
            ("nonce", "INVALID_NONCE", [
                "--root", str(self.root), "--nonce", "ABC",
                "--timeout", "1", "--receipt", str(receipt),
                "--denial-log", str(denial), "--", "/usr/bin/true",
            ]),
            ("timeout", "INVALID_TIMEOUT", [
                "--root", str(self.root), "--nonce", self.nonce,
                "--timeout", "nan", "--receipt", str(receipt),
                "--denial-log", str(denial), "--", "/bin/true",
            ]),
        )
        for name, blocker, argv in cases:
            with self.subTest(name=name):
                result = self._invoke(argv)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(blocker, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())

    def test_output_preflight_is_no_write_and_never_uses_fallback_parent(self) -> None:
        outside_receipt = self.base / "outside-receipt.json"
        valid_denial = self.caller_tmpdir / "valid-denial.log"
        outside_result = self._invoke(
            [*self._valid_prefix(outside_receipt, valid_denial), "--", "/usr/bin/true"]
        )
        self.assertNotEqual(outside_result.returncode, 0)
        self.assertIn("OUTPUT_INVALID", outside_result.stderr)
        self.assertFalse(outside_receipt.exists())
        self.assertFalse(valid_denial.exists())

        occupied, denial = self._paths("occupied")
        occupied.write_text("preserve-me", encoding="utf-8")
        occupied_result = self._invoke(
            [*self._valid_prefix(occupied, denial), "--", "/usr/bin/true"]
        )
        self.assertNotEqual(occupied_result.returncode, 0)
        self.assertIn("OUTPUT_INVALID", occupied_result.stderr)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "preserve-me")
        self.assertFalse(denial.exists())

    def test_output_matrix_rejects_directory_symlink_fifo_parent_alias_and_name_aliases(self) -> None:
        occupied_file = self.caller_tmpdir / "occupied-source"
        occupied_file.write_text("preserve", encoding="utf-8")
        occupied_directory = self.caller_tmpdir / "occupied-directory"
        occupied_directory.mkdir()
        occupied_symlink = self.caller_tmpdir / "occupied-symlink"
        occupied_symlink.symlink_to(occupied_file)
        occupied_fifo = self.caller_tmpdir / "occupied-fifo"
        os.mkfifo(occupied_fifo, 0o600)
        parent_real = self.caller_tmpdir / "real-parent"
        parent_real.mkdir()
        parent_alias = self.caller_tmpdir / "parent-alias"
        parent_alias.symlink_to(parent_real, target_is_directory=True)
        cases = (
            ("directory", occupied_directory, self.caller_tmpdir / "denial-directory"),
            ("symlink", occupied_symlink, self.caller_tmpdir / "denial-symlink"),
            ("fifo", occupied_fifo, self.caller_tmpdir / "denial-fifo"),
            ("parent-alias", parent_alias / "receipt", self.caller_tmpdir / "denial-parent"),
            (
                "ascii-case-alias",
                self.caller_tmpdir / "Boundary-Receipt.json",
                self.caller_tmpdir / "boundary-receipt.JSON",
            ),
            (
                "unicode-alias",
                self.caller_tmpdir / "évidence.json",
                self.caller_tmpdir / "e\u0301vidence.json",
            ),
        )
        for suffix, receipt, denial in cases:
            with self.subTest(suffix=suffix):
                result = self._invoke(
                    [*self._valid_prefix(receipt, denial), "--", "/usr/bin/true"]
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, r"OUTPUT_(?:INVALID|COLLISION)")
                self.assertFalse(denial.exists())
        self.assertEqual(occupied_file.read_text(encoding="utf-8"), "preserve")
        self.assertTrue(occupied_directory.is_dir())
        self.assertTrue(occupied_symlink.is_symlink())
        self.assertTrue(stat.S_ISFIFO(os.lstat(occupied_fifo).st_mode))

    def test_direct_mode_rejects_each_bootstrap_environment_combination_without_outputs(self) -> None:
        bootstrap_cases = (
            {inherited.BOOTSTRAP_NONCE_ENV: "a" * 64},
            {inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "b" * 64},
            {
                inherited.BOOTSTRAP_NONCE_ENV: "a" * 64,
                inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "b" * 64,
            },
            {"SAMVIL_BOOTSTRAP_FORGED": "candidate"},
        )
        for index, additions in enumerate(bootstrap_cases):
            with self.subTest(additions=sorted(additions)):
                receipt, denial = self._paths(f"bootstrap-matrix-{index}")
                result = self._invoke(
                    [*self._valid_prefix(receipt, denial), "--", "/usr/bin/true"],
                    environment={**self.environment, **additions},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("INHERITED_ENVIRONMENT_ONLY", result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())

    def test_output_collision_with_trusted_probe_paths_precedes_any_lstat_or_write(self) -> None:
        self.assertIn(
            "reserved_paths",
            inspect.signature(launcher.validate_direct_output_preflight).parameters,
            "direct output preflight does not bind trusted probe paths",
        )
        reserved = self.caller_tmpdir / "reserved-protected-write"
        denial = self.caller_tmpdir / "reserved-denial.log"
        with self.assertRaises(launcher.LaunchError) as raised:
            launcher.validate_direct_output_preflight(
                str(reserved),
                str(denial),
                tmpdir=self.caller_tmpdir,
                execution_root=self.root,
                reserved_paths=(reserved,),
            )
        self.assertEqual(raised.exception.status, "OUTPUT_COLLISION")
        self.assertFalse(reserved.exists())
        self.assertFalse(denial.exists())

    def test_repository_root_marker_nonce_and_remote_tokens_fail_before_outputs(self) -> None:
        receipt, denial = self._paths("adversarial")
        cases: list[tuple[str, str, list[str]]] = []
        (self.root / ".git").mkdir()
        cases.append(
            (
                "repository-root",
                "INVALID_EXECUTION_ROOT",
                [*self._valid_prefix(receipt, denial), "--", "/usr/bin/true"],
            )
        )
        for name, blocker, argv in cases:
            with self.subTest(name=name):
                result = self._invoke(argv)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(blocker, result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())
        (self.root / ".git").rmdir()

        wrong_nonce = "e" * 64
        nonce_argv = self._valid_prefix(receipt, denial)
        nonce_argv[3] = wrong_nonce
        result = self._invoke([*nonce_argv, "--", "/usr/bin/true"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NONCE_MISMATCH", result.stderr)
        self.assertFalse(receipt.exists())
        self.assertFalse(denial.exists())

        for index, command in enumerate(
            (
                ["/usr/bin/git", "clone", "https://example.invalid/repo"],
                ["/usr/bin/ssh", "example.invalid"],
            )
        ):
            with self.subTest(command=command):
                current_receipt, current_denial = self._paths(f"remote-{index}")
                result = self._invoke(
                    [*self._valid_prefix(current_receipt, current_denial), "--", *command]
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("REMOTE_TARGET_REJECTED", result.stderr)
                self.assertFalse(current_receipt.exists())
                self.assertFalse(current_denial.exists())

class LauncherPolicyC2Test(unittest.TestCase):
    def setUp(self) -> None:
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-launcher-c2-",
            dir=Path(raw_temp_parent).resolve(strict=True),
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        protected_home = self.base / "protected-home"
        protected_codex = protected_home / ".codex"
        protected_codex.mkdir(parents=True)
        self.protected_roots = (protected_home, protected_codex)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_direct_invocation_cleanup_removes_locked_tree_without_following_symlinks(self) -> None:
        invocation = self.base / "cleanup-invocation"
        locked = invocation / "locked"
        locked.mkdir(parents=True)
        (locked / "payload").write_bytes(b"candidate")
        external = self.base / "external-sentinel"
        external.write_text("keep", encoding="utf-8")
        external.chmod(0o755)
        external_before = os.stat(external)
        (invocation / "external-link").symlink_to(external)
        os.link(external, invocation / "external-hardlink")
        self.assertEqual(os.stat(external).st_nlink, external_before.st_nlink + 1)
        locked.chmod(0)
        invocation.chmod(0)

        launcher._cleanup_direct_invocation_root(invocation)
        self.assertFalse(invocation.exists())
        self.assertEqual(external.read_text(encoding="utf-8"), "keep")
        external_after = os.stat(external)
        self.assertEqual(external_after.st_nlink, external_before.st_nlink)
        self.assertEqual(
            (external_after.st_dev, external_after.st_ino, stat.S_IMODE(external_after.st_mode)),
            (external_before.st_dev, external_before.st_ino, 0o755),
        )

    def test_direct_wrapper_evidence_emit_retries_partial_and_interrupted_writes(self) -> None:
        tree = ast.parse(launcher.DIRECT_BOUNDARY_WRAPPER)
        emit_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "emit"
        )
        compiled = compile(
            ast.fix_missing_locations(ast.Module(body=[emit_node], type_ignores=[])),
            "<direct-boundary-emit>",
            "exec",
        )

        class PartialWriter:
            def __init__(self) -> None:
                self.interrupted = False
                self.output = bytearray()

            def write(self, descriptor: int, data: bytes) -> int:
                self.assert_descriptor(descriptor)
                if not self.interrupted:
                    self.interrupted = True
                    raise InterruptedError
                written = min(7, len(data))
                self.output.extend(data[:written])
                return written

            @staticmethod
            def assert_descriptor(descriptor: int) -> None:
                if descriptor != 17:
                    raise AssertionError("wrong evidence descriptor")

        writer = PartialWriter()
        namespace = {"os": writer, "json": json, "evidence_fd": 17}
        exec(compiled, namespace)
        payload = {"status": "PASS", "evidence": {"blob": "x" * 2048}}
        namespace["emit"](payload)
        self.assertEqual(
            bytes(writer.output),
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )

        namespace["os"] = mock.Mock(write=mock.Mock(return_value=0))
        with self.assertRaisesRegex(SystemExit, "90"):
            namespace["emit"]({"status": "PASS"})

    def test_macos_rusage_v2_ctypes_layout_matches_the_sdk_abi(self) -> None:
        self.assertEqual(
            [name for name, _ in launcher._RUsageInfoV2._fields_][-2:],
            ["ri_diskio_bytesread", "ri_diskio_byteswritten"],
        )
        self.assertEqual(ctypes.sizeof(launcher._RUsageInfoV2), 160)
        guard_size = 32
        buffer = (ctypes.c_ubyte * (160 + guard_size))()
        for index in range(160, len(buffer)):
            buffer[index] = 0xA5
        function = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pid_rusage
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(launcher._RUsageInfoV2),
        ]
        function.restype = ctypes.c_int
        result = function(
            os.getpid(),
            2,
            ctypes.cast(buffer, ctypes.POINTER(launcher._RUsageInfoV2)),
        )
        self.assertEqual(result, 0, ctypes.get_errno())
        self.assertEqual(bytes(buffer[160:]), b"\xa5" * guard_size)

    def test_trusted_renderer_has_fixed_equivalence_evidence_for_nested_roots(self) -> None:
        self.assertTrue(
            hasattr(launcher, "render_trusted_policy"),
            "trusted ordered-slot renderer is missing",
        )
        invocation_a = self.base / "outer-a"
        invocation_b = self.base / "outer-b"
        execution_a = invocation_a / "candidate"
        execution_b = invocation_b / "candidate"
        for path in (execution_a, execution_b):
            path.mkdir(parents=True)

        first = launcher.render_trusted_policy(
            execution_a, invocation_a, self.protected_roots
        )
        second = launcher.render_trusted_policy(
            execution_b, invocation_b, self.protected_roots
        )

        self.assertEqual(first.profile_class, inherited.INHERITED_PROFILE_CLASS)
        self.assertNotEqual(first.profile_sha256, second.profile_sha256)
        self.assertEqual(first.source_template_sha256, second.source_template_sha256)
        self.assertEqual(
            first.normalized_policy_sha256, second.normalized_policy_sha256
        )
        self.assertEqual(first.decisions, second.decisions)
        encoded = json.dumps(first.equivalence_evidence(), sort_keys=True)
        self.assertNotIn(str(self.base), encoded)

    def test_candidate_renderer_is_fixed_strict_and_not_user_selectable(self) -> None:
        invocation = self.base / "candidate-invocation"
        execution = self.base / "candidate-execution"
        invocation.mkdir()
        execution.mkdir()

        policy = launcher.render_candidate_policy(
            execution, invocation, self.protected_roots
        )

        self.assertEqual(policy.profile_class, CANDIDATE_PROFILE_CLASS)
        self.assertIn(b"(deny process-fork)", policy.profile_bytes)
        self.assertIn(b"(allow process-exec)", policy.profile_bytes)
        self.assertNotIn(b"(allow process*)", policy.profile_bytes)
        self.assertNotIn(b"(allow signal)", policy.profile_bytes)
        self.assertNotIn(b"(allow sysctl-read)", policy.profile_bytes)
        self.assertNotIn(b"(allow mach-lookup)", policy.profile_bytes)
        self.assertNotIn(b"(allow ipc-posix-shm)", policy.profile_bytes)
        self.assertEqual(
            policy.source_template_sha256,
            sha256(launcher.CANDIDATE_PROFILE_SOURCE_TEMPLATE),
        )
        self.assertEqual(
            set(launcher.LaunchArguments.__dataclass_fields__),
            {
                "root",
                "nonce",
                "timeout",
                "receipt",
                "denial_log",
                "inherited_context",
                "command",
            },
        )

    def test_renderer_rejects_any_template_or_ordered_slot_drift(self) -> None:
        self.assertTrue(
            hasattr(launcher, "PROFILE_SLOT_MANIFEST"),
            "trusted ordered-slot manifest is missing",
        )
        invocation = self.base / "outer"
        execution = invocation / "candidate"
        execution.mkdir(parents=True)
        trusted = launcher.PROFILE_SLOT_MANIFEST
        variants = (
            ("missing", trusted[:-1]),
            ("extra", (*trusted, trusted[-1])),
            ("duplicated", (trusted[0], *trusted)),
            ("reordered", tuple(reversed(trusted))),
            (
                "overlapping",
                (
                    launcher.ProfileSlot(
                        trusted[0].name,
                        trusted[0].start,
                        trusted[0].end + 1,
                    ),
                    *trusted[1:],
                ),
            ),
        )
        for name, manifest in variants:
            with self.subTest(name=name):
                with self.assertRaises(launcher.LaunchError) as raised:
                    launcher.render_trusted_policy(
                        execution,
                        invocation,
                        self.protected_roots,
                        slot_manifest=manifest,
                    )
                self.assertEqual(raised.exception.status, "PROFILE_TEMPLATE_INVALID")

        tampered = launcher.PROFILE_SOURCE_TEMPLATE + b"\n{{EXECUTION_ROOT}}"
        with self.assertRaises(launcher.LaunchError) as raised:
            launcher.render_trusted_policy(
                execution,
                invocation,
                self.protected_roots,
                source_template=tampered,
            )
        self.assertEqual(raised.exception.status, "PROFILE_TEMPLATE_INVALID")

    def test_environment_is_fixed_path_scoped_and_strips_all_bootstrap_keys(self) -> None:
        self.assertTrue(
            hasattr(launcher, "build_direct_environment"),
            "fixed sanitized environment builder is missing",
        )
        invocation = self.base / "direct-invocation"
        invocation.mkdir()
        environment = launcher.build_direct_environment(invocation)
        self.assertEqual(tuple(sorted(environment)), launcher.CHILD_ENVIRONMENT_KEYS)
        self.assertFalse(
            any(key.startswith(inherited.BOOTSTRAP_PREFIX) for key in environment)
        )
        for key in (
            "HOME",
            "CODEX_HOME",
            "CLAUDE_CONFIG_DIR",
            "GNUPGHOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ):
            self.assertTrue(Path(environment[key]).is_relative_to(invocation))

        inherited_parent = {
            **environment,
            inherited.BOOTSTRAP_NONCE_ENV: "a" * 64,
            inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "b" * 64,
            "SAMVIL_BOOTSTRAP_FORGED": "candidate",
            "UNTRUSTED_EXTRA": "candidate",
        }
        sanitized = launcher.sanitize_inherited_environment(inherited_parent)
        self.assertEqual(tuple(sorted(sanitized)), launcher.CHILD_ENVIRONMENT_KEYS)
        self.assertFalse(any(key.startswith("SAMVIL_BOOTSTRAP_") for key in sanitized))
        self.assertNotIn("UNTRUSTED_EXTRA", sanitized)


class LauncherDirectC3Test(LauncherContractC1Test):
    def setUp(self) -> None:
        self.seatbelt_context = require_real_seatbelt_opt_in()
        super().setUp()

    def _run_direct(
        self,
        command: list[str],
        *,
        suffix: str,
        environment: dict[str, str] | None = None,
        timeout: str = "3",
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object], Path]:
        receipt, denial = self._paths(suffix)
        argv = self._valid_prefix(receipt, denial)
        argv[5] = timeout
        result = self._invoke([*argv, "--", *command], environment=environment)
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return result, payload, denial

    def test_direct_real_network_zero_boundary_runs_exactly_one_sandbox(self) -> None:
        script = self.root / "child.py"
        script.write_text(
            """import os
raise SystemExit(0 if not any(k.startswith('SAMVIL_BOOTSTRAP_') for k in os.environ) else 71)
""",
            encoding="utf-8",
        )
        result, receipt, denial = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="real"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["profile_class"], CANDIDATE_PROFILE_CLASS)
        self.assertEqual(receipt["sandbox_exec_count"], 1)
        self.assertEqual(receipt["sandbox_invocations"], 1)
        self.assertTrue(receipt["denial_observed"])
        self.assertEqual(receipt["environment_keys"], list(launcher.CHILD_ENVIRONMENT_KEYS))
        self.assertEqual(
            receipt["decisions"], list(launcher.CANDIDATE_PROFILE_DECISIONS)
        )
        self.assertRegex(receipt["profile_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            receipt["source_template_sha256"],
            sha256(launcher.CANDIDATE_PROFILE_SOURCE_TEMPLATE),
        )
        self.assertEqual(
            receipt["normalized_policy_sha256"],
            launcher.render_candidate_policy(
                self.root, self.base, self.protected_roots
            ).normalized_policy_sha256,
        )
        self.assertEqual(
            receipt["boundary_evidence"],
            {
                "applications_open_eperm": True,
                "dev_null_read": True,
                "rlimit_fsize_bytes": launcher.RLIMIT_FSIZE_BYTES,
                "rlimit_cpu_seconds": launcher.RLIMIT_CPU_SECONDS,
                "rlimit_nofile_count": launcher.RLIMIT_NOFILE_COUNT,
                "resource_status": "within_limits",
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
            },
        )
        self.assertTrue(denial.is_file())
        self.assertNotIn(str(self.base), json.dumps(receipt, sort_keys=True))

    def test_direct_mode_rejects_every_bootstrap_variable_before_outputs(self) -> None:
        environment = {
            **self.environment,
            "SAMVIL_BOOTSTRAP_FORGED": "candidate",
        }
        result, receipt, denial = self._run_direct(
            ["/usr/bin/true"], suffix="bootstrap", environment=environment
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INHERITED_ENVIRONMENT_ONLY", result.stderr)
        self.assertEqual(receipt, {})
        self.assertFalse(denial.exists())

    def test_direct_child_receives_literal_separator_and_launcher_flag_unchanged(self) -> None:
        script = self.root / "opaque-argv.py"
        script.write_text(
            "import sys\n"
            "expected=['--','--inherited-sandbox-context','literal-context']\n"
            "raise SystemExit(0 if sys.argv[1:]==expected else 73)\n",
            encoding="utf-8",
        )
        result, receipt, _ = self._run_direct(
            [
                str(SYSTEM_PYTHON),
                str(script),
                "--",
                "--inherited-sandbox-context",
                "literal-context",
            ],
            suffix="opaque-command",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")

    def test_direct_popen_permission_race_is_typed_path_free_blocker(self) -> None:
        receipt, denial = self._paths("direct-spawn-race")
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(
            launcher.subprocess,
            "Popen",
            side_effect=PermissionError(errno.EACCES, "candidate path must not leak"),
        ), contextlib.redirect_stderr(stderr):
            try:
                result = launcher.main(
                    [*self._valid_prefix(receipt, denial), "--", "/usr/bin/true"]
                )
            except Exception as exc:
                self.fail(f"spawn error escaped launcher: {type(exc).__name__}")

        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(receipt.read_bytes())
        self.assertEqual(payload["status"], "CHILD_SPAWN_FAILED")
        self.assertFalse(payload["promotable"])
        self.assertNotIn(str(self.base), receipt.read_text(encoding="utf-8"))
        self.assertTrue(denial.is_file())

    def test_direct_cleanup_removes_deep_chmod_resistant_special_tree_without_following_symlink(self) -> None:
        external = self.base / "cleanup-external-owner-data"
        external.write_text("owner-data\n", encoding="utf-8")
        invocation_root = self.caller_tmpdir / f"samvil-release-control-{self.nonce}"
        script = self.root / "hostile-cleanup-tree.py"
        script.write_text(
            "import errno, os, pathlib, sys\n"
            "root=pathlib.Path(os.environ['TMPDIR'])\n"
            "directories=[root]\n"
            "current=root\n"
            "for index in range(48):\n"
            "    current=current/f'd{index}'\n"
            "    current.mkdir()\n"
            "    directories.append(current)\n"
            "(current/'payload').write_bytes(b'x')\n"
            "(current/'external-link').symlink_to(sys.argv[1])\n"
            "try:\n"
            "    os.link(sys.argv[2], current/'snapshot-hardlink')\n"
            "except OSError as exc:\n"
            "    if exc.errno not in (errno.EPERM, errno.EACCES): raise\n"
            "os.mkfifo(current/'candidate-fifo')\n"
            "for directory in reversed(directories):\n"
            "    directory.chmod(0)\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        script_bytes = script.read_bytes()
        script_before = os.stat(script)

        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), str(external), str(script)],
                suffix="hostile-cleanup-tree",
            )

            self.assertIn(result.returncode, (0, 125), result.stderr + json.dumps(receipt))
            self.assertIn(receipt["status"], ("PASS", "RESOURCE_LIMIT_EXCEEDED"))
            with self.assertRaises(FileNotFoundError):
                os.lstat(invocation_root)
            self.assertEqual(external.read_text(encoding="utf-8"), "owner-data\n")
            script_after = os.stat(script)
            self.assertEqual(script.read_bytes(), script_bytes)
            self.assertEqual(
                (script_after.st_dev, script_after.st_ino, stat.S_IMODE(script_after.st_mode)),
                (script_before.st_dev, script_before.st_ino, 0o755),
            )
        finally:
            try:
                os.lstat(invocation_root)
            except FileNotFoundError:
                pass
            else:
                for directory, child_directories, _ in os.walk(
                    invocation_root, topdown=True, followlinks=False
                ):
                    try:
                        os.chmod(directory, 0o700, follow_symlinks=False)
                    except OSError:
                        pass
                    for child in child_directories:
                        try:
                            os.chmod(
                                Path(directory) / child,
                                0o700,
                                follow_symlinks=False,
                            )
                        except OSError:
                            pass
                shutil.rmtree(invocation_root, ignore_errors=True)

    def test_direct_cleanup_failure_overrides_success_and_resource_results(self) -> None:
        cases = (
            ("success", 0, None, 0),
            ("resource", -signal.SIGKILL, "rss_bytes", 125),
        )
        boundary_raw = inherited.canonical_json_bytes(
            {"status": "PASS", "evidence": {}}
        )
        for suffix, child_code, resource_reason, original_code in cases:
            with self.subTest(suffix=suffix):
                receipt, denial = self._paths(f"cleanup-failure-{suffix}")
                invocation_root = (
                    self.caller_tmpdir / f"samvil-release-control-{self.nonce}"
                )
                outcome = launcher.ChildOutcome(
                    returncode=child_code,
                    timed_out=False,
                    child_cleanup_performed=resource_reason is not None,
                    stdout=b"",
                    stderr=b"",
                    boundary_raw=boundary_raw,
                    resource_limit_reason=resource_reason,
                    resource_evidence={
                        "observed_status": (
                            "limit_exceeded" if resource_reason else "within_limits"
                        ),
                        "reason": resource_reason,
                    },
                )
                self.assertIn(original_code, (0, 125))
                try:
                    with mock.patch.dict(
                        os.environ, self.environment, clear=True
                    ), mock.patch.object(
                        launcher, "_run_direct_child", return_value=outcome
                    ), mock.patch.object(
                        launcher,
                        "_cleanup_direct_invocation_root",
                        create=True,
                        side_effect=launcher.LaunchError(
                            "INVOCATION_CLEANUP_FAILED"
                        ),
                    ):
                        result = launcher.main(
                            [
                                *self._valid_prefix(receipt, denial),
                                "--",
                                "/usr/bin/true",
                            ]
                        )

                    payload = json.loads(receipt.read_text(encoding="utf-8"))
                    self.assertEqual(result, 2)
                    self.assertEqual(
                        payload["status"], "INVOCATION_CLEANUP_FAILED"
                    )
                    self.assertFalse(payload["promotable"])
                    self.assertNotIn(str(self.base), json.dumps(payload, sort_keys=True))
                finally:
                    shutil.rmtree(invocation_root, ignore_errors=True)

    def test_persistent_receipt_fd_failure_is_typed_stderr_and_never_valid_json(self) -> None:
        receipt, denial = self._paths("persistent-receipt-write")
        captured: dict[str, int] = {}
        real_create_outputs = launcher.create_outputs
        real_write = os.write

        def capture_outputs(receipt_path: Path, denial_path: Path) -> launcher.OutputFiles:
            outputs = real_create_outputs(receipt_path, denial_path)
            captured["receipt_fd"] = outputs.receipt_fd
            return outputs

        def fail_receipt(descriptor: int, data: bytes) -> int:
            if descriptor == captured.get("receipt_fd"):
                raise OSError(errno.EIO, "persistent injected receipt write failure")
            return real_write(descriptor, data)

        stderr = io.StringIO()
        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(
            launcher, "create_outputs", side_effect=capture_outputs
        ), mock.patch.object(
            launcher.os, "write", side_effect=fail_receipt
        ), contextlib.redirect_stderr(stderr):
            try:
                result = launcher.main(
                    [*self._valid_prefix(receipt, denial), "--", "/usr/bin/true"]
                )
            except Exception as exc:
                self.fail(f"persistent receipt error escaped: {type(exc).__name__}")

        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "OUTPUT_WRITE_FAILED\n")
        self.assertTrue(receipt.exists())
        self.assertEqual(receipt.read_bytes(), b"")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(receipt.read_text(encoding="utf-8"))
        self.assertTrue(denial.is_file())


class LauncherInheritedC4ChildOnlyTest(unittest.TestCase):
    """Candidate-side behavior only; the external controller owns all trust facts."""

    def test_external_controller_child_observes_exact_sanitized_boundary(self) -> None:
        marker = Path.cwd() / ".release-control-root.json"
        try:
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.skipTest("independent C4 external controller was not requested")
        if marker_payload.get("controller") != "independent-c4":
            self.skipTest("independent C4 external controller was not requested")
        self.assertFalse(any(key.startswith("SAMVIL_BOOTSTRAP_") for key in os.environ))
        self.assertEqual(sorted(os.environ), SAFE_COMMAND_ENVIRONMENT_KEYS)
        probe = Path(os.environ["TMPDIR"]) / "c4-child-roundtrip"
        probe.write_bytes(b"child-only")
        self.assertEqual(probe.read_bytes(), b"child-only")
        probe.unlink()
        for operation in ("bind", "connect"):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                with self.assertRaises(OSError) as raised:
                    if operation == "bind":
                        sock.bind(("127.0.0.1", 0))
                    else:
                        sock.connect(("127.0.0.1", 9))
                self.assertEqual(raised.exception.errno, errno.EPERM)
            finally:
                sock.close()


class InheritedLauncherIntegrationFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.seatbelt_context = require_real_seatbelt_opt_in()
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-inherited-launcher-",
            dir=Path(raw_temp_parent).resolve(strict=True),
        )
        self.base = Path(self._temp.name).resolve(strict=True)
        self.invocation = self.base / "outer"
        self.execution = self.invocation / "execution"
        self.control = self.invocation / "control"
        self.execution.mkdir(parents=True)
        self.control.mkdir()
        self.nonce = "d" * 64
        (self.execution / ".release-control-root.json").write_text(
            json.dumps({"kind": "snapshot", "nonce": self.nonce}),
            encoding="utf-8",
        )
        self.copied_runner = self.control / RUNNER.name
        shutil.copyfile(RUNNER, self.copied_runner)
        shutil.copyfile(TOOLS_ROOT / "inherited_context.py", self.control / "inherited_context.py")
        directories = {
            "HOME": self.invocation / "home",
            "CODEX_HOME": self.invocation / "codex-home",
            "CLAUDE_CONFIG_DIR": self.invocation / "claude-config",
            "GNUPGHOME": self.invocation / "gnupg",
            "TMPDIR": self.invocation / "tmp",
            "XDG_CACHE_HOME": self.invocation / "xdg-cache",
            "XDG_CONFIG_HOME": self.invocation / "xdg-config",
            "XDG_DATA_HOME": self.invocation / "xdg-data",
            "XDG_STATE_HOME": self.invocation / "xdg-state",
        }
        for path in directories.values():
            path.mkdir()
        gitconfig = self.invocation / "gitconfig"
        gitconfig.write_text("[credential]\n\thelper =\n", encoding="utf-8")
        self.environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            **{key: str(path) for key, path in directories.items()},
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS": "/usr/bin/false",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PIP_CONFIG_FILE": "/dev/null",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "__CF_USER_TEXT_ENCODING": f"0x{os.getuid():X}:0:0",
        }
        self.assertEqual(sorted(self.environment), SAFE_COMMAND_ENVIRONMENT_KEYS)
        self.profile_bytes, _, _ = independent_render_profile(
            self.execution, self.invocation
        )
        self.profile = self.control / "network-zero.sb"
        self.profile.write_bytes(self.profile_bytes)
        home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
        codex = (home / ".codex").resolve(strict=True)
        self.protected_roots = (home, codex)
        leaf = f".samvil-inherited-integration-{os.getpid()}-{id(self)}"
        self.protected_writes = (home / leaf, codex / leaf)
        for target in self.protected_writes:
            capture_outer_absence(target, "INTEGRATION_PRECHECK")
        self.outer_receipt = self.control / "outer-receipt.json"
        self.context = self.control / "inherited-context.json"
        self.context_payload: dict[str, object] = {}
        self.launcher_environment: dict[str, str] = {}
        self.rebuild_protocol()

    def tearDown(self) -> None:
        for target in self.protected_writes:
            capture_outer_absence(target, "INTEGRATION_POSTCHECK")
        self._temp.cleanup()

    def rebuild_protocol(
        self,
        *,
        context_changes: dict[str, object] | None = None,
        outer_changes: dict[str, object] | None = None,
    ) -> None:
        profile_digest = sha256(self.profile.read_bytes())
        outer = {
            "schema": inherited.OUTER_RECEIPT_SCHEMA,
            "status": "PASS",
            "nonce": self.nonce,
            "profile_class": INDEPENDENT_PROFILE_CLASS,
            "profile_sha256": profile_digest,
            "protected_roots_sha256": inherited.protected_roots_sha256(
                self.protected_roots
            ),
            "environment_keys": SAFE_COMMAND_ENVIRONMENT_KEYS,
        }
        if outer_changes:
            outer.update(outer_changes)
        outer_raw = inherited.canonical_json_bytes(outer)
        self.outer_receipt.write_bytes(outer_raw + b"\n")
        context = {
            "schema": inherited.CONTEXT_SCHEMA,
            "nonce": self.nonce,
            "profile_class": INDEPENDENT_PROFILE_CLASS,
            "profile_path": str(self.profile),
            "profile_sha256": profile_digest,
            "outer_receipt_path": str(self.outer_receipt),
            "outer_receipt_sha256": sha256(outer_raw),
            "invocation_root": str(self.invocation),
            "execution_root": str(self.execution),
            "protected_read_roots": [str(path) for path in self.protected_roots],
            "protected_write_paths": [str(path) for path in self.protected_writes],
            "temp_probe_path": str(Path(self.environment["TMPDIR"]) / "boundary-probe"),
        }
        if context_changes:
            context.update(context_changes)
        context_raw = inherited.canonical_json_bytes(context)
        self.context.write_bytes(context_raw + b"\n")
        self.context_payload = context
        self.launcher_environment = {
            **self.environment,
            inherited.BOOTSTRAP_NONCE_ENV: self.nonce,
            inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: sha256(context_raw),
        }

    def run_inherited(
        self,
        command: list[str],
        *,
        suffix: str,
        timeout: str = "3",
        environment: dict[str, str] | None = None,
        include_context_flag: bool = True,
        outer_sandbox: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object], Path, Path]:
        receipt = Path(self.environment["TMPDIR"]) / f"receipt-{suffix}.json"
        denial = Path(self.environment["TMPDIR"]) / f"denial-{suffix}.log"
        argv = [
            str(SYSTEM_PYTHON),
            str(self.copied_runner),
            "--root",
            str(self.execution),
            "--nonce",
            self.nonce,
            "--timeout",
            timeout,
            "--receipt",
            str(receipt),
            "--denial-log",
            str(denial),
        ]
        if include_context_flag:
            argv.extend(["--inherited-sandbox-context", str(self.context)])
        argv.extend(["--", *command])
        if outer_sandbox:
            argv = ["/usr/bin/sandbox-exec", "-p", self.profile_bytes.decode(), *argv]
        result = subprocess.run(
            argv,
            cwd=self.execution,
            env=environment or self.launcher_environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
        payload = (
            json.loads(receipt.read_text(encoding="utf-8"))
            if receipt.exists() and not receipt.is_symlink()
            else {}
        )
        return result, payload, receipt, denial


class LauncherInheritedNegativeC4Test(InheritedLauncherIntegrationFixture):
    def test_cli_only_env_only_and_authority_mismatches_are_no_write_blockers(self) -> None:
        cli_only, _, receipt, denial = self.run_inherited(
            ["/usr/bin/true"],
            suffix="cli-only",
            environment=self.environment,
            outer_sandbox=False,
        )
        self.assertIn("INHERITED_CLI_ONLY", cli_only.stderr)
        self.assertFalse(receipt.exists())
        self.assertFalse(denial.exists())

        env_only, _, receipt, denial = self.run_inherited(
            ["/usr/bin/true"],
            suffix="env-only",
            include_context_flag=False,
            outer_sandbox=False,
        )
        self.assertIn("INHERITED_ENVIRONMENT_ONLY", env_only.stderr)
        self.assertFalse(receipt.exists())
        self.assertFalse(denial.exists())

        cases = (
            (
                "missing-nonce-env",
                {
                    key: value
                    for key, value in self.launcher_environment.items()
                    if key != inherited.BOOTSTRAP_NONCE_ENV
                },
                "INHERITED_CLI_ONLY",
            ),
            (
                "missing-context-env",
                {
                    key: value
                    for key, value in self.launcher_environment.items()
                    if key != inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV
                },
                "INHERITED_CLI_ONLY",
            ),
            (
                "nonce",
                {**self.launcher_environment, inherited.BOOTSTRAP_NONCE_ENV: "e" * 64},
                "INVALID_BOOTSTRAP_NONCE",
            ),
            (
                "context-digest",
                {
                    **self.launcher_environment,
                    inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: "0" * 64,
                },
                "INHERITED_CONTEXT_DIGEST_MISMATCH",
            ),
        )
        for suffix, environment, blocker in cases:
            with self.subTest(suffix=suffix):
                result, _, receipt, denial = self.run_inherited(
                    ["/usr/bin/true"],
                    suffix=suffix,
                    environment=environment,
                    outer_sandbox=False,
                )
                self.assertIn(blocker, result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())

        for missing_field in ("profile_sha256", "outer_receipt_sha256"):
            with self.subTest(missing_field=missing_field):
                payload = dict(self.context_payload)
                del payload[missing_field]
                raw = inherited.canonical_json_bytes(payload)
                self.context.write_bytes(raw + b"\n")
                environment = {
                    **self.launcher_environment,
                    inherited.BOOTSTRAP_CONTEXT_DIGEST_ENV: sha256(raw),
                }
                result, _, receipt, denial = self.run_inherited(
                    ["/usr/bin/true"],
                    suffix=f"missing-{missing_field}",
                    environment=environment,
                    outer_sandbox=False,
                )
                self.assertIn("INHERITED_CONTEXT_SCHEMA_INVALID", result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())
                self.rebuild_protocol()

    def test_profile_receipt_digests_and_loopback_class_fail_before_probe_or_child(self) -> None:
        child_marker = self.execution / "child-must-not-run"
        command = ["/usr/bin/touch", str(child_marker)]
        cases = (
            ("profile-digest", {"profile_sha256": "0" * 64}, None, "INHERITED_PROFILE_MISMATCH"),
            ("receipt-digest", {"outer_receipt_sha256": "0" * 64}, None, "INHERITED_RECEIPT_MISMATCH"),
            (
                "loopback",
                {"profile_class": inherited.LOOPBACK_PROFILE_CLASS},
                {"profile_class": inherited.LOOPBACK_PROFILE_CLASS},
                "INHERITED_PROFILE_CLASS_REJECTED",
            ),
        )
        for suffix, context_changes, outer_changes, blocker in cases:
            with self.subTest(suffix=suffix):
                self.rebuild_protocol(
                    context_changes=context_changes,
                    outer_changes=outer_changes,
                )
                result, _, receipt, denial = self.run_inherited(
                    command,
                    suffix=suffix,
                    outer_sandbox=False,
                )
                self.assertIn(blocker, result.stderr)
                self.assertFalse(receipt.exists())
                self.assertFalse(denial.exists())
                self.assertFalse(child_marker.exists())
                self.assertFalse(Path(str(self.context_payload["temp_probe_path"])).exists())


class LauncherInheritedSupervisionC5Test(InheritedLauncherIntegrationFixture):
    def _matching_processes(self, token: str) -> list[int]:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", token],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return [int(row) for row in result.stdout.splitlines() if row.isdigit()]

    def _kill_matches(self, token: str) -> None:
        for pid in self._matching_processes(token):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_inherited_rlimit_nproc_denies_os_fork_without_a_survivor(self) -> None:
        token = f"samvil-inherited-fork-{os.getpid()}-{id(self)}"
        script = self.execution / "deny-inherited-fork.py"
        script.write_text(
            "import errno,os,sys,time\n"
            "try:\n"
            "    pid=os.fork()\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EAGAIN else 82)\n"
            "if pid==0:\n"
            "    os.setsid(); time.sleep(30); os._exit(0)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _, _ = self.run_inherited(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-fork"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["boundary_evidence"]["rlimit_nproc_soft"], 1)
            self.assertEqual(receipt["boundary_evidence"]["rlimit_nproc_hard"], 1)
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_inherited_rlimit_nproc_denies_ctypes_fork_without_a_survivor(self) -> None:
        token = f"samvil-inherited-ctypes-fork-{os.getpid()}-{id(self)}"
        script = self.execution / "deny-inherited-ctypes-fork.py"
        script.write_text(
            "import ctypes,errno,os,sys,time\n"
            "libc=ctypes.CDLL(None,use_errno=True)\n"
            "pid=libc.fork()\n"
            "if pid==-1:\n"
            "    raise SystemExit(0 if ctypes.get_errno()==errno.EAGAIN else 82)\n"
            "if pid==0:\n"
            "    os.setsid(); time.sleep(30); os._exit(0)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _, _ = self.run_inherited(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-ctypes-fork"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_inherited_rlimit_nproc_denies_posix_spawn_without_a_survivor(self) -> None:
        token = f"samvil-inherited-posix-spawn-{os.getpid()}-{id(self)}"
        script = self.execution / "deny-inherited-posix-spawn.py"
        script.write_text(
            "import errno,os,sys\n"
            "try:\n"
            "    os.posix_spawn(sys.executable,[sys.executable,'-c','import time;time.sleep(30)',sys.argv[1]],os.environ)\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EAGAIN else 82)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _, _ = self.run_inherited(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-posix-spawn"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_inherited_timeout_preserves_primary_and_cleans_the_process_group(self) -> None:
        token = f"samvil-inherited-timeout-{os.getpid()}-{id(self)}"
        script = self.execution / "timeout.py"
        script.write_text(
            "import time\ntime.sleep(30)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _, _ = self.run_inherited(
                [str(SYSTEM_PYTHON), str(script), token],
                suffix="timeout-survivor",
                timeout="0.2",
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertEqual(receipt["status"], "TIMEOUT")
            self.assertTrue(receipt["timed_out"])
            self.assertTrue(receipt["child_cleanup_performed"])
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_inherited_child_receives_literal_separator_and_launcher_flag_unchanged(self) -> None:
        script = self.execution / "opaque-inherited-argv.py"
        script.write_text(
            "import sys\n"
            "expected=['--','--inherited-sandbox-context','literal-context']\n"
            "raise SystemExit(0 if sys.argv[1:]==expected else 74)\n",
            encoding="utf-8",
        )
        result, receipt, _, _ = self.run_inherited(
            [
                str(SYSTEM_PYTHON),
                str(script),
                "--",
                "--inherited-sandbox-context",
                "literal-context",
            ],
            suffix="opaque-command",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")

    def test_inherited_popen_oserror_race_is_typed_path_free_blocker(self) -> None:
        receipt = Path(self.environment["TMPDIR"]) / "receipt-inherited-spawn-race.json"
        denial = Path(self.environment["TMPDIR"]) / "denial-inherited-spawn-race.log"
        evidence = inherited.BoundaryProbeEvidence(
            protected_root_count=2,
            protected_list_eperm=2,
            protected_open_eperm=2,
            protected_stat_eperm=2,
            protected_lstat_eperm=2,
            protected_access_false=2,
            protected_exists_false=2,
            protected_write_eperm=2,
            temp_roundtrip=True,
            execution_root_read=True,
            loopback_bind_eperm=True,
            loopback_connect_eperm=True,
        )
        argv = [
            "--root",
            str(self.execution),
            "--nonce",
            self.nonce,
            "--timeout",
            "3",
            "--receipt",
            str(receipt),
            "--denial-log",
            str(denial),
            "--inherited-sandbox-context",
            str(self.context),
            "--",
            "/usr/bin/true",
        ]
        stderr = io.StringIO()
        with mock.patch.dict(
            os.environ, self.launcher_environment, clear=True
        ), mock.patch.object(
            launcher.inherited, "run_boundary_probes", return_value=evidence
        ), mock.patch.object(
            launcher.subprocess,
            "Popen",
            side_effect=OSError(errno.ENOEXEC, "candidate path must not leak"),
        ), contextlib.redirect_stderr(stderr):
            try:
                result = launcher.main(argv)
            except Exception as exc:
                self.fail(f"inherited spawn error escaped: {type(exc).__name__}")

        self.assertEqual(result, 2)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(receipt.read_bytes())
        self.assertEqual(payload["status"], "CHILD_SPAWN_FAILED")
        self.assertFalse(payload["promotable"])
        self.assertNotIn(str(self.base), receipt.read_text(encoding="utf-8"))
        self.assertTrue(denial.is_file())


class LauncherSupervisionC5Test(LauncherDirectC3Test):
    def _matching_processes(self, token: str) -> list[int]:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", token],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return [int(row) for row in result.stdout.splitlines() if row.isdigit()]

    def _kill_matches(self, token: str) -> None:
        for pid in self._matching_processes(token):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_candidate_profile_denies_fork_before_setsid_child_exists(self) -> None:
        token = f"samvil-candidate-fork-{os.getpid()}-{id(self)}"
        script = self.root / "deny-fork.py"
        script.write_text(
            "import errno,os,sys,time\n"
            "try:\n"
            "    pid=os.fork()\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EPERM else 82)\n"
            "if pid==0:\n"
            "    os.setsid()\n"
            "    time.sleep(30)\n"
            "    os._exit(0)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-fork"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["profile_class"], CANDIDATE_PROFILE_CLASS)
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_candidate_profile_denies_ctypes_fork_before_child_exists(self) -> None:
        token = f"samvil-candidate-ctypes-fork-{os.getpid()}-{id(self)}"
        script = self.root / "deny-ctypes-fork.py"
        script.write_text(
            "import ctypes,errno,os,sys,time\n"
            "libc=ctypes.CDLL(None,use_errno=True)\n"
            "pid=libc.fork()\n"
            "if pid==-1:\n"
            "    raise SystemExit(0 if ctypes.get_errno()==errno.EPERM else 82)\n"
            "if pid==0:\n"
            "    os.setsid()\n"
            "    time.sleep(30)\n"
            "    os._exit(0)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-ctypes-fork"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_candidate_profile_denies_posix_spawn_before_child_exists(self) -> None:
        token = f"samvil-candidate-posix-spawn-{os.getpid()}-{id(self)}"
        script = self.root / "deny-posix-spawn.py"
        script.write_text(
            "import errno,os,sys\n"
            "try:\n"
            "    os.posix_spawn(sys.executable,[sys.executable,'-c','import time;time.sleep(30)',sys.argv[1]],os.environ)\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EPERM else 82)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), token], suffix="deny-posix-spawn"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(self._matching_processes(token), [])
        finally:
            self._kill_matches(token)

    def test_candidate_profile_denies_signal_to_external_process(self) -> None:
        target = subprocess.Popen(["/bin/sleep", "30"])
        script = self.root / "deny-signal.py"
        script.write_text(
            "import errno,os,sys\n"
            "try:\n"
            "    os.kill(int(sys.argv[1]),0)\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EPERM else 82)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), str(target.pid)],
                suffix="deny-signal",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(receipt["status"], "PASS")
            self.assertIsNone(target.poll())
        finally:
            target.terminate()
            target.wait(timeout=5)

    def test_normal_exit_has_no_surviving_descendant_processes(self) -> None:
        token = f"samvil-survivor-{self.nonce[:16]}-{os.getpid()}"
        script = self.root / "survivor.py"
        script.write_text(
            "import errno,subprocess,sys\n"
            "try:\n"
            "    subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)',sys.argv[1]])\n"
            "except OSError as exc:\n"
            "    raise SystemExit(0 if exc.errno==errno.EPERM else 82)\n"
            "raise SystemExit(81)\n",
            encoding="utf-8",
        )
        try:
            result, receipt, _ = self._run_direct(
                [str(SYSTEM_PYTHON), str(script), token], suffix="survivor"
            )
            time.sleep(0.2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(receipt["child_cleanup_performed"])
            self.assertEqual(self._matching_processes(token), [])
        finally:
            for pid in self._matching_processes(token):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_timeout_preserves_primary_status_and_kills_the_group(self) -> None:
        script = self.root / "timeout.py"
        script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        result, receipt, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="timeout", timeout="0.15"
        )
        self.assertEqual(result.returncode, 124)
        self.assertEqual(receipt["status"], "TIMEOUT")
        self.assertTrue(receipt["timed_out"])
        self.assertTrue(receipt["child_cleanup_performed"])

    def test_candidate_pass_text_never_overrides_nonzero_exit(self) -> None:
        script = self.root / "forged-pass.py"
        script.write_text("print('PASS')\nraise SystemExit(7)\n", encoding="utf-8")
        result, receipt, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="forged-pass"
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["exit_code"], 7)
        self.assertNotIn("stdout", receipt)
        self.assertEqual(receipt["stdout_bytes"], len(b"PASS\n"))

    def test_unbounded_stdout_is_a_typed_resource_blocker(self) -> None:
        script = self.root / "unbounded-stdout.py"
        script.write_text(
            "import os\n"
            "chunk=b'x'*65536\n"
            "while True:\n"
            "    os.write(1,chunk)\n",
            encoding="utf-8",
        )

        result, receipt, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)],
            suffix="unbounded-stdout",
            timeout="5",
        )

        self.assertEqual(result.returncode, 125, result.stderr + json.dumps(receipt))
        self.assertEqual(receipt["status"], "RESOURCE_LIMIT_EXCEEDED")
        self.assertEqual(receipt["resource_evidence"]["observed_status"], "exceeded")
        self.assertIn(
            receipt["resource_evidence"]["reason"],
            {"capture_bytes", "rlimit_fsize"},
        )

    def test_fast_exit_many_temp_files_are_caught_by_final_aggregate_scan(self) -> None:
        script = self.root / "many-temp-files.py"
        script.write_text(
            "import os,pathlib\n"
            "root=pathlib.Path(os.environ['TMPDIR'])\n"
            "chunk=b'x'*(1024*1024)\n"
            "for index in range(34):\n"
            "    (root/f'payload-{index}').write_bytes(chunk)\n",
            encoding="utf-8",
        )

        result, receipt, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)],
            suffix="aggregate-files",
            timeout="5",
        )

        self.assertEqual(result.returncode, 125, result.stderr + json.dumps(receipt))
        self.assertEqual(receipt["status"], "RESOURCE_LIMIT_EXCEEDED")
        self.assertEqual(
            receipt["resource_evidence"]["reason"], "invocation_total_bytes"
        )
        self.assertGreater(
            receipt["resource_evidence"]["max_invocation_bytes"],
            launcher.INVOCATION_TOTAL_BYTE_LIMIT,
        )

    def test_allocate_touch_and_exit_is_caught_by_wait4_peak_rss(self) -> None:
        script = self.root / "peak-rss.py"
        script.write_text(
            "payload=bytearray(256*1024*1024)\n"
            "for index in range(0,len(payload),4096): payload[index]=1\n",
            encoding="utf-8",
        )

        result, receipt, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="peak-rss", timeout="5"
        )

        self.assertEqual(result.returncode, 125, result.stderr + json.dumps(receipt))
        self.assertEqual(receipt["status"], "RESOURCE_LIMIT_EXCEEDED")
        self.assertEqual(receipt["resource_evidence"]["reason"], "rss_bytes")
        self.assertGreater(
            receipt["resource_evidence"]["max_rss_bytes"],
            launcher.CHILD_RSS_BYTE_LIMIT,
        )

    def test_fast_true_repeats_without_resource_monitor_flakes(self) -> None:
        for index in range(10):
            with self.subTest(index=index):
                result, receipt, _ = self._run_direct(
                    ["/usr/bin/true"], suffix=f"fast-true-{index}"
                )
                self.assertEqual(result.returncode, 0, result.stderr + json.dumps(receipt))
                self.assertEqual(receipt["status"], "PASS")
                self.assertEqual(
                    receipt["resource_evidence"]["observed_status"],
                    "within_limits",
                )

    def test_exact_retry_produces_byte_identical_path_free_receipts(self) -> None:
        script = self.root / "stable.py"
        script.write_text("print('stable')\n", encoding="utf-8")
        first_result, first, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="retry-first"
        )
        second_result, second, _ = self._run_direct(
            [str(SYSTEM_PYTHON), str(script)], suffix="retry-second"
        )
        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        self.assertEqual(
            inherited.canonical_json_bytes(first),
            inherited.canonical_json_bytes(second),
        )
        encoded = json.dumps(first, sort_keys=True)
        self.assertNotIn(str(self.base), encoded)
        self.assertNotIn(str(Path.home()), encoded)

    def test_child_has_exact_cwd_environment_and_outputs_are_single_link_files(self) -> None:
        script = self.root / "contract.py"
        expected_keys = json.dumps(list(launcher.CHILD_ENVIRONMENT_KEYS))
        script.write_text(
            """import json, os, pathlib, sys
expected = json.loads(sys.argv[1])
ok = pathlib.Path.cwd() == pathlib.Path(sys.argv[2])
ok = ok and sorted(os.environ) == expected
ok = ok and not any(k.startswith('SAMVIL_BOOTSTRAP_') for k in os.environ)
raise SystemExit(0 if ok else 81)
""",
            encoding="utf-8",
        )
        result, receipt, denial = self._run_direct(
            [str(SYSTEM_PYTHON), str(script), expected_keys, str(self.root)],
            suffix="contract",
        )
        receipt_path, _ = self._paths("contract")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        for output in (receipt_path, denial):
            metadata = os.lstat(output)
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertEqual(metadata.st_nlink, 1)


class VerifierGitTimeoutTest(unittest.TestCase):
    def spawn_exited_leader_with_pipe_descendant(
        self,
        real_popen: object,
        spawned: list[subprocess.Popen[bytes]],
        **kwargs: object,
    ) -> subprocess.Popen[bytes]:
        process = real_popen(
            [
                sys.executable,
                "-c",
                "import os,time\n"
                "if os.fork()==0:\n time.sleep(5); os._exit(0)\n"
                "os._exit(0)\n",
            ],
            stdin=subprocess.DEVNULL,
            stdout=kwargs.get("stdout", subprocess.PIPE),
            stderr=kwargs.get("stderr", subprocess.DEVNULL),
            start_new_session=True,
        )
        process.wait(timeout=2)
        spawned.append(process)
        return process

    def assert_process_groups_gone(
        self, spawned: list[subprocess.Popen[bytes]]
    ) -> None:
        for process in spawned:
            try:
                os.killpg(process.pid, 0)
            except (ProcessLookupError, PermissionError):
                continue
            self.fail("test-owned Git process group survived cleanup")

    def cleanup_process_groups(
        self, spawned: list[subprocess.Popen[bytes]]
    ) -> None:
        for process in spawned:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def test_git_bytes_kills_descendant_after_git_leader_exits(self) -> None:
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []
        try:
            with mock.patch.object(
                verifier, "GIT_TIMEOUT_SECONDS", 0.05
            ), mock.patch.object(
                verifier.subprocess,
                "run",
                side_effect=AssertionError("git_bytes must use group supervision"),
            ), mock.patch.object(
                verifier.subprocess,
                "Popen",
                side_effect=lambda *_args, **kwargs: self.spawn_exited_leader_with_pipe_descendant(
                    real_popen, spawned, **kwargs
                ),
            ), self.assertRaises(ValueError):
                verifier.git_bytes(Path("/tmp/candidate"), {}, "status")
            self.assert_process_groups_gone(spawned)
        finally:
            self.cleanup_process_groups(spawned)

    def test_bounded_candidate_git_kills_a_hung_process_group(self) -> None:
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []

        def spawn_hung(*_args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            process = real_popen(
                ["/bin/sh", "-c", "sleep 0.3"],
                stdin=subprocess.DEVNULL,
                stdout=kwargs.get("stdout", subprocess.PIPE),
                stderr=kwargs.get("stderr", subprocess.DEVNULL),
                start_new_session=True,
            )
            spawned.append(process)
            return process

        started = time.monotonic()
        try:
            with mock.patch.object(
                verifier, "GIT_TIMEOUT_SECONDS", 0.05
            ), mock.patch.object(
                verifier.subprocess, "Popen", side_effect=spawn_hung
            ), self.assertRaises(ValueError):
                verifier.candidate_git_bytes_bounded(
                    Path("/tmp/candidate"), {}, 1024, "status"
                )
            self.assertLess(time.monotonic() - started, 0.25)
        finally:
            for process in spawned:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)

    def test_bounded_candidate_git_kills_descendant_after_leader_exits(self) -> None:
        real_popen = subprocess.Popen
        spawned: list[subprocess.Popen[bytes]] = []
        try:
            with mock.patch.object(
                verifier, "GIT_TIMEOUT_SECONDS", 0.05
            ), mock.patch.object(
                verifier.subprocess,
                "Popen",
                side_effect=lambda *_args, **kwargs: self.spawn_exited_leader_with_pipe_descendant(
                    real_popen, spawned, **kwargs
                ),
            ), self.assertRaises(ValueError):
                verifier.candidate_git_bytes_bounded(
                    Path("/tmp/candidate"), {}, 1024, "status"
                )
            self.assert_process_groups_gone(spawned)
        finally:
            self.cleanup_process_groups(spawned)


class ReleaseControlTest(unittest.TestCase):
    @classmethod
    def _record_runtime_setup_issue(
        cls, kind: str, status: str, detail: str
    ) -> None:
        if cls._runtime_temp is not None:
            try:
                cls._runtime_temp.cleanup()
            except Exception as cleanup_exc:
                kind = "error"
                status = "PINNED_RUNTIME_SETUP_CLEANUP_FAILED"
                detail = (
                    f"{detail}; runtime fixture cleanup failed: "
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )
            finally:
                cls._runtime_temp = None
        cls._runtime_setup_issue = (kind, status, detail)

    @classmethod
    def setUpClass(cls) -> None:
        cls._runtime_temp: tempfile.TemporaryDirectory[str] | None = None
        cls._runtime_setup_issue: tuple[str, str, str] | None = None
        try:
            execution_context = require_copied_runtime_execution()
            runtime_source = execution_context.pinned_runtime_source
            temp_parent = execution_context.invocation_tmpdir
            cls._runtime_temp = tempfile.TemporaryDirectory(
                prefix="samvil-pinned-runtime-", dir=temp_parent
            )
            runtime = Path(cls._runtime_temp.name) / "runtime"
            copy_pinned_runtime(runtime, runtime_source=runtime_source)
            cls.pinned_python = (runtime / "bin/python3.12").resolve(strict=True)
            probe_copied_runtime_pytest(
                cls.pinned_python, execution_context=execution_context
            )
        except unittest.SkipTest as exc:
            cls._record_runtime_setup_issue("skip", "", str(exc))
        except ReleaseControlConfigurationError as exc:
            cls._record_runtime_setup_issue("error", exc.status, str(exc))
        except Exception as exc:
            cls._record_runtime_setup_issue(
                "error",
                "PINNED_RUNTIME_SETUP_FAILED",
                f"{type(exc).__name__}: {exc}",
            )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._runtime_temp is not None:
            cls._runtime_temp.cleanup()

    def setUp(self) -> None:
        issue = self._runtime_setup_issue
        if issue is not None:
            kind, status, detail = issue
            if kind == "skip":
                self.skipTest(detail)
            raise ReleaseControlConfigurationError(status, detail)
        raw_temp_parent = os.environ.get("TMPDIR")
        if not raw_temp_parent:
            self.fail("trusted bootstrap must provide an invocation-owned TMPDIR")
        try:
            temp_parent = Path(raw_temp_parent).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            self.fail(f"trusted bootstrap TMPDIR is invalid: {exc}")
        if not temp_parent.is_dir():
            self.fail("trusted bootstrap TMPDIR is not a directory")
        self._temp = tempfile.TemporaryDirectory(
            prefix="samvil-release-control-test-", dir=temp_parent
        )
        self.base = Path(self._temp.name).resolve()
        if not self.base.is_relative_to(temp_parent):
            self._temp.cleanup()
            self.fail("test temporary root escaped the invocation-owned TMPDIR")
        self.safe_env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(self.base / "test-home"),
            "TMPDIR": str(self.base / "test-tmp"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
        Path(self.safe_env["HOME"]).mkdir()
        Path(self.safe_env["TMPDIR"]).mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def command(
        self,
        argv: list[str],
        *,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            cwd=self.base,
            env=env or self.safe_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def git(self, repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/usr/bin/git", "-C", str(repo), *args],
            env=self.safe_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def init_repo(self, repo: Path) -> None:
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.name", "Release Control Test")
        self.git(repo, "config", "user.email", "release-control@example.invalid")

    def commit_all(self, repo: Path, message: str) -> str:
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", message)
        return self.git(repo, "rev-parse", "HEAD").stdout.strip()

    def make_control_repo(self) -> tuple[Path, str]:
        control = self.base / "control"
        self.init_repo(control)
        target = control / "tools" / "release-control"
        target.mkdir(parents=True)
        shutil.copyfile(TOOLS_ROOT / "inherited_context.py", target / "inherited_context.py")
        shutil.copyfile(RUNNER, target / RUNNER.name)
        shutil.copyfile(VERIFIER, target / VERIFIER.name)
        return control, self.commit_all(control, "pin trusted control")

    def make_candidate_repo(
        self,
        *,
        gate_exit: int = 0,
        symlink: bool = False,
        executable_gate: bool = False,
        remote: bool = False,
        tests_source: str = "assert True\n",
        verifier_source: str = "print('FORGED VERIFIER PASS')\n",
    ) -> Path:
        candidate = self.base / "candidate"
        self.init_repo(candidate)
        policy = candidate / "release" / "quarantine" / "v4322-policy.json"
        passive_manifest = (
            candidate
            / "release"
            / "quarantine"
            / "v4322-passive-surface-manifest.json"
        )
        validator = candidate / "scripts" / "quarantine-fuse.py"
        gate = candidate / "scripts" / "pre-commit-check.sh"
        focused_test = candidate / "mcp" / "tests" / "test_quarantine_fuse.py"
        plugin_manifest = candidate / ".claude-plugin" / "plugin.json"
        marketplace_manifest = candidate / ".claude-plugin" / "marketplace.json"
        mcp_manifest = candidate / ".mcp.json"
        policy.parent.mkdir(parents=True)
        validator.parent.mkdir(parents=True)
        focused_test.parent.mkdir(parents=True)
        plugin_manifest.parent.mkdir(parents=True)
        policy.write_text('{"passive":true}\n', encoding="utf-8")
        passive_manifest.write_text('{"surfaces":[]}\n', encoding="utf-8")
        plugin_manifest.write_text('{"version":"4.32.2"}\n', encoding="utf-8")
        marketplace_manifest.write_text('{"plugins":[]}\n', encoding="utf-8")
        mcp_manifest.write_text('{"mcpServers":{}}\n', encoding="utf-8")
        validator.write_text(
            "import sys\n"
            "expected=['verify','--policy','release/quarantine/v4322-policy.json']\n"
            f"raise SystemExit({gate_exit} if sys.argv[1:]==expected else 74)\n",
            encoding="utf-8",
        )
        gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        validator.chmod(0o755)
        gate.chmod(0o755)
        focused_test.write_text(
            "def test_quarantine_fuse():\n" + textwrap.indent(tests_source, "    "),
            encoding="utf-8",
        )
        if executable_gate:
            focused_test.chmod(0o755)
        replacement = candidate / "tools" / "release-control"
        replacement.mkdir(parents=True)
        (replacement / VERIFIER.name).write_text(
            verifier_source, encoding="utf-8"
        )
        if symlink:
            os.symlink("release/quarantine/v4322-policy.json", candidate / "unsafe-link")
        self.commit_all(candidate, "candidate")
        if remote:
            self.git(candidate, "remote", "add", "origin", "https://example.invalid/repo.git")
        return candidate

    def inventory(self, candidate: Path) -> list[dict[str, str]]:
        raw = subprocess.run(
            ["/usr/bin/git", "-C", str(candidate), "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
            env=self.safe_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
        entries = []
        for row in raw.split(b"\0"):
            if not row:
                continue
            meta, path = row.split(b"\t", 1)
            mode, kind, blob = meta.decode("ascii").split()
            entries.append(
                {"path": path.decode("utf-8"), "mode": mode, "type": kind, "blob": blob}
            )
        return entries

    def make_authorization(
        self,
        candidate: Path,
        control_commit: str,
        *,
        nonce: str = "a" * 64,
        include_tests: bool = True,
        trusted_python: Path | None = None,
    ) -> tuple[Path, dict[str, object]]:
        pinned_python = (trusted_python or self.pinned_python).resolve(strict=True)
        commit = self.git(candidate, "rev-parse", "HEAD^{commit}").stdout.strip()
        tree = self.git(candidate, "rev-parse", "HEAD^{tree}").stdout.strip()
        inventory = self.inventory(candidate)
        blobs = {entry["path"]: entry["blob"] for entry in inventory}
        commands = [
            {
                "id": "quarantine-gate",
                "argv": [
                    str(pinned_python),
                    "-I",
                    "scripts/quarantine-fuse.py",
                    "verify",
                    "--policy",
                    "release/quarantine/v4322-policy.json",
                ],
            },
        ]
        if include_tests:
            commands.insert(
                0,
                {
                    "id": "quarantine-tests",
                    "argv": [
                        str(pinned_python),
                        "-I",
                        "-m",
                        "pytest",
                        "-p",
                        "no:cacheprovider",
                        "--noconftest",
                        "-c",
                        verifier.TRUSTED_PYTEST_CONFIG_SENTINEL,
                        "--rootdir=.",
                        "--import-mode=importlib",
                        "mcp/tests/test_quarantine_fuse.py",
                        "-q",
                    ],
                },
            )
        authorization: dict[str, object] = {
            "schema_version": 1,
            "nonce": nonce,
            "expected_control_commit": control_commit,
            "trusted_python": {
                "path": str(pinned_python),
                "sha256": sha256(pinned_python.read_bytes()),
            },
            "candidate": {
                "commit": commit,
                "tree": tree,
                "inventory": inventory,
                "allowed_executable_paths": [
                    "scripts/pre-commit-check.sh",
                    "scripts/quarantine-fuse.py",
                ],
                "digests": {
                    name: {
                        "path": path,
                        "blob": blobs[path],
                        "sha256": sha256(
                            self.git(candidate, "cat-file", "blob", blobs[path]).stdout.encode()
                        ),
                    }
                    for name, path in {
                        "policy": "release/quarantine/v4322-policy.json",
                        "plugin_manifest": ".claude-plugin/plugin.json",
                        "marketplace_manifest": ".claude-plugin/marketplace.json",
                        "mcp_manifest": ".mcp.json",
                        "passive_surface_manifest": "release/quarantine/v4322-passive-surface-manifest.json",
                        "gate": "scripts/pre-commit-check.sh",
                        "validator": "scripts/quarantine-fuse.py",
                        "focused_test": "mcp/tests/test_quarantine_fuse.py",
                    }.items()
                },
            },
            "required_commands": commands,
        }
        path = self.base / "authorization.json"
        path.write_text(
            json.dumps(authorization, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return path, authorization

    def sign_authorization(self, authorization: Path) -> tuple[Path, Path]:
        private = self.base / "private.pem"
        public = self.base / "public.pem"
        signature = self.base / "authorization.sig"
        self.command(
            [
                str(OPENSSL),
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(private),
            ],
            check=True,
        )
        self.command(
            [str(OPENSSL), "pkey", "-in", str(private), "-pubout", "-out", str(public)],
            check=True,
        )
        self.command(
            [
                str(OPENSSL),
                "dgst",
                "-sha256",
                "-sign",
                str(private),
                "-out",
                str(signature),
                str(authorization),
            ],
            check=True,
        )
        return public, signature

    def run_verifier(
        self,
        candidate: Path,
        authorization: Path,
        control: Path,
        control_commit: str,
        *,
        policy: str = "local-only",
        public_key: Path | None = None,
        signature: Path | None = None,
        expected_public_key_sha256: str | None = None,
        nonce: str = "a" * 64,
        suffix: str = "",
        receipt_override: Path | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        receipt = receipt_override or (
            Path(self.safe_env["TMPDIR"]) / f"verifier-receipt{suffix}.json"
        )
        verifier_python = self.pinned_python
        argv = [
            str(verifier_python),
            str(VERIFIER),
            "--candidate",
            str(candidate),
            "--authorization",
            str(authorization),
            "--control-root",
            str(control),
            "--expected-control-commit",
            control_commit,
            "--signature-policy",
            policy,
            "--nonce",
            nonce,
            "--receipt",
            str(receipt),
        ]
        if public_key is not None:
            argv.extend(
                [
                    "--public-key",
                    str(public_key),
                    "--expected-public-key-sha256",
                    expected_public_key_sha256 or sha256(public_key.read_bytes()),
                ]
            )
        if signature is not None:
            argv.extend(["--signature", str(signature)])
        result = self.command(argv)
        payload = (
            json.loads(receipt.read_text(encoding="utf-8"))
            if receipt.exists() and not receipt.is_symlink()
            else {}
        )
        return result, payload

    def test_preexisting_symlink_receipt_is_not_followed_or_overwritten(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        target = Path(self.safe_env["TMPDIR"]) / "receipt-target"
        target.write_text("owner-data\n", encoding="utf-8")
        receipt = Path(self.safe_env["TMPDIR"]) / "receipt-link.json"
        receipt.symlink_to(target)

        result, payload = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            receipt_override=receipt,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(payload, {})
        self.assertEqual(target.read_text(encoding="utf-8"), "owner-data\n")
        self.assertIn("VERIFIER_RECEIPT_INVALID", result.stderr)

    def test_execute_checks_uses_direct_candidate_launcher_grammar(self) -> None:
        snapshot = Path(self.safe_env["TMPDIR"]) / "prebound-snapshot"
        snapshot.mkdir()
        trusted_pytest_config = verifier.create_trusted_pytest_config(snapshot)
        runner = self.base / "runner.py"
        runner.write_text("raise SystemExit(91)\n", encoding="utf-8")
        isolated = Path(self.safe_env["TMPDIR"]) / "check-0.json"
        boundary_evidence = {
            "applications_open_eperm": True,
            "dev_null_read": True,
            "rlimit_fsize_bytes": launcher.RLIMIT_FSIZE_BYTES,
            "rlimit_cpu_seconds": launcher.RLIMIT_CPU_SECONDS,
            "rlimit_nofile_count": launcher.RLIMIT_NOFILE_COUNT,
            "resource_status": "within_limits",
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
        }

        def complete(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            isolated.write_text(
                json.dumps(
                    {
                        "schema": "samvil.release-control.launch-receipt.v1",
                        "status": "PASS",
                        "profile_class": CANDIDATE_PROFILE_CLASS,
                        "sandbox_exec_count": 1,
                        "sandbox_invocations": 1,
                        "timed_out": False,
                        "exit_code": 0,
                        "promotable": False,
                        "child_cleanup_performed": False,
                        "stderr_bytes": 0,
                        "boundary_evidence": boundary_evidence,
                        "resource_evidence": {
                            "limits": verifier.EXPECTED_CANDIDATE_RESOURCE_LIMITS,
                            "observed_status": "within_limits",
                            "reason": None,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertNotIn("--inherited-sandbox-context", argv)
            separator = argv.index("--")
            self.assertEqual(
                argv[separator + 1 :],
                [
                    str(SYSTEM_PYTHON.resolve(strict=True)),
                    "-I",
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "--noconftest",
                    "-c",
                    str(trusted_pytest_config),
                    "--rootdir=.",
                    "--import-mode=importlib",
                    "mcp/tests/test_quarantine_fuse.py",
                    "-q",
                ],
            )
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        with mock.patch.object(verifier.subprocess, "run", side_effect=complete):
            checks = verifier.execute_checks(
                runner,
                snapshot,
                [
                    {
                        "id": "quarantine-tests",
                        "argv": [
                            str(SYSTEM_PYTHON.resolve(strict=True)),
                            "-I",
                            "-m",
                            "pytest",
                            "-p",
                            "no:cacheprovider",
                            "--noconftest",
                            "-c",
                            verifier.TRUSTED_PYTEST_CONFIG_SENTINEL,
                            "--rootdir=.",
                            "--import-mode=importlib",
                            "mcp/tests/test_quarantine_fuse.py",
                            "-q",
                        ],
                    }
                ],
                "a" * 64,
                self.safe_env,
                SYSTEM_PYTHON.resolve(strict=True),
                trusted_pytest_config,
                Path(self.safe_env["TMPDIR"]) / "outer.json",
            )

        self.assertEqual(checks[0]["status"], "PASS")
        self.assertEqual(checks[0]["profile_class"], CANDIDATE_PROFILE_CLASS)
        self.assertEqual(checks[0]["sandbox_invocations"], 1)
        self.assertEqual(checks[0]["boundary_evidence"], boundary_evidence)

    def test_trusted_pytest_manifest_is_path_independent_and_candidate_config_free(self) -> None:
        self.assertEqual(
            verifier.REQUIRED_DIGEST_PATHS,
            {
                "policy": "release/quarantine/v4322-policy.json",
                "plugin_manifest": ".claude-plugin/plugin.json",
                "marketplace_manifest": ".claude-plugin/marketplace.json",
                "mcp_manifest": ".mcp.json",
                "passive_surface_manifest": "release/quarantine/v4322-passive-surface-manifest.json",
                "gate": "scripts/pre-commit-check.sh",
                "validator": "scripts/quarantine-fuse.py",
                "focused_test": "mcp/tests/test_quarantine_fuse.py",
            },
        )
        self.assertEqual(
            verifier.TRUSTED_PYTEST_CONFIG_SENTINEL,
            "__SAMVIL_TRUSTED_PYTEST_CONFIG__",
        )
        pinned = Path("/trusted/python")
        self.assertEqual(
            verifier.expected_command_argv(pinned)["quarantine-tests"],
            [
                str(pinned),
                "-I",
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--noconftest",
                "-c",
                verifier.TRUSTED_PYTEST_CONFIG_SENTINEL,
                "--rootdir=.",
                "--import-mode=importlib",
                "mcp/tests/test_quarantine_fuse.py",
                "-q",
            ],
        )

    def test_verifier_typed_rejects_legacy_inherited_candidate_mode(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        receipt = Path(self.safe_env["TMPDIR"]) / "legacy-inherited-receipt.json"
        context = self.base / "legacy-inherited-context.json"
        context.write_text("{}\n", encoding="utf-8")

        result = self.command(
            [
                str(SYSTEM_PYTHON),
                str(VERIFIER),
                "--candidate",
                str(candidate),
                "--authorization",
                str(authorization),
                "--control-root",
                str(control),
                "--expected-control-commit",
                control_commit,
                "--signature-policy",
                "local-only",
                "--nonce",
                "a" * 64,
                "--receipt",
                str(receipt),
                "--inherited-sandbox-context",
                str(context),
            ]
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "INHERITED_CANDIDATE_MODE_REJECTED\n")
        self.assertFalse(receipt.exists())

        equals_result = self.command(
            [
                str(SYSTEM_PYTHON),
                str(VERIFIER),
                "--inherited-sandbox-context=" + str(context),
            ]
        )
        self.assertNotEqual(equals_result.returncode, 0)
        self.assertEqual(
            equals_result.stderr, "INHERITED_CANDIDATE_MODE_REJECTED\n"
        )

    def test_materialize_snapshot_reuses_only_prebound_marker_root(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization_path, authorization = self.make_authorization(
            candidate, control_commit
        )
        del authorization_path
        _, _, inventory, verified_blobs = verifier.verify_candidate(
            candidate, authorization, self.safe_env, Path(self.safe_env["TMPDIR"]) / "verify.json"
        )
        snapshot = Path(self.safe_env["TMPDIR"]) / "prebound-execution"
        snapshot.mkdir()
        marker = snapshot / ".release-control-root.json"
        marker.write_text(
            json.dumps({"kind": "snapshot", "nonce": "a" * 64}), encoding="utf-8"
        )

        with mock.patch.object(
            verifier,
            "candidate_git_bytes",
            side_effect=AssertionError("materialization must not call candidate Git"),
        ):
            verifier.materialize_snapshot(
                snapshot,
                inventory,
                verified_blobs,
                "a" * 64,
                prebound=True,
            )

        self.assertTrue((snapshot / "mcp/tests/test_quarantine_fuse.py").is_file())
        self.assertTrue(marker.is_file())

    def test_materialize_snapshot_requires_exact_preverified_blob_map(self) -> None:
        candidate = self.make_candidate_repo()
        inventory = self.inventory(candidate)
        blobs = {
            entry["blob"]: self.git(
                candidate, "cat-file", "blob", entry["blob"]
            ).stdout.encode("utf-8")
            for entry in inventory
        }
        expected = set(blobs)
        missing = dict(blobs)
        missing.pop(next(iter(expected)))
        unexpected = {**blobs, "0" * 40: b"unexpected"}
        for suffix, candidate_blobs in (
            ("missing", missing),
            ("unexpected", unexpected),
        ):
            with self.subTest(suffix=suffix):
                snapshot = Path(self.safe_env["TMPDIR"]) / f"blob-map-{suffix}"
                with self.assertRaises(ValueError):
                    verifier.materialize_snapshot(
                        snapshot,
                        inventory,
                        candidate_blobs,
                        "a" * 64,
                    )

    def test_materialize_snapshot_bounds_duplicate_blob_path_expansion_before_write(self) -> None:
        content = b"shared-content\n"
        blob = verifier.git_sha1_blob_oid(content)
        inventory = [
            {"mode": "100644", "type": "blob", "blob": blob, "path": path}
            for path in ("one/file", "two/file", "three/file")
        ]
        snapshot = Path(self.safe_env["TMPDIR"]) / "expanded-blob-bound"

        with mock.patch.object(
            verifier,
            "MAX_CANDIDATE_TOTAL_BLOB_BYTES",
            len(content) * 2,
        ), self.assertRaises(ValueError):
            verifier.materialize_snapshot(
                snapshot,
                inventory,
                {blob: content},
                "a" * 64,
            )

        self.assertFalse(snapshot.exists())

    def test_materialize_snapshot_rejects_ascii_case_marker_alias_before_write(self) -> None:
        marker_bytes = json.dumps(
            {"kind": "snapshot", "nonce": "a" * 64}
        ).encode()
        candidate_bytes = b"signed candidate marker alias\n"
        blob = verifier.git_sha1_blob_oid(candidate_bytes)
        inventory = [
            {
                "mode": "100644",
                "type": "blob",
                "blob": blob,
                "path": ".RELEASE-CONTROL-ROOT.JSON",
            }
        ]
        inventory_before = json.loads(json.dumps(inventory))
        verified_blobs = {blob: candidate_bytes}
        blobs_before = dict(verified_blobs)
        snapshot = Path(self.safe_env["TMPDIR"]) / "ascii-marker-alias"
        snapshot.mkdir()
        marker = snapshot / ".release-control-root.json"
        marker.write_bytes(marker_bytes)

        with self.assertRaises(ValueError):
            verifier.materialize_snapshot(
                snapshot,
                inventory,
                verified_blobs,
                "a" * 64,
                prebound=True,
            )

        self.assertEqual(inventory, inventory_before)
        self.assertEqual(verified_blobs, blobs_before)
        self.assertEqual({path.name for path in snapshot.iterdir()}, {marker.name})
        self.assertEqual(marker.read_bytes(), marker_bytes)

    def test_materialize_snapshot_rejects_nfc_and_nfd_casefold_marker_aliases(self) -> None:
        aliases = {
            "nfc": unicodedata.normalize(
                "NFC", ".releaſe-control-root.json"
            ),
            "nfd": unicodedata.normalize(
                "NFD", ".releaſe-control-root.json"
            ),
        }
        for name, alias in aliases.items():
            with self.subTest(name=name, alias=alias):
                content = alias.encode("utf-8")
                blob = verifier.git_sha1_blob_oid(content)
                inventory = [
                    {
                        "mode": "100644",
                        "type": "blob",
                        "blob": blob,
                        "path": alias,
                    }
                ]
                snapshot = Path(self.safe_env["TMPDIR"]) / f"unicode-alias-{name}"

                with self.assertRaises(ValueError):
                    verifier.materialize_snapshot(
                        snapshot,
                        inventory,
                        {blob: content},
                        "a" * 64,
                    )

                self.assertFalse(snapshot.exists())

    def test_materialize_snapshot_alias_rejection_precedes_any_mkdir_or_write(self) -> None:
        content = b"must remain immutable\n"
        blob = verifier.git_sha1_blob_oid(content)
        inventory = [
            {
                "mode": "100644",
                "type": "blob",
                "blob": blob,
                "path": ".Release-Control-Root.Json",
            }
        ]
        snapshot = Path(self.safe_env["TMPDIR"]) / "prewrite-alias-bound"

        with mock.patch.object(
            verifier.Path,
            "mkdir",
            side_effect=AssertionError("alias rejection must precede mkdir"),
        ), mock.patch.object(
            verifier.Path,
            "write_bytes",
            side_effect=AssertionError("alias rejection must precede write"),
        ), self.assertRaises(ValueError):
            verifier.materialize_snapshot(
                snapshot,
                inventory,
                {blob: content},
                "a" * 64,
            )

        self.assertFalse(snapshot.exists())

    def test_reserved_directory_prefix_aliases_are_rejected_before_any_write(self) -> None:
        aliases = {
            "ascii_marker": ".RELEASE-CONTROL-ROOT.JSON/child",
            "ascii_config": ".SAMVIL-TRUSTED-PYTEST.INI/child",
            "nfc_marker": unicodedata.normalize(
                "NFC", ".releaſe-control-root.json/child"
            ),
            "nfd_config": unicodedata.normalize(
                "NFD", ".ſamvil-trusted-pytest.ini/child"
            ),
        }
        for name, alias in aliases.items():
            with self.subTest(name=name, alias=alias):
                content = alias.encode("utf-8")
                blob = verifier.git_sha1_blob_oid(content)
                inventory = [
                    {
                        "mode": "100644",
                        "type": "blob",
                        "blob": blob,
                        "path": alias,
                    }
                ]
                inventory_before = json.loads(json.dumps(inventory))
                verified_blobs = {blob: content}
                blobs_before = dict(verified_blobs)
                snapshot = Path(self.safe_env["TMPDIR"]) / f"prefix-alias-{name}"

                with mock.patch.object(
                    verifier.Path,
                    "mkdir",
                    side_effect=AssertionError(
                        "reserved directory alias must precede mkdir"
                    ),
                ) as mkdir, mock.patch.object(
                    verifier.Path,
                    "write_bytes",
                    side_effect=AssertionError(
                        "reserved directory alias must precede write"
                    ),
                ) as write_bytes, self.assertRaises(ValueError):
                    verifier.materialize_snapshot(
                        snapshot,
                        inventory,
                        verified_blobs,
                        "a" * 64,
                    )

                mkdir.assert_not_called()
                write_bytes.assert_not_called()
                self.assertFalse(snapshot.exists())
                self.assertEqual(inventory, inventory_before)
                self.assertEqual(verified_blobs, blobs_before)

    def test_git_replace_ref_is_rejected_before_candidate_git_execution(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        original_blob = {
            entry["path"]: entry["blob"] for entry in self.inventory(candidate)
        }["mcp/tests/test_quarantine_fuse.py"]
        replacement = self.base / "replacement-tests.py"
        replacement.write_text("raise SystemExit(77)\n", encoding="utf-8")
        replacement_blob = self.git(
            candidate, "hash-object", "-w", str(replacement)
        ).stdout.strip()
        self.git(candidate, "replace", original_blob, replacement_blob)
        self.assertEqual(
            {
                entry["path"]: entry["blob"] for entry in self.inventory(candidate)
            }["mcp/tests/test_quarantine_fuse.py"],
            original_blob,
        )
        self.assertEqual(
            self.git(candidate, "cat-file", "blob", original_blob).stdout,
            "raise SystemExit(77)\n",
        )
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_CANDIDATE_OBJECT_STORE")
        self.assertFalse(receipt["promotable"])

    def test_signed_candidate_passes_external_direct_candidate_profile(self) -> None:
        require_real_seatbelt_opt_in()
        nonce = "e" * 64
        source_python = self.pinned_python
        copied_python = source_python
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(
            candidate, control_commit, nonce=nonce, trusted_python=copied_python
        )
        public, signature = self.sign_authorization(authorization)
        direct_tmpdir = self.base / "direct-verifier-tmp"
        direct_home = self.base / "direct-verifier-home"
        direct_tmpdir.mkdir()
        direct_home.mkdir()
        environment = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
            "HOME": str(direct_home),
            "TMPDIR": str(direct_tmpdir),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        receipt = direct_tmpdir / "verifier-direct-receipt.json"
        copied_verifier = control / "tools" / "release-control" / VERIFIER.name
        argv = [
            str(copied_python),
            str(copied_verifier),
            "--candidate",
            str(candidate),
            "--authorization",
            str(authorization),
            "--control-root",
            str(control),
            "--expected-control-commit",
            control_commit,
            "--signature-policy",
            "required",
            "--public-key",
            str(public),
            "--expected-public-key-sha256",
            sha256(public.read_bytes()),
            "--signature",
            str(signature),
            "--nonce",
            nonce,
            "--receipt",
            str(receipt),
        ]
        result = subprocess.run(
            argv,
            cwd=self.base,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=90,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr
            + (receipt.read_text(encoding="utf-8") if receipt.exists() else ""),
        )
        self.assertTrue(receipt.is_file(), result.stderr)
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["promotable"])
        self.assertEqual(len(payload["checks"]), 2)
        for check in payload["checks"]:
            self.assertEqual(check["profile_class"], CANDIDATE_PROFILE_CLASS)
            self.assertEqual(check["sandbox_invocations"], 1)
            self.assertEqual(
                check["boundary_evidence"],
                verifier.EXPECTED_CANDIDATE_BOUNDARY_EVIDENCE,
            )
        self.assertNotIn(str(self.base), json.dumps(payload, sort_keys=True))

    def test_signed_candidate_passes_without_using_candidate_verifier(self) -> None:
        control, control_commit = self.make_control_repo()
        forged_marker = self.base / "candidate-verifier-executed"
        candidate = self.make_candidate_repo(
            verifier_source=(
                "from pathlib import Path\n"
                f"Path({str(forged_marker)!r}).write_text('FORGED')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["promotable"])
        self.assertNotIn("FORGED", json.dumps(receipt))
        self.assertFalse(forged_marker.exists())

    def test_candidate_local_authorization_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        local = candidate / "candidate-authorization.json"
        shutil.copyfile(authorization, local)

        result, receipt = self.run_verifier(
            candidate, local, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "CANDIDATE_LOCAL_AUTHORIZATION")

    def test_live_control_runner_replacement_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        (control / "tools" / "release-control" / RUNNER.name).write_text(
            "print('FORGED CONTROL PASS')\n", encoding="utf-8"
        )

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "CONTROL_FILE_MISMATCH")

    def test_hardlinked_external_authorization_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        hardlink = self.base / "authorization-hardlink.json"
        os.link(authorization, hardlink)

        result, receipt = self.run_verifier(
            candidate, hardlink, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_FILE_INVALID")

    def test_fifo_external_authorization_is_rejected_without_blocking(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        fifo = self.base / "authorization.fifo"
        os.mkfifo(fifo)

        started = time.monotonic()
        result, receipt = self.run_verifier(
            candidate, fifo, control, control_commit
        )

        self.assertLess(time.monotonic() - started, 2.0)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_FILE_INVALID")

    def test_oversized_authorization_is_rejected_before_json_parse(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization = self.base / "oversized-authorization.json"
        authorization.write_bytes(b"x" * (verifier.MAX_AUTHORIZATION_BYTES + 1))

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_FILE_INVALID")

    def test_duplicate_authorization_key_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        raw = authorization.read_text(encoding="utf-8")
        authorization.write_text(
            raw.replace('"nonce":', '"nonce":"b", "nonce":', 1),
            encoding="utf-8",
        )

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_SCHEMA_INVALID")

    def test_authorization_schema_version_requires_exact_json_integer_one(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        _, valid_payload = self.make_authorization(candidate, control_commit)
        invalid_values = {
            "true": True,
            "false": False,
            "string": "1",
            "float": 1.0,
        }
        for name, value in invalid_values.items():
            with self.subTest(name=name, value=value):
                payload = json.loads(json.dumps(valid_payload))
                payload["schema_version"] = value
                authorization = self.base / f"authorization-schema-{name}.json"
                authorization.write_text(json.dumps(payload), encoding="utf-8")

                result, receipt = self.run_verifier(
                    candidate,
                    authorization,
                    control,
                    control_commit,
                    suffix=f"-schema-{name}",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(receipt["status"], "AUTHORIZATION_SCHEMA_INVALID")

    def test_verifier_nonce_requires_exact_lowercase_hex64_before_authorization(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        invalid_nonces = {
            "short": "a" * 63,
            "long": "a" * 65,
            "uppercase": "A" * 64,
            "wrong": "wrong",
        }
        for name, nonce in invalid_nonces.items():
            with self.subTest(name=name):
                authorization, payload = self.make_authorization(
                    candidate, control_commit, nonce=nonce
                )
                self.assertEqual(payload["nonce"], nonce)

                result, receipt = self.run_verifier(
                    candidate,
                    authorization,
                    control,
                    control_commit,
                    suffix=f"-nonce-{name}",
                    nonce=nonce,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(receipt["status"], "INVALID_NONCE")

    def test_strict_json_rejects_float_deep_huge_integer_and_lone_surrogate(self) -> None:
        deep: object = "leaf"
        for _ in range(verifier.MAX_JSON_DEPTH + 1):
            deep = [deep]
        cases = {
            "float": b'{"value":1.25}',
            "constant": b'{"value":NaN}',
            "deep": json.dumps(deep).encode(),
            "huge_integer": (
                '{"value":' + "9" * (verifier.MAX_JSON_INTEGER_DIGITS + 1) + "}"
            ).encode(),
            "lone_surrogate": b'{"value":"\\ud800"}',
            "duplicate_launch_receipt": b'{"status":"PASS","status":"FAIL"}',
        }
        for name, raw in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                verifier.decode_strict_json(raw)

    def test_fifo_swap_after_authorization_lstat_fails_promptly_without_blocking(self) -> None:
        target = self.base / "racing-authorization.json"
        target.write_text('{"schema_version":1}\n', encoding="utf-8")
        fifo = self.base / "racing-authorization.fifo"
        os.mkfifo(fifo)
        receipt_path = Path(self.safe_env["TMPDIR"]) / "fifo-race-receipt.json"
        original_lstat = verifier.os.lstat
        swapped = False

        def racing_lstat(path: object) -> os.stat_result:
            nonlocal swapped
            metadata = original_lstat(path)
            if not swapped and Path(path) == target:
                swapped = True
                os.replace(fifo, target)
            return metadata

        started = time.monotonic()
        with mock.patch.object(verifier.os, "lstat", side_effect=racing_lstat):
            with self.assertRaises(SystemExit):
                verifier.regular_single_link_bytes(
                    target,
                    receipt_path,
                    "AUTHORIZATION_FILE_INVALID",
                    max_bytes=verifier.MAX_AUTHORIZATION_BYTES,
                )

        self.assertLess(time.monotonic() - started, 1.0)
        self.assertTrue(stat.S_ISFIFO(os.lstat(target).st_mode))
        self.assertEqual(
            json.loads(receipt_path.read_text(encoding="utf-8"))["status"],
            "AUTHORIZATION_FILE_INVALID",
        )

    def test_receipt_path_replacement_during_write_is_detected(self) -> None:
        receipt_path = Path(self.safe_env["TMPDIR"]) / "racing-receipt.json"
        displaced = Path(self.safe_env["TMPDIR"]) / "displaced-receipt.json"
        original_write = verifier.os.write
        replaced = False

        def replace_then_write(descriptor: int, data: bytes) -> int:
            nonlocal replaced
            if not replaced:
                replaced = True
                os.replace(receipt_path, displaced)
                receipt_path.write_text("forged\n", encoding="utf-8")
            return original_write(descriptor, data)

        stderr = io.StringIO()
        with mock.patch.object(
            verifier.os, "write", side_effect=replace_then_write
        ), contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            verifier.write_json(receipt_path, verifier.receipt("PASS"))

        self.assertIn("VERIFIER_RECEIPT_WRITE_FAILED", stderr.getvalue())
        self.assertEqual(receipt_path.read_text(encoding="utf-8"), "forged\n")
        self.assertEqual(
            json.loads(displaced.read_text(encoding="utf-8"))["status"], "PASS"
        )

    def test_candidate_with_remote_is_rejected_before_execution(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(remote=True)
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_CANDIDATE_GIT_CONFIG")

    def test_candidate_fsmonitor_config_is_rejected_without_execution(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        sentinel = self.base / "candidate-fsmonitor-executed"
        monitor = self.base / "malicious-fsmonitor.sh"
        monitor.write_text(
            "#!/bin/sh\n/usr/bin/touch " + str(sentinel) + "\nexit 0\n",
            encoding="utf-8",
        )
        monitor.chmod(0o755)
        self.git(candidate, "config", "core.fsmonitor", str(monitor))

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_CANDIDATE_GIT_CONFIG")
        self.assertFalse(sentinel.exists())

    def test_symlink_inside_candidate_git_closure_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        branch = self.git(candidate, "symbolic-ref", "--short", "HEAD").stdout.strip()
        reference = candidate / ".git" / "refs" / "heads" / branch
        external = self.base / "external-ref"
        external.write_bytes(reference.read_bytes())
        reference.unlink()
        reference.symlink_to(external)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_CANDIDATE_GIT_CLOSURE")

    def test_candidate_object_alternates_surface_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        alternates = candidate / ".git" / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(self.base / "external-objects") + "\n", encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_CANDIDATE_OBJECT_STORE")

    def test_linked_worktree_candidate_is_rejected_as_real_repository_target(self) -> None:
        control, control_commit = self.make_control_repo()
        primary = self.make_candidate_repo()
        candidate = self.base / "linked-candidate"
        self.git(primary, "worktree", "add", "-q", "-b", "linked", str(candidate), "HEAD")
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "REAL_REPOSITORY_TARGET_REJECTED")

    def test_unexpected_executable_bit_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(executable_gate=True)
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNEXPECTED_EXECUTABLE")

    def test_pinned_python_digest_mismatch_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, payload = self.make_authorization(candidate, control_commit)
        payload["trusted_python"]["sha256"] = "0" * 64
        authorization.write_text(json.dumps(payload), encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "PINNED_PYTHON_MISMATCH")

    def test_real_repository_path_in_expected_command_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, payload = self.make_authorization(candidate, control_commit)
        payload["required_commands"][0]["argv"].append(str(candidate))
        authorization.write_text(json.dumps(payload), encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "INVALID_EXPECTED_COMMAND")

    def test_one_byte_digest_mismatch_is_fail_closed(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, payload = self.make_authorization(candidate, control_commit)
        digest = payload["candidate"]["digests"]["policy"]["sha256"]
        payload["candidate"]["digests"]["policy"]["sha256"] = (
            ("0" if digest[0] != "0" else "1") + digest[1:]
        )
        authorization.write_text(json.dumps(payload), encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "DIGEST_MISMATCH")

    def test_missing_required_digest_role_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, payload = self.make_authorization(candidate, control_commit)
        del payload["candidate"]["digests"]["focused_test"]
        authorization.write_text(json.dumps(payload), encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_SCHEMA_INVALID")

    def test_digest_roles_cannot_be_rebound_to_each_others_paths(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, payload = self.make_authorization(candidate, control_commit)
        digests = payload["candidate"]["digests"]
        digests["policy"], digests["plugin_manifest"] = (
            digests["plugin_manifest"],
            digests["policy"],
        )
        authorization.write_text(json.dumps(payload), encoding="utf-8")

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "AUTHORIZATION_SCHEMA_INVALID")

    def test_historical_pytest_and_script_shadow_surfaces_are_unreachable(self) -> None:
        require_real_seatbelt_opt_in()
        control, control_commit = self.make_control_repo()
        marker = self.base / "autoload-shadow-executed"
        candidate = self.make_candidate_repo()
        marker_source = (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
        )
        (candidate / "conftest.py").write_text(marker_source, encoding="utf-8")
        (candidate / "pytest.py").write_text(marker_source, encoding="utf-8")
        (candidate / "pytest.ini").write_text(
            "[pytest]\naddopts=--samvil-forged-option\n", encoding="utf-8"
        )
        (candidate / "scripts" / "json.py").write_text(
            marker_source, encoding="utf-8"
        )
        validator = candidate / "scripts" / "quarantine-fuse.py"
        validator.write_text(
            "import json\n" + validator.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.commit_all(candidate, "add historical autoload shadows")
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        self.safe_env["PYTEST_ADDOPTS"] = "--samvil-environment-injection"

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr + json.dumps(receipt))
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(marker.exists())

    def test_forged_pass_output_is_untrusted(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(gate_exit=9)
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "CANDIDATE_CHECK_FAILED")
        self.assertFalse(receipt["promotable"])
        self.assertNotIn(str(self.base), json.dumps(receipt, sort_keys=True))

    def test_caught_protected_control_read_remains_contained_and_can_pass(self) -> None:
        control, control_commit = self.make_control_repo()
        protected = control / "tools" / "release-control" / VERIFIER.name
        candidate = self.make_candidate_repo(
            tests_source=(
                "from pathlib import Path\n"
                "try:\n"
                f"    Path({str(protected)!r}).read_bytes()\n"
                "except PermissionError:\n"
                "    return\n"
                "raise AssertionError('protected read unexpectedly succeeded')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["promotable"])

    def test_caught_socket_attempt_remains_contained_and_can_pass(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(
            tests_source=(
                "try:\n"
                "    import errno, socket\n"
                "    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
                "    sock.bind(('127.0.0.1',0))\n"
                "except PermissionError:\n"
                "    return\n"
                "except OSError as exc:\n"
                "    assert exc.errno==errno.EPERM\n"
                "    return\n"
                "raise AssertionError('socket bind unexpectedly succeeded')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["promotable"])

    def test_candidate_subprocess_denial_can_be_caught_without_failing_verification(self) -> None:
        control, control_commit = self.make_control_repo()
        python = str(SYSTEM_PYTHON.resolve(strict=True))
        candidate = self.make_candidate_repo(
            tests_source=(
                "try:\n"
                "    import subprocess\n"
                f"    subprocess.Popen([{python!r},'-c','import time; time.sleep(30)'])\n"
                "except PermissionError:\n"
                "    return\n"
                "raise AssertionError('subprocess unexpectedly started')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["promotable"])

    def test_candidate_stderr_is_diagnostic_not_pass_authority(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(
            tests_source=(
                "import sys\n"
                "sys.stderr.write('candidate diagnostic only\\n')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["promotable"])

    def test_candidate_check_cannot_rewrite_the_authorized_gate(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(
            gate_exit=9,
            tests_source=(
                "from pathlib import Path\n"
                "Path('scripts/quarantine-fuse.py').write_text('raise SystemExit(0)\\n')\n"
            ),
        )
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "CANDIDATE_CHECK_FAILED")

    def test_missing_expected_test_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(
            candidate, control_commit, include_tests=False
        )

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "MISSING_REQUIRED_CHECK")

    def test_symlink_or_path_escape_entry_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo(symlink=True)
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNSAFE_GIT_ENTRY")

    def test_wrong_control_commit_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, "0" * 40
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "CONTROL_COMMIT_MISMATCH")

    def test_signature_required_missing_or_invalid_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        signature.write_bytes(signature.read_bytes()[:-1] + b"x")

        missing_result, missing = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            suffix="-missing",
        )
        invalid_result, invalid = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
            suffix="-invalid",
        )

        self.assertNotEqual(missing_result.returncode, 0)
        self.assertEqual(missing["status"], "SIGNATURE_REQUIRED")
        self.assertNotEqual(invalid_result.returncode, 0)
        self.assertEqual(invalid["status"], "INVALID_SIGNATURE")

    def test_hardlinked_signature_artifact_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        hardlink = self.base / "authorization-hardlink.sig"
        os.link(signature, hardlink)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=hardlink,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "SIGNATURE_FILE_INVALID")

    def test_symlinked_public_key_and_signature_cli_inputs_are_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        public_link = self.base / "public-link.pem"
        signature_link = self.base / "signature-link.sig"
        public_link.symlink_to(public)
        signature_link.symlink_to(signature)

        public_result, public_receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public_link,
            signature=signature,
            suffix="-public-symlink",
        )
        signature_result, signature_receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature_link,
            suffix="-signature-symlink",
        )

        self.assertNotEqual(public_result.returncode, 0)
        self.assertEqual(public_receipt["status"], "PUBLIC_KEY_FILE_INVALID")
        self.assertNotEqual(signature_result.returncode, 0)
        self.assertEqual(signature_receipt["status"], "SIGNATURE_FILE_INVALID")

    def test_noncanonical_public_key_cli_spelling_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        alias_parent = self.base / "key-path-alias"
        alias_parent.mkdir()
        noncanonical_public = alias_parent / ".." / public.name

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=noncanonical_public,
            signature=signature,
            expected_public_key_sha256=sha256(public.read_bytes()),
            suffix="-noncanonical-public-key",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "PUBLIC_KEY_FILE_INVALID")

    def test_malformed_public_key_and_truncated_signature_fail_closed(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)
        malformed_public = self.base / "malformed-public.pem"
        malformed_public.write_bytes(
            b"-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"
        )
        truncated_signature = self.base / "truncated-authorization.sig"
        truncated_signature.write_bytes(signature.read_bytes()[:-1])

        malformed_result, malformed = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=malformed_public,
            signature=signature,
            suffix="-malformed-key",
        )
        truncated_result, truncated = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=truncated_signature,
            suffix="-truncated-signature",
        )

        self.assertNotEqual(malformed_result.returncode, 0)
        self.assertEqual(malformed["status"], "INVALID_SIGNATURE")
        self.assertNotEqual(truncated_result.returncode, 0)
        self.assertEqual(truncated["status"], "INVALID_SIGNATURE")

    def test_der_lengths_and_positive_integers_must_be_canonical(self) -> None:
        malformed_lengths = (
            b"\x04\x81\x01x",
            b"\x04\x82\x00\x01x",
            b"\x04\x80",
        )
        for encoded in malformed_lengths:
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                verifier._der_value(encoded, 0, 0x04)

        malformed_integers = (
            b"",
            b"\x80",
            b"\x00\x01",
            b"\x00\x00",
        )
        for encoded in malformed_integers:
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                verifier._positive_der_integer(encoded)

    def test_rsa_parameters_have_strict_modulus_and_exponent_bounds(self) -> None:
        valid_modulus = (1 << 2047) | 1
        verifier._validate_rsa_parameters(valid_modulus, 65537)
        invalid = (
            (1 << 2047, 65537),
            ((1 << 2046) | 1, 65537),
            ((1 << 8192) | 1, 65537),
            (valid_modulus, 1),
            (valid_modulus, 2),
            (valid_modulus, (1 << 32) + 1),
        )
        for modulus, exponent in invalid:
            with self.subTest(
                modulus_bits=modulus.bit_length(), exponent=exponent
            ), self.assertRaises(ValueError):
                verifier._validate_rsa_parameters(modulus, exponent)

    def test_signature_key_must_match_the_outer_pinned_identity(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)
        public, signature = self.sign_authorization(authorization)

        result, receipt = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            policy="required",
            public_key=public,
            signature=signature,
            expected_public_key_sha256="0" * 64,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "UNTRUSTED_PUBLIC_KEY")

    def test_local_only_unsigned_is_typed_non_promotable_blocker(self) -> None:
        control, control_commit = self.make_control_repo()
        execution_marker = self.base / "local-only-candidate-executed"
        candidate = self.make_candidate_repo(
            tests_source=(
                "from pathlib import Path\n"
                f"Path({str(execution_marker)!r}).write_text('executed')\n"
            )
        )
        authorization, _ = self.make_authorization(candidate, control_commit)

        result, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt["status"], "BLOCKED_RELEASE_AUTHORIZATION")
        self.assertFalse(receipt["promotable"])
        self.assertNotEqual(receipt["verdict"], "PASS")
        self.assertFalse(execution_marker.exists())

    def test_wrong_or_missing_authorization_nonce_is_rejected(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)

        wrong_result, wrong = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            nonce="wrong",
            suffix="-wrong-nonce",
        )
        payload = json.loads(authorization.read_text(encoding="utf-8"))
        del payload["nonce"]
        authorization.write_text(json.dumps(payload), encoding="utf-8")
        missing_result, missing = self.run_verifier(
            candidate,
            authorization,
            control,
            control_commit,
            suffix="-missing-nonce",
        )

        self.assertNotEqual(wrong_result.returncode, 0)
        self.assertEqual(wrong["status"], "INVALID_NONCE")
        self.assertNotEqual(missing_result.returncode, 0)
        self.assertEqual(missing["status"], "INVALID_NONCE")

    def test_verifier_receipt_is_path_free(self) -> None:
        control, control_commit = self.make_control_repo()
        candidate = self.make_candidate_repo()
        authorization, _ = self.make_authorization(candidate, control_commit)

        _, receipt = self.run_verifier(
            candidate, authorization, control, control_commit
        )

        encoded = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.base), encoded)
        self.assertNotIn(str(Path.home()), encoded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
