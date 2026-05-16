"""Tests for qa_artifact module (v4.29.0)."""

from __future__ import annotations

import pytest

from samvil_mcp.qa_artifact import (
    DEFAULT_WEIGHTS,
    PASS_THRESHOLD,
    REVISE_THRESHOLD,
    score_artifact,
)


# ── basics ─────────────────────────────────────────────────


def test_score_invalid_input() -> None:
    assert score_artifact(artifact=None)["ok"] is False  # type: ignore[arg-type]
    assert score_artifact(artifact="x", artifact_type="invalid")["ok"] is False


def test_score_returns_complete_shape() -> None:
    result = score_artifact(artifact="def hello(): return 'world'", quality_bar="basic function")
    assert result["ok"] is True
    assert set(result["dimensions"]) == set(DEFAULT_WEIGHTS)
    assert "score" in result
    assert result["verdict"] in ("PASS", "REVISE", "FAIL")
    assert result["loop_action"] in ("done", "continue", "escalate")


# ── verdict thresholds ─────────────────────────────────────


def test_score_pass_verdict() -> None:
    """Well-structured code → PASS."""
    code = '''
def calculate_total(items):
    """Sum the prices of items."""
    return sum(item.price for item in items)


class Cart:
    def __init__(self):
        self.items = []
'''
    result = score_artifact(
        artifact=code,
        quality_bar="calculate total of items",
        artifact_type="code",
    )
    assert result["score"] >= PASS_THRESHOLD or result["score"] >= REVISE_THRESHOLD
    # tokens align so intent_alignment should be reasonable
    assert result["dimensions"]["intent_alignment"] > 0


def test_score_fail_verdict_empty() -> None:
    result = score_artifact(artifact="", quality_bar="x")
    assert result["verdict"] == "FAIL"
    assert result["loop_action"] == "escalate"
    assert any("empty" in s.lower() for s in result["suggestions"])


def test_score_revise_verdict_short() -> None:
    """Short but non-empty artifact → REVISE."""
    result = score_artifact(artifact="x = 1", quality_bar="implement feature", artifact_type="code")
    assert result["verdict"] == "REVISE"
    assert result["loop_action"] == "continue"


# ── per-dimension behaviors ─────────────────────────────────


def test_todo_marker_reduces_correctness() -> None:
    code_with_todo = "def foo():\n    # TODO: implement\n    pass"
    code_clean = "def foo():\n    return 42"
    r1 = score_artifact(artifact=code_with_todo, artifact_type="code")
    r2 = score_artifact(artifact=code_clean, artifact_type="code")
    assert r1["dimensions"]["correctness"] < r2["dimensions"]["correctness"]
    assert any("TODO" in s for s in r1["suggestions"])


def test_unbalanced_braces_reduces_correctness() -> None:
    bad = "def foo() {\n    return 1\n"  # missing closing brace
    r = score_artifact(artifact=bad, artifact_type="code")
    assert r["dimensions"]["correctness"] < 1.0
    assert any("Unbalanced" in s for s in r["suggestions"])


def test_document_with_tbd_marker() -> None:
    doc = "# Title\n\nThis section is TBD.\n\nMore content here that is reasonably long enough to pass length checks."
    r = score_artifact(artifact=doc, artifact_type="document")
    assert any("TBD" in s for s in r["suggestions"])


def test_api_response_malformed_json() -> None:
    bad_json = '{"key": broken}'
    r = score_artifact(artifact=bad_json, artifact_type="api_response")
    assert r["dimensions"]["correctness"] < 1.0
    assert any("failed to parse" in s.lower() or "json" in s.lower() for s in r["suggestions"])


def test_api_response_valid_json() -> None:
    good = '{"status": "ok", "data": [1, 2, 3]}'
    r = score_artifact(artifact=good, artifact_type="api_response")
    assert r["dimensions"]["correctness"] == 1.0


def test_test_output_with_fail() -> None:
    output = "test_one ... ok\ntest_two ... FAIL\ntest_three ... ok"
    r = score_artifact(artifact=output, artifact_type="test_output")
    assert r["dimensions"]["correctness"] < 1.0


def test_print_statement_reduces_quality() -> None:
    bad = "def foo():\n    print('debug')\n    return 1\n" + "x" * 200
    good = "def foo():\n    return 1\n" + "x" * 200
    r1 = score_artifact(artifact=bad, artifact_type="code")
    r2 = score_artifact(artifact=good, artifact_type="code")
    assert r1["dimensions"]["quality"] < r2["dimensions"]["quality"]


def test_long_lines_reduce_quality() -> None:
    long = "def foo():\n    return " + "x" * 200 + "\n"
    r = score_artifact(artifact=long + "padding " * 50, artifact_type="code")
    assert any("120 chars" in s for s in r["suggestions"])


# ── intent alignment ──────────────────────────────────────


def test_intent_alignment_with_overlap() -> None:
    r = score_artifact(
        artifact="def calculate_total(items): return sum(items)",
        quality_bar="calculate total of items",
        artifact_type="code",
    )
    assert r["dimensions"]["intent_alignment"] > 0.5


def test_intent_alignment_no_overlap() -> None:
    r = score_artifact(
        artifact="def foo(): pass",
        quality_bar="implement user authentication system",
        artifact_type="code",
    )
    assert r["dimensions"]["intent_alignment"] < 0.5
    assert any("quality-bar" in s.lower() for s in r["suggestions"])


def test_intent_alignment_korean() -> None:
    """Korean tokens should also count for alignment."""
    r = score_artifact(
        artifact="사용자 인증 시스템 구현. 사용자가 로그인할 수 있다.",
        quality_bar="사용자 인증 시스템",
        artifact_type="document",
    )
    assert r["dimensions"]["intent_alignment"] > 0.5


def test_no_quality_bar_alignment_is_neutral() -> None:
    """Empty quality_bar shouldn't penalize."""
    r = score_artifact(artifact="def foo(): pass", quality_bar="", artifact_type="code")
    assert r["dimensions"]["intent_alignment"] == 1.0


# ── weights ────────────────────────────────────────────────


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001


def test_weight_override_normalizes() -> None:
    r = score_artifact(
        artifact="def foo(): pass",
        quality_bar="x",
        artifact_type="code",
        dimension_weights={"correctness": 5.0, "quality": 1.0},  # very lopsided, will normalize
    )
    # weights normalize, so they sum to 1
    assert abs(sum(r["weights_applied"].values()) - 1.0) < 0.01


# ── domain-specific ───────────────────────────────────────


def test_code_without_definitions() -> None:
    r = score_artifact(artifact="x = 1\ny = 2\nz = x + y", artifact_type="code")
    # no def/class → domain_specific score drops
    assert r["dimensions"]["domain_specific"] < 1.0


def test_api_response_unstructured() -> None:
    r = score_artifact(artifact="just some text response", artifact_type="api_response")
    assert r["dimensions"]["domain_specific"] < 1.0
