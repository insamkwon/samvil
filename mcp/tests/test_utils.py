"""Tests for samvil_mcp.utils (v4.30 W1.3 — dedup of _read_json_safe)."""

from __future__ import annotations

from pathlib import Path

from samvil_mcp.utils import read_json_or_empty, read_json_safe


def test_read_json_safe_valid(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    p.write_text('{"k": 1}')
    assert read_json_safe(p) == {"k": 1}


def test_read_json_safe_missing_and_invalid(tmp_path: Path) -> None:
    assert read_json_safe(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert read_json_safe(bad) is None


def test_read_json_or_empty_fallbacks(tmp_path: Path) -> None:
    assert read_json_or_empty(tmp_path / "missing.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert read_json_or_empty(bad) == {}
    # non-dict JSON coerces to {}
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2]")
    assert read_json_or_empty(arr) == {}


def test_read_json_or_empty_valid(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    p.write_text('{"k": "v"}')
    assert read_json_or_empty(p) == {"k": "v"}
