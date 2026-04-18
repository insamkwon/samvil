"""Tests for v3.0.0 T2 dependency analyzer."""

import pytest

from samvil_mcp.dependency_analyzer import (
    ACDepNode,
    analyze_structured,
    build_plan,
    compute_execution_levels,
    merge_llm,
)


def test_analyze_structured_assigns_default_ids():
    nodes = analyze_structured([
        {"description": "a"},
        {"description": "b"},
    ])
    assert nodes[0].id == "AC-1"
    assert nodes[1].id == "AC-2"


def test_analyze_structured_reads_depends_on_and_prerequisites():
    nodes = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b", "depends_on": ["A"]},
        {"id": "C", "description": "c", "prerequisites": ["B"]},
    ])
    assert nodes[1].depends_on == ["A"]
    assert nodes[2].depends_on == ["B"]


def test_analyze_structured_rejects_duplicate_id():
    with pytest.raises(ValueError):
        analyze_structured([
            {"id": "X", "description": "a"},
            {"id": "X", "description": "b"},
        ])


def test_analyze_structured_drops_self_reference():
    nodes = analyze_structured([
        {"id": "A", "description": "a", "depends_on": ["A"]},
    ])
    assert nodes[0].depends_on == []


def test_analyze_structured_marks_serial_only():
    nodes = analyze_structured([
        {"id": "A", "description": "a", "serial_only": True},
    ])
    assert nodes[0].requires_serial_stage is True
    assert "explicit serial_only=true" in nodes[0].serialization_reasons


def test_merge_llm_adds_inferred_deps():
    structured = analyze_structured([
        {"id": "A", "description": "sign up"},
        {"id": "B", "description": "log in"},
    ])
    merged = merge_llm(structured, [
        {"ac_id": "B", "depends_on": ["A"], "reason": "login requires signup"},
    ])
    b = next(n for n in merged if n.id == "B")
    assert b.depends_on == ["A"]


def test_merge_llm_ignores_unknown_ids():
    structured = analyze_structured([{"id": "A", "description": "a"}])
    merged = merge_llm(structured, [
        {"ac_id": "A", "depends_on": ["GHOST"]},
    ])
    assert merged[0].depends_on == []


def test_merge_llm_dedups_existing():
    structured = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b", "depends_on": ["A"]},
    ])
    merged = merge_llm(structured, [
        {"ac_id": "B", "depends_on": ["A"]},
    ])
    b = next(n for n in merged if n.id == "B")
    assert b.depends_on == ["A"]  # no duplicate


def test_compute_execution_levels_parallel_then_sequential():
    nodes = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b"},
        {"id": "C", "description": "c", "depends_on": ["A", "B"]},
    ])
    levels = compute_execution_levels(nodes)
    assert levels == [["A", "B"], ["C"]]


def test_compute_execution_levels_serial_only_splits():
    nodes = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b", "serial_only": True},
        {"id": "C", "description": "c"},
    ])
    levels = compute_execution_levels(nodes)
    # A + C parallel (no deps, no serial), B alone afterwards
    assert ["A", "C"] in levels or (["A"] in levels and ["C"] in levels)
    assert ["B"] in levels


def test_compute_execution_levels_detects_cycle():
    nodes = [
        ACDepNode(id="A", description="a", depends_on=["B"]),
        ACDepNode(id="B", description="b", depends_on=["A"]),
    ]
    with pytest.raises(ValueError, match="Cycle"):
        compute_execution_levels(nodes)


def test_build_plan_marks_parallelizable():
    nodes = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b"},
    ])
    levels = compute_execution_levels(nodes)
    plan = build_plan(nodes, levels)
    assert plan["is_parallelizable"] is True
    assert plan["total_acs"] == 2
    assert plan["total_levels"] == 1


def test_build_plan_non_parallelizable():
    nodes = analyze_structured([
        {"id": "A", "description": "a"},
        {"id": "B", "description": "b", "depends_on": ["A"]},
    ])
    levels = compute_execution_levels(nodes)
    plan = build_plan(nodes, levels)
    assert plan["is_parallelizable"] is False
    assert plan["total_levels"] == 2


def test_acdepnode_roundtrip_dict():
    node = ACDepNode(id="A", description="a", depends_on=["B"])
    d = node.to_dict()
    restored = ACDepNode.from_dict(d)
    assert restored.id == "A"
    assert restored.depends_on == ["B"]
