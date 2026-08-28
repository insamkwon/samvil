from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_claude_harness_reports_real_binary_and_manifest():
    spec = importlib.util.spec_from_file_location("claude_native_e2e", ROOT / "scripts" / "claude-native-e2e.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    result = module.readiness()
    assert result["tested_commit"]
    assert result["tested_tree"]
    assert result["plugin_manifest"] is True


def test_claude_harness_fails_closed_when_runtime_scenario_is_not_implemented():
    spec = importlib.util.spec_from_file_location(
        "claude_native_e2e_scenario", ROOT / "scripts" / "claude-native-e2e.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    result = module.evaluate_mode(module.readiness(), check=False, scenario="all", repeat=1)

    assert result["scenario_executed"] is False
    assert result["ready"] is False
    assert "not implemented" in " ".join(result["blockers"])
