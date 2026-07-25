"""Second DoD dogfood: standard automation, evidence, guard, touchpoints."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "wave4-automation-dogfood.py"


def test_standard_automation_dogfood_closes_trustworthy_core_dod() -> None:
    spec = importlib.util.spec_from_file_location("wave4_automation_dogfood", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run_dogfood()

    assert result["solution_type"] == "automation"
    assert result["solution_confidence"] == "high"
    assert result["events_file_exists"] is True
    assert result["stage_durations_ms"]["interview"] == 1000
    assert result["qa_reported_passed"] == result["raw_test_passed"] == 3
    assert result["injected_failure_gate_verdict"] == "block"
    assert result["destructive_guard_blocked"] is True
    assert result["ask_user_question_calls"] <= 12
    assert result["interview_converged"] is True
