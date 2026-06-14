"""Tests for negative/edge AC checklist (A1)."""

from __future__ import annotations

import asyncio
import json

from samvil_mcp.negative_ac import negative_ac_checklist
from samvil_mcp.server import negative_ac_checklist as negative_ac_checklist_tool


def _cats(result) -> set[str]:
    return {e["category"] for e in result.required_edges}


def test_create_feature_requires_input_edges() -> None:
    r = negative_ac_checklist(
        "todo",
        ["사용자가 할일을 추가할 수 있다", "할일 목록이 표시된다"],
    )
    cats = _cats(r)
    assert "empty_input" in cats
    assert "too_long" in cats
    assert "empty_state" in cats  # from "목록이 표시된다"
    assert "create" in r.detected_patterns
    assert "list" in r.detected_patterns


def test_persist_feature_requires_reload() -> None:
    r = negative_ac_checklist("storage", ["값이 localStorage에 저장된다"])
    assert "survives_reload" in _cats(r)


def test_numeric_feature_requires_boundaries() -> None:
    r = negative_ac_checklist("counter", ["증가 버튼이 카운트를 1 올린다"])
    cats = _cats(r)
    assert "boundary_min" in cats
    assert "boundary_max" in cats


def test_delete_feature_requires_confirm() -> None:
    r = negative_ac_checklist("items", ["사용자가 항목을 삭제할 수 있다"])
    assert "confirm_or_undo" in _cats(r)


def test_english_acs_detected() -> None:
    r = negative_ac_checklist("f", ["user can add a task", "tasks are saved"])
    cats = _cats(r)
    assert "empty_input" in cats
    assert "survives_reload" in cats


def test_no_pattern_falls_back_to_empty_state() -> None:
    r = negative_ac_checklist("mystery", ["something abstract happens"])
    assert _cats(r) == {"empty_state"}


def test_edges_deduplicated() -> None:
    r = negative_ac_checklist(
        "f",
        ["할일을 추가한다", "메모를 추가한다", "댓글을 추가한다"],
    )
    cats = [e["category"] for e in r.required_edges]
    assert len(cats) == len(set(cats))  # no dupes despite 3 create ACs


def test_templates_present_for_filling() -> None:
    r = negative_ac_checklist("counter", ["카운트를 증가시킨다"])
    for edge in r.required_edges:
        assert edge["ac_template"]
        assert edge["rationale"]


def test_handles_dict_acs() -> None:
    r = negative_ac_checklist(
        "todo", [{"description": "할일을 추가할 수 있다"}, {"criterion": "목록 표시"}]
    )
    assert "empty_input" in _cats(r)


def test_mcp_tool_roundtrip() -> None:
    result = json.loads(
        asyncio.run(
            negative_ac_checklist_tool(
                "todo", json.dumps(["사용자가 할일을 추가할 수 있다"])
            )
        )
    )
    assert "required_edges" in result
    assert any(e["category"] == "empty_input" for e in result["required_edges"])
    assert "coverage_note" in result


def test_mcp_tool_bad_input() -> None:
    result = json.loads(
        asyncio.run(negative_ac_checklist_tool("f", json.dumps({"not": "a list"})))
    )
    assert "error" in result
