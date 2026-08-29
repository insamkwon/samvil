"""Pure ownership and capability planning tests for Codex setup."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest
import samvil_mcp.codex_installer as installer
import samvil_mcp.codex_migration as migration
from samvil_mcp.codex_installer import (
    CodexCapabilityProbe,
    CodexInstallPlan,
    InstallBlocked,
    LegacyOwnership,
    MigrationAction,
    build_install_plan,
    classify_generated_file,
    classify_legacy_skill,
    compare_skill_inventories,
    inventory_personal_skills,
    parse_capability_probe,
    validate_activation_readiness,
    validate_cli_environment,
    validate_marketplace_root,
)

_execute_isolated_install = installer._execute_isolated_install_impl


class FakeNativeRegistry:
    def __init__(
        self,
        commands: list[tuple[tuple[str, ...], dict[str, str]]] | None = None,
    ) -> None:
        self.commands = commands if commands is not None else []
        self.marketplaces: dict[str, str] = {}
        self.plugins: set[str] = set()

    def apply(self, command: tuple[str, ...]) -> None:
        if command[:4] == ("codex", "plugin", "marketplace", "add"):
            source = command[-1]
            self.marketplaces[Path(source).name] = source
            return
        if command[:4] == ("codex", "plugin", "marketplace", "remove"):
            self.marketplaces.pop(command[-1], None)
            return
        if command[:3] == ("codex", "plugin", "add"):
            self.plugins.add(command[-1])
            return
        if command[:3] == ("codex", "plugin", "remove"):
            self.plugins.discard(command[-1])
            return
        raise AssertionError(f"unexpected fake Codex command: {command}")

    def run(self, command: tuple[str, ...], env: dict[str, str]) -> None:
        self.commands.append((command, env))
        self.apply(command)

    def read(self, _env: dict[str, str]) -> installer.NativeRegistrySnapshot:
        marketplaces = tuple(
            json.dumps(
                {
                    "name": name,
                    "root": source,
                    "marketplaceSource": {
                        "sourceType": "local",
                        "source": source,
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for name, source in sorted(self.marketplaces.items())
        )
        plugins = tuple(
            json.dumps(
                {
                    "pluginId": plugin_id,
                    "name": plugin_id.partition("@")[0],
                    "marketplaceName": plugin_id.partition("@")[2],
                    "installed": True,
                    "enabled": True,
                    "source": {
                        "source": "local",
                        "path": str(
                            Path(self.marketplaces[plugin_id.partition("@")[2]])
                            / plugin_id.partition("@")[0]
                        ),
                    },
                    "marketplaceSource": {
                        "sourceType": "local",
                        "source": self.marketplaces[plugin_id.partition("@")[2]],
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for plugin_id in sorted(self.plugins)
        )
        return installer.NativeRegistrySnapshot(
            "codex_cli",
            marketplaces,
            plugins,
            installer._bytes_sha256("\n".join(marketplaces).encode("utf-8")),
            installer._bytes_sha256("\n".join(plugins).encode("utf-8")),
            installer._bytes_sha256(b'{"marketplaces":[],"plugins":[]}'),
        )


_TEST_NATIVE_REGISTRIES: dict[Path, FakeNativeRegistry] = {}


def execute_isolated_install(*args: object, **kwargs: object) -> object:
    """Attach a persistent semantic registry double to migration unit tests."""

    if kwargs.get("migrate") and kwargs.get("registry_reader") is None:
        codex_home = installer._lexical_absolute(Path(kwargs["codex_home"]))
        registry = _TEST_NATIVE_REGISTRIES.setdefault(
            codex_home,
            FakeNativeRegistry(),
        )
        original_runner = kwargs["command_runner"]

        def verified_runner(
            command: tuple[str, ...],
            env: dict[str, str],
        ) -> object:
            result = original_runner(command, env)  # type: ignore[operator]
            registry.apply(command)
            return result

        kwargs["command_runner"] = verified_runner
        kwargs["registry_reader"] = registry.read
    return _execute_isolated_install(*args, **kwargs)  # type: ignore[arg-type]


def test_capability_probe_uses_feature_outputs_not_only_version(tmp_path: Path) -> None:
    probe = parse_capability_probe(
        help_output="plugin marketplace list --json\nplugin add",
        marketplace_output=json.dumps(
            {"marketplaces": [{"name": "samvil", "root": str(tmp_path)}]}
        ),
        plugin_output=json.dumps({"plugins": [{"name": "samvil", "enabled": True}]}),
        feature_output=json.dumps({"features": {"plugins": True, "mcp_servers": True}}),
    )

    assert probe.plugin_commands_supported is True
    assert probe.plugins_feature_enabled is True
    assert probe.marketplaces == ({"name": "samvil", "root": str(tmp_path)},)
    assert probe.plugins == ({"name": "samvil", "enabled": True},)
    assert probe.blockers == ()


@pytest.mark.parametrize(
    ("marketplaces", "plugins"),
    [
        (["not-an-object"], []),
        ([{"root": "/missing-name"}], []),
        ([], ["not-an-object"]),
        ([], [{"installed": True}]),
    ],
)
def test_cli_registry_snapshot_rejects_malformed_entries(
    marketplaces: list[object],
    plugins: list[object],
) -> None:
    with pytest.raises(InstallBlocked, match="inventory.*invalid entry"):
        installer._snapshot_from_cli_outputs(
            json.dumps({"marketplaces": marketplaces}),
            json.dumps({"installed": plugins}),
        )


@pytest.mark.parametrize(
    ("marketplaces", "plugins", "message"),
    [
        (
            [{"name": "samvil"}, {"name": "samvil"}],
            [],
            "duplicate name",
        ),
        (
            [],
            [
                {"pluginId": "samvil@samvil"},
                {"pluginId": "samvil@samvil"},
            ],
            "duplicate pluginId",
        ),
    ],
)
def test_cli_registry_snapshot_rejects_duplicate_identities(
    marketplaces: list[dict[str, str]],
    plugins: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(InstallBlocked, match=message):
        installer._snapshot_from_cli_outputs(
            json.dumps({"marketplaces": marketplaces}),
            json.dumps({"installed": plugins}),
        )


@pytest.mark.parametrize(
    "missing",
    (
        "marketplace_output_sha256",
        "plugin_output_sha256",
        "unrelated_fingerprint",
    ),
)
def test_stored_cli_registry_evidence_requires_all_digests(missing: str) -> None:
    snapshot = installer._snapshot_from_cli_outputs(
        json.dumps({"marketplaces": []}),
        json.dumps({"installed": []}),
    )
    payload = snapshot.to_dict()
    payload.pop(missing)

    with pytest.raises(InstallBlocked, match="missing an output hash"):
        installer._registry_snapshot_from_payload(payload)


def test_native_postcondition_rejects_plugin_source_outside_owned_wrapper(
    tmp_path: Path,
) -> None:
    wrapper = tmp_path / "profile" / "marketplaces" / "samvil-codex"
    foreign = tmp_path / "foreign-plugin"
    snapshot = installer.NativeRegistrySnapshot(
        "codex_cli",
        (
            json.dumps(
                {"name": "samvil-codex", "root": str(wrapper)},
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
        (
            json.dumps(
                {
                    "pluginId": "samvil@samvil-codex",
                    "installed": True,
                    "enabled": True,
                    "source": {"source": "local", "path": str(foreign)},
                    "marketplaceSource": {
                        "sourceType": "local",
                        "source": str(wrapper),
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )

    with pytest.raises(InstallBlocked, match="plugin source"):
        installer._verify_native_postcondition(snapshot, wrapper=wrapper)


def test_activation_readiness_requires_complete_public_surface() -> None:
    repo = Path(__file__).resolve().parents[2]
    readiness = validate_activation_readiness(repo)
    assert readiness["ready"] is True
    assert readiness["public_skills"] == ["resume", "run", "status"]


def test_activation_readiness_blocks_incomplete_copy(tmp_path: Path) -> None:
    (tmp_path / ".codex-plugin").mkdir()
    (tmp_path / ".codex-plugin" / "plugin.json").write_text("{}")
    (tmp_path / ".codex-mcp.json").write_text("{}")
    result = validate_activation_readiness(tmp_path)
    assert result["ready"] is False
    assert result["blockers"]


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink"])
def test_activation_readiness_blocks_unsafe_canonical_manifest(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    source = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    shutil.copytree(source / ".codex-plugin", repo / ".codex-plugin")
    shutil.copytree(source / "codex", repo / "codex")
    shutil.copytree(source / "scripts", repo / "scripts")
    shutil.copy2(source / ".codex-mcp.json", repo / ".codex-mcp.json")
    manifest = repo / ".codex-plugin" / "plugin.json"
    external = tmp_path / "external-plugin.json"
    external.write_bytes(manifest.read_bytes())
    manifest.unlink()
    if unsafe_kind == "symlink":
        manifest.symlink_to(external)
    else:
        manifest.hardlink_to(external)

    readiness = validate_activation_readiness(repo)
    migration_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=tmp_path / "profile",
    )

    assert readiness["ready"] is False
    assert any("unsafe" in blocker for blocker in readiness["blockers"])
    assert migration_plan.to_dict()["ready"] is False
    assert any("unsafe" in blocker for blocker in migration_plan.blockers)


_UNSET = object()


def _write_ready_activation_files(
    repo: Path,
    *,
    manifest: object = _UNSET,
    launcher: object = _UNSET,
) -> None:
    (repo / ".codex-plugin").mkdir()
    skills_root = repo / "codex" / "skills"
    for name in ("resume", "run", "status"):
        skill = skills_root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
    if manifest is _UNSET:
        manifest = {
            "skills": "./codex/skills/",
            "mcpServers": "./.codex-mcp.json",
        }
    if launcher is _UNSET:
        launcher = {
            "mcpServers": {
                "samvil-mcp": {
                    "command": "bash",
                    "args": ["./scripts/start-codex-mcp.sh"],
                }
            }
        }
    (repo / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (repo / ".codex-mcp.json").write_text(json.dumps(launcher), encoding="utf-8")
    launcher_script = repo / "scripts" / "start-codex-mcp.sh"
    launcher_script.parent.mkdir()
    launcher_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")


@pytest.mark.parametrize("document", [[], None, "not-an-object"])
def test_activation_readiness_rejects_non_object_manifest_json(
    tmp_path: Path, document: object
) -> None:
    _write_ready_activation_files(tmp_path, manifest=document)

    result = validate_activation_readiness(tmp_path)

    assert result["ready"] is False
    assert "Codex plugin manifest JSON must be an object" in result["blockers"]
    assert "Codex manifest does not use relative public surfaces" in result["blockers"]


@pytest.mark.parametrize("document", [[], None, "not-an-object"])
def test_activation_readiness_rejects_non_object_launcher_json(
    tmp_path: Path, document: object
) -> None:
    _write_ready_activation_files(tmp_path, launcher=document)

    result = validate_activation_readiness(tmp_path)

    assert result["ready"] is False
    assert "relative Codex MCP launcher JSON must be an object" in result["blockers"]
    assert "Codex MCP launcher is not the relative package launcher" in result["blockers"]


@pytest.mark.parametrize("mcp_servers", [["samvil-mcp"], True, 1, "samvil-mcp"])
def test_activation_readiness_rejects_non_object_launcher_mcp_servers(
    tmp_path: Path, mcp_servers: object
) -> None:
    _write_ready_activation_files(tmp_path, launcher={"mcpServers": mcp_servers})

    result = validate_activation_readiness(tmp_path)

    assert result["ready"] is False
    assert "Codex MCP launcher mcpServers must be an object" in result["blockers"]
    assert "Codex MCP launcher is not the relative package launcher" in result["blockers"]


def test_activation_readiness_retains_public_surface_blockers_after_wrong_json_shape(
    tmp_path: Path,
) -> None:
    _write_ready_activation_files(tmp_path, manifest=[])
    (tmp_path / "codex" / "skills" / "private").mkdir()
    (tmp_path / "codex" / "skills" / "status" / "SKILL.md").unlink()

    result = validate_activation_readiness(tmp_path)

    assert result["ready"] is False
    assert "Codex plugin manifest JSON must be an object" in result["blockers"]
    assert "Codex public skill surface must be exactly run/resume/status" in result["blockers"]
    assert "missing public Codex skill: status" in result["blockers"]


def test_activation_readiness_retains_invalid_json_blocker(tmp_path: Path) -> None:
    _write_ready_activation_files(tmp_path)
    (tmp_path / ".codex-plugin" / "plugin.json").write_text("{", encoding="utf-8")

    result = validate_activation_readiness(tmp_path)

    assert result["ready"] is False
    assert "Codex manifest or launcher is invalid JSON" in result["blockers"]


def test_activation_readiness_preserves_successful_return_schema(tmp_path: Path) -> None:
    _write_ready_activation_files(tmp_path)

    result = validate_activation_readiness(tmp_path)

    assert result == {
        "ready": True,
        "blockers": [],
        "public_skills": ["resume", "run", "status"],
        "manifest": str(tmp_path / ".codex-plugin" / "plugin.json"),
        "launcher": str(tmp_path / ".codex-mcp.json"),
    }


def test_cli_environment_check_requires_codex_uvx_and_plugin_commands(tmp_path: Path) -> None:
    missing = validate_cli_environment(
        tmp_path / ".codex",
        which=lambda _name: None,
        command_runner=lambda _command, _env: None,
    )
    assert missing["ready"] is False
    assert "codex binary is unavailable" in missing["blockers"]
    assert "uvx binary is unavailable" in missing["blockers"]

    class Result:
        returncode = 0
        stdout = "Commands: add marketplace list remove"
        stderr = ""

    ready = validate_cli_environment(
        tmp_path / ".codex",
        which=lambda name: f"/fake/{name}",
        command_runner=lambda _command, _env: Result(),
    )
    assert ready["ready"] is True
    assert ready["plugin_commands_supported"] is True


def test_cli_environment_check_blocks_symlinked_profile_before_command(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "user-owned-profile"
    codex_home = tmp_path / "profile-link"
    outside.mkdir()
    codex_home.symlink_to(outside, target_is_directory=True)
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []

    result = validate_cli_environment(
        codex_home,
        which=lambda name: f"/fake/{name}",
        command_runner=lambda command, env: commands.append((command, env)),
    )

    assert result["ready"] is False
    assert "Codex profile root is a symbolic link" in result["blockers"]
    assert commands == []
    assert list(outside.iterdir()) == []


def test_marketplace_root_must_not_claim_user_owned_codex_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    repo = tmp_path / "repo"
    skills.mkdir(parents=True)
    repo.mkdir()

    assert (
        validate_marketplace_root(repo, user_home=home, codex_skills_root=skills)
        == repo.resolve()
    )

    for unsafe in (home, home.parent, skills, skills.parent, Path(skills.anchor)):
        with pytest.raises(ValueError):
            validate_marketplace_root(unsafe, user_home=home, codex_skills_root=skills)


def test_marketplace_root_allows_normal_repository_below_user_home(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    repo = home / "dev" / "samvil"
    skills.mkdir(parents=True)
    repo.mkdir(parents=True)

    assert (
        validate_marketplace_root(repo, user_home=home, codex_skills_root=skills)
        == repo.resolve()
    )


def test_symlinked_marketplace_root_is_resolved_before_safety_check(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    skills.mkdir(parents=True)
    unsafe_link = tmp_path / "repo-link"
    unsafe_link.symlink_to(home, target_is_directory=True)

    with pytest.raises(ValueError):
        validate_marketplace_root(unsafe_link, user_home=home, codex_skills_root=skills)


def test_personal_skill_inventory_records_bare_name_and_content_hash(
    tmp_path: Path,
) -> None:
    skills = tmp_path / "skills"
    skill = skills / "pre-pr-review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: pre-pr-review\ndescription: review\n---\ncontent\n",
        encoding="utf-8",
    )

    inventory = inventory_personal_skills(skills)

    assert len(inventory) == 1
    assert inventory[0].name == "pre-pr-review"
    assert inventory[0].path == skill.resolve()
    assert len(inventory[0].content_hash) == 64
    assert "samvil:" not in inventory[0].name


def test_personal_skill_inventory_compare_detects_name_or_hash_drift(
    tmp_path: Path,
) -> None:
    skills = tmp_path / "skills"
    skill = skills / "commit"
    skill.mkdir(parents=True)
    file = skill / "SKILL.md"
    file.write_text("---\nname: commit\n---\noriginal\n", encoding="utf-8")
    before = inventory_personal_skills(skills)

    file.write_text("---\nname: samvil:commit\n---\nchanged\n", encoding="utf-8")
    after = inventory_personal_skills(skills)

    assert compare_skill_inventories(before, before) is True
    assert compare_skill_inventories(before, after) is False


def test_personal_skill_inventory_compare_detects_directory_replacement(
    tmp_path: Path,
) -> None:
    skills = tmp_path / "skills"
    original = skills / "original"
    replacement = skills / "replacement"
    original.mkdir(parents=True)
    manifest = original / "SKILL.md"
    manifest.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    before = inventory_personal_skills(skills)

    original.rename(replacement)
    after = inventory_personal_skills(skills)

    assert before[0].name == after[0].name
    assert before[0].content_hash == after[0].content_hash
    assert compare_skill_inventories(before, after) is False


def test_personal_skill_inventory_detects_support_file_loss(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    skill = skills / "custom-review"
    helper = skill / "scripts" / "helper.py"
    helper.parent.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: custom-review\n---\nReview with helper.\n",
        encoding="utf-8",
    )
    helper.write_text("print('helper')\n", encoding="utf-8")
    before = inventory_personal_skills(skills)

    helper.unlink()
    after = inventory_personal_skills(skills)

    assert compare_skill_inventories(before, after) is False


def test_personal_skill_inventory_does_not_follow_symlinked_root_ancestor(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    personal = outside / "skills" / "personal"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text(
        "---\nname: personal\n---\nkeep\n",
        encoding="utf-8",
    )
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(outside, target_is_directory=True)

    inventory = inventory_personal_skills(linked_parent / "skills")

    assert inventory == ()


def test_legacy_skill_classification_requires_byte_identity(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical" / "run" / "SKILL.md"
    legacy = tmp_path / "legacy" / "samvil-run" / "SKILL.md"
    canonical.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    canonical.write_text("canonical skill\n", encoding="utf-8")
    legacy.write_text(canonical.read_text(encoding="utf-8"), encoding="utf-8")

    generated = classify_legacy_skill(legacy, canonical)
    assert isinstance(generated, LegacyOwnership)
    assert generated.classification == "generated_legacy"

    legacy.write_text("user changed\n", encoding="utf-8")
    modified = classify_legacy_skill(legacy, canonical)
    assert modified.classification == "user_modified"
    assert modified.blocks_mutation is True


def test_legacy_skill_classifier_checks_the_whole_tree_and_rejects_links(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical" / "samvil-run"
    legacy = tmp_path / "legacy" / "samvil-run"
    (canonical / "scripts").mkdir(parents=True)
    (canonical / "SKILL.md").write_text("same\n", encoding="utf-8")
    (canonical / "scripts" / "helper.py").write_text("safe\n", encoding="utf-8")
    shutil.copytree(canonical, legacy)
    (legacy / "scripts" / "helper.py").write_text("changed\n", encoding="utf-8")

    changed = classify_legacy_skill(legacy / "SKILL.md", canonical / "SKILL.md")

    assert changed.classification == "user_modified"
    assert "tree" in changed.reason

    linked = tmp_path / "linked-skill"
    linked.symlink_to(canonical, target_is_directory=True)
    result = classify_legacy_skill(linked / "SKILL.md", canonical / "SKILL.md")
    assert result.classification == "user_modified"
    assert result.blocks_mutation is True


def test_legacy_skill_tree_hash_frames_file_content_and_following_entries(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical" / "samvil-run"
    legacy = tmp_path / "legacy" / "samvil-run"
    canonical.mkdir(parents=True)
    legacy.mkdir(parents=True)
    canonical_manifest = canonical / "SKILL.md"
    legacy_manifest = legacy / "SKILL.md"
    canonical_manifest.write_bytes(b"canonical\n")
    legacy_manifest.write_bytes(b"canonical\n")

    # Without an explicit content boundary, these bytes can impersonate the
    # serialization of the following empty file and make two different trees
    # hash to the same input stream before SHA-256 is applied.
    trailing = canonical / "z"
    trailing.write_bytes(b"")
    forged_entry = (
        len(b"z").to_bytes(8, "big")
        + b"z"
        + (trailing.stat().st_mode & 0o7777).to_bytes(4, "big")
        + b"F"
    )
    legacy_manifest.write_bytes(legacy_manifest.read_bytes() + forged_entry)

    result = classify_legacy_skill(
        legacy_manifest,
        canonical_manifest,
    )

    assert result.classification == "user_modified"
    assert result.blocks_mutation is True


def test_generated_file_classifier_distinguishes_ambiguous_content(
    tmp_path: Path,
) -> None:
    file = tmp_path / "AGENTS.md"
    expected = "generated\n"
    file.write_text(expected, encoding="utf-8")
    assert classify_generated_file(file, expected).classification == "generated_legacy"

    file.write_text(expected + "user section\n", encoding="utf-8")
    result = classify_generated_file(file, expected)
    assert result.classification == "user_modified"
    assert result.blocks_mutation is True


def test_generated_file_classifier_rejects_symlink_even_when_target_matches(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.md"
    target.write_text("generated\n", encoding="utf-8")
    linked = tmp_path / "AGENTS.md"
    linked.symlink_to(target)

    result = classify_generated_file(linked, "generated\n")

    assert result.classification == "user_modified"
    assert result.blocks_mutation is True
    assert result.path == linked.absolute()


def test_generated_file_classifier_fails_closed_on_invalid_utf8(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "AGENTS.md"
    candidate.write_bytes(b"\xff\xfe")

    result = classify_generated_file(candidate, "generated\n")

    assert result.classification == "user_modified"
    assert result.blocks_mutation is True
    assert "UTF-8" in result.reason


def test_legacy_skill_classifier_fails_closed_on_non_regular_candidate(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical" / "SKILL.md"
    candidate = tmp_path / "legacy" / "SKILL.md"
    canonical.parent.mkdir(parents=True)
    candidate.mkdir(parents=True)
    canonical.write_text("generated\n", encoding="utf-8")

    result = classify_legacy_skill(candidate, canonical)

    assert result.classification == "user_modified"
    assert result.blocks_mutation is True


def test_legacy_classifiers_reject_symlinked_parent_without_following_it(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical" / "skill" / "SKILL.md"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("generated\n", encoding="utf-8")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    (real_parent / "skill" / "SKILL.md").parent.mkdir()
    (real_parent / "skill" / "SKILL.md").write_text("generated\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    skill_result = classify_legacy_skill(
        linked_parent / "skill" / "SKILL.md",
        canonical,
    )
    generated_result = classify_generated_file(
        linked_parent / "AGENTS.md",
        "generated\n",
    )

    assert skill_result.blocks_mutation is True
    assert "ancestor" in skill_result.reason
    assert generated_result.blocks_mutation is True
    assert "symbolic link" in generated_result.reason


def test_install_plan_is_deterministic_and_read_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    repo.mkdir()
    (home / ".codex" / "skills" / "personal").mkdir(parents=True)
    personal = home / ".codex" / "skills" / "personal" / "SKILL.md"
    personal.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    before = personal.read_bytes()

    plan = build_install_plan(
        repo_root=repo,
        codex_home=home / ".codex",
        current_marketplace_root=home,
        capability_help="plugin marketplace list --json",
    )

    assert isinstance(plan, CodexInstallPlan)
    assert plan.canonical_root == repo.resolve()
    assert plan.blockers
    assert any(action.kind == "report_blocker" for action in plan.actions)
    json.dumps(plan.to_dict())
    assert personal.read_bytes() == before


def test_personal_skill_inventory_preserves_yaml_scalar_like_names(
    tmp_path: Path,
) -> None:
    skills = tmp_path / "profile" / ".codex" / "skills"
    expected = ("on", "off", "yes", "no", "null", "123")
    for index, name in enumerate(expected):
        manifest = skills / f"personal-{index}" / "SKILL.md"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            f"---\nname: {name}\n---\nkeep\n",
            encoding="utf-8",
        )

    inventory = inventory_personal_skills(skills)

    assert tuple(item.name for item in inventory) == expected


def test_check_and_install_admit_legacy_inventory_before_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    reserved = codex_home / "skills" / "personal-review" / "SKILL.md"
    reserved.parent.mkdir(parents=True)
    reserved.write_text(
        '---\nname: "ＳＡＭＶＩＬ:private"\n---\nkeep\n',
        encoding="utf-8",
    )
    config = codex_home / "config.toml"
    config.write_text(
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        "env     = {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        installer,
        "validate_cli_environment",
        lambda _root: pytest.fail(
            "legacy admission must precede the Codex CLI environment check"
        ),
    )
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    monkeypatch.setattr(
        installer,
        "_subprocess_runner",
        lambda command, env: commands.append((command, env)),
    )

    result = installer._main(
        [
            "--check",
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["ready"] is False
    assert payload["legacy_migration"]["ready"] is False
    assert any("reserved SAMVIL namespace" in item for item in payload["blockers"])
    assert any("legacy migration required" in item for item in payload["blockers"])

    with pytest.raises(InstallBlocked, match="reserved SAMVIL namespace"):
        installer._main(
            [
                "--install",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
            ]
        )
    assert commands == []


def test_install_rechecks_legacy_inventory_immediately_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    late_skill = codex_home / "skills" / "late-personal" / "SKILL.md"
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def change_profile_during_capability_check(_root: Path) -> dict[str, object]:
        late_skill.parent.mkdir(parents=True)
        late_skill.write_text(
            "---\nname: samvil:late-personal\n---\nkeep\n",
            encoding="utf-8",
        )
        return {"ready": True, "blockers": []}

    monkeypatch.setattr(
        installer,
        "validate_cli_environment",
        change_profile_during_capability_check,
    )
    monkeypatch.setattr(
        installer,
        "_subprocess_runner",
        lambda command, env: commands.append((command, env)),
    )

    with pytest.raises(
        InstallBlocked, match="profile changed during install admission"
    ):
        installer._main(
            [
                "--install",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
            ]
        )

    assert late_skill.read_text(encoding="utf-8").endswith("keep\n")
    assert commands == []
    assert not (codex_home / "marketplaces").exists()


def test_direct_executor_admits_legacy_inventory_before_writes(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    personal = codex_home / "skills" / "personal-review" / "SKILL.md"
    personal.parent.mkdir(parents=True)
    personal.write_text(
        "---\nname: samvil:private\n---\nkeep\n",
        encoding="utf-8",
    )
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    with pytest.raises(InstallBlocked, match="reserved SAMVIL namespace"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert personal.read_text(encoding="utf-8").endswith("keep\n")
    assert commands == []
    assert not (codex_home / "marketplaces").exists()


def test_public_executor_requires_native_readback_before_any_write(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "profile" / ".codex"
    commands: list[tuple[str, ...]] = []

    with pytest.raises(InstallBlocked, match="machine-readable registry readback"):
        installer.execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, _env: commands.append(command),
        )

    assert commands == []
    assert not codex_home.exists()


def test_registry_read_failure_before_mutation_is_plain_blocker() -> None:
    def broken_reader(_env: dict[str, str]) -> installer.NativeRegistrySnapshot:
        raise RuntimeError("injected pre-mutation readback failure")

    with pytest.raises(InstallBlocked) as raised:
        installer._read_native_registry(
            broken_reader,
            {},
            mutation_started=False,
        )

    assert type(raised.value) is InstallBlocked
    assert "before native mutation" in str(raised.value)


def test_registry_read_failure_after_mutation_requires_recovery() -> None:
    def broken_reader(_env: dict[str, str]) -> installer.NativeRegistrySnapshot:
        raise RuntimeError("injected post-mutation readback failure")

    with pytest.raises(installer.NativeRecoveryRequired, match="after native mutation"):
        installer._read_native_registry(
            broken_reader,
            {},
            mutation_started=True,
        )


def test_direct_executor_blocks_generated_legacy_action_before_writes(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    before = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    with pytest.raises(InstallBlocked, match="legacy migration required"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    after = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert commands == []
    assert not (codex_home / "marketplaces").exists()


def test_clean_cli_install_rechecks_and_activates_only_the_supplied_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "isolated-profile" / ".codex"
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    registry = FakeNativeRegistry(commands)
    monkeypatch.setattr(
        installer,
        "validate_cli_environment",
        lambda _root: {"ready": True, "blockers": []},
    )
    monkeypatch.setattr(
        installer,
        "_subprocess_runner",
        registry.run,
    )
    monkeypatch.setattr(installer, "_subprocess_registry_reader", registry.read)

    result = installer._main(
        [
            "--install",
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["mode"] == "install"
    assert [command for command, _env in commands] == [
        (
            "codex",
            "plugin",
            "marketplace",
            "add",
            str((codex_home / "marketplaces" / "samvil-codex").resolve()),
        ),
        ("codex", "plugin", "add", "samvil@samvil-codex"),
    ]
    assert all(env["CODEX_HOME"] == str(codex_home.resolve()) for _cmd, env in commands)
    assert (codex_home / "marketplaces" / "samvil-codex" / "samvil").resolve() == repo


def test_cli_migrate_probes_a_temporary_profile_then_applies_the_sealed_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "isolated-profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    probed_roots: list[Path] = []
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    registry = FakeNativeRegistry(commands)

    def ready(root: Path) -> dict[str, object]:
        probed_roots.append(root)
        assert root != codex_home
        assert not codex_home.joinpath("backups").exists()
        return {"ready": True, "blockers": []}

    monkeypatch.setattr(installer, "validate_cli_environment", ready)
    monkeypatch.setattr(
        installer,
        "_subprocess_runner",
        registry.run,
    )
    monkeypatch.setattr(installer, "_subprocess_registry_reader", registry.read)

    result = installer._main(
        [
            "--migrate",
            "--expected-plan-sha256",
            checked.to_dict()["plan_sha256"],
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["mode"] == "migrate"
    assert payload["legacy_plan_sha256"] == checked.to_dict()["plan_sha256"]
    assert len(probed_roots) == 1
    assert not legacy.exists()
    assert commands
    assert all(env["CODEX_HOME"] == str(codex_home.resolve()) for _cmd, env in commands)


def test_migrate_cli_subprocess_uses_only_explicit_profile_with_fake_codex(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "explicit-profile"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    ambient = tmp_path / "ambient-profile"
    ambient.mkdir()
    sentinel = ambient / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "codex.log"
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        'printf "%s|%s\\n" "$CODEX_HOME" "$*" >> "$FAKE_CODEX_LOG"\n'
        'marketplace_state="$CODEX_HOME/.fake-marketplace-source"\n'
        'plugin_state="$CODEX_HOME/.fake-plugin-id"\n'
        'if [ "$1 $2" = "plugin --help" ]; then\n'
        '  echo "Commands: add marketplace list remove"\n'
        'elif [ "$1 $2 $3 $4" = "plugin marketplace list --json" ]; then\n'
        '  if [ -f "$marketplace_state" ]; then\n'
        '    source_path=$(sed -n "1p" "$marketplace_state")\n'
        '    printf \'{"marketplaces":[{"name":"samvil-codex","root":"%s","marketplaceSource":{"sourceType":"local","source":"%s"}}]}\\n\' "$source_path" "$source_path"\n'
        "  else\n"
        "    printf '{\"marketplaces\":[]}\\n'\n"
        "  fi\n"
        'elif [ "$1 $2 $3" = "plugin list --json" ]; then\n'
        '  if [ -f "$plugin_state" ]; then\n'
        '    plugin_id=$(sed -n "1p" "$plugin_state")\n'
        '    source_path=$(sed -n "1p" "$marketplace_state")\n'
        '    printf \'{"installed":[{"pluginId":"%s","name":"samvil","marketplaceName":"samvil-codex","installed":true,"enabled":true,"source":{"source":"local","path":"%s/samvil"},"marketplaceSource":{"sourceType":"local","source":"%s"}}]}\\n\' "$plugin_id" "$source_path" "$source_path"\n'
        "  else\n"
        "    printf '{\"installed\":[]}\\n'\n"
        "  fi\n"
        'elif [ "$1 $2 $3" = "plugin marketplace add" ]; then\n'
        '  printf "%s\\n" "$4" > "$marketplace_state"\n'
        'elif [ "$1 $2 $3" = "plugin marketplace remove" ]; then\n'
        '  rm -f "$marketplace_state"\n'
        'elif [ "$1 $2" = "plugin add" ]; then\n'
        '  printf "%s\\n" "$3" > "$plugin_state"\n'
        'elif [ "$1 $2" = "plugin remove" ]; then\n'
        '  rm -f "$plugin_state"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    fake_uvx = fake_bin / "uvx"
    fake_uvx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_uvx.chmod(0o755)
    environment = {
        "CODEX_HOME": str(ambient),
        "FAKE_CODEX_LOG": str(command_log),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(repo / "mcp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "samvil_mcp.codex_installer",
            "--migrate",
            "--dry-run",
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    plan_sha = json.loads(checked.stdout)["plan_sha256"]

    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "samvil_mcp.codex_installer",
            "--migrate",
            "--expected-plan-sha256",
            plan_sha,
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert applied.returncode == 0, applied.stderr
    payload = json.loads(applied.stdout)
    assert payload["mode"] == "migrate"
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert list(ambient.iterdir()) == [sentinel]
    logged = command_log.read_text(encoding="utf-8").splitlines()
    target_commands = [line for line in logged if line.startswith(f"{codex_home}|")]
    target_mutations = [
        line
        for line in target_commands
        if "|plugin marketplace add " in line or "|plugin add " in line
    ]
    assert target_mutations == [
        f"{codex_home}|plugin marketplace add {codex_home / 'marketplaces' / 'samvil-codex'}",
        f"{codex_home}|plugin add samvil@samvil-codex",
    ]
    assert f"{codex_home}|plugin marketplace list --json" in target_commands
    assert f"{codex_home}|plugin list --json" in target_commands
    assert all(not line.startswith(f"{ambient}|") for line in logged)
    assert any(
        "|plugin --help" in line and not line.startswith(f"{codex_home}|")
        for line in logged
    )


def test_isolated_executor_backups_config_and_preserves_personal_skills(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    personal = codex_home / "skills" / "commit"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text(
        "---\nname: commit\n---\nkeep\n", encoding="utf-8"
    )
    config = codex_home / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    original = '[marketplaces.other]\nsource_type = "local"\nsource = "/other"\n'
    config.write_text(original, encoding="utf-8")
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []

    plan = CodexInstallPlan(
        canonical_root=repo.resolve(),
        capability=CodexCapabilityProbe(True, True),
        actions=(),
    )
    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
    )

    assert commands == [
        (
            (
                "codex",
                "plugin",
                "marketplace",
                "add",
                str((codex_home / "marketplaces" / "samvil-codex").resolve()),
            ),
            {
                "CODEX_HOME": str(codex_home.resolve()),
                "HOME": str(codex_home.resolve().parent),
            },
        ),
        (
            ("codex", "plugin", "add", "samvil@samvil-codex"),
            {
                "CODEX_HOME": str(codex_home.resolve()),
                "HOME": str(codex_home.resolve().parent),
            },
        ),
    ]
    assert receipt.to_dict()["personal_skills_unchanged"] is True
    assert receipt.backup_paths
    assert config.read_text(encoding="utf-8") == original
    assert (codex_home / "skills" / "commit" / "SKILL.md").exists()
    assert (
        codex_home / "marketplaces" / "samvil-codex" / "samvil"
    ).resolve() == repo.resolve()


def test_isolated_executor_blocks_unproven_existing_samvil_marketplace_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    config.write_text(
        '[marketplaces.samvil]\nsource_type = "local"\nsource = "/old/root"\n',
        encoding="utf-8",
    )
    commands = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    with pytest.raises(InstallBlocked, match="not a proven SAMVIL legacy"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert config.read_text(encoding="utf-8").endswith('source = "/old/root"\n')


def test_isolated_executor_blocks_invalid_config_before_commands(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    config.write_text("[broken", encoding="utf-8")
    commands = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    with pytest.raises(InstallBlocked, match="invalid Codex config TOML"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert config.read_text(encoding="utf-8") == "[broken"


def test_isolated_executor_restores_config_when_plugin_add_fails(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = '[marketplaces.other]\nsource_type = "local"\nsource = "/other"\n'
    config.write_text(original, encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    calls = 0

    def failing_runner(_command, _env):
        nonlocal calls
        calls += 1
        config.write_text(
            '[marketplaces.samvil]\nsource = "/partial"\n', encoding="utf-8"
        )
        if calls == 2:
            raise RuntimeError("plugin add failed")

    with pytest.raises(InstallBlocked, match="config restored"):
        execute_isolated_install(
            plan, codex_home=codex_home, command_runner=failing_runner
        )

    assert config.read_text(encoding="utf-8") == original
    assert not (codex_home / "marketplaces" / "samvil-codex").exists()


def test_isolated_executor_compensates_registry_when_plugin_add_fails(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    registered_marketplaces: set[str] = set()
    registered_plugins: set[str] = set()
    observed: list[tuple[str, ...]] = []

    def stateful_runner(command: tuple[str, ...], _env: dict[str, str]) -> None:
        observed.append(command)
        if command[:4] == ("codex", "plugin", "marketplace", "add"):
            registered_marketplaces.add("samvil-codex")
            return
        if command == ("codex", "plugin", "add", "samvil@samvil-codex"):
            registered_plugins.add("samvil@samvil-codex")
            raise RuntimeError("plugin add failed after marketplace registration")
        if command == (
            "codex",
            "plugin",
            "marketplace",
            "remove",
            "samvil-codex",
        ):
            registered_marketplaces.discard("samvil-codex")
            return
        if command == (
            "codex",
            "plugin",
            "remove",
            "samvil@samvil-codex",
        ):
            registered_plugins.discard("samvil@samvil-codex")
            return
        raise AssertionError(f"unexpected command: {command}")

    def stateful_reader(_env: dict[str, str]) -> installer.NativeRegistrySnapshot:
        marketplaces = tuple(
            json.dumps(
                {
                    "name": name,
                    "root": str(codex_home / "marketplaces" / name),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for name in sorted(registered_marketplaces)
        )
        plugins = tuple(
            json.dumps(
                {
                    "pluginId": plugin_id,
                    "installed": True,
                    "enabled": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for plugin_id in sorted(registered_plugins)
        )
        return installer.NativeRegistrySnapshot(
            "codex_cli",
            marketplaces,
            plugins,
        )

    with pytest.raises(InstallBlocked, match="config restored"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=stateful_runner,
            registry_reader=stateful_reader,
        )

    wrapper = codex_home / "marketplaces" / "samvil-codex"
    assert observed == [
        ("codex", "plugin", "marketplace", "add", str(wrapper.resolve())),
        ("codex", "plugin", "add", "samvil@samvil-codex"),
        ("codex", "plugin", "remove", "samvil@samvil-codex"),
        ("codex", "plugin", "marketplace", "remove", "samvil-codex"),
    ]
    assert registered_marketplaces == set()
    assert registered_plugins == set()
    assert not wrapper.exists()


def test_isolated_executor_never_deletes_a_concurrently_replaced_wrapper(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    wrapper = codex_home / "marketplaces" / "samvil-codex"
    sentinel = wrapper / "USER-SENTINEL.txt"

    def replace_wrapper_then_fail(
        _command: tuple[str, ...],
        _env: dict[str, str],
    ) -> None:
        shutil.rmtree(wrapper)
        wrapper.mkdir(parents=True)
        sentinel.write_text("keep\n", encoding="utf-8")
        raise RuntimeError("injected activation failure after wrapper replacement")

    with pytest.raises(installer.NativeRecoveryRequired, match="wrapper changed"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=replace_wrapper_then_fail,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_isolated_executor_preserves_concurrent_unrelated_config_edit_on_rollback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    config.write_text('model = "before"\n', encoding="utf-8")
    registry = FakeNativeRegistry()

    def mutate_registry_then_fail(
        command: tuple[str, ...],
        env: dict[str, str],
    ) -> None:
        registry.run(command, env)
        if command == ("codex", "plugin", "add", "samvil@samvil-codex"):
            config.write_text('model = "user-new"\n', encoding="utf-8")
            raise RuntimeError("injected failure after concurrent user edit")

    with pytest.raises(
        installer.NativeRecoveryRequired,
        match="unrelated Codex config changed during native rollback",
    ):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=mutate_registry_then_fail,
            registry_reader=registry.read,
        )

    assert config.read_text(encoding="utf-8") == 'model = "user-new"\n'
    assert registry.marketplaces == {}
    assert registry.plugins == set()


def test_isolated_executor_accepts_codex_newline_normalization(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = b'# keep\r\nmodel = "gpt-5"\r\n\r\n[features]\r\nplugins = true\r\n'
    config.write_bytes(original)
    registry = FakeNativeRegistry()

    def normalize_like_codex(
        command: tuple[str, ...],
        env: dict[str, str],
    ) -> None:
        registry.run(command, env)
        config.write_bytes(config.read_bytes().replace(b"\r\n", b"\n"))

    receipt = execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=normalize_like_codex,
        registry_reader=registry.read,
    )

    assert receipt.native_registry_after is not None
    assert config.read_bytes() == original.replace(b"\r\n", b"\n")
    assert registry.plugins == {"samvil@samvil-codex"}


def test_unrelated_config_projection_ignores_owned_table_separator_churn(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '# user comment\nmodel = "gpt-5"\n\n'
        '[marketplaces.samvil]\nsource = "/legacy"\n\n'
        '[plugins."samvil@samvil"]\nenabled = true\n',
        encoding="utf-8",
    )
    before = installer._unrelated_config_projection(config)

    # Codex 0.144.1 can leave structural blank lines around the replacement
    # SAMVIL tables when it retires the legacy marketplace.
    config.write_text(
        '# user comment\nmodel = "gpt-5"\n\n\n'
        '[marketplaces.samvil-codex]\nsource = "/native"\n\n'
        '[plugins."samvil@samvil-codex"]\nenabled = true\n',
        encoding="utf-8",
    )

    assert installer._unrelated_config_projection(config) == before


def test_isolated_executor_detects_unrelated_comment_drift(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    config.write_text('# keep\nmodel = "gpt-5"\n', encoding="utf-8")
    registry = FakeNativeRegistry()

    def edit_comment(
        command: tuple[str, ...],
        env: dict[str, str],
    ) -> None:
        registry.run(command, env)
        config.write_text('# changed\nmodel = "gpt-5"\n', encoding="utf-8")

    with pytest.raises(
        installer.NativeRecoveryRequired,
        match="unrelated Codex config changed during native rollback",
    ):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=edit_comment,
            registry_reader=registry.read,
        )

    assert config.read_text(encoding="utf-8").startswith("# changed\n")


def test_isolated_executor_restores_original_newlines_after_native_failure(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = b'# keep\r\nmodel = "gpt-5"\r\n'
    config.write_bytes(original)
    registry = FakeNativeRegistry()

    def normalize_then_fail(
        command: tuple[str, ...],
        env: dict[str, str],
    ) -> None:
        registry.run(command, env)
        config.write_bytes(config.read_bytes().replace(b"\r\n", b"\n"))
        if command == ("codex", "plugin", "add", "samvil@samvil-codex"):
            raise RuntimeError("injected native failure")

    with pytest.raises(InstallBlocked, match="config restored"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=normalize_then_fail,
            registry_reader=registry.read,
        )

    assert config.read_bytes() == original
    assert registry.marketplaces == {}
    assert registry.plugins == set()


def _write_proven_legacy_registry(config: Path, repo: Path) -> None:
    manifest = repo / ".claude-plugin" / "marketplace.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "name": "samvil",
                "plugins": [{"name": "samvil", "source": "./"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "[marketplaces.samvil]\n"
        'source_type = "local"\n'
        f'source = "{repo}"\n\n'
        '[plugins."samvil@samvil"]\n'
        "enabled = true\n",
        encoding="utf-8",
    )


def test_legacy_registry_at_canonical_path_requires_legacy_manifest_proof(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "codex-home" / ".codex"
    config = codex_home / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[marketplaces.samvil]\n"
        'source_type = "local"\n'
        f'source = "{repo}"\n\n'
        '[plugins."samvil@samvil"]\n'
        "enabled = true\n",
        encoding="utf-8",
    )

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert any("not a proven SAMVIL legacy" in item for item in plan.blockers)
    assert plan.native_registry_actions == ()


def test_native_migration_activates_new_plugin_before_retiring_legacy(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    _write_proven_legacy_registry(codex_home / "config.toml", repo)
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    registry = FakeNativeRegistry(commands)
    registry.marketplaces["samvil"] = str(repo)
    registry.plugins.add("samvil@samvil")

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=registry.run,
        registry_reader=registry.read,
        allow_legacy_registry_migration=True,
    )

    mutations = [command for command, _env in commands]
    assert mutations == [
        (
            "codex",
            "plugin",
            "marketplace",
            "add",
            str((codex_home / "marketplaces" / "samvil-codex").resolve()),
        ),
        ("codex", "plugin", "add", "samvil@samvil-codex"),
        ("codex", "plugin", "remove", "samvil@samvil"),
        ("codex", "plugin", "marketplace", "remove", "samvil"),
    ]
    assert registry.marketplaces == {
        "samvil-codex": str((codex_home / "marketplaces" / "samvil-codex").resolve())
    }
    assert registry.plugins == {"samvil@samvil-codex"}


def test_native_migration_keeps_legacy_active_when_new_plugin_add_fails(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    _write_proven_legacy_registry(codex_home / "config.toml", repo)
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    registry = FakeNativeRegistry(commands)
    registry.marketplaces["samvil"] = str(repo)
    registry.plugins.add("samvil@samvil")

    def fail_before_new_plugin(
        command: tuple[str, ...],
        env: dict[str, str],
    ) -> None:
        if command == ("codex", "plugin", "add", "samvil@samvil-codex"):
            commands.append((command, env))
            raise RuntimeError("injected new plugin failure")
        registry.run(command, env)

    with pytest.raises(InstallBlocked, match="activation failed"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=fail_before_new_plugin,
            registry_reader=registry.read,
            allow_legacy_registry_migration=True,
        )

    assert registry.marketplaces == {"samvil": str(repo)}
    assert registry.plugins == {"samvil@samvil"}
    assert ("codex", "plugin", "remove", "samvil@samvil") not in [
        command for command, _env in commands
    ]


def test_isolated_executor_restores_personal_skills_when_activation_mutates_them(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    skill = codex_home / "skills" / "personal-review"
    helper = skill / "scripts" / "helper.py"
    repo.mkdir()
    helper.parent.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: personal-review\n---\nkeep\n",
        encoding="utf-8",
    )
    helper.write_text("print('keep')\n", encoding="utf-8")
    config = codex_home / "config.toml"
    original_config = '[marketplaces.other]\nsource = "/other"\n'
    config.write_text(original_config, encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    def mutating_runner(_command, _env):
        helper.unlink(missing_ok=True)
        config.write_text(
            '[marketplaces.samvil-codex]\nsource = "/partial"\n',
            encoding="utf-8",
        )

    with pytest.raises(InstallBlocked, match="personal Codex skill inventory"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=mutating_runner,
        )

    assert helper.read_text(encoding="utf-8") == "print('keep')\n"
    assert config.read_text(encoding="utf-8") == original_config
    assert not (codex_home / "marketplaces" / "samvil-codex").exists()


def test_isolated_executor_quarantines_personal_skill_added_during_failure(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    existing = codex_home / "skills" / "existing" / "SKILL.md"
    added = codex_home / "skills" / "added-during-install" / "SKILL.md"
    repo.mkdir()
    existing.parent.mkdir(parents=True)
    existing.write_text("---\nname: existing\n---\nkeep\n", encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    def mutating_runner(_command, _env):
        added.parent.mkdir(parents=True, exist_ok=True)
        added.write_text("---\nname: added\n---\nkeep\n", encoding="utf-8")

    with pytest.raises(InstallBlocked, match="personal Codex skill inventory"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=mutating_runner,
        )

    assert existing.is_file()
    assert not added.exists()
    quarantined = list(
        (codex_home / "backups").glob(
            "unexpected-personal-skills-*/added-during-install/SKILL.md"
        )
    )
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8").endswith("keep\n")


def test_isolated_executor_rollback_does_not_follow_runtime_skills_symlink(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    personal_root = codex_home / "skills"
    original_root = codex_home / "skills-moved-by-runner"
    personal = personal_root / "personal" / "SKILL.md"
    outside = tmp_path / "outside-skills"
    external = outside / "external" / "SKILL.md"
    repo.mkdir()
    personal.parent.mkdir(parents=True)
    personal.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    external.parent.mkdir(parents=True)
    external.write_text("---\nname: external\n---\nkeep\n", encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    def swapping_runner(_command, _env):
        personal_root.replace(original_root)
        personal_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstallBlocked, match="skills path escapes isolated profile"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=swapping_runner,
        )

    assert external.read_text(encoding="utf-8").endswith("keep\n")
    assert personal.is_file()
    assert personal_root.is_symlink() is False


def test_isolated_executor_rollback_does_not_follow_nested_skill_symlink(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    personal_root = codex_home / "skills"
    personal_dir = personal_root / "personal"
    personal = personal_dir / "SKILL.md"
    outside = tmp_path / "outside-skill"
    external = outside / "SKILL.md"
    sentinel = outside / "USER-DATA.txt"
    repo.mkdir()
    personal_dir.mkdir(parents=True)
    personal.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    outside.mkdir()
    external.write_text("---\nname: external\n---\nkeep\n", encoding="utf-8")
    sentinel.write_text("do not move\n", encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    def swapping_runner(_command, _env):
        shutil.rmtree(personal_dir)
        personal_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstallBlocked, match="unsafe personal skill symlink"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=swapping_runner,
        )

    assert sentinel.read_text(encoding="utf-8") == "do not move\n"
    assert external.is_file()
    assert personal.read_text(encoding="utf-8").endswith("keep\n")
    assert personal_dir.is_symlink() is False


def test_isolated_executor_blocks_symlink_inside_personal_skill_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    personal_dir = codex_home / "skills" / "personal"
    personal = personal_dir / "SKILL.md"
    outside = tmp_path / "outside-user-data.txt"
    helper = personal_dir / "helper.txt"
    repo.mkdir()
    personal_dir.mkdir(parents=True)
    personal.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    outside.write_text("before\n", encoding="utf-8")
    helper.symlink_to(outside)
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    runner_called = False

    def mutating_runner(_command, _env):
        nonlocal runner_called
        runner_called = True
        helper.write_text("after\n", encoding="utf-8")

    with pytest.raises(InstallBlocked, match="unsafe personal skill symlink"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=mutating_runner,
        )

    assert runner_called is False
    assert outside.read_text(encoding="utf-8") == "before\n"


def test_isolated_executor_preserves_snapshot_when_restore_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    helper = codex_home / "skills" / "personal" / "helper.txt"
    skill = helper.parent / "SKILL.md"
    repo.mkdir()
    helper.parent.mkdir(parents=True)
    skill.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    helper.write_text("before\n", encoding="utf-8")
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    original_copytree = shutil.copytree

    def fail_restore_copy(source, destination, *args, **kwargs):
        if Path(source).parent.name.startswith(".personal-skills."):
            raise OSError("injected restore copy failure")
        return original_copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copytree", fail_restore_copy)

    with pytest.raises(InstallBlocked, match="snapshot preserved"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: helper.write_text(
                "changed\n", encoding="utf-8"
            ),
        )

    assert helper.read_text(encoding="utf-8") == "changed\n"
    snapshots = list((codex_home / "backups").glob(".personal-skills.*"))
    assert len(snapshots) == 1
    assert (snapshots[0] / "personal" / "helper.txt").read_text(
        encoding="utf-8"
    ) == "before\n"


def test_isolated_executor_blocks_config_symlink_without_overwriting_target(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    target = tmp_path / "user-owned.toml"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    original = '[marketplaces.other]\nsource = "/other"\n'
    target.write_text(original, encoding="utf-8")
    personal = codex_home / "skills" / "personal" / "SKILL.md"
    personal.parent.mkdir(parents=True)
    personal.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    config = codex_home / "config.toml"
    config.symlink_to(target)
    plan = CodexInstallPlan(
        canonical_root=repo.resolve(),
        capability=CodexCapabilityProbe(True, True),
    )

    with pytest.raises(InstallBlocked, match="config symlink is not safe"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: (_ for _ in ()).throw(
                AssertionError("no command")
            ),
        )

    assert target.read_text(encoding="utf-8") == original
    assert config.is_symlink() is True
    assert list((codex_home / "backups").glob(".personal-skills.*")) == []


def test_isolated_executor_blocks_skills_parent_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    outside = tmp_path / "outside-skills"
    external_skill = outside / "personal" / "SKILL.md"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    external_skill.parent.mkdir(parents=True)
    external_skill.write_text("---\nname: personal\n---\nkeep\n", encoding="utf-8")
    (codex_home / "skills").symlink_to(outside, target_is_directory=True)

    with pytest.raises(InstallBlocked, match="skills path escapes isolated profile"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: None,
        )

    assert external_skill.read_text(encoding="utf-8").endswith("keep\n")
    assert sorted(path.name for path in outside.iterdir()) == ["personal"]


def test_direct_executor_blocks_symlinked_codex_profile_before_any_write(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "user-owned-profile"
    codex_home = tmp_path / "profile-link"
    repo.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n", encoding="utf-8")
    codex_home.symlink_to(outside, target_is_directory=True)
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []

    with pytest.raises(InstallBlocked, match="Codex profile root is a symbolic link"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert sorted(path.name for path in outside.iterdir()) == ["keep.txt"]


def test_direct_executor_blocks_symlinked_codex_profile_ancestor_before_any_write(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "user-owned-parent"
    linked_parent = tmp_path / "linked-parent"
    codex_home = linked_parent / ".codex"
    repo.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n", encoding="utf-8")
    linked_parent.symlink_to(outside, target_is_directory=True)
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []

    with pytest.raises(
        InstallBlocked,
        match="Codex profile path contains symbolic-link ancestor",
    ):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert sorted(path.name for path in outside.iterdir()) == ["keep.txt"]


def test_isolated_executor_blocks_ambiguous_codex_wrapper_before_commands(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    wrapper = codex_home / "marketplaces" / "samvil-codex"
    repo.mkdir()
    wrapper.mkdir(parents=True)
    (wrapper / "user-file.txt").write_text("keep\n", encoding="utf-8")
    commands = []

    with pytest.raises(InstallBlocked, match="ambiguous Codex marketplace wrapper"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert (wrapper / "user-file.txt").read_text(encoding="utf-8") == "keep\n"


def test_isolated_executor_cleans_partial_wrapper_when_symlink_creation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    wrapper = codex_home / "marketplaces" / "samvil-codex"
    repo.mkdir()
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    original_symlink_to = Path.symlink_to
    failed = False

    def fail_first_plugin_link(
        path: Path,
        target: Path,
        target_is_directory: bool = False,
    ) -> None:
        nonlocal failed
        if path.name == "samvil" and not failed:
            failed = True
            raise OSError("injected symlink failure")
        original_symlink_to(
            path,
            target,
            target_is_directory=target_is_directory,
        )

    monkeypatch.setattr(Path, "symlink_to", fail_first_plugin_link)

    with pytest.raises(InstallBlocked, match="injected symlink failure"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: None,
        )

    assert not wrapper.exists()
    assert list((codex_home / "marketplaces").iterdir()) == []

    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
    )

    assert receipt.canonical_root == repo.resolve()
    assert (wrapper / "samvil").resolve() == repo.resolve()


def test_isolated_executor_blocks_marketplaces_parent_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    outside = tmp_path / "user-owned-marketplaces"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    outside.mkdir()
    (codex_home / "marketplaces").symlink_to(outside, target_is_directory=True)
    commands = []

    with pytest.raises(
        InstallBlocked, match="marketplaces path escapes isolated profile"
    ):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert list(outside.iterdir()) == []


def test_isolated_executor_blocks_backups_parent_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    outside = tmp_path / "outside-backups"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    outside.mkdir()
    (codex_home / "config.toml").write_text(
        '[marketplaces.other]\nsource = "/other"\n', encoding="utf-8"
    )
    (codex_home / "backups").symlink_to(outside, target_is_directory=True)
    commands = []

    with pytest.raises(InstallBlocked, match="backups path escapes isolated profile"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
        )

    assert commands == []
    assert list(outside.iterdir()) == []


def test_isolated_executor_accepts_explicit_custom_codex_home_name(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "profiles" / "codex-work"
    repo.mkdir()
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    commands = []

    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
    )

    assert receipt.canonical_root == repo.resolve()
    assert commands
    assert all(env["CODEX_HOME"] == str(codex_home.resolve()) for _, env in commands)


def test_isolated_executor_refuses_blockers_and_unsafe_root(tmp_path: Path) -> None:
    plan = CodexInstallPlan(
        canonical_root=(tmp_path / "repo").resolve(),
        capability=CodexCapabilityProbe(False, False, blockers=("missing capability",)),
        blockers=("ambiguous user config",),
    )

    with pytest.raises(InstallBlocked):
        execute_isolated_install(
            plan,
            codex_home=tmp_path / "codex-home" / ".codex",
            command_runner=lambda _command, _env: None,
        )

    clean = CodexInstallPlan(
        canonical_root=(tmp_path / "repo").resolve(),
        capability=CodexCapabilityProbe(True, True),
    )
    with pytest.raises(InstallBlocked):
        execute_isolated_install(
            clean,
            codex_home=Path(tmp_path.anchor),
            command_runner=lambda _command, _env: None,
        )


def test_isolated_migrate_applies_only_rebuilt_generated_actions_and_keeps_backups(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    personal = codex_home / "skills" / "personal-review" / "SKILL.md"
    personal.parent.mkdir(parents=True)
    personal.write_text(
        "---\nname: personal-review\n---\nkeep\n",
        encoding="utf-8",
    )
    agents = codex_home / "AGENTS.md"
    agents.write_text(
        _generated_legacy_agents(repo, tmp_path / "old-samvil-clone"),
        encoding="utf-8",
    )
    config = codex_home / "config.toml"
    other_config = '[marketplaces.other]\nsource = "/other"\n\n'
    config.write_text(
        other_config
        + "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args    = ["-m", "samvil_mcp.server"]\n'
        + "env     = {}\n",
        encoding="utf-8",
    )
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    legacy_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
        expected_legacy_plan_sha256=legacy_plan.to_dict()["plan_sha256"],
    )

    assert receipt.mode == "migrate"
    assert (
        receipt.to_dict()["legacy_plan_sha256"] == legacy_plan.to_dict()["plan_sha256"]
    )
    assert receipt.to_dict()["migration_receipt_sha256"]
    assert not legacy_root.exists()
    assert not agents.exists()
    assert config.read_text(encoding="utf-8") == other_config
    assert personal.read_text(encoding="utf-8").endswith("keep\n")
    assert any(path.name.startswith("legacy-skill-") for path in receipt.backup_paths)
    assert any(path.name == "global-AGENTS.md" for path in receipt.backup_paths)
    assert any(path.name == "config.toml.before" for path in receipt.backup_paths)
    assert commands


def test_isolated_migrate_moves_canonical_link_tree_to_reversible_backup(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    canonical = repo / "skills" / "samvil-resume"
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / canonical.name
    legacy_root.mkdir(parents=True)
    for entry in canonical.iterdir():
        (legacy_root / entry.name).symlink_to(entry)

    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    receipt = execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert not legacy_root.exists()
    backup = next(
        path
        for path in receipt.backup_paths
        if path.name.startswith("legacy-skill-")
    )
    assert all(path.is_symlink() for path in backup.iterdir())
    assert all(
        path.resolve(strict=False) == canonical / path.name
        for path in backup.iterdir()
    )


def test_isolated_migrate_exact_retry_returns_byte_identical_receipt_without_commands(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    legacy_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
        expected_legacy_plan_sha256=legacy_plan.to_dict()["plan_sha256"],
    )
    first_commands = tuple(commands)
    second = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
        expected_legacy_plan_sha256=legacy_plan.to_dict()["plan_sha256"],
    )

    assert second.to_dict() == first.to_dict()
    assert json.dumps(second.to_dict(), indent=2) == json.dumps(
        first.to_dict(), indent=2
    )
    assert list(second.to_dict()["canonical_contract"]) == sorted(
        second.to_dict()["canonical_contract"]
    )
    assert tuple(commands) == first_commands
    journals = list(
        (codex_home / "backups" / "legacy-migrations").glob("*/journal.json")
    )
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["state"] == "committed"


def test_isolated_migrate_fresh_postcondition_retry_reuses_committed_receipt(
    tmp_path: Path,
) -> None:
    """A new dry-run hash after a successful migration must still replay safely."""

    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    first_commands = tuple(commands)
    backups_before = tuple(
        sorted(
            path.relative_to(codex_home / "backups").as_posix()
            for path in (codex_home / "backups").rglob("*")
            if path.is_file()
        )
    )
    postcondition = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    assert not postcondition.blockers
    assert not postcondition.actions
    assert postcondition.to_dict()["plan_sha256"] != first.legacy_plan_sha256

    second = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
        expected_legacy_plan_sha256=postcondition.to_dict()["plan_sha256"],
    )

    assert second.to_dict() == first.to_dict()
    assert tuple(commands) == first_commands
    transactions = list(
        (codex_home / "backups" / "legacy-migrations").iterdir()
    )
    assert len(transactions) == 1
    backups_after = tuple(
        sorted(path.relative_to(codex_home / "backups").as_posix()
               for path in (codex_home / "backups").rglob("*")
               if path.is_file())
    )
    assert backups_after == backups_before

    with pytest.raises(InstallBlocked, match="profile changed"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "arbitrary replay hash must not activate"
            ),
            migrate=True,
            expected_legacy_plan_sha256="0" * 64,
        )
    assert tuple(commands) == first_commands
    assert len(list((codex_home / "backups" / "legacy-migrations").iterdir())) == 1


def test_committed_migration_replay_rejects_canonical_contract_drift(
    tmp_path: Path,
) -> None:
    source_repo = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    shutil.copytree(source_repo / ".codex-plugin", repo / ".codex-plugin")
    shutil.copy2(source_repo / ".codex-mcp.json", repo / ".codex-mcp.json")
    shutil.copytree(source_repo / "codex", repo / "codex")
    (repo / "scripts").mkdir()
    shutil.copy2(
        source_repo / "scripts" / "start-codex-mcp.sh",
        repo / "scripts" / "start-codex-mcp.sh",
    )
    (repo / "skills").mkdir()
    shutil.copytree(
        source_repo / "skills" / "samvil-resume",
        repo / "skills" / "samvil-resume",
    )
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    commands: list[tuple[str, ...]] = []
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))

    execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, _env: commands.append(command),
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    first_commands = tuple(commands)
    manifest = repo / ".codex-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["description"] = "changed after committed migration"
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(InstallBlocked, match="canonical contract changed"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, _env: commands.append(command),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert tuple(commands) == first_commands
    assert (
        len(list((codex_home / "backups" / "legacy-migrations").glob("*/journal.json")))
        == 1
    )


def test_isolated_migrate_rejects_external_or_stale_actions_before_any_write(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    external = tmp_path / "user-owned.txt"
    external.write_text("keep\n", encoding="utf-8")
    plan = CodexInstallPlan(
        canonical_root=repo.resolve(),
        capability=CodexCapabilityProbe(True, True),
        actions=(
            MigrationAction(
                "migrate_generated",
                external.resolve(),
                "forged action",
                "legacy_skill_tree",
                "0" * 64,
            ),
        ),
    )

    clean_legacy_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=clean_legacy_plan.to_dict()["plan_sha256"],
    )

    assert receipt.mode == "migrate"
    assert external.read_text(encoding="utf-8") == "keep\n"
    assert codex_home.exists()


def test_isolated_migrate_requires_a_matching_internal_plan_before_any_write(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    before = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }

    with pytest.raises(InstallBlocked, match="matching checked legacy plan"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "plan blocker must precede commands"
            ),
            migrate=True,
        )

    after = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not (codex_home / "backups").exists()


def test_migrate_registry_readback_failure_occurs_before_legacy_staging(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    agents = codex_home / "AGENTS.md"
    agents.write_text(
        _generated_legacy_agents(repo, tmp_path / "old-samvil-clone"),
        encoding="utf-8",
    )
    config = codex_home / "config.toml"
    config.write_text(
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        "env     = {}\n",
        encoding="utf-8",
    )
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    legacy_identity = (legacy.lstat().st_dev, legacy.lstat().st_ino)
    legacy_hash = installer._skill_tree_hash(legacy)
    agents_identity = (agents.lstat().st_dev, agents.lstat().st_ino)
    agents_bytes = agents.read_bytes()
    config_identity = (config.lstat().st_dev, config.lstat().st_ino)
    config_bytes = config.read_bytes()
    commands: list[tuple[str, ...]] = []

    def broken_reader(_env: dict[str, str]) -> installer.NativeRegistrySnapshot:
        raise RuntimeError("injected readback failure")

    with pytest.raises(
        InstallBlocked,
        match="registry preflight failed before migration",
    ):
        _execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda command, _env: commands.append(command),
            registry_reader=broken_reader,
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert (legacy.lstat().st_dev, legacy.lstat().st_ino) == legacy_identity
    assert installer._skill_tree_hash(legacy) == legacy_hash
    assert (agents.lstat().st_dev, agents.lstat().st_ino) == agents_identity
    assert agents.read_bytes() == agents_bytes
    assert (config.lstat().st_dev, config.lstat().st_ino) == config_identity
    assert config.read_bytes() == config_bytes
    assert commands == []
    assert not (codex_home / "backups").exists()


def test_isolated_migrate_restores_every_legacy_artifact_when_activation_fails(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    agents = codex_home / "AGENTS.md"
    agents.write_text(
        _generated_legacy_agents(repo, tmp_path / "old-samvil-clone"),
        encoding="utf-8",
    )
    config = codex_home / "config.toml"
    original_config = (
        '[marketplaces.other]\nsource = "/other"\n\n'
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        "env     = {}\n"
    )
    config.write_text(original_config, encoding="utf-8")
    legacy_hash = installer._skill_tree_hash(legacy_root)
    agents_bytes = agents.read_bytes()
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    def fail_activation(_command: tuple[str, ...], _env: dict[str, str]) -> None:
        raise RuntimeError("injected activation failure")

    with pytest.raises(InstallBlocked, match="activation failure"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=fail_activation,
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert installer._skill_tree_hash(legacy_root) == legacy_hash
    assert agents.read_bytes() == agents_bytes
    assert config.read_text(encoding="utf-8") == original_config
    journals = list(
        (codex_home / "backups" / "legacy-migrations").glob("*/journal.json")
    )
    assert len(journals) == 1
    journal = json.loads(journals[0].read_text(encoding="utf-8"))
    assert journal["state"] == "rolled_back"
    assert all(not Path(action["backup"]).exists() for action in journal["actions"])


def test_isolated_migrate_rejects_plan_drift_without_moving_user_artifacts(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    manifest = legacy_root / "SKILL.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8"
    )
    edited = manifest.read_bytes()

    with pytest.raises(InstallBlocked, match="differs from canonical source"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "drift must block before activation"
            ),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert manifest.read_bytes() == edited
    assert not (codex_home / "backups").exists()


def test_isolated_migrate_seals_canonical_activation_contract_before_writes(
    tmp_path: Path,
) -> None:
    source_repo = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    shutil.copytree(source_repo / ".codex-plugin", repo / ".codex-plugin")
    shutil.copy2(source_repo / ".codex-mcp.json", repo / ".codex-mcp.json")
    shutil.copytree(source_repo / "codex", repo / "codex")
    (repo / "scripts").mkdir()
    shutil.copy2(
        source_repo / "scripts" / "start-codex-mcp.sh",
        repo / "scripts" / "start-codex-mcp.sh",
    )
    (repo / "skills").mkdir()
    shutil.copytree(
        source_repo / "skills" / "samvil-resume",
        repo / "skills" / "samvil-resume",
    )
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    manifest = repo / ".codex-plugin" / "plugin.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(InstallBlocked, match="rerun the check"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "canonical drift must block activation"
            ),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert legacy.exists()
    assert not (codex_home / "backups").exists()


def test_isolated_migrate_refuses_tampered_journal_without_touching_external_path(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy_root = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy_root)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    external = tmp_path / "external-user-file"
    external.write_text("keep\n", encoding="utf-8")
    journal_path = next(
        (codex_home / "backups" / "legacy-migrations").glob("*/journal.json")
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["actions"][0]["source"] = str(external)
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(InstallBlocked, match="unsafe source"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "tampered journal must block before activation"
            ),
            migrate=True,
            expected_legacy_plan_sha256=first.legacy_plan_sha256,
        )

    assert external.read_text(encoding="utf-8") == "keep\n"


def test_isolated_migrate_recovers_a_crash_during_legacy_staging_then_retries(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan_sha = checked.to_dict()["plan_sha256"]
    transition_id = f"20260828T010203000000Z-{plan_sha[:12]}-deadbeef"
    transaction = codex_home / "backups" / "legacy-migrations" / transition_id
    transaction.mkdir(parents=True)
    journal_path = transaction / "journal.json"
    journal = {
        "schema_version": migration._JOURNAL_SCHEMA,
        "migration_transition_id": transition_id,
        "legacy_plan_sha256": plan_sha,
        "canonical_root": str(repo),
        "codex_home": str(codex_home),
        "created_at": "2026-08-28T01:02:03+00:00",
        "native_activation_started": False,
        "actions": migration._journal_actions(checked, transaction),
    }
    migration._write_journal(journal_path, journal, "prepared")
    action = journal["actions"][0]
    legacy.replace(Path(action["backup"]))
    action["staged"] = True
    migration._write_journal(journal_path, journal, "staging")
    commands: list[tuple[str, ...]] = []

    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    with pytest.raises(InstallBlocked, match="rerun the check"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, _env: commands.append(command),
            migrate=True,
            expected_legacy_plan_sha256=plan_sha,
        )

    recovered = json.loads(journal_path.read_text(encoding="utf-8"))
    assert recovered["state"] == "rolled_back"
    assert legacy.exists()
    assert commands == []
    rechecked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, _env: commands.append(command),
        migrate=True,
        expected_legacy_plan_sha256=rechecked.to_dict()["plan_sha256"],
    )

    assert receipt.mode == "migrate"
    assert commands
    assert not legacy.exists()
    assert (
        len(list((codex_home / "backups" / "legacy-migrations").glob("*/journal.json")))
        == 2
    )


def test_isolated_migrate_blocks_uncertain_crash_after_native_activation_begins(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan_sha = checked.to_dict()["plan_sha256"]
    transition_id = f"20260828T010203000000Z-{plan_sha[:12]}-feedface"
    transaction = codex_home / "backups" / "legacy-migrations" / transition_id
    transaction.mkdir(parents=True)
    journal_path = transaction / "journal.json"
    journal = {
        "schema_version": migration._JOURNAL_SCHEMA,
        "migration_transition_id": transition_id,
        "legacy_plan_sha256": plan_sha,
        "canonical_root": str(repo),
        "codex_home": str(codex_home),
        "created_at": "2026-08-28T01:02:03+00:00",
        "native_activation_started": True,
        "actions": migration._journal_actions(checked, transaction),
    }
    action = journal["actions"][0]
    legacy.replace(Path(action["backup"]))
    action["staged"] = True
    migration._write_journal(journal_path, journal, "native_activating")

    with pytest.raises(InstallBlocked, match="manual recovery is required"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "uncertain recovery must block activation"
            ),
            migrate=True,
            expected_legacy_plan_sha256=plan_sha,
        )

    assert not legacy.exists()
    assert Path(action["backup"]).exists()
    assert (
        json.loads(journal_path.read_text(encoding="utf-8"))["state"]
        == "native_activating"
    )


def test_isolated_migrate_replay_rejects_a_changed_legacy_backup(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    skill_backup = next(
        path for path in first.backup_paths if path.name.startswith("legacy-skill-")
    )
    manifest = skill_backup / "SKILL.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8"
    )

    with pytest.raises(InstallBlocked, match="backup hash changed"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "invalid replay must not activate"
            ),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )


def test_isolated_migrate_finishes_commit_decided_receipt_without_commands(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    commands: list[tuple[str, ...]] = []
    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, _env: commands.append(command),
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    first_commands = tuple(commands)
    transaction = (
        codex_home
        / "backups"
        / "legacy-migrations"
        / str(first.migration_transition_id)
    )
    journal_path = transaction / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["state"] = "commit_decided"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    (transaction / "receipt.json").unlink()

    replay = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, _env: commands.append(command),
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert replay.to_dict() == first.to_dict()
    assert tuple(commands) == first_commands
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "committed"
    assert (transaction / "receipt.json").is_file()


def test_commit_decided_replay_rejects_foreign_transition_before_promotion(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    plan = CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True))
    first = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )
    transaction = (
        codex_home
        / "backups"
        / "legacy-migrations"
        / str(first.migration_transition_id)
    )
    journal_path = transaction / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["state"] = "commit_decided"
    journal["receipt"]["migration_transition_id"] = (
        f"20260828T010203000000Z-{checked.to_dict()['plan_sha256'][:12]}-deadbeef"
    )
    unsigned = dict(journal["receipt"])
    unsigned.pop("migration_receipt_sha256", None)
    journal["receipt"]["migration_receipt_sha256"] = migration._receipt_digest(unsigned)
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    (transaction / "receipt.json").unlink()

    with pytest.raises(InstallBlocked, match="does not match its journal"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "invalid commit decision must not run commands"
            ),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    persisted = json.loads(journal_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "commit_decided"
    assert not (transaction / "receipt.json").exists()


def test_isolated_migrate_preserves_unrelated_config_bytes_and_crlf(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    prefix = b'# keep this comment\r\n[marketplaces.other]\r\nsource = "/other"\r\n\r\n'
    suffix = b"[features]\r\nplugins = true\r\n"
    generated = (
        b"[mcp_servers.samvil-mcp]\r\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\r\n'.encode()
        + b'args    = ["-m", "samvil_mcp.server"]\r\n'
        + b"env     = {}\r\n"
    )
    original = prefix + generated + suffix
    config.write_bytes(original)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    receipt = execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_bytes() == prefix + suffix
    backup = next(
        path for path in receipt.backup_paths if path.name == "config.toml.before"
    )
    assert backup.read_bytes() == original


def test_isolated_migrate_moves_normalized_mcp_tool_overrides_to_native_plugin(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args = ["-m", "samvil_mcp.server"]\n\n'
        "[mcp_servers.samvil-mcp.tools.begin_stage]\n"
        'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == (
        '[plugins."samvil@samvil-codex".tools.begin_stage]\n'
        'approval_mode = "approve"\n'
    )
    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert "mcp_servers" not in parsed
    assert (
        parsed["plugins"]["samvil@samvil-codex"]["tools"]["begin_stage"]
        == {"approval_mode": "approve"}
    )


def test_isolated_migrate_preserves_multiline_strings_that_resemble_tool_tables(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    instructions = (
        "developer_instructions = \"\"\"\n"
        "[mcp_servers.samvil-mcp.tools.begin_stage]\n"
        "Keep this documentation unchanged.\n"
        "\"\"\"\n\n"
    )
    original = (
        instructions
        + "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n\n'
        + "[mcp_servers.samvil-mcp.tools.begin_stage]\n"
        + 'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == (
        instructions
        + '[plugins."samvil@samvil-codex".tools.begin_stage]\n'
        + 'approval_mode = "approve"\n'
    )


def test_isolated_migrate_preserves_escaped_triple_quotes_in_multiline_strings(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    instructions = (
        "developer_instructions = \"\"\"before\n"
        "escaped quotes: \\\"\"\"\n"
        "[mcp_servers.samvil-mcp.tools.DO_NOT_CHANGE]\n"
        "after\n\"\"\"\n\n"
    )
    original = (
        instructions
        + "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == instructions


def test_isolated_migrate_handles_literal_triple_quotes_without_escape_rules(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    instructions = (
        "developer_instructions = '''before\n"
        "backslash delimiter: " "\\'''" "\n"
        "[mcp_servers.samvil-mcp.tools.DO_NOT_CHANGE]\n"
        'approval_mode = "approve"\n'
        "notes = '''after\n"
        "[mcp_servers.samvil-mcp.tools.KEEP_TEXT]\n"
        "still text\n"
        "'''\n\n"
    )
    original = (
        instructions
        + "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == (
        instructions.replace(
            "[mcp_servers.samvil-mcp.tools.DO_NOT_CHANGE]",
            '[plugins."samvil@samvil-codex".tools.DO_NOT_CHANGE]',
        )
    )


def test_isolated_migrate_moves_quoted_normalized_mcp_tool_overrides(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n\n'
        + '[mcp_servers."samvil-mcp".tools.begin_stage]\n'
        + 'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == (
        '[plugins."samvil@samvil-codex".tools.begin_stage]\n'
        + 'approval_mode = "approve"\n'
    )


def test_isolated_migrate_preserves_comments_on_normalized_tool_headers(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n\n'
        + "[mcp_servers.samvil-mcp.tools.begin_stage] # keep approval note\n"
        + 'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert config.read_text(encoding="utf-8") == (
        '[plugins."samvil@samvil-codex".tools.begin_stage] # keep approval note\n'
        + 'approval_mode = "approve"\n'
    )


def test_isolated_migrate_blocks_unrewritable_quoted_tool_key(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        + f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        + 'args = ["-m", "samvil_mcp.server"]\n\n'
        + '[mcp_servers.samvil-mcp.tools."begin]stage"]\n'
        + 'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert checked.to_dict()["ready"] is True
    with pytest.raises(InstallBlocked, match="ambiguous"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: None,
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert config.read_text(encoding="utf-8") == original


def test_isolated_migrate_never_overwrites_a_concurrent_user_file_during_rollback(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    agents = codex_home / "AGENTS.md"
    agents.parent.mkdir(parents=True)
    agents.write_text(
        _generated_legacy_agents(repo, tmp_path / "old-samvil-clone"),
        encoding="utf-8",
    )
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    def concurrent_user_write_then_fail(
        _command: tuple[str, ...],
        _env: dict[str, str],
    ) -> None:
        agents.write_text("user-created replacement\n", encoding="utf-8")
        raise RuntimeError("injected activation failure")

    with pytest.raises(InstallBlocked, match="rollback failed"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=concurrent_user_write_then_fail,
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert agents.read_text(encoding="utf-8") == "user-created replacement\n"
    transaction = next((codex_home / "backups" / "legacy-migrations").iterdir())
    journal = json.loads((transaction / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "rollback_failed"
    backup = next(
        Path(action["backup"])
        for action in journal["actions"]
        if action["artifact_kind"] == "global_agents"
    )
    assert backup.is_file()


def test_isolated_migrate_fails_closed_without_profile_locking_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    monkeypatch.setattr(migration, "fcntl", None)

    with pytest.raises(InstallBlocked, match="profile locking support"):
        execute_isolated_install(
            CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "missing lock support must block activation"
            ),
            migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )

    assert legacy.exists()


def test_profile_lock_retries_transient_concurrent_create_enoent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".codex"
    root.mkdir()
    real_open = os.open
    transient_failures = 0

    def transient_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal transient_failures
        if (
            path == ".samvil-legacy-migration.lock"
            and flags & os.O_CREAT
            and transient_failures == 0
        ):
            transient_failures += 1
            raise FileNotFoundError(2, "simulated concurrent create race", path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(migration.os, "open", transient_open)

    with migration._profile_lock(root):
        assert transient_failures == 1

    assert (root / ".samvil-legacy-migration.lock").is_file()


def test_isolated_migrate_concurrent_processes_share_one_receipt_and_command_set(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    command_log = tmp_path / "commands.log"
    helper = tmp_path / "concurrent_migrate.py"
    helper.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import sys
            import time
            from pathlib import Path

            from samvil_mcp.codex_installer import (
                CodexCapabilityProbe,
                CodexInstallPlan,
                NativeRegistrySnapshot,
                execute_isolated_install,
            )

            repo = Path(sys.argv[1])
            codex_home = Path(sys.argv[2])
            plan_sha = sys.argv[3]
            command_log = Path(sys.argv[4])
            state_file = codex_home / ".test-native-registry.json"

            def load_state():
                if not state_file.exists():
                    return {"marketplaces": {}, "plugins": []}
                return json.loads(state_file.read_text(encoding="utf-8"))

            def save_state(state):
                temporary = state_file.with_name(
                    f"{state_file.name}.{os.getpid()}.tmp"
                )
                temporary.write_text(
                    json.dumps(state, sort_keys=True),
                    encoding="utf-8",
                )
                temporary.replace(state_file)

            def reader(_env):
                state = load_state()
                marketplaces = tuple(
                    json.dumps(
                        {
                            "name": name,
                            "root": source,
                            "marketplaceSource": {
                                "sourceType": "local",
                                "source": source,
                            },
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for name, source in sorted(state["marketplaces"].items())
                )
                plugins = tuple(
                    json.dumps(
                        {
                            "pluginId": plugin_id,
                            "name": plugin_id.partition("@")[0],
                            "marketplaceName": plugin_id.partition("@")[2],
                            "installed": True,
                            "enabled": True,
                            "source": {
                                "source": "local",
                                "path": str(
                                    Path(
                                        state["marketplaces"][
                                            plugin_id.partition("@")[2]
                                        ]
                                    )
                                    / plugin_id.partition("@")[0]
                                ),
                            },
                            "marketplaceSource": {
                                "sourceType": "local",
                                "source": state["marketplaces"][
                                    plugin_id.partition("@")[2]
                                ],
                            },
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for plugin_id in sorted(state["plugins"])
                )
                digest = "0" * 64
                return NativeRegistrySnapshot(
                    "codex_cli",
                    marketplaces,
                    plugins,
                    digest,
                    digest,
                    digest,
                )

            def runner(command, _env):
                with command_log.open("a", encoding="utf-8") as handle:
                    handle.write(" ".join(command) + "\\n")
                    handle.flush()
                state = load_state()
                if command[:4] == ("codex", "plugin", "marketplace", "add"):
                    source = command[-1]
                    state["marketplaces"][Path(source).name] = source
                elif command[:4] == ("codex", "plugin", "marketplace", "remove"):
                    state["marketplaces"].pop(command[-1], None)
                elif command[:3] == ("codex", "plugin", "add"):
                    if command[-1] not in state["plugins"]:
                        state["plugins"].append(command[-1])
                elif command[:3] == ("codex", "plugin", "remove"):
                    state["plugins"] = [
                        item for item in state["plugins"] if item != command[-1]
                    ]
                else:
                    raise AssertionError(f"unexpected command: {command}")
                save_state(state)
                time.sleep(0.15)

            receipt = execute_isolated_install(
                CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
                codex_home=codex_home,
                command_runner=runner,
                registry_reader=reader,
                migrate=True,
                expected_legacy_plan_sha256=plan_sha,
            )
            print(json.dumps(receipt.to_dict(), sort_keys=True))
            """
        ),
        encoding="utf-8",
    )
    arguments = [
        sys.executable,
        str(helper),
        str(repo),
        str(codex_home),
        checked.to_dict()["plan_sha256"],
        str(command_log),
    ]
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(repo / "mcp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }

    first = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    second = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    first_stdout, first_stderr = first.communicate(timeout=20)
    second_stdout, second_stderr = second.communicate(timeout=20)

    assert first.returncode == 0, first_stderr
    assert second.returncode == 0, second_stderr
    assert json.loads(first_stdout) == json.loads(second_stdout)
    assert command_log.read_text(encoding="utf-8").splitlines() == [
        f"codex plugin marketplace add {codex_home / 'marketplaces' / 'samvil-codex'}",
        "codex plugin add samvil@samvil-codex",
    ]
    assert (
        len(list((codex_home / "backups" / "legacy-migrations").glob("*/receipt.json")))
        == 1
    )


def test_isolated_migrate_ignores_ambient_codex_home_and_mutates_only_explicit_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    ambient = tmp_path / "ambient-codex-home"
    ambient.mkdir()
    sentinel = ambient / "user-owned.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(ambient))
    codex_home = tmp_path / "explicit-codex-home"
    legacy = codex_home / "skills" / "samvil-resume"
    shutil.copytree(repo / "skills" / "samvil-resume", legacy)
    checked = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )
    command_environments: list[dict[str, str]] = []

    execute_isolated_install(
        CodexInstallPlan(repo.resolve(), CodexCapabilityProbe(True, True)),
        codex_home=codex_home,
        command_runner=lambda _command, env: command_environments.append(env),
        migrate=True,
        expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
    )

    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert list(ambient.iterdir()) == [sentinel]
    assert command_environments
    assert all(
        env["CODEX_HOME"] == str(codex_home.resolve())
        for env in command_environments
    )


def test_setup_shell_routes_codex_to_native_installer_without_legacy_global_writes() -> (
    None
):
    repo = Path(__file__).resolve().parents[2]
    script = (repo / "scripts" / "setup-codex.sh").read_text(encoding="utf-8")

    assert '"$PYTHON_BIN" -P -m samvil_mcp.codex_installer' in script
    assert script.index("[1/5] Python") < script.index('if [[ "$HOST" == "codex" ]]')
    assert '_install_agents "$HOME/.codex"' not in script
    assert "[mcp_servers.samvil-mcp]" not in script
    assert "--dry-run" in script
    assert 'json.load(open(sys.argv[1], encoding="utf-8"))["plan_sha256"]' in script
    assert '--expected-plan-sha256 "$expected_plan_sha256"' in script


def _generated_legacy_agents(repo: Path, installed_root: Path | None = None) -> str:
    source = (repo / "AGENTS.md").read_text(encoding="utf-8")
    root = installed_root or repo
    return source.replace("references/", f"{root}/references/").replace(
        "scripts/", f"{root}/scripts/"
    )


def test_legacy_migration_dry_run_classifies_exact_skill_tree_without_writes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "samvil-example"
    (canonical / "scripts").mkdir(parents=True)
    (canonical / "SKILL.md").write_text(
        "---\nname: samvil-example\n---\ncanonical\n", encoding="utf-8"
    )
    (canonical / "scripts" / "helper.py").write_text(
        "print('canonical')\n", encoding="utf-8"
    )
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-example"
    shutil.copytree(canonical, legacy)
    personal = codex_home / "skills" / "personal-review"
    personal.mkdir()
    personal_file = personal / "SKILL.md"
    personal_file.write_text(
        "---\nname: personal-review\n---\nkeep\n", encoding="utf-8"
    )
    before = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    payload = plan.to_dict()
    assert payload["ready"] is True
    assert len(payload["plan_sha256"]) == 64
    assert [item["name"] for item in payload["personal_skills"]] == ["personal-review"]
    assert [item["artifact_kind"] for item in payload["artifacts"]] == [
        "legacy_skill_tree"
    ]
    assert payload["artifacts"][0]["classification"] == "generated_legacy"
    assert len(payload["actions"]) == 1
    action = payload["actions"][0]
    assert action["kind"] == "migrate_generated"
    assert action["path"] == str(legacy.resolve())
    assert action["reason"] == "legacy skill tree is byte-identical to canonical source"
    assert action["artifact_kind"] == "legacy_skill_tree"
    assert action["expected_hash"] == payload["artifacts"][0]["content_hash"]
    assert all(
        isinstance(action[field], int)
        for field in (
            "expected_device",
            "expected_inode",
            "expected_mode",
            "expected_size",
            "expected_nlink",
            "expected_uid",
            "expected_ctime_ns",
        )
    )
    assert (
        plan.to_dict()
        == installer.build_legacy_migration_plan(
            repo_root=repo,
            codex_home=codex_home,
        ).to_dict()
    )
    after = {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in codex_home.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_legacy_migration_dry_run_matches_historical_repo_skill_tree(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    canonical = repo / "skills" / "samvil-resume"
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / canonical.name
    shutil.copytree(canonical, legacy)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = plan.artifacts[0]
    assert artifact.artifact_kind == "legacy_skill_tree"
    assert artifact.classification == "generated_legacy"
    assert artifact.expected_hash == artifact.content_hash
    assert plan.to_dict()["ready"] is True


def test_legacy_migration_dry_run_recognizes_canonical_skill_file_links(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "samvil-example"
    canonical.mkdir(parents=True)
    (canonical / "SKILL.md").write_text("canonical\n", encoding="utf-8")
    (canonical / "SKILL.legacy.md").write_text("legacy\n", encoding="utf-8")
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-example"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").symlink_to(canonical / "SKILL.md")
    (legacy / "SKILL.legacy.md").symlink_to(canonical / "SKILL.legacy.md")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = plan.artifacts[0]
    assert plan.to_dict()["ready"] is True
    assert artifact.classification == "generated_legacy"
    assert artifact.reason == "legacy skill tree links exactly to canonical source"
    assert len(plan.actions) == 1


def test_legacy_migration_dry_run_blocks_canonical_link_tree_after_target_drift(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "samvil-example"
    canonical.mkdir(parents=True)
    manifest = canonical / "SKILL.md"
    manifest.write_text("canonical\n", encoding="utf-8")
    foreign = tmp_path / "foreign" / "SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("foreign\n", encoding="utf-8")
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-example"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").symlink_to(foreign)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = plan.artifacts[0]
    assert artifact.classification == "user_modified"
    assert artifact.blocks_mutation is True
    assert plan.to_dict()["ready"] is False


@pytest.mark.parametrize(
    "mutation",
    ("content", "file_mode", "directory_mode", "symlink", "hardlink"),
)
def test_legacy_migration_dry_run_blocks_ambiguous_skill_tree(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "samvil-example"
    canonical.mkdir(parents=True)
    (canonical / "SKILL.md").write_text("canonical\n", encoding="utf-8")
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-example"
    shutil.copytree(canonical, legacy)
    if mutation == "content":
        (legacy / "SKILL.md").write_text("changed\n", encoding="utf-8")
    elif mutation == "file_mode":
        manifest = legacy / "SKILL.md"
        manifest.chmod((manifest.stat().st_mode & 0o777) ^ 0o111)
    elif mutation == "directory_mode":
        legacy.chmod((legacy.stat().st_mode & 0o777) ^ 0o011)
    elif mutation == "symlink":
        outside = tmp_path / "outside"
        outside.write_text("outside\n", encoding="utf-8")
        (legacy / "outside-link").symlink_to(outside)
    else:
        outside = tmp_path / "outside"
        outside.write_text("outside\n", encoding="utf-8")
        (legacy / "outside-hardlink").hardlink_to(outside)
    before = legacy.lstat()

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = plan.to_dict()["artifacts"][0]
    assert artifact["classification"] == "user_modified"
    assert artifact["blocks_mutation"] is True
    assert plan.to_dict()["ready"] is False
    assert not any(action.kind == "migrate_generated" for action in plan.actions)
    assert legacy.lstat().st_ino == before.st_ino


def test_legacy_migration_dry_run_blocks_unsafe_profile_and_skill_roots(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    real_profile = tmp_path / "real-profile"
    real_profile.mkdir()
    linked_profile = tmp_path / "linked-profile"
    linked_profile.symlink_to(real_profile, target_is_directory=True)

    linked_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=linked_profile,
    )

    assert linked_plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "codex_profile_root"
        for artifact in linked_plan.artifacts
    )

    profile = tmp_path / "profile" / ".codex"
    profile.mkdir(parents=True)
    (profile / "skills").write_text("not a directory\n", encoding="utf-8")
    skills_plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=profile,
    )

    assert skills_plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "legacy_skill_root"
        for artifact in skills_plan.artifacts
    )


def test_legacy_migration_dry_run_blocks_filesystem_root_profile(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=Path(tmp_path.anchor),
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "codex_profile_root"
        and "filesystem root" in artifact.reason
        for artifact in plan.artifacts
    )


def test_legacy_migration_dry_run_blocks_symlinked_profile_ancestor(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    profile_parent = tmp_path / "profile-parent"
    profile_parent.symlink_to(real_parent, target_is_directory=True)
    profile = profile_parent / ".codex"
    (real_parent / ".codex" / "skills" / "samvil-example").mkdir(parents=True)
    (real_parent / ".codex" / "skills" / "samvil-example" / "SKILL.md").write_text(
        "user content\n", encoding="utf-8"
    )

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=profile,
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "codex_profile_root" and "ancestor" in artifact.reason
        for artifact in plan.artifacts
    )


def test_legacy_migration_dry_run_blocks_unsafe_personal_skill_links(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    personal = codex_home / "skills" / "personal-review"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text(
        "---\nname: personal-review\n---\nkeep\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("keep outside\n", encoding="utf-8")
    (personal / "outside-link").symlink_to(outside)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "personal_skill_tree"
        and artifact.path == personal.absolute()
        and artifact.blocks_mutation
        for artifact in plan.artifacts
    )
    assert outside.read_text(encoding="utf-8") == "keep outside\n"


@pytest.mark.parametrize(
    "claimed_name",
    (
        "samvil:private",
        "SAMVIL:private",
        "ſamvil:private",
        "ＳＡＭＶＩＬ:private",
        '"samvil:private"',
        "'samvil:private'",
    ),
)
def test_legacy_migration_dry_run_blocks_personal_skill_claiming_samvil_namespace(
    tmp_path: Path,
    claimed_name: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    personal = codex_home / "skills" / "personal-review"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text(
        f"---\nname: {claimed_name}\n---\nkeep\n",
        encoding="utf-8",
    )

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "personal_skill_tree"
        and "reserved SAMVIL namespace" in artifact.reason
        for artifact in plan.artifacts
    )


def test_legacy_migration_dry_run_reports_unreadable_personal_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    personal = codex_home / "skills" / "personal-review"
    personal.mkdir(parents=True)
    manifest = personal / "SKILL.md"
    manifest.write_bytes(b"\xff\xfe")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item for item in plan.artifacts if item.artifact_kind == "personal_skill_tree"
    )
    assert plan.to_dict()["ready"] is False
    assert "cannot be inventoried safely" in artifact.reason
    assert manifest.read_bytes() == b"\xff\xfe"


@pytest.mark.parametrize("filename", ("AGENTS.md", "config.toml"))
def test_legacy_migration_dry_run_reports_unreadable_profile_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    profile_file = codex_home / filename
    profile_file.write_text("placeholder\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def fail_profile_read(path: Path) -> bytes:
        if path == profile_file:
            raise PermissionError("injected unreadable profile file")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_profile_read)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.path == profile_file.absolute()
        and "cannot be read safely" in artifact.reason
        for artifact in plan.artifacts
    )


def test_legacy_migration_dry_run_reports_unreadable_skills_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    skills_root = codex_home / "skills"
    skills_root.mkdir(parents=True)
    original_iterdir = Path.iterdir

    def fail_skills_iteration(path: Path):
        if path == skills_root:
            raise PermissionError("injected unreadable skills directory")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fail_skills_iteration)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert any(
        artifact.artifact_kind == "legacy_skill_root"
        and "cannot be inventoried safely" in artifact.reason
        for artifact in plan.artifacts
    )


def test_legacy_migration_dry_run_requires_skill_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "samvil-example"
    canonical.mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    legacy = codex_home / "skills" / "samvil-example"
    legacy.mkdir(parents=True)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert "SKILL.md" in plan.artifacts[0].reason


def test_legacy_migration_dry_run_rejects_repo_inside_profile(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "profile" / ".codex"
    repo = codex_home / "skills" / "samvil-source"
    repo.mkdir(parents=True)

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    assert plan.to_dict()["ready"] is False
    assert any("unsafe Codex marketplace root" in blocker for blocker in plan.blockers)


@pytest.mark.parametrize(
    "skill_name",
    ("samvil-private", "SAMVIL-private", "ſamvil-private", "ＳＡＭＶＩＬ-private"),
)
def test_legacy_migration_dry_run_blocks_unknown_samvil_skill(
    tmp_path: Path,
    skill_name: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / "skills").mkdir(parents=True)
    codex_home = tmp_path / "profile" / ".codex"
    unknown = codex_home / "skills" / skill_name
    unknown.mkdir(parents=True)
    (unknown / "SKILL.md").write_text("user owned\n", encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = plan.to_dict()["artifacts"][0]
    assert artifact["path"] == str(unknown.resolve())
    assert artifact["classification"] == "user_modified"
    assert "canonical source is unavailable" in artifact["reason"]
    assert plan.blockers


def test_legacy_migration_dry_run_recognizes_generated_global_agents(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    agents = codex_home / "AGENTS.md"
    agents.write_text(
        _generated_legacy_agents(repo, tmp_path / "old-samvil-clone"),
        encoding="utf-8",
    )
    before = agents.read_bytes()

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "global_agents"
    )
    assert artifact["classification"] == "generated_legacy"
    assert any(
        action.kind == "migrate_generated" and action.path == agents.resolve()
        for action in plan.actions
    )
    assert agents.read_bytes() == before


def test_legacy_migration_dry_run_blocks_global_agents_with_mixed_roots(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    agents = codex_home / "AGENTS.md"
    original = _generated_legacy_agents(repo, tmp_path / "old-one")
    original = original.replace(
        f"{tmp_path / 'old-one'}/scripts/",
        f"{tmp_path / 'old-two'}/scripts/",
        1,
    )
    agents.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item for item in plan.artifacts if item.artifact_kind == "global_agents"
    )
    assert artifact.classification == "user_modified"
    assert artifact.blocks_mutation is True
    assert plan.to_dict()["ready"] is False
    assert agents.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_blocks_modified_global_agents(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    agents = codex_home / "AGENTS.md"
    original = (
        _generated_legacy_agents(repo) + "\n## My personal instructions\nKeep this.\n"
    )
    agents.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "global_agents"
    )
    assert artifact["classification"] == "user_modified"
    assert artifact["blocks_mutation"] is True
    assert agents.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_recognizes_exact_direct_mcp_table(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        '[marketplaces.other]\nsource = "/other"\n\n'
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        "env     = {}\n"
    )
    config.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "generated_legacy"
    assert any(
        action.kind == "remove_generated_mcp_table"
        and action.expected_hash == artifact["content_hash"]
        for action in plan.actions
    )
    assert config.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_recognizes_codex_normalized_mcp_table_and_preserves_tools(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args = ["-m", "samvil_mcp.server"]\n\n'
        "[mcp_servers.samvil-mcp.tools.begin_stage]\n"
        'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "generated_legacy"
    assert not artifact["blocks_mutation"]
    assert any(action.kind == "remove_generated_mcp_table" for action in plan.actions)
    assert config.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_blocks_array_mcp_tool_overrides(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args = ["-m", "samvil_mcp.server"]\n\n'
        "[[mcp_servers.samvil-mcp.tools.begin_stage]]\n"
        'approval_mode = "approve"\n'
    )
    config.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.artifacts
        if item.artifact_kind == "direct_mcp_table"
    )
    assert artifact.classification == "user_modified"
    assert artifact.blocks_mutation is True
    assert "not TOML tables" in artifact.reason
    assert plan.to_dict()["ready"] is False
    assert config.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_recognizes_direct_mcp_from_old_repo_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "new-repo"
    repo.mkdir()
    old_repo = tmp_path / "old-repo"
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    config.write_text(
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{old_repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        "env     = {}\n",
        encoding="utf-8",
    )

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "generated_legacy"
    assert plan.to_dict()["ready"] is True


def test_legacy_migration_dry_run_blocks_modified_direct_mcp_table(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        "[mcp_servers.samvil-mcp]\n"
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args    = ["-m", "samvil_mcp.server"]\n'
        'env     = { USER_FLAG = "keep" }\n'
    )
    config.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "user_modified"
    assert artifact["blocks_mutation"] is True
    assert not any(
        action.kind == "remove_generated_mcp_table" for action in plan.actions
    )
    assert config.read_text(encoding="utf-8") == original


def test_legacy_migration_dry_run_blocks_reformatted_direct_mcp_table(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    codex_home = tmp_path / "profile" / ".codex"
    codex_home.mkdir(parents=True)
    config = codex_home / "config.toml"
    original = (
        '[mcp_servers."samvil-mcp"]\n'
        f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
        'args = ["-m", "samvil_mcp.server"]\n'
        "env = {}\n"
    )
    config.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item
        for item in plan.to_dict()["artifacts"]
        if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "user_modified"
    assert "exact installer-generated text" in artifact["reason"]
    assert config.read_text(encoding="utf-8") == original


def test_migrate_dry_run_cli_is_read_only_and_requires_checked_hash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = Path(__file__).resolve().parents[2]
    codex_home = tmp_path / "profile" / ".codex"

    result = installer._main(
        [
            "--migrate",
            "--dry-run",
            "--repo-root",
            str(repo),
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["mode"] == "migration_dry_run"
    assert payload["ready"] is True
    assert not codex_home.exists()

    with pytest.raises(InstallBlocked, match="matching checked legacy plan"):
        installer._main(
            [
                "--migrate",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
            ]
        )


def test_dry_run_flag_is_rejected_outside_migrate(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    with pytest.raises(SystemExit):
        installer._main(
            [
                "--check",
                "--dry-run",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(tmp_path / ".codex"),
            ]
        )


def test_migrate_cli_fails_closed_without_checked_plan_hash(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    with pytest.raises(InstallBlocked, match="matching checked legacy plan"):
        installer._main(
            [
                "--migrate",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(tmp_path / ".codex"),
            ]
        )
