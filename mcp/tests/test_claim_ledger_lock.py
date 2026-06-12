"""Concurrency + integrity tests for claim_ledger file locking (v4.30 W1.1).

Hooks and the main skill can both write `.samvil/claims.jsonl`. Before the
flock fix, two concurrent post() calls could read the same seq and collide
on claim_id. These tests pin the locked behavior.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from samvil_mcp.claim_ledger import Claim, ClaimLedger


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "claims.jsonl"


def _post_one(path: Path, i: int) -> str:
    # Fresh ClaimLedger per call — mimics independent processes (hook vs
    # skill), each opening its own fd on the shared jsonl.
    ledger = ClaimLedger(path)
    claim = ledger.post(
        type="evidence_posted",
        subject=f"subject-{i}",
        statement=f"statement {i}",
        authority_file="state.json",
        claimed_by=f"agent:worker-{i}",
    )
    return claim.claim_id


def test_concurrent_posts_yield_unique_claim_ids(ledger_path: Path) -> None:
    n = 32
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda i: _post_one(ledger_path, i), range(n)))
    assert len(set(ids)) == n, f"claim_id collision: {sorted(ids)}"

    # Every post must have landed as its own intact JSONL row.
    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == n
    assert ClaimLedger(ledger_path).integrity_errors() == []


def test_concurrent_posts_keep_lines_unmangled(ledger_path: Path) -> None:
    n = 16
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: _post_one(ledger_path, i), range(n)))
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        # json.loads raises on interleaved/torn writes
        Claim.from_dict(json.loads(line))


def test_integrity_errors_detect_pre_lock_collision(ledger_path: Path) -> None:
    """Synthetic pre-v4.30 corruption: two different posts, same claim_id."""
    ledger = ClaimLedger(ledger_path)
    real = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="real claim",
        authority_file="qa-results.json",
        claimed_by="agent:a",
    )
    impostor = Claim(
        claim_id=real.claim_id,  # collision
        type="ac_verdict",
        subject="AC-9.9",
        statement="different post, same id",
        authority_file="qa-results.json",
        claimed_by="agent:b",
    )
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(impostor.to_json() + "\n")

    assert ledger.integrity_errors() == [real.claim_id]
    assert ledger.stats()["integrity_errors"] == [real.claim_id]


def test_verify_rows_do_not_trip_integrity_check(
    ledger_path: Path, tmp_path: Path
) -> None:
    """post → verify legitimately repeats claim_id; must NOT be flagged."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.ts").write_text("line1\n")

    ledger = ClaimLedger(ledger_path)
    c = ledger.post(
        type="ac_verdict",
        subject="AC-1.1",
        statement="works",
        authority_file="qa-results.json",
        claimed_by="agent:a",
        evidence=["src/app.ts:1"],
    )
    ledger.verify(c.claim_id, verified_by="agent:b", project_root=tmp_path)
    assert ledger.integrity_errors() == []
