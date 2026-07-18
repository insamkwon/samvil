"""Wave 2 trustworthy evidence gate dogfood."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from samvil_mcp.claim_ledger import ClaimLedger
from samvil_mcp.gates import active_gate_override, gate_override
from samvil_mcp.qa_finalize import finalize_qa_verdict
from samvil_mcp.qa_synthesis import materialize_qa_synthesis
from samvil_mcp.server import gate_check


def _evidence() -> dict:
    return {
        "pass1": {"status": "PASS"},
        "pass2": {"items": [{"id": "AC-1", "verdict": "PASS"}]},
        "pass3": {"verdict": "PASS"},
    }


def test_wave2_mechanical_evidence_and_override_flow(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (tmp_path / "project.state.json").write_text(
        json.dumps({"selected_tier": "standard", "qa_history": []})
    )
    (samvil / "qa.log").write_text("SAMVIL_EXIT:0\n")
    (samvil / "test-results.json").write_text(
        json.dumps({"stats": {"expected": 3, "unexpected": 0, "skipped": 1}})
    )

    finalized = finalize_qa_verdict(tmp_path, evidence=_evidence())
    materialize_qa_synthesis(tmp_path, finalized["synthesis"])
    report = (samvil / "qa-report.md").read_text()
    raw_passed = json.loads((samvil / "test-results.json").read_text())["stats"]["expected"]
    assert finalized["synthesis"]["runtime_evidence"]["passed"] == raw_passed
    assert f"passed={raw_passed}" in report

    (samvil / "qa.log").write_text("SAMVIL_EXIT:1\n")
    (samvil / "test-results.json").write_text(
        json.dumps({"stats": {"expected": 2, "unexpected": 1, "skipped": 1}})
    )
    broken = json.loads(
        asyncio.run(
            gate_check(
                gate_name="qa_to_deploy",
                samvil_tier="standard",
                metrics_json=json.dumps(
                    {
                        "three_pass_pass": True,
                        "zero_stubs": True,
                        "test_pass_rate": 1.0,
                        "runtime_verified": True,
                    }
                ),
                project_root=str(tmp_path),
                evidence_mode="mechanical",
            )
        )
    )
    assert broken["verdict"] == "block"
    assert broken["metrics"]["test_pass_rate"] == pytest.approx(2 / 3, abs=1e-6)

    (samvil / "qa.log").unlink()
    (samvil / "test-results.json").unlink()
    static = json.loads(
        asyncio.run(
            gate_check(
                gate_name="qa_to_deploy",
                samvil_tier="standard",
                metrics_json=json.dumps(
                    {"three_pass_pass": True, "zero_stubs": True}
                ),
                project_root=str(tmp_path),
                evidence_mode="mechanical",
            )
        )
    )
    assert static["verdict"] == "block"
    assert static["metrics"]["verification_mode"] == "static"

    ledger = ClaimLedger(samvil / "claims.jsonl")
    ledger.post(
        type="gate_verdict",
        subject="qa_to_deploy",
        statement="verdict=block",
        authority_file="project.state.json",
        claimed_by="agent:orchestrator-agent",
        meta={"verdict": "block"},
    )
    reason = "dogfood accepts static deployment risk"
    approval_claim_id = ledger.record_host_user_approval(
        gate="qa_to_deploy",
        reason=reason,
        host_event_id="dogfood-user-approval",
    ).claim_id
    override = gate_override(
        tmp_path,
        gate="qa_to_deploy",
        reason=reason,
        approval_claim_id=approval_claim_id,
    )
    active = active_gate_override(ledger, "qa_to_deploy")
    assert active is not None
    assert active.claim_id == override["claim_id"]
