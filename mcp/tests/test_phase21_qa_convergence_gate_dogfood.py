"""Test Phase 21 QA convergence gate dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase21_qa_convergence_gate_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase21-qa-convergence-gate-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase21 QA convergence gate dogfood passed" in result.stdout
    assert "convergence=blocked" in result.stdout
