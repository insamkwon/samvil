"""Regression test for Phase 6 real runtime dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase6_real_runtime_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase6-real-runtime-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=40,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase6 real runtime dogfood passed" in result.stdout
    assert "saas-dashboard-runtime: pack=saas-dashboard" in result.stdout
    assert "browser-game-runtime: pack=browser-game" in result.stdout
    assert "retro=0" in result.stdout
    assert "html_bytes=" in result.stdout
