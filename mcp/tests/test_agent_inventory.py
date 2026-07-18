"""Agent persona count and registry drift checks."""

from __future__ import annotations

import subprocess
import sys
import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load_inventory_module():
    script = REPO / "scripts" / "check-agent-inventory.py"
    spec = importlib.util.spec_from_file_location("check_agent_inventory", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_inventory_ci_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check-agent-inventory.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_count_document_is_reported_without_traceback(tmp_path: Path, capsys) -> None:
    module = _load_inventory_module()
    missing = tmp_path / "missing.md"
    module.COUNT_DOCS = (missing,)

    assert module.main() == 1
    captured = capsys.readouterr()
    assert f"missing count document: {missing}" in captured.out
