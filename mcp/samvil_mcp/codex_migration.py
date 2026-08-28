"""Recoverable migration of proven-generated legacy Codex artifacts.

The planner in :mod:`samvil_mcp.codex_installer` remains the authority.  This
module never executes caller-supplied actions: it rebuilds the plan while a
profile lock is held, revalidates each source at its mutation boundary, stages
the original object in a durable timestamped backup, and compensates in reverse
order if native activation does not complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

from .ssot_io import atomic_write_text_unlocked

try:  # POSIX, including every currently supported Codex Desktop host.
    import fcntl
except ImportError:  # pragma: no cover - fail closed on unsupported hosts
    fcntl = None  # type: ignore[assignment]


_PLAN_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSITION_ID = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{12}-[0-9a-f]{8}$")
_RECEIPT_SCHEMA = "samvil.codex-legacy-migration-receipt.v1"
_JOURNAL_SCHEMA = "samvil.codex-legacy-migration-journal.v1"
_TERMINAL_STATES = frozenset({"committed", "rolled_back"})


def _installer() -> Any:
    # Delayed import avoids a module cycle: codex_installer delegates to this
    # coordinator only for the explicit migrate path.
    from . import codex_installer

    return codex_installer


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text_unlocked(path, _canonical_json(payload) + "\n")


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _installer().InstallBlocked(f"invalid {label}: {path}") from exc
    if not isinstance(value, dict):
        raise _installer().InstallBlocked(f"invalid {label}: {path}")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _open_pinned_directory(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    create: bool,
    exist_ok: bool = True,
) -> int:
    installer = _installer()
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except FileExistsError as exc:
            if not exist_ok:
                raise installer.InstallBlocked(f"{label} already exists") from exc
        except OSError as exc:
            raise installer.InstallBlocked(f"{label} cannot be created safely") from exc
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_descriptor)
    except OSError as exc:
        raise installer.InstallBlocked(f"{label} cannot be opened safely") from exc
    try:
        _assert_entry_matches_descriptor(
            parent_descriptor,
            name,
            descriptor,
            label=label,
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _open_profile_lock_file(root_descriptor: int, lock_name: str) -> int:
    """Open one persistent lock inode despite a concurrent first creation.

    Darwin/APFS can report ``ENOENT`` when two processes race on the same
    ``O_CREAT`` open.  Electing one creator with ``O_EXCL`` avoids that race;
    the bounded retry covers the existing entry disappearing between the
    losing process's create and open calls.  Later descriptor/path checks
    remain the authority for rejecting replacement attacks.
    """

    installer = _installer()
    common_flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        common_flags |= os.O_NOFOLLOW
    create_flags = common_flags | os.O_CREAT | os.O_EXCL
    for _attempt in range(3):
        try:
            return os.open(
                lock_name,
                create_flags,
                0o600,
                dir_fd=root_descriptor,
            )
        except FileExistsError:
            try:
                return os.open(
                    lock_name,
                    common_flags,
                    dir_fd=root_descriptor,
                )
            except FileNotFoundError:
                continue
        except FileNotFoundError:
            continue
    raise installer.InstallBlocked(
        "legacy migration lock path changed repeatedly during acquisition"
    )


def _write_json_at(
    parent_descriptor: int,
    name: str,
    payload: dict[str, Any],
    *,
    replace_existing: bool = True,
) -> None:
    content = (_canonical_json(payload) + "\n").encode("utf-8")
    temporary_name = f".{name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if replace_existing:
            os.replace(
                temporary_name,
                name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
        else:
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise _installer().InstallBlocked(
                    f"durable migration artifact already exists: {name}"
                ) from exc
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        except FileNotFoundError:
            pass


def _read_json_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    display_path: Path,
) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise _installer().InstallBlocked(f"invalid {label}: {display_path}")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            raw = handle.read()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _installer().InstallBlocked(f"invalid {label}: {display_path}") from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    if not isinstance(value, dict):
        raise _installer().InstallBlocked(f"invalid {label}: {display_path}")
    return value


def _regular_file_exists_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> bool:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _installer().InstallBlocked(
            f"{label} cannot be inspected safely"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise _installer().InstallBlocked(f"{label} is unsafe")
    return True


def _publish_json_at(
    parent_descriptor: int,
    name: str,
    payload: dict[str, Any],
    *,
    label: str,
    display_path: Path,
) -> None:
    """Publish once, or accept an already published byte-equivalent value."""

    if _regular_file_exists_at(parent_descriptor, name, label=label):
        if (
            _read_json_at(
                parent_descriptor,
                name,
                label=label,
                display_path=display_path,
            )
            != payload
        ):
            raise _installer().InstallBlocked(
                f"existing {label} differs from the commit decision"
            )
        return
    _write_json_at(
        parent_descriptor,
        name,
        payload,
        replace_existing=False,
    )


def _move_no_replace(
    source: Path,
    destination: Path,
    *,
    source_parent_descriptor: int | None = None,
    destination_parent_descriptor: int | None = None,
) -> None:
    """Move an owned object without ever replacing an existing destination."""

    installer = _installer()
    source_parent = (
        os.dup(source_parent_descriptor)
        if source_parent_descriptor is not None
        else os.open(source.parent, _directory_flags())
    )
    try:
        destination_parent = (
            os.dup(destination_parent_descriptor)
            if destination_parent_descriptor is not None
            else os.open(destination.parent, _directory_flags())
        )
    except BaseException:
        os.close(source_parent)
        raise
    try:
        metadata = os.stat(source.name, dir_fd=source_parent, follow_symlinks=False)
        try:
            os.stat(destination.name, dir_fd=destination_parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise installer.InstallBlocked(
                f"migration destination already exists: {destination}"
            )
        if stat.S_ISREG(metadata.st_mode):
            try:
                os.link(
                    source.name,
                    destination.name,
                    src_dir_fd=source_parent,
                    dst_dir_fd=destination_parent,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise installer.InstallBlocked(
                    f"migration destination appeared concurrently: {destination}"
                ) from exc
            os.fsync(destination_parent)
            current = os.stat(
                source.name,
                dir_fd=source_parent,
                follow_symlinks=False,
            )
            if int(current.st_dev) != int(metadata.st_dev) or int(
                current.st_ino
            ) != int(metadata.st_ino):
                raise installer.InstallBlocked(
                    f"migration source changed concurrently: {source}"
                )
            os.unlink(source.name, dir_fd=source_parent)
        elif stat.S_ISDIR(metadata.st_mode):
            # The destination lives in a fresh mode-0700 transaction directory.
            # A pre-existing name is rejected above; moved identity/hash are
            # checked immediately after the rename.
            os.rename(
                source.name,
                destination.name,
                src_dir_fd=source_parent,
                dst_dir_fd=destination_parent,
            )
        else:
            raise installer.InstallBlocked(f"unsupported migration source: {source}")
        os.fsync(source_parent)
        os.fsync(destination_parent)
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _publish_bytes_no_replace(destination: Path, content: bytes, *, mode: int) -> None:
    installer = _installer()
    parent = os.open(destination.parent, _directory_flags())
    temporary_name = f".{destination.name}.migration-{os.getpid()}-{uuid.uuid4().hex}"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary_name, flags, mode, dir_fd=parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
        try:
            os.link(
                temporary_name,
                destination.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise installer.InstallBlocked(
                f"migration destination appeared concurrently: {destination}"
            ) from exc
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            pass
        finally:
            os.close(parent)


@dataclass(frozen=True)
class ProfileIdentity:
    """Pinned profile authority held for the lifetime of one migration."""

    root_descriptor: int
    backups_descriptor: int
    migrations_descriptor: int
    lock_descriptor: int
    root_identity: tuple[int, int]
    backups_identity: tuple[int, int]
    migrations_identity: tuple[int, int]
    lock_identity: tuple[int, int]


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise _installer().InstallBlocked(f"unsafe migration directory: {path}")
    return int(metadata.st_dev), int(metadata.st_ino)


def _metadata_identity(metadata: os.stat_result) -> tuple[int, int]:
    return int(metadata.st_dev), int(metadata.st_ino)


def _assert_directory_descriptor(
    descriptor: int,
    *,
    expected: tuple[int, int],
    label: str,
) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_nlink < 1
        or _metadata_identity(metadata) != expected
    ):
        raise _installer().InstallBlocked(
            f"{label} descriptor changed during migration"
        )


def _assert_entry_matches_descriptor(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    *,
    label: str,
    regular_file: bool = False,
) -> None:
    installer = _installer()
    try:
        entry = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        held = os.fstat(descriptor)
    except OSError as exc:
        raise installer.InstallBlocked(
            f"{label} path entry cannot be revalidated"
        ) from exc
    expected_type = stat.S_ISREG if regular_file else stat.S_ISDIR
    expected_links = held.st_nlink == 1 if regular_file else held.st_nlink >= 1
    if (
        not expected_type(entry.st_mode)
        or not expected_type(held.st_mode)
        or not expected_links
        or (regular_file and entry.st_nlink != 1)
        or entry.st_nlink != held.st_nlink
        or _metadata_identity(entry) != _metadata_identity(held)
    ):
        raise installer.InstallBlocked(f"{label} path entry changed during migration")


def _assert_transaction_identity(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    expected: tuple[int, int],
    *,
    path: Path,
) -> None:
    """Revalidate a transaction directory both by FD and by its parent entry."""

    _assert_entry_matches_descriptor(
        parent_descriptor,
        name,
        descriptor,
        label=f"migration transaction {path}",
    )
    metadata = os.fstat(descriptor)
    if _metadata_identity(metadata) != expected:
        raise _installer().InstallBlocked(
            f"migration transaction identity changed: {path}"
        )


def _assert_profile_identity(root: Path, expected: ProfileIdentity) -> None:
    installer = _installer()
    unsafe = installer._unsafe_directory_path_reason(root, label="Codex profile")
    if unsafe is not None:
        raise installer.InstallBlocked(unsafe)
    try:
        _assert_directory_descriptor(
            expected.root_descriptor,
            expected=expected.root_identity,
            label="Codex profile",
        )
        _assert_directory_descriptor(
            expected.backups_descriptor,
            expected=expected.backups_identity,
            label="Codex backups root",
        )
        _assert_directory_descriptor(
            expected.migrations_descriptor,
            expected=expected.migrations_identity,
            label="legacy migration transaction root",
        )
        if _directory_identity(root) != expected.root_identity:
            raise installer.InstallBlocked(
                "Codex profile path entry changed during migration"
            )
        _assert_entry_matches_descriptor(
            expected.root_descriptor,
            "backups",
            expected.backups_descriptor,
            label="Codex backups root",
        )
        if _directory_identity(root / "backups") != expected.backups_identity:
            raise installer.InstallBlocked(
                "Codex backups path entry changed during migration"
            )
        _assert_entry_matches_descriptor(
            expected.backups_descriptor,
            "legacy-migrations",
            expected.migrations_descriptor,
            label="legacy migration transaction root",
        )
        if (
            _directory_identity(root / "backups" / "legacy-migrations")
            != expected.migrations_identity
        ):
            raise installer.InstallBlocked(
                "legacy migration transaction path entry changed during migration"
            )
        _assert_entry_matches_descriptor(
            expected.root_descriptor,
            ".samvil-legacy-migration.lock",
            expected.lock_descriptor,
            label="legacy migration lock",
            regular_file=True,
        )
        lock_metadata = os.fstat(expected.lock_descriptor)
        if _metadata_identity(lock_metadata) != expected.lock_identity:
            raise installer.InstallBlocked(
                "legacy migration lock descriptor changed during migration"
            )
    except OSError as exc:
        raise installer.InstallBlocked(
            "Codex profile identity cannot be revalidated"
        ) from exc


@contextmanager
def _profile_lock(root: Path) -> Iterator[ProfileIdentity]:
    if fcntl is None:
        raise _installer().InstallBlocked(
            "legacy migration requires POSIX profile locking support"
        )
    directory_flags = _directory_flags()
    try:
        root_descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise _installer().InstallBlocked(
            f"unsafe Codex profile directory: {root}"
        ) from exc
    root_metadata = os.fstat(root_descriptor)
    if not stat.S_ISDIR(root_metadata.st_mode):
        os.close(root_descriptor)
        raise _installer().InstallBlocked("Codex migration root must be a directory")
    lock_name = ".samvil-legacy-migration.lock"
    lock_path = root / lock_name
    try:
        descriptor = _open_profile_lock_file(root_descriptor, lock_name)
    except BaseException:
        os.close(root_descriptor)
        raise
    backups_descriptor: int | None = None
    migrations_descriptor: int | None = None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise _installer().InstallBlocked(
                f"unsafe legacy migration lock file: {lock_path}"
            )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _assert_entry_matches_descriptor(
            root_descriptor,
            lock_name,
            descriptor,
            label="legacy migration lock",
            regular_file=True,
        )
        # The file lock serializes normal migrations. Directory locks keep a
        # second migration that opened a concurrently replaced lock entry from
        # reaching any profile mutation before the first holder fails closed.
        fcntl.flock(root_descriptor, fcntl.LOCK_EX)
        if _directory_identity(root) != _metadata_identity(root_metadata):
            raise _installer().InstallBlocked(
                "Codex profile path entry changed during migration"
            )
        _assert_entry_matches_descriptor(
            root_descriptor,
            lock_name,
            descriptor,
            label="legacy migration lock",
            regular_file=True,
        )
        backups_descriptor = _open_pinned_directory(
            root_descriptor,
            "backups",
            label=f"unsafe Codex backups directory: {root / 'backups'}",
            create=True,
        )
        backups_metadata = os.fstat(backups_descriptor)
        if not stat.S_ISDIR(backups_metadata.st_mode):
            raise _installer().InstallBlocked("Codex backups root must be a directory")
        fcntl.flock(backups_descriptor, fcntl.LOCK_EX)
        _assert_entry_matches_descriptor(
            root_descriptor,
            "backups",
            backups_descriptor,
            label="Codex backups root",
        )
        migrations_descriptor = _open_pinned_directory(
            backups_descriptor,
            "legacy-migrations",
            label=(
                "unsafe legacy migration transaction root: "
                f"{root / 'backups' / 'legacy-migrations'}"
            ),
            create=True,
        )
        migrations_metadata = os.fstat(migrations_descriptor)
        fcntl.flock(migrations_descriptor, fcntl.LOCK_EX)
        identity = ProfileIdentity(
            root_descriptor=root_descriptor,
            backups_descriptor=backups_descriptor,
            migrations_descriptor=migrations_descriptor,
            lock_descriptor=descriptor,
            root_identity=_metadata_identity(root_metadata),
            backups_identity=_metadata_identity(backups_metadata),
            migrations_identity=_metadata_identity(migrations_metadata),
            lock_identity=_metadata_identity(metadata),
        )
        _assert_profile_identity(root, identity)
        yield identity
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            if backups_descriptor is not None:
                if migrations_descriptor is not None:
                    fcntl.flock(migrations_descriptor, fcntl.LOCK_UN)
                    os.close(migrations_descriptor)
                fcntl.flock(backups_descriptor, fcntl.LOCK_UN)
                os.close(backups_descriptor)
            fcntl.flock(root_descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
            os.close(root_descriptor)


def _remove_generated_direct_mcp_table(content: bytes) -> bytes:
    """Remove only the four exact generated lines, preserving all other bytes."""

    installer = _installer()
    try:
        text = content.decode("utf-8")
        parsed = tomllib.loads(text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise installer.InstallBlocked(
            "legacy Codex config is not valid UTF-8 TOML"
        ) from exc
    servers = parsed.get("mcp_servers")
    table = servers.get("samvil-mcp") if isinstance(servers, dict) else None
    command = table.get("command") if isinstance(table, dict) else None
    if not isinstance(command, str):
        raise installer.InstallBlocked("generated direct MCP table disappeared")
    lines = text.splitlines(keepends=True)

    def body(line: str) -> str:
        return line.removesuffix("\n").removesuffix("\r")

    expected = (
        "[mcp_servers.samvil-mcp]",
        f'command = "{command}"',
        'args    = ["-m", "samvil_mcp.server"]',
        "env     = {}",
    )
    for index in range(max(0, len(lines) - 3)):
        if tuple(body(line) for line in lines[index : index + 4]) == expected:
            result = "".join((*lines[:index], *lines[index + 4 :])).encode("utf-8")
            try:
                post = tomllib.loads(result.decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
                raise installer.InstallBlocked(
                    "removing generated direct MCP table would invalidate config"
                ) from exc
            post_servers = post.get("mcp_servers")
            if isinstance(post_servers, dict) and "samvil-mcp" in post_servers:
                raise installer.InstallBlocked(
                    "generated direct MCP table removal is ambiguous"
                )
            return result
    raise installer.InstallBlocked(
        "generated direct MCP text block changed before migration"
    )


def _action_identity(action: Any) -> tuple[int, int, int, int, int, int, int]:
    values = (
        action.expected_device,
        action.expected_inode,
        action.expected_mode,
        action.expected_size,
        action.expected_nlink,
        action.expected_uid,
        action.expected_ctime_ns,
    )
    if any(value is None for value in values):
        raise _installer().InstallBlocked(
            f"migration action lacks sealed source identity: {action.path}"
        )
    return tuple(int(value) for value in values)  # type: ignore[arg-type, return-value]


def _revalidate_action(action: Any, *, root: Path, canonical_root: Path) -> Any:
    installer = _installer()
    source = installer._lexical_absolute(action.path)
    if action.artifact_kind == "legacy_skill_tree":
        if (
            action.kind != "migrate_generated"
            or source.parent != root / "skills"
            or source.name in {"", ".", ".."}
            or not installer._is_samvil_prefixed(source.name)
        ):
            raise installer.InstallBlocked(
                f"invalid legacy skill migration source: {source}"
            )
        artifact = installer._legacy_skill_artifact(
            source,
            canonical_root / "skills" / source.name,
        )
    elif action.artifact_kind == "global_agents":
        if action.kind != "migrate_generated" or source != root / "AGENTS.md":
            raise installer.InstallBlocked(
                f"invalid global AGENTS migration source: {source}"
            )
        artifact = installer._global_agents_artifact(source)
    elif action.artifact_kind == "direct_mcp_table":
        if (
            action.kind != "remove_generated_mcp_table"
            or source != root / "config.toml"
        ):
            raise installer.InstallBlocked(
                f"invalid direct MCP migration source: {source}"
            )
        artifact = installer._direct_mcp_artifact(source)
    else:
        raise installer.InstallBlocked(
            f"unsupported legacy migration artifact kind: {action.artifact_kind}"
        )
    if (
        artifact is None
        or artifact.classification != "generated_legacy"
        or artifact.blocks_mutation
        or artifact.content_hash != action.expected_hash
    ):
        raise installer.InstallBlocked(
            f"legacy artifact provenance changed before migration: {source}"
        )
    if installer._path_identity(source) != _action_identity(action):
        raise installer.InstallBlocked(
            f"legacy artifact identity changed before migration: {source}"
        )
    return artifact


def _moved_identity_matches(action: Any, backup: Path) -> bool:
    identity = _installer()._path_identity(backup)
    expected = _action_identity(action)
    # A rename may update ctime while every authority-bearing identity field
    # remains stable. Inode/device/mode/size/link-count/uid must still match.
    return identity is not None and identity[:6] == expected[:6]


def _artifact_hash(path: Path, artifact_kind: str) -> str:
    installer = _installer()
    metadata = path.lstat()
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)) and (
        artifact_kind != "legacy_skill_tree" or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise installer.InstallBlocked(f"unsafe migration backup artifact: {path}")
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
        raise installer.InstallBlocked(f"hard-linked migration backup artifact: {path}")
    if artifact_kind == "legacy_skill_tree":
        unsafe = installer._unsafe_tree_reason(path)
        if unsafe is not None:
            raise installer.InstallBlocked(f"unsafe migration backup artifact: {path}")
        return installer._skill_tree_hash(path)
    return installer._bytes_sha256(path.read_bytes())


def _receipt_digest(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("migration_receipt_sha256", None)
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _canonical_contract_from_payload(
    raw_contract: Any,
    *,
    label: str,
) -> tuple[tuple[str, str], ...]:
    if (
        not isinstance(raw_contract, dict)
        or not raw_contract
        or not all(
            isinstance(key, str)
            and isinstance(value, str)
            and (
                value == "missing" or value == "unsafe" or _PLAN_SHA256.fullmatch(value)
            )
            for key, value in raw_contract.items()
        )
    ):
        raise _installer().InstallBlocked(f"{label} is invalid")
    return tuple(sorted(raw_contract.items()))


def _receipt_from_payload(payload: dict[str, Any], *, root: Path) -> Any:
    installer = _installer()
    digest = payload.get("migration_receipt_sha256")
    if not isinstance(digest, str) or digest != _receipt_digest(payload):
        raise installer.InstallBlocked(
            "stored migration receipt integrity check failed"
        )
    if payload.get("mode") != "migrate":
        raise installer.InstallBlocked("stored migration receipt has an invalid mode")

    def entries(key: str) -> tuple[Any, ...]:
        raw = payload.get(key)
        if not isinstance(raw, list):
            raise installer.InstallBlocked("stored migration receipt is incomplete")
        result = []
        for item in raw:
            if not isinstance(item, dict):
                raise installer.InstallBlocked("stored migration receipt is incomplete")
            path = installer._lexical_absolute(Path(str(item.get("path", ""))))
            if path != root / "skills" / path.name:
                raise installer.InstallBlocked(
                    "stored migration receipt has an unsafe skill path"
                )
            name = item.get("name")
            content_hash = item.get("content_hash")
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(content_hash, str)
                or _PLAN_SHA256.fullmatch(content_hash) is None
            ):
                raise installer.InstallBlocked(
                    "stored migration receipt has invalid skill evidence"
                )
            result.append(
                installer.SkillInventoryEntry(
                    path,
                    name,
                    content_hash,
                )
            )
        return tuple(result)

    raw_backups = payload.get("backup_paths")
    raw_commands = payload.get("commands")
    if not isinstance(raw_backups, list) or not isinstance(raw_commands, list):
        raise installer.InstallBlocked("stored migration receipt is incomplete")
    backup_root = root / "backups"
    backups = tuple(
        installer._lexical_absolute(Path(str(item))) for item in raw_backups
    )
    if any(path == backup_root or backup_root not in path.parents for path in backups):
        raise installer.InstallBlocked(
            "stored migration receipt has an unsafe backup path"
        )
    if any(not path.exists() for path in backups):
        raise installer.InstallBlocked("stored migration backup is missing")
    for path in backups:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
        ):
            raise installer.InstallBlocked("stored migration backup is unsafe")
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
            raise installer.InstallBlocked("stored migration backup is hard-linked")
    commands: list[tuple[str, ...]] = []
    for command in raw_commands:
        if not isinstance(command, list) or not all(
            isinstance(part, str) for part in command
        ):
            raise installer.InstallBlocked(
                "stored migration receipt has an invalid command"
            )
        commands.append(tuple(command))
    canonical_root = Path(str(payload.get("canonical_root", ""))).expanduser()
    transition_id = payload.get("migration_transition_id")
    legacy_plan_sha256 = payload.get("legacy_plan_sha256")
    if (
        not canonical_root.is_absolute()
        or not isinstance(transition_id, str)
        or _TRANSITION_ID.fullmatch(transition_id) is None
        or not isinstance(legacy_plan_sha256, str)
        or _PLAN_SHA256.fullmatch(legacy_plan_sha256) is None
    ):
        raise installer.InstallBlocked("stored migration receipt authority is invalid")
    registry_before = installer._registry_snapshot_from_payload(
        payload.get("native_registry_before")
    )
    registry_after = installer._registry_snapshot_from_payload(
        payload.get("native_registry_after")
    )
    installer._require_cli_registry_evidence(registry_before)
    installer._require_cli_registry_evidence(registry_after)
    canonical_contract = _canonical_contract_from_payload(
        payload.get("canonical_contract"),
        label="stored migration canonical contract",
    )
    return installer.InstallReceipt(
        mode="migrate",
        canonical_root=canonical_root.resolve(strict=False),
        backup_paths=backups,
        commands=tuple(commands),
        personal_skills_before=entries("personal_skills_before"),
        personal_skills_after=entries("personal_skills_after"),
        native_registry_before=registry_before,
        native_registry_after=registry_after,
        canonical_contract=canonical_contract,
        legacy_plan_sha256=legacy_plan_sha256,
        migration_transition_id=transition_id,
        migration_receipt_sha256=digest,
    )


def _journal_actions(plan: Any, transaction: Path) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, action in enumerate(plan.actions):
        if action.artifact_kind == "legacy_skill_tree":
            backup = transaction / f"legacy-skill-{index:03d}-{action.path.name}"
        elif action.artifact_kind == "global_agents":
            backup = transaction / "global-AGENTS.md"
        elif action.artifact_kind == "direct_mcp_table":
            backup = transaction / "config.toml.before"
        else:
            raise _installer().InstallBlocked(
                f"unsupported legacy migration artifact kind: {action.artifact_kind}"
            )
        actions.append(
            {
                "index": index,
                "kind": action.kind,
                "artifact_kind": action.artifact_kind,
                "source": str(action.path),
                "backup": str(backup),
                "expected_hash": action.expected_hash,
                "replacement_hash": None,
                "staged": False,
            }
        )
    return actions


def _write_journal(
    path: Path,
    journal: dict[str, Any],
    state: str,
    *,
    parent_descriptor: int | None = None,
) -> None:
    journal["state"] = state
    journal["updated_at"] = datetime.now(timezone.utc).isoformat()
    if parent_descriptor is None:
        _write_json(path, journal)
    else:
        _write_json_at(parent_descriptor, path.name, journal)


def _native_backup_evidence(paths: tuple[Path, ...]) -> list[dict[str, str]]:
    installer = _installer()
    evidence: list[dict[str, str]] = []
    for path in paths:
        lexical = installer._lexical_absolute(path)
        metadata = lexical.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise installer.InstallBlocked(
                f"native Codex backup is not an independent regular file: {lexical}"
            )
        evidence.append(
            {
                "path": str(lexical),
                "sha256": installer._bytes_sha256(lexical.read_bytes()),
            }
        )
    return evidence


def _rollback_actions(
    journal: dict[str, Any],
    journal_path: Path,
    *,
    transaction_descriptor: int | None = None,
    verify_boundary: Any | None = None,
) -> None:
    installer = _installer()

    def persist(state: str) -> None:
        if verify_boundary is not None:
            verify_boundary()
        _write_journal(
            journal_path,
            journal,
            state,
            parent_descriptor=transaction_descriptor,
        )

    persist("rolling_back")
    errors: list[str] = []
    for record in reversed(journal.get("actions", [])):
        source = installer._lexical_absolute(Path(str(record["source"])))
        backup = installer._lexical_absolute(Path(str(record["backup"])))
        if not backup.exists() and not backup.is_symlink():
            try:
                already_restored = (
                    source.exists()
                    and not source.is_symlink()
                    and _artifact_hash(source, str(record["artifact_kind"]))
                    == record["expected_hash"]
                )
            except (OSError, installer.InstallBlocked):
                already_restored = False
            if already_restored:
                record["staged"] = False
                persist("rolling_back")
                continue
            if record.get("staged"):
                errors.append(f"staged migration backup is missing: {backup}")
            continue
        try:
            if source.exists() and not source.is_symlink():
                try:
                    same_object = os.path.samestat(source.lstat(), backup.lstat())
                except OSError:
                    same_object = False
                if same_object:
                    if verify_boundary is not None:
                        verify_boundary()
                    if transaction_descriptor is None:
                        backup.unlink()
                        _fsync_directory(backup.parent)
                    else:
                        os.unlink(backup.name, dir_fd=transaction_descriptor)
                        os.fsync(transaction_descriptor)
                    record["staged"] = False
                    persist("rolling_back")
                    continue
            if (
                _artifact_hash(backup, str(record["artifact_kind"]))
                != record["expected_hash"]
            ):
                raise installer.InstallBlocked(
                    f"legacy migration backup changed before rollback: {backup}"
                )
            if record["artifact_kind"] == "direct_mcp_table" and source.exists():
                replacement_hash = record.get("replacement_hash")
                if (
                    source.is_symlink()
                    or not source.is_file()
                    or installer._bytes_sha256(source.read_bytes()) != replacement_hash
                ):
                    raise installer.InstallBlocked(
                        f"unexpected Codex config blocks rollback: {source}"
                    )
                if verify_boundary is not None:
                    verify_boundary()
                source.unlink()
                _fsync_directory(source.parent)
            elif source.exists() or source.is_symlink():
                raise installer.InstallBlocked(
                    f"unexpected path blocks legacy rollback: {source}"
                )
            if verify_boundary is not None:
                verify_boundary()
            _move_no_replace(
                backup,
                source,
                source_parent_descriptor=transaction_descriptor,
            )
            if (
                _artifact_hash(source, str(record["artifact_kind"]))
                != record["expected_hash"]
            ):
                raise installer.InstallBlocked(
                    f"restored legacy artifact hash mismatch: {source}"
                )
            record["staged"] = False
            persist("rolling_back")
        except (OSError, installer.InstallBlocked) as exc:
            errors.append(str(exc))
    if errors:
        journal["rollback_errors"] = errors
        persist("rollback_failed")
        raise installer.InstallBlocked(
            "legacy migration rollback failed; backups were preserved: "
            + "; ".join(errors)
        )
    persist("rolled_back")


def _validate_journal(
    journal: dict[str, Any],
    *,
    journal_path: Path,
    transaction: Path,
    root: Path,
) -> None:
    installer = _installer()
    transition_id = journal.get("migration_transition_id")
    if (
        not isinstance(transition_id, str)
        or _TRANSITION_ID.fullmatch(transition_id) is None
        or transaction.name != transition_id
    ):
        raise installer.InstallBlocked(
            f"invalid migration transaction id: {transaction}"
        )
    if journal.get("schema_version") != _JOURNAL_SCHEMA:
        raise installer.InstallBlocked(
            f"unknown migration journal schema: {journal_path}"
        )
    if installer._lexical_absolute(Path(str(journal.get("codex_home", "")))) != root:
        raise installer.InstallBlocked(
            f"migration journal profile mismatch: {journal_path}"
        )
    raw_canonical_root = Path(str(journal.get("canonical_root", ""))).expanduser()
    if not raw_canonical_root.is_absolute():
        raise installer.InstallBlocked(
            f"migration journal canonical root is invalid: {journal_path}"
        )
    if "canonical_contract" in journal:
        _canonical_contract_from_payload(
            journal["canonical_contract"],
            label=f"migration journal canonical contract: {journal_path}",
        )
    plan_sha256 = journal.get("legacy_plan_sha256")
    if not isinstance(plan_sha256, str) or _PLAN_SHA256.fullmatch(plan_sha256) is None:
        raise installer.InstallBlocked(
            f"migration journal plan hash is invalid: {journal_path}"
        )
    if not isinstance(journal.get("native_activation_started"), bool):
        raise installer.InstallBlocked(
            f"migration journal native activation state is invalid: {journal_path}"
        )
    # Journals written before per-command native evidence was introduced may
    # not have this field.  Treat the missing field as an empty evidence list,
    # then let the state machine below keep any post-native journal fail-closed
    # (rather than rejecting it as malformed and losing the recovery hint).
    raw_native_events = journal.get("native_events", [])
    if not isinstance(raw_native_events, list):
        raise installer.InstallBlocked(
            f"migration journal native event evidence is invalid: {journal_path}"
        )
    allowed_native_events = {
        "snapshot_before",
        "command_intent",
        "command_applied",
        "command_readback",
        "snapshot_after",
        "activation_verified_before_legacy_retirement",
        "rollback_started",
        "rollback_intent",
        "rollback_applied",
        "rollback_verified",
    }
    for event in raw_native_events:
        if (
            not isinstance(event, dict)
            or event.get("kind") not in allowed_native_events
        ):
            raise installer.InstallBlocked(
                f"migration journal native event is invalid: {journal_path}"
            )
        argv = event.get("argv")
        if argv is not None and (
            not isinstance(argv, list)
            or not argv
            or argv[0] != "codex"
            or not all(isinstance(part, str) for part in argv)
        ):
            raise installer.InstallBlocked(
                f"migration journal native command is invalid: {journal_path}"
            )
        snapshot = event.get("snapshot")
        if snapshot is not None:
            installer._registry_snapshot_from_payload(snapshot)
    raw_actions = journal.get("actions")
    if not isinstance(raw_actions, list):
        raise installer.InstallBlocked(
            f"migration journal actions are invalid: {journal_path}"
        )
    seen_sources: set[Path] = set()
    seen_backups: set[Path] = set()
    for expected_index, record in enumerate(raw_actions):
        if not isinstance(record, dict):
            raise installer.InstallBlocked(
                f"migration journal action is invalid: {journal_path}"
            )
        source = installer._lexical_absolute(Path(str(record.get("source", ""))))
        backup = installer._lexical_absolute(Path(str(record.get("backup", ""))))
        kind = record.get("artifact_kind")
        if record.get("index") != expected_index or not isinstance(
            record.get("staged"), bool
        ):
            raise installer.InstallBlocked(
                f"migration journal action state is invalid: {journal_path}"
            )
        expected_kind = (
            "remove_generated_mcp_table"
            if kind == "direct_mcp_table"
            else "migrate_generated"
        )
        if record.get("kind") != expected_kind:
            raise installer.InstallBlocked(
                f"migration journal action kind is invalid: {journal_path}"
            )
        source_allowed = (
            (
                kind == "legacy_skill_tree"
                and source.parent == root / "skills"
                and installer._is_samvil_prefixed(source.name)
            )
            or (kind == "global_agents" and source == root / "AGENTS.md")
            or (kind == "direct_mcp_table" and source == root / "config.toml")
        )
        if not source_allowed:
            raise installer.InstallBlocked(
                f"migration journal contains an unsafe source: {source}"
            )
        if backup.parent != transaction or backup == transaction:
            raise installer.InstallBlocked(
                f"migration journal contains an unsafe backup: {backup}"
            )
        expected_backup_name = (
            f"legacy-skill-{expected_index:03d}-{source.name}"
            if kind == "legacy_skill_tree"
            else "global-AGENTS.md"
            if kind == "global_agents"
            else "config.toml.before"
        )
        if backup.name != expected_backup_name:
            raise installer.InstallBlocked(
                f"migration journal contains an unexpected backup name: {backup}"
            )
        if source in seen_sources or backup in seen_backups:
            raise installer.InstallBlocked(
                f"migration journal contains duplicate paths: {journal_path}"
            )
        expected_hash = record.get("expected_hash")
        replacement_hash = record.get("replacement_hash")
        if (
            not isinstance(expected_hash, str)
            or _PLAN_SHA256.fullmatch(expected_hash) is None
        ):
            raise installer.InstallBlocked(
                f"migration journal contains an invalid artifact hash: {journal_path}"
            )
        if replacement_hash is not None and (
            not isinstance(replacement_hash, str)
            or _PLAN_SHA256.fullmatch(replacement_hash) is None
        ):
            raise installer.InstallBlocked(
                f"migration journal contains an invalid replacement hash: {journal_path}"
            )
        seen_sources.add(source)
        seen_backups.add(backup)


@contextmanager
def _pinned_transaction(
    profile_identity: ProfileIdentity,
    *,
    root: Path,
    transaction_name: str,
    transaction_path: Path,
) -> Iterator[tuple[int, Any]]:
    descriptor = _open_pinned_directory(
        profile_identity.migrations_descriptor,
        transaction_name,
        label=f"unsafe legacy migration transaction entry: {transaction_path}",
        create=False,
    )
    expected = _metadata_identity(os.fstat(descriptor))

    def verify_boundary() -> None:
        _assert_profile_identity(root, profile_identity)
        _assert_transaction_identity(
            profile_identity.migrations_descriptor,
            transaction_name,
            descriptor,
            expected,
            path=transaction_path,
        )

    try:
        verify_boundary()
        yield descriptor, verify_boundary
    finally:
        os.close(descriptor)


def _load_committed_receipt(
    migrations_root: Path,
    *,
    root: Path,
    expected_plan_sha256: str,
    canonical_root: Path,
    registry_reader: Any | None,
    profile_identity: ProfileIdentity,
) -> Any | None:
    installer = _installer()
    _assert_profile_identity(root, profile_identity)
    for transaction_name in sorted(os.listdir(profile_identity.migrations_descriptor)):
        transaction = migrations_root / transaction_name
        with _pinned_transaction(
            profile_identity,
            root=root,
            transaction_name=transaction_name,
            transaction_path=transaction,
        ) as (transaction_descriptor, verify_boundary):
            journal_path = transaction / "journal.json"
            journal = _read_json_at(
                transaction_descriptor,
                journal_path.name,
                label="migration journal",
                display_path=journal_path,
            )
            _validate_journal(
                journal,
                journal_path=journal_path,
                transaction=transaction,
                root=root,
            )
            journal_canonical_root = Path(str(journal["canonical_root"])).resolve(
                strict=False
            )
            raw_journal_contract = journal.get("canonical_contract")
            journal_canonical_contract = (
                _canonical_contract_from_payload(
                    raw_journal_contract,
                    label=f"migration journal canonical contract: {journal_path}",
                )
                if raw_journal_contract is not None
                else ()
            )
            state = journal.get("state")
            if state in {"prepared", "staging", "staged", "rolling_back"}:
                if state == "rolling_back" and journal.get("native_activation_started"):
                    raise installer.InstallBlocked(
                        "legacy migration rollback was interrupted after native activation "
                        f"began; manual recovery is required: {transaction}"
                    )
                _rollback_actions(
                    journal,
                    journal_path,
                    transaction_descriptor=transaction_descriptor,
                    verify_boundary=verify_boundary,
                )
                continue
            if state == "rolled_back":
                continue
            if state == "rollback_failed":
                raise installer.InstallBlocked(
                    "unresolved legacy migration rollback blocks further mutation: "
                    f"{transaction}"
                )
            finalize_commit_decided = False
            if state == "commit_decided":
                embedded = journal.get("receipt")
                if not isinstance(embedded, dict):
                    raise installer.InstallBlocked(
                        f"commit-decided migration has no durable receipt: {transaction}"
                    )
                receipt = _receipt_from_payload(embedded, root=root)
                if (
                    receipt.canonical_root != journal_canonical_root
                    or receipt.legacy_plan_sha256 != journal.get("legacy_plan_sha256")
                    or receipt.canonical_contract != journal_canonical_contract
                    or receipt.migration_transition_id != transaction.name
                ):
                    raise installer.InstallBlocked(
                        "commit-decided migration receipt does not match its journal: "
                        f"{transaction}"
                    )
                if journal_canonical_root != canonical_root:
                    raise installer.InstallBlocked(
                        "commit-decided migration canonical root differs from the "
                        "requested repository"
                    )
                current_canonical_contract = tuple(
                    sorted(installer._canonical_activation_contract(canonical_root))
                )
                if receipt.canonical_contract != current_canonical_contract:
                    raise installer.InstallBlocked(
                        "commit-decided migration canonical contract changed"
                    )
                finalize_commit_decided = True
                state = "committed"
            elif state in {
                "native_activating",
                "native_verified",
                "native_recovery_required",
            }:
                raise installer.InstallBlocked(
                    "legacy migration stopped after native activation began; manual recovery "
                    f"is required before further mutation: {transaction}"
                )
            elif state not in _TERMINAL_STATES:
                raise installer.InstallBlocked(
                    f"unknown legacy migration journal state: {state!r}"
                )
            if (
                state != "committed"
                or journal.get("legacy_plan_sha256") != expected_plan_sha256
            ):
                continue
            if journal_canonical_root != canonical_root:
                raise installer.InstallBlocked(
                    "stored migration receipt canonical root differs from the requested repository"
                )
            receipt_path = transaction / "receipt.json"
            if finalize_commit_decided:
                receipt_payload = journal["receipt"]
            else:
                receipt_envelope = _read_json_at(
                    transaction_descriptor,
                    receipt_path.name,
                    label="migration receipt",
                    display_path=receipt_path,
                )
                if receipt_envelope.get("schema_version") != _RECEIPT_SCHEMA:
                    raise installer.InstallBlocked(
                        "unknown stored migration receipt schema"
                    )
                receipt_payload = receipt_envelope.get("receipt")
                if not isinstance(receipt_payload, dict):
                    raise installer.InstallBlocked(
                        "stored migration receipt is incomplete"
                    )
            embedded_receipt = journal.get("receipt")
            if (
                isinstance(embedded_receipt, dict)
                and receipt_payload != embedded_receipt
            ):
                raise installer.InstallBlocked(
                    "stored migration receipt differs from its committed journal"
                )
            receipt = _receipt_from_payload(receipt_payload, root=root)
            if receipt.canonical_root != canonical_root:
                raise installer.InstallBlocked(
                    "stored migration receipt canonical root changed"
                )
            if receipt.legacy_plan_sha256 != expected_plan_sha256:
                raise installer.InstallBlocked(
                    "stored migration receipt plan hash changed"
                )
            if receipt.canonical_contract != journal_canonical_contract:
                raise installer.InstallBlocked(
                    "stored migration receipt canonical contract differs from its journal"
                )
            current_canonical_contract = tuple(
                sorted(installer._canonical_activation_contract(canonical_root))
            )
            if receipt.canonical_contract != current_canonical_contract:
                raise installer.InstallBlocked(
                    "stored migration receipt canonical contract changed"
                )
            if receipt.migration_transition_id != transaction.name:
                raise installer.InstallBlocked(
                    "stored migration receipt transaction changed"
                )
            if registry_reader is None:
                raise installer.InstallBlocked(
                    "stored migration replay requires Codex CLI registry evidence"
                )
            current_registry = installer._read_native_registry(
                registry_reader,
                {"CODEX_HOME": str(root), "HOME": str(root.parent)},
                mutation_started=False,
            )
            installer._require_cli_registry_evidence(current_registry)
            if (
                receipt.native_registry_after is None
                or not installer._registry_related_equal(
                    receipt.native_registry_after,
                    current_registry,
                )
            ):
                raise installer.InstallBlocked(
                    "stored migration receipt native registry postcondition changed"
                )
            if receipt.native_registry_after.evidence_kind == "codex_cli":
                installer._verify_native_postcondition(
                    current_registry,
                    wrapper=root / "marketplaces" / "samvil-codex",
                )
            receipt_backup_paths = set(receipt.backup_paths)
            for record in journal["actions"]:
                verify_boundary()
                backup = Path(str(record["backup"]))
                if backup not in receipt_backup_paths:
                    raise installer.InstallBlocked(
                        "stored migration receipt omits a legacy backup"
                    )
                if (
                    _artifact_hash(backup, str(record["artifact_kind"]))
                    != record["expected_hash"]
                ):
                    raise installer.InstallBlocked(
                        f"stored legacy migration backup hash changed: {backup}"
                    )
            native_backups = journal.get("native_backups")
            if not isinstance(native_backups, list):
                raise installer.InstallBlocked(
                    "stored migration journal omits native backup evidence"
                )
            for item in native_backups:
                verify_boundary()
                if not isinstance(item, dict):
                    raise installer.InstallBlocked(
                        "stored native backup evidence is invalid"
                    )
                path = installer._lexical_absolute(Path(str(item.get("path", ""))))
                digest = item.get("sha256")
                if (
                    path not in receipt_backup_paths
                    or not isinstance(digest, str)
                    or _PLAN_SHA256.fullmatch(digest) is None
                    or not path.is_file()
                    or path.is_symlink()
                    or path.lstat().st_nlink != 1
                    or installer._bytes_sha256(path.read_bytes()) != digest
                ):
                    raise installer.InstallBlocked(
                        f"stored native Codex backup evidence changed: {path}"
                    )
            verify_boundary()
            current = installer.build_legacy_migration_plan(
                repo_root=canonical_root,
                codex_home=root,
            )
            if current.blockers or current.actions:
                raise installer.InstallBlocked(
                    "stored migration receipt postcondition no longer holds"
                )
            if not installer.compare_skill_inventories(
                current.personal_skills,
                receipt.personal_skills_after,
            ):
                raise installer.InstallBlocked(
                    "personal Codex skills changed since the stored migration receipt"
                )
            readiness = installer.validate_activation_readiness(canonical_root)
            if not readiness["ready"]:
                raise installer.InstallBlocked(
                    "stored migration canonical plugin is no longer activation-ready"
                )
            wrapper = root / "marketplaces" / "samvil-codex"
            if not wrapper.is_dir() or wrapper.is_symlink():
                raise installer.InstallBlocked(
                    "stored migration marketplace wrapper is missing"
                )
            verify_boundary()
            installer._codex_marketplace_wrapper(root, canonical_root)
            if finalize_commit_decided:
                verify_boundary()
                _publish_json_at(
                    transaction_descriptor,
                    receipt_path.name,
                    {"schema_version": _RECEIPT_SCHEMA, "receipt": receipt_payload},
                    label="migration receipt",
                    display_path=receipt_path,
                )
                verify_boundary()
                _write_journal(
                    journal_path,
                    journal,
                    "committed",
                    parent_descriptor=transaction_descriptor,
                )
            return receipt
    return None


def _stage_actions(
    plan: Any,
    *,
    root: Path,
    journal: dict[str, Any],
    journal_path: Path,
    profile_identity: ProfileIdentity,
    transaction_descriptor: int,
    verify_boundary: Any,
) -> None:
    installer = _installer()
    for action, record in zip(plan.actions, journal["actions"], strict=True):
        _assert_profile_identity(root, profile_identity)
        _revalidate_action(action, root=root, canonical_root=plan.canonical_root)
        source = installer._lexical_absolute(action.path)
        backup = installer._lexical_absolute(Path(record["backup"]))
        if backup.exists() or backup.is_symlink():
            raise installer.InstallBlocked(
                f"migration backup destination already exists: {backup}"
            )
        if action.artifact_kind == "direct_mcp_table":
            original = source.read_bytes()
            replacement = _remove_generated_direct_mcp_table(original)
            record["replacement_hash"] = installer._bytes_sha256(replacement)
        else:
            replacement = None
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "staging",
            parent_descriptor=transaction_descriptor,
        )
        verify_boundary()
        _move_no_replace(
            source,
            backup,
            destination_parent_descriptor=transaction_descriptor,
        )
        verify_boundary()
        if (
            not _moved_identity_matches(action, backup)
            or _artifact_hash(backup, str(action.artifact_kind)) != action.expected_hash
        ):
            raise installer.InstallBlocked(f"migration backup hash mismatch: {backup}")
        record["staged"] = True
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "staging",
            parent_descriptor=transaction_descriptor,
        )
        if replacement is not None:
            verify_boundary()
            _publish_bytes_no_replace(
                source,
                replacement,
                mode=int(action.expected_mode),
            )
            if (
                installer._bytes_sha256(source.read_bytes())
                != record["replacement_hash"]
            ):
                raise installer.InstallBlocked(
                    f"migrated Codex config hash mismatch: {source}"
                )
    verify_boundary()
    _write_journal(
        journal_path,
        journal,
        "staged",
        parent_descriptor=transaction_descriptor,
    )


def _run_locked_migration(
    plan: Any,
    *,
    root: Path,
    command_runner: Any,
    registry_reader: Any | None,
    expected_plan_sha256: str,
    profile_identity: ProfileIdentity,
) -> Any:
    installer = _installer()
    _assert_profile_identity(root, profile_identity)
    migrations_root = root / "backups" / "legacy-migrations"
    if (
        os.fstat(profile_identity.root_descriptor).st_dev
        != os.fstat(profile_identity.migrations_descriptor).st_dev
    ):
        raise installer.InstallBlocked(
            "legacy migration backups must be on the Codex profile filesystem"
        )
    replay = _load_committed_receipt(
        migrations_root,
        root=root,
        expected_plan_sha256=expected_plan_sha256,
        canonical_root=plan.canonical_root,
        registry_reader=registry_reader,
        profile_identity=profile_identity,
    )
    if replay is not None:
        return replay

    authoritative = installer.build_legacy_migration_plan(
        repo_root=plan.canonical_root,
        codex_home=root,
    )
    authoritative_payload = authoritative.to_dict()
    if authoritative.blockers:
        raise installer.InstallBlocked("; ".join(authoritative.blockers))
    if authoritative_payload["plan_sha256"] != expected_plan_sha256:
        raise installer.InstallBlocked(
            "legacy Codex profile changed after the checked plan; rerun the check"
        )
    if registry_reader is None:
        raise installer.InstallBlocked(
            "legacy Codex migration requires machine-readable native readback"
        )
    locked_registry = installer._read_native_registry(
        registry_reader,
        {"CODEX_HOME": str(root), "HOME": str(root.parent)},
        mutation_started=False,
    )
    installer._require_cli_registry_evidence(locked_registry)
    sealed_registry_available = True

    def activation_registry_reader(env: dict[str, str]) -> Any:
        nonlocal sealed_registry_available
        if sealed_registry_available:
            sealed_registry_available = False
            return locked_registry
        return registry_reader(env)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    transition_id = f"{stamp}-{expected_plan_sha256[:12]}-{uuid.uuid4().hex[:8]}"
    transaction = migrations_root / transition_id
    _assert_profile_identity(root, profile_identity)
    transaction_descriptor = _open_pinned_directory(
        profile_identity.migrations_descriptor,
        transition_id,
        label=f"legacy migration transaction: {transaction}",
        create=True,
        exist_ok=False,
    )
    transaction_identity = _metadata_identity(os.fstat(transaction_descriptor))

    def verify_boundary() -> None:
        _assert_profile_identity(root, profile_identity)
        _assert_transaction_identity(
            profile_identity.migrations_descriptor,
            transition_id,
            transaction_descriptor,
            transaction_identity,
            path=transaction,
        )

    journal_path = transaction / "journal.json"
    journal: dict[str, Any] = {
        "schema_version": _JOURNAL_SCHEMA,
        "migration_transition_id": transition_id,
        "legacy_plan_sha256": expected_plan_sha256,
        "canonical_root": str(plan.canonical_root),
        "codex_home": str(root),
        "canonical_contract": dict(authoritative.canonical_contract),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "native_activation_started": False,
        "native_backups": [],
        "native_events": [],
        "actions": _journal_actions(authoritative, transaction),
    }
    native_completed = False
    try:
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "prepared",
            parent_descriptor=transaction_descriptor,
        )
        _stage_actions(
            authoritative,
            root=root,
            journal=journal,
            journal_path=journal_path,
            profile_identity=profile_identity,
            transaction_descriptor=transaction_descriptor,
            verify_boundary=verify_boundary,
        )
        _assert_profile_identity(root, profile_identity)
        clean_plan = installer.build_legacy_migration_plan(
            repo_root=plan.canonical_root,
            codex_home=root,
        )
        if (
            clean_plan.blockers
            or clean_plan.actions
            or clean_plan.canonical_contract != authoritative.canonical_contract
        ):
            raise installer.InstallBlocked(
                "legacy postcondition failed before native Codex activation"
            )
        journal["native_activation_started"] = True
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "native_activating",
            parent_descriptor=transaction_descriptor,
        )
        verify_boundary()

        def record_native_event(event: dict[str, Any]) -> None:
            journal["native_events"].append(event)
            verify_boundary()
            _write_journal(
                journal_path,
                journal,
                "native_activating",
                parent_descriptor=transaction_descriptor,
            )

        native_receipt = installer.execute_isolated_install(
            plan,
            codex_home=root,
            command_runner=command_runner,
            registry_reader=activation_registry_reader,
            native_event_recorder=record_native_event,
            migrate=False,
            expected_legacy_plan_sha256=clean_plan.to_dict()["plan_sha256"],
            allow_legacy_registry_migration=True,
        )
        native_completed = True
        journal["native_backups"] = _native_backup_evidence(native_receipt.backup_paths)
        final_plan = installer.build_legacy_migration_plan(
            repo_root=plan.canonical_root,
            codex_home=root,
        )
        if (
            final_plan.blockers
            or final_plan.actions
            or final_plan.canonical_contract != authoritative.canonical_contract
        ):
            raise installer.InstallBlocked(
                "legacy artifacts reappeared during native Codex activation"
            )
        _assert_profile_identity(root, profile_identity)
        if not installer.compare_skill_inventories(
            authoritative.personal_skills,
            native_receipt.personal_skills_after,
        ):
            raise installer.InstallBlocked(
                "personal Codex skills changed during legacy migration"
            )
        if (
            native_receipt.canonical_contract != authoritative.canonical_contract
            or installer._canonical_activation_contract(plan.canonical_root)
            != authoritative.canonical_contract
        ):
            raise installer.NativeRecoveryRequired(
                "canonical SAMVIL activation contract changed before migration commit"
            )
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "native_verified",
            parent_descriptor=transaction_descriptor,
        )
        migration_backups = tuple(
            Path(str(record["backup"])) for record in journal["actions"]
        )
        receipt = installer.InstallReceipt(
            mode="migrate",
            canonical_root=plan.canonical_root,
            backup_paths=(*migration_backups, *native_receipt.backup_paths),
            commands=native_receipt.commands,
            personal_skills_before=authoritative.personal_skills,
            personal_skills_after=native_receipt.personal_skills_after,
            native_registry_before=native_receipt.native_registry_before,
            native_registry_after=native_receipt.native_registry_after,
            canonical_contract=authoritative.canonical_contract,
            legacy_plan_sha256=expected_plan_sha256,
            migration_transition_id=transition_id,
        )
        receipt = replace(
            receipt,
            migration_receipt_sha256=_receipt_digest(receipt.to_dict()),
        )
        journal["receipt"] = receipt.to_dict()
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "commit_decided",
            parent_descriptor=transaction_descriptor,
        )
        verify_boundary()
        _publish_json_at(
            transaction_descriptor,
            "receipt.json",
            {"schema_version": _RECEIPT_SCHEMA, "receipt": receipt.to_dict()},
            label="migration receipt",
            display_path=transaction / "receipt.json",
        )
        verify_boundary()
        _write_journal(
            journal_path,
            journal,
            "committed",
            parent_descriptor=transaction_descriptor,
        )
        return receipt
    except BaseException as exc:
        native_rollback_uncertain = isinstance(
            exc,
            installer.NativeRecoveryRequired,
        )
        if native_completed or native_rollback_uncertain:
            # Once native activation returned success, compensating only the
            # legacy filesystem objects could produce a duplicate native/direct
            # registration. Preserve the transaction and require an operator to
            # reconcile the native registry before any further mutation.
            try:
                verify_boundary()
                _write_journal(
                    journal_path,
                    journal,
                    "native_recovery_required",
                    parent_descriptor=transaction_descriptor,
                )
            except Exception as journal_exc:
                raise installer.InstallBlocked(
                    "native Codex activation proof failed and the recovery-required "
                    f"journal could not be persisted at {transaction}: {journal_exc}"
                ) from journal_exc
            if isinstance(exc, Exception):
                raise installer.InstallBlocked(
                    "native Codex activation completed but final migration proof failed; "
                    f"legacy backups were preserved at {transaction}: {exc}"
                ) from exc
            raise
        try:
            _rollback_actions(
                journal,
                journal_path,
                transaction_descriptor=transaction_descriptor,
                verify_boundary=verify_boundary,
            )
        except BaseException as rollback_exc:
            if isinstance(rollback_exc, Exception):
                raise rollback_exc from exc
            raise
        if isinstance(exc, installer.InstallBlocked):
            raise
        if isinstance(exc, Exception):
            raise installer.InstallBlocked(
                f"legacy migration failed; generated artifacts restored: {exc}"
            ) from exc
        raise
    finally:
        os.close(transaction_descriptor)


def execute_legacy_migration(
    plan: Any,
    *,
    codex_home: Path,
    command_runner: Any,
    registry_reader: Any | None,
    expected_plan_sha256: str | None,
) -> Any:
    """Apply a checked plan inside an explicit profile and return a durable receipt."""

    installer = _installer()
    if plan.blockers:
        raise installer.InstallBlocked("; ".join(plan.blockers))
    if fcntl is None:
        raise installer.InstallBlocked(
            "legacy migration requires POSIX profile locking support"
        )
    if (
        not plan.capability.plugin_commands_supported
        or not plan.capability.plugins_feature_enabled
        or plan.capability.blockers
    ):
        raise installer.InstallBlocked("Codex native plugin capability is unavailable")
    if (
        expected_plan_sha256 is None
        or _PLAN_SHA256.fullmatch(expected_plan_sha256) is None
    ):
        raise installer.InstallBlocked(
            "legacy migration requires a matching checked legacy plan SHA-256"
        )
    lexical_root = installer._lexical_absolute(codex_home)
    unsafe = installer._unsafe_directory_path_reason(
        lexical_root,
        label="Codex profile",
    )
    if unsafe is not None:
        raise installer.InstallBlocked(unsafe)
    root = lexical_root.resolve(strict=False)
    if root == Path(root.anchor):
        raise installer.InstallBlocked(
            f"isolated Codex root must not be a filesystem root: {root}"
        )
    if registry_reader is None:
        raise installer.InstallBlocked(
            "legacy Codex migration requires machine-readable native readback"
        )
    try:
        registry_preflight = installer._read_native_registry(
            registry_reader,
            {"CODEX_HOME": str(root), "HOME": str(root.parent)},
            mutation_started=False,
        )
    except installer.InstallBlocked as exc:
        raise installer.InstallBlocked(
            f"native Codex registry preflight failed before migration: {exc}"
        ) from exc
    if registry_preflight.evidence_kind != "codex_cli":
        raise installer.InstallBlocked(
            "legacy Codex migration requires Codex CLI registry evidence"
        )
    readiness = installer.validate_activation_readiness(plan.canonical_root)
    if not readiness["ready"]:
        raise installer.InstallBlocked("; ".join(readiness["blockers"]))
    try:
        installer.safe_child_directory(root, "backups", label="backups")
        installer.safe_child_directory(root, "skills", label="skills")
    except installer.RuntimeLayoutError as exc:
        raise installer.InstallBlocked(
            "Codex profile contains an unsafe migration path"
        ) from exc

    # Before the first write, prove that the checked plan still describes this
    # profile. Existing transaction state is handled under its existing lock.
    preflight = installer.build_legacy_migration_plan(
        repo_root=plan.canonical_root,
        codex_home=root,
    )
    migrations_root = root / "backups" / "legacy-migrations"
    if not migrations_root.exists():
        if preflight.blockers:
            raise installer.InstallBlocked("; ".join(preflight.blockers))
        if preflight.to_dict()["plan_sha256"] != expected_plan_sha256:
            raise installer.InstallBlocked(
                "legacy Codex profile changed after the checked plan; rerun the check"
            )

    try:
        root.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if not root.is_dir() or root.is_symlink():
            raise installer.InstallBlocked(f"unsafe Codex profile directory: {root}")
    with _profile_lock(root) as profile_identity:
        return _run_locked_migration(
            plan,
            root=root,
            command_runner=command_runner,
            registry_reader=registry_reader,
            expected_plan_sha256=expected_plan_sha256,
            profile_identity=profile_identity,
        )


__all__ = ["execute_legacy_migration"]
