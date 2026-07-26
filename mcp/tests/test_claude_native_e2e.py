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
