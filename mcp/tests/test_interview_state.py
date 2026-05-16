"""Tests for interview_state module (v4.19.0 + v4.21.0 Refine Gate).

Covers:
- persist_answer happy path (Q&A only)
- persist_answer with AC candidates (unified signature)
- persist_answer with refine payload (v4.21 — Refine Gate)
- refine payload validation (5-section schema)
- load_progress aggregates constraints / out_of_scope / tech_preferences
- mark_phase_complete marker write
- load_progress with mixed entries
- load_progress with missing file
- load_progress with malformed lines (graceful)
- clear_progress
- Concurrent appends (atomic-ish via flock)
- Korean/UTF-8 content preserved
- Permission/OS error returns ok=False without raising
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from samvil_mcp.interview_state import (
    PROGRESS_FILENAME,
    clear_progress,
    load_progress,
    mark_phase_complete,
    persist_answer,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Temporary project root with .samvil/ created on demand."""
    return tmp_path


def _read_lines(project_root: Path) -> list[dict]:
    path = project_root / ".samvil" / PROGRESS_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── persist_answer ─────────────────────────────────────────────────


def test_persist_answer_qa_only(project_root: Path) -> None:
    result = persist_answer(
        project_root=str(project_root),
        phase="core",
        question="이 앱의 타겟 사용자는?",
        answer="개인 솔로 개발자",
        source="from-user",
    )
    assert result["ok"] is True
    assert result["counts"] == {"qa": 1, "ac_candidate": 0, "refined_answer": 0}

    entries = _read_lines(project_root)
    assert len(entries) == 1
    assert entries[0]["type"] == "qa"
    assert entries[0]["phase"] == "core"
    assert entries[0]["q"] == "이 앱의 타겟 사용자는?"
    assert entries[0]["a"] == "개인 솔로 개발자"
    assert entries[0]["source"] == "from-user"
    assert "ts" in entries[0]


def test_persist_answer_with_ac_candidates(project_root: Path) -> None:
    result = persist_answer(
        project_root=str(project_root),
        phase="scope",
        question="어떤 기능이 필요한가요?",
        answer="할일 추가, 삭제, 완료 표시",
        ac_candidates=[
            "사용자는 할일을 추가할 수 있다",
            "사용자는 할일을 삭제할 수 있다",
            "사용자는 할일을 완료 표시할 수 있다",
        ],
    )
    assert result["ok"] is True
    assert result["counts"] == {"qa": 1, "ac_candidate": 3, "refined_answer": 0}

    entries = _read_lines(project_root)
    assert len(entries) == 4
    assert entries[0]["type"] == "qa"
    assert all(e["type"] == "ac_candidate" for e in entries[1:])
    assert entries[1]["ac_text"] == "사용자는 할일을 추가할 수 있다"


def test_persist_answer_skips_blank_ac_candidates(project_root: Path) -> None:
    result = persist_answer(
        project_root=str(project_root),
        phase="scope",
        question="q",
        answer="a",
        ac_candidates=["", "  ", "real ac", None],  # type: ignore[list-item]
    )
    assert result["ok"] is True
    assert result["counts"]["ac_candidate"] == 1


def test_persist_answer_required_fields(project_root: Path) -> None:
    r1 = persist_answer(project_root=str(project_root), phase="", question="q", answer="a")
    assert r1["ok"] is False
    assert "phase" in r1["error"]

    r2 = persist_answer(project_root=str(project_root), phase="core", question="", answer="a")
    assert r2["ok"] is False
    assert "question" in r2["error"]


def test_persist_answer_korean_utf8_preserved(project_root: Path) -> None:
    persist_answer(
        project_root=str(project_root),
        phase="core",
        question="앱의 핵심 가치는?",
        answer="사용자가 30초 안에 가치를 느끼는 것",
        ac_candidates=["사용자는 30초 안에 첫 가치를 경험한다"],
    )
    raw = (project_root / ".samvil" / PROGRESS_FILENAME).read_text(encoding="utf-8")
    assert "앱의 핵심 가치는?" in raw
    assert "사용자가 30초 안에" in raw
    # Should not be escaped to \uXXXX (ensure_ascii=False)
    assert "\\u" not in raw


def test_persist_answer_returns_error_on_unwritable_path(tmp_path: Path) -> None:
    # Create a file at the .samvil path so creating the directory fails
    bad_root = tmp_path / "ro_root"
    bad_root.mkdir()
    blocker = bad_root / ".samvil"
    blocker.write_text("not a directory")  # makes mkdir fail with FileExistsError

    result = persist_answer(
        project_root=str(bad_root),
        phase="core",
        question="q",
        answer="a",
    )
    assert result["ok"] is False
    assert "error" in result


# ── mark_phase_complete ─────────────────────────────────────────────


def test_mark_phase_complete(project_root: Path) -> None:
    result = mark_phase_complete(project_root=str(project_root), phase="core")
    assert result["ok"] is True

    entries = _read_lines(project_root)
    assert len(entries) == 1
    assert entries[0]["type"] == "phase_complete"
    assert entries[0]["phase"] == "core"


def test_mark_phase_complete_required_phase(project_root: Path) -> None:
    result = mark_phase_complete(project_root=str(project_root), phase="")
    assert result["ok"] is False


# ── load_progress ────────────────────────────────────────────────────


def test_load_progress_missing_file(project_root: Path) -> None:
    result = load_progress(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is False
    assert result["qa_entries"] == []
    assert result["ac_candidates"] == []
    assert result["completed_phases"] == []
    assert result["ac_by_phase"] == {}


def test_load_progress_full_replay(project_root: Path) -> None:
    persist_answer(
        project_root=str(project_root),
        phase="core",
        question="Q1",
        answer="A1",
        ac_candidates=["AC1", "AC2"],
    )
    mark_phase_complete(project_root=str(project_root), phase="core")
    persist_answer(
        project_root=str(project_root),
        phase="scope",
        question="Q2",
        answer="A2",
        ac_candidates=["AC3"],
    )

    result = load_progress(project_root=str(project_root))
    assert result["ok"] is True
    assert result["exists"] is True
    assert len(result["qa_entries"]) == 2
    assert len(result["ac_candidates"]) == 3
    assert result["completed_phases"] == ["core"]
    assert result["ac_by_phase"]["core"] == ["AC1", "AC2"]
    assert result["ac_by_phase"]["scope"] == ["AC3"]
    assert len(result["answers_by_phase"]["core"]) == 1
    assert result["answers_by_phase"]["core"][0]["q"] == "Q1"


def test_load_progress_skips_malformed_lines(project_root: Path) -> None:
    # Create file with mix of valid + malformed lines
    samvil_dir = project_root / ".samvil"
    samvil_dir.mkdir()
    path = samvil_dir / PROGRESS_FILENAME
    path.write_text(
        '{"type": "qa", "phase": "core", "q": "ok", "a": "ok"}\n'
        'not json garbage\n'
        '{"type": "ac_candidate", "phase": "core", "ac_text": "valid AC"}\n'
        '\n'  # blank line
        '"just a string"\n'  # valid JSON but not a dict
        '{"type": "qa", "phase": "scope", "q": "ok2", "a": "ok2"}\n',
        encoding="utf-8",
    )

    result = load_progress(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["qa_entries"]) == 2
    assert len(result["ac_candidates"]) == 1


def test_load_progress_dedupes_completed_phases(project_root: Path) -> None:
    mark_phase_complete(project_root=str(project_root), phase="core")
    mark_phase_complete(project_root=str(project_root), phase="core")  # dup
    mark_phase_complete(project_root=str(project_root), phase="scope")

    result = load_progress(project_root=str(project_root))
    assert result["completed_phases"] == ["core", "scope"]


# ── clear_progress ──────────────────────────────────────────────────


def test_clear_progress_existing_file(project_root: Path) -> None:
    persist_answer(project_root=str(project_root), phase="core", question="q", answer="a")
    path = project_root / ".samvil" / PROGRESS_FILENAME
    assert path.exists()

    result = clear_progress(project_root=str(project_root))
    assert result["ok"] is True
    assert not path.exists()


def test_clear_progress_missing_file(project_root: Path) -> None:
    result = clear_progress(project_root=str(project_root))
    assert result["ok"] is True


# ── concurrent append (lock smoke) ──────────────────────────────────


def test_concurrent_appends_no_loss(project_root: Path) -> None:
    """Single-threaded SAMVIL doesn't really stress this, but sanity-check
    that 50 sequential appends produce 50 entries."""
    for i in range(50):
        persist_answer(
            project_root=str(project_root),
            phase="core",
            question=f"Q{i}",
            answer=f"A{i}",
        )

    entries = _read_lines(project_root)
    assert len(entries) == 50
    qs = sorted(e["q"] for e in entries)
    assert qs == sorted(f"Q{i}" for i in range(50))


# ── refine payload (v4.21 — Refine Gate) ────────────────────────────


def test_persist_answer_with_refine_payload(project_root: Path) -> None:
    result = persist_answer(
        project_root=str(project_root),
        phase="scope",
        question="어떤 데이터 처리 방식?",
        answer="Excel 받아서 정리하고 Slack으로. 100MB 이상 거부.",
        source="from-user-refined",
        refine_payload={
            "decision": "Excel 업로드 → 정리 → Slack 결과 발송",
            "constraints": ["100MB 이상 파일 거부", "새벽 2-6시 처리 중단"],
            "out_of_scope": ["모바일 지원"],
            "tech_preferences": ["차트: d3.js"],
        },
    )
    assert result["ok"] is True
    assert result["counts"] == {"qa": 1, "ac_candidate": 0, "refined_answer": 1}

    entries = _read_lines(project_root)
    assert len(entries) == 2
    assert entries[0]["type"] == "qa"
    assert entries[1]["type"] == "refined_answer"
    assert entries[1]["payload"]["decision"] == "Excel 업로드 → 정리 → Slack 결과 발송"
    assert "100MB 이상 파일 거부" in entries[1]["payload"]["constraints"]


def test_refine_payload_validation_drops_extras(project_root: Path) -> None:
    """Extra keys outside the schema are dropped; non-string list items become strings."""
    result = persist_answer(
        project_root=str(project_root),
        phase="core",
        question="q",
        answer="a",
        refine_payload={
            "decision": "valid",
            "constraints": ["one", "two", "", "  "],  # blanks dropped
            "out_of_scope": [42, "three"],  # 42 → "42"
            "unknown_field": "ignored",
        },
    )
    assert result["ok"] is True
    entries = _read_lines(project_root)
    refined = [e for e in entries if e["type"] == "refined_answer"][0]
    assert refined["payload"]["constraints"] == ["one", "two"]
    assert refined["payload"]["out_of_scope"] == ["42", "three"]
    assert "unknown_field" not in refined["payload"]


def test_refine_empty_payload_skipped(project_root: Path) -> None:
    """Empty refine_payload (after validation) → no refined_answer entry written."""
    result = persist_answer(
        project_root=str(project_root),
        phase="core",
        question="q",
        answer="a",
        refine_payload={"unknown": "value", "constraints": []},
    )
    assert result["ok"] is True
    assert result["counts"]["refined_answer"] == 0
    entries = _read_lines(project_root)
    assert all(e["type"] != "refined_answer" for e in entries)


def test_load_progress_aggregates_refine_payloads(project_root: Path) -> None:
    """Cross-phase aggregation — constraints / out_of_scope / tech_preferences merged."""
    persist_answer(
        project_root=str(project_root),
        phase="core",
        question="Q1",
        answer="A1",
        refine_payload={
            "decision": "D1",
            "constraints": ["100MB 제한", "한국어 전용"],
            "tech_preferences": ["Next.js"],
        },
    )
    persist_answer(
        project_root=str(project_root),
        phase="scope",
        question="Q2",
        answer="A2",
        refine_payload={
            "decision": "D2",
            "constraints": ["100MB 제한", "TLS 필수"],  # dup intentional
            "out_of_scope": ["모바일"],
        },
    )

    result = load_progress(project_root=str(project_root))
    assert result["ok"] is True
    assert len(result["refined_answers"]) == 2
    # Cross-phase dedup
    assert sorted(result["constraints_aggregated"]) == ["100MB 제한", "TLS 필수", "한국어 전용"]
    assert result["out_of_scope_aggregated"] == ["모바일"]
    assert result["tech_preferences_aggregated"] == ["Next.js"]
    # Per-phase grouping
    assert "core" in result["refined_by_phase"]
    assert "scope" in result["refined_by_phase"]


def test_refine_payload_korean_utf8_preserved(project_root: Path) -> None:
    persist_answer(
        project_root=str(project_root),
        phase="core",
        question="앱 핵심 가치?",
        answer="자유 텍스트 답변",
        refine_payload={
            "decision": "사용자가 30초 안에 가치를 느낀다",
            "reasoning": "첫인상이 재방문을 결정함",
            "constraints": ["오프라인에서도 동작"],
        },
    )
    raw = (project_root / ".samvil" / PROGRESS_FILENAME).read_text(encoding="utf-8")
    assert "30초 안에 가치" in raw
    assert "오프라인에서도 동작" in raw
    assert "\\u" not in raw  # ensure_ascii=False preserved


def test_concurrent_appends_threaded(project_root: Path) -> None:
    """Multi-threaded sanity check via file lock. Some platforms (Windows)
    fall back to no-op locking; we still expect no JSON corruption (each
    write is a single os.write call <= PIPE_BUF in practice)."""
    import threading

    def worker(idx: int) -> None:
        for j in range(10):
            persist_answer(
                project_root=str(project_root),
                phase="core",
                question=f"T{idx}-Q{j}",
                answer=f"T{idx}-A{j}",
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = _read_lines(project_root)
    assert len(entries) == 50  # 5 threads * 10 each
    # Every line was a parseable JSON dict — proven by _read_lines not raising
