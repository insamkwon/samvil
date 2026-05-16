"""Tests for benchmark module (v4.29.0).

External fetches are mocked. We do NOT make real network calls in
pytest — that would be flaky. The fetch function is exercised via its
output shape only.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from samvil_mcp.benchmark import (
    DEFAULT_TARGETS,
    append_gap_to_feedback_log,
    classify_changelog_items,
    fetch_external_changelog,
    load_benchmark_targets,
    render_gap_entry,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


SAMPLE_CHANGELOG = """# Changelog

## [1.2.3] - 2026-05-16

### Added
- New refine gate pattern
- Multi-repo brownfield support

### Fixed
- Race condition in interview persist

## [1.2.2] - 2026-05-01

### Added
- Welcome skill
"""


# ── fetch_external_changelog ────────────────────────────────


def test_fetch_invalid_url() -> None:
    result = fetch_external_changelog(url="")
    assert result["ok"] is False


def test_fetch_network_error_graceful() -> None:
    """Bad host → ok=False, no raise."""
    result = fetch_external_changelog(
        url="http://this-host-does-not-exist.invalid", timeout=1.0,
    )
    assert result["ok"] is False
    assert "error" in result


def test_fetch_parses_keep_a_changelog_format(monkeypatch) -> None:
    """Mock urlopen to return our sample changelog and verify parsing."""
    mock_response = MagicMock()
    mock_response.read.return_value = SAMPLE_CHANGELOG.encode("utf-8")
    mock_response.__enter__ = lambda self: mock_response
    mock_response.__exit__ = lambda self, *a: None
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = fetch_external_changelog(url="http://example.com/CHANGELOG.md")
    assert result["ok"] is True
    assert len(result["items"]) == 2
    assert result["items"][0]["version"] == "1.2.3"
    assert result["items"][0]["date"] == "2026-05-16"
    assert "New refine gate pattern" in result["items"][0]["bullets"]
    assert "Welcome skill" in result["items"][1]["bullets"]


def test_fetch_no_sections_found(monkeypatch) -> None:
    """Markdown without ## headings → no sections → ok=False."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"Just some text\nNothing structured"
    mock_response.__enter__ = lambda self: mock_response
    mock_response.__exit__ = lambda self, *a: None
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = fetch_external_changelog(url="http://example.com/CHANGELOG.md")
    assert result["ok"] is False
    assert "no parseable" in result["error"].lower()


# ── classify_changelog_items ────────────────────────────────


def test_classify_categorizes_correctly() -> None:
    items = [
        {"version": "1.0", "bullets": [
            "Added refine gate pattern",
            "Auto-implement competitor patterns",
            "Completely new paradigm Z",
        ]},
    ]
    result = classify_changelog_items(
        items,
        samvil_already_have=["refine gate"],
        samvil_rejected=["auto-implement"],
    )
    assert result["ok"] is True
    cat = result["categorized"]
    assert len(cat["already_have"]) == 1
    assert cat["already_have"][0]["matched_token"] == "refine gate"
    assert len(cat["rejected"]) == 1
    assert len(cat["gaps"]) == 1
    assert "paradigm Z" in cat["gaps"][0]["bullet"]


def test_classify_empty_signals_all_gaps() -> None:
    items = [{"version": "1.0", "bullets": ["X", "Y", "Z"]}]
    result = classify_changelog_items(items)
    assert len(result["categorized"]["gaps"]) == 3
    assert len(result["categorized"]["already_have"]) == 0


def test_classify_invalid_input() -> None:
    assert classify_changelog_items("not a list")["ok"] is False  # type: ignore[arg-type]


def test_classify_korean_signals() -> None:
    items = [{"version": "1.0", "bullets": ["한국어 처리 추가됨"]}]
    result = classify_changelog_items(items, samvil_already_have=["한국어"])
    assert len(result["categorized"]["already_have"]) == 1


# ── render_gap_entry ────────────────────────────────────────


def test_render_gap_entry_shape() -> None:
    gap = {"section": "1.2.3", "bullet": "Cool new feature X"}
    entry = render_gap_entry(gap, target_name="ouroboros", target_url="http://example.com")
    assert entry["priority"] == "BENEFIT"
    assert entry["source"] == "samvil-benchmark"
    assert entry["component"] == "external:ouroboros"
    assert entry["id"].startswith("benchmark-")
    assert "Cool new feature X" in entry["problem"]


# ── append_gap_to_feedback_log ──────────────────────────────


def test_append_to_new_log(project_root: Path) -> None:
    log_path = project_root / "harness-feedback.log"
    entry = {"id": "test-1", "priority": "BENEFIT", "name": "X"}
    result = append_gap_to_feedback_log(entry, str(log_path))
    assert result["ok"] is True
    assert result["appended"] is True
    parsed = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(parsed) == 1
    assert parsed[0]["id"] == "test-1"


def test_append_dedup_by_id(project_root: Path) -> None:
    log_path = project_root / "harness-feedback.log"
    entry = {"id": "test-1", "priority": "BENEFIT", "name": "X"}
    append_gap_to_feedback_log(entry, str(log_path))
    result = append_gap_to_feedback_log(entry, str(log_path))
    assert result["ok"] is True
    assert result["appended"] is False
    assert "duplicate" in result["reason"]


def test_append_to_existing_log(project_root: Path) -> None:
    log_path = project_root / "harness-feedback.log"
    log_path.write_text(json.dumps([{"id": "old-1"}]), encoding="utf-8")
    entry = {"id": "new-1", "priority": "BENEFIT", "name": "X"}
    result = append_gap_to_feedback_log(entry, str(log_path))
    assert result["ok"] is True
    parsed = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(parsed) == 2


def test_append_existing_log_not_array(project_root: Path) -> None:
    log_path = project_root / "harness-feedback.log"
    log_path.write_text('{"not": "array"}', encoding="utf-8")
    result = append_gap_to_feedback_log({"id": "x"}, str(log_path))
    assert result["ok"] is False
    assert "not a JSON array" in result["error"]


def test_append_invalid_input() -> None:
    result = append_gap_to_feedback_log({}, "/tmp/x")
    assert result["ok"] is False


def test_append_korean_in_entry(project_root: Path) -> None:
    log_path = project_root / "harness-feedback.log"
    entry = {"id": "ko-1", "priority": "BENEFIT", "name": "한국어 항목"}
    append_gap_to_feedback_log(entry, str(log_path))
    raw = log_path.read_text(encoding="utf-8")
    assert "한국어 항목" in raw
    assert "\\u" not in raw


# ── load_benchmark_targets ──────────────────────────────────


def test_load_defaults_only(project_root: Path) -> None:
    config = project_root / "no-such-file.json"
    result = load_benchmark_targets(str(config))
    assert result["ok"] is True
    assert len(result["targets"]) >= len(DEFAULT_TARGETS)
    assert result["overrides_applied"] == 0


def test_load_with_user_overrides(project_root: Path) -> None:
    config = project_root / "benchmark-targets.json"
    config.write_text(json.dumps([
        {"name": "ouroboros", "url": "https://my-fork.example/CHANGELOG.md", "why": "fork"},
        {"name": "custom-system", "url": "https://example.com/changelog", "why": "internal"},
    ]), encoding="utf-8")
    result = load_benchmark_targets(str(config))
    assert result["ok"] is True
    assert result["overrides_applied"] == 2
    by_name = {t["name"]: t for t in result["targets"]}
    assert by_name["ouroboros"]["url"] == "https://my-fork.example/CHANGELOG.md"
    assert by_name["ouroboros"]["source"] == "user"
    assert "custom-system" in by_name


def test_load_malformed_overrides(project_root: Path) -> None:
    config = project_root / "benchmark-targets.json"
    config.write_text("not json", encoding="utf-8")
    result = load_benchmark_targets(str(config))
    assert result["ok"] is False
    # Defaults still returned
    assert len(result["targets"]) >= len(DEFAULT_TARGETS)
