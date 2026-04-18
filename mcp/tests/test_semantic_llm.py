"""Tests for semantic_checker LLM extensions (v2.7.0, T1)."""

import pytest

from samvil_mcp.semantic_checker import (
    build_llm_prompt,
    merge_llm_verdict,
    should_use_llm,
    analyze_code_snippet,
)


def test_should_use_llm_minimal():
    assert not should_use_llm("minimal", "HIGH")


def test_should_use_llm_standard():
    assert not should_use_llm("standard", "HIGH")


def test_should_use_llm_thorough_low_risk():
    assert not should_use_llm("thorough", "LOW")


def test_should_use_llm_thorough_medium_risk():
    assert should_use_llm("thorough", "MEDIUM")


def test_should_use_llm_thorough_high_risk():
    assert should_use_llm("thorough", "HIGH")


def test_should_use_llm_full_low_risk():
    assert should_use_llm("full", "LOW")


def test_build_llm_prompt_contains_ac():
    prompt = build_llm_prompt("return 1", "User signup")
    assert "User signup" in prompt
    assert "return 1" in prompt


def test_merge_llm_verdict_real_implementation():
    heuristic = analyze_code_snippet("const x = await db.query()", "Query DB")
    llm_resp = {"is_real_implementation": True, "confidence": 0.95, "reasoning": "Real DB call"}
    result = merge_llm_verdict(heuristic, llm_resp)
    assert "llm_verdict" in result
    assert result["llm_verdict"]["is_real_implementation"] is True
    assert result["risk_level"] == heuristic["risk_level"]  # unchanged


def test_merge_llm_verdict_stub_detected():
    heuristic = analyze_code_snippet("return { status: 'ok' }", "Payment")
    llm_resp = {
        "is_real_implementation": False,
        "confidence": 0.9,
        "reasoning": "Returns hardcoded constant",
        "evidence_citations": ["line 1"],
    }
    result = merge_llm_verdict(heuristic, llm_resp)
    assert result["risk_level"] == "HIGH"
    assert any(f["pattern"] == "llm_detected" for f in result["findings"])


def test_merge_llm_verdict_preserves_original_findings():
    heuristic = analyze_code_snippet("return 'mock_123'", "Auth check")
    original_count = len(heuristic["findings"])
    llm_resp = {"is_real_implementation": False, "confidence": 0.8, "reasoning": "Mock"}
    result = merge_llm_verdict(heuristic, llm_resp)
    assert len(result["findings"]) >= original_count
