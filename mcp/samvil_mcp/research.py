"""Research WebFetch helpers (v2.7.0, PATH 4).

Provides query extraction and result formatting for research-routed
interview questions. The actual Tavily MCP call is done by the skill.

Flow:
  1. skill detects path=research → calls extract_query
  2. skill calls Tavily MCP → gets raw results
  3. skill calls format_research → formatted summary
  4. skill asks user to confirm → [from-research] prefix
"""

from __future__ import annotations

import re


def extract_research_query(question: str) -> str:
    """Extract searchable query from a research-routed question."""
    q = question.strip()
    prefixes = [
        r"^(What are|What is|Does|How does|How do|어떤|최신|무엇)\s+",
    ]
    for p in prefixes:
        q = re.sub(p, "", q, flags=re.IGNORECASE)
    q = q.rstrip("?").strip()
    return q if q else question


def format_research_results(results: list[dict]) -> dict:
    """Format top 3 results for user confirmation."""
    if not results:
        return {
            "has_results": False,
            "fallback_message": "검색 결과 없음. 사용자가 직접 답변 필요.",
        }

    top_3 = results[:3]
    summary = []
    sources = []
    for r in top_3:
        title = r.get("title", "untitled")
        snippet = r.get("snippet", r.get("content", ""))[:200]
        url = r.get("url", r.get("link", "unknown"))
        summary.append(f"- {title}: {snippet}")
        sources.append(url)

    return {
        "has_results": True,
        "summary_markdown": "\n".join(summary),
        "sources": sources,
        "count": len(top_3),
    }
