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


def test_discover_modules_finds_src_subdirs(tmp_path):
    """discover_modules treats each direct child of src/ as a module."""
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text("export const signIn = () => {};")
    (tmp_path / "src" / "billing").mkdir(parents=True)
    (tmp_path / "src" / "billing" / "stripe.ts").write_text("// stripe")

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    names = {m.name for m in modules}
    assert names == {"auth", "billing"}


def test_discover_modules_skips_node_modules(tmp_path):
    """discover_modules ignores node_modules / .next / .git."""
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text("// auth")
    (tmp_path / "node_modules" / "react").mkdir(parents=True)
    (tmp_path / ".next" / "cache").mkdir(parents=True)
    (tmp_path / ".git" / "objects").mkdir(parents=True)

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    assert len(modules) == 1
    assert modules[0].name == "auth"


def test_discover_modules_collects_files(tmp_path):
    """Each ModuleEntry.files lists the .ts/.tsx/.js files it owns."""
    auth = tmp_path / "src" / "auth"
    auth.mkdir(parents=True)
    (auth / "index.ts").write_text("export {};")
    (auth / "session.ts").write_text("export {};")
    (auth / "session.test.ts").write_text("// test")
    (auth / "README.md").write_text("# auth")  # should be skipped

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    assert len(modules) == 1
    files = modules[0].files
    assert "src/auth/index.ts" in files
    assert "src/auth/session.ts" in files
    # Test files are kept (regression suite needs them); markdown not
    assert "src/auth/session.test.ts" in files
    assert "src/auth/README.md" not in files


def test_discover_modules_returns_empty_when_no_src(tmp_path):
    """No src/ directory → no modules (graceful, not error)."""
    from samvil_mcp.manifest import discover_modules

    assert discover_modules(tmp_path) == []


def test_discover_modules_skips_nested_ignore_dir(tmp_path):
    """A node_modules INSIDE a module dir must not leak files."""
    web = tmp_path / "src" / "web"
    web.mkdir(parents=True)
    (web / "page.tsx").write_text("export default () => null;")
    nested_pkg = web / "node_modules" / "react"
    nested_pkg.mkdir(parents=True)
    (nested_pkg / "index.js").write_text("module.exports = {};")
    (nested_pkg / "index.d.ts").write_text("export {};")

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    assert len(modules) == 1
    files = modules[0].files
    assert files == ["src/web/page.tsx"]  # zero leakage from nested node_modules


def test_discover_modules_skips_dot_prefixed_dirs(tmp_path):
    """Directories like src/.cache/ are not treated as modules."""
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text("export {};")
    (tmp_path / "src" / ".cache").mkdir(parents=True)
    (tmp_path / "src" / ".cache" / "stuff.ts").write_text("// cache")

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    assert {m.name for m in modules} == {"auth"}


def test_extract_public_api_from_index_ts(tmp_path):
    """index.ts re-exports become the module's public API list."""
    auth = tmp_path / "src" / "auth"
    auth.mkdir(parents=True)
    (auth / "index.ts").write_text(
        "export { signIn, signOut } from './session';\n"
        "export { getUser } from './user';\n"
    )

    from samvil_mcp.manifest import extract_public_api

    api = extract_public_api(auth)
    assert set(api) == {"signIn", "signOut", "getUser"}


def test_extract_public_api_handles_default_export(tmp_path):
    """`export default Foo;` becomes a 'default' entry."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "index.ts").write_text("export default class App {}\n")

    from samvil_mcp.manifest import extract_public_api

    api = extract_public_api(mod)
    assert "default" in api


def test_extract_public_api_returns_empty_when_no_index(tmp_path):
    """No index.ts → empty public API (not an error)."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "thing.ts").write_text("export const X = 1;")

    from samvil_mcp.manifest import extract_public_api

    assert extract_public_api(mod) == []


def test_discover_modules_populates_public_api(tmp_path):
    """discover_modules wires extract_public_api into each ModuleEntry."""
    auth = tmp_path / "src" / "auth"
    auth.mkdir(parents=True)
    (auth / "index.ts").write_text("export { signIn } from './session';")

    from samvil_mcp.manifest import discover_modules

    modules = discover_modules(tmp_path)
    assert modules[0].public_api == ["signIn"]


def test_extract_public_api_handles_interface_enum_type(tmp_path):
    """interface, enum, type, async function are surfaced."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "index.ts").write_text(
        "export interface Foo { bar: string }\n"
        "export enum Color { Red, Blue }\n"
        "export type ID = string;\n"
        "export async function fetchUser() { return null; }\n"
    )
    from samvil_mcp.manifest import extract_public_api
    api = extract_public_api(mod)
    assert set(api) == {"Foo", "Color", "ID", "fetchUser"}


def test_extract_public_api_handles_export_type_reexport(tmp_path):
    """`export type { Foo } from '...'` is parsed like a regular re-export."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "index.ts").write_text("export type { User, Session } from './types';\n")
    from samvil_mcp.manifest import extract_public_api
    api = extract_public_api(mod)
    assert set(api) == {"User", "Session"}


def test_extract_public_api_strips_comments(tmp_path):
    """Names inside line/block comments must not leak into the API list."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "index.ts").write_text(
        "// export const TODO_REMOVE = 1;\n"
        "/* export const fake = 2; */\n"
        "export const real = 3;\n"
    )
    from samvil_mcp.manifest import extract_public_api
    api = extract_public_api(mod)
    assert "real" in api
    assert "TODO_REMOVE" not in api
    assert "fake" not in api


def test_extract_public_api_handles_alias_and_dedup(tmp_path):
    """`a as b` extracts b; duplicates collapse with order preserved."""
    mod = tmp_path / "src" / "x"
    mod.mkdir(parents=True)
    (mod / "index.ts").write_text(
        "export { default as MyComp } from './comp';\n"
        "export { foo } from './a';\n"
        "export { foo } from './b';\n"
    )
    from samvil_mcp.manifest import extract_public_api
    api = extract_public_api(mod)
    # MyComp first (alias), then foo once (dedup), no second foo
    assert api == ["MyComp", "foo"]


def test_extract_public_api_index_tsx_fallback(tmp_path):
    """When index.ts is absent, index.tsx is parsed instead."""
    mod = tmp_path / "src" / "Page"
    mod.mkdir(parents=True)
    (mod / "index.tsx").write_text("export default function Page() { return null; }\n")
    from samvil_mcp.manifest import extract_public_api
    api = extract_public_api(mod)
    assert "default" in api


def test_detect_conventions_finds_typescript(tmp_path):
    """tsconfig.json present → conventions['language'] == 'typescript'."""
    (tmp_path / "tsconfig.json").write_text("{}")

    from samvil_mcp.manifest import detect_conventions

    conv = detect_conventions(tmp_path)
    assert conv.get("language") == "typescript"


def test_detect_conventions_finds_tailwind(tmp_path):
    """tailwind.config.* present → conventions['css'] == 'tailwind'."""
    (tmp_path / "tailwind.config.ts").write_text("export default {};")

    from samvil_mcp.manifest import detect_conventions

    conv = detect_conventions(tmp_path)
    assert conv.get("css") == "tailwind"


def test_detect_conventions_finds_nextjs(tmp_path):
    """next.config.* present → conventions['framework'] == 'next'."""
    (tmp_path / "next.config.mjs").write_text("export default {};")

    from samvil_mcp.manifest import detect_conventions

    conv = detect_conventions(tmp_path)
    assert conv.get("framework") == "next"


def test_detect_conventions_returns_empty_for_bare_dir(tmp_path):
    """No config files → empty dict (graceful, not error)."""
    from samvil_mcp.manifest import detect_conventions

    assert detect_conventions(tmp_path) == {}


def test_detect_conventions_directory_vs_file_for_supabase(tmp_path):
    """A *file* named 'supabase' must not trigger auth_db detection."""
    (tmp_path / "supabase").write_text("not a real supabase project")

    from samvil_mcp.manifest import detect_conventions

    conv = detect_conventions(tmp_path)
    assert "auth_db" not in conv


def test_detect_conventions_finds_eslint(tmp_path):
    """ESLint detection works across the various .eslintrc* shapes."""
    (tmp_path / ".eslintrc.json").write_text("{}")

    from samvil_mcp.manifest import detect_conventions

    assert detect_conventions(tmp_path).get("linter") == "eslint"


def test_detect_conventions_multiple_rules_fire(tmp_path):
    """Realistic Next.js + TS + Tailwind project: all three keys present."""
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "next.config.mjs").write_text("export default {};")
    (tmp_path / "tailwind.config.ts").write_text("export default {};")

    from samvil_mcp.manifest import detect_conventions

    conv = detect_conventions(tmp_path)
    assert conv == {
        "language": "typescript",
        "framework": "next",
        "css": "tailwind",
    }


def test_detect_conventions_first_rule_wins_on_conflict(tmp_path):
    """When both next.config.* and vite.config.* exist, next wins (first rule)."""
    (tmp_path / "next.config.mjs").write_text("")
    (tmp_path / "vite.config.ts").write_text("")

    from samvil_mcp.manifest import detect_conventions

    assert detect_conventions(tmp_path)["framework"] == "next"


def test_build_manifest_full_integration(tmp_path):
    """build_manifest combines discover_modules + detect_conventions + meta."""
    # Set up a minimal project
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "tailwind.config.ts").write_text("export default {};")
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "index.ts").write_text(
        "export { signIn } from './session';"
    )

    from samvil_mcp.manifest import build_manifest

    m = build_manifest(tmp_path, project_name="todo-app")

    assert m.schema_version == "1.0"
    assert m.project_name == "todo-app"
    assert m.project_root == str(tmp_path)
    assert len(m.modules) == 1
    assert m.modules[0].name == "auth"
    assert m.modules[0].public_api == ["signIn"]
    assert m.conventions["language"] == "typescript"
    assert m.conventions["css"] == "tailwind"
    assert m.public_apis == {"auth": ["signIn"]}
    # generated_at is set
    assert m.generated_at != ""
