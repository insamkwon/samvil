"""Unit tests for AC leaf schema (Sprint 3, ③)."""

from __future__ import annotations

import pytest

from samvil_mcp.ac_leaf_schema import (
    ALL_FIELDS,
    AI_DESIGN_FIELDS,
    AI_SEED_FIELDS,
    CostTierHint,
    LeafStatus,
    RUNTIME_FIELDS,
    USER_FIELDS,
    ACLeaf,
    RiskLevel,
    Stage,
    ac_is_testable,
    compute_parallel_safety,
    lock_user_fields,
    validate_leaf,
)


# ── Schema shape ──────────────────────────────────────────────────────


def test_14_fields_total() -> None:
    assert len(ALL_FIELDS) == 14


def test_field_partition_disjoint() -> None:
    groups = (USER_FIELDS, AI_SEED_FIELDS, AI_DESIGN_FIELDS, RUNTIME_FIELDS)
    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            assert not (a & b), f"overlap: {a & b}"


def test_field_partition_covers_all() -> None:
    union = USER_FIELDS | AI_SEED_FIELDS | AI_DESIGN_FIELDS | RUNTIME_FIELDS
    assert union == ALL_FIELDS


def test_leaf_round_trips_to_dict() -> None:
    leaf = ACLeaf(
        id="AC-1.1",
        intent="User can log in",
        verification="Login form returns 200 on valid credentials",
        description="Auth endpoint",
        input="valid email + password",
        action="POST /auth/login",
        expected="200 + JWT",
    )
    d = leaf.to_dict()
    assert ACLeaf.from_dict(d).to_dict() == d


# ── validate_leaf ────────────────────────────────────────────────────


def _minimal_seed_leaf() -> ACLeaf:
    return ACLeaf(
        id="AC-1.1",
        intent="User logs in",
        verification="Login form returns 200 on valid credentials",
        description="Auth",
        input="email + pw",
        action="POST /login",
        expected="200",
        risk_level=RiskLevel.LOW.value,
        model_tier_hint=CostTierHint.BALANCED.value,
    )


def test_valid_at_seed_stage() -> None:
    issues = validate_leaf(_minimal_seed_leaf(), stage=Stage.SEED)
    assert issues == []


def test_interview_stage_allows_missing_seed_fields() -> None:
    leaf = ACLeaf(
        id="AC-1",
        intent="User logs in",
        verification="Login returns 200",
    )
    issues = validate_leaf(leaf, stage=Stage.INTERVIEW)
    assert issues == []


def test_seed_stage_flags_missing_ai_fields() -> None:
    leaf = ACLeaf(
        id="AC-1",
        intent="User logs in",
        verification="Login returns 200",
    )
    issues = validate_leaf(leaf, stage=Stage.SEED)
    assert any(i.field == "description" for i in issues)
    assert any(i.field == "action" for i in issues)


def test_design_stage_flags_missing_likely_files() -> None:
    leaf = _minimal_seed_leaf()
    # Design-stage fields unset.
    issues = validate_leaf(leaf, stage=Stage.DESIGN)
    assert any(i.field == "likely_files" for i in issues)


def test_non_testable_verification_rejected_at_seed() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = "Looks nice and clean"
    issues = validate_leaf(leaf, stage=Stage.SEED)
    assert any(i.code == "not_testable" for i in issues)


def test_empty_verification_rejected_at_seed() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = ""
    issues = validate_leaf(leaf, stage=Stage.SEED)
    # Caught by required-at-stage (empty), not by testability sniff.
    assert any(i.code == "missing" for i in issues)


def test_bad_risk_level_flagged() -> None:
    leaf = _minimal_seed_leaf()
    leaf.risk_level = "CATASTROPHIC"
    issues = validate_leaf(leaf, stage=Stage.SEED)
    assert any(i.code == "bad_enum" and i.field == "risk_level" for i in issues)


def test_bad_status_flagged() -> None:
    leaf = _minimal_seed_leaf()
    leaf.status = "magic"
    issues = validate_leaf(leaf, stage=Stage.BUILD)
    assert any(i.code == "bad_enum" and i.field == "status" for i in issues)


def test_bad_cost_tier_hint_flagged() -> None:
    leaf = _minimal_seed_leaf()
    leaf.model_tier_hint = "standard"  # samvil_tier value, not cost_tier  # glossary-allow: anti-example
    issues = validate_leaf(leaf, stage=Stage.SEED)
    assert any(i.code == "bad_enum" and i.field == "model_tier_hint" for i in issues)  # glossary-allow: schema field test


# ── Testability ──────────────────────────────────────────────────────


def test_testable_returns_true_for_measurable() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = "Login form renders within 2s on 3G"
    ok, reason = ac_is_testable(leaf)
    assert ok


def test_testable_false_for_vague_words() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = "Elegant, production-ready solution"
    ok, reason = ac_is_testable(leaf)
    assert not ok
    assert "vague" in reason


def test_testable_false_without_verb() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = "Authentication feature for users"
    ok, _ = ac_is_testable(leaf)
    assert not ok


def test_testable_handles_short_phrases() -> None:
    leaf = _minimal_seed_leaf()
    leaf.verification = "returns 200"
    ok, _ = ac_is_testable(leaf)
    assert ok


# ── parallel_safety ─────────────────────────────────────────────────


def test_parallel_safety_marks_file_overlap_unsafe() -> None:
    a = ACLeaf(id="A", likely_files=["src/auth.ts"])
    b = ACLeaf(id="B", likely_files=["src/auth.ts", "src/b.ts"])
    c = ACLeaf(id="C", likely_files=["src/unrelated.ts"])
    safety = compute_parallel_safety([a, b, c])
    assert safety["A"] is False
    assert safety["B"] is False
    assert safety["C"] is True


def test_parallel_safety_marks_shared_resource_overlap_unsafe() -> None:
    a = ACLeaf(id="A", shared_resources=["db.users"])
    b = ACLeaf(id="B", shared_resources=["db.users"])
    safety = compute_parallel_safety([a, b])
    assert safety["A"] is False
    assert safety["B"] is False


def test_parallel_safety_all_safe_when_disjoint() -> None:
    a = ACLeaf(id="A", likely_files=["src/a.ts"])
    b = ACLeaf(id="B", likely_files=["src/b.ts"])
    safety = compute_parallel_safety([a, b])
    assert all(v is True for v in safety.values())


def test_parallel_safety_ignores_empty_id() -> None:
    a = ACLeaf(id="", likely_files=["src/a.ts"])
    b = ACLeaf(id="B", likely_files=["src/a.ts"])
    safety = compute_parallel_safety([a, b])
    assert "" not in safety  # skipped
    assert safety == {"B": True}


# ── Field locking ───────────────────────────────────────────────────


def test_lock_user_fields_returns_independent_copy() -> None:
    leaf = _minimal_seed_leaf()
    leaf.depends_on = ["AC-0.1"]
    locked = lock_user_fields(leaf)
    locked.depends_on.append("AC-0.2")
    assert leaf.depends_on == ["AC-0.1"]
    assert locked.depends_on == ["AC-0.1", "AC-0.2"]
