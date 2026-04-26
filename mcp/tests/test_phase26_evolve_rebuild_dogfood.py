"""Test Phase 26 evolve rebuild handoff dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase26_evolve_rebuild_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase26-evolve-rebuild-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase26 evolve rebuild dogfood passed" in result.stdout
    assert "next=samvil-scaffold" in result.stdout
