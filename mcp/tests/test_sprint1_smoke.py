"""End-to-end smoke tests for Sprint 1 — ① Claim + ⑥ Gate together.

These tests exercise the contract-layer handoff: a build pipeline posts a
gate_verdict claim via the ledger and view-layer scripts can rebuild the
current state from that claim. Everything runs in-process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from samvil_mcp.claim_ledger import ClaimLedger
from samvil_mcp.gates import GateName, Verdict, gate_check


REPO = Path(__file__).resolve().parents[2]


def test_gate_verdict_posted_as_claim_round_trips(tmp_path: Path) -> None:
    """A failing gate should be recorded as a pending gate_verdict claim,
    later verified by a different agent, and the view layer should render
    it as the latest verdict."""
    # 1. Run a gate check — expect block (0.70 below 0.85 standard floor).
    v = gate_check(
        GateName.BUILD_TO_QA.value,
        samvil_tier="standard",
        metrics={"implementation_rate": 0.70},
        subject="project:focus-timer",
    )
    assert v.verdict == Verdict.BLOCK.value

    # 2. Post the verdict to a project ledger.
    ledger = ClaimLedger(tmp_path / ".samvil" / "claims.jsonl")
    evidence_src = tmp_path / "src"
    evidence_src.mkdir()
    (evidence_src / "build.log").write_text("npm run build\nSUCCESS\n")

    claim = ledger.post(
        type="gate_verdict",
        subject=v.gate,  # gate name
        statement=(
            f"{v.gate} blocked on standard tier; "
            f"failed={','.join(v.failed_checks)}"
        ),
        authority_file="state.json",
        claimed_by="agent:build-worker",
        evidence=["src/build.log:1"],
        meta=asdict(v),  # preserve the full verdict for view layer
    )
    assert claim.status == "pending"

    # 3. Judge role verifies.
    verified = ledger.verify(
        claim.claim_id,
        verified_by="agent:product-owner",
        project_root=tmp_path,
    )
    assert verified.status == "verified"

    # 4. Materialized view pulls back the verdict.
    rows = ledger.materialize_view("state.json")
    assert len(rows) == 1
    assert rows[0].subject == GateName.BUILD_TO_QA.value
    meta = rows[0].meta
    assert meta["verdict"] == Verdict.BLOCK.value
    assert "implementation_rate" in meta["failed_checks"]


def test_view_claims_script_runs_clean(tmp_path: Path) -> None:
    """The view-claims CLI reads a jsonl at --path and emits non-zero-length
    output. We point it at a throwaway ledger so it doesn't read the repo's
    real one."""
    ledger_path = tmp_path / "claims.jsonl"
    ledger = ClaimLedger(ledger_path)
    ledger.post(
        type="seed_field_set",
        subject="features[0].name",
        statement="Focus Timer",
        authority_file="seed.json",
        claimed_by="agent:seed-architect",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "view-claims.py"),
            "--path",
            str(ledger_path),
            "--format",
            "count",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # Expect: "total=1 pending=1 verified=0 rejected=0"
    assert "total=1" in result.stdout
    assert "pending=1" in result.stdout


def test_exit_gate_skeleton_round_trip() -> None:
    """The exit-gate check's skeleton round-trip function should pass.
    (This re-exercises the already-green path A in CI.)"""
    # Import directly to avoid subprocess cost.
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_exit_gate",
            str(REPO / "scripts" / "check-exit-gate-sprint1.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        assert mod.check_a_skeleton_round_trip() is True
    finally:
        if str(REPO / "scripts") in sys.path:
            sys.path.remove(str(REPO / "scripts"))
