"""Pure ownership and capability planning tests for Codex setup."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import samvil_mcp.codex_installer as installer

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
    validate_cli_environment,
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

    changed = classify_legacy_skill(
        legacy / "SKILL.md", canonical / "SKILL.md"
    )

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


def test_generated_file_classifier_distinguishes_ambiguous_content(tmp_path: Path) -> None:
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
    (real_parent / "skill" / "SKILL.md").write_text(
        "generated\n", encoding="utf-8"
    )
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

    with pytest.raises(InstallBlocked, match="profile changed during install admission"):
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
    monkeypatch.setattr(
        installer,
        "validate_cli_environment",
        lambda _root: {"ready": True, "blockers": []},
    )
    monkeypatch.setattr(
        installer,
        "_subprocess_runner",
        lambda command, env: commands.append((command, env)),
    )

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


def test_isolated_executor_backups_config_and_preserves_personal_skills(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    repo.mkdir()
    personal = codex_home / "skills" / "commit"
    personal.mkdir(parents=True)
    (personal / "SKILL.md").write_text("---\nname: commit\n---\nkeep\n", encoding="utf-8")
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
                "codex", "plugin", "marketplace", "add",
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
    assert (codex_home / "marketplaces" / "samvil-codex" / "samvil").resolve() == repo.resolve()


def test_isolated_executor_corrects_existing_samvil_marketplace_root(tmp_path: Path) -> None:
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

    execute_isolated_install(
        plan,
        codex_home=codex_home,
        command_runner=lambda command, env: commands.append((command, env)),
    )

    assert [command for command, _env in commands] == [
        ("codex", "plugin", "marketplace", "remove", "samvil"),
        (
            "codex", "plugin", "marketplace", "add",
            str((codex_home / "marketplaces" / "samvil-codex").resolve()),
        ),
        ("codex", "plugin", "add", "samvil@samvil-codex"),
    ]


def test_isolated_executor_blocks_invalid_config_before_commands(tmp_path: Path) -> None:
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


def test_isolated_executor_restores_config_when_plugin_add_fails(tmp_path: Path) -> None:
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
        config.write_text('[marketplaces.samvil]\nsource = "/partial"\n', encoding="utf-8")
        if calls == 2:
            raise RuntimeError("plugin add failed")

    with pytest.raises(InstallBlocked, match="config restored"):
        execute_isolated_install(plan, codex_home=codex_home, command_runner=failing_runner)

    assert config.read_text(encoding="utf-8") == original
    assert not (codex_home / "marketplaces" / "samvil-codex").exists()


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


def test_isolated_executor_blocks_config_symlink_without_overwriting_target(tmp_path: Path) -> None:
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
            command_runner=lambda _command, _env: (_ for _ in ()).throw(AssertionError("no command")),
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


def test_isolated_executor_blocks_ambiguous_codex_wrapper_before_commands(tmp_path: Path) -> None:
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

    with pytest.raises(InstallBlocked, match="marketplaces path escapes isolated profile"):
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


def test_isolated_executor_accepts_explicit_custom_codex_home_name(tmp_path: Path) -> None:
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

    with pytest.raises(InstallBlocked, match="legacy migration apply is unavailable"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda command, env: commands.append((command, env)),
            migrate=True,
        )

    assert legacy.read_text(encoding="utf-8") == "generated legacy\n"
    assert commands == []


def test_isolated_migrate_rejects_external_or_stale_actions_before_any_write(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    codex_home = tmp_path / "codex-home" / ".codex"
    external = tmp_path / "user-owned.txt"
    repo.mkdir()
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

    with pytest.raises(InstallBlocked, match="legacy migration apply is unavailable"):
        execute_isolated_install(
            plan,
            codex_home=codex_home,
            command_runner=lambda _command, _env: pytest.fail(
                "migration blocker must precede commands"
            ),
            migrate=True,
        )

    assert external.read_text(encoding="utf-8") == "keep\n"
    assert not codex_home.exists()


def test_setup_shell_routes_codex_to_native_installer_without_legacy_global_writes() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = (repo / "scripts" / "setup-codex.sh").read_text(encoding="utf-8")

    assert '"$PYTHON_BIN" -P -m samvil_mcp.codex_installer' in script
    assert script.index("[1/5] Python") < script.index('if [[ "$HOST" == "codex" ]]')
    assert '_install_agents "$HOME/.codex"' not in script
    assert "[mcp_servers.samvil-mcp]" not in script


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
    assert [item["name"] for item in payload["personal_skills"]] == [
        "personal-review"
    ]
    assert [item["artifact_kind"] for item in payload["artifacts"]] == [
        "legacy_skill_tree"
    ]
    assert payload["artifacts"][0]["classification"] == "generated_legacy"
    assert payload["actions"] == [
        {
            "kind": "migrate_generated",
            "path": str(legacy.resolve()),
            "reason": "legacy skill tree is byte-identical to canonical source",
            "artifact_kind": "legacy_skill_tree",
            "expected_hash": payload["artifacts"][0]["content_hash"],
        }
    ]
    assert plan.to_dict() == installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    ).to_dict()
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
        (legacy / "SKILL.md").chmod(0o600)
    elif mutation == "directory_mode":
        legacy.chmod(0o700)
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
        artifact.artifact_kind == "codex_profile_root"
        and "ancestor" in artifact.reason
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
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "global_agents"
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
    original = _generated_legacy_agents(repo) + "\n## My personal instructions\nKeep this.\n"
    agents.write_text(original, encoding="utf-8")

    plan = installer.build_legacy_migration_plan(
        repo_root=repo,
        codex_home=codex_home,
    )

    artifact = next(
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "global_agents"
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
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "generated_legacy"
    assert any(
        action.kind == "remove_generated_mcp_table"
        and action.expected_hash == artifact["content_hash"]
        for action in plan.actions
    )
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
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "direct_mcp_table"
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
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "user_modified"
    assert artifact["blocks_mutation"] is True
    assert not any(action.kind == "remove_generated_mcp_table" for action in plan.actions)
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
        item for item in plan.to_dict()["artifacts"] if item["artifact_kind"] == "direct_mcp_table"
    )
    assert artifact["classification"] == "user_modified"
    assert "exact installer-generated text" in artifact["reason"]
    assert config.read_text(encoding="utf-8") == original


def test_migrate_dry_run_cli_is_read_only_and_keeps_apply_blocked(
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

    with pytest.raises(InstallBlocked, match="legacy migration is unavailable"):
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


def test_migrate_cli_fails_closed_until_legacy_actions_are_classified(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]

    with pytest.raises(InstallBlocked, match="legacy migration is unavailable"):
        installer._main(
            [
                "--migrate",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(tmp_path / ".codex"),
            ]
        )
