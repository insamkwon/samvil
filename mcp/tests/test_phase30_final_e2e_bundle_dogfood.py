from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_dogfood_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "phase30-final-e2e-bundle-dogfood.py"
    spec = importlib.util.spec_from_file_location("phase30_final_e2e_bundle_dogfood", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase30_final_e2e_bundle_scenario(tmp_path: Path) -> None:
    module = _load_dogfood_module()

    result = module._scenario(tmp_path)
    bundle = json.loads((tmp_path / ".samvil" / "final-e2e-bundle.json").read_text(encoding="utf-8"))

    assert result["status"] == "pass"
    assert result["cycle_verdict"] == "closed"
    assert result["issue_count"] == 0
    assert bundle["chain"]["cycle_next"] == "samvil-retro"
