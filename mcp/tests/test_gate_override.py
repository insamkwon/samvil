"""User-approved gate override contract and hook integration."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from samvil_mcp.claim_ledger import ClaimLedger
from samvil_mcp.gates import active_gate_override, gate_override


def _post_block(ledger: ClaimLedger, gate: str) -> None:
    ledger.post(
        type="gate_verdict",
        subject=gate,
        statement="verdict=block",
        authority_file="project.state.json",
        claimed_by="agent:orchestrator-agent",
        evidence=["project.state.json"],
        meta={"verdict": "block"},
    )


def test_gate_override_records_verified_user_claim(tmp_path: Path) -> None:
    ledger = ClaimLedger(tmp_path / ".samvil" / "claims.jsonl")
    _post_block(ledger, "qa_to_deploy")

    result = gate_override(
        tmp_path,
        gate="qa_to_deploy",
        reason="accept static-only deployment risk",
    )

    claim = active_gate_override(ledger, "qa_to_deploy")
    assert claim is not None
    assert result["claim_id"] == claim.claim_id
    assert claim.type == "gate_override"
    assert claim.status == "verified"
    assert claim.verified_by == "agent:user"
    assert claim.meta["overridden_by"] == "user"
    assert claim.meta["reason"] == "accept static-only deployment risk"


def test_gate_override_rejects_non_user_approval(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit user approval"):
        gate_override(
            tmp_path,
            gate="qa_to_deploy",
            reason="agent chose to proceed",
            approved_by="agent:qa-functional",
        )


def test_gate_override_is_consumed_by_newer_gate_verdict(tmp_path: Path) -> None:
    ledger = ClaimLedger(tmp_path / ".samvil" / "claims.jsonl")
    _post_block(ledger, "qa_to_deploy")
    gate_override(tmp_path, gate="qa_to_deploy", reason="one-time approval")
    assert active_gate_override(ledger, "qa_to_deploy") is not None

    _post_block(ledger, "qa_to_deploy")

    assert active_gate_override(ledger, "qa_to_deploy") is None


def test_gate_override_mcp_tool_records_claim(tmp_path: Path) -> None:
    from samvil_mcp.server import gate_override as gate_override_tool

    ledger = ClaimLedger(tmp_path / ".samvil" / "claims.jsonl")
    _post_block(ledger, "build_to_qa")

    result = json.loads(
        asyncio.run(
            gate_override_tool(
                project_root=str(tmp_path),
                gate="build_to_qa",
                reason="user accepts build evidence risk",
                approved_by="user",
            )
        )
    )

    assert result["status"] == "verified"
    assert active_gate_override(ledger, "build_to_qa") is not None


def test_stage_end_hook_applies_override_once(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    (project / "project.state.json").write_text(
        json.dumps({"samvil_tier": "standard", "qa_verdict": "unknown"})
    )
    (project / "project.seed.json").write_text(json.dumps({"schema_version": "3.2"}))

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "TOOL_NAME": "Skill",
            "CLAUDE_PLUGIN_ROOT": str(repo),
        }
    )
    command = [
        "bash",
        str(repo / "hooks" / "contract-stage-end.sh"),
        json.dumps({"skill": "samvil-qa"}),
        "0",
    ]

    subprocess.run(command, cwd=project, env=env, check=True)
    gate_override(project, gate="qa_to_deploy", reason="user accepts runtime risk")
    subprocess.run(command, cwd=project, env=env, check=True)

    health_path = home / ".samvil" / "mcp-health.jsonl"
    stage_end = [
        json.loads(line)
        for line in health_path.read_text().splitlines()
        if '"tool": "hook:stage-end"' in line
    ]
    assert "verdict=pass" in stage_end[-1]["error"]
    assert "override=claim_" in stage_end[-1]["error"]

    subprocess.run(command, cwd=project, env=env, check=True)
    stage_end = [
        json.loads(line)
        for line in health_path.read_text().splitlines()
        if '"tool": "hook:stage-end"' in line
    ]
    assert "verdict=block" in stage_end[-1]["error"]
    assert "override=none" in stage_end[-1]["error"]
