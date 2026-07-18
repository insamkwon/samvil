"""Wave 3 standard web-app touchpoint dogfood."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_dogfood_module():
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "wave3-touchpoint-dogfood.py"
    )
    spec = importlib.util.spec_from_file_location("wave3_touchpoint_dogfood", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_standard_dashboard_dogfood_stays_within_twelve_touchpoints() -> None:
    module = _load_dogfood_module()
    result = module.run_dogfood()

    assert result["scenario"] == "standard-dashboard"
    assert result["solution_type"] == "dashboard"
    assert result["solution_confidence"] == "high"
    assert result["questions_asked"] == 10
    assert result["interview_converged"] is True
    assert result["ask_user_question_calls"] == 12
    assert result["within_goal"] is True
    assert result["council_opt_in"] is False
