"""Test Phase 24 evolve proposal dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase24_evolve_proposal_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase24-evolve-proposal-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase24 evolve proposal dogfood passed" in result.stdout
    assert "changes=1" in result.stdout
