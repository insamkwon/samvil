"""Unit tests for claim_ledger (Sprint 1, ①)."""

from __future__ import annotations

from pathlib import Path

import pytest

from samvil_mcp.claim_ledger import (
    CLAIM_TYPES,
    Claim,
    ClaimLedger,
    ClaimLedgerError,
    _unresolved_evidence,
)


@pytest.fixture
def ledger(tmp_path: Path) -> ClaimLedger:
    return ClaimLedger(tmp_path / "claims.jsonl")


@pytest.fixture
def project_with_file(tmp_path: Path) -> Path:
    """A tmp 'project root' containing a small file to resolve file:line
    evidence against."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.ts").write_text("line1\nline2\nline3\n")
    return tmp_path


def test_post_creates_pending_claim(ledger: ClaimLedger) -> None:
    c = ledger.post(
        type="seed_field_set",
        subject="features[0].name",
        statement="feature name set to 'todo list'",
        authority_file="seed.json",
        claimed_by="agent:seed-architect",
    )
    assert c.status == "pending"
    assert c.verified_by is None
    assert c.claim_id.startswith("claim_")


def test_post_rejects_unknown_type(ledger: ClaimLedger) -> None:
    with pytest.raises(ClaimLedgerError, match="whitelist"):
        ledger.post(
            type="random_type",  # not whitelisted
            subject="x",
            statement="y",
            authority_file="x.json",
            claimed_by="agent:x",
        )


def test_post_requires_claimed_by(ledger: ClaimLedger) -> None:
    with pytest.raises(ClaimLedgerError, match="claimed_by"):
        ledger.post(
            type="seed_field_set",
            subject="x",
            statement="y",
            authority_file="seed.json",
            claimed_by="",
        )


def test_verify_happy_path(ledger: ClaimLedger, project_with_file: Path) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="login form renders",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:2"],
    )
    v = ledger.verify(
        c.claim_id,
        verified_by="agent:product-owner",
        project_root=project_with_file,
    )
    assert v.status == "verified"
    assert v.verified_by == "agent:product-owner"
    assert v.evidence == ["src/app.ts:2"]


def test_verify_rejects_same_agent_as_claimer(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:1"],
    )
    with pytest.raises(ClaimLedgerError, match="Generator"):
        ledger.verify(
            c.claim_id,
            verified_by="agent:qa-functional",
            project_root=project_with_file,
        )


def test_verify_rejects_empty_evidence(ledger: ClaimLedger, tmp_path: Path) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
    )
    with pytest.raises(ClaimLedgerError, match="evidence is empty"):
        ledger.verify(
            c.claim_id,
            verified_by="agent:product-owner",
            project_root=tmp_path,
        )


def test_verify_rejects_unresolved_file_line(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/missing.ts:5"],
    )
    with pytest.raises(ClaimLedgerError, match="unresolved"):
        ledger.verify(
            c.claim_id,
            verified_by="agent:product-owner",
            project_root=project_with_file,
        )


def test_verify_rejects_line_out_of_range(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:99"],  # file has 3 lines
    )
    with pytest.raises(ClaimLedgerError, match="unresolved"):
        ledger.verify(
            c.claim_id,
            verified_by="agent:product-owner",
            project_root=project_with_file,
        )


def test_verify_is_idempotent(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:1"],
    )
    v1 = ledger.verify(
        c.claim_id, verified_by="agent:product-owner", project_root=project_with_file
    )
    v2 = ledger.verify(
        c.claim_id, verified_by="agent:product-owner", project_root=project_with_file
    )
    assert v1.claim_id == v2.claim_id
    assert v2.status == "verified"


def test_reject_happy_path(ledger: ClaimLedger) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
    )
    r = ledger.reject(
        c.claim_id, verified_by="agent:product-owner", reason="no evidence"
    )
    assert r.status == "rejected"
    assert r.meta.get("reject_reason") == "no evidence"


def test_reject_after_verify_blocks(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:1"],
    )
    ledger.verify(
        c.claim_id, verified_by="agent:product-owner", project_root=project_with_file
    )
    with pytest.raises(ClaimLedgerError, match="already verified"):
        ledger.reject(c.claim_id, verified_by="agent:product-owner")


def test_query_by_subject(ledger: ClaimLedger) -> None:
    ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="a",
        authority_file="qa-results.json",
        claimed_by="agent:x",
    )
    ledger.post(
        type="ac_verdict",
        subject="AC-1.2",
        statement="b",
        authority_file="qa-results.json",
        claimed_by="agent:x",
    )
    results = ledger.query_by_subject("AC-1.1")
    assert len(results) == 1
    assert results[0].subject == "AC-1.1"


def test_stats(ledger: ClaimLedger, project_with_file: Path) -> None:
    c1 = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="a",
        authority_file="qa-results.json",
        claimed_by="agent:x",
        evidence=["src/app.ts:1"],
    )
    ledger.post(
        type="gate_verdict",
        subject="gate:seed_to_council",
        statement="b",
        authority_file="state.json",
        claimed_by="agent:y",
    )
    ledger.verify(
        c1.claim_id,
        verified_by="agent:z",
        project_root=project_with_file,
    )
    s = ledger.stats()
    assert s["total"] == 2
    assert s["by_status"]["verified"] == 1
    assert s["by_status"]["pending"] == 1
    assert s["by_type"]["ac_verdict"] == 1
    assert s["by_type"]["gate_verdict"] == 1


def test_materialize_view_returns_verified_only(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    c1 = ledger.post(
        type="seed_field_set",
        subject="features[0].name",
        statement="Todo",
        authority_file="seed.json",
        claimed_by="agent:seed-architect",
        evidence=["src/app.ts:1"],
    )
    ledger.post(
        type="seed_field_set",
        subject="features[1].name",
        statement="Pending",
        authority_file="seed.json",
        claimed_by="agent:seed-architect",
    )
    ledger.verify(
        c1.claim_id, verified_by="agent:user", project_root=project_with_file
    )
    view = ledger.materialize_view("seed.json")
    assert len(view) == 1
    assert view[0].subject == "features[0].name"


def test_append_only_reconstruction(
    ledger: ClaimLedger, project_with_file: Path
) -> None:
    """After verify, the JSONL file has two rows for the claim but the
    in-memory state shows the latest."""
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="x",
        authority_file="qa-results.json",
        claimed_by="agent:qa-functional",
        evidence=["src/app.ts:1"],
    )
    ledger.verify(
        c.claim_id, verified_by="agent:user", project_root=project_with_file
    )
    raw = ledger.path.read_text().splitlines()
    assert len(raw) == 2
    latest = ledger.query_by_subject("AC-1.1")[0]
    assert latest.status == "verified"


def test_unresolved_evidence_bare_path(tmp_path: Path) -> None:
    (tmp_path / "exists.txt").write_text("x")
    result = _unresolved_evidence(
        ["exists.txt", "missing.txt"], project_root=tmp_path
    )
    assert result == ["missing.txt"]


def test_claim_types_whitelist_size() -> None:
    # Matches the spec decision (~10 types). Keep this honest so adding a
    # new type requires a conscious bump here.
    assert 8 <= len(CLAIM_TYPES) <= 12


def test_post_increments_sequence_within_same_second(
    ledger: ClaimLedger,
) -> None:
    """Two posts in rapid succession should get distinct claim_ids even when
    the ISO timestamp rounds to the same second."""
    ids = set()
    for _ in range(5):
        c = ledger.post(
            type="evidence_posted",
            subject="x",
            statement="y",
            authority_file="events.jsonl",
            claimed_by="agent:x",
        )
        ids.add(c.claim_id)
    assert len(ids) == 5
