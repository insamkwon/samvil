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
import subprocess
import tempfile
import tomllib
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .ssot_io import atomic_write_text
from .runtime_layout import RuntimeLayoutError, safe_child_directory

_FRONTMATTER_NAME = re.compile(r"^name:\s*([^\n#]+?)\s*$", re.MULTILINE)


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
    command_ready = all(token in command_text for token in ("plugin", "marketplace", "--json"))
    plugins_ready = feature_flags.get("plugins") is True and feature_flags.get("mcp_servers") is True
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
    home = Path(user_home).expanduser().resolve(strict=False)
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frontmatter_name(path: Path) -> str:
    match = _FRONTMATTER_NAME.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else path.parent.name


def _skill_tree_hash(skill_root: Path) -> str:
    """Hash every owned path without following symlinks outside the skill."""
    digest = hashlib.sha256()
    for path in sorted(
        skill_root.rglob("*"),
        key=lambda item: item.relative_to(skill_root).as_posix(),
    ):
        relative = path.relative_to(skill_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"L")
            target = os.readlink(path).encode("utf-8")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
        elif path.is_dir():
            digest.update(b"D")
        elif path.is_file():
            digest.update(b"F")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
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
    root = Path(skills_root).expanduser().resolve(strict=False)
    if not root.is_dir():
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
    def normalized(items: tuple[SkillInventoryEntry, ...]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((item.name, item.content_hash) for item in items))

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
    path = Path(path).expanduser().resolve(strict=False)
    canonical = Path(canonical_path).expanduser().resolve(strict=False)
    if not path.exists():
        return LegacyOwnership(path, "absent", reason="path does not exist")
    digest = _sha256(path)
    if canonical.is_file() and path.read_bytes() == canonical.read_bytes():
        return LegacyOwnership(path, "generated_legacy", digest, False, "byte-identical canonical copy")
    return LegacyOwnership(path, "user_modified", digest, True, "content differs from canonical copy")


def classify_generated_file(path: Path, expected_content: str) -> LegacyOwnership:
    path = Path(path).expanduser().resolve(strict=False)
    if not path.exists():
        return LegacyOwnership(path, "absent", reason="path does not exist")
    digest = _sha256(path)
    if path.read_text(encoding="utf-8") == expected_content:
        return LegacyOwnership(path, "generated_legacy", digest, False, "known generated content")
    return LegacyOwnership(path, "user_modified", digest, True, "content is ambiguous")


@dataclass(frozen=True)
class MigrationAction:
    kind: str
    path: Path
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "path": str(self.path), "reason": self.reason}


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


def validate_activation_readiness(repo_root: Path) -> dict[str, Any]:
    """Prove the repository is complete enough for actual-profile activation."""
    root = Path(repo_root).expanduser().resolve(strict=False)
    blockers: list[str] = []
    manifest = root / ".codex-plugin" / "plugin.json"
    launcher = root / ".codex-mcp.json"
    skills_root = root / "codex" / "skills"
    if not manifest.is_file():
        blockers.append("Codex plugin manifest is missing")
    if not launcher.is_file():
        blockers.append("relative Codex MCP launcher is missing")
    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        launcher_data = json.loads(launcher.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest_data = {}
        launcher_data = {}
        blockers.append("Codex manifest or launcher is invalid JSON")
    public_skills = sorted(path.name for path in skills_root.iterdir() if path.is_dir()) if skills_root.is_dir() else []
    if public_skills != ["resume", "run", "status"]:
        blockers.append("Codex public skill surface must be exactly run/resume/status")
    for name in ("run", "resume", "status"):
        if not (skills_root / name / "SKILL.md").is_file():
            blockers.append(f"missing public Codex skill: {name}")
    if manifest_data.get("skills") != "./codex/skills/" or manifest_data.get("mcpServers") != "./.codex-mcp.json":
        blockers.append("Codex manifest does not use relative public surfaces")
    server = (launcher_data.get("mcpServers") or {}).get("samvil-mcp")
    launcher_script = root / "scripts" / "start-codex-mcp.sh"
    if (
        not isinstance(server, dict)
        or server.get("command") != "bash"
        or server.get("args") != ["./scripts/start-codex-mcp.sh"]
        or not launcher_script.is_file()
    ):
        blockers.append("Codex MCP launcher is not the relative package launcher")
    return {"ready": not blockers, "blockers": blockers, "public_skills": public_skills, "manifest": str(manifest), "launcher": str(launcher)}


def _capability_probe_runner(command: tuple[str, ...], env: dict[str, str]) -> Any:
    return subprocess.run(
        command,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def validate_cli_environment(
    codex_home: Path,
    *,
    which: Any = shutil.which,
    command_runner: Any = _capability_probe_runner,
) -> dict[str, Any]:
    """Read-only proof that native Codex and the relative MCP launcher can run."""
    root = Path(codex_home).expanduser().resolve(strict=False)
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
        output = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}".lower()
        plugin_commands_supported = (
            getattr(result, "returncode", 1) == 0
            and all(token in output for token in ("add", "marketplace", "list", "remove"))
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "canonical_root": str(self.canonical_root),
            "backup_paths": [str(path) for path in self.backup_paths],
            "commands": [list(command) for command in self.commands],
            "personal_skills_before": [entry.to_dict() for entry in self.personal_skills_before],
            "personal_skills_after": [entry.to_dict() for entry in self.personal_skills_after],
            "personal_skills_unchanged": compare_skill_inventories(
                self.personal_skills_before, self.personal_skills_after
            ),
        }


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


def _codex_marketplace_wrapper(root: Path, canonical_root: Path) -> tuple[Path, bool]:
    marketplaces_root = root / "marketplaces"
    resolved_marketplaces = marketplaces_root.resolve(strict=False)
    if (
        marketplaces_root.is_symlink()
        or (
            resolved_marketplaces != root
            and root not in resolved_marketplaces.parents
        )
    ):
        raise InstallBlocked(
            f"Codex marketplaces path escapes isolated profile: {marketplaces_root}"
        )
    wrapper = marketplaces_root / "samvil-codex"
    manifest = wrapper / ".claude-plugin" / "marketplace.json"
    plugin_link = wrapper / "samvil"
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
    expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if wrapper.exists():
        if (
            not manifest.is_file()
            or manifest.read_text(encoding="utf-8") != expected
            or not plugin_link.is_symlink()
            or plugin_link.resolve(strict=False) != canonical_root
        ):
            raise InstallBlocked(f"ambiguous Codex marketplace wrapper: {wrapper}")
        return wrapper, False
    marketplaces_root.mkdir(parents=True, exist_ok=True)
    temporary_wrapper = Path(
        tempfile.mkdtemp(prefix=".samvil-codex.", dir=marketplaces_root)
    )
    try:
        temporary_manifest = (
            temporary_wrapper / ".claude-plugin" / "marketplace.json"
        )
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


def execute_isolated_install(
    plan: CodexInstallPlan,
    *,
    codex_home: Path,
    command_runner: Any,
    migrate: bool = False,
) -> InstallReceipt:
    """Execute only inside an explicitly supplied isolated Codex root.

    This executor intentionally has no default home/config path. Callers must pass
    an explicit root and the runner receives a pinned ``CODEX_HOME`` environment.
    """

    if plan.blockers:
        raise InstallBlocked("; ".join(plan.blockers))
    root = Path(codex_home).expanduser().resolve(strict=False)
    if root == Path(root.anchor):
        raise InstallBlocked(f"isolated Codex root must not be a filesystem root: {root}")
    root.mkdir(parents=True, exist_ok=True)
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
    legacy_samvil_root = _configured_marketplace_root(config, "samvil")
    current_samvil_root = _configured_marketplace_root(config, "samvil-codex")
    wrapper_path = root / "marketplaces" / "samvil-codex"
    if wrapper_path.exists():
        _codex_marketplace_wrapper(root, plan.canonical_root)

    before = inventory_personal_skills(personal_root)
    migrated_paths = set()
    for action in plan.actions:
        if action.kind != "migrate_generated":
            continue
        candidate = action.path.expanduser().resolve(strict=False)
        migrated_paths.add(candidate.parent if candidate.name == "SKILL.md" else candidate)
    protected_before = tuple(entry for entry in before if entry.path not in migrated_paths)
    backup_paths: list[Path] = []
    commands: list[tuple[str, ...]] = []
    personal_snapshot_root: Path | None = None
    config_backup: Path | None = None
    wrapper = wrapper_path
    wrapper_created = False
    remove_legacy_marketplace = ("codex", "plugin", "marketplace", "remove", "samvil")
    remove_marketplace = ("codex", "plugin", "marketplace", "remove", "samvil-codex")
    command_env = {"CODEX_HOME": str(root), "HOME": str(root.parent)}
    moved_paths: list[tuple[Path, Path]] = []
    personal_snapshot_ready = False
    unexpected_quarantine: Path | None = None
    preserve_personal_snapshot = False

    def protected_inventory() -> tuple[SkillInventoryEntry, ...]:
        try:
            safe_child_directory(root, "skills", label="skills")
        except RuntimeLayoutError as exc:
            raise InstallBlocked(
                f"skills path escapes isolated profile: {personal_root}"
            ) from exc
        if _unsafe_personal_skill_links(personal_root):
            raise InstallBlocked("unsafe personal skill symlink detected")
        current = inventory_personal_skills(personal_root)
        return tuple(entry for entry in current if entry.path not in migrated_paths)

    def quarantine_root() -> Path:
        nonlocal unexpected_quarantine
        if unexpected_quarantine is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            unexpected_quarantine = (
                backups_root / f"unexpected-personal-skills-{stamp}"
            )
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
        current_by_path = {
            entry.path: entry for entry in protected_inventory()
        }
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

    def rollback_install() -> None:
        for backup, source in reversed(moved_paths):
            if backup.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(source)
        if config_backup is not None:
            _atomic_copy(config_backup, config)
        elif not config_existed:
            config.unlink(missing_ok=True)
        if wrapper_created:
            shutil.rmtree(wrapper, ignore_errors=True)
        restore_personal_skills()

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
        wrapper, wrapper_created = _codex_marketplace_wrapper(
            root, plan.canonical_root
        )
        add_marketplace = (
            "codex",
            "plugin",
            "marketplace",
            "add",
            str(wrapper),
        )
        add_plugin = ("codex", "plugin", "add", "samvil@samvil-codex")
        planned_commands = []
        if legacy_samvil_root is not None:
            planned_commands.append(remove_legacy_marketplace)
        if current_samvil_root is not None and current_samvil_root != wrapper:
            planned_commands.append(remove_marketplace)
        if current_samvil_root != wrapper:
            planned_commands.append(add_marketplace)
        planned_commands.append(add_plugin)

        for command in planned_commands:
            command_runner(command, command_env)
            commands.append(command)
            if not compare_skill_inventories(protected_before, protected_inventory()):
                raise InstallBlocked(
                    "personal Codex skill inventory changed during isolated install"
                )

        if migrate:
            for action in plan.actions:
                if action.kind != "migrate_generated":
                    continue
                source = action.path
                label = source.parent.name if source.name == "SKILL.md" else source.name
                backup = backups_root / f"{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
                backup.parent.mkdir(parents=True, exist_ok=True)
                source.replace(backup)
                moved_paths.append((backup, source))
                backup_paths.append(backup)

        protected_after = protected_inventory()
        if not compare_skill_inventories(protected_before, protected_after):
            raise InstallBlocked(
                "personal Codex skill inventory changed during isolated install"
            )
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
                raise InstallBlocked(
                    f"Codex rollback failed: {rollback_exc}{snapshot_note}"
                ) from rollback_exc
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


def _subprocess_runner(command: tuple[str, ...], env: dict[str, str]) -> None:
    subprocess.run(
        command,
        check=True,
        env={**os.environ, **env},
        text=True,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate the native SAMVIL Codex plugin")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--migrate", action="store_true")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    readiness = validate_activation_readiness(args.repo_root)
    if args.migrate:
        raise InstallBlocked(
            "legacy migration is unavailable until generated artifacts are classified"
        )
    environment = validate_cli_environment(args.codex_home)
    readiness["environment"] = environment
    readiness["blockers"] = [*readiness["blockers"], *environment["blockers"]]
    readiness["ready"] = not readiness["blockers"]
    if args.check:
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
        return 0 if readiness["ready"] else 1
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
        migrate=args.migrate,
    )
    payload = receipt.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else f"Codex native plugin activated: {canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "CodexCapabilityProbe",
    "CodexInstallPlan",
    "InstallBlocked",
    "InstallReceipt",
    "LegacyOwnership",
    "MigrationAction",
    "SkillInventoryEntry",
    "build_install_plan",
    "classify_generated_file",
    "classify_legacy_skill",
    "compare_skill_inventories",
    "inventory_personal_skills",
    "execute_isolated_install",
    "parse_capability_probe",
    "validate_marketplace_root",
    "validate_cli_environment",
]
