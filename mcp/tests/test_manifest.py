"""Tests for mcp.samvil_mcp.manifest — Codebase Manifest module."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from samvil_mcp.manifest import (
    Manifest,
    ModuleEntry,
    MANIFEST_SCHEMA_VERSION,
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
