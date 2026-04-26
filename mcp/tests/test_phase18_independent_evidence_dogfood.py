"""Regression test for Phase 18 independent evidence contract dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase18_independent_evidence_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase18-independent-evidence-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase18 independent evidence dogfood passed" in result.stdout
    assert "design_feasibility: pass" in result.stdout
    assert "independent_qa: pass" in result.stdout
