"""Tests for pain_capture module (v4.22.0).

Covers:
- capture_pain happy path (1..5 severity)
- capture_pain invalid stage / severity
- pain_text optional for severity 1-3, required-but-missing flag for 4-5
- load_pain_feedback aggregations (by_stage / by_severity / avg / high_severity)
- load_pain_feedback missing file
- load_pain_feedback malformed lines (graceful skip)
- Korean UTF-8 preserved in pain_text
- File errors return ok=False without raising
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.pain_capture import (
    FEEDBACK_FILENAME,
    VALID_STAGES,
    capture_pain,
    load_pain_feedback,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def _read_lines(project_root: Path) -> list[dict]:
    path = project_root / ".samvil" / FEEDBACK_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── capture_pain ───────────────────────────────────────────────


def test_capture_pain_happy(project_root: Path) -> None:
    result = capture_pain(
        project_root=str(project_root),
        stage="interview",
        severity=3,
        pain_text="보통이었어",
    )
    assert result["ok"] is True
    assert result["severity"] == 3
    assert result["pain_required_but_missing"] is False
    entries = _read_lines(project_root)
    assert len(entries) == 1
    assert entries[0]["stage"] == "interview"
    assert entries[0]["pain_text"] == "보통이었어"


def test_capture_pain_invalid_stage(project_root: Path) -> None:
    result = capture_pain(
        project_root=str(project_root),
        stage="invalid_stage",
        severity=3,
    )
    assert result["ok"] is False
    assert "invalid stage" in result["error"]


def test_capture_pain_invalid_severity(project_root: Path) -> None:
    for bad in [0, 6, -1, "three", None]:
        result = capture_pain(
            project_root=str(project_root),
            stage="interview",
            severity=bad,  # type: ignore[arg-type]
        )
        assert result["ok"] is False, f"expected fail for severity={bad!r}"


def test_capture_pain_high_severity_text_required_flag(project_root: Path) -> None:
    """Severity ≥ 4 with empty pain_text → entry still written, but flag raised."""
    result = capture_pain(
        project_root=str(project_root),
        stage="build",
        severity=4,
        pain_text="",
    )
    assert result["ok"] is True
    assert result["pain_required_but_missing"] is True

    # With text
    result2 = capture_pain(
        project_root=str(project_root),
        stage="build",
        severity=5,
        pain_text="재작업 필요했음",
    )
    assert result2["pain_required_but_missing"] is False


def test_capture_pain_low_severity_no_text_ok(project_root: Path) -> None:
    """Severity 1-3 doesn't require pain_text."""
    for sev in [1, 2, 3]:
        result = capture_pain(
            project_root=str(project_root),
            stage="qa",
            severity=sev,
        )
        assert result["ok"] is True
        assert result["pain_required_but_missing"] is False


def test_capture_pain_korean_utf8(project_root: Path) -> None:
    capture_pain(
        project_root=str(project_root),
        stage="seed",
        severity=4,
        pain_text="시드가 인터뷰에서 한 말이랑 달랐음 — 제약 누락",
    )
    raw = (project_root / ".samvil" / FEEDBACK_FILENAME).read_text(encoding="utf-8")
    assert "제약 누락" in raw
    assert "\\u" not in raw  # ensure_ascii=False


def test_capture_pain_appends_not_overwrites(project_root: Path) -> None:
    capture_pain(project_root=str(project_root), stage="interview", severity=2)
    capture_pain(project_root=str(project_root), stage="seed", severity=4, pain_text="x")
    capture_pain(project_root=str(project_root), stage="build", severity=3)

    entries = _read_lines(project_root)
    assert len(entries) == 3
    assert [e["stage"] for e in entries] == ["interview", "seed", "build"]


def test_capture_pain_unwritable_path(tmp_path: Path) -> None:
    bad_root = tmp_path / "ro"
    bad_root.mkdir()
    (bad_root / ".samvil").write_text("not a directory")
    result = capture_pain(
        project_root=str(bad_root),
        stage="interview",
        severity=3,
    )
    assert result["ok"] is False
    assert "error" in result


# ── load_pain_feedback ─────────────────────────────────────────


def test_load_missing_file(project_root: Path) -> None:
    result = load_pain_feedback(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["entries"] == []


def test_load_aggregations(project_root: Path) -> None:
    capture_pain(project_root=str(project_root), stage="interview", severity=2)
    capture_pain(project_root=str(project_root), stage="interview", severity=4, pain_text="질문 너무 많음")
    capture_pain(project_root=str(project_root), stage="seed", severity=5, pain_text="시드 완전히 다름")
    capture_pain(project_root=str(project_root), stage="build", severity=3)

    result = load_pain_feedback(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["entries"]) == 4
    assert len(result["by_stage"]["interview"]) == 2
    assert len(result["by_stage"]["seed"]) == 1
    assert result["by_severity"][4] == 1
    assert result["by_severity"][5] == 1
    assert result["high_severity_count"] == 2
    assert "질문 너무 많음" in result["high_severity_texts"]
    assert "시드 완전히 다름" in result["high_severity_texts"]
    assert result["severity_avg"] == 3.5  # (2+4+5+3)/4


def test_load_skips_malformed(project_root: Path) -> None:
    samvil = project_root / ".samvil"
    samvil.mkdir()
    (samvil / FEEDBACK_FILENAME).write_text(
        '{"stage": "interview", "severity": 3, "ts": "x"}\n'
        'not json\n'
        '{"stage": "INVALID", "severity": 3}\n'  # invalid stage
        '{"stage": "build", "severity": 99}\n'   # out-of-range severity
        '"just a string"\n'
        '{"stage": "qa", "severity": 4, "pain_text": "ok"}\n',
        encoding="utf-8",
    )

    result = load_pain_feedback(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["entries"]) == 2  # interview + qa
    assert result["high_severity_count"] == 1


def test_load_dedupes_nothing(project_root: Path) -> None:
    """Each call appends — same severity / stage can occur many times."""
    for _ in range(5):
        capture_pain(project_root=str(project_root), stage="interview", severity=3)
    result = load_pain_feedback(project_root=str(project_root))
    assert len(result["entries"]) == 5
    assert len(result["by_stage"]["interview"]) == 5


def test_valid_stages_includes_main_pipeline(project_root: Path) -> None:
    """Sanity: all major pipeline stages are accepted."""
    for stage in ["interview", "seed", "build", "qa", "scaffold", "retro"]:
        result = capture_pain(project_root=str(project_root), stage=stage, severity=2)
        assert result["ok"] is True, f"stage {stage} should be valid"
    assert "interview" in VALID_STAGES
    assert "seed" in VALID_STAGES
