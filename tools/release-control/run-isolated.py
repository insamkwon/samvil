#!/usr/bin/env python3
"""Run one untrusted command through the pinned SAMVIL release boundary.

This control-plane launcher imports only its adjacent trusted modules.  It
never imports code from the execution root and never accepts candidate-owned
profile or policy bytes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from typing import Iterable, Mapping, NoReturn, Sequence
import unicodedata

import inherited_context as inherited


SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
CONTROL_PROFILE_CLASS = "release-control-network-zero"
CANDIDATE_PROFILE_CLASS = "release-candidate-network-zero"
PROFILE_CLASS = CONTROL_PROFILE_CLASS
BOOTSTRAP_PREFIX = "SAMVIL_BOOTSTRAP_"
RLIMIT_FSIZE_BYTES = 1 * 1024 * 1024
RLIMIT_CPU_SECONDS = 15
RLIMIT_NOFILE_COUNT = 32
RLIMIT_NPROC_COUNT = 1
CAPTURE_BYTE_LIMIT = 1 * 1024 * 1024
INVOCATION_TOTAL_BYTE_LIMIT = 32 * 1024 * 1024
CHILD_RSS_BYTE_LIMIT = 192 * 1024 * 1024
RESOURCE_WATCH_INTERVAL_SECONDS = 0.02
MAX_EXECUTION_MARKER_BYTES = 4096
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
REMOTE_TOKEN = re.compile(r"(?:^[^/\s]+@[^:\s]+:|^[a-z][a-z0-9+.-]*://)", re.I)
SSH_COMMANDS = frozenset({"ssh", "scp", "sftp"})
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
INVOCATION_TOKEN = b"{{INVOCATION_ROOT}}"
EXECUTION_TOKEN = b"{{EXECUTION_ROOT}}"
PYTHON_ROOT_TOKEN = b"{{PINNED_PYTHON_ROOT}}"
PROTECTED_ROOT_ONE_TOKEN = b"{{PROTECTED_ROOT_ONE}}"
PROTECTED_ROOT_TWO_TOKEN = b"{{PROTECTED_ROOT_TWO}}"
CONTROL_PROFILE_SOURCE_TEMPLATE = b"\n".join(
    (
        b"(version 1)",
        b'(import "system.sb")',
        b"(deny default)",
        b"(deny network*)",
        b"(deny system-socket)",
        b"(allow process*)",
        b"(allow signal (target children))",
        b"(deny file-read-metadata file-test-existence (require-any (literal "
        + PROTECTED_ROOT_ONE_TOKEN
        + b") (subpath "
        + PROTECTED_ROOT_ONE_TOKEN
        + b") (literal "
        + PROTECTED_ROOT_TWO_TOKEN
        + b") (subpath "
        + PROTECTED_ROOT_TWO_TOKEN
        + b")))",
        b"(allow file-read-metadata file-test-existence)",
        b'(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/Library/Apple") (subpath "/Library/Developer/CommandLineTools") (subpath "/private/var/db/dyld") (subpath '
        + PYTHON_ROOT_TOKEN
        + b") (subpath "
        + EXECUTION_TOKEN
        + b") (subpath "
        + INVOCATION_TOKEN
        + b"))",
        b"(allow file-write* (subpath " + INVOCATION_TOKEN + b"))",
    )
)
CONTROL_PROFILE_DECISIONS = (
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
CANDIDATE_PROFILE_SOURCE_TEMPLATE = b"\n".join(
    (
        b"(version 1)",
        b'(import "system.sb")',
        b"(deny default)",
        b"(deny network*)",
        b"(deny system-socket)",
        b"(deny process-fork)",
        b"(allow process-exec)",
        b"(deny file-read-metadata file-test-existence (require-any (literal "
        + PROTECTED_ROOT_ONE_TOKEN
        + b") (subpath "
        + PROTECTED_ROOT_ONE_TOKEN
        + b") (literal "
        + PROTECTED_ROOT_TWO_TOKEN
        + b") (subpath "
        + PROTECTED_ROOT_TWO_TOKEN
        + b")))",
        b"(allow file-read-metadata file-test-existence)",
        b'(allow file-read* (literal "/dev/null"))',
        b'(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/Library/Apple") (subpath "/Library/Developer/CommandLineTools") (subpath "/private/var/db/dyld") (subpath '
        + PYTHON_ROOT_TOKEN
        + b") (subpath "
        + EXECUTION_TOKEN
        + b") (subpath "
        + INVOCATION_TOKEN
        + b"))",
        b"(allow file-write* (subpath " + INVOCATION_TOKEN + b"))",
    )
)
CANDIDATE_PROFILE_DECISIONS = (
    "execution_root_read=allow",
    "invocation_root_write=allow",
    "network=deny",
    "protected_read=deny",
    "protected_write=deny",
    "process_exec=allow",
    "process_fork=deny",
    "signal=deny",
    "sysctl_read=deny",
    "mach_lookup=deny",
    "ipc_posix_shm=deny",
)
PROFILE_SOURCE_TEMPLATE = CONTROL_PROFILE_SOURCE_TEMPLATE
PROFILE_DECISIONS = CONTROL_PROFILE_DECISIONS


class LaunchError(ValueError):
    """A typed fail-closed launcher blocker."""

    def __init__(self, status: str, *, evidence: Iterable[str] = ()) -> None:
        super().__init__(status)
        self.status = status
        self.evidence = tuple(evidence)


class ReceiptWriteError(LaunchError):
    """Terminal receipt write failure with explicit fallback state."""

    def __init__(self, *, fallback_written: bool) -> None:
        super().__init__("OUTPUT_WRITE_FAILED")
        self.fallback_written = fallback_written


class OutputIdentityError(LaunchError):
    """A candidate replaced or detached one launcher-owned output path."""

    def __init__(self) -> None:
        super().__init__("OUTPUT_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class LaunchArguments:
    root: str
    nonce: str
    timeout: float
    receipt: str
    denial_log: str
    inherited_context: str | None
    command: tuple[str, ...]


@dataclass(frozen=True)
class ProfileSlot:
    name: str
    start: int
    end: int


def _slot_manifest(source_template: bytes) -> tuple[ProfileSlot, ...]:
    expected = (
        ("protected_root_one", PROTECTED_ROOT_ONE_TOKEN),
        ("protected_root_one", PROTECTED_ROOT_ONE_TOKEN),
        ("protected_root_two", PROTECTED_ROOT_TWO_TOKEN),
        ("protected_root_two", PROTECTED_ROOT_TWO_TOKEN),
        ("pinned_python_root", PYTHON_ROOT_TOKEN),
        ("execution_root", EXECUTION_TOKEN),
        ("invocation_root", INVOCATION_TOKEN),
        ("invocation_root", INVOCATION_TOKEN),
    )
    cursor = 0
    slots: list[ProfileSlot] = []
    for name, token in expected:
        start = source_template.find(token, cursor)
        if start < 0:
            raise RuntimeError("trusted release profile template is invalid")
        slots.append(ProfileSlot(name, start, start + len(token)))
        cursor = start + len(token)
    return tuple(slots)


CONTROL_PROFILE_SLOT_MANIFEST = _slot_manifest(CONTROL_PROFILE_SOURCE_TEMPLATE)
CANDIDATE_PROFILE_SLOT_MANIFEST = _slot_manifest(CANDIDATE_PROFILE_SOURCE_TEMPLATE)
PROFILE_SLOT_MANIFEST = CONTROL_PROFILE_SLOT_MANIFEST


@dataclass(frozen=True)
class RenderedPolicy:
    profile_class: str
    profile_bytes: bytes
    profile_sha256: str
    source_template_sha256: str
    normalized_policy_sha256: str
    decisions: tuple[str, ...]

    def equivalence_evidence(self) -> dict[str, object]:
        return {
            "profile_class": self.profile_class,
            "source_template_sha256": self.source_template_sha256,
            "normalized_policy_sha256": self.normalized_policy_sha256,
            "decisions": list(self.decisions),
        }


@dataclass
class OutputFiles:
    receipt_path: Path
    denial_path: Path
    receipt_fd: int
    denial_fd: int
    receipt_identity: tuple[int, int, int, int]
    denial_identity: tuple[int, int, int, int]

    def close(self) -> None:
        for name in ("receipt_fd", "denial_fd"):
            descriptor = getattr(self, name)
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                finally:
                    setattr(self, name, -1)

    def validate_receipt(self) -> None:
        _validate_output_identity(
            self.receipt_path, self.receipt_fd, self.receipt_identity
        )

    def validate_denial(self) -> None:
        _validate_output_identity(self.denial_path, self.denial_fd, self.denial_identity)

    def validate_all(self) -> None:
        self.validate_receipt()
        self.validate_denial()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise LaunchError("RECEIPT_SERIALIZATION_FAILED") from exc


def _raise(status: str) -> NoReturn:
    raise LaunchError(status)


def _profile_literal(value: str) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (TypeError, UnicodeEncodeError) as exc:
        raise LaunchError("PROFILE_TEMPLATE_INVALID") from exc


def _validate_profile_contract(
    source_template: bytes,
    slot_manifest: Sequence[ProfileSlot],
    *,
    expected_source_template: bytes,
    expected_slot_manifest: Sequence[ProfileSlot],
) -> tuple[ProfileSlot, ...]:
    manifest = tuple(slot_manifest)
    if (
        source_template != expected_source_template
        or manifest != tuple(expected_slot_manifest)
    ):
        _raise("PROFILE_TEMPLATE_INVALID")
    cursor = 0
    for slot in manifest:
        if slot.start < cursor or slot.end <= slot.start or slot.end > len(source_template):
            _raise("PROFILE_TEMPLATE_INVALID")
        expected_token = {
            "invocation_root": INVOCATION_TOKEN,
            "execution_root": EXECUTION_TOKEN,
            "pinned_python_root": PYTHON_ROOT_TOKEN,
            "protected_root_one": PROTECTED_ROOT_ONE_TOKEN,
            "protected_root_two": PROTECTED_ROOT_TWO_TOKEN,
        }.get(slot.name)
        if expected_token is None or source_template[slot.start : slot.end] != expected_token:
            _raise("PROFILE_TEMPLATE_INVALID")
        cursor = slot.end
    token_count = (
        source_template.count(INVOCATION_TOKEN)
        + source_template.count(EXECUTION_TOKEN)
        + source_template.count(PYTHON_ROOT_TOKEN)
        + source_template.count(PROTECTED_ROOT_ONE_TOKEN)
        + source_template.count(PROTECTED_ROOT_TWO_TOKEN)
    )
    if token_count != len(manifest) or b"{{" in _render_slots(
        source_template,
        manifest,
        {
            "invocation_root": b"",
            "execution_root": b"",
            "pinned_python_root": b"",
            "protected_root_one": b"",
            "protected_root_two": b"",
        },
    ):
        _raise("PROFILE_TEMPLATE_INVALID")
    return manifest


def _render_slots(
    source_template: bytes,
    slots: Sequence[ProfileSlot],
    replacements: Mapping[str, bytes],
) -> bytes:
    chunks: list[bytes] = []
    cursor = 0
    for slot in slots:
        chunks.append(source_template[cursor : slot.start])
        try:
            chunks.append(replacements[slot.name])
        except KeyError as exc:
            raise LaunchError("PROFILE_TEMPLATE_INVALID") from exc
        cursor = slot.end
    chunks.append(source_template[cursor:])
    return b"".join(chunks)


def _render_policy(
    execution_root: Path,
    invocation_root: Path,
    protected_roots: Sequence[Path],
    *,
    profile_class: str,
    decisions: tuple[str, ...],
    source_template: bytes,
    slot_manifest: Sequence[ProfileSlot],
    expected_source_template: bytes,
    expected_slot_manifest: Sequence[ProfileSlot],
) -> RenderedPolicy:
    if len(protected_roots) != 2:
        _raise("PROFILE_TEMPLATE_INVALID")
    manifest = _validate_profile_contract(
        source_template,
        slot_manifest,
        expected_source_template=expected_source_template,
        expected_slot_manifest=expected_slot_manifest,
    )
    expanded = _render_slots(
        source_template,
        manifest,
        {
            "invocation_root": _profile_literal(str(invocation_root)),
            "execution_root": _profile_literal(str(execution_root)),
            "pinned_python_root": _profile_literal(str(Path(sys.prefix).resolve())),
            "protected_root_one": _profile_literal(str(protected_roots[0])),
            "protected_root_two": _profile_literal(str(protected_roots[1])),
        },
    )
    normalized = _render_slots(
        source_template,
        manifest,
        {
            "invocation_root": _profile_literal("<INVOCATION_ROOT>"),
            "execution_root": _profile_literal("<EXECUTION_ROOT>"),
            "pinned_python_root": _profile_literal("<PINNED_PYTHON_ROOT>"),
            "protected_root_one": _profile_literal("<PROTECTED_ROOT_ONE>"),
            "protected_root_two": _profile_literal("<PROTECTED_ROOT_TWO>"),
        },
    )
    return RenderedPolicy(
        profile_class=profile_class,
        profile_bytes=expanded,
        profile_sha256=digest(expanded),
        source_template_sha256=digest(source_template),
        normalized_policy_sha256=digest(normalized),
        decisions=decisions,
    )


def render_trusted_policy(
    execution_root: Path,
    invocation_root: Path,
    protected_roots: Sequence[Path],
    *,
    source_template: bytes = CONTROL_PROFILE_SOURCE_TEMPLATE,
    slot_manifest: Sequence[ProfileSlot] = CONTROL_PROFILE_SLOT_MANIFEST,
) -> RenderedPolicy:
    return _render_policy(
        execution_root,
        invocation_root,
        protected_roots,
        profile_class=CONTROL_PROFILE_CLASS,
        decisions=CONTROL_PROFILE_DECISIONS,
        source_template=source_template,
        slot_manifest=slot_manifest,
        expected_source_template=CONTROL_PROFILE_SOURCE_TEMPLATE,
        expected_slot_manifest=CONTROL_PROFILE_SLOT_MANIFEST,
    )


def render_candidate_policy(
    execution_root: Path,
    invocation_root: Path,
    protected_roots: Sequence[Path],
    *,
    source_template: bytes = CANDIDATE_PROFILE_SOURCE_TEMPLATE,
    slot_manifest: Sequence[ProfileSlot] = CANDIDATE_PROFILE_SLOT_MANIFEST,
) -> RenderedPolicy:
    return _render_policy(
        execution_root,
        invocation_root,
        protected_roots,
        profile_class=CANDIDATE_PROFILE_CLASS,
        decisions=CANDIDATE_PROFILE_DECISIONS,
        source_template=source_template,
        slot_manifest=slot_manifest,
        expected_source_template=CANDIDATE_PROFILE_SOURCE_TEMPLATE,
        expected_slot_manifest=CANDIDATE_PROFILE_SLOT_MANIFEST,
    )


def build_direct_environment(invocation_root: Path) -> dict[str, str]:
    directories = {
        "HOME": invocation_root / "home",
        "CODEX_HOME": invocation_root / "codex-home",
        "CLAUDE_CONFIG_DIR": invocation_root / "claude-config",
        "GNUPGHOME": invocation_root / "gnupg",
        "TMPDIR": invocation_root / "tmp",
        "XDG_CACHE_HOME": invocation_root / "xdg-cache",
        "XDG_CONFIG_HOME": invocation_root / "xdg-config",
        "XDG_DATA_HOME": invocation_root / "xdg-data",
        "XDG_STATE_HOME": invocation_root / "xdg-state",
    }
    for path in directories.values():
        path.mkdir(mode=0o700)
    git_config = invocation_root / "gitconfig"
    descriptor = os.open(git_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(
            descriptor,
            b"[credential]\n\thelper =\n[core]\n\taskPass = /usr/bin/false\n"
            b"[protocol]\n\tallow = never\n",
        )
    finally:
        os.close(descriptor)
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        **{key: str(value) for key, value in directories.items()},
        "GIT_CONFIG_GLOBAL": str(git_config),
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
    if tuple(sorted(environment)) != CHILD_ENVIRONMENT_KEYS:
        _raise("ENVIRONMENT_INVALID")
    return environment


def sanitize_inherited_environment(environment: Mapping[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key in CHILD_ENVIRONMENT_KEYS:
        value = environment.get(key)
        if not isinstance(value, str) or not value:
            _raise("INHERITED_ENVIRONMENT_INVALID")
        sanitized[key] = value
    sanitized["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if any(key.startswith(BOOTSTRAP_PREFIX) for key in sanitized):
        _raise("INHERITED_ENVIRONMENT_INVALID")
    return sanitized


def _parse_positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError, OverflowError):
        _raise("INVALID_TIMEOUT")
    if not math.isfinite(timeout) or timeout <= 0:
        _raise("INVALID_TIMEOUT")
    return timeout


def parse_exact_argv(argv: Sequence[str]) -> LaunchArguments:
    """Parse the exact, ordered launcher grammar without argparse recovery."""

    values = list(argv)
    required = ("--root", "--nonce", "--timeout", "--receipt", "--denial-log")
    cursor = 0
    parsed: dict[str, str] = {}
    for flag in required:
        if cursor + 1 >= len(values) or values[cursor] != flag:
            _raise("LAUNCHER_GRAMMAR_INVALID")
        parsed[flag] = values[cursor + 1]
        cursor += 2

    inherited_context: str | None = None
    if cursor < len(values) and values[cursor] == "--inherited-sandbox-context":
        if cursor + 1 >= len(values):
            _raise("LAUNCHER_GRAMMAR_INVALID")
        inherited_context = values[cursor + 1]
        cursor += 2

    if cursor >= len(values) or values[cursor] != "--":
        _raise("LAUNCHER_GRAMMAR_INVALID")
    command = tuple(values[cursor + 1 :])
    if not command:
        _raise("INVALID_COMMAND")

    nonce = parsed["--nonce"]
    if HEX64.fullmatch(nonce) is None:
        _raise("INVALID_NONCE")
    return LaunchArguments(
        root=parsed["--root"],
        nonce=nonce,
        timeout=_parse_positive_timeout(parsed["--timeout"]),
        receipt=parsed["--receipt"],
        denial_log=parsed["--denial-log"],
        inherited_context=inherited_context,
        command=command,
    )


def _canonical_existing_directory(raw: str, status: str) -> Path:
    if not isinstance(raw, str) or not raw or not os.path.isabs(raw):
        _raise(status)
    candidate = Path(raw)
    try:
        canonical = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if str(canonical) != raw or not canonical.is_dir():
        _raise(status)
    return canonical


def _read_regular_control_bytes(path: Path, *, max_bytes: int, status: str) -> bytes:
    descriptor = -1
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > max_bytes
        ):
            raise OSError("unsafe control file")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes - observed + 1))
            if not chunk:
                break
            observed += len(chunk)
            if observed > max_bytes:
                raise OSError("control file exceeded bound")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        after_path = os.lstat(path)
    except (OSError, RuntimeError, MemoryError):
        _raise(status)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        stat.S_IFMT(item.st_mode),
        item.st_nlink,
        item.st_size,
        getattr(item, "st_mtime_ns", int(item.st_mtime * 1_000_000_000)),
        getattr(item, "st_ctime_ns", int(item.st_ctime * 1_000_000_000)),
    )
    if (
        identity(before) != identity(opened)
        or identity(opened) != identity(after_fd)
        or identity(after_fd) != identity(after_path)
    ):
        _raise(status)
    return b"".join(chunks)


def _decode_execution_marker(raw: bytes) -> dict[str, object]:
    def exact_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate marker key")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=exact_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
        MemoryError,
    ):
        _raise("INVALID_EXECUTION_ROOT")
    if (
        not isinstance(payload, dict)
        or set(payload) != {"kind", "nonce"}
        or any(
            isinstance(value, str)
            and any("\ud800" <= character <= "\udfff" for character in value)
            for value in payload.values()
        )
    ):
        _raise("INVALID_EXECUTION_ROOT")
    return payload


def validate_execution_root(raw: str, nonce: str) -> Path:
    root = _canonical_existing_directory(raw, "INVALID_EXECUTION_ROOT")
    if (root / ".git").exists():
        _raise("INVALID_EXECUTION_ROOT")
    marker = root / ".release-control-root.json"
    payload = _decode_execution_marker(
        _read_regular_control_bytes(
            marker,
            max_bytes=MAX_EXECUTION_MARKER_BYTES,
            status="INVALID_EXECUTION_ROOT",
        )
    )
    if not isinstance(payload, dict) or payload.get("kind") not in {"snapshot", "control"}:
        _raise("INVALID_EXECUTION_ROOT")
    if payload.get("nonce") != nonce:
        _raise("NONCE_MISMATCH")
    for parent in root.parents:
        if parent == Path("/"):
            break
        if (parent / ".git").exists():
            _raise("INVALID_EXECUTION_ROOT")
    return root


def validate_command(command: Sequence[str], root: Path) -> tuple[str, ...]:
    if not command or not os.path.isabs(command[0]):
        _raise("INVALID_COMMAND")
    if any(REMOTE_TOKEN.search(token) for token in command):
        _raise("REMOTE_TARGET_REJECTED")
    if any(Path(token).name.lower() in SSH_COMMANDS for token in command):
        _raise("REMOTE_TARGET_REJECTED")
    try:
        executable = Path(command[0]).resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("INVALID_COMMAND")
    try:
        metadata = executable.stat()
    except OSError:
        _raise("INVALID_COMMAND")
    if not stat.S_ISREG(metadata.st_mode) or not os.access(executable, os.X_OK):
        _raise("INVALID_COMMAND")
    return tuple(command)


def validate_direct_tmpdir(environment: Mapping[str, str], root: Path) -> Path:
    tmpdir = _canonical_existing_directory(
        environment.get("TMPDIR", ""), "DIRECT_TMPDIR_INVALID"
    )
    if tmpdir == root or tmpdir.is_relative_to(root):
        _raise("DIRECT_TMPDIR_INVALID")
    return tmpdir


def _leaf_collision_key(path: Path) -> str:
    return unicodedata.normalize("NFC", str(path)).casefold()


def _canonical_absent_leaf(raw: str, status: str) -> Path:
    if not isinstance(raw, str) or not raw or not os.path.isabs(raw):
        _raise(status)
    candidate = Path(raw)
    if candidate.name in {"", ".", ".."} or "\x00" in candidate.name:
        _raise(status)
    try:
        parent = candidate.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if str(parent) != str(candidate.parent) or not parent.is_dir():
        _raise(status)
    canonical = parent / candidate.name
    if str(canonical) != raw:
        _raise(status)
    try:
        os.lstat(canonical)
    except OSError as exc:
        if exc.errno == getattr(os, "ENOENT", 2):
            return canonical
        _raise(status)
    _raise(status)


def validate_direct_output_preflight(
    receipt_raw: str,
    denial_raw: str,
    *,
    tmpdir: Path,
    execution_root: Path,
    reserved_paths: Sequence[Path] = (),
) -> tuple[Path, Path]:
    raw_paths = (Path(receipt_raw), Path(denial_raw))
    collision_paths = (*raw_paths, *reserved_paths)
    if len({_leaf_collision_key(path) for path in collision_paths}) != len(
        collision_paths
    ):
        _raise("OUTPUT_COLLISION")
    receipt = _canonical_absent_leaf(receipt_raw, "OUTPUT_INVALID")
    denial = _canonical_absent_leaf(denial_raw, "OUTPUT_INVALID")
    for output in (receipt, denial):
        if not output.is_relative_to(tmpdir) or output == tmpdir:
            _raise("OUTPUT_INVALID")
        if output == execution_root or output.is_relative_to(execution_root):
            _raise("OUTPUT_INVALID")
    return receipt, denial


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_nlink,
    )


def _validate_output_identity(
    path: Path,
    descriptor: int,
    expected: tuple[int, int, int, int],
) -> None:
    read_descriptor = -1
    try:
        held = os.fstat(descriptor)
        named = os.lstat(path)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
            os, "O_NONBLOCK", 0
        )
        read_descriptor = os.open(path, flags)
        opened = os.fstat(read_descriptor)
    except OSError:
        raise OutputIdentityError() from None
    finally:
        if read_descriptor >= 0:
            os.close(read_descriptor)
    identities = (_identity(held), _identity(named), _identity(opened))
    if (
        any(identity != expected for identity in identities)
        or expected[2] != stat.S_IFREG
        or expected[3] != 1
    ):
        raise OutputIdentityError()


def _open_exclusive_regular(path: Path) -> tuple[int, tuple[int, int, int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise LaunchError("OUTPUT_CREATION_FAILED") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        os.close(descriptor)
        _raise("OUTPUT_CREATION_FAILED")
    return descriptor, _identity(metadata)


def create_outputs(receipt: Path, denial: Path) -> OutputFiles:
    receipt_fd, receipt_identity = _open_exclusive_regular(receipt)
    try:
        denial_fd, denial_identity = _open_exclusive_regular(denial)
    except LaunchError:
        os.close(receipt_fd)
        try:
            os.unlink(receipt)
        except OSError:
            pass
        raise
    return OutputFiles(
        receipt,
        denial,
        receipt_fd,
        denial_fd,
        receipt_identity,
        denial_identity,
    )


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        try:
            written = os.write(descriptor, data[offset:])
        except OSError as exc:
            raise LaunchError("OUTPUT_WRITE_FAILED") from exc
        if written <= 0:
            _raise("OUTPUT_WRITE_FAILED")
        offset += written


def _replace_fd_bytes(descriptor: int, data: bytes) -> None:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        _write_all(descriptor, data)
        os.ftruncate(descriptor, len(data))
        os.fsync(descriptor)
    except LaunchError:
        raise
    except OSError as exc:
        raise LaunchError("OUTPUT_WRITE_FAILED") from exc


def _clear_fd_best_effort(descriptor: int) -> None:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        os.fsync(descriptor)
    except OSError:
        pass


def write_receipt(outputs: OutputFiles, payload: dict[str, object]) -> None:
    primary_status = payload.get("status")
    if not isinstance(primary_status, str) or not primary_status:
        primary_status = "UNKNOWN"
    primary_profile_class = payload.get("profile_class")
    if primary_profile_class not in {
        CONTROL_PROFILE_CLASS,
        CANDIDATE_PROFILE_CLASS,
    }:
        primary_profile_class = CANDIDATE_PROFILE_CLASS
    primary_bytes = canonical_json_bytes(payload) + b"\n"
    try:
        outputs.validate_receipt()
        _replace_fd_bytes(outputs.receipt_fd, primary_bytes)
        outputs.validate_receipt()
        return
    except OutputIdentityError:
        raise
    except LaunchError:
        pass

    fallback_bytes = canonical_json_bytes(
        blocker_receipt(
            "OUTPUT_WRITE_FAILED",
            profile_class=primary_profile_class,
            primary_status=primary_status,
        )
    ) + b"\n"
    try:
        outputs.validate_receipt()
        _replace_fd_bytes(outputs.receipt_fd, fallback_bytes)
        outputs.validate_receipt()
    except OutputIdentityError:
        raise
    except LaunchError:
        _clear_fd_best_effort(outputs.receipt_fd)
        raise ReceiptWriteError(fallback_written=False) from None
    raise ReceiptWriteError(fallback_written=True) from None


def write_denial(outputs: OutputFiles, payload: bytes) -> None:
    outputs.validate_denial()
    _write_all(outputs.denial_fd, payload)
    try:
        os.fsync(outputs.denial_fd)
    except OSError:
        _raise("OUTPUT_WRITE_FAILED")
    outputs.validate_denial()


def blocker_receipt(
    status: str,
    *,
    profile_class: str = CANDIDATE_PROFILE_CLASS,
    primary_status: str | None = None,
    evidence: Sequence[str] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "samvil.release-control.launch-receipt.v1",
        "status": status,
        "profile_class": profile_class,
        "promotable": False,
    }
    if primary_status is not None:
        payload["primary_status"] = primary_status
    if evidence:
        payload["evidence"] = list(evidence)
    return payload


DIRECT_BOUNDARY_WRAPPER = r'''import ctypes,errno,json,os,resource,socket,sys
evidence_fd=int(sys.argv[1])
protected=json.loads(sys.argv[2])
writes=json.loads(sys.argv[3])
temp_probe=sys.argv[4]
execution_root=sys.argv[5]
command=json.loads(sys.argv[6])
expected_environment_keys=json.loads(sys.argv[7])
limits=json.loads(sys.argv[8])
resource.setrlimit(resource.RLIMIT_FSIZE,(limits["fsize_bytes"],limits["fsize_bytes"]))
resource.setrlimit(resource.RLIMIT_CPU,(limits["cpu_seconds"],limits["cpu_seconds"]))
resource.setrlimit(resource.RLIMIT_NOFILE,(limits["nofile_count"],limits["nofile_count"]))
if resource.getrlimit(resource.RLIMIT_FSIZE)!=(limits["fsize_bytes"],limits["fsize_bytes"]): raise SystemExit(89)
if resource.getrlimit(resource.RLIMIT_CPU)!=(limits["cpu_seconds"],limits["cpu_seconds"]): raise SystemExit(89)
if resource.getrlimit(resource.RLIMIT_NOFILE)!=(limits["nofile_count"],limits["nofile_count"]): raise SystemExit(89)
evidence={"protected_root_count":len(protected),"protected_list_eperm":0,"protected_open_eperm":0,"protected_stat_eperm":0,"protected_lstat_eperm":0,"protected_access_false":0,"protected_exists_false":0,"protected_write_eperm":0,"applications_open_eperm":False,"dev_null_read":False,"temp_roundtrip":False,"execution_root_read":False,"loopback_bind_eperm":False,"loopback_connect_eperm":False,"fork_eperm":False,"ctypes_fork_eperm":False,"posix_spawn_eperm":False,"parent_signal_eperm":False,"setsid_eperm":False,"rlimit_fsize_bytes":limits["fsize_bytes"],"rlimit_cpu_seconds":limits["cpu_seconds"],"rlimit_nofile_count":limits["nofile_count"],"resource_status":"within_limits"}
def emit(payload):
    data=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    offset=0
    while offset<len(data):
        try: written=os.write(evidence_fd,data[offset:])
        except InterruptedError: continue
        except OSError: raise SystemExit(90)
        if written<=0: raise SystemExit(90)
        offset+=written
def fail(operation,outcome):
    payload={"status":"SANDBOX_PROBE_FAILED","operation":operation,"outcome":outcome}
    emit(payload)
    os.close(evidence_fd)
    raise SystemExit(90)
def expect_eperm(operation,call):
    try: value=call()
    except OSError as exc:
        if exc.errno==errno.EPERM: return
        fail(operation,"errno="+str(exc.errno))
    if isinstance(value,int): os.close(value)
    fail(operation,"success")
for root in protected:
    expect_eperm("protected_list",lambda root=root: os.listdir(root)); evidence["protected_list_eperm"]+=1
    expect_eperm("protected_open",lambda root=root: os.open(root,os.O_RDONLY|os.O_DIRECTORY)); evidence["protected_open_eperm"]+=1
    expect_eperm("protected_stat",lambda root=root: os.stat(root)); evidence["protected_stat_eperm"]+=1
    expect_eperm("protected_lstat",lambda root=root: os.lstat(root)); evidence["protected_lstat_eperm"]+=1
    if os.access(root,os.F_OK): fail("protected_access","true")
    evidence["protected_access_false"]+=1
    if os.path.exists(root): fail("protected_exists","true")
    evidence["protected_exists_false"]+=1
for path in writes:
    expect_eperm("protected_write",lambda path=path: os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)); evidence["protected_write_eperm"]+=1
expect_eperm("applications_open",lambda: os.open("/Applications",os.O_RDONLY|os.O_DIRECTORY)); evidence["applications_open_eperm"]=True
fd=os.open("/dev/null",os.O_RDONLY); os.close(fd); evidence["dev_null_read"]=True
marker=b"samvil-direct-boundary-v1"
fd=os.open(temp_probe,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
os.write(fd,marker); os.close(fd)
fd=os.open(temp_probe,os.O_RDONLY); observed=os.read(fd,len(marker)+1); os.close(fd); os.unlink(temp_probe)
if observed!=marker: fail("temp_roundtrip","content_mismatch")
evidence["temp_roundtrip"]=True
fd=os.open(execution_root,os.O_RDONLY|os.O_DIRECTORY); os.listdir(fd); os.close(fd); evidence["execution_root_read"]=True
for operation in ("loopback_bind","loopback_connect"):
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM); sock.settimeout(1.0)
    try:
        if operation=="loopback_bind": sock.bind(("127.0.0.1",0))
        else: sock.connect(("127.0.0.1",9))
    except OSError as exc:
        if exc.errno!=errno.EPERM: sock.close(); fail(operation,"errno="+str(exc.errno))
    else: sock.close(); fail(operation,"success")
    sock.close(); evidence[operation+"_eperm"]=True
try: pid=os.fork()
except OSError as exc:
    if exc.errno!=errno.EPERM: fail("fork","errno="+str(exc.errno))
    evidence["fork_eperm"]=True
else:
    if pid==0: os._exit(97)
    os.waitpid(pid,0); fail("fork","success")
libc=ctypes.CDLL(None,use_errno=True)
pid=libc.fork()
if pid==-1:
    observed_errno=ctypes.get_errno()
    if observed_errno!=errno.EPERM: fail("ctypes_fork","errno="+str(observed_errno))
    evidence["ctypes_fork_eperm"]=True
else:
    if pid==0: os._exit(97)
    os.waitpid(pid,0); fail("ctypes_fork","success")
try: pid=os.posix_spawn("/usr/bin/true",["true"],os.environ)
except OSError as exc:
    if exc.errno!=errno.EPERM: fail("posix_spawn","errno="+str(exc.errno))
    evidence["posix_spawn_eperm"]=True
else:
    os.waitpid(pid,0); fail("posix_spawn","success")
expect_eperm("parent_signal",lambda: os.kill(os.getppid(),0)); evidence["parent_signal_eperm"]=True
expect_eperm("setsid",os.setsid); evidence["setsid_eperm"]=True
payload={"status":"PASS","evidence":evidence}
emit(payload)
os.close(evidence_fd)
child_environment={key:os.environ[key] for key in expected_environment_keys}
os.execve(command[0],command,child_environment)
'''


INHERITED_EXEC_WRAPPER = r'''import json,os,resource,sys
evidence_fd=int(sys.argv[1])
def emit(payload):
    data=(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode()
    offset=0
    while offset<len(data):
        try: written=os.write(evidence_fd,data[offset:])
        except InterruptedError: continue
        except OSError: raise RuntimeError("evidence")
        if written<=0: raise RuntimeError("evidence")
        offset+=written
try:
    command=json.loads(sys.argv[2])
    expected_environment_keys=json.loads(sys.argv[3])
    limits=json.loads(sys.argv[4])
    child_environment={key:os.environ[key] for key in expected_environment_keys}
    resource.setrlimit(resource.RLIMIT_NPROC,(limits["nproc_count"],limits["nproc_count"]))
    resource.setrlimit(resource.RLIMIT_FSIZE,(limits["fsize_bytes"],limits["fsize_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU,(limits["cpu_seconds"],limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_NOFILE,(limits["nofile_count"],limits["nofile_count"]))
    if resource.getrlimit(resource.RLIMIT_NPROC)!=(limits["nproc_count"],limits["nproc_count"]): raise RuntimeError("nproc")
    if resource.getrlimit(resource.RLIMIT_FSIZE)!=(limits["fsize_bytes"],limits["fsize_bytes"]): raise RuntimeError("fsize")
    if resource.getrlimit(resource.RLIMIT_CPU)!=(limits["cpu_seconds"],limits["cpu_seconds"]): raise RuntimeError("cpu")
    if resource.getrlimit(resource.RLIMIT_NOFILE)!=(limits["nofile_count"],limits["nofile_count"]): raise RuntimeError("nofile")
    emit({"status":"PASS","evidence":{"rlimit_nproc_soft":limits["nproc_count"],"rlimit_nproc_hard":limits["nproc_count"],"descendant_creation":"rlimit_configured","rlimit_fsize_bytes":limits["fsize_bytes"],"rlimit_cpu_seconds":limits["cpu_seconds"],"rlimit_nofile_count":limits["nofile_count"],"resource_status":"within_limits"}})
    os.set_inheritable(evidence_fd,False)
    os.execve(command[0],command,child_environment)
except BaseException:
    try: emit({"status":"INHERITED_EXEC_SETUP_FAILED"})
    except BaseException: pass
    try: os.close(evidence_fd)
    except OSError: pass
    raise SystemExit(91)
'''


@dataclass(frozen=True)
class ChildOutcome:
    returncode: int
    timed_out: bool
    child_cleanup_performed: bool
    stdout: bytes
    stderr: bytes
    boundary_raw: bytes
    resource_limit_reason: str | None
    resource_evidence: dict[str, object]


class _RUsageInfoV2(ctypes.Structure):
    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
        ("ri_child_user_time", ctypes.c_uint64),
        ("ri_child_system_time", ctypes.c_uint64),
        ("ri_child_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_child_interrupt_wkups", ctypes.c_uint64),
        ("ri_child_pageins", ctypes.c_uint64),
        ("ri_child_elapsed_abstime", ctypes.c_uint64),
        ("ri_diskio_bytesread", ctypes.c_uint64),
        ("ri_diskio_byteswritten", ctypes.c_uint64),
    ]


def _child_resource_usage(pid: int) -> tuple[int, int]:
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pid_rusage
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_RUsageInfoV2),
        ]
        function.restype = ctypes.c_int
        info = _RUsageInfoV2()
        if function(pid, 2, ctypes.byref(info)) != 0:
            raise OSError(ctypes.get_errno(), "proc_pid_rusage")
        return int(info.ri_resident_size), int(
            info.ri_user_time + info.ri_system_time
        )
    except (AttributeError, OSError) as exc:
        raise LaunchError("RESOURCE_MONITOR_UNAVAILABLE") from exc


def _invocation_regular_bytes(root: Path) -> int:
    total = 0
    stack = [root]
    observed_entries = 0
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    observed_entries += 1
                    if observed_entries > 100_000:
                        return INVOCATION_TOTAL_BYTE_LIMIT + 1
                    metadata = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(metadata.st_mode) and not entry.is_symlink():
                        stack.append(Path(entry.path))
                    elif stat.S_ISREG(metadata.st_mode):
                        total += metadata.st_size
                        if total > INVOCATION_TOTAL_BYTE_LIMIT:
                            return total
        except OSError:
            return INVOCATION_TOTAL_BYTE_LIMIT + 1
    return total


def _resource_manifest(*, inherited_mode: bool) -> dict[str, int]:
    manifest = {
        "fsize_bytes": RLIMIT_FSIZE_BYTES,
        "cpu_seconds": RLIMIT_CPU_SECONDS,
        "nofile_count": RLIMIT_NOFILE_COUNT,
        "capture_bytes": CAPTURE_BYTE_LIMIT,
        "invocation_total_bytes": INVOCATION_TOTAL_BYTE_LIMIT,
        "rss_bytes": CHILD_RSS_BYTE_LIMIT,
    }
    if inherited_mode:
        manifest["nproc_count"] = RLIMIT_NPROC_COUNT
    return manifest


def _wait4_child(
    process: subprocess.Popen[bytes], *, block: bool
) -> tuple[int | None, object | None]:
    if process.returncode is not None:
        return process.returncode, None
    options = 0 if block else os.WNOHANG
    try:
        pid, status, usage = os.wait4(process.pid, options)
    except ChildProcessError:
        if process.returncode is None:
            raise LaunchError("CHILD_WAIT_FAILED") from None
        return process.returncode, None
    if pid == 0:
        return None, None
    process.returncode = os.waitstatus_to_exitcode(status)
    return process.returncode, usage


def _supervise_child(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
    invocation_root: Path,
    stdout_handle: object,
    stderr_handle: object,
    evidence_fd: int,
    inherited_mode: bool,
) -> tuple[bool, bool, str | None, dict[str, object], bytes]:
    setup_deadline = time.monotonic() + 5.0
    command_deadline: float | None = None
    timed_out = False
    cleanup = False
    reason: str | None = None
    max_rss = 0
    max_cpu = 0
    max_invocation = 0
    exit_usage: object | None = None
    evidence_bytes = bytearray()
    evidence_eof = False

    def drain_evidence() -> None:
        nonlocal evidence_eof
        while not evidence_eof:
            try:
                chunk = os.read(
                    evidence_fd, min(4096, 64 * 1024 + 1 - len(evidence_bytes))
                )
            except InterruptedError:
                continue
            except BlockingIOError:
                return
            except OSError:
                raise LaunchError(
                    "SANDBOX_PROBE_FAILED", evidence=("outcome=evidence_read_error",)
                ) from None
            if not chunk:
                evidence_eof = True
                return
            evidence_bytes.extend(chunk)
            if len(evidence_bytes) > 64 * 1024:
                raise LaunchError(
                    "SANDBOX_PROBE_FAILED", evidence=("outcome=evidence_oversized",)
                )

    def drain_or_terminate() -> None:
        nonlocal command_deadline
        try:
            drain_evidence()
        except LaunchError:
            _terminate_process_group(process.pid)
            _wait4_child(process, block=True)
            raise
        if evidence_eof and command_deadline is None:
            command_deadline = time.monotonic() + timeout

    while process.returncode is None:
        drain_or_terminate()
        returncode, observed_exit_usage = _wait4_child(process, block=False)
        if returncode is not None:
            exit_usage = observed_exit_usage
            break
        now = time.monotonic()
        if not evidence_eof and now >= setup_deadline:
            cleanup = _terminate_process_group(process.pid)
            _wait4_child(process, block=True)
            raise LaunchError(
                "SANDBOX_PROBE_FAILED", evidence=("outcome=evidence_setup_timeout",)
            )
        if command_deadline is not None and now >= command_deadline:
            timed_out = True
            cleanup = _terminate_process_group(process.pid)
            _, exit_usage = _wait4_child(process, block=True)
            break
        try:
            stdout_size = os.fstat(stdout_handle.fileno()).st_size
            stderr_size = os.fstat(stderr_handle.fileno()).st_size
        except (AttributeError, OSError):
            reason = "capture_identity"
            cleanup = _terminate_process_group(process.pid)
            _, exit_usage = _wait4_child(process, block=True)
            break
        invocation_size = _invocation_regular_bytes(invocation_root)
        max_invocation = max(max_invocation, invocation_size)
        try:
            rss_size, cpu_time = _child_resource_usage(process.pid)
        except LaunchError:
            returncode, observed_exit_usage = _wait4_child(process, block=False)
            if returncode is not None:
                exit_usage = observed_exit_usage
                break
            cleanup = _terminate_process_group(process.pid)
            _wait4_child(process, block=True)
            raise
        max_rss = max(max_rss, rss_size)
        max_cpu = max(max_cpu, cpu_time)
        if stdout_size >= CAPTURE_BYTE_LIMIT or stderr_size >= CAPTURE_BYTE_LIMIT:
            reason = "capture_bytes"
        elif invocation_size > INVOCATION_TOTAL_BYTE_LIMIT:
            reason = "invocation_total_bytes"
        elif rss_size > CHILD_RSS_BYTE_LIMIT:
            reason = "rss_bytes"
        if reason is not None:
            cleanup = _terminate_process_group(process.pid)
            _, exit_usage = _wait4_child(process, block=True)
            break
        time.sleep(RESOURCE_WATCH_INTERVAL_SECONDS)
    drain_or_terminate()
    if process.returncode is None:
        _, exit_usage = _wait4_child(process, block=True)
    drain_or_terminate()
    if not evidence_eof:
        _terminate_process_group(process.pid)
        raise LaunchError(
            "SANDBOX_PROBE_FAILED", evidence=("outcome=evidence_pipe_not_closed",)
        )
    if exit_usage is not None:
        max_rss = max(max_rss, int(exit_usage.ru_maxrss))
        if reason is None and max_rss > CHILD_RSS_BYTE_LIMIT:
            reason = "rss_bytes"
    try:
        final_stdout_size = os.fstat(stdout_handle.fileno()).st_size
        final_stderr_size = os.fstat(stderr_handle.fileno()).st_size
    except (AttributeError, OSError):
        final_stdout_size = CAPTURE_BYTE_LIMIT + 1
        final_stderr_size = CAPTURE_BYTE_LIMIT + 1
    final_invocation_size = _invocation_regular_bytes(invocation_root)
    max_invocation = max(max_invocation, final_invocation_size)
    if reason is None:
        if (
            final_stdout_size >= CAPTURE_BYTE_LIMIT
            or final_stderr_size >= CAPTURE_BYTE_LIMIT
        ):
            reason = "capture_bytes"
        elif final_invocation_size > INVOCATION_TOTAL_BYTE_LIMIT:
            reason = "invocation_total_bytes"
    if reason is None and process.returncode in {
        -getattr(signal, "SIGXFSZ", 25),
        -getattr(signal, "SIGXCPU", 24),
    }:
        reason = (
            "rlimit_fsize"
            if process.returncode == -getattr(signal, "SIGXFSZ", 25)
            else "rlimit_cpu"
        )
    if not timed_out and process.returncode is not None:
        cleanup = _terminate_process_group(process.pid) or cleanup
    evidence = {
        "limits": _resource_manifest(inherited_mode=inherited_mode),
        "observed_status": "exceeded" if reason is not None else "within_limits",
        "reason": reason,
    }
    if reason is not None:
        evidence.update(
            {
                "max_rss_bytes": max_rss,
                "max_cpu_time": max_cpu,
                "max_invocation_bytes": max_invocation,
            }
        )
    return timed_out, cleanup, reason, evidence, bytes(evidence_bytes)


def _bounded_capture_read(handle: object) -> bytes:
    handle.flush()
    handle.seek(0)
    data = handle.read(CAPTURE_BYTE_LIMIT + 1)
    if len(data) > CAPTURE_BYTE_LIMIT:
        return data[:CAPTURE_BYTE_LIMIT]
    return data


def _protected_roots_and_writes(nonce: str) -> tuple[tuple[Path, Path], tuple[Path, Path]]:
    try:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
        codex = (home / ".codex").resolve(strict=True)
    except (KeyError, OSError, RuntimeError):
        _raise("PROTECTED_ROOT_INVALID")
    if not home.is_dir() or not codex.is_dir():
        _raise("PROTECTED_ROOT_INVALID")
    leaf = f".samvil-release-control-{nonce[:16]}"
    writes = (home / leaf, codex / leaf)
    for path in writes:
        try:
            os.lstat(path)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                continue
            _raise("PROTECTED_WRITE_PREFLIGHT_FAILED")
        _raise("PROTECTED_WRITE_PREFLIGHT_FAILED")
    return (home, codex), writes


def _create_direct_invocation_root(tmpdir: Path, nonce: str) -> Path:
    target = tmpdir / f"samvil-release-control-{nonce}"
    try:
        os.mkdir(target, 0o700)
        canonical = target.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LaunchError("DIRECT_INVOCATION_ROOT_INVALID") from exc
    if canonical != target or not canonical.is_relative_to(tmpdir):
        _raise("DIRECT_INVOCATION_ROOT_INVALID")
    return canonical


def _cleanup_direct_invocation_root(invocation_root: Path) -> None:
    """Remove a candidate-writable tree without following candidate symlinks."""

    def repair_and_retry(function: object, raw_path: str, _: object) -> None:
        path = Path(raw_path)
        try:
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode):
                os.unlink(path)
                return
            if stat.S_ISDIR(metadata.st_mode):
                os.chmod(path, 0o700)
                if function is os.open:
                    shutil.rmtree(path, onerror=repair_and_retry)
                else:
                    function(raw_path)  # type: ignore[operator]
                return
            os.unlink(path)
        except (OSError, TypeError):
            return

    try:
        metadata = os.lstat(invocation_root)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return
        raise LaunchError("INVOCATION_CLEANUP_FAILED") from None
    try:
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise LaunchError("INVOCATION_CLEANUP_FAILED")
        os.chmod(invocation_root, 0o700)
        shutil.rmtree(invocation_root, onerror=repair_and_retry)
    except OSError:
        raise LaunchError("INVOCATION_CLEANUP_FAILED") from None
    try:
        os.lstat(invocation_root)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return
        raise LaunchError("INVOCATION_CLEANUP_FAILED") from None
    raise LaunchError("INVOCATION_CLEANUP_FAILED")


def _direct_invocation_root_preflight(tmpdir: Path, nonce: str) -> Path:
    target = tmpdir / f"samvil-release-control-{nonce}"
    try:
        os.lstat(target)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return target
        _raise("DIRECT_INVOCATION_ROOT_INVALID")
    _raise("DIRECT_INVOCATION_ROOT_INVALID")


def _capture_file(invocation_tmpdir: Path, name: str) -> tuple[int, object]:
    path = invocation_tmpdir / name
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.unlink(path)
    return descriptor, os.fdopen(descriptor, "w+b", closefd=True)


def _terminate_process_group(pgid: int) -> bool:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return True
        time.sleep(0.01)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return True


def _run_direct_child(
    *,
    root: Path,
    invocation_root: Path,
    environment: Mapping[str, str],
    command: Sequence[str],
    timeout: float,
    policy: RenderedPolicy,
    protected_roots: Sequence[Path],
    protected_writes: Sequence[Path],
) -> ChildOutcome:
    invocation_tmpdir = Path(environment["TMPDIR"])
    temp_probe = invocation_tmpdir / "boundary-probe"
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    _, stdout_handle = _capture_file(invocation_tmpdir, "stdout.capture")
    _, stderr_handle = _capture_file(invocation_tmpdir, "stderr.capture")
    wrapper_argv = [
        str(SANDBOX_EXEC),
        "-p",
        policy.profile_bytes.decode("utf-8"),
        sys.executable,
        "-c",
        DIRECT_BOUNDARY_WRAPPER,
        str(write_fd),
        json.dumps([str(path) for path in protected_roots], separators=(",", ":")),
        json.dumps([str(path) for path in protected_writes], separators=(",", ":")),
        str(temp_probe),
        str(root),
        json.dumps(list(command), separators=(",", ":")),
        json.dumps(list(CHILD_ENVIRONMENT_KEYS), separators=(",", ":")),
        json.dumps(_resource_manifest(inherited_mode=False), separators=(",", ":")),
    ]
    try:
        process = subprocess.Popen(
            wrapper_argv,
            cwd=root,
            env=dict(environment),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
            pass_fds=(write_fd,),
        )
    except OSError:
        os.close(write_fd)
        os.close(read_fd)
        stdout_handle.close()
        stderr_handle.close()
        raise LaunchError("CHILD_SPAWN_FAILED") from None
    else:
        os.close(write_fd)
    try:
        timed_out, cleanup, resource_reason, resource_evidence, boundary_raw = _supervise_child(
            process,
            timeout=timeout,
            invocation_root=invocation_root,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            evidence_fd=read_fd,
            inherited_mode=False,
        )
    except LaunchError:
        stdout_handle.close()
        stderr_handle.close()
        os.close(read_fd)
        raise
    stdout = _bounded_capture_read(stdout_handle)
    stderr = _bounded_capture_read(stderr_handle)
    stdout_handle.close()
    stderr_handle.close()
    os.close(read_fd)
    return ChildOutcome(
        returncode=process.returncode,
        timed_out=timed_out,
        child_cleanup_performed=cleanup,
        stdout=stdout,
        stderr=stderr,
        boundary_raw=boundary_raw,
        resource_limit_reason=resource_reason,
        resource_evidence=resource_evidence,
    )


def _decode_boundary_evidence(raw: bytes) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise LaunchError(
            "SANDBOX_PROBE_FAILED",
            evidence=(f"outcome=invalid_json_bytes_{len(raw)}",),
        ) from None
    if not isinstance(payload, dict) or payload.get("status") != "PASS":
        evidence: list[str] = []
        if isinstance(payload, dict):
            operation = payload.get("operation")
            outcome = payload.get("outcome")
            if isinstance(operation, str) and "/" not in operation:
                evidence.append(f"operation={operation}")
            if isinstance(outcome, str) and "/" not in outcome:
                evidence.append(f"outcome={outcome}")
        raise LaunchError("SANDBOX_PROBE_FAILED", evidence=evidence)
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise LaunchError(
            "SANDBOX_PROBE_FAILED", evidence=("outcome=missing_evidence",)
        )
    return evidence


def _normalized_command_digest(command: Sequence[str], root: Path) -> str:
    root_text = str(root)
    root_prefix = root_text + os.sep
    encoded: list[dict[str, str]] = []
    for token in command:
        if token == root_text:
            encoded.append({"kind": "execution_root"})
            continue
        if token.startswith(root_prefix):
            relative = token[len(root_prefix) :]
            parts = Path(relative).parts
            if relative and all(part not in {"", ".", ".."} for part in parts):
                encoded.append(
                    {"kind": "execution_root_relative", "value": relative}
                )
                continue
        encoded.append({"kind": "literal", "value": token})
    return digest(canonical_json_bytes(encoded))


def _direct_receipt(
    *,
    outcome: ChildOutcome,
    policy: RenderedPolicy,
    command: Sequence[str],
    root: Path,
    denial_log: bytes,
    boundary_evidence: Mapping[str, object],
) -> dict[str, object]:
    status = (
        "RESOURCE_LIMIT_EXCEEDED"
        if outcome.resource_limit_reason is not None
        else "TIMEOUT"
        if outcome.timed_out
        else "PASS"
        if outcome.returncode == 0
        else "FAIL"
    )
    return {
        "schema": "samvil.release-control.launch-receipt.v1",
        "status": status,
        "profile_class": policy.profile_class,
        "profile_sha256": policy.profile_sha256,
        "source_template_sha256": policy.source_template_sha256,
        "normalized_policy_sha256": policy.normalized_policy_sha256,
        "environment_keys": list(CHILD_ENVIRONMENT_KEYS),
        "decisions": list(policy.decisions),
        "sandbox_exec_count": 1,
        "sandbox_invocations": 1,
        "denial_observed": True,
        "boundary_evidence": dict(boundary_evidence),
        "resource_evidence": dict(outcome.resource_evidence),
        "exit_code": outcome.returncode,
        "timed_out": outcome.timed_out,
        "child_cleanup_performed": outcome.child_cleanup_performed,
        "denial_log_sha256": digest(denial_log),
        "command_sha256": _normalized_command_digest(command, root),
        "stdout_sha256": digest(outcome.stdout),
        "stdout_bytes": len(outcome.stdout),
        "stderr_sha256": digest(outcome.stderr),
        "stderr_bytes": len(outcome.stderr),
        "promotable": False,
    }


def _run_inherited_child(
    *,
    root: Path,
    tmpdir: Path,
    invocation_root: Path,
    environment: Mapping[str, str],
    command: Sequence[str],
    timeout: float,
) -> ChildOutcome:
    _, stdout_handle = _capture_file(tmpdir, "inherited-stdout.capture")
    _, stderr_handle = _capture_file(tmpdir, "inherited-stderr.capture")
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    wrapper_argv = [
        sys.executable,
        "-I",
        "-c",
        INHERITED_EXEC_WRAPPER,
        str(write_fd),
        json.dumps(list(command), separators=(",", ":")),
        json.dumps(list(CHILD_ENVIRONMENT_KEYS), separators=(",", ":")),
        json.dumps(_resource_manifest(inherited_mode=True), separators=(",", ":")),
    ]
    try:
        process = subprocess.Popen(
            wrapper_argv,
            cwd=root,
            env=dict(environment),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
            pass_fds=(write_fd,),
        )
    except OSError:
        os.close(write_fd)
        os.close(read_fd)
        stdout_handle.close()
        stderr_handle.close()
        raise LaunchError("CHILD_SPAWN_FAILED") from None
    else:
        os.close(write_fd)
    try:
        timed_out, cleanup, resource_reason, resource_evidence, boundary_raw = _supervise_child(
            process,
            timeout=timeout,
            invocation_root=invocation_root,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            evidence_fd=read_fd,
            inherited_mode=True,
        )
    except LaunchError:
        stdout_handle.close()
        stderr_handle.close()
        os.close(read_fd)
        raise
    stdout = _bounded_capture_read(stdout_handle)
    stderr = _bounded_capture_read(stderr_handle)
    stdout_handle.close()
    stderr_handle.close()
    os.close(read_fd)
    return ChildOutcome(
        returncode=process.returncode,
        timed_out=timed_out,
        child_cleanup_performed=cleanup,
        stdout=stdout,
        stderr=stderr,
        boundary_raw=boundary_raw,
        resource_limit_reason=resource_reason,
        resource_evidence={
            **resource_evidence,
            "limits": _resource_manifest(inherited_mode=True),
        },
    )


def _decode_inherited_exec_evidence(raw: bytes) -> dict[str, object]:
    try:
        rows = [row for row in raw.splitlines() if row]
        payloads = [json.loads(row.decode("utf-8")) for row in rows]
    except (UnicodeError, json.JSONDecodeError, RecursionError, MemoryError):
        _raise("INHERITED_EXEC_SETUP_FAILED")
    if len(payloads) != 1 or not isinstance(payloads[0], dict):
        _raise("INHERITED_EXEC_SETUP_FAILED")
    payload = payloads[0]
    if payload.get("status") != "PASS" or not isinstance(
        payload.get("evidence"), dict
    ):
        _raise("INHERITED_EXEC_SETUP_FAILED")
    expected = {
        "rlimit_nproc_soft": RLIMIT_NPROC_COUNT,
        "rlimit_nproc_hard": RLIMIT_NPROC_COUNT,
        "descendant_creation": "rlimit_configured",
        "rlimit_fsize_bytes": RLIMIT_FSIZE_BYTES,
        "rlimit_cpu_seconds": RLIMIT_CPU_SECONDS,
        "rlimit_nofile_count": RLIMIT_NOFILE_COUNT,
        "resource_status": "within_limits",
    }
    if payload["evidence"] != expected:
        _raise("INHERITED_EXEC_SETUP_FAILED")
    return expected


def _inherited_receipt(
    *,
    outcome: ChildOutcome,
    validated: inherited.ValidatedInheritedContext,
    policy: RenderedPolicy,
    command: Sequence[str],
    denial_log: bytes,
    boundary_evidence: Mapping[str, object],
) -> dict[str, object]:
    status = (
        "RESOURCE_LIMIT_EXCEEDED"
        if outcome.resource_limit_reason is not None
        else "TIMEOUT"
        if outcome.timed_out
        else "PASS"
        if outcome.returncode == 0
        else "FAIL"
    )
    return {
        "schema": "samvil.release-control.launch-receipt.v1",
        "status": status,
        "profile_class": validated.profile_class,
        "profile_sha256": validated.profile_sha256,
        "source_template_sha256": policy.source_template_sha256,
        "normalized_policy_sha256": policy.normalized_policy_sha256,
        "environment_keys": list(validated.environment_keys),
        "decisions": list(policy.decisions),
        "sandbox_exec_count": 0,
        "sandbox_invocations": 0,
        "denial_observed": True,
        "boundary_evidence": dict(boundary_evidence),
        "resource_evidence": dict(outcome.resource_evidence),
        "exit_code": outcome.returncode,
        "timed_out": outcome.timed_out,
        "child_cleanup_performed": outcome.child_cleanup_performed,
        "denial_log_sha256": digest(denial_log),
        "command_sha256": _normalized_command_digest(
            command, validated.execution_root
        ),
        "stdout_sha256": digest(outcome.stdout),
        "stdout_bytes": len(outcome.stdout),
        "stderr_sha256": digest(outcome.stderr),
        "stderr_bytes": len(outcome.stderr),
        "promotable": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    outputs: OutputFiles | None = None
    invocation_root: Path | None = None
    blocker_profile_class = CANDIDATE_PROFILE_CLASS
    try:
        args = parse_exact_argv(sys.argv[1:] if argv is None else argv)
        root = validate_execution_root(args.root, args.nonce)
        command = validate_command(args.command, root)
        if args.inherited_context is not None:
            blocker_profile_class = CONTROL_PROFILE_CLASS
            inherited_environment = sanitize_inherited_environment(os.environ)
            try:
                validated = inherited.validate_inherited_request(
                    context_path=args.inherited_context,
                    cli_root=args.root,
                    cli_nonce=args.nonce,
                    environment=os.environ,
                    expected_environment_keys=CHILD_ENVIRONMENT_KEYS,
                    receipt_path=args.receipt,
                    denial_log_path=args.denial_log,
                )
            except inherited.ProtocolError as exc:
                raise LaunchError(exc.status, evidence=exc.evidence) from None
            policy = render_trusted_policy(
                validated.execution_root,
                validated.invocation_root,
                validated.protected_read_roots,
            )
            if (
                validated.profile_class != policy.profile_class
                or validated.profile_bytes != policy.profile_bytes
                or validated.environment_keys != CHILD_ENVIRONMENT_KEYS
            ):
                _raise("PROFILE_EQUIVALENCE_MISMATCH")
            outputs = create_outputs(
                validated.receipt_path, validated.denial_log_path
            )
            try:
                probe_evidence = inherited.run_boundary_probes(validated)
            except inherited.ProtocolError as exc:
                raise LaunchError(exc.status, evidence=exc.evidence) from None
            boundary_evidence = asdict(probe_evidence)
            outcome = _run_inherited_child(
                root=validated.execution_root,
                tmpdir=validated.tmpdir,
                invocation_root=validated.invocation_root,
                environment=inherited_environment,
                command=command,
                timeout=args.timeout,
            )
            boundary_evidence.update(
                _decode_inherited_exec_evidence(outcome.boundary_raw)
            )
            denial_bytes = canonical_json_bytes(boundary_evidence) + b"\n" + outcome.stderr
            write_denial(outputs, denial_bytes)
            write_receipt(
                outputs,
                _inherited_receipt(
                    outcome=outcome,
                    validated=validated,
                    policy=policy,
                    command=command,
                    denial_log=denial_bytes,
                    boundary_evidence=boundary_evidence,
                ),
            )
            outputs.validate_all()
            return (
                125
                if outcome.resource_limit_reason is not None
                else 124
                if outcome.timed_out
                else outcome.returncode
            )
        if any(key.startswith(BOOTSTRAP_PREFIX) for key in os.environ):
            _raise("INHERITED_ENVIRONMENT_ONLY")
        if not SANDBOX_EXEC.is_file():
            _raise("SANDBOX_UNAVAILABLE")
        tmpdir = validate_direct_tmpdir(os.environ, root)
        protected_roots, protected_writes = _protected_roots_and_writes(args.nonce)
        invocation_candidate = _direct_invocation_root_preflight(tmpdir, args.nonce)
        receipt, denial = validate_direct_output_preflight(
            args.receipt,
            args.denial_log,
            tmpdir=tmpdir,
            execution_root=root,
            reserved_paths=(
                invocation_candidate,
                invocation_candidate / "tmp" / "boundary-probe",
                *protected_writes,
            ),
        )
        outputs = create_outputs(receipt, denial)
        invocation_root = _create_direct_invocation_root(tmpdir, args.nonce)
        environment = build_direct_environment(invocation_root)
        policy = render_candidate_policy(root, invocation_root, protected_roots)
        outcome = _run_direct_child(
            root=root,
            invocation_root=invocation_root,
            environment=environment,
            command=command,
            timeout=args.timeout,
            policy=policy,
            protected_roots=protected_roots,
            protected_writes=protected_writes,
        )
        boundary_evidence = _decode_boundary_evidence(outcome.boundary_raw)
        denial_bytes = outcome.boundary_raw + b"\n" + outcome.stderr
        write_denial(outputs, denial_bytes)
        for protected_write in protected_writes:
            try:
                os.lstat(protected_write)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    continue
                _raise("PROTECTED_WRITE_POSTCHECK_FAILED")
            _raise("PROTECTED_WRITE_ARTIFACT")
        write_receipt(
            outputs,
            _direct_receipt(
                outcome=outcome,
                policy=policy,
                command=command,
                root=root,
                denial_log=denial_bytes,
                boundary_evidence=boundary_evidence,
            ),
        )
        outputs.validate_all()
        return (
            125
            if outcome.resource_limit_reason is not None
            else 124
            if outcome.timed_out
            else outcome.returncode
        )
    except OutputIdentityError as exc:
        print(exc.status, file=sys.stderr)
        return 2
    except ReceiptWriteError as exc:
        if not exc.fallback_written:
            print(exc.status, file=sys.stderr)
        return 2
    except LaunchError as exc:
        if outputs is not None:
            try:
                write_receipt(
                    outputs,
                    blocker_receipt(
                        exc.status,
                        profile_class=blocker_profile_class,
                        evidence=exc.evidence,
                    ),
                )
            except ReceiptWriteError as write_exc:
                if not write_exc.fallback_written:
                    print(write_exc.status, file=sys.stderr)
        else:
            print(exc.status, file=sys.stderr)
        return 2
    finally:
        cleanup_failed = False
        if invocation_root is not None:
            try:
                _cleanup_direct_invocation_root(invocation_root)
            except LaunchError:
                cleanup_failed = True
            if cleanup_failed and outputs is not None:
                try:
                    write_receipt(
                        outputs,
                        blocker_receipt(
                            "INVOCATION_CLEANUP_FAILED",
                            profile_class=CANDIDATE_PROFILE_CLASS,
                        ),
                    )
                except ReceiptWriteError as exc:
                    if not exc.fallback_written:
                        print(exc.status, file=sys.stderr)
        if outputs is not None:
            outputs.close()
        if cleanup_failed:
            print("INVOCATION_CLEANUP_FAILED", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
