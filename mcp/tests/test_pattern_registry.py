"""Tests for Pattern Registry."""

from samvil_mcp.pattern_registry import get_pattern, list_patterns, render_patterns


def test_list_patterns_filters_solution_type():
    patterns = list_patterns(solution_type="game")

    assert [p.pattern_id for p in patterns] == ["phaser-game"]


def test_list_patterns_filters_framework():
    patterns = list_patterns(framework="vite-react")
    ids = {p.pattern_id for p in patterns}

    assert "vite-react" in ids
    assert "dashboard-recharts" in ids


def test_get_pattern_returns_entry():
    pattern = get_pattern("nextjs-app-router")

    assert pattern is not None
    assert pattern.name == "Next.js App Router Web App"


def test_get_pattern_missing_returns_none():
    assert get_pattern("missing") is None


def test_render_patterns_includes_build_and_qa_guidance():
    pattern = get_pattern("vite-react")
    assert pattern is not None

    text = render_patterns([pattern])

    assert "vite-react" in text
    assert "Build guidance" in text
    assert "QA focus" in text
