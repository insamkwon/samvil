"""Read-only Codex ownership and installation planning primitives.

Mutation is intentionally out of scope for this module's first contract.  The
planner produces deterministic, JSON-serializable evidence so a later executor
can refuse ambiguous user-owned state before changing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib
import yaml

from .runtime_layout import RuntimeLayoutError, safe_child_directory
from .ssot_io import atomic_write_text

_FRONTMATTER_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEGACY_AGENTS_TEMPLATE_SHA256 = frozenset(
    {
        # Exact AGENTS.md templates that the retired global installer shipped.
        # Absolute SAMVIL_ROOT prefixes are normalized before comparison.
        # 2d81cdd9fba610cafe4e886e9b55b3e6672af799
        "714ecaa522f196ad7960d531438a8c7958762c0b18cb88f6cf994366de02c9d2",
        # 980b4ee9d67e617df9f5ad21fe15757a3f11e71e
        "459c1fd5c2c736318f9753e986d3a385bb3c4258da0b61fafc23dc145b8a610a",
        # 58e4ff055a7c81bbfa3334f8c88e96e896259b65
        "0d2f6d917fa084c090e42654cdd7e2cd4b6fce8a0cb02d5cf8807a1fd15a047a",
        # 56d8d61d166227da0c11c2c9ffe81c3ce74c0f2b and current template
        "412d5167f038815621ec8135299d5a30a1e5db99cecdead2b690b2338581776f",
    }
)
_LEGACY_AGENTS_ABSOLUTE_ROOT = re.compile(
    r"(?P<root>/[^\n`|]*?)/(?=(?:references|scripts)/)"
)


def _json_object(raw: str, label: str, blockers: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        blockers.append(f"invalid {label} JSON")
        return {}
    if not isinstance(value, dict):
        blockers.append(f"{label} JSON must be an object")
        return {}
    return value


@dataclass(frozen=True)
class CodexCapabilityProbe:
    plugin_commands_supported: bool
    plugins_feature_enabled: bool
    marketplaces: tuple[dict[str, Any], ...] = ()
    plugins: tuple[dict[str, Any], ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_commands_supported": self.plugin_commands_supported,
            "plugins_feature_enabled": self.plugins_feature_enabled,
            "marketplaces": list(self.marketplaces),
            "plugins": list(self.plugins),
            "blockers": list(self.blockers),
        }


def parse_capability_probe(
    *,
    help_output: str,
    marketplace_output: str,
    plugin_output: str,
    feature_output: str,
) -> CodexCapabilityProbe:
    """Parse capability evidence without treating a version string as proof."""

    blockers: list[str] = []
    marketplace = _json_object(marketplace_output, "marketplace", blockers)
    plugins = _json_object(plugin_output, "plugin", blockers)
    features = _json_object(feature_output, "feature", blockers)
    marketplaces = marketplace.get("marketplaces", [])
    plugin_entries = plugins.get("plugins", [])
    feature_flags = features.get("features", {})
    if not isinstance(marketplaces, list):
        blockers.append("marketplaces must be a list")
        marketplaces = []
    if not isinstance(plugin_entries, list):
        blockers.append("plugins must be a list")
        plugin_entries = []
    if not isinstance(feature_flags, dict):
        blockers.append("features must be an object")
        feature_flags = {}

    command_text = help_output.lower()
    command_ready = all(
        token in command_text for token in ("plugin", "marketplace", "--json")
    )
    plugins_ready = (
        feature_flags.get("plugins") is True
        and feature_flags.get("mcp_servers") is True
    )
    if not command_ready:
        blockers.append("Codex plugin JSON commands are unavailable")
    if not plugins_ready:
        blockers.append("Codex plugin/MCP features are unavailable")

    return CodexCapabilityProbe(
        plugin_commands_supported=command_ready,
        plugins_feature_enabled=plugins_ready,
        marketplaces=tuple(item for item in marketplaces if isinstance(item, dict)),
        plugins=tuple(item for item in plugin_entries if isinstance(item, dict)),
        blockers=tuple(blockers),
    )


def validate_marketplace_root(
    root: Path,
    *,
    user_home: Path,
    codex_skills_root: Path,
) -> Path:
    """Return a canonical root or reject user-owned/unsafe Codex paths."""

    resolved = Path(root).expanduser().resolve(strict=False)
    skills = Path(codex_skills_root).expanduser().resolve(strict=False)
    codex_root = skills.parent
    filesystem_root = Path(resolved.anchor)

    unsafe = (
        resolved == filesystem_root
        or resolved in codex_root.parents
        or resolved == codex_root
        or codex_root in resolved.parents
        or skills in resolved.parents
    )
    if unsafe:
        raise ValueError(f"unsafe Codex marketplace root: {resolved}")
    return resolved


def _frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    parsed_name: object
    if lines and lines[0].strip() == "---":
        try:
            closing_index = next(
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            )
        except StopIteration as exc:
            raise ValueError(f"skill frontmatter is not closed: {path}") from exc
        try:
            # Skill names are identifiers, not YAML booleans/numbers. The base
            # loader preserves legacy unquoted values such as ``on``, ``null``
            # and ``123`` as source strings while parsing the mapping shape.
            frontmatter = (
                yaml.load(
                    "\n".join(lines[1:closing_index]),
                    Loader=yaml.BaseLoader,
                )
                or {}
            )
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid skill frontmatter: {path}") from exc
        if not isinstance(frontmatter, dict):
            raise ValueError(f"skill frontmatter must be a mapping: {path}")
        parsed_name = frontmatter.get("name", path.parent.name)
    else:
        match = _FRONTMATTER_NAME.search(text)
        raw_name = match.group(1).strip() if match else path.parent.name
        try:
            parsed_name = yaml.load(raw_name, Loader=yaml.BaseLoader)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid skill frontmatter name: {path}") from exc
    if not isinstance(parsed_name, str) or not parsed_name.strip():
        raise ValueError(f"skill frontmatter name must be a non-empty string: {path}")
    return parsed_name.strip()


def _skill_tree_hash(skill_root: Path) -> str:
    """Hash every owned path with unambiguous type/content framing.

    The digest is evidence for ownership classification, so a file's bytes must
    not be allowed to impersonate the metadata of a following entry.  Every
    path, mode, entry type, symlink target, and regular-file length is framed
    before its value is added.  Callers perform the no-link tree walk before
    invoking this helper; a later executor still rechecks the tree before any
    mutation.
    """
    digest = hashlib.sha256()
    digest.update(b"samvil-skill-tree-hash-v2\0")
    digest.update(stat.S_IMODE(skill_root.lstat().st_mode).to_bytes(4, "big"))
    for path in sorted(
        skill_root.rglob("*"),
        key=lambda item: item.relative_to(skill_root).as_posix(),
    ):
        relative = path.relative_to(skill_root).as_posix().encode("utf-8")
        digest.update(b"E")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        mode = stat.S_IMODE(path.lstat().st_mode)
        digest.update(mode.to_bytes(4, "big"))
        if path.is_symlink():
            digest.update(b"L")
            target = os.readlink(path).encode("utf-8")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
        elif path.is_dir():
            digest.update(b"D")
        elif path.is_file():
            digest.update(b"F")
            content = path.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        else:
            digest.update(b"S")
    return digest.hexdigest()


@dataclass(frozen=True)
class SkillInventoryEntry:
    path: Path
    name: str
    content_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": str(self.path),
            "name": self.name,
            "content_hash": self.content_hash,
        }


def inventory_personal_skills(skills_root: Path) -> tuple[SkillInventoryEntry, ...]:
    root = _lexical_absolute(Path(skills_root).expanduser())
    if (
        _unsafe_directory_path_reason(root, label="personal skills") is not None
        or root.is_symlink()
        or not root.is_dir()
    ):
        return ()
    entries: list[SkillInventoryEntry] = []
    for skill_root in sorted(root.iterdir()):
        skill_file = skill_root / "SKILL.md"
        if (
            not skill_root.is_symlink()
            and skill_root.is_dir()
            and not skill_file.is_symlink()
            and skill_file.is_file()
        ):
            entries.append(
                SkillInventoryEntry(
                    path=skill_root,
                    name=_frontmatter_name(skill_file),
                    content_hash=_skill_tree_hash(skill_root),
                )
            )
    return tuple(entries)


def _unsafe_personal_skill_links(skills_root: Path) -> tuple[Path, ...]:
    """Return lexical skill entries that could escape the isolated root."""
    root = Path(skills_root)
    if not root.is_dir() or root.is_symlink():
        return ()
    unsafe: list[Path] = []
    for skill_root in sorted(root.iterdir()):
        contains_symlink = skill_root.is_symlink()
        if skill_root.is_dir() and not contains_symlink:
            for current_root, directory_names, file_names in os.walk(
                skill_root, followlinks=False
            ):
                current = Path(current_root)
                if any(
                    (current / name).is_symlink()
                    for name in (*directory_names, *file_names)
                ):
                    contains_symlink = True
                    break
        if contains_symlink:
            unsafe.append(skill_root)
    return tuple(unsafe)


def compare_skill_inventories(
    before: tuple[SkillInventoryEntry, ...],
    after: tuple[SkillInventoryEntry, ...],
) -> bool:
    def normalized(
        items: tuple[SkillInventoryEntry, ...],
    ) -> tuple[tuple[str, str, str], ...]:
        # The path is part of the preservation contract.  Comparing only the
        # frontmatter name and digest would let an executor delete a personal
        # skill and recreate the same bytes under a different directory while
        # reporting an unchanged inventory.
        return tuple(
            sorted((str(item.path), item.name, item.content_hash) for item in items)
        )

    return normalized(before) == normalized(after)


@dataclass(frozen=True)
class LegacyOwnership:
    path: Path
    classification: str
    content_hash: str | None = None
    blocks_mutation: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(self.path)
        return result


def classify_legacy_skill(path: Path, canonical_path: Path) -> LegacyOwnership:
    candidate_file = _lexical_absolute(Path(path))
    canonical_file = _lexical_absolute(Path(canonical_path))
    unsafe_parent = _unsafe_directory_path_reason(
        candidate_file.parent,
        label="legacy skill",
    )
    if unsafe_parent is not None or candidate_file.is_symlink():
        return LegacyOwnership(
            candidate_file,
            "user_modified",
            blocks_mutation=True,
            reason=unsafe_parent or "legacy skill path is a symbolic link",
        )
    if not candidate_file.exists():
        return LegacyOwnership(candidate_file, "absent", reason="path does not exist")
    try:
        candidate_metadata = candidate_file.stat(follow_symlinks=False)
    except OSError as exc:
        return LegacyOwnership(
            candidate_file,
            "user_modified",
            blocks_mutation=True,
            reason=f"legacy skill candidate cannot be inspected safely: {exc}",
        )
    if not stat.S_ISREG(candidate_metadata.st_mode) or candidate_metadata.st_nlink != 1:
        return LegacyOwnership(
            candidate_file,
            "user_modified",
            blocks_mutation=True,
            reason="legacy skill candidate is not an independent regular file",
        )
    if candidate_file.name == "SKILL.md" and canonical_file.name == "SKILL.md":
        artifact = _legacy_skill_artifact(candidate_file.parent, canonical_file.parent)
        return LegacyOwnership(
            candidate_file,
            artifact.classification,
            artifact.content_hash,
            artifact.blocks_mutation,
            artifact.reason,
        )
    try:
        candidate_bytes = candidate_file.read_bytes()
        canonical_bytes = (
            canonical_file.read_bytes() if canonical_file.is_file() else None
        )
    except (OSError, UnicodeError) as exc:
        return LegacyOwnership(
            candidate_file,
            "user_modified",
            blocks_mutation=True,
            reason=f"legacy skill candidate cannot be read safely: {exc}",
        )
    digest = _bytes_sha256(candidate_bytes)
    if canonical_bytes is not None and candidate_bytes == canonical_bytes:
        return LegacyOwnership(
            candidate_file,
            "generated_legacy",
            digest,
            False,
            "byte-identical canonical copy",
        )
    return LegacyOwnership(
        candidate_file,
        "user_modified",
        digest,
        True,
        "content differs from canonical copy",
    )


def classify_generated_file(path: Path, expected_content: str) -> LegacyOwnership:
    candidate = _lexical_absolute(Path(path))
    unsafe_parent = _unsafe_directory_path_reason(
        candidate.parent,
        label="generated file",
    )
    if unsafe_parent is not None or candidate.is_symlink():
        return LegacyOwnership(
            candidate,
            "user_modified",
            blocks_mutation=True,
            reason=unsafe_parent or "generated-file candidate is a symbolic link",
        )
    if not candidate.exists():
        return LegacyOwnership(candidate, "absent", reason="path does not exist")
    if not candidate.is_file() or candidate.stat(follow_symlinks=False).st_nlink != 1:
        return LegacyOwnership(
            candidate,
            "user_modified",
            blocks_mutation=True,
            reason="generated-file candidate is not an independent regular file",
        )
    try:
        content = candidate.read_bytes()
        digest = _bytes_sha256(content)
        text = content.decode("utf-8")
    except UnicodeError:
        return LegacyOwnership(
            candidate,
            "user_modified",
            digest,
            True,
            "generated file is not valid UTF-8",
        )
    except OSError as exc:
        return LegacyOwnership(
            candidate,
            "user_modified",
            None,
            True,
            f"generated file cannot be read safely: {exc}",
        )
    if text == expected_content:
        return LegacyOwnership(
            candidate,
            "generated_legacy",
            digest,
            False,
            "known generated content",
        )
    return LegacyOwnership(
        candidate, "user_modified", digest, True, "content is ambiguous"
    )


@dataclass(frozen=True)
class MigrationAction:
    kind: str
    path: Path
    reason: str
    artifact_kind: str | None = None
    expected_hash: str | None = None
    expected_device: int | None = None
    expected_inode: int | None = None
    expected_mode: int | None = None
    expected_size: int | None = None
    expected_nlink: int | None = None
    expected_uid: int | None = None
    expected_ctime_ns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "path": str(self.path),
            "reason": self.reason,
        }
        if self.artifact_kind is not None:
            result["artifact_kind"] = self.artifact_kind
        if self.expected_hash is not None:
            result["expected_hash"] = self.expected_hash
        if self.expected_device is not None:
            result["expected_device"] = self.expected_device
        if self.expected_inode is not None:
            result["expected_inode"] = self.expected_inode
        if self.expected_mode is not None:
            result["expected_mode"] = self.expected_mode
        if self.expected_size is not None:
            result["expected_size"] = self.expected_size
        if self.expected_nlink is not None:
            result["expected_nlink"] = self.expected_nlink
        if self.expected_uid is not None:
            result["expected_uid"] = self.expected_uid
        if self.expected_ctime_ns is not None:
            result["expected_ctime_ns"] = self.expected_ctime_ns
        return result


@dataclass(frozen=True)
class LegacyArtifact:
    artifact_kind: str
    path: Path
    classification: str
    content_hash: str | None
    expected_hash: str | None
    blocks_mutation: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "path": str(self.path),
            "classification": self.classification,
            "content_hash": self.content_hash,
            "expected_hash": self.expected_hash,
            "blocks_mutation": self.blocks_mutation,
            "reason": self.reason,
        }


def _artifact(
    kind: str,
    path: Path,
    reason: str,
    *,
    content_hash: str | None = None,
    expected_hash: str | None = None,
) -> LegacyArtifact:
    return LegacyArtifact(
        kind,
        path,
        "user_modified",
        content_hash,
        expected_hash,
        True,
        reason,
    )


@dataclass(frozen=True)
class LegacyMigrationPlan:
    canonical_root: Path
    codex_home: Path
    canonical_contract: tuple[tuple[str, str], ...] = ()
    native_registry_contract: tuple[tuple[str, str], ...] = ()
    native_registry_actions: tuple[str, ...] = ()
    personal_skills: tuple[SkillInventoryEntry, ...] = ()
    artifacts: tuple[LegacyArtifact, ...] = ()
    actions: tuple[MigrationAction, ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": "migration_dry_run",
            "canonical_root": str(self.canonical_root),
            "codex_home": str(self.codex_home),
            "canonical_contract": dict(sorted(self.canonical_contract)),
            "native_registry_contract": dict(sorted(self.native_registry_contract)),
            "native_registry_actions": list(self.native_registry_actions),
            "personal_skills": [entry.to_dict() for entry in self.personal_skills],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "actions": [action.to_dict() for action in self.actions],
            "blockers": list(self.blockers),
            "ready": not self.blockers,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
        return payload


@dataclass(frozen=True)
class CodexInstallPlan:
    canonical_root: Path
    capability: CodexCapabilityProbe
    personal_skills: tuple[SkillInventoryEntry, ...] = ()
    actions: tuple[MigrationAction, ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_root": str(self.canonical_root),
            "capability": self.capability.to_dict(),
            "personal_skills": [entry.to_dict() for entry in self.personal_skills],
            "actions": [action.to_dict() for action in self.actions],
            "blockers": list(self.blockers),
        }


class InstallBlocked(RuntimeError):
    """Raised when a plan contains an ambiguous or unsafe mutation."""


class NativeRecoveryRequired(InstallBlocked):
    """Raised after a native Codex mutation has an uncertain final outcome."""


@dataclass(frozen=True)
class NativeRegistrySnapshot:
    """Stable projection of Codex registry state and its full-state fingerprint."""

    evidence_kind: str
    marketplaces: tuple[str, ...]
    plugins: tuple[str, ...]
    marketplace_output_sha256: str | None = None
    plugin_output_sha256: str | None = None
    unrelated_fingerprint: str | None = None

    @property
    def fingerprint(self) -> str:
        payload = {
            "marketplaces": list(self.marketplaces),
            "plugins": list(self.plugins),
            "unrelated_fingerprint": self.unrelated_fingerprint,
        }
        return _bytes_sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence_kind": self.evidence_kind,
            "marketplaces": [json.loads(item) for item in self.marketplaces],
            "plugins": [json.loads(item) for item in self.plugins],
            "fingerprint": self.fingerprint,
        }
        if self.marketplace_output_sha256 is not None:
            payload["marketplace_output_sha256"] = self.marketplace_output_sha256
        if self.plugin_output_sha256 is not None:
            payload["plugin_output_sha256"] = self.plugin_output_sha256
        if self.unrelated_fingerprint is not None:
            payload["unrelated_fingerprint"] = self.unrelated_fingerprint
        return payload


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _unsafe_directory_path_reason(path: Path, *, label: str) -> str | None:
    """Reject existing symlink or non-directory components without resolving them."""

    candidate = _lexical_absolute(path)
    if candidate == Path(candidate.anchor):
        return f"{label} root must not be a filesystem root"
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            # Once a component is absent no deeper component can exist yet. A new
            # profile path is safe to inventory because dry-run never creates it.
            return None
        except OSError as exc:
            return f"{label} path cannot be inspected safely at {current}: {exc}"
        if stat.S_ISLNK(metadata.st_mode):
            if current == candidate:
                return f"{label} root is a symbolic link"
            return f"{label} path contains symbolic-link ancestor: {current}"
        if not stat.S_ISDIR(metadata.st_mode):
            if current == candidate:
                return f"{label} root is not a directory"
            return f"{label} path contains non-directory ancestor: {current}"
    return None


def _bytes_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_text_newlines(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _path_identity(path: Path) -> tuple[int, int, int, int, int, int, int] | None:
    """Return the lstat identity needed to revalidate a migration source."""

    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError):
        return None
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(stat.S_IMODE(metadata.st_mode)),
        int(metadata.st_size),
        int(metadata.st_nlink),
        int(metadata.st_uid),
        int(metadata.st_ctime_ns),
    )


def _canonical_activation_contract(root: Path) -> tuple[tuple[str, str], ...]:
    """Seal the native plugin files whose contents authorize activation."""

    canonical = Path(root).expanduser().resolve(strict=False)
    contract: list[tuple[str, str]] = []
    for relative in (
        ".codex-plugin/plugin.json",
        ".codex-mcp.json",
        "scripts/start-codex-mcp.sh",
    ):
        path = canonical / relative
        try:
            metadata = path.lstat()
            digest = (
                _bytes_sha256(path.read_bytes())
                if stat.S_ISREG(metadata.st_mode)
                and not stat.S_ISLNK(metadata.st_mode)
                and metadata.st_nlink == 1
                else "unsafe"
            )
        except OSError:
            digest = "missing"
        contract.append((relative, digest))
    for name in ("resume", "run", "status"):
        relative = f"codex/skills/{name}"
        path = canonical / relative
        try:
            if not path.exists() and not path.is_symlink():
                digest = "missing"
            else:
                unsafe = _unsafe_tree_reason(path)
                digest = _skill_tree_hash(path) if unsafe is None else "unsafe"
        except OSError:
            digest = "missing"
        contract.append((relative, digest))
    return tuple(contract)


def _independent_regular_file_reason(path: Path, *, label: str) -> str | None:
    """Require an activation file that cannot alias mutable external content."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        return f"{label} is missing or unreadable: {exc}"
    if stat.S_ISLNK(metadata.st_mode):
        return f"{label} is unsafe because it is a symbolic link"
    if not stat.S_ISREG(metadata.st_mode):
        return f"{label} is unsafe because it is not a regular file"
    if metadata.st_nlink != 1:
        return f"{label} is unsafe because it is hard-linked"
    return None


def _canonical_entry_json(entry: dict[str, Any]) -> str:
    return json.dumps(
        entry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _related_registry_name(value: object) -> bool:
    return isinstance(value, str) and _is_samvil_prefixed(value)


def _legacy_marketplace_source_is_owned(
    source: Path,
    *,
    canonical_root: Path,
    codex_home: Path,
) -> bool:
    """Recognize only marketplace roots produced by prior SAMVIL installers."""

    if source not in {canonical_root, codex_home.parent}:
        return False
    manifest = source / ".claude-plugin" / "marketplace.json"
    try:
        metadata = manifest.lstat()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not isinstance(payload, dict)
        or payload.get("name") != "samvil"
    ):
        return False
    plugins = payload.get("plugins")
    return (
        isinstance(plugins, list)
        and len(plugins) == 1
        and isinstance(plugins[0], dict)
        and plugins[0].get("name") == "samvil"
        and plugins[0].get("source") in {"./", "."}
    )


def _native_registry_profile_contract(
    config_path: Path,
    *,
    canonical_root: Path,
    codex_home: Path,
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...], tuple[str, ...]]:
    """Seal and classify existing SAMVIL registry entries without mutation."""

    contract: list[tuple[str, str]] = []
    actions: list[str] = []
    blockers: list[str] = []
    if not config_path.exists():
        return (("config_sha256", "missing"),), (), ()
    if config_path.is_symlink() or not config_path.is_file():
        return (
            (("config_sha256", "unsafe"),),
            (),
            (f"Codex registry config is unsafe: {config_path}",),
        )
    try:
        content = config_path.read_bytes()
        parsed = tomllib.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return (
            (("config_sha256", "invalid"),),
            (),
            (f"invalid Codex registry config: {config_path}: {exc}",),
        )
    contract.append(("config_sha256", _bytes_sha256(content)))
    marketplaces = parsed.get("marketplaces", {})
    plugins = parsed.get("plugins", {})
    if not isinstance(marketplaces, dict):
        blockers.append("Codex marketplaces registry must be a table")
        marketplaces = {}
    if not isinstance(plugins, dict):
        blockers.append("Codex plugins registry must be a table")
        plugins = {}

    legacy_marketplace_owned = False
    for name, raw_entry in sorted(marketplaces.items(), key=lambda item: str(item[0])):
        if not _related_registry_name(name):
            continue
        label = str(name)
        if not isinstance(raw_entry, dict):
            blockers.append(f"Codex marketplace entry is not a table: {label}")
            continue
        contract.append((f"marketplace:{label}", _canonical_entry_json(raw_entry)))
        source_value = raw_entry.get("source")
        source_type = raw_entry.get("source_type")
        if not isinstance(source_value, str) or not source_value:
            blockers.append(f"Codex marketplace source is missing: {label}")
            continue
        source_candidate = Path(source_value).expanduser()
        if not source_candidate.is_absolute() or source_type not in {None, "local"}:
            blockers.append(f"Codex marketplace source is ambiguous: {label}")
            continue
        source = source_candidate.resolve(strict=False)
        if label == "samvil":
            legacy_marketplace_owned = _legacy_marketplace_source_is_owned(
                source,
                canonical_root=canonical_root,
                codex_home=codex_home,
            )
            if not legacy_marketplace_owned:
                blockers.append(
                    "existing Codex marketplace 'samvil' is not a proven SAMVIL legacy registration"
                )
            else:
                actions.append("remove_marketplace:samvil")
        elif label == "samvil-codex":
            expected = codex_home / "marketplaces" / "samvil-codex"
            if source != expected or not expected.exists():
                blockers.append(
                    "existing Codex marketplace 'samvil-codex' does not use the owned wrapper"
                )
            else:
                try:
                    _codex_marketplace_wrapper(codex_home, canonical_root)
                except InstallBlocked as exc:
                    blockers.append(str(exc))
        else:
            blockers.append(f"reserved SAMVIL marketplace name is ambiguous: {label}")

    for plugin_id, raw_entry in sorted(plugins.items(), key=lambda item: str(item[0])):
        label = str(plugin_id)
        marketplace_name = label.rpartition("@")[2] if "@" in label else ""
        if not (
            _related_registry_name(label) or _related_registry_name(marketplace_name)
        ):
            continue
        if not isinstance(raw_entry, dict):
            blockers.append(f"Codex plugin entry is not a table: {label}")
            continue
        # During migration, legacy per-tool approval tables are rewritten into
        # the native plugin namespace before the CLI registers the plugin.  A
        # tools-only table is an intentional pending fragment, not a registry
        # entry that can be judged enabled/disabled yet.
        if label == "samvil@samvil-codex" and set(raw_entry) == {"tools"}:
            continue
        contract.append((f"plugin:{label}", _canonical_entry_json(raw_entry)))
        if label == "samvil@samvil":
            if not legacy_marketplace_owned:
                blockers.append(
                    "legacy Codex plugin has no proven SAMVIL marketplace registration"
                )
            elif raw_entry.get("enabled") is not True:
                blockers.append(
                    "disabled legacy SAMVIL plugin requires an explicit user decision"
                )
            else:
                actions.append("remove_plugin:samvil@samvil")
        elif label == "samvil@samvil-codex":
            if "samvil-codex" not in marketplaces:
                blockers.append(
                    "native SAMVIL plugin has no owned marketplace registration"
                )
            elif raw_entry.get("enabled") is not True:
                blockers.append(
                    "disabled native SAMVIL plugin requires an explicit user decision"
                )
        else:
            blockers.append(f"reserved SAMVIL plugin id is ambiguous: {label}")

    return tuple(contract), tuple(actions), tuple(blockers)


def _is_samvil_prefixed(name: str) -> bool:
    """Treat case/compatibility-equivalent SAMVIL names as one namespace."""

    return unicodedata.normalize("NFKC", name).casefold().startswith("samvil")


def _unsafe_tree_reason(root: Path) -> str | None:
    try:
        if root.is_symlink():
            return "legacy skill tree is a symbolic link"
        if not root.is_dir():
            return "legacy skill candidate is not a directory"

        def raise_walk_error(exc: OSError) -> None:
            raise exc

        for current_root, directory_names, file_names in os.walk(
            root,
            followlinks=False,
            onerror=raise_walk_error,
        ):
            current = Path(current_root)
            for name in (*directory_names, *file_names):
                candidate = current / name
                if candidate.is_symlink():
                    return f"legacy skill tree contains symbolic link: {candidate}"
                metadata = candidate.stat(follow_symlinks=False)
                if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
                    return f"legacy skill tree contains hard-linked file: {candidate}"
                if not (
                    stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
                ):
                    return f"legacy skill tree contains unsupported entry: {candidate}"
    except OSError as exc:
        return f"legacy skill tree cannot be inspected safely: {exc}"
    return None


def _canonical_link_skill_tree_matches(path: Path, canonical: Path) -> bool:
    """Recognize a legacy skill tree made only of exact canonical file links.

    Older local setups sometimes represented the generated skill files as links
    back into the checked-out SAMVIL repository.  Such a tree is safe to retire
    only when its complete lexical shape matches the canonical tree and every
    linked file points directly at its corresponding canonical file.  A link
    to another location, an extra entry, or a canonical link is ambiguous.
    """

    legacy = _lexical_absolute(path)
    source = _lexical_absolute(canonical)
    if (
        legacy.is_symlink()
        or not legacy.is_dir()
        or source.is_symlink()
        or not source.is_dir()
    ):
        return False

    def lexical_target(link: Path) -> Path:
        try:
            target = Path(os.readlink(link))
        except OSError as exc:
            raise ValueError(f"cannot read symbolic link: {link}") from exc
        if not target.is_absolute():
            target = link.parent / target
        return Path(os.path.abspath(os.fspath(target)))

    def matches(legacy_root: Path, source_root: Path) -> bool:
        try:
            legacy_entries = {
                entry.name: entry for entry in legacy_root.iterdir()
            }
            source_entries = {
                entry.name: entry for entry in source_root.iterdir()
            }
        except OSError:
            return False
        if set(legacy_entries) != set(source_entries):
            return False
        for name, source_entry in source_entries.items():
            legacy_entry = legacy_entries[name]
            try:
                source_metadata = source_entry.lstat()
                legacy_metadata = legacy_entry.lstat()
            except OSError:
                return False
            if stat.S_ISDIR(source_metadata.st_mode):
                if (
                    stat.S_ISLNK(legacy_metadata.st_mode)
                    or not stat.S_ISDIR(legacy_metadata.st_mode)
                    or not matches(legacy_entry, source_entry)
                ):
                    return False
                continue
            if not stat.S_ISREG(source_metadata.st_mode):
                return False
            if source_metadata.st_nlink != 1:
                return False
            if not stat.S_ISLNK(legacy_metadata.st_mode):
                return False
            try:
                target = lexical_target(legacy_entry)
            except ValueError:
                return False
            if target != _lexical_absolute(source_entry):
                return False
        return True

    return matches(legacy, source)


def _personal_skill_inventory_reason(candidate: Path) -> str | None:
    """Return a blocker when a personal skill cannot be hashed/read safely."""

    path = _lexical_absolute(candidate)
    if path.is_symlink():
        return "personal skill tree is a symbolic link"
    if not path.is_dir():
        return None
    unsafe = _unsafe_tree_reason(path)
    if unsafe is not None:
        return unsafe.replace("legacy skill", "personal skill")
    manifest = path / "SKILL.md"
    if manifest.is_symlink() or not manifest.is_file():
        return None
    try:
        declared_name = _frontmatter_name(manifest)
        _skill_tree_hash(path)
    except (OSError, UnicodeError, ValueError) as exc:
        return f"personal skill cannot be inventoried safely: {exc}"
    normalized_name = unicodedata.normalize("NFKC", declared_name).casefold()
    if normalized_name.startswith("samvil:"):
        return "personal skill claims the reserved SAMVIL namespace"
    return None


def _legacy_skill_artifact(candidate: Path, canonical: Path) -> LegacyArtifact:
    path = _lexical_absolute(candidate)
    unsafe_parent = _unsafe_directory_path_reason(path.parent, label="legacy skill")
    if unsafe_parent is not None:
        return _artifact("legacy_skill_tree", path, unsafe_parent)
    unsafe_reason = _unsafe_tree_reason(path)
    if unsafe_reason is not None:
        if (
            "symbolic link" in unsafe_reason
            and _canonical_link_skill_tree_matches(path, canonical)
        ):
            try:
                content_hash = _skill_tree_hash(path)
            except (OSError, UnicodeError) as exc:
                return _artifact(
                    "legacy_skill_link_tree",
                    path,
                    f"legacy skill link tree cannot be hashed safely: {exc}",
                )
            return LegacyArtifact(
                "legacy_skill_link_tree",
                path,
                "generated_legacy",
                content_hash,
                content_hash,
                False,
                "legacy skill tree links exactly to canonical source",
            )
        return _artifact("legacy_skill_tree", path, unsafe_reason)
    skill_manifest = path / "SKILL.md"
    if skill_manifest.is_symlink() or not skill_manifest.is_file():
        return _artifact(
            "legacy_skill_tree",
            path,
            "legacy skill tree has no regular non-symlink SKILL.md",
        )
    try:
        content_hash = _skill_tree_hash(path)
    except (OSError, UnicodeError) as exc:
        return _artifact(
            "legacy_skill_tree",
            path,
            f"legacy skill tree cannot be hashed safely: {exc}",
        )
    canonical_path = _lexical_absolute(canonical)
    if not canonical_path.is_dir():
        return LegacyArtifact(
            "legacy_skill_tree",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            "canonical source is unavailable for this samvil-prefixed skill",
        )
    canonical_unsafe = _unsafe_tree_reason(canonical_path)
    if canonical_unsafe is not None:
        return LegacyArtifact(
            "legacy_skill_tree",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            f"canonical source cannot establish provenance: {canonical_unsafe}",
        )
    canonical_manifest = canonical_path / "SKILL.md"
    if canonical_manifest.is_symlink() or not canonical_manifest.is_file():
        return LegacyArtifact(
            "legacy_skill_tree",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            "canonical source has no regular non-symlink SKILL.md",
        )
    try:
        expected_hash = _skill_tree_hash(canonical_path)
    except (OSError, UnicodeError) as exc:
        return LegacyArtifact(
            "legacy_skill_tree",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            f"canonical source cannot be hashed safely: {exc}",
        )
    if content_hash != expected_hash:
        return LegacyArtifact(
            "legacy_skill_tree",
            path,
            "user_modified",
            content_hash,
            expected_hash,
            True,
            "legacy skill tree differs from canonical source",
        )
    return LegacyArtifact(
        "legacy_skill_tree",
        path,
        "generated_legacy",
        content_hash,
        expected_hash,
        False,
        "legacy skill tree is byte-identical to canonical source",
    )


def _global_agents_artifact(path: Path) -> LegacyArtifact | None:
    candidate = _lexical_absolute(path)
    unsafe_parent = _unsafe_directory_path_reason(
        candidate.parent, label="global AGENTS"
    )
    if unsafe_parent is not None:
        return _artifact("global_agents", candidate, unsafe_parent)
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return _artifact(
            "global_agents",
            candidate,
            f"global_agents cannot be inspected safely: {exc}",
        )
    if stat.S_ISLNK(metadata.st_mode):
        return LegacyArtifact(
            "global_agents",
            candidate,
            "user_modified",
            None,
            None,
            True,
            "global_agents is a symbolic link",
        )
    if not stat.S_ISREG(metadata.st_mode):
        return LegacyArtifact(
            "global_agents",
            candidate,
            "user_modified",
            None,
            None,
            True,
            "global_agents is not a regular file",
        )
    try:
        content = candidate.read_bytes()
    except OSError as exc:
        return _artifact(
            "global_agents",
            candidate,
            f"global_agents cannot be read safely: {exc}",
        )
    content_hash = _bytes_sha256(content)
    if metadata.st_nlink != 1:
        return LegacyArtifact(
            "global_agents",
            candidate,
            "user_modified",
            content_hash,
            None,
            True,
            "global_agents is hard-linked",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return LegacyArtifact(
            "global_agents",
            candidate,
            "user_modified",
            content_hash,
            None,
            True,
            "global_agents is not valid UTF-8",
        )

    roots = tuple(
        sorted(
            {
                match.group("root")
                for match in _LEGACY_AGENTS_ABSOLUTE_ROOT.finditer(text)
            }
        )
    )
    if len(roots) > 1:
        normalized_hash = None
    else:
        normalized = text
        if roots:
            root = roots[0]
            normalized = normalized.replace(
                f"{root}/references/", "references/"
            ).replace(f"{root}/scripts/", "scripts/")
        normalized_hash = _bytes_sha256(normalized.encode("utf-8"))
    if normalized_hash not in _LEGACY_AGENTS_TEMPLATE_SHA256:
        return LegacyArtifact(
            "global_agents",
            candidate,
            "user_modified",
            content_hash,
            normalized_hash,
            True,
            "global_agents content is not an exact known generated template",
        )
    return LegacyArtifact(
        "global_agents",
        candidate,
        "generated_legacy",
        content_hash,
        normalized_hash,
        False,
        "global_agents matches an exact known generated template",
    )


def _direct_mcp_artifact(config_path: Path) -> LegacyArtifact | None:
    path = _lexical_absolute(config_path)
    unsafe_parent = _unsafe_directory_path_reason(path.parent, label="Codex config")
    if unsafe_parent is not None:
        return _artifact("direct_mcp_table", path, unsafe_parent)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return _artifact(
            "direct_mcp_table",
            path,
            f"Codex config cannot be inspected safely: {exc}",
        )
    if stat.S_ISLNK(metadata.st_mode):
        return LegacyArtifact(
            "direct_mcp_table",
            path,
            "user_modified",
            None,
            None,
            True,
            "Codex config containing legacy MCP state is a symbolic link",
        )
    if not stat.S_ISREG(metadata.st_mode):
        return LegacyArtifact(
            "direct_mcp_table",
            path,
            "user_modified",
            None,
            None,
            True,
            "Codex config is not a regular file",
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        return _artifact(
            "direct_mcp_table",
            path,
            f"Codex config cannot be read safely: {exc}",
        )
    content_hash = _bytes_sha256(content)
    if metadata.st_nlink != 1:
        return LegacyArtifact(
            "direct_mcp_table",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            "Codex config is hard-linked",
        )
    try:
        parsed = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return LegacyArtifact(
            "direct_mcp_table",
            path,
            "user_modified",
            content_hash,
            None,
            True,
            "Codex config is not valid UTF-8 TOML",
        )
    servers = parsed.get("mcp_servers")
    if not isinstance(servers, dict) or "samvil-mcp" not in servers:
        return None
    table = servers.get("samvil-mcp")
    # An orphaned nested table is not a valid Codex server definition.  It can
    # only be observed after an interrupted/manual edit, so leave it as an
    # explicit blocker instead of silently accepting an invalid config.
    if isinstance(table, dict) and set(table) == {"tools"}:
        return _artifact(
            "direct_mcp_table",
            path,
            "legacy MCP tool overrides have no server parent",
        )
    normalized_expected = {
        "command": "{{SAMVIL_ROOT}}/mcp/.venv/bin/python",
        "args": ["-m", "samvil_mcp.server"],
        "env": {},
    }
    expected_hash = _bytes_sha256(
        json.dumps(normalized_expected, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    command = table.get("command") if isinstance(table, dict) else None
    command_path = Path(command) if isinstance(command, str) else Path()
    command_has_generated_shape = (
        isinstance(command, str)
        and command_path.is_absolute()
        and ".." not in command_path.parts
        and len(command_path.parts) > 5
        and command_path.parts[-4:] == ("mcp", ".venv", "bin", "python")
    )
    table_has_generated_shape = (
        isinstance(table, dict)
        and set(table).issubset({"command", "args", "env", "tools"})
        and table.get("args") == ["-m", "samvil_mcp.server"]
        and ("env" not in table or table.get("env") == {})
        and command_has_generated_shape
    )
    exact_table_text = False
    if table_has_generated_shape:
        lines = content.decode("utf-8").splitlines()
        try:
            header_index = lines.index("[mcp_servers.samvil-mcp]")
        except ValueError:
            header_index = -1
        if header_index >= 0:
            end_index = len(lines)
            for index in range(header_index + 1, len(lines)):
                if lines[index].startswith("["):
                    end_index = index
                    break
            command_text = str(table["command"])
            block_lines = lines[header_index:end_index]
            while block_lines and not block_lines[-1]:
                block_lines.pop()
            assignments: dict[str, str] = {}
            for line in block_lines[1:]:
                stripped = line.strip()
                if not stripped or "=" not in stripped:
                    exact_table_text = False
                    break
                key, _, value = stripped.partition("=")
                key = key.strip()
                if key in assignments:
                    exact_table_text = False
                    break
                assignments[key] = value.strip()
            else:
                expected_assignments = {
                    "command": f'"{command_text}"',
                    "args": '["-m", "samvil_mcp.server"]',
                }
                if "env" in table:
                    expected_assignments["env"] = "{}"
                exact_table_text = (
                    set(assignments) == set(expected_assignments)
                    and assignments == expected_assignments
                )
    if not exact_table_text:
        return LegacyArtifact(
            "direct_mcp_table",
            path,
            "user_modified",
            content_hash,
            expected_hash,
            True,
            "legacy direct MCP table is not an exact installer-generated text block",
        )
    return LegacyArtifact(
        "direct_mcp_table",
        path,
        "generated_legacy",
        content_hash,
        expected_hash,
        False,
        "legacy direct MCP table has the exact installer-generated text block",
    )


def build_legacy_migration_plan(
    *,
    repo_root: Path,
    codex_home: Path,
) -> LegacyMigrationPlan:
    """Inventory legacy Codex artifacts without creating or changing any path."""

    canonical = Path(repo_root).expanduser().resolve(strict=False)
    supplied_profile = Path(codex_home).expanduser()
    profile = _lexical_absolute(supplied_profile)
    artifacts: list[LegacyArtifact] = []
    actions: list[MigrationAction] = []
    blockers: list[str] = []
    native_registry_contract: tuple[tuple[str, str], ...] = ()
    native_registry_actions: tuple[str, ...] = ()

    profile_unsafe_reason = _unsafe_directory_path_reason(
        profile,
        label="Codex profile",
    )
    profile_path_is_unsafe = profile_unsafe_reason is not None
    if profile_unsafe_reason is not None:
        artifacts.append(
            _artifact(
                "codex_profile_root",
                profile,
                profile_unsafe_reason,
            )
        )

    try:
        validate_marketplace_root(
            canonical,
            user_home=profile.parent,
            codex_skills_root=profile / "skills",
        )
    except ValueError as exc:
        blockers.append(str(exc))

    skills_root = profile / "skills"
    if not profile_path_is_unsafe and skills_root.is_symlink():
        artifacts.append(
            LegacyArtifact(
                "legacy_skill_root",
                _lexical_absolute(skills_root),
                "user_modified",
                None,
                None,
                True,
                "Codex skills root is a symbolic link",
            )
        )
    elif (
        not profile_path_is_unsafe and skills_root.exists() and not skills_root.is_dir()
    ):
        artifacts.append(
            _artifact(
                "legacy_skill_root",
                _lexical_absolute(skills_root),
                "Codex skills root is not a directory",
            )
        )
    elif not profile_path_is_unsafe and skills_root.is_dir():
        try:
            entries = tuple(skills_root.iterdir())
        except OSError as exc:
            artifacts.append(
                _artifact(
                    "legacy_skill_root",
                    _lexical_absolute(skills_root),
                    f"Codex skills root cannot be inventoried safely: {exc}",
                )
            )
        else:
            for candidate in sorted(
                (entry for entry in entries if _is_samvil_prefixed(entry.name)),
                key=lambda entry: entry.name,
            ):
                artifacts.append(
                    _legacy_skill_artifact(
                        candidate, canonical / "skills" / candidate.name
                    )
                )
            for candidate in sorted(
                (entry for entry in entries if not _is_samvil_prefixed(entry.name)),
                key=lambda entry: entry.name,
            ):
                unsafe_personal_reason = _personal_skill_inventory_reason(candidate)
                if unsafe_personal_reason is not None:
                    artifacts.append(
                        _artifact(
                            "personal_skill_tree",
                            _lexical_absolute(candidate),
                            unsafe_personal_reason.replace(
                                "legacy skill", "personal skill"
                            ),
                        )
                    )

    if not profile_path_is_unsafe:
        agents_artifact = _global_agents_artifact(profile / "AGENTS.md")
        if agents_artifact is not None:
            artifacts.append(agents_artifact)

        mcp_artifact = _direct_mcp_artifact(profile / "config.toml")
        if mcp_artifact is not None:
            artifacts.append(mcp_artifact)
        (
            native_registry_contract,
            native_registry_actions,
            native_registry_blockers,
        ) = _native_registry_profile_contract(
            profile / "config.toml",
            canonical_root=canonical,
            codex_home=profile,
        )
        blockers.extend(native_registry_blockers)

    for artifact in artifacts:
        if artifact.blocks_mutation:
            blockers.append(f"{artifact.path}: {artifact.reason}")
            continue
        if artifact.classification != "generated_legacy":
            continue
        action_kind = (
            "remove_generated_mcp_table"
            if artifact.artifact_kind == "direct_mcp_table"
            else "migrate_generated"
        )
        identity = _path_identity(artifact.path)
        if identity is None:
            blockers.append(
                f"{artifact.path}: generated artifact disappeared during planning"
            )
            continue
        actions.append(
            MigrationAction(
                action_kind,
                artifact.path,
                artifact.reason,
                artifact.artifact_kind,
                artifact.content_hash,
                identity[0],
                identity[1],
                identity[2],
                identity[3],
                identity[4],
                identity[5],
                identity[6],
            )
        )

    personal = ()
    if (
        not profile_path_is_unsafe
        and skills_root.is_dir()
        and not skills_root.is_symlink()
    ):
        try:
            generated_legacy_paths = {
                artifact.path
                for artifact in artifacts
                if artifact.artifact_kind == "legacy_skill_tree"
                and artifact.classification == "generated_legacy"
            }
            personal = tuple(
                entry
                for entry in inventory_personal_skills(skills_root)
                if entry.path not in generated_legacy_paths
            )
        except (OSError, UnicodeError, ValueError) as exc:
            blockers.append(f"personal skill inventory failed safely: {exc}")
    canonical_contract = _canonical_activation_contract(canonical)
    for relative, digest in canonical_contract:
        if digest == "unsafe":
            blockers.append(f"canonical activation surface is unsafe: {relative}")

    return LegacyMigrationPlan(
        canonical_root=canonical,
        codex_home=profile,
        canonical_contract=canonical_contract,
        native_registry_contract=native_registry_contract,
        native_registry_actions=native_registry_actions,
        personal_skills=personal,
        artifacts=tuple(artifacts),
        actions=tuple(actions),
        blockers=tuple(blockers),
    )


def _legacy_install_blockers(plan: LegacyMigrationPlan) -> list[str]:
    blockers = list(plan.blockers)
    if plan.actions or plan.native_registry_actions:
        action_kinds = ", ".join(
            sorted(
                {
                    *(action.kind for action in plan.actions),
                    *plan.native_registry_actions,
                }
            )
        )
        blockers.append(
            f"legacy migration required before native installation: {action_kinds}"
        )
    return blockers


def validate_activation_readiness(repo_root: Path) -> dict[str, Any]:
    """Prove the repository is complete enough for actual-profile activation."""
    root = Path(repo_root).expanduser().resolve(strict=False)
    blockers: list[str] = []
    manifest = root / ".codex-plugin" / "plugin.json"
    launcher = root / ".codex-mcp.json"
    skills_root = root / "codex" / "skills"
    for path, label in (
        (manifest, "Codex plugin manifest"),
        (launcher, "relative Codex MCP launcher"),
    ):
        reason = _independent_regular_file_reason(path, label=label)
        if reason is not None:
            blockers.append(reason)
    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        launcher_data = json.loads(launcher.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest_data = {}
        launcher_data = {}
        blockers.append("Codex manifest or launcher is invalid JSON")
    if not isinstance(manifest_data, dict):
        manifest_data = {}
        blockers.append("Codex plugin manifest JSON must be an object")
    if not isinstance(launcher_data, dict):
        launcher_data = {}
        blockers.append("relative Codex MCP launcher JSON must be an object")
    skills_reason = _unsafe_tree_reason(skills_root)
    if skills_reason is not None:
        blockers.append(f"Codex public skill surface is unsafe: {skills_reason}")
        public_skills = []
    else:
        public_skills = sorted(
            path.name for path in skills_root.iterdir() if path.is_dir()
        )
    if public_skills != ["resume", "run", "status"]:
        blockers.append("Codex public skill surface must be exactly run/resume/status")
    for name in ("run", "resume", "status"):
        skill_manifest = skills_root / name / "SKILL.md"
        reason = _independent_regular_file_reason(
            skill_manifest,
            label=f"public Codex skill {name}",
        )
        if reason is not None:
            if not skill_manifest.exists() and not skill_manifest.is_symlink():
                blockers.append(f"missing public Codex skill: {name}")
            blockers.append(reason)
    if (
        manifest_data.get("skills") != "./codex/skills/"
        or manifest_data.get("mcpServers") != "./.codex-mcp.json"
    ):
        blockers.append("Codex manifest does not use relative public surfaces")
    mcp_servers = launcher_data.get("mcpServers")
    if "mcpServers" in launcher_data and not isinstance(mcp_servers, dict):
        mcp_servers = {}
        blockers.append("Codex MCP launcher mcpServers must be an object")
    server = (mcp_servers or {}).get("samvil-mcp")
    launcher_script = root / "scripts" / "start-codex-mcp.sh"
    launcher_script_reason = _independent_regular_file_reason(
        launcher_script,
        label="Codex MCP package launcher",
    )
    if (
        not isinstance(server, dict)
        or server.get("command") != "bash"
        or server.get("args") != ["./scripts/start-codex-mcp.sh"]
        or launcher_script_reason is not None
    ):
        blockers.append("Codex MCP launcher is not the relative package launcher")
    if launcher_script_reason is not None:
        blockers.append(launcher_script_reason)
    return {
        "ready": not blockers,
        "blockers": blockers,
        "public_skills": public_skills,
        "manifest": str(manifest),
        "launcher": str(launcher),
    }


def _capability_probe_runner(command: tuple[str, ...], env: dict[str, str]) -> Any:
    return subprocess.run(
        command,
        env=_codex_subprocess_environment(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _codex_subprocess_environment(env: dict[str, str]) -> dict[str, str]:
    inherited = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CODEX_HOME", "CODEX_CONFIG", "CODEX_PROFILE", "XDG_CONFIG_HOME"}
    }
    return {**inherited, **env}


def validate_cli_environment(
    codex_home: Path,
    *,
    which: Any = shutil.which,
    command_runner: Any = _capability_probe_runner,
) -> dict[str, Any]:
    """Read-only proof that native Codex and the relative MCP launcher can run."""
    lexical_root = _lexical_absolute(codex_home)
    unsafe_profile_reason = _unsafe_directory_path_reason(
        lexical_root,
        label="Codex profile",
    )
    if unsafe_profile_reason is not None:
        return {
            "ready": False,
            "blockers": [unsafe_profile_reason],
            "codex_binary": "",
            "uvx_binary": "",
            "plugin_commands_supported": False,
        }
    root = lexical_root.resolve(strict=False)
    blockers: list[str] = []
    codex_binary = which("codex") or ""
    uvx_binary = which("uvx") or ""
    if not codex_binary:
        blockers.append("codex binary is unavailable")
    if not uvx_binary:
        blockers.append("uvx binary is unavailable")
    plugin_commands_supported = False
    if codex_binary:
        result = command_runner(
            (str(codex_binary), "plugin", "--help"),
            {"CODEX_HOME": str(root), "HOME": str(root.parent)},
        )
        output = (
            f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}".lower()
        )
        plugin_commands_supported = getattr(result, "returncode", 1) == 0 and all(
            token in output for token in ("add", "marketplace", "list", "remove")
        )
        if not plugin_commands_supported:
            blockers.append("Codex native plugin commands are unavailable")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "codex_binary": str(codex_binary),
        "uvx_binary": str(uvx_binary),
        "plugin_commands_supported": plugin_commands_supported,
    }


@dataclass(frozen=True)
class InstallReceipt:
    mode: str
    canonical_root: Path
    backup_paths: tuple[Path, ...]
    commands: tuple[tuple[str, ...], ...]
    personal_skills_before: tuple[SkillInventoryEntry, ...]
    personal_skills_after: tuple[SkillInventoryEntry, ...]
    native_registry_before: NativeRegistrySnapshot | None = None
    native_registry_after: NativeRegistrySnapshot | None = None
    canonical_contract: tuple[tuple[str, str], ...] = ()
    legacy_plan_sha256: str | None = None
    migration_transition_id: str | None = None
    migration_receipt_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "canonical_root": str(self.canonical_root),
            "backup_paths": [str(path) for path in self.backup_paths],
            "commands": [list(command) for command in self.commands],
            "personal_skills_before": [
                entry.to_dict() for entry in self.personal_skills_before
            ],
            "personal_skills_after": [
                entry.to_dict() for entry in self.personal_skills_after
            ],
            "personal_skills_unchanged": compare_skill_inventories(
                self.personal_skills_before, self.personal_skills_after
            ),
        }
        if self.native_registry_before is not None:
            payload["native_registry_before"] = self.native_registry_before.to_dict()
        if self.native_registry_after is not None:
            payload["native_registry_after"] = self.native_registry_after.to_dict()
        if self.canonical_contract:
            payload["canonical_contract"] = dict(sorted(self.canonical_contract))
        if self.legacy_plan_sha256 is not None:
            payload["legacy_plan_sha256"] = self.legacy_plan_sha256
        if self.migration_transition_id is not None:
            payload["migration_transition_id"] = self.migration_transition_id
        if self.migration_receipt_sha256 is not None:
            payload["migration_receipt_sha256"] = self.migration_receipt_sha256
        return payload


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as temporary:
        temporary.write(source.read_bytes())
        temporary.flush()
    Path(temporary.name).replace(destination)


def _configured_marketplace_root(config_path: Path, name: str) -> Path | None:
    if not config_path.exists():
        return None
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstallBlocked(f"invalid Codex config TOML: {config_path}") from exc
    marketplaces = parsed.get("marketplaces")
    if not isinstance(marketplaces, dict):
        return None
    entry = marketplaces.get(name)
    if not isinstance(entry, dict) or not entry.get("source"):
        return None
    return Path(str(entry["source"])).expanduser().resolve(strict=False)


def _configured_plugin_enabled(config_path: Path, plugin_id: str) -> bool:
    if not config_path.exists():
        return False
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstallBlocked(f"invalid Codex config TOML: {config_path}") from exc
    plugins = parsed.get("plugins")
    if not isinstance(plugins, dict):
        return False
    entry = plugins.get(plugin_id)
    return isinstance(entry, dict) and entry.get("enabled") is True


def _config_registry_snapshot(config_path: Path) -> NativeRegistrySnapshot:
    """Read the SAMVIL registry projection directly from an explicit profile."""

    if not config_path.exists():
        return NativeRegistrySnapshot("config", (), ())
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InstallBlocked(f"invalid Codex config TOML: {config_path}") from exc
    marketplaces = parsed.get("marketplaces", {})
    plugins = parsed.get("plugins", {})
    if not isinstance(marketplaces, dict) or not isinstance(plugins, dict):
        raise InstallBlocked("Codex registry tables have an invalid shape")
    marketplace_entries = tuple(
        _canonical_entry_json({"name": str(name), **entry})
        for name, entry in sorted(marketplaces.items(), key=lambda item: str(item[0]))
        if _related_registry_name(name) and isinstance(entry, dict)
    )
    plugin_entries = tuple(
        _canonical_entry_json({"pluginId": str(plugin_id), **entry})
        for plugin_id, entry in sorted(plugins.items(), key=lambda item: str(item[0]))
        if (
            _related_registry_name(plugin_id)
            or _related_registry_name(str(plugin_id).rpartition("@")[2])
        )
        and isinstance(entry, dict)
    )
    return NativeRegistrySnapshot("config", marketplace_entries, plugin_entries)


def _unrelated_config_projection(config_path: Path) -> str:
    """Seal user configuration while excluding SAMVIL-owned registry entries.

    Codex currently rewrites TOML line endings while changing its plugin
    registry. Comparing raw bytes would therefore reject a valid native
    command. This projection instead compares every parsed user setting and
    every non-SAMVIL marketplace/plugin entry.
    """

    if not config_path.exists():
        parsed: dict[str, Any] = {}
    else:
        try:
            value = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise NativeRecoveryRequired(
                f"cannot verify unrelated Codex config state: {config_path}"
            ) from exc
        if not isinstance(value, dict):  # pragma: no cover - tomllib contract
            raise NativeRecoveryRequired("Codex config root is not a table")
        parsed = dict(value)

    for table_name in ("marketplaces", "plugins"):
        raw_table = parsed.get(table_name)
        if raw_table is None:
            continue
        if not isinstance(raw_table, dict):
            raise NativeRecoveryRequired(f"Codex {table_name} registry is not a table")
        unrelated = {
            str(name): entry
            for name, entry in raw_table.items()
            if not (
                _related_registry_name(name)
                or (
                    table_name == "plugins"
                    and _related_registry_name(str(name).rpartition("@")[2])
                )
            )
        }
        if unrelated:
            parsed[table_name] = unrelated
        else:
            parsed.pop(table_name, None)
    raw_projection = _unrelated_config_raw_projection(config_path)
    return _canonical_entry_json(
        {
            "semantic": parsed,
            "raw": raw_projection.hex(),
        }
    )


def _unrelated_config_raw_projection(config_path: Path) -> bytes:
    """Keep exact bytes for non-owned TOML sections.

    Codex may rewrite owned registry tables and normalize line endings. Raw
    bytes outside those sections are still user state, including comments and
    spacing, so they remain part of the rollback invariant.
    """

    if not config_path.exists():
        return b""
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise NativeRecoveryRequired(
            f"cannot read unrelated Codex config state: {config_path}"
        ) from exc
    normalized = _normalize_text_newlines(raw)
    lines = normalized.splitlines(keepends=True)
    section_re = re.compile(rb"^[ \t]*\[\[?([^\]\r\n]+)\]\]?[^\r\n]*(?:\n|$)")

    def owned_header(header: bytes) -> bool:
        try:
            parsed = tomllib.loads(header.decode("utf-8") + "value = 1\n")
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            return False
        return any(
            isinstance(parsed.get(table), dict)
            and any(
                _related_registry_name(key)
                or (
                    table == "plugins"
                    and _related_registry_name(str(key).rpartition("@")[2])
                )
                for key in parsed[table]
            )
            for table in ("marketplaces", "plugins")
        ) or (
            isinstance(parsed.get("mcp_servers"), dict)
            and "samvil-mcp" in parsed["mcp_servers"]
        )

    kept: list[bytes] = []
    trim_separator_after_owned = False
    index = 0
    while index < len(lines):
        match = section_re.match(lines[index])
        if match is None or not owned_header(lines[index]):
            line = lines[index]
            # Codex can leave a different number of structural blank lines at
            # the boundary where an owned registry table was rewritten. Those
            # separators are not user state; remove them on both sides of the
            # omitted owned span while retaining all comments and content.
            if trim_separator_after_owned and not line.strip():
                index += 1
                continue
            trim_separator_after_owned = False
            kept.append(line)
            index += 1
            continue
        while kept and not kept[-1].strip():
            kept.pop()
        index += 1
        while index < len(lines) and section_re.match(lines[index]) is None:
            index += 1
        trim_separator_after_owned = True
    return b"".join(kept)


def _snapshot_from_cli_outputs(
    marketplace_output: str,
    plugin_output: str,
) -> NativeRegistrySnapshot:
    blockers: list[str] = []
    marketplaces_envelope = _json_object(
        marketplace_output,
        "Codex marketplace inventory",
        blockers,
    )
    plugins_envelope = _json_object(
        plugin_output,
        "Codex plugin inventory",
        blockers,
    )
    raw_marketplaces = marketplaces_envelope.get("marketplaces")
    raw_plugins = plugins_envelope.get("installed")
    if not isinstance(raw_marketplaces, list):
        blockers.append("Codex marketplace inventory has no marketplaces list")
        raw_marketplaces = []
    if not isinstance(raw_plugins, list):
        blockers.append("Codex plugin inventory has no installed list")
        raw_plugins = []
    for entry in raw_marketplaces:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not entry["name"]
        ):
            blockers.append("Codex marketplace inventory contains an invalid entry")
            break
    for entry in raw_plugins:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("pluginId"), str)
            or not entry["pluginId"]
        ):
            blockers.append("Codex plugin inventory contains an invalid entry")
            break
    marketplace_names = [
        entry.get("name") for entry in raw_marketplaces if isinstance(entry, dict)
    ]
    plugin_ids = [
        entry.get("pluginId") for entry in raw_plugins if isinstance(entry, dict)
    ]
    if len(marketplace_names) != len(set(marketplace_names)):
        blockers.append("Codex marketplace inventory contains a duplicate name")
    if len(plugin_ids) != len(set(plugin_ids)):
        blockers.append("Codex plugin inventory contains a duplicate pluginId")
    if blockers:
        raise InstallBlocked("; ".join(blockers))
    marketplaces = tuple(
        _canonical_entry_json(entry)
        for entry in raw_marketplaces
        if isinstance(entry, dict) and _related_registry_name(entry.get("name"))
    )
    plugins = tuple(
        _canonical_entry_json(entry)
        for entry in raw_plugins
        if isinstance(entry, dict)
        and (
            _related_registry_name(entry.get("pluginId"))
            or _related_registry_name(entry.get("name"))
            or _related_registry_name(entry.get("marketplaceName"))
        )
    )
    unrelated_projection = {
        "marketplaces": sorted(
            _canonical_entry_json(entry)
            for entry in raw_marketplaces
            if isinstance(entry, dict) and not _related_registry_name(entry.get("name"))
        ),
        "plugins": sorted(
            _canonical_entry_json(entry)
            for entry in raw_plugins
            if isinstance(entry, dict)
            and not (
                _related_registry_name(entry.get("pluginId"))
                or _related_registry_name(entry.get("name"))
                or _related_registry_name(entry.get("marketplaceName"))
            )
        ),
    }
    return NativeRegistrySnapshot(
        "codex_cli",
        tuple(sorted(marketplaces)),
        tuple(sorted(plugins)),
        _bytes_sha256(marketplace_output.encode("utf-8")),
        _bytes_sha256(plugin_output.encode("utf-8")),
        _bytes_sha256(
            json.dumps(
                unrelated_projection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ),
    )


def _subprocess_registry_reader(env: dict[str, str]) -> NativeRegistrySnapshot:
    def read(command: tuple[str, ...]) -> str:
        result = subprocess.run(
            command,
            env=_codex_subprocess_environment(env),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise InstallBlocked(
                f"Codex registry readback failed ({result.returncode}): {command}"
            )
        return result.stdout

    marketplace_output = read(("codex", "plugin", "marketplace", "list", "--json"))
    plugin_output = read(("codex", "plugin", "list", "--json"))
    return _snapshot_from_cli_outputs(marketplace_output, plugin_output)


def _registry_contains(
    snapshot: NativeRegistrySnapshot,
    *,
    marketplace: str | None = None,
    plugin_id: str | None = None,
) -> bool:
    entries = snapshot.marketplaces if marketplace is not None else snapshot.plugins
    key = "name" if marketplace is not None else "pluginId"
    expected = marketplace if marketplace is not None else plugin_id
    return any(json.loads(item).get(key) == expected for item in entries)


def _registry_entry(
    snapshot: NativeRegistrySnapshot,
    *,
    marketplace: str | None = None,
    plugin_id: str | None = None,
) -> dict[str, Any] | None:
    entries = snapshot.marketplaces if marketplace is not None else snapshot.plugins
    key = "name" if marketplace is not None else "pluginId"
    expected = marketplace if marketplace is not None else plugin_id
    for encoded in entries:
        value = json.loads(encoded)
        if value.get(key) == expected:
            return value
    return None


def _registry_related_equal(
    left: NativeRegistrySnapshot,
    right: NativeRegistrySnapshot,
) -> bool:
    """Compare the complete observed state, including unrelated entries."""

    if left.evidence_kind != right.evidence_kind:
        return False
    if left.unrelated_fingerprint != right.unrelated_fingerprint:
        return False
    return left.fingerprint == right.fingerprint


def _registry_unrelated_equal(
    left: NativeRegistrySnapshot,
    right: NativeRegistrySnapshot,
) -> bool:
    return (
        left.unrelated_fingerprint is None
        or right.unrelated_fingerprint is None
        or left.unrelated_fingerprint == right.unrelated_fingerprint
    )


def _native_compensation_commands(
    before: NativeRegistrySnapshot,
    current: NativeRegistrySnapshot,
) -> tuple[tuple[str, ...], ...]:
    """Return the only safe delta back to the sealed SAMVIL pre-state."""

    commands: list[tuple[str, ...]] = []
    for plugin_id in ("samvil@samvil-codex", "samvil@samvil"):
        prior = _registry_entry(before, plugin_id=plugin_id)
        now = _registry_entry(current, plugin_id=plugin_id)
        if prior is None and now is not None:
            commands.append(("codex", "plugin", "remove", plugin_id))
        elif prior is not None and now is not None and prior != now:
            raise NativeRecoveryRequired(
                f"native plugin changed concurrently during rollback: {plugin_id}"
            )
    for name in ("samvil-codex", "samvil"):
        prior = _registry_entry(before, marketplace=name)
        now = _registry_entry(current, marketplace=name)
        if prior is None and now is not None:
            commands.append(("codex", "plugin", "marketplace", "remove", name))
        elif prior is not None and now is not None and prior != now:
            raise NativeRecoveryRequired(
                f"native marketplace changed concurrently during rollback: {name}"
            )
    for name in ("samvil", "samvil-codex"):
        prior = _registry_entry(before, marketplace=name)
        now = _registry_entry(current, marketplace=name)
        if prior is not None and now is None:
            raise NativeRecoveryRequired(
                "pre-existing Codex marketplace was removed; automatic recreation "
                f"could change its cache: {name}"
            )
    for plugin_id in ("samvil@samvil", "samvil@samvil-codex"):
        prior = _registry_entry(before, plugin_id=plugin_id)
        now = _registry_entry(current, plugin_id=plugin_id)
        if prior is not None and now is None:
            raise NativeRecoveryRequired(
                "pre-existing Codex plugin was removed; automatic recreation could "
                f"change its cache: {plugin_id}"
            )
    return tuple(commands)


def _normalize_native_registry_snapshot(value: Any) -> NativeRegistrySnapshot:
    if isinstance(value, NativeRegistrySnapshot):
        return value
    if isinstance(value, dict):
        return _registry_snapshot_from_payload(value)
    # ``python -m samvil_mcp.codex_installer`` executes this module as
    # ``__main__`` while the migration transaction imports the package module
    # by its canonical name.  That creates two otherwise identical dataclass
    # identities.  Normalize through the sealed payload instead of trusting
    # Python class identity, and run the same hash/schema validation used for a
    # durable receipt before accepting it.
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return _registry_snapshot_from_payload(payload)
    raise InstallBlocked("native Codex registry readback returned an invalid value")


def _read_native_registry(
    registry_reader: Any,
    command_env: dict[str, str],
    *,
    mutation_started: bool,
) -> NativeRegistrySnapshot:
    try:
        return _normalize_native_registry_snapshot(registry_reader(command_env))
    except NativeRecoveryRequired as exc:
        if mutation_started:
            raise
        raise InstallBlocked(
            f"native Codex registry readback failed before native mutation: {exc}"
        ) from exc
    except InstallBlocked as exc:
        if mutation_started:
            raise NativeRecoveryRequired(
                f"native Codex registry readback failed after native mutation: {exc}"
            ) from exc
        raise
    except BaseException as exc:
        error_type = NativeRecoveryRequired if mutation_started else InstallBlocked
        phase = "after" if mutation_started else "before"
        raise error_type(
            f"native Codex registry readback failed {phase} native mutation: {exc}"
        ) from exc


def _require_cli_registry_evidence(snapshot: NativeRegistrySnapshot) -> None:
    digests = (
        snapshot.marketplace_output_sha256,
        snapshot.plugin_output_sha256,
        snapshot.unrelated_fingerprint,
    )
    if snapshot.evidence_kind != "codex_cli" or any(
        digest is None or _SHA256.fullmatch(digest) is None for digest in digests
    ):
        raise InstallBlocked(
            "Codex native activation requires complete Codex CLI registry evidence"
        )


def _verify_native_postcondition(
    snapshot: NativeRegistrySnapshot,
    *,
    wrapper: Path,
    allow_legacy: bool = False,
) -> None:
    desired_marketplace = next(
        (
            json.loads(item)
            for item in snapshot.marketplaces
            if json.loads(item).get("name") == "samvil-codex"
        ),
        None,
    )
    desired_plugin = next(
        (
            json.loads(item)
            for item in snapshot.plugins
            if json.loads(item).get("pluginId") == "samvil@samvil-codex"
        ),
        None,
    )
    if desired_marketplace is None or desired_plugin is None:
        raise InstallBlocked("native Codex registry postcondition is incomplete")
    root = desired_marketplace.get("root")
    if not isinstance(root, str) or Path(root).resolve(strict=False) != wrapper:
        raise InstallBlocked(
            "native Codex marketplace root does not match the owned wrapper"
        )
    if (
        desired_plugin.get("installed") is not True
        or desired_plugin.get("enabled") is not True
    ):
        raise InstallBlocked("native SAMVIL Codex plugin is not installed and enabled")
    plugin_source = desired_plugin.get("source")
    marketplace_source = desired_plugin.get("marketplaceSource")
    expected_plugin_source = wrapper / "samvil"
    if (
        not isinstance(plugin_source, dict)
        or plugin_source.get("source") != "local"
        or not isinstance(plugin_source.get("path"), str)
        or _lexical_absolute(Path(plugin_source["path"]))
        != _lexical_absolute(expected_plugin_source)
        or not isinstance(marketplace_source, dict)
        or marketplace_source.get("sourceType") != "local"
        or not isinstance(marketplace_source.get("source"), str)
        or _lexical_absolute(Path(marketplace_source["source"]))
        != _lexical_absolute(wrapper)
    ):
        raise InstallBlocked(
            "native SAMVIL Codex plugin source does not match the owned wrapper"
        )
    if not allow_legacy and any(
        json.loads(item).get("name") == "samvil" for item in snapshot.marketplaces
    ):
        raise InstallBlocked("legacy Codex marketplace remains registered")
    if not allow_legacy and any(
        json.loads(item).get("pluginId") == "samvil@samvil" for item in snapshot.plugins
    ):
        raise InstallBlocked("legacy SAMVIL Codex plugin remains installed")


def _registry_snapshot_from_payload(payload: object) -> NativeRegistrySnapshot:
    if not isinstance(payload, dict):
        raise InstallBlocked("stored native Codex registry evidence is invalid")
    evidence_kind = payload.get("evidence_kind")
    raw_marketplaces = payload.get("marketplaces")
    raw_plugins = payload.get("plugins")
    if (
        evidence_kind not in {"config", "codex_cli"}
        or not isinstance(raw_marketplaces, list)
        or not isinstance(raw_plugins, list)
        or not all(isinstance(item, dict) for item in raw_marketplaces)
        or not all(isinstance(item, dict) for item in raw_plugins)
    ):
        raise InstallBlocked("stored native Codex registry evidence is invalid")
    marketplace_names = [item.get("name") for item in raw_marketplaces]
    plugin_ids = [item.get("pluginId") for item in raw_plugins]
    if (
        not all(isinstance(name, str) and name for name in marketplace_names)
        or not all(isinstance(plugin_id, str) and plugin_id for plugin_id in plugin_ids)
        or len(marketplace_names) != len(set(marketplace_names))
        or len(plugin_ids) != len(set(plugin_ids))
    ):
        raise InstallBlocked(
            "stored native Codex registry evidence has invalid identities"
        )
    snapshot = NativeRegistrySnapshot(
        evidence_kind,
        tuple(sorted(_canonical_entry_json(item) for item in raw_marketplaces)),
        tuple(sorted(_canonical_entry_json(item) for item in raw_plugins)),
        (
            str(payload["marketplace_output_sha256"])
            if "marketplace_output_sha256" in payload
            else None
        ),
        (
            str(payload["plugin_output_sha256"])
            if "plugin_output_sha256" in payload
            else None
        ),
        (
            str(payload["unrelated_fingerprint"])
            if "unrelated_fingerprint" in payload
            else None
        ),
    )
    for digest in (
        snapshot.marketplace_output_sha256,
        snapshot.plugin_output_sha256,
        snapshot.unrelated_fingerprint,
    ):
        if digest is not None and _SHA256.fullmatch(digest) is None:
            raise InstallBlocked("stored native Codex registry hash is invalid")
    if evidence_kind == "codex_cli" and any(
        digest is None
        for digest in (
            snapshot.marketplace_output_sha256,
            snapshot.plugin_output_sha256,
            snapshot.unrelated_fingerprint,
        )
    ):
        raise InstallBlocked(
            "stored Codex CLI registry evidence is missing an output hash"
        )
    if payload.get("fingerprint") != snapshot.fingerprint:
        raise InstallBlocked("stored native Codex registry fingerprint changed")
    return snapshot


def _codex_marketplace_wrapper_content(canonical_root: Path) -> tuple[str, Path]:
    payload = {
        "name": "samvil-codex",
        "owner": {"name": "insam"},
        "plugins": [
            {
                "name": "samvil",
                "source": "./samvil",
                "description": "Codex-first trustworthy app-building harness.",
                "category": "development",
            }
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n", canonical_root


def _owned_marketplace_wrapper_matches(wrapper: Path, canonical_root: Path) -> bool:
    """Return true only for the exact wrapper tree created by this installer."""

    expected, expected_plugin_root = _codex_marketplace_wrapper_content(canonical_root)
    manifest_root = wrapper / ".claude-plugin"
    manifest = manifest_root / "marketplace.json"
    manifest_lock = manifest_root / "marketplace.json.lock"
    plugin_link = wrapper / "samvil"
    try:
        wrapper_metadata = wrapper.lstat()
        manifest_root_metadata = manifest_root.lstat()
        manifest_metadata = manifest.lstat()
        return (
            stat.S_ISDIR(wrapper_metadata.st_mode)
            and not stat.S_ISLNK(wrapper_metadata.st_mode)
            and {entry.name for entry in wrapper.iterdir()}
            == {".claude-plugin", "samvil"}
            and stat.S_ISDIR(manifest_root_metadata.st_mode)
            and not stat.S_ISLNK(manifest_root_metadata.st_mode)
            and {entry.name for entry in manifest_root.iterdir()}
            in ({"marketplace.json"}, {"marketplace.json", "marketplace.json.lock"})
            and stat.S_ISREG(manifest_metadata.st_mode)
            and not stat.S_ISLNK(manifest_metadata.st_mode)
            and manifest_metadata.st_nlink == 1
            and manifest.read_text(encoding="utf-8") == expected
            and (
                not manifest_lock.exists()
                or (
                    not manifest_lock.is_symlink()
                    and manifest_lock.is_file()
                    and manifest_lock.lstat().st_nlink == 1
                    and manifest_lock.stat().st_size == 0
                )
            )
            and plugin_link.is_symlink()
            and plugin_link.resolve(strict=False) == expected_plugin_root
        )
    except (OSError, UnicodeError):
        return False


def _codex_marketplace_wrapper(root: Path, canonical_root: Path) -> tuple[Path, bool]:
    marketplaces_root = root / "marketplaces"
    resolved_marketplaces = marketplaces_root.resolve(strict=False)
    if marketplaces_root.is_symlink() or (
        resolved_marketplaces != root and root not in resolved_marketplaces.parents
    ):
        raise InstallBlocked(
            f"Codex marketplaces path escapes isolated profile: {marketplaces_root}"
        )
    wrapper = marketplaces_root / "samvil-codex"
    expected, _expected_plugin_root = _codex_marketplace_wrapper_content(canonical_root)
    if wrapper.exists():
        if not _owned_marketplace_wrapper_matches(wrapper, canonical_root):
            raise InstallBlocked(f"ambiguous Codex marketplace wrapper: {wrapper}")
        return wrapper, False
    marketplaces_root.mkdir(parents=True, exist_ok=True)
    temporary_wrapper = Path(
        tempfile.mkdtemp(prefix=".samvil-codex.", dir=marketplaces_root)
    )
    try:
        temporary_manifest = temporary_wrapper / ".claude-plugin" / "marketplace.json"
        temporary_plugin_link = temporary_wrapper / "samvil"
        temporary_manifest.parent.mkdir(parents=True, exist_ok=False)
        atomic_write_text(temporary_manifest, expected)
        temporary_plugin_link.symlink_to(
            canonical_root,
            target_is_directory=True,
        )
        if wrapper.exists():
            raise InstallBlocked(
                f"Codex marketplace wrapper appeared during install: {wrapper}"
            )
        temporary_wrapper.replace(wrapper)
    except BaseException:
        shutil.rmtree(temporary_wrapper, ignore_errors=True)
        raise
    return wrapper, True


def _execute_isolated_install_impl(
    plan: CodexInstallPlan,
    *,
    codex_home: Path,
    command_runner: Any,
    registry_reader: Any | None = None,
    native_event_recorder: Any | None = None,
    migrate: bool = False,
    expected_legacy_plan_sha256: str | None = None,
    allow_legacy_registry_migration: bool = False,
) -> InstallReceipt:
    """Internal executor retained for filesystem-focused unit tests.

    Production callers must use :func:`execute_isolated_install`, which requires
    machine-readable Codex CLI evidence. Keeping the unverified fallback private
    prevents a no-op command runner from producing a public success receipt.
    """

    if migrate:
        from .codex_migration import execute_legacy_migration

        return execute_legacy_migration(
            plan,
            codex_home=codex_home,
            command_runner=command_runner,
            registry_reader=registry_reader,
            expected_plan_sha256=expected_legacy_plan_sha256,
        )
    if plan.blockers:
        raise InstallBlocked("; ".join(plan.blockers))
    lexical_root = _lexical_absolute(codex_home)
    unsafe_profile_reason = _unsafe_directory_path_reason(
        lexical_root,
        label="Codex profile",
    )
    if unsafe_profile_reason is not None:
        raise InstallBlocked(unsafe_profile_reason)
    root = lexical_root.resolve(strict=False)
    if root == Path(root.anchor):
        raise InstallBlocked(
            f"isolated Codex root must not be a filesystem root: {root}"
        )
    canonical_root = plan.canonical_root.expanduser().resolve(strict=False)
    if (
        root == canonical_root
        or root in canonical_root.parents
        or canonical_root in root.parents
    ):
        raise InstallBlocked(
            "Codex profile and canonical SAMVIL repository must not overlap"
        )
    canonical_contract = _canonical_activation_contract(canonical_root)

    def verify_canonical_contract() -> None:
        if _canonical_activation_contract(canonical_root) != canonical_contract:
            raise InstallBlocked(
                "canonical SAMVIL activation contract changed during native activation"
            )

    try:
        backups_root = safe_child_directory(root, "backups", label="backups")
    except RuntimeLayoutError as exc:
        raise InstallBlocked(
            f"backups path escapes isolated profile: {root / 'backups'}"
        ) from exc
    try:
        personal_root = safe_child_directory(root, "skills", label="skills")
    except RuntimeLayoutError as exc:
        raise InstallBlocked(
            f"skills path escapes isolated profile: {root / 'skills'}"
        ) from exc
    if _unsafe_personal_skill_links(personal_root):
        raise InstallBlocked("unsafe personal skill symlink blocks isolated install")
    config = root / "config.toml"
    if config.is_symlink():
        raise InstallBlocked(f"Codex config symlink is not safe to mutate: {config}")
    config_existed = config.exists()
    current_samvil_root = _configured_marketplace_root(config, "samvil-codex")
    current_plugin_enabled = _configured_plugin_enabled(
        config,
        "samvil@samvil-codex",
    )
    wrapper_path = root / "marketplaces" / "samvil-codex"
    if wrapper_path.exists():
        _codex_marketplace_wrapper(root, plan.canonical_root)
    legacy_admission = build_legacy_migration_plan(
        repo_root=plan.canonical_root,
        codex_home=codex_home,
    )
    legacy_payload = legacy_admission.to_dict()
    if (
        expected_legacy_plan_sha256 is not None
        and legacy_payload["plan_sha256"] != expected_legacy_plan_sha256
    ):
        raise InstallBlocked(
            "legacy Codex profile changed during install admission; rerun the check"
        )
    legacy_blockers = (
        _legacy_install_blockers(legacy_admission)
        if legacy_admission.actions
        or (
            legacy_admission.native_registry_actions
            and not allow_legacy_registry_migration
        )
        else list(legacy_admission.blockers)
    )
    if legacy_blockers:
        raise InstallBlocked("; ".join(legacy_blockers))

    root.mkdir(parents=True, exist_ok=True)
    strict_registry_proof = registry_reader is not None
    if allow_legacy_registry_migration and not strict_registry_proof:
        raise InstallBlocked(
            "legacy Codex registry migration requires machine-readable native readback"
        )
    effective_registry_reader = registry_reader or (
        lambda _env: _config_registry_snapshot(config)
    )
    registry_before = _read_native_registry(
        effective_registry_reader,
        {"CODEX_HOME": str(root), "HOME": str(root.parent)},
        mutation_started=False,
    )
    protected_before = inventory_personal_skills(personal_root)
    backup_paths: list[Path] = []
    commands: list[tuple[str, ...]] = []
    personal_snapshot_root: Path | None = None
    config_backup: Path | None = None
    wrapper = wrapper_path
    wrapper_created = False
    wrapper_created_identity: tuple[int, int] | None = None
    command_env = {"CODEX_HOME": str(root), "HOME": str(root.parent)}
    unrelated_config_before = _unrelated_config_projection(config)
    personal_snapshot_ready = False
    unexpected_quarantine: Path | None = None
    preserve_personal_snapshot = False

    def record_native_event(kind: str, **details: Any) -> None:
        if native_event_recorder is not None:
            native_event_recorder({"kind": kind, **details})

    record_native_event("snapshot_before", snapshot=registry_before.to_dict())

    def protected_inventory() -> tuple[SkillInventoryEntry, ...]:
        try:
            safe_child_directory(root, "skills", label="skills")
        except RuntimeLayoutError as exc:
            raise InstallBlocked(
                f"skills path escapes isolated profile: {personal_root}"
            ) from exc
        if _unsafe_personal_skill_links(personal_root):
            raise InstallBlocked("unsafe personal skill symlink detected")
        return inventory_personal_skills(personal_root)

    def quarantine_root() -> Path:
        nonlocal unexpected_quarantine
        if unexpected_quarantine is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            unexpected_quarantine = backups_root / f"unexpected-personal-skills-{stamp}"
            unexpected_quarantine.mkdir(parents=True, exist_ok=False)
        return unexpected_quarantine

    def restore_personal_skills() -> None:
        if personal_root.is_symlink():
            personal_root.replace(quarantine_root() / "skills-symlink")
            personal_root.mkdir(parents=True, exist_ok=False)
        else:
            try:
                safe_child_directory(root, "skills", label="skills")
            except RuntimeLayoutError as exc:
                raise InstallBlocked(
                    f"skills path escapes isolated profile: {personal_root}"
                ) from exc
            personal_root.mkdir(parents=True, exist_ok=True)
        for unsafe in _unsafe_personal_skill_links(personal_root):
            unsafe.replace(quarantine_root() / unsafe.name)
        protected_paths = {entry.path for entry in protected_before}
        unexpected = tuple(
            entry
            for entry in protected_inventory()
            if entry.path not in protected_paths
        )
        if unexpected:
            for entry in unexpected:
                entry.path.replace(quarantine_root() / entry.path.name)
        if not personal_snapshot_ready or personal_snapshot_root is None:
            return
        current_by_path = {entry.path: entry for entry in protected_inventory()}
        for entry in protected_before:
            current = current_by_path.get(entry.path)
            if current == entry:
                continue
            snapshot = personal_snapshot_root / entry.path.name
            restore_root = Path(
                tempfile.mkdtemp(prefix=".restore-personal-skill.", dir=backups_root)
            )
            candidate = restore_root / entry.path.name
            try:
                shutil.copytree(snapshot, candidate, symlinks=True)
                destination = personal_root / entry.path.name
                displaced: Path | None = None
                if destination.is_symlink() or destination.exists():
                    displaced = quarantine_root() / entry.path.name
                    destination.replace(displaced)
                try:
                    candidate.replace(destination)
                except BaseException:
                    if displaced is not None and not destination.exists():
                        displaced.replace(destination)
                    raise
            finally:
                shutil.rmtree(restore_root, ignore_errors=True)

    def rollback_install() -> NativeRegistrySnapshot:
        record_native_event("rollback_started")
        if strict_registry_proof:
            try:
                current = _read_native_registry(
                    effective_registry_reader,
                    command_env,
                    mutation_started=True,
                )
            except BaseException as exc:
                raise NativeRecoveryRequired(
                    f"cannot inspect native Codex state before rollback: {exc}"
                ) from exc
            if not _registry_unrelated_equal(registry_before, current):
                raise NativeRecoveryRequired(
                    "unrelated Codex registry state changed during native activation"
                )
            compensation_commands = _native_compensation_commands(
                registry_before,
                current,
            )
        else:
            # Injected unit runners cannot prove semantic Codex state. Preserve
            # the historical filesystem-only test contract; production CLI
            # activation always supplies the strict machine-readable reader.
            compensation_commands = ()
        for inverse in compensation_commands:
            record_native_event("rollback_intent", argv=list(inverse))
            try:
                command_runner(inverse, command_env)
            except BaseException as exc:
                raise NativeRecoveryRequired(
                    f"native Codex compensation command failed: {inverse}: {exc}"
                ) from exc
            record_native_event("rollback_applied", argv=list(inverse))
        if not strict_registry_proof:
            if config_backup is not None:
                _atomic_copy(config_backup, config)
            elif not config_existed:
                config.unlink(missing_ok=True)
        if wrapper_created:
            if wrapper_created_identity is None:
                raise NativeRecoveryRequired(
                    "created Codex marketplace wrapper has no sealed identity"
                )
            wrapper_quarantine = Path(
                tempfile.mkdtemp(prefix=".rollback-marketplace.", dir=backups_root)
            )
            quarantined_wrapper = wrapper_quarantine / wrapper.name
            try:
                wrapper.replace(quarantined_wrapper)
                metadata = quarantined_wrapper.lstat()
                current_identity = (int(metadata.st_dev), int(metadata.st_ino))
                if (
                    current_identity != wrapper_created_identity
                    or not _owned_marketplace_wrapper_matches(
                        quarantined_wrapper,
                        plan.canonical_root,
                    )
                ):
                    if not wrapper.exists() and not wrapper.is_symlink():
                        quarantined_wrapper.replace(wrapper)
                    raise NativeRecoveryRequired(
                        "Codex marketplace wrapper changed concurrently; user data was preserved"
                    )
                shutil.rmtree(quarantined_wrapper)
                wrapper_quarantine.rmdir()
            except NativeRecoveryRequired:
                raise
            except OSError as exc:
                raise NativeRecoveryRequired(
                    f"Codex marketplace wrapper changed during rollback: {exc}"
                ) from exc
        restore_personal_skills()
        restored = _read_native_registry(
            effective_registry_reader,
            command_env,
            mutation_started=True,
        )
        if not _registry_related_equal(registry_before, restored):
            raise NativeRecoveryRequired(
                "native Codex registry rollback could not reproduce the sealed pre-state"
            )
        if strict_registry_proof:
            if _unrelated_config_projection(config) != unrelated_config_before:
                raise NativeRecoveryRequired(
                    "unrelated Codex config changed during native rollback; current "
                    "content and the pre-migration backup were preserved"
                )
            if config_existed:
                if config_backup is None or not config.exists():
                    raise NativeRecoveryRequired(
                        "native registry was restored but its original Codex config "
                        "cannot be proven; available state was preserved"
                    )
                current_config = config.read_bytes()
                original_config = config_backup.read_bytes()
                if current_config != original_config:
                    if _normalize_text_newlines(
                        current_config
                    ) == _normalize_text_newlines(original_config):
                        _atomic_copy(config_backup, config)
                    else:
                        raise NativeRecoveryRequired(
                            "native registry was restored semantically but Codex config "
                            "bytes changed beyond newline normalization; current content "
                            "and the original backup were preserved"
                        )
            elif config.exists():
                if config.read_bytes().strip():
                    raise NativeRecoveryRequired(
                        "native registry was restored semantically but Codex created a "
                        "non-empty config file; current content was preserved"
                    )
                config.unlink()
        else:
            if config_existed:
                if (
                    config_backup is None
                    or config.read_bytes() != config_backup.read_bytes()
                ):
                    raise NativeRecoveryRequired(
                        "Codex config bytes differ after native rollback"
                    )
            elif config.exists():
                raise NativeRecoveryRequired(
                    "Codex config appeared after rollback of an initially empty profile"
                )
        if not compare_skill_inventories(protected_before, protected_inventory()):
            raise NativeRecoveryRequired(
                "personal Codex skill inventory differs after native rollback"
            )
        record_native_event("rollback_verified", snapshot=restored.to_dict())
        return restored

    try:
        backups_root.mkdir(parents=True, exist_ok=True)
        if protected_before:
            personal_snapshot_root = Path(
                tempfile.mkdtemp(prefix=".personal-skills.", dir=backups_root)
            )
            for entry in protected_before:
                shutil.copytree(
                    entry.path,
                    personal_snapshot_root / entry.path.name,
                    symlinks=True,
                )
            personal_snapshot_ready = True
        if config_existed:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = backups_root / f"config-{stamp}.toml"
            _atomic_copy(config, backup)
            backup_paths.append(backup)
            config_backup = backup
        verify_canonical_contract()
        wrapper, wrapper_created = _codex_marketplace_wrapper(root, plan.canonical_root)
        if wrapper_created:
            wrapper_metadata = wrapper.lstat()
            wrapper_created_identity = (
                int(wrapper_metadata.st_dev),
                int(wrapper_metadata.st_ino),
            )
        add_marketplace = (
            "codex",
            "plugin",
            "marketplace",
            "add",
            str(wrapper),
        )
        add_plugin = ("codex", "plugin", "add", "samvil@samvil-codex")
        activation_commands: list[tuple[str, ...]] = []
        retirement_commands: list[tuple[str, ...]] = []
        if current_samvil_root != wrapper:
            activation_commands.append(add_marketplace)
        if not (current_samvil_root == wrapper and current_plugin_enabled):
            activation_commands.append(add_plugin)
        if "remove_plugin:samvil@samvil" in legacy_admission.native_registry_actions:
            retirement_commands.append(("codex", "plugin", "remove", "samvil@samvil"))
        if "remove_marketplace:samvil" in legacy_admission.native_registry_actions:
            retirement_commands.append(
                ("codex", "plugin", "marketplace", "remove", "samvil")
            )

        def run_native_commands(planned_commands: list[tuple[str, ...]]) -> None:
            for command in planned_commands:
                if (
                    strict_registry_proof
                    and _unrelated_config_projection(config) != unrelated_config_before
                ):
                    raise NativeRecoveryRequired(
                        "unrelated Codex config changed before native activation command"
                    )
                record_native_event("command_intent", argv=list(command))
                command_runner(command, command_env)
                commands.append(command)
                record_native_event("command_applied", argv=list(command))
                if strict_registry_proof:
                    current_registry = _read_native_registry(
                        effective_registry_reader,
                        command_env,
                        mutation_started=True,
                    )
                    if not _registry_unrelated_equal(
                        registry_before,
                        current_registry,
                    ):
                        raise NativeRecoveryRequired(
                            "unrelated Codex registry state changed during native activation"
                        )
                    record_native_event(
                        "command_readback",
                        argv=list(command),
                        snapshot=current_registry.to_dict(),
                    )
                    if _unrelated_config_projection(config) != unrelated_config_before:
                        raise NativeRecoveryRequired(
                            "unrelated Codex config changed during native activation"
                        )
                if not compare_skill_inventories(
                    protected_before,
                    protected_inventory(),
                ):
                    raise InstallBlocked(
                        "personal Codex skill inventory changed during isolated install"
                    )

        run_native_commands(activation_commands)
        if retirement_commands:
            activation_registry = _read_native_registry(
                effective_registry_reader,
                command_env,
                mutation_started=bool(commands),
            )
            _verify_native_postcondition(
                activation_registry,
                wrapper=wrapper,
                allow_legacy=True,
            )
            record_native_event(
                "activation_verified_before_legacy_retirement",
                snapshot=activation_registry.to_dict(),
            )
        run_native_commands(retirement_commands)

        protected_after = protected_inventory()
        if not compare_skill_inventories(protected_before, protected_after):
            raise InstallBlocked(
                "personal Codex skill inventory changed during isolated install"
            )
        registry_after = _read_native_registry(
            effective_registry_reader,
            command_env,
            mutation_started=bool(commands),
        )
        if not _registry_unrelated_equal(registry_before, registry_after):
            raise NativeRecoveryRequired(
                "unrelated Codex registry state changed during native activation"
            )
        if strict_registry_proof:
            _verify_native_postcondition(registry_after, wrapper=wrapper)
            if _unrelated_config_projection(config) != unrelated_config_before:
                raise NativeRecoveryRequired(
                    "unrelated Codex config changed during native activation"
                )
        verify_canonical_contract()
        record_native_event("snapshot_after", snapshot=registry_after.to_dict())
    except BaseException as exc:
        try:
            rollback_install()
        except BaseException as rollback_exc:
            preserve_personal_snapshot = personal_snapshot_root is not None
            snapshot_note = (
                f"; personal skill snapshot preserved at {personal_snapshot_root}"
                if personal_snapshot_root is not None
                else ""
            )
            if isinstance(rollback_exc, Exception):
                raise NativeRecoveryRequired(
                    f"Codex rollback requires recovery: {rollback_exc}{snapshot_note}"
                ) from rollback_exc
            raise
        if isinstance(exc, NativeRecoveryRequired):
            raise
        if isinstance(exc, InstallBlocked):
            if unexpected_quarantine is not None:
                raise InstallBlocked(
                    f"{exc}; unexpected personal skills preserved at "
                    f"{unexpected_quarantine}"
                ) from exc
            raise
        if isinstance(exc, Exception):
            raise InstallBlocked(
                f"Codex activation failed; config restored: {exc}"
            ) from exc
        raise
    finally:
        if personal_snapshot_root is not None and not preserve_personal_snapshot:
            shutil.rmtree(personal_snapshot_root, ignore_errors=True)

    return InstallReceipt(
        mode="migrate" if migrate else "install",
        canonical_root=plan.canonical_root,
        backup_paths=tuple(backup_paths),
        commands=tuple(commands),
        personal_skills_before=protected_before,
        personal_skills_after=protected_after,
        native_registry_before=registry_before,
        native_registry_after=registry_after,
        canonical_contract=canonical_contract,
    )


def execute_isolated_install(
    plan: CodexInstallPlan,
    *,
    codex_home: Path,
    command_runner: Any,
    registry_reader: Any | None = None,
    native_event_recorder: Any | None = None,
    migrate: bool = False,
    expected_legacy_plan_sha256: str | None = None,
    allow_legacy_registry_migration: bool = False,
) -> InstallReceipt:
    """Execute inside an explicit profile with Codex CLI readback proof."""

    if registry_reader is None:
        raise InstallBlocked(
            "Codex native activation requires machine-readable registry readback"
        )
    readiness = validate_activation_readiness(plan.canonical_root)
    if not readiness["ready"]:
        raise InstallBlocked("; ".join(readiness["blockers"]))

    def verified_registry_reader(env: dict[str, str]) -> NativeRegistrySnapshot:
        # The outer executor owns mutation phase classification; this wrapper
        # only normalizes and enforces complete Codex CLI evidence.
        snapshot = _normalize_native_registry_snapshot(registry_reader(env))
        _require_cli_registry_evidence(snapshot)
        return snapshot

    return _execute_isolated_install_impl(
        plan,
        codex_home=codex_home,
        command_runner=command_runner,
        registry_reader=verified_registry_reader,
        native_event_recorder=native_event_recorder,
        migrate=migrate,
        expected_legacy_plan_sha256=expected_legacy_plan_sha256,
        allow_legacy_registry_migration=allow_legacy_registry_migration,
    )


def build_install_plan(
    *,
    repo_root: Path,
    codex_home: Path,
    current_marketplace_root: Path | None = None,
    capability_help: str = "",
    marketplace_output: str = "{}",
    plugin_output: str = "{}",
    feature_output: str = "{}",
) -> CodexInstallPlan:
    """Build a deterministic plan without creating or modifying any path."""

    codex_home = Path(codex_home).expanduser().resolve(strict=False)
    skills_root = codex_home / "skills"
    blockers: list[str] = []
    actions: list[MigrationAction] = []
    try:
        canonical = validate_marketplace_root(
            repo_root,
            user_home=codex_home.parent,
            codex_skills_root=skills_root,
        )
    except ValueError as exc:
        canonical = Path(repo_root).expanduser().resolve(strict=False)
        blockers.append(str(exc))

    if current_marketplace_root is not None:
        current = Path(current_marketplace_root).expanduser().resolve(strict=False)
        if current != canonical:
            actions.append(
                MigrationAction(
                    "report_blocker",
                    current,
                    "current marketplace root differs from canonical repository root",
                )
            )
            blockers.append(f"marketplace root mismatch: {current} != {canonical}")

    capability = parse_capability_probe(
        help_output=capability_help,
        marketplace_output=marketplace_output,
        plugin_output=plugin_output,
        feature_output=feature_output,
    )
    personal = inventory_personal_skills(skills_root)
    return CodexInstallPlan(
        canonical_root=canonical,
        capability=capability,
        personal_skills=personal,
        actions=tuple(actions),
        blockers=tuple(blockers),
    )


def _subprocess_runner(command: tuple[str, ...], env: dict[str, str]) -> Any:
    return subprocess.run(
        command,
        check=True,
        env=_codex_subprocess_environment(env),
        capture_output=True,
        text=True,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Activate the native SAMVIL Codex plugin"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--migrate", action="store_true")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inventory legacy artifacts without creating or modifying the profile",
    )
    parser.add_argument(
        "--expected-plan-sha256",
        help="SHA-256 emitted by the preceding migration dry-run",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run and not args.migrate:
        parser.error("--dry-run requires --migrate")
    if args.migrate and args.dry_run:
        plan = build_legacy_migration_plan(
            repo_root=args.repo_root,
            codex_home=args.codex_home,
        )
        payload = plan.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if plan.to_dict()["ready"] else 1

    if args.migrate and args.expected_plan_sha256 is None:
        raise InstallBlocked(
            "legacy migration requires a matching checked legacy plan SHA-256"
        )

    readiness = validate_activation_readiness(args.repo_root)
    legacy_migration = build_legacy_migration_plan(
        repo_root=args.repo_root,
        codex_home=args.codex_home,
    )
    legacy_payload = legacy_migration.to_dict()
    legacy_blockers = (
        list(legacy_migration.blockers)
        if args.migrate
        else _legacy_install_blockers(legacy_migration)
    )
    readiness["legacy_migration"] = legacy_payload
    if legacy_blockers:
        environment = {
            "ready": False,
            "blockers": [
                (
                    "Codex CLI environment check skipped because legacy profile "
                    "admission failed"
                )
            ],
            "codex_binary": "",
            "uvx_binary": "",
            "plugin_commands_supported": False,
        }
    elif args.migrate or args.check:
        # Capability probing must not point Codex at the profile that is still
        # awaiting mutation-boundary admission. A temporary empty profile proves
        # the binary surface without giving the command a chance to write target
        # state before the sealed plan is revalidated.
        with tempfile.TemporaryDirectory(prefix="samvil-codex-capability-") as probe:
            environment = validate_cli_environment(
                Path(probe).resolve(strict=True) / ".codex"
            )
    else:
        environment = validate_cli_environment(args.codex_home)
    readiness["environment"] = environment
    readiness["blockers"] = [
        *readiness["blockers"],
        *legacy_blockers,
        *environment["blockers"],
    ]
    readiness["ready"] = not readiness["blockers"]
    if args.check:
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
        return 0 if readiness["ready"] else 1
    if args.migrate:
        if legacy_migration.blockers:
            raise InstallBlocked("; ".join(legacy_migration.blockers))
        if not readiness["environment"]["ready"]:
            raise InstallBlocked("; ".join(readiness["environment"]["blockers"]))
    if not readiness["ready"]:
        raise InstallBlocked("; ".join(readiness["blockers"]))

    canonical = validate_marketplace_root(
        args.repo_root,
        user_home=args.codex_home.expanduser().resolve(strict=False).parent,
        codex_skills_root=args.codex_home / "skills",
    )
    plan = CodexInstallPlan(
        canonical_root=canonical,
        capability=CodexCapabilityProbe(True, True),
    )
    receipt = execute_isolated_install(
        plan,
        codex_home=args.codex_home,
        command_runner=_subprocess_runner,
        registry_reader=_subprocess_registry_reader,
        migrate=args.migrate,
        expected_legacy_plan_sha256=(
            args.expected_plan_sha256 if args.migrate else legacy_payload["plan_sha256"]
        ),
    )
    payload = receipt.to_dict()
    print(
        json.dumps(payload, ensure_ascii=False, indent=2)
        if args.json
        else f"Codex native plugin activated: {canonical}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "CodexCapabilityProbe",
    "CodexInstallPlan",
    "InstallBlocked",
    "InstallReceipt",
    "LegacyArtifact",
    "LegacyMigrationPlan",
    "LegacyOwnership",
    "MigrationAction",
    "NativeRecoveryRequired",
    "NativeRegistrySnapshot",
    "SkillInventoryEntry",
    "build_install_plan",
    "build_legacy_migration_plan",
    "classify_generated_file",
    "classify_legacy_skill",
    "compare_skill_inventories",
    "execute_isolated_install",
    "inventory_personal_skills",
    "parse_capability_probe",
    "validate_cli_environment",
    "validate_marketplace_root",
]
