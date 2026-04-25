"""Tests for mcp.samvil_mcp.manifest — Codebase Manifest module."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from samvil_mcp.manifest import (
    Manifest,
    ModuleEntry,
    MANIFEST_SCHEMA_VERSION,
    write_manifest,
    read_manifest,
    manifest_path,
)


def test_module_entry_roundtrip():
    """ModuleEntry serializes to dict and back without loss."""
    entry = ModuleEntry(
        name="auth",
        path="src/auth",
        public_api=["signIn", "signOut"],
        depends_on=["db"],
        summary="Handles login/signup via Supabase",
        files=["src/auth/index.ts", "src/auth/session.ts"],
        convention_tags=["server-component", "uses-supabase"],
        last_updated="2026-04-25T10:00:00Z",
    )
    d = asdict(entry)
    assert d["name"] == "auth"
    assert d["public_api"] == ["signIn", "signOut"]
    rebuilt = ModuleEntry(**d)
    assert rebuilt == entry


def test_manifest_schema_version_constant():
    """Schema version is fixed at 1.0 for Phase 1."""
    assert MANIFEST_SCHEMA_VERSION == "1.0"


def test_manifest_to_dict_includes_all_fields():
    """Manifest.to_dict produces a JSON-serializable dict with required fields."""
    m = Manifest(
        schema_version="1.0",
        project_name="todo-app",
        project_root="/Users/test/dev/todo-app",
        generated_at="2026-04-25T10:00:00Z",
        modules=[],
        conventions={"naming": "camelCase"},
        public_apis={"auth": ["signIn"]},
    )
    d = m.to_dict()
    assert d["schema_version"] == "1.0"
    assert d["project_name"] == "todo-app"
    assert d["conventions"] == {"naming": "camelCase"}


def test_manifest_from_dict_roundtrip():
    """Manifest.from_dict(m.to_dict()) reconstructs the original manifest."""
    original = Manifest(
        schema_version="1.0",
        project_name="todo-app",
        project_root="/Users/test/dev/todo-app",
        generated_at="2026-04-25T10:00:00Z",
        modules=[
            ModuleEntry(
                name="auth",
                path="src/auth",
                public_api=["signIn"],
                last_updated="2026-04-25T10:00:00Z",
            )
        ],
        conventions={"language": "typescript"},
        public_apis={"auth": ["signIn"]},
    )
    rebuilt = Manifest.from_dict(original.to_dict())
    assert rebuilt == original


def test_manifest_path_default(tmp_path):
    """manifest_path resolves to .samvil/manifest.json under project_root."""
    expected = tmp_path / ".samvil" / "manifest.json"
    assert manifest_path(tmp_path) == expected


def test_write_then_read_roundtrip(tmp_path):
    """write_manifest then read_manifest returns the same data."""
    m = Manifest(
        schema_version="1.0",
        project_name="proj",
        project_root=str(tmp_path),
        generated_at="2026-04-25T10:00:00Z",
        modules=[
            ModuleEntry(
                name="auth",
                path="src/auth",
                public_api=["signIn"],
                summary="auth handler",
                last_updated="2026-04-25T10:00:00Z",
            )
        ],
        conventions={"naming": "camelCase"},
        public_apis={"auth": ["signIn"]},
    )
    write_manifest(m, tmp_path)
    rebuilt = read_manifest(tmp_path)
    assert rebuilt is not None
    assert rebuilt.project_name == "proj"
    assert len(rebuilt.modules) == 1
    assert rebuilt.modules[0].name == "auth"


def test_read_manifest_returns_none_when_missing(tmp_path):
    """read_manifest returns None when no manifest file exists."""
    assert read_manifest(tmp_path) is None


def test_write_manifest_is_atomic(tmp_path):
    """write_manifest does not leave a half-written file on failure.

    Strategy: write twice. The second write must fully replace, never merge.
    """
    m1 = Manifest(
        schema_version="1.0",
        project_name="v1",
        project_root=str(tmp_path),
        generated_at="2026-04-25T10:00:00Z",
    )
    m2 = Manifest(
        schema_version="1.0",
        project_name="v2",
        project_root=str(tmp_path),
        generated_at="2026-04-25T11:00:00Z",
    )
    write_manifest(m1, tmp_path)
    write_manifest(m2, tmp_path)
    rebuilt = read_manifest(tmp_path)
    assert rebuilt.project_name == "v2"
    # No leftover .tmp files
    assert not list((tmp_path / ".samvil").glob("*.tmp"))
