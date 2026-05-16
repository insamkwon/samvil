"""Tests for multi_repo module (v4.29.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.multi_repo import (
    iterate_brownfield_repos,
    load_repo_registry,
    parse_inline_paths,
    validate_repo_paths,
)


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch) -> Path:
    """Force ~/.samvil/ to resolve under tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# ── load_repo_registry ────────────────────────────────────


def test_load_missing_file(tmp_home: Path) -> None:
    result = load_repo_registry()
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["repos"] == []


def test_load_happy(tmp_path: Path) -> None:
    config = tmp_path / "registry.json"
    config.write_text(json.dumps([
        {"name": "zep-crm", "path": str(tmp_path), "is_default": True, "role": "backend"},
        {"name": "zep-client", "path": str(tmp_path), "role": "frontend"},
    ]), encoding="utf-8")
    result = load_repo_registry(str(config))
    assert result["ok"] is True
    assert len(result["repos"]) == 2
    assert result["default_count"] == 1
    assert result["repos"][0]["name"] == "zep-crm"
    assert result["repos"][0]["is_default"] is True
    assert result["repos"][1]["is_default"] is False


def test_load_skips_bad_entries(tmp_path: Path) -> None:
    config = tmp_path / "registry.json"
    config.write_text(json.dumps([
        {"name": "ok-1", "path": str(tmp_path)},
        "not a dict",  # invalid
        {"path": "only path no name"},  # invalid
        {"name": "no-path"},  # invalid
        {"name": "ok-2", "path": str(tmp_path)},
    ]), encoding="utf-8")
    result = load_repo_registry(str(config))
    assert result["ok"] is True
    assert len(result["repos"]) == 2
    assert len(result["warnings"]) == 3


def test_load_malformed_json(tmp_path: Path) -> None:
    config = tmp_path / "registry.json"
    config.write_text("not json", encoding="utf-8")
    result = load_repo_registry(str(config))
    assert result["ok"] is False
    assert "invalid JSON" in result["error"]


def test_load_not_array(tmp_path: Path) -> None:
    config = tmp_path / "registry.json"
    config.write_text(json.dumps({"not": "array"}), encoding="utf-8")
    result = load_repo_registry(str(config))
    assert result["ok"] is False


def test_load_korean_names(tmp_path: Path) -> None:
    config = tmp_path / "registry.json"
    config.write_text(json.dumps([
        {"name": "한국어레포", "path": str(tmp_path), "notes": "메인 백엔드"},
    ], ensure_ascii=False), encoding="utf-8")
    result = load_repo_registry(str(config))
    assert result["ok"] is True
    assert result["repos"][0]["name"] == "한국어레포"
    assert result["repos"][0]["notes"] == "메인 백엔드"


# ── validate_repo_paths ───────────────────────────────────


def test_validate_existing_paths(tmp_path: Path) -> None:
    (tmp_path / "repo-a").mkdir()
    (tmp_path / "repo-a" / "package.json").write_text("{}")
    (tmp_path / "repo-a" / ".git").mkdir()
    (tmp_path / "repo-b").mkdir()  # no manifest, no git

    repos = [
        {"name": "a", "path": str(tmp_path / "repo-a")},
        {"name": "b", "path": str(tmp_path / "repo-b")},
        {"name": "c", "path": str(tmp_path / "does-not-exist")},
    ]
    result = validate_repo_paths(repos)
    assert result["ok"] is True
    assert len(result["passed"]) == 2
    assert len(result["failed"]) == 1
    a = next(p for p in result["passed"] if p["name"] == "a")
    assert a["has_git"] is True
    assert a["has_manifest"] is True
    b = next(p for p in result["passed"] if p["name"] == "b")
    assert b["has_git"] is False
    assert b["has_manifest"] is False


def test_validate_path_is_file_not_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("")
    result = validate_repo_paths([{"name": "x", "path": str(file_path)}])
    assert len(result["failed"]) == 1
    assert "not a directory" in result["failed"][0]["reason"]


def test_validate_invalid_input() -> None:
    assert validate_repo_paths("not a list")["ok"] is False  # type: ignore[arg-type]


# ── iterate_brownfield_repos ─────────────────────────────


def test_iterate_orders_defaults_first() -> None:
    repos = [
        {"name": "a", "is_default": False},
        {"name": "b", "is_default": True},
        {"name": "c", "is_default": False},
        {"name": "d", "is_default": True},
    ]
    ordered = iterate_brownfield_repos(repos)
    names = [r["name"] for r in ordered]
    assert names == ["b", "d", "a", "c"]


def test_iterate_only_defaults() -> None:
    repos = [
        {"name": "a", "is_default": True},
        {"name": "b", "is_default": False},
    ]
    only = iterate_brownfield_repos(repos, only_defaults=True)
    assert len(only) == 1
    assert only[0]["name"] == "a"


def test_iterate_empty() -> None:
    assert iterate_brownfield_repos([]) == []


def test_iterate_invalid() -> None:
    assert iterate_brownfield_repos("not a list") == []  # type: ignore[arg-type]


# ── parse_inline_paths ────────────────────────────────────


def test_parse_inline_csv(tmp_path: Path) -> None:
    csv = f"{tmp_path}/repo-a, {tmp_path}/repo-b , {tmp_path}/repo-c"
    result = parse_inline_paths(csv)
    assert result["ok"] is True
    assert len(result["repos"]) == 3
    assert all(r["is_default"] for r in result["repos"])  # inline = default
    assert all(r["notes"] == "inline" for r in result["repos"])


def test_parse_inline_empty() -> None:
    result = parse_inline_paths("")
    assert result["ok"] is True
    assert result["repos"] == []


def test_parse_inline_invalid_input() -> None:
    assert parse_inline_paths(None)["ok"] is False  # type: ignore[arg-type]


def test_parse_inline_korean_names(tmp_path: Path) -> None:
    korean_dir = tmp_path / "한국어레포"
    korean_dir.mkdir()
    result = parse_inline_paths(str(korean_dir))
    assert result["repos"][0]["name"] == "한국어레포"
