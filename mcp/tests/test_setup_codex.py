"""Pure ownership and capability planning tests for Codex setup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.codex_installer import (
    CodexInstallPlan,
    CodexCapabilityProbe,
    InstallBlocked,
    MigrationAction,
    LegacyOwnership,
    build_install_plan,
    classify_generated_file,
    classify_legacy_skill,
    compare_skill_inventories,
    execute_isolated_install,
    inventory_personal_skills,
    parse_capability_probe,
    validate_marketplace_root,
    validate_activation_readiness,
)


def test_capability_probe_uses_feature_outputs_not_only_version(tmp_path: Path) -> None:
    probe = parse_capability_probe(
        help_output="plugin marketplace list --json\nplugin add",
        marketplace_output=json.dumps({"marketplaces": [{"name": "samvil", "root": str(tmp_path)}]}),
        plugin_output=json.dumps({"plugins": [{"name": "samvil", "enabled": True}]}),
        feature_output=json.dumps({"features": {"plugins": True, "mcp_servers": True}}),
    )

    assert probe.plugin_commands_supported is True
    assert probe.plugins_feature_enabled is True
    assert probe.marketplaces == ({"name": "samvil", "root": str(tmp_path)},)
    assert probe.plugins == ({"name": "samvil", "enabled": True},)
    assert probe.blockers == ()


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


def test_marketplace_root_must_not_claim_user_owned_codex_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    repo = tmp_path / "repo"
    skills.mkdir(parents=True)
    repo.mkdir()

    assert validate_marketplace_root(repo, user_home=home, codex_skills_root=skills) == repo.resolve()

    for unsafe in (home, home.parent, skills, skills.parent, Path(skills.anchor)):
        with pytest.raises(ValueError):
            validate_marketplace_root(unsafe, user_home=home, codex_skills_root=skills)


def test_marketplace_root_allows_normal_repository_below_user_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    repo = home / "dev" / "samvil"
    skills.mkdir(parents=True)
    repo.mkdir(parents=True)

    assert validate_marketplace_root(repo, user_home=home, codex_skills_root=skills) == repo.resolve()


def test_symlinked_marketplace_root_is_resolved_before_safety_check(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skills = home / ".codex" / "skills"
    skills.mkdir(parents=True)
    unsafe_link = tmp_path / "repo-link"
    unsafe_link.symlink_to(home, target_is_directory=True)

    with pytest.raises(ValueError):
        validate_marketplace_root(unsafe_link, user_home=home, codex_skills_root=skills)


def test_personal_skill_inventory_records_bare_name_and_content_hash(tmp_path: Path) -> None:
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


def test_personal_skill_inventory_compare_detects_name_or_hash_drift(tmp_path: Path) -> None:
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


def test_generated_file_classifier_distinguishes_ambiguous_content(tmp_path: Path) -> None:
    file = tmp_path / "AGENTS.md"
    expected = "generated\n"
    file.write_text(expected, encoding="utf-8")
    assert classify_generated_file(file, expected).classification == "generated_legacy"

    file.write_text(expected + "user section\n", encoding="utf-8")
    result = classify_generated_file(file, expected)
    assert result.classification == "user_modified"
    assert result.blocks_mutation is True


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


def test_isolated_executor_backups_registry_and_preserves_personal_skills(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    personal = codex_home / "skills" / "commit"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text("---\nname: commit\n---\nkeep\n", encoding="utf-8")
    registry = codex_home / "marketplaces.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "old": True,
                "marketplaces": [{"name": "other", "root": "/other"}],
                "plugins": [{"name": "other", "enabled": False}],
            }
        ),
        encoding="utf-8",
    )
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
            ("codex", "plugin", "marketplace", "add", str(repo.resolve())),
            {"CODEX_HOME": str(codex_home.resolve())},
        ),
        (
            ("codex", "plugin", "add", "samvil@samvil"),
            {"CODEX_HOME": str(codex_home.resolve())},
        ),
    ]
    assert receipt.to_dict()["personal_skills_unchanged"] is True
    assert receipt.backup_paths
    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    assert registry_data["old"] is True
    assert {item["name"] for item in registry_data["marketplaces"]} == {"other", "samvil"}
    assert {item["name"] for item in registry_data["plugins"]} == {"other", "samvil"}
    assert (codex_home / "skills" / "commit" / "SKILL.md").exists()


def test_isolated_executor_replaces_registry_symlink_without_overwriting_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    target = tmp_path / "user-owned.json"
    repo.mkdir()
    codex_home.mkdir(parents=True)
    target.write_text('{"owner": "user"}\n', encoding="utf-8")
    registry = codex_home / "marketplaces.json"
    registry.symlink_to(target)
    plan = CodexInstallPlan(
        canonical_root=repo.resolve(),
        capability=CodexCapabilityProbe(True, True),
    )

    execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda _command, _env: None,
    )

    assert target.read_text(encoding="utf-8") == '{"owner": "user"}\n'
    assert registry.is_symlink() is False
    assert json.loads(registry.read_text(encoding="utf-8"))["owner"] == "user"


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
            codex_home=tmp_path / "home",
            command_runner=lambda _command, _env: None,
        )


def test_isolated_migrate_moves_only_explicit_generated_action_to_backup(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    legacy = codex_home / "skills" / "samvil-run" / "SKILL.md"
    repo.mkdir()
    legacy.parent.mkdir(parents=True)
    legacy.write_text("generated legacy\n", encoding="utf-8")
    commands: list[tuple[tuple[str, ...], dict[str, str]]] = []
    plan = CodexInstallPlan(
        canonical_root=repo.resolve(),
        capability=CodexCapabilityProbe(True, True),
        actions=(MigrationAction("migrate_generated", legacy.resolve(), "hash match"),),
    )

    receipt = execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
        migrate=True,
    )

    assert not legacy.exists()
    assert any(path.name.startswith("samvil-run-") for path in receipt.backup_paths)


def test_setup_shell_routes_codex_to_native_installer_without_legacy_global_writes() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = (repo / "scripts" / "setup-codex.sh").read_text(encoding="utf-8")

    assert "python3 -m samvil_mcp.codex_installer" in script
    assert '_install_agents "$HOME/.codex"' not in script
    assert "[mcp_servers.samvil-mcp]" not in script
