"""Tests for mechanical_toml module (v4.26.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.mechanical_toml import (
    KNOWN_FIELDS,
    MECHANICAL_FILENAME,
    read_mechanical_toml,
    render_default_toml,
    resolve_command,
    write_default_toml,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


# ── read_mechanical_toml ────────────────────────────────────


def test_read_missing(project_root: Path) -> None:
    result = read_mechanical_toml(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["commands"] == {}


def test_read_happy(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'solution_type = "web-app"\n'
        'build = "npm run build"\n'
        'lint = "npx eslint . --quiet"\n'
        'typecheck = "npx tsc --noEmit"\n',
        encoding="utf-8",
    )
    result = read_mechanical_toml(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is True
    assert result["commands"]["build"] == "npm run build"
    assert result["commands"]["lint"] == "npx eslint . --quiet"
    assert result["commands"]["solution_type"] == "web-app"


def test_read_skips_empty_strings(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'build = "npm run build"\n'
        'test = ""\n'
        'lint = "   "\n',
        encoding="utf-8",
    )
    result = read_mechanical_toml(project_root=str(project_root))
    assert "build" in result["commands"]
    assert "test" not in result["commands"]
    assert "lint" not in result["commands"]
    assert any("test" in w for w in result["warnings"])
    assert any("lint" in w for w in result["warnings"])


def test_read_preserves_unknown_fields(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'build = "x"\n'
        'custom_field = "y"\n',
        encoding="utf-8",
    )
    result = read_mechanical_toml(project_root=str(project_root))
    assert "custom_field" in result["extra"]
    assert any("custom_field" in w for w in result["warnings"])


def test_read_malformed_toml(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text("not valid toml [[[", encoding="utf-8")
    result = read_mechanical_toml(project_root=str(project_root))
    assert result["ok"] is False
    assert "error" in result


def test_read_korean_in_commands(project_root: Path) -> None:
    """Commands themselves should be ASCII shell, but extra fields can have Korean."""
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'build = "npm run build"\n'
        'description = "한국어 설명도 OK"\n',
        encoding="utf-8",
    )
    result = read_mechanical_toml(project_root=str(project_root))
    assert result["extra"]["description"] == "한국어 설명도 OK"


def test_read_non_string_command(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'build = 42\n',
        encoding="utf-8",
    )
    result = read_mechanical_toml(project_root=str(project_root))
    assert "build" not in result["commands"]
    assert any("build" in w and "expected string" in w for w in result["warnings"])


# ── render_default_toml ─────────────────────────────────────


def test_render_default_web_app() -> None:
    text = render_default_toml(solution_type="web-app")
    assert 'solution_type = "web-app"' in text
    assert 'build = "npm run build"' in text
    assert 'typecheck = "npx tsc --noEmit"' in text


def test_render_default_automation() -> None:
    text = render_default_toml(solution_type="automation")
    assert 'solution_type = "automation"' in text
    assert "python" in text


def test_render_default_unknown_type() -> None:
    text = render_default_toml(solution_type="unknown_type")
    assert "Unknown solution_type" in text
    assert 'build = ""' in text


def test_render_default_with_framework() -> None:
    text = render_default_toml(solution_type="web-app", framework="nextjs")
    assert 'framework = "nextjs"' in text


def test_render_is_valid_toml(project_root: Path) -> None:
    """Defaults should parse cleanly when written back."""
    text = render_default_toml(solution_type="web-app", framework="nextjs")
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(text, encoding="utf-8")
    result = read_mechanical_toml(project_root=str(project_root))
    assert result["ok"] is True
    assert result["commands"]["solution_type"] == "web-app"
    assert result["commands"]["framework"] == "nextjs"


# ── write_default_toml ──────────────────────────────────────


def test_write_creates_file(project_root: Path) -> None:
    result = write_default_toml(
        project_root=str(project_root), solution_type="web-app", framework="nextjs",
    )
    assert result["ok"] is True
    assert result["wrote"] is True
    assert (project_root / ".samvil" / MECHANICAL_FILENAME).exists()


def test_write_refuses_existing(project_root: Path) -> None:
    write_default_toml(project_root=str(project_root), solution_type="web-app")
    result = write_default_toml(project_root=str(project_root), solution_type="automation")
    assert result["ok"] is True
    assert result["wrote"] is False  # didn't overwrite
    # Original web-app content preserved
    read_result = read_mechanical_toml(project_root=str(project_root))
    assert read_result["commands"]["solution_type"] == "web-app"


def test_write_overwrite_force(project_root: Path) -> None:
    write_default_toml(project_root=str(project_root), solution_type="web-app")
    result = write_default_toml(
        project_root=str(project_root), solution_type="automation", overwrite=True,
    )
    assert result["wrote"] is True
    read_result = read_mechanical_toml(project_root=str(project_root))
    assert read_result["commands"]["solution_type"] == "automation"


# ── resolve_command ────────────────────────────────────────


def test_resolve_from_toml(project_root: Path) -> None:
    write_default_toml(project_root=str(project_root), solution_type="web-app")
    result = resolve_command(project_root=str(project_root), field="build", fallback="X")
    assert result["ok"] is True
    assert result["command"] == "npm run build"
    assert result["source"] == "toml"


def test_resolve_fallback_when_no_toml(project_root: Path) -> None:
    result = resolve_command(
        project_root=str(project_root), field="build", fallback="npm run build",
    )
    assert result["ok"] is True
    assert result["command"] == "npm run build"
    assert result["source"] == "fallback"


def test_resolve_fallback_when_field_empty(project_root: Path) -> None:
    """Field defined as empty string in toml → use fallback."""
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / MECHANICAL_FILENAME).write_text(
        'build = "from-toml"\ntest = ""\n', encoding="utf-8",
    )
    result = resolve_command(
        project_root=str(project_root), field="test", fallback="default-test",
    )
    assert result["command"] == "default-test"
    assert result["source"] == "fallback"


def test_resolve_unknown_field(project_root: Path) -> None:
    result = resolve_command(
        project_root=str(project_root), field="not_a_field", fallback="x",
    )
    assert result["ok"] is False


def test_resolve_no_toml_no_fallback(project_root: Path) -> None:
    result = resolve_command(project_root=str(project_root), field="build")
    assert result["ok"] is True
    assert result["command"] == ""
    assert result["source"] == "none"


def test_known_fields_includes_basics() -> None:
    """Sanity: KNOWN_FIELDS has all the commands SAMVIL stages need."""
    for f in ("build", "test", "lint", "typecheck", "dev_server", "deploy"):
        assert f in KNOWN_FIELDS, f"missing core field: {f}"
