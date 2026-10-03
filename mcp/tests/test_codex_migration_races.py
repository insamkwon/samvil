"""Deterministic filesystem interleavings; all profiles are temporary."""

import json
import os
from pathlib import Path

import pytest
from .test_setup_codex import FakeNativeRegistry, _generated_legacy_agents

from samvil_mcp import codex_installer as installer
from samvil_mcp import codex_migration as migration


@pytest.mark.parametrize("mode", [["--migrate", "--dry-run"], ["--check"]])
def test_hardlinked_config_diagnostics_are_structured_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    mode: list[str],
) -> None:
    repo = Path(__file__).resolve().parents[2]
    profile = tmp_path / "profile"
    profile.mkdir()
    config = profile / "config.toml"
    content = b'model = "personal-model"\n'
    config.write_bytes(content)
    other = tmp_path / "other-config.toml"
    os.link(config, other)
    before = config.stat()

    def no_cli(*args, **kwargs):
        pytest.fail("unsafe config diagnostics must not invoke the actual CLI")

    monkeypatch.setattr(installer, "validate_cli_environment", no_cli)
    monkeypatch.setattr(installer, "_subprocess_runner", no_cli)
    monkeypatch.setattr(installer.subprocess, "run", no_cli)
    result = installer._main([
        *mode, "--repo-root", str(repo), "--codex-home", str(profile), "--json",
    ])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result != 0
    assert payload["ready"] is False
    assert payload["blockers"]
    assert any("hardlink" in blocker.lower() or "regular file" in blocker.lower()
               for blocker in payload["blockers"])
    assert captured.err == ""
    assert list(profile.iterdir()) == [config]
    assert config.read_bytes() == other.read_bytes() == content
    after = config.stat()
    for field in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"):
        assert getattr(after, field) == getattr(before, field)
    with pytest.raises(installer.InstallBlocked):
        installer._read_regular_file_bytes(config)


@pytest.mark.parametrize("intrusion", [
    "none", "read_atime", "manifest", "manifest_edit", "link", "child",
    "late_manifest", "late_manifest_root", "late_wrapper",
])
def test_public_migration_partial_wrapper_cleanup_preserves_foreign_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, intrusion: str
) -> None:
    repo = Path(__file__).resolve().parents[2]
    profile = tmp_path / "profile"
    profile.mkdir()
    agents = profile / "AGENTS.md"
    original = _generated_legacy_agents(repo).encode()
    agents.write_bytes(original)
    checked = installer.build_legacy_migration_plan(repo_root=repo, codex_home=profile)
    assert not checked.blockers
    plan = installer.CodexInstallPlan(repo, installer.CodexCapabilityProbe(True, True))
    wrapper = profile / "marketplaces" / "samvil-codex"
    manifest = wrapper / ".claude-plugin" / "marketplace.json"
    registry = FakeNativeRegistry()
    real_symlink = os.symlink
    real_fstat = os.fstat
    real_read = os.read
    real_stat = os.stat
    manifest_read = False
    late_replaced = False
    failed = False
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"user-owned content")

    def stat_then_replace(path, *args, **kwargs):
        nonlocal late_replaced
        metadata = real_stat(path, *args, **kwargs)
        if (intrusion.startswith("late_") and failed and not late_replaced
                and path == "marketplace.json" and kwargs.get("dir_fd") is not None):
            late_replaced = True
            if intrusion == "late_manifest":
                manifest.unlink()
                manifest.write_bytes(b"user late manifest replacement")
            elif intrusion == "late_manifest_root":
                manifest.parent.rename(wrapper / "saved-manifest-root")
                manifest.parent.mkdir()
                (manifest.parent / "user-note").write_bytes(b"user directory replacement")
            else:
                wrapper.rename(profile / "saved-wrapper")
                wrapper.mkdir()
                (wrapper / "user-note").write_bytes(b"user wrapper replacement")
        return metadata

    def reading(fd, size):
        nonlocal manifest_read
        result = real_read(fd, size)
        if failed and intrusion == "read_atime" and result:
            manifest_read = True
        return result

    def with_read_atime(fd):
        metadata = real_fstat(fd)
        if manifest_read:
            fields = list(metadata)
            fields[7] += 1
            return os.stat_result(fields, {
                "st_mtime_ns": metadata.st_mtime_ns,
                "st_ctime_ns": metadata.st_ctime_ns,
            })
        return metadata

    def fail_once(src, dst, *args, **kwargs):
        nonlocal failed
        if dst == "samvil" and kwargs.get("dir_fd") is not None and not failed:
            failed = True
            if intrusion == "manifest":
                manifest.unlink()
                manifest.write_bytes(b"user manifest replacement")
            elif intrusion == "manifest_edit":
                manifest.write_bytes(b"user manifest edit")
            elif intrusion == "link":
                real_symlink(str(foreign), dst, **kwargs)
            elif intrusion == "child":
                (wrapper / "user-note").write_bytes(b"user child")
            raise OSError("injected one-time pinned symlink failure")
        return real_symlink(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "symlink", fail_once)
    monkeypatch.setattr(os, "read", reading)
    monkeypatch.setattr(os, "fstat", with_read_atime)
    monkeypatch.setattr(os, "stat", stat_then_replace)
    with pytest.raises(installer.InstallBlocked, match="injected one-time pinned symlink failure"):
        installer.execute_isolated_install(
            plan, codex_home=profile, command_runner=registry.run,
            registry_reader=registry.read, migrate=True,
            expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
        )
    assert failed
    assert agents.read_bytes() == original
    assert not registry.commands
    assert foreign.read_bytes() == b"user-owned content"
    fresh = installer.build_legacy_migration_plan(repo_root=repo, codex_home=profile)
    if intrusion in {"none", "read_atime"}:
        assert not wrapper.exists()
        monkeypatch.setattr(os, "fstat", real_fstat)
        monkeypatch.setattr(os, "read", real_read)
        assert not fresh.blockers
        receipt = installer.execute_isolated_install(
            plan, codex_home=profile, command_runner=registry.run,
            registry_reader=registry.read, migrate=True,
            expected_legacy_plan_sha256=fresh.to_dict()["plan_sha256"],
        )
        assert receipt.mode == "migrate"
        assert not agents.exists()
        assert (wrapper / "samvil").resolve() == repo
        assert registry.plugins == {"samvil@samvil-codex"}
    else:
        if intrusion == "manifest":
            assert manifest.read_bytes() == b"user manifest replacement"
        elif intrusion == "manifest_edit":
            assert manifest.read_bytes() == b"user manifest edit"
        elif intrusion == "late_manifest":
            assert late_replaced
            assert manifest.read_bytes() == b"user late manifest replacement"
        elif intrusion == "late_manifest_root":
            assert late_replaced
            assert (manifest.parent / "user-note").read_bytes() == b"user directory replacement"
            assert (wrapper / "saved-manifest-root" / "marketplace.json").is_file()
        elif intrusion == "late_wrapper":
            assert late_replaced
            assert (wrapper / "user-note").read_bytes() == b"user wrapper replacement"
            assert (profile / "saved-wrapper" / ".claude-plugin" / "marketplace.json").is_file()
        elif intrusion == "link":
            assert (wrapper / "samvil").is_symlink()
            assert os.readlink(wrapper / "samvil") == str(foreign)
        else:
            assert (wrapper / "user-note").read_bytes() == b"user child"
        with pytest.raises(installer.InstallBlocked, match="ambiguous Codex marketplace wrapper"):
            installer.execute_isolated_install(
                plan, codex_home=profile, command_runner=registry.run,
                registry_reader=registry.read, migrate=True,
                expected_legacy_plan_sha256=fresh.to_dict()["plan_sha256"],
            )
        assert not registry.commands
        assert agents.read_bytes() == original


@pytest.mark.parametrize("artifact", ["agents", "config"])
@pytest.mark.parametrize("failure", ["source_reappeared", "stat_error"])
def test_public_migration_keeps_quarantined_fd_edit_on_late_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact: str, failure: str
) -> None:
    repo = Path(__file__).resolve().parents[2]
    profile = tmp_path / "profile"
    profile.mkdir()
    source = profile / ("AGENTS.md" if artifact == "agents" else "config.toml")
    original = (
        _generated_legacy_agents(repo).encode()
        if artifact == "agents"
        else (
            "[mcp_servers.samvil-mcp]\n"
            f'command = "{repo / "mcp" / ".venv" / "bin" / "python"}"\n'
            'args = ["-m", "samvil_mcp.server"]\nenv = {}\n'
        ).encode()
    )
    source.write_bytes(original)
    checked = installer.build_legacy_migration_plan(repo_root=repo, codex_home=profile)
    assert not checked.blockers
    registry = FakeNativeRegistry()
    held = os.open(source, os.O_WRONLY)
    real_stat = os.stat
    real_rename = migration._rename_no_replace_at
    renamed = False
    raced = False
    edited = b"# edit committed through original descriptor\n"
    recreated = b"# independently recreated source\n"

    def rename(*args, **kwargs):
        nonlocal renamed
        result = real_rename(*args, **kwargs)
        if args[0] == source.name:
            renamed = True
        return result

    def racing_stat(path, *args, **kwargs):
        nonlocal raced
        # This source-name stat is after the final digest of the quarantined FD.
        if path == source.name and kwargs.get("dir_fd") is not None and renamed and not raced:
            raced = True
            os.write(held, edited)
            os.ftruncate(held, len(edited))
            os.fsync(held)
            source.write_bytes(recreated)
            if failure == "stat_error":
                raise OSError("injected post-quarantine stat failure")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(migration, "_rename_no_replace_at", rename)
    monkeypatch.setattr(os, "stat", racing_stat)
    try:
        with pytest.raises(installer.InstallBlocked):
            installer.execute_isolated_install(
                installer.CodexInstallPlan(repo, installer.CodexCapabilityProbe(True, True)),
                codex_home=profile,
                command_runner=registry.run,
                registry_reader=registry.read,
                migrate=True,
                expected_legacy_plan_sha256=checked.to_dict()["plan_sha256"],
            )
    finally:
        os.close(held)
    assert raced
    assert source.read_bytes() == recreated
    assert not registry.commands
    quarantine = list(profile.rglob(f".{source.name}.quarantine-*"))
    assert len(quarantine) == 1
    assert quarantine[0].read_bytes() == edited
    backup_name = "global-AGENTS.md" if artifact == "agents" else "config.toml.before"
    backups = list(profile.rglob(backup_name))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert backups[0].stat().st_ino != quarantine[0].stat().st_ino


def test_missing_config_has_empty_unrelated_projection(tmp_path: Path) -> None:
    assert installer._unrelated_config_projection(tmp_path / "config.toml") == (
        '{"raw":"","semantic":{}}'
    )


def test_wrapper_collision_keeps_concurrent_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "marketplaces"
    parent.mkdir()
    descriptor = os.open(parent, installer._directory_flags())
    real_mkdir = os.mkdir
    raced = False

    def racing_mkdir(path, mode=0o777, *, dir_fd=None):
        nonlocal raced
        if path == "samvil-codex" and not raced:
            raced = True
            real_mkdir(path, mode, dir_fd=dir_fd)
        return real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    try:
        with pytest.raises((installer.InstallBlocked, FileExistsError)):
            installer._codex_marketplace_wrapper(
                tmp_path, tmp_path / "repo", marketplaces_parent_descriptor=descriptor
            )
    finally:
        os.close(descriptor)
    assert (parent / "samvil-codex").is_dir()


def test_move_keeps_source_edited_during_backup_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "config.toml"
    backup = tmp_path / "config.before"
    source.write_bytes(b"original")
    real_link = os.link

    def racing_link(*args, **kwargs):
        result = real_link(*args, **kwargs)
        source.write_bytes(b"useredit")
        return result

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(installer.InstallBlocked):
        migration._move_no_replace(source, backup)
    assert source.read_bytes() == b"useredit"
    assert backup.read_bytes() == b"original"


def test_regular_reader_rejects_same_size_edit_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "config.toml"
    source.write_bytes(b"original")
    real_read = os.read
    raced = False

    def racing_read(fd, size):
        nonlocal raced
        chunk = real_read(fd, size)
        if chunk and not raced:
            raced = True
            source.write_bytes(b"useredit")
        return chunk

    monkeypatch.setattr(os, "read", racing_read)
    with pytest.raises(installer.InstallBlocked):
        installer._read_regular_file_bytes(source)


def test_atomic_backup_copy_does_not_replace_concurrent_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "config.toml"
    source.write_bytes(b"original")
    parent = tmp_path / "backups"
    parent.mkdir()
    real_link = os.link
    raced = False

    def racing_link(*args, **kwargs):
        nonlocal raced
        if not raced:
            raced = True
            (parent / "config.toml").write_bytes(b"user-file")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    descriptor = os.open(parent, installer._directory_flags())
    try:
        with pytest.raises(installer.InstallBlocked):
            installer._atomic_copy_at(source, "config.toml", descriptor)
    finally:
        os.close(descriptor)
    assert (parent / "config.toml").read_bytes() == b"user-file"
