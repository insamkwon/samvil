from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_dogfood_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "phase28-post-rebuild-qa-dogfood.py"
    spec = importlib.util.spec_from_file_location("phase28_post_rebuild_qa_dogfood", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase28_post_rebuild_qa_scenario(tmp_path: Path) -> None:
    module = _load_dogfood_module()

    result = module._scenario(tmp_path)
    marker = json.loads((tmp_path / ".samvil" / "next-skill.json").read_text(encoding="utf-8"))

    assert result["status"] == "ready"
    assert result["next_skill"] == "samvil-qa"
    assert result["previous_issues"] == 1
    assert marker["next_skill"] == "samvil-qa"
