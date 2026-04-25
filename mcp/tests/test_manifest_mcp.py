"""Integration tests for manifest MCP tool wrappers."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_build_and_persist_manifest_writes_file(tmp_path):
    """build_and_persist_manifest produces .samvil/manifest.json on disk."""
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text(
        "export { signIn } from './session';"
    )

    from samvil_mcp.server import _build_and_persist_manifest_impl

    result = _build_and_persist_manifest_impl(
        project_root=str(tmp_path),
        project_name="todo-app",
    )

    assert result["status"] == "ok"
    assert result["module_count"] == 1
    assert (tmp_path / ".samvil" / "manifest.json").exists()


def test_read_manifest_impl_returns_dict(tmp_path):
    """_read_manifest_impl returns the manifest as a dict."""
    from samvil_mcp.manifest import build_manifest, write_manifest
    from samvil_mcp.server import _read_manifest_impl

    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text("export const x = 1;")
    m = build_manifest(tmp_path, project_name="proj")
    write_manifest(m, tmp_path)

    result = _read_manifest_impl(project_root=str(tmp_path))
    assert result["status"] == "ok"
    assert result["manifest"]["project_name"] == "proj"


def test_read_manifest_impl_returns_missing_when_absent(tmp_path):
    from samvil_mcp.server import _read_manifest_impl

    result = _read_manifest_impl(project_root=str(tmp_path))
    assert result["status"] == "missing"


def test_render_manifest_context_impl_returns_string(tmp_path):
    from samvil_mcp.manifest import build_manifest, write_manifest
    from samvil_mcp.server import _render_manifest_context_impl

    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text("export const x = 1;")
    m = build_manifest(tmp_path, project_name="proj")
    write_manifest(m, tmp_path)

    result = _render_manifest_context_impl(project_root=str(tmp_path))
    assert result["status"] == "ok"
    assert "proj" in result["context"]
    assert "auth" in result["context"]


def test_build_and_persist_rejects_empty_project_root():
    """Empty project_root must NOT silently pollute CWD — returns error."""
    from samvil_mcp.server import _build_and_persist_manifest_impl

    result = _build_and_persist_manifest_impl(project_root="", project_name="x")
    assert result["status"] == "error"
    assert "empty" in result["error"].lower() or "directory" in result["error"].lower()


def test_build_and_persist_rejects_nonexistent_dir(tmp_path):
    """Nonexistent project_root returns error, doesn't create dir."""
    from samvil_mcp.server import _build_and_persist_manifest_impl

    fake = tmp_path / "does-not-exist"
    result = _build_and_persist_manifest_impl(
        project_root=str(fake),
        project_name="x",
    )
    assert result["status"] == "error"
    assert not fake.exists()  # confirm no dir was silently created


def test_read_manifest_distinguishes_corrupted_from_missing(tmp_path):
    """Corrupted manifest.json returns 'corrupted', not 'missing'."""
    (tmp_path / ".samvil").mkdir()
    (tmp_path / ".samvil" / "manifest.json").write_text("{ this is not json")

    from samvil_mcp.server import _read_manifest_impl

    result = _read_manifest_impl(project_root=str(tmp_path))
    assert result["status"] == "corrupted"


def test_render_manifest_context_validates_project_root():
    """Empty project_root returns error from render path too."""
    from samvil_mcp.server import _render_manifest_context_impl

    result = _render_manifest_context_impl(project_root="")
    assert result["status"] == "error"
