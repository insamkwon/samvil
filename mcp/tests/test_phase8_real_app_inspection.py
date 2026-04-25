"""Regression test for Phase 8 real app inspection dogfood."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.getenv("SAMVIL_RUN_BROWSER_DOGFOOD") != "1",
    reason="set SAMVIL_RUN_BROWSER_DOGFOOD=1 to run network/browser inspection dogfood",
)
def test_phase8_real_app_inspection_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase8-real-app-inspection.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=220,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase8 real app inspection passed" in result.stdout
    assert "vite-saas-dashboard-inspection: pack=saas-dashboard" in result.stdout
    assert "vite-phaser-game-inspection: pack=browser-game" in result.stdout
    assert "failed=0" in result.stdout
    assert "console_errors=0" in result.stdout
    assert "screenshots=2" in result.stdout
    assert "viewports=2" in result.stdout
    assert "retro=0" in result.stdout
