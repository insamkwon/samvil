"""Tests for evidence_validator.py (v2.5.0, Phase 3)."""

import pytest
from pathlib import Path

from samvil_mcp.evidence_validator import (
    parse_evidence,
    validate_file_exists,
    validate_line_range,
    read_evidence_snippet,
    validate_evidence_list,
)


def test_parse_simple_evidence():
    result = parse_evidence("src/auth.ts:15")
    assert result == {
        "file": "src/auth.ts",
        "line_start": 15,
        "line_end": 15,
        "note": "",
    }


def test_parse_range_evidence():
    result = parse_evidence("src/auth.ts:15-20")
    assert result["line_start"] == 15
    assert result["line_end"] == 20


def test_parse_evidence_with_note():
    result = parse_evidence("src/auth.ts:15 (zod schema)")
    assert result["note"] == "zod schema"


def test_parse_invalid():
    result = parse_evidence("not a valid reference")
    assert result is None


def test_validate_file_exists_true(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("line1\nline2\n")
    result = validate_file_exists({"file": "a.py"}, str(tmp_path))
    assert result["exists"] is True


def test_validate_file_exists_false(tmp_path):
    result = validate_file_exists({"file": "missing.py"}, str(tmp_path))
    assert result["exists"] is False


def test_validate_line_range(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("line1\nline2\nline3\n")
    evidence = {"file": "x.py", "line_start": 1, "line_end": 2}
    result = validate_line_range(evidence, str(tmp_path))
    assert result["valid"] is True


def test_validate_line_out_of_range(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("line1\n")
    evidence = {"file": "x.py", "line_start": 1, "line_end": 50}
    result = validate_line_range(evidence, str(tmp_path))
    assert result["valid"] is False


def test_read_snippet(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("line1\nline2\nline3\nline4\n")
    evidence = {"file": "x.py", "line_start": 2, "line_end": 2}
    snippet = read_evidence_snippet(evidence, str(tmp_path), context=0)
    assert "line2" in snippet


def test_read_snippet_with_context(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("a\nb\nc\nd\ne\n")
    evidence = {"file": "x.py", "line_start": 3, "line_end": 3}
    snippet = read_evidence_snippet(evidence, str(tmp_path), context=1)
    # Should include lines 2, 3, 4
    assert "b" in snippet
    assert "c" in snippet
    assert "d" in snippet


def test_validate_evidence_list(tmp_path):
    (tmp_path / "a.py").write_text("x\ny\nz\n")
    result = validate_evidence_list(
        ["a.py:1", "a.py:2", "missing.py:1", "malformed"],
        str(tmp_path),
    )
    assert result["total"] == 4
    assert result["valid_count"] == 2  # a.py:1 and a.py:2
    assert result["all_valid"] is False
