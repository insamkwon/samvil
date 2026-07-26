from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_codex_harness_binds_and_releases_localhost_port():
    harness = _load("codex_native_e2e", "codex-native-e2e.py")
    assert harness.localhost_probe() is True


def test_codex_harness_receipt_is_bound_to_clean_revision():
    harness = _load("codex_native_e2e_receipt", "codex-native-e2e.py")
    result = harness.readiness()
    assert result["tested_commit"]
    assert result["tested_tree"]
    assert result["localhost_bind"] is True
