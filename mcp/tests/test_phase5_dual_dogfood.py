"""Regression test for Phase 5 dual dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase5_dual_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase5-dual-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase5 dual dogfood passed" in result.stdout
    assert "saas-dashboard: pack=saas-dashboard" in result.stdout
    assert "browser-game: pack=browser-game" in result.stdout
    assert "retro=0" in result.stdout
