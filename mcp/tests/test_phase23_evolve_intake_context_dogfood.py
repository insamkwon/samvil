"""Test Phase 23 evolve intake context dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase23_evolve_intake_context_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase23-evolve-intake-context-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase23 evolve intake context dogfood passed" in result.stdout
    assert "focus=functional_spec" in result.stdout
