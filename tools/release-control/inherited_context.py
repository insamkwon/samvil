#!/usr/bin/env python3
"""Validate the private inherited-sandbox bootstrap protocol.

This module validates trusted bootstrap evidence and performs the narrow,
context-bound inherited boundary probes. It never invokes ``sandbox-exec``,
selects a profile, executes untrusted code, or issues a final release verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
from typing import Iterable, Mapping, NoReturn, Sequence
import unicodedata


CONTEXT_SCHEMA = "samvil.bootstrap.inherited-sandbox-context.v1"
OUTER_RECEIPT_SCHEMA = "samvil.bootstrap.outer-receipt.v1"
INHERITED_PROFILE_CLASS = "release-control-network-zero"
LOOPBACK_PROFILE_CLASS = "pinned-full-gate-loopback-only"
BOOTSTRAP_PREFIX = "SAMVIL_BOOTSTRAP_"
BOOTSTRAP_NONCE_ENV = "SAMVIL_BOOTSTRAP_NONCE"
BOOTSTRAP_CONTEXT_DIGEST_ENV = "SAMVIL_BOOTSTRAP_CONTEXT_SHA256"

CONTEXT_FIELDS = frozenset(
    {
        "schema",
        "nonce",
        "profile_class",
        "profile_path",
        "profile_sha256",
        "outer_receipt_path",
        "outer_receipt_sha256",
        "invocation_root",
        "execution_root",
        "protected_read_roots",
        "protected_write_paths",
        "temp_probe_path",
    }
)
OUTER_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "nonce",
        "profile_class",
        "profile_sha256",
        "protected_roots_sha256",
        "environment_keys",
    }
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_CONTEXT_BYTES = 64 * 1024
MAX_OUTER_RECEIPT_BYTES = 32 * 1024
MAX_PROFILE_BYTES = 256 * 1024
MAX_JSON_DEPTH = 32
READ_CHUNK_BYTES = 64 * 1024


class ProtocolError(ValueError):
    """A fail-closed, typed inherited-protocol blocker."""

    def __init__(self, status: str, *, evidence: Iterable[str] = ()) -> None:
        super().__init__(status)
        self.status = status
        self.evidence = tuple(evidence)


class _InvalidJSON(ValueError):
    pass


@dataclass(frozen=True)
class FileIdentity:
    """Diagnostic evidence for the exact file descriptor that was validated."""

    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, metadata: os.stat_result) -> "FileIdentity":
        return cls(
            device=metadata.st_dev,
            inode=metadata.st_ino,
            size=metadata.st_size,
            mtime_ns=getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)),
            ctime_ns=getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)),
        )


@dataclass(frozen=True)
class ValidatedInheritedContext:
    """Immutable inherited evidence with profile bytes as the only authority.

    ``profile_path`` and ``profile_identity`` are diagnostic evidence only.
    Consumers MUST pass ``profile_bytes`` directly to ``sandbox-exec -p`` and
    MUST NOT reopen ``profile_path`` for authorization or execution.
    """

    context_path: Path
    context_sha256: str
    nonce: str
    profile_class: str
    profile_path: Path
    profile_sha256: str
    profile_bytes: bytes
    profile_identity: FileIdentity
    outer_receipt_path: Path
    outer_receipt_sha256: str
    invocation_root: Path
    execution_root: Path
    protected_read_roots: tuple[Path, Path]
    protected_write_paths: tuple[Path, Path]
    temp_probe_path: Path
    tmpdir: Path
    receipt_path: Path
    denial_log_path: Path
    environment_keys: tuple[str, ...]


@dataclass(frozen=True)
class BoundaryProbeEvidence:
    """Path-free evidence that the inherited boundary behaved as required."""

    protected_root_count: int
    protected_list_eperm: int
    protected_open_eperm: int
    protected_stat_eperm: int
    protected_lstat_eperm: int
    protected_access_false: int
    protected_exists_false: int
    protected_write_eperm: int
    temp_roundtrip: bool
    execution_root_read: bool
    loopback_bind_eperm: bool
    loopback_connect_eperm: bool


def canonical_json_bytes(value: object) -> bytes:
    """Return the protocol's compact, key-sorted UTF-8 JSON representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except ProtocolError:
        raise
    except (
        TypeError,
        ValueError,
        UnicodeEncodeError,
        RecursionError,
        MemoryError,
    ) as exc:
        raise ProtocolError("INHERITED_JSON_INVALID") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def protected_roots_sha256(roots: Sequence[Path]) -> str:
    return sha256_bytes(canonical_json_bytes([str(path) for path in roots]))


def sanitized_environment_keys(keys: Iterable[str]) -> tuple[str, ...]:
    try:
        collected = tuple(keys)
    except TypeError as exc:
        raise ProtocolError("INHERITED_ENVIRONMENT_KEYS_INVALID") from exc
    if (
        any(not isinstance(key, str) or not key for key in collected)
        or any(key.startswith(BOOTSTRAP_PREFIX) for key in collected)
        or len(set(collected)) != len(collected)
        or tuple(sorted(collected)) != collected
    ):
        raise ProtocolError("INHERITED_ENVIRONMENT_KEYS_INVALID")
    return collected


def environment_keys_sha256(keys: Iterable[str]) -> str:
    validated = sanitized_environment_keys(keys)
    return sha256_bytes(canonical_json_bytes(list(validated)))


def _raise(status: str) -> NoReturn:
    raise ProtocolError(status)


def _raise_probe(status: str, operation: str, outcome: str) -> NoReturn:
    raise _probe_blocker(status, operation, outcome)


def _probe_blocker(status: str, operation: str, outcome: str) -> ProtocolError:
    return ProtocolError(
        status,
        evidence=(f"operation={operation}", f"outcome={outcome}"),
    )


def _errno_outcome(exc: OSError) -> str:
    code = exc.errno
    return f"errno={errno.errorcode.get(code, str(code))}"


def _close_descriptor(
    descriptor: int,
    *,
    cleanup_status: str,
    operation: str,
    primary: BaseException | None = None,
) -> None:
    cleanup_outcome: str | None = None
    try:
        os.close(descriptor)
    except OSError as exc:
        cleanup_outcome = _errno_outcome(exc)
    if primary is not None:
        return
    if cleanup_outcome is not None:
        raise _probe_blocker(
            cleanup_status,
            operation,
            cleanup_outcome,
        ) from None


def _artifact_close_contract(status: str) -> tuple[str, str]:
    contracts = {
        "INHERITED_CONTEXT_INVALID": (
            "INHERITED_CONTEXT_CLOSE_FAILED",
            "context_artifact_cleanup",
        ),
        "INHERITED_PROFILE_INVALID": (
            "INHERITED_PROFILE_CLOSE_FAILED",
            "profile_artifact_cleanup",
        ),
        "INHERITED_RECEIPT_INVALID": (
            "INHERITED_RECEIPT_CLOSE_FAILED",
            "receipt_artifact_cleanup",
        ),
    }
    return contracts.get(
        status,
        ("INHERITED_ARTIFACT_CLOSE_FAILED", "control_artifact_cleanup"),
    )


def _hex64(value: object, status: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        _raise(status)
    return value


def _exact_object(
    value: object, fields: frozenset[str], status: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        _raise(status)
    if any(not isinstance(key, str) for key in value):
        _raise(status)
    return value


def _decode_object(raw: bytes, fields: frozenset[str], status: str) -> dict[str, object]:
    def exact_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _InvalidJSON("duplicate key")
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise _InvalidJSON(value)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=exact_pairs,
            parse_constant=reject_constant,
        )
        stack: list[tuple[object, int]] = [(value, 1)]
        while stack:
            current, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                _raise(status)
            if isinstance(current, dict):
                stack.extend((item, depth + 1) for item in current.values())
            elif isinstance(current, list):
                stack.extend((item, depth + 1) for item in current)
        return _exact_object(value, fields, status)
    except ProtocolError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _InvalidJSON,
        ValueError,
        RecursionError,
        MemoryError,
    ):
        _raise(status)


def _raw_absolute_path(value: object, status: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or not os.path.isabs(value)
    ):
        _raise(status)
    return value


def _canonical_existing_path(value: object, status: str) -> Path:
    raw = _raw_absolute_path(value, status)
    try:
        resolved = str(Path(raw).resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        _raise(status)
    if raw != resolved:
        _raise(status)
    return Path(resolved)


def _canonical_directory(value: object, status: str) -> Path:
    path = _canonical_existing_path(value, status)
    try:
        metadata = os.lstat(path)
    except OSError:
        _raise(status)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _raise(status)
    return path


def _regular_single_link_file(
    value: object, status: str, max_bytes: int
) -> tuple[Path, bytes, FileIdentity]:
    path = _canonical_existing_path(value, status)
    descriptor = -1
    try:
        before_open = os.lstat(path)
        if (
            not stat.S_ISREG(before_open.st_mode)
            or before_open.st_nlink != 1
            or before_open.st_size > max_bytes
        ):
            _raise(status)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(path, flags)
        after_open = os.fstat(descriptor)
        if not _same_file_state(before_open, after_open):
            _raise(status)
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after_read = os.fstat(descriptor)
        if (
            len(raw) > max_bytes
            or len(raw) != after_read.st_size
            or not _same_file_state(after_open, after_read)
        ):
            _raise(status)
    except (OSError, MemoryError):
        _raise(status)
    finally:
        if descriptor >= 0:
            cleanup_status, operation = _artifact_close_contract(status)
            to_close = descriptor
            descriptor = -1
            _close_descriptor(
                to_close,
                cleanup_status=cleanup_status,
                operation=operation,
                primary=sys.exc_info()[1],
            )
    return path, raw, FileIdentity.from_stat(after_read)


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
        and left.st_nlink == right.st_nlink == 1
        and left.st_size == right.st_size
        and getattr(left, "st_mtime_ns", int(left.st_mtime * 1_000_000_000))
        == getattr(right, "st_mtime_ns", int(right.st_mtime * 1_000_000_000))
        and getattr(left, "st_ctime_ns", int(left.st_ctime * 1_000_000_000))
        == getattr(right, "st_ctime_ns", int(right.st_ctime * 1_000_000_000))
    )


def _is_within(path: Path, parent: Path, *, strict: bool = False) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return not strict or path != parent


def _canonical_leaf_target(value: object, status: str) -> Path:
    raw = _raw_absolute_path(value, status)
    name = os.path.basename(raw)
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        _raise(status)
    parent_raw = os.path.dirname(raw)
    parent = _canonical_directory(parent_raw, status)
    canonical = str(parent / name)
    if raw != canonical:
        _raise(status)
    return Path(canonical)


def _require_absent_target(target: Path, status: str) -> None:
    try:
        os.lstat(target)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            _raise(status)
    else:
        _raise(status)


def _absent_leaf_collision_key(
    path: Path, status: str
) -> tuple[int, int, str]:
    """Return a conservative alias key without touching the absent leaf.

    NFD plus casefold deliberately overrejects aliases on case-sensitive file
    systems so a candidate cannot select the filesystem normalization policy.
    """

    try:
        before = os.lstat(path.parent)
        after = os.lstat(path.parent)
    except OSError:
        _raise(status)
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or stat.S_IFMT(before.st_mode) != stat.S_IFMT(after.st_mode)
    ):
        _raise(status)
    normalized_leaf = unicodedata.normalize("NFD", path.name).casefold()
    return before.st_dev, before.st_ino, normalized_leaf


def _require_control_file_location(
    path: Path, invocation_root: Path, execution_root: Path, status: str
) -> None:
    if not _is_within(path, invocation_root, strict=True) or _is_within(
        path, execution_root
    ):
        _raise(status)


def _validate_authority(
    context_path: str | None, environment: Mapping[str, str]
) -> tuple[str, str, str]:
    bootstrap_present = any(key.startswith(BOOTSTRAP_PREFIX) for key in environment)
    if context_path is None:
        if bootstrap_present:
            _raise("INHERITED_ENVIRONMENT_ONLY")
        _raise("INHERITED_MODE_NOT_REQUESTED")
    nonce = environment.get(BOOTSTRAP_NONCE_ENV)
    context_digest = environment.get(BOOTSTRAP_CONTEXT_DIGEST_ENV)
    if nonce is None or context_digest is None:
        _raise("INHERITED_CLI_ONLY")
    return context_path, _hex64(nonce, "INVALID_BOOTSTRAP_NONCE"), _hex64(
        context_digest, "INHERITED_CONTEXT_DIGEST_MISMATCH"
    )


def _validate_output_preflight(
    *,
    receipt_path: object,
    denial_log_path: object,
    tmpdir: Path,
    execution_root: Path,
    temp_probe_path: Path,
    protected_write_paths: Sequence[Path],
) -> tuple[Path, Path]:
    receipt = _canonical_leaf_target(receipt_path, "INHERITED_OUTPUT_INVALID")
    denial = _canonical_leaf_target(denial_log_path, "INHERITED_OUTPUT_INVALID")
    all_targets = (receipt, denial, temp_probe_path, *protected_write_paths)
    protected_parents = {path.parent for path in protected_write_paths}
    collision_keys = tuple(
        (
            "protected",
            unicodedata.normalize("NFD", str(path.parent)).casefold(),
            unicodedata.normalize("NFD", path.name).casefold(),
        )
        if path.parent in protected_parents
        else _absent_leaf_collision_key(path, "INHERITED_OUTPUT_INVALID")
        for path in all_targets
    )
    if len(set(collision_keys)) != len(collision_keys):
        _raise("INHERITED_OUTPUT_COLLISION")
    for output in (receipt, denial):
        if not _is_within(output, tmpdir, strict=True) or _is_within(
            output, execution_root
        ):
            _raise("INHERITED_OUTPUT_INVALID")
    _require_absent_target(receipt, "INHERITED_OUTPUT_INVALID")
    _require_absent_target(denial, "INHERITED_OUTPUT_INVALID")
    _require_absent_target(temp_probe_path, "INHERITED_TEMP_PROBE_INVALID")
    return receipt, denial


def validate_inherited_request(
    *,
    context_path: str | None,
    cli_root: str,
    cli_nonce: str,
    environment: Mapping[str, str],
    expected_environment_keys: Iterable[str],
    receipt_path: str,
    denial_log_path: str,
) -> ValidatedInheritedContext:
    """Validate inherited authority and all preflight evidence without writes."""

    raw_context_path, bootstrap_nonce, expected_context_digest = _validate_authority(
        context_path, environment
    )
    cli_nonce = _hex64(cli_nonce, "INVALID_BOOTSTRAP_NONCE")
    if cli_nonce != bootstrap_nonce:
        _raise("INVALID_BOOTSTRAP_NONCE")

    context_file, context_raw, _ = _regular_single_link_file(
        raw_context_path, "INHERITED_CONTEXT_INVALID", MAX_CONTEXT_BYTES
    )
    context = _decode_object(
        context_raw, CONTEXT_FIELDS, "INHERITED_CONTEXT_SCHEMA_INVALID"
    )
    canonical_context = canonical_json_bytes(context)
    actual_context_digest = sha256_bytes(canonical_context)
    if actual_context_digest != expected_context_digest:
        _raise("INHERITED_CONTEXT_DIGEST_MISMATCH")

    if context["schema"] != CONTEXT_SCHEMA:
        _raise("INHERITED_CONTEXT_SCHEMA_INVALID")
    context_nonce = _hex64(context["nonce"], "INVALID_BOOTSTRAP_NONCE")
    if context_nonce != cli_nonce:
        _raise("INVALID_BOOTSTRAP_NONCE")
    if context["profile_class"] == LOOPBACK_PROFILE_CLASS:
        _raise("INHERITED_PROFILE_CLASS_REJECTED")
    if context["profile_class"] != INHERITED_PROFILE_CLASS:
        _raise("INHERITED_PROFILE_CLASS_REJECTED")

    invocation_root = _canonical_directory(
        context["invocation_root"], "INHERITED_INVOCATION_ROOT_INVALID"
    )
    execution_root = _canonical_directory(
        context["execution_root"], "INHERITED_EXECUTION_ROOT_INVALID"
    )
    cli_execution_root = _canonical_directory(
        cli_root, "INHERITED_EXECUTION_ROOT_MISMATCH"
    )
    if cli_execution_root != execution_root:
        _raise("INHERITED_EXECUTION_ROOT_MISMATCH")
    _require_control_file_location(
        context_file,
        invocation_root,
        execution_root,
        "INHERITED_CONTEXT_INVALID",
    )

    profile_path, profile_raw, profile_identity = _regular_single_link_file(
        context["profile_path"], "INHERITED_PROFILE_INVALID", MAX_PROFILE_BYTES
    )
    _require_control_file_location(
        profile_path,
        invocation_root,
        execution_root,
        "INHERITED_PROFILE_INVALID",
    )
    profile_digest = _hex64(
        context["profile_sha256"], "INHERITED_PROFILE_MISMATCH"
    )
    if sha256_bytes(profile_raw) != profile_digest:
        _raise("INHERITED_PROFILE_MISMATCH")

    outer_receipt_path, outer_receipt_raw, _ = _regular_single_link_file(
        context["outer_receipt_path"],
        "INHERITED_RECEIPT_INVALID",
        MAX_OUTER_RECEIPT_BYTES,
    )
    _require_control_file_location(
        outer_receipt_path,
        invocation_root,
        execution_root,
        "INHERITED_RECEIPT_INVALID",
    )
    outer_receipt_digest = _hex64(
        context["outer_receipt_sha256"], "INHERITED_RECEIPT_MISMATCH"
    )
    outer_receipt = _decode_object(
        outer_receipt_raw,
        OUTER_RECEIPT_FIELDS,
        "INHERITED_RECEIPT_SCHEMA_INVALID",
    )
    if sha256_bytes(canonical_json_bytes(outer_receipt)) != outer_receipt_digest:
        _raise("INHERITED_RECEIPT_MISMATCH")
    if outer_receipt["schema"] != OUTER_RECEIPT_SCHEMA:
        _raise("INHERITED_RECEIPT_SCHEMA_INVALID")
    if outer_receipt["profile_class"] == LOOPBACK_PROFILE_CLASS:
        _raise("INHERITED_PROFILE_CLASS_REJECTED")

    raw_protected_roots = context["protected_read_roots"]
    if not isinstance(raw_protected_roots, list) or len(raw_protected_roots) != 2:
        _raise("INHERITED_PROTECTED_ROOTS_INVALID")
    protected_roots_list: list[Path] = []
    for value in raw_protected_roots:
        raw_root = _raw_absolute_path(value, "INHERITED_PROTECTED_ROOTS_INVALID")
        root_path = Path(raw_root)
        if str(root_path) != raw_root or any(
            part in {".", ".."} for part in root_path.parts
        ):
            _raise("INHERITED_PROTECTED_ROOTS_INVALID")
        protected_roots_list.append(root_path)
    protected_roots = tuple(protected_roots_list)

    raw_protected_writes = context["protected_write_paths"]
    if not isinstance(raw_protected_writes, list) or len(raw_protected_writes) != 2:
        _raise("INHERITED_PROTECTED_WRITES_INVALID")
    protected_writes_list: list[Path] = []
    for raw_path, protected_root in zip(raw_protected_writes, protected_roots):
        raw_write = _raw_absolute_path(
            raw_path, "INHERITED_PROTECTED_WRITES_INVALID"
        )
        protected_write = Path(raw_write)
        if (
            str(protected_write) != raw_write
            or protected_write.name in {"", ".", ".."}
            or any(part in {".", ".."} for part in protected_write.parts)
            or protected_write.parent != protected_root
        ):
            _raise("INHERITED_PROTECTED_WRITES_INVALID")
        protected_writes_list.append(protected_write)
    protected_writes = tuple(protected_writes_list)

    raw_tmpdir = environment.get("TMPDIR")
    tmpdir = _canonical_directory(raw_tmpdir, "INHERITED_TMPDIR_INVALID")
    if not _is_within(tmpdir, invocation_root, strict=True) or _is_within(
        tmpdir, execution_root
    ):
        _raise("INHERITED_TMPDIR_INVALID")
    temp_probe_path = _canonical_leaf_target(
        context["temp_probe_path"], "INHERITED_TEMP_PROBE_INVALID"
    )
    if not _is_within(temp_probe_path, tmpdir, strict=True):
        _raise("INHERITED_TEMP_PROBE_INVALID")

    environment_keys = sanitized_environment_keys(expected_environment_keys)

    receipt_roots_digest = _hex64(
        outer_receipt["protected_roots_sha256"],
        "INHERITED_RECEIPT_EVIDENCE_MISMATCH",
    )
    receipt_environment_keys = outer_receipt["environment_keys"]
    expected_evidence = (
        outer_receipt["status"] == "PASS"
        and outer_receipt["nonce"] == context_nonce
        and outer_receipt["profile_class"] == INHERITED_PROFILE_CLASS
        and outer_receipt["profile_sha256"] == profile_digest
        and receipt_roots_digest == protected_roots_sha256(protected_roots)
        and isinstance(receipt_environment_keys, list)
        and tuple(receipt_environment_keys) == environment_keys
    )
    if not expected_evidence:
        _raise("INHERITED_RECEIPT_EVIDENCE_MISMATCH")

    validated_receipt, validated_denial = _validate_output_preflight(
        receipt_path=receipt_path,
        denial_log_path=denial_log_path,
        tmpdir=tmpdir,
        execution_root=execution_root,
        temp_probe_path=temp_probe_path,
        protected_write_paths=protected_writes,
    )

    return ValidatedInheritedContext(
        context_path=context_file,
        context_sha256=actual_context_digest,
        nonce=context_nonce,
        profile_class=INHERITED_PROFILE_CLASS,
        profile_path=profile_path,
        profile_sha256=profile_digest,
        profile_bytes=profile_raw,
        profile_identity=profile_identity,
        outer_receipt_path=outer_receipt_path,
        outer_receipt_sha256=outer_receipt_digest,
        invocation_root=invocation_root,
        execution_root=execution_root,
        protected_read_roots=protected_roots,
        protected_write_paths=protected_writes,
        temp_probe_path=temp_probe_path,
        tmpdir=tmpdir,
        receipt_path=validated_receipt,
        denial_log_path=validated_denial,
        environment_keys=environment_keys,
    )


def _expect_list_eperm(path: Path) -> None:
    try:
        os.listdir(path)
    except OSError as exc:
        if exc.errno == errno.EPERM:
            return
        _raise_probe(
            "INHERITED_PROTECTED_LIST_NOT_DENIED",
            "protected_list",
            _errno_outcome(exc),
        )
    _raise_probe(
        "INHERITED_PROTECTED_LIST_NOT_DENIED",
        "protected_list",
        "success",
    )


def _expect_open_eperm(path: Path, flags: int, status: str, operation: str) -> None:
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.EPERM:
            return
        _raise_probe(status, operation, _errno_outcome(exc))
    primary = _probe_blocker(status, operation, "success")
    _close_descriptor(
        descriptor,
        cleanup_status="INHERITED_PROTECTED_OPEN_CLEANUP_FAILED",
        operation="protected_open_cleanup",
        primary=primary,
    )
    raise primary from None


def _expect_create_eperm(path: Path) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except OSError as exc:
        if exc.errno == errno.EPERM:
            return
        _raise_probe(
            "INHERITED_PROTECTED_WRITE_NOT_DENIED",
            "protected_write",
            _errno_outcome(exc),
        )
    primary = _probe_blocker(
        "INHERITED_PROTECTED_WRITE_NOT_DENIED",
        "protected_write",
        "success",
    )
    _close_descriptor(
        descriptor,
        cleanup_status="INHERITED_PROTECTED_WRITE_CLEANUP_FAILED",
        operation="protected_write_cleanup",
        primary=primary,
    )
    raise primary from None


def _best_effort_remove_temp_probe(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _probe_temp_roundtrip(path: Path) -> None:
    marker = b"samvil-inherited-boundary-probe-v1"
    descriptor = -1
    created = False
    try:
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            created = True
            offset = 0
            while offset < len(marker):
                written = os.write(descriptor, marker[offset:])
                if written <= 0:
                    _raise_probe(
                        "INHERITED_TEMP_PROBE_FAILED",
                        "temp_roundtrip",
                        "short_write",
                    )
                offset += written
        except OSError as exc:
            _raise_probe(
                "INHERITED_TEMP_PROBE_FAILED",
                "temp_roundtrip",
                _errno_outcome(exc),
            )
        finally:
            if descriptor >= 0:
                to_close = descriptor
                descriptor = -1
                _close_descriptor(
                    to_close,
                    cleanup_status="INHERITED_TEMP_WRITE_CLEANUP_FAILED",
                    operation="temp_write_cleanup",
                    primary=sys.exc_info()[1],
                )

        try:
            descriptor = os.open(path, os.O_RDONLY)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, READ_CHUNK_BYTES)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError as exc:
            _raise_probe(
                "INHERITED_TEMP_PROBE_FAILED",
                "temp_roundtrip",
                _errno_outcome(exc),
            )
        finally:
            if descriptor >= 0:
                to_close = descriptor
                descriptor = -1
                _close_descriptor(
                    to_close,
                    cleanup_status="INHERITED_TEMP_READ_CLEANUP_FAILED",
                    operation="temp_read_cleanup",
                    primary=sys.exc_info()[1],
                )
        if b"".join(chunks) != marker:
            _raise_probe(
                "INHERITED_TEMP_PROBE_FAILED",
                "temp_roundtrip",
                "content_mismatch",
            )
        try:
            os.unlink(path)
            created = False
        except OSError as exc:
            _raise_probe(
                "INHERITED_TEMP_PROBE_FAILED",
                "temp_roundtrip",
                _errno_outcome(exc),
            )
    finally:
        if descriptor >= 0:
            to_close = descriptor
            descriptor = -1
            _close_descriptor(
                to_close,
                cleanup_status="INHERITED_TEMP_CLEANUP_FAILED",
                operation="temp_cleanup",
                primary=sys.exc_info()[1],
            )
        if created:
            _best_effort_remove_temp_probe(path)


def _probe_execution_root_read(path: Path) -> None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        os.listdir(descriptor)
    except OSError as exc:
        _raise_probe(
            "INHERITED_EXECUTION_ROOT_UNREADABLE",
            "execution_root_read",
            _errno_outcome(exc),
        )
    finally:
        if descriptor >= 0:
            to_close = descriptor
            descriptor = -1
            _close_descriptor(
                to_close,
                cleanup_status="INHERITED_EXECUTION_ROOT_CLEANUP_FAILED",
                operation="execution_root_cleanup",
                primary=sys.exc_info()[1],
            )


def _expect_loopback_eperm(operation: str) -> None:
    sock: socket.socket | None = None
    creation_outcome: str | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        creation_outcome = _errno_outcome(exc)
    if sock is None:
        raise _probe_blocker(
            "INHERITED_LOOPBACK_SOCKET_UNAVAILABLE",
            operation,
            creation_outcome or "invalid_socket",
        ) from None

    primary: ProtocolError | None = None
    timeout_outcome: str | None = None
    try:
        sock.settimeout(1.0)
    except OSError as exc:
        timeout_outcome = _errno_outcome(exc)
    if timeout_outcome is not None:
        primary = _probe_blocker(
            "INHERITED_LOOPBACK_TIMEOUT_SETUP_FAILED",
            f"{operation}_timeout",
            timeout_outcome,
        )

    if primary is None:
        expected_eperm = False
        operation_outcome: str | None = None
        try:
            if operation == "loopback_bind":
                sock.bind(("127.0.0.1", 0))
            else:
                sock.connect(("127.0.0.1", 9))
        except OSError as exc:
            if exc.errno == errno.EPERM:
                expected_eperm = True
            else:
                operation_outcome = _errno_outcome(exc)
        if not expected_eperm:
            operation_outcome = operation_outcome or "success"
            status = (
                "INHERITED_LOOPBACK_BIND_NOT_DENIED"
                if operation == "loopback_bind"
                else "INHERITED_LOOPBACK_CONNECT_NOT_DENIED"
            )
            primary = _probe_blocker(status, operation, operation_outcome)

    cleanup_outcome: str | None = None
    try:
        sock.close()
    except OSError as exc:
        cleanup_outcome = _errno_outcome(exc)

    if primary is not None:
        raise primary from None
    if cleanup_outcome is not None:
        raise _probe_blocker(
            "INHERITED_LOOPBACK_CLEANUP_FAILED",
            f"{operation}_cleanup",
            cleanup_outcome,
        ) from None


def run_boundary_probes(
    context: ValidatedInheritedContext,
) -> BoundaryProbeEvidence:
    """Run only the inherited boundary probes bound by validated context."""

    for protected_root in context.protected_read_roots:
        _expect_list_eperm(protected_root)
        _expect_open_eperm(
            protected_root,
            os.O_RDONLY | os.O_DIRECTORY,
            "INHERITED_PROTECTED_OPEN_NOT_DENIED",
            "protected_open",
        )
        for operation, probe in (
            ("protected_stat", lambda path=protected_root: os.stat(path)),
            ("protected_lstat", lambda path=protected_root: os.lstat(path)),
        ):
            try:
                probe()
            except OSError as exc:
                if exc.errno == errno.EPERM:
                    continue
                _raise_probe(
                    "INHERITED_PROTECTED_METADATA_NOT_DENIED",
                    operation,
                    _errno_outcome(exc),
                )
            _raise_probe(
                "INHERITED_PROTECTED_METADATA_NOT_DENIED",
                operation,
                "success",
            )
        if os.access(protected_root, os.F_OK):
            _raise_probe(
                "INHERITED_PROTECTED_METADATA_NOT_DENIED",
                "protected_access",
                "true",
            )
        if os.path.exists(protected_root):
            _raise_probe(
                "INHERITED_PROTECTED_METADATA_NOT_DENIED",
                "protected_exists",
                "true",
            )
    for protected_write in context.protected_write_paths:
        _expect_create_eperm(protected_write)

    _probe_temp_roundtrip(context.temp_probe_path)
    _probe_execution_root_read(context.execution_root)
    _expect_loopback_eperm("loopback_bind")
    _expect_loopback_eperm("loopback_connect")

    root_count = len(context.protected_read_roots)
    return BoundaryProbeEvidence(
        protected_root_count=root_count,
        protected_list_eperm=root_count,
        protected_open_eperm=root_count,
        protected_stat_eperm=root_count,
        protected_lstat_eperm=root_count,
        protected_access_false=root_count,
        protected_exists_false=root_count,
        protected_write_eperm=len(context.protected_write_paths),
        temp_roundtrip=True,
        execution_root_read=True,
        loopback_bind_eperm=True,
        loopback_connect_eperm=True,
    )
