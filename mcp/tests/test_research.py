"""Tests for research.py (v2.7.0, PATH 4)."""

import pytest

from samvil_mcp.research import extract_research_query, format_research_results


def test_extract_query_strips_english_prefix():
    assert extract_research_query("What are Stripe rate limits?") == "Stripe rate limits"


def test_extract_query_strips_how_prefix():
    assert extract_research_query("How does OAuth work?") == "OAuth work"


def test_extract_query_strips_korean_prefix():
    result = extract_research_query("최신 Next.js 버전?")
    assert "Next.js" in result


def test_extract_query_returns_original_on_no_match():
    assert extract_research_query("Stripe API") == "Stripe API"


def test_extract_query_empty_fallback():
    result = extract_research_query("")
    assert result == ""


def test_format_results_top_3():
    results = [
        {"title": f"T{i}", "snippet": f"S{i}", "url": f"u{i}"}
        for i in range(5)
    ]
    formatted = format_research_results(results)
    assert formatted["has_results"]
    assert formatted["count"] == 3
    assert len(formatted["sources"]) == 3


def test_format_empty_results():
    formatted = format_research_results([])
    assert not formatted["has_results"]


def test_format_results_with_content_field():
    results = [{"title": "T", "content": "C" * 300, "url": "u1"}]
    formatted = format_research_results(results)
    assert formatted["has_results"]
    assert formatted["count"] == 1
