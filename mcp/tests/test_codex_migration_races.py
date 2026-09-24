"""Deterministic filesystem interleavings; all profiles are temporary."""

import os
from pathlib import Path

import pytest

from samvil_mcp import codex_installer as installer
from samvil_mcp import codex_migration as migration


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
