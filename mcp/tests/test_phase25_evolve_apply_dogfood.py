"""Test Phase 25 evolve apply dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase25_evolve_apply_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase25-evolve-apply-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase25 evolve apply dogfood passed" in result.stdout
    assert "status=applied" in result.stdout
