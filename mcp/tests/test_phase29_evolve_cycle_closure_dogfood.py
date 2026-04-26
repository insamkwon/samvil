from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_dogfood_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "phase29-evolve-cycle-closure-dogfood.py"
    spec = importlib.util.spec_from_file_location("phase29_evolve_cycle_closure_dogfood", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase29_evolve_cycle_closure_scenario(tmp_path: Path) -> None:
    module = _load_dogfood_module()

    result = module._scenario(tmp_path)
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert result["status"] == "ready"
    assert result["verdict"] == "closed"
    assert result["next_skill"] == "samvil-retro"
    assert result["qa_iteration"] == 3
    assert marker["cycle_verdict"] == "closed"
