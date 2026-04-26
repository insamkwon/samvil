"""Regression test for Phase 20 QA materialization dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase20_qa_materialization_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase20-qa-materialization-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase20 QA materialization dogfood passed" in result.stdout
    assert "verdict=REVISE" in result.stdout
    assert "replace stubs or hardcoded paths with real implementation" in result.stdout
