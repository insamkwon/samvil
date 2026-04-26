"""Tests for central QA synthesis."""

from __future__ import annotations

import json

from samvil_mcp.qa_synthesis import (
    materialize_qa_synthesis,
    qa_summary,
    read_qa_results,
    render_qa_synthesis,
    synthesize_qa_evidence,
)


def _base(pass2_items: list[dict], pass3: dict | None = None) -> dict:
    return {
        "iteration": 1,
        "max_iterations": 3,
        "pass1": {"status": "PASS"},
        "pass2": {"items": pass2_items},
        "pass3": pass3 or {"verdict": "PASS"},
    }


def test_synthesis_passes_with_partial_functional_evidence():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
        {"id": "AC-2", "criterion": "Drag feel", "verdict": "PARTIAL", "reason": "runtime feel"},
    ]))

    assert result["verdict"] == "PASS"
    assert result["pass2"]["counts"]["PARTIAL"] == 1
    assert any(event["event_type"] == "qa_partial" for event in result["events"])


def test_synthesis_revises_on_unimplemented_non_core_ac():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "AI summary", "verdict": "UNIMPLEMENTED", "reason": "stub"},
    ]))

    assert result["verdict"] == "REVISE"
    assert result["next_action"] == "replace stubs or hardcoded paths with real implementation"
    assert any(event["event_type"] == "qa_unimplemented" for event in result["events"])


def test_synthesis_fails_on_core_unimplemented():
    result = synthesize_qa_evidence(_base([
        {
            "id": "AC-core",
            "criterion": "Primary flow",
            "verdict": "UNIMPLEMENTED",
            "is_core_experience": True,
        },
    ]))

    assert result["verdict"] == "FAIL"
    assert result["reason"] == "core experience is unimplemented"


def test_synthesis_revises_for_quality_only_issue():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ], pass3={"verdict": "REVISE", "issues": ["missing focus state"]}))

    assert result["verdict"] == "REVISE"
    assert result["reason"] == "quality QA requires revision"


def test_synthesis_blocks_independent_protected_writes():
    data = _base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ])
    data["agent_writes"] = [{"agent": "qa-functional", "path": ".samvil/qa-report.md"}]

    result = synthesize_qa_evidence(data)

    assert result["verdict"] == "REVISE"
    assert result["reason"] == "independent QA attempted protected writes"
    assert result["ownership_violations"] == [{"agent": "qa-functional", "path": ".samvil/qa-report.md"}]


def test_render_qa_synthesis_includes_verdict_and_counts():
    result = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "PASS", "evidence": ["app/page.tsx:10"]},
    ]))

    rendered = render_qa_synthesis(result)

    assert "# QA Synthesis" in rendered
    assert "- Verdict: PASS" in rendered
    assert "PASS=1" in rendered


def test_materialize_qa_synthesis_writes_report_results_events_and_state(tmp_path):
    (tmp_path / "project.state.json").write_text(
        json.dumps({"session_id": "s1", "current_stage": "qa", "qa_history": []}),
        encoding="utf-8",
    )
    synthesis = synthesize_qa_evidence(_base([
        {"id": "AC-1", "criterion": "Create task", "verdict": "UNIMPLEMENTED", "reason": "stub"},
    ]))

    result = materialize_qa_synthesis(tmp_path, synthesis)

    assert result["status"] == "ok"
    assert result["verdict"] == "REVISE"
    assert result["events_appended"] == 2
    persisted = read_qa_results(tmp_path)
    assert persisted["synthesis"]["verdict"] == "REVISE"
    assert (tmp_path / ".samvil" / "qa-report.md").read_text(encoding="utf-8").startswith("# QA Synthesis")
    events = [
        json.loads(line)
        for line in (tmp_path / ".samvil" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event_type"] for event in events] == ["qa_unimplemented", "qa_verdict"]
    assert events[0]["session_id"] == "s1"
    state = json.loads((tmp_path / "project.state.json").read_text(encoding="utf-8"))
    assert state["last_qa_verdict"] == "REVISE"
    assert state["qa_history"][0]["pass2_counts"]["UNIMPLEMENTED"] == 1
    summary = qa_summary(tmp_path)
    assert summary["present"] is True
    assert summary["verdict"] == "REVISE"
    assert summary["pass2_counts"]["UNIMPLEMENTED"] == 1
