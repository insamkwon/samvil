"""Read-only Codex ownership and installation planning primitives.

Mutation is intentionally out of scope for this module's first contract.  The
planner produces deterministic, JSON-serializable evidence so a later executor
can refuse ambiguous user-owned state before changing anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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
    filesystem_root = Path(resolved.anchor)

    unsafe = (
        resolved == filesystem_root
        or resolved == home
        or home in resolved.parents
        or resolved == skills
        or skills in resolved.parents
        or resolved in skills.parents
    )
    if unsafe:
        raise ValueError(f"unsafe Codex marketplace root: {resolved}")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frontmatter_name(path: Path) -> str:
    match = _FRONTMATTER_NAME.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else path.parent.name


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
    for skill_file in sorted(root.glob("*/SKILL.md")):
        if skill_file.is_file():
            entries.append(
                SkillInventoryEntry(
                    path=skill_file.parent.resolve(),
                    name=_frontmatter_name(skill_file),
                    content_hash=_sha256(skill_file),
                )
            )
    return tuple(entries)


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


__all__ = [
    "CodexCapabilityProbe",
    "CodexInstallPlan",
    "LegacyOwnership",
    "MigrationAction",
    "SkillInventoryEntry",
    "build_install_plan",
    "classify_generated_file",
    "classify_legacy_skill",
    "compare_skill_inventories",
    "inventory_personal_skills",
    "parse_capability_probe",
    "validate_marketplace_root",
]
