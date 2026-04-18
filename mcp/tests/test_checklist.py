"""Tests for checklist.py (v2.5.0, Phase 3)."""

import pytest

from samvil_mcp.checklist import (
    ACCheckItem,
    ACChecklist,
    aggregate,
    checklist_from_dict,
    validate_evidence_mandatory,
    enforce_evidence_mandatory,
)


def test_checklist_all_pass():
    items = (
        ACCheckItem("a", True, ("src/a.ts:1",), ""),
        ACCheckItem("b", True, ("src/b.ts:2",), ""),
    )
    cl = ACChecklist("AC-1", "test", items)
    assert cl.verdict == "PASS"
    assert cl.passed_count == 2
    assert cl.total_count == 2


def test_checklist_partial():
    items = (
        ACCheckItem("a", True, ("x:1",)),
        ACCheckItem("b", False, ()),
    )
    cl = ACChecklist("AC-1", "test", items)
    assert cl.verdict == "PARTIAL"


def test_checklist_all_fail():
    items = (ACCheckItem("a", False), ACCheckItem("b", False))
    cl = ACChecklist("AC-1", "test", items)
    assert cl.verdict == "FAIL"


def test_empty_checklist_is_fail():
    cl = ACChecklist("AC-1", "empty", ())
    assert cl.verdict == "FAIL"


def test_aggregate():
    cls = [
        ACChecklist("AC-1", "a", (ACCheckItem("i", True, ("f:1",)),)),  # PASS
        ACChecklist("AC-2", "b", (
            ACCheckItem("i1", True, ("f:2",)),
            ACCheckItem("i2", False),
        )),  # PARTIAL
        ACChecklist("AC-3", "c", (ACCheckItem("i", False),)),  # FAIL
    ]
    feedback = aggregate(cls)
    assert feedback.ac_full_pass == 1
    assert feedback.ac_partial == 1
    assert feedback.ac_fail == 1
    assert feedback.overall_verdict == "FAIL"


def test_aggregate_all_pass_verdict():
    cls = [
        ACChecklist("AC-1", "a", (ACCheckItem("i", True, ("f:1",)),)),
        ACChecklist("AC-2", "b", (ACCheckItem("i", True, ("f:2",)),)),
    ]
    assert aggregate(cls).overall_verdict == "PASS"


def test_aggregate_missing_evidence_count():
    cls = [
        ACChecklist("AC-1", "a", (ACCheckItem("i", True, ()),)),  # PASS but no evidence
    ]
    fb = aggregate(cls)
    assert fb.missing_evidence_count == 1


def test_validate_evidence_mandatory_catches_missing():
    cl = ACChecklist("AC-1", "x", (
        ACCheckItem("good", True, ("src/a.ts:1",)),
        ACCheckItem("bad", True, ()),  # PASS but no evidence
    ))
    violations = validate_evidence_mandatory(cl)
    assert len(violations) == 1
    assert "bad" in violations[0]


def test_enforce_evidence_mandatory_downgrades():
    cl = ACChecklist("AC-1", "x", (
        ACCheckItem("ok", True, ("src:1",)),
        ACCheckItem("nope", True, ()),  # Should be downgraded
    ))
    enforced = enforce_evidence_mandatory(cl)
    assert enforced.items[0].passed is True
    assert enforced.items[1].passed is False  # Downgraded
    assert "P1" in enforced.items[1].rationale


def test_checklist_from_dict_roundtrip():
    data = {
        "ac_id": "AC-1",
        "ac_description": "desc",
        "items": [
            {"description": "i1", "passed": True, "evidence": ["x:1"], "rationale": "r"},
            {"description": "i2", "passed": False, "evidence": [], "rationale": ""},
        ],
    }
    cl = checklist_from_dict(data)
    assert cl.ac_id == "AC-1"
    assert cl.verdict == "PARTIAL"
    assert cl.items[0].evidence == ("x:1",)


def test_ac_check_item_with_verification_questions():
    item = ACCheckItem(
        description="x",
        passed=True,
        evidence=("src/a.ts:1",),
        verification_questions=("Q1?", "Q2?"),
    )
    assert len(item.verification_questions) == 2
    d = item.to_dict()
    assert d["verification_questions"] == ["Q1?", "Q2?"]


def test_ac_check_item_without_verification_questions():
    item = ACCheckItem(description="x", passed=True)
    assert item.verification_questions == ()
    d = item.to_dict()
    assert d["verification_questions"] == []


def test_checklist_from_dict_with_verification_questions():
    data = {
        "ac_id": "AC-1",
        "ac_description": "desc",
        "items": [
            {
                "description": "i1",
                "passed": True,
                "evidence": ["x:1"],
                "rationale": "",
                "verification_questions": ["실제 API 호출인가?"],
            },
        ],
    }
    cl = checklist_from_dict(data)
    assert cl.items[0].verification_questions == ("실제 API 호출인가?",)


def test_checklist_from_dict_missing_verification_questions():
    data = {
        "ac_id": "AC-1",
        "ac_description": "desc",
        "items": [
            {"description": "i1", "passed": True, "evidence": ["x:1"]},
        ],
    }
    cl = checklist_from_dict(data)
    assert cl.items[0].verification_questions == ()
