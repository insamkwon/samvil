#!/usr/bin/env python3
"""Run the second Trustworthy Core DoD dogfood on standard automation."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.dogfood_interactions import run_standard_interaction_workflow  # noqa: E402
from samvil_mcp.qa_finalize import finalize_qa_verdict  # noqa: E402
from samvil_mcp.qa_synthesis import materialize_qa_synthesis  # noqa: E402
from samvil_mcp.retro_aggregate import aggregate_retro_metrics  # noqa: E402
from samvil_mcp.server import gate_check  # noqa: E402


def _clear_automation_state() -> dict:
    return {
        "target_user": "Team of 5 operations managers working with daily partner CSV exports",
        "core_problem": "Manual cleanup and Slack reporting takes 40 minutes daily",
        "core_experience": "First-time operator runs one command, receives a Slack notification, and returns next day for the next file",
        "features": ["csv-validation", "normalization", "slack-summary"],
        "exclusions": ["web dashboard", "real-time streaming", "database"],
        "constraints": [
            "Python CLI calls the Slack REST API only outside --dry-run",
            "No external writes during dry-run",
            "Malformed rows produce actionable errors",
            "Secure TLS credentials come from environment variables",
            "CSV validation completes under 30 seconds for 1000 rows",
            "CSV cleanup works offline before the Slack send step",
        ],
        "acceptance_criteria": [
            "1000 valid rows produce the expected normalized fixture under 30 seconds",
            "1 malformed row exits non-zero before any Slack message",
            "Dry-run performs 0 network requests",
            "A successful real run records 2 counts: processed and rejected",
            "Missing credentials fail before row 1 is processed",
        ],
    }


def _qa_evidence() -> dict:
    return {
        "pass1": {"status": "PASS"},
        "pass2": {"items": [{"id": "AC-1", "verdict": "PASS"}]},
        "pass3": {"verdict": "PASS"},
    }


def run_dogfood() -> dict:
    with tempfile.TemporaryDirectory(prefix="samvil-wave4-automation-") as tmp:
        root = Path(tmp)
        samvil = root / ".samvil"
        samvil.mkdir()

        workflow = run_standard_interaction_workflow(
            str(root),
            prompt="매일 파트너 CSV를 정리해서 슬랙으로 보내는 자동화",
            interview_state=_clear_automation_state(),
        )
        orchestrator = workflow["orchestrator"]
        interview = workflow["interview"]

        (root / "project.seed.json").write_text(
            json.dumps(
                {
                    "schema_version": "3.0",
                    "name": "partner-csv-slack",
                    "solution_type": "automation",
                    "features": [],
                }
            ),
            encoding="utf-8",
        )
        (root / "project.state.json").write_text(
            json.dumps(
                {
                    "selected_tier": "standard",
                    "config": {"selected_tier": "standard"},
                    "qa_history": [],
                }
            ),
            encoding="utf-8",
        )
        events = [
            {
                "event_type": "interview_start",
                "stage": "interview",
                "timestamp": "2026-07-18T10:00:00Z",
                "data": {},
            },
            {
                "event_type": "interview_complete",
                "stage": "interview",
                "timestamp": "2026-07-18T10:00:01Z",
                "data": {"questions": 10},
            },
        ]
        (samvil / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        retro = aggregate_retro_metrics(str(root))

        (samvil / "qa.log").write_text("SAMVIL_EXIT:0\n", encoding="utf-8")
        (samvil / "test-results.json").write_text(
            json.dumps({"stats": {"expected": 3, "unexpected": 0, "skipped": 0}}),
            encoding="utf-8",
        )
        finalized = finalize_qa_verdict(root, evidence=_qa_evidence())
        materialize_qa_synthesis(root, finalized["synthesis"])
        raw_test_passed = json.loads(
            (samvil / "test-results.json").read_text(encoding="utf-8")
        )["stats"]["expected"]
        qa_reported_passed = finalized["synthesis"]["runtime_evidence"]["passed"]

        (samvil / "qa.log").write_text("SAMVIL_EXIT:1\n", encoding="utf-8")
        (samvil / "test-results.json").write_text(
            json.dumps({"stats": {"expected": 2, "unexpected": 1, "skipped": 0}}),
            encoding="utf-8",
        )
        injected = json.loads(
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
                    project_root=str(root),
                    evidence_mode="mechanical",
                )
            )
        )

        guard = subprocess.run(
            [
                "bash",
                str(REPO / "hooks" / "guard-destructive.sh"),
                json.dumps({"tool_input": {"command": "rm -fr $TARGET"}}),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        return {
            "scenario": "standard-automation",
            "solution_type": orchestrator["solution_type"]["solution_type"],
            "solution_confidence": orchestrator["solution_type"]["confidence"],
            "events_file_exists": (samvil / "events.jsonl").exists(),
            "stage_durations_ms": retro["metrics"]["stage_durations_ms"],
            "raw_test_passed": raw_test_passed,
            "qa_reported_passed": qa_reported_passed,
            "injected_failure_gate_verdict": injected["verdict"],
            "destructive_guard_blocked": guard.returncode == 1,
            "ask_user_question_calls": workflow["ask_user_question_calls"],
            "touchpoints": workflow["touchpoints"],
            "interview_ambiguity": interview["ambiguity"],
            "interview_converged": interview["converged"],
        }


if __name__ == "__main__":
    result = run_dogfood()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    expected = (
        result["solution_type"] == "automation"
        and result["solution_confidence"] == "high"
        and result["events_file_exists"] is True
        and result["stage_durations_ms"].get("interview") == 1000
        and result["qa_reported_passed"] == result["raw_test_passed"] == 3
        and result["injected_failure_gate_verdict"] == "block"
        and result["destructive_guard_blocked"] is True
        and result["ask_user_question_calls"] <= 12
        and result["interview_converged"] is True
    )
    if not expected:
        raise SystemExit(1)
