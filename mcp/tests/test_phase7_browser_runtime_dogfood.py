"""Regression test for Phase 7 browser runtime dogfood."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.getenv("SAMVIL_RUN_BROWSER_DOGFOOD") != "1",
    reason="set SAMVIL_RUN_BROWSER_DOGFOOD=1 to run network/browser dogfood",
)
def test_phase7_browser_runtime_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase7-browser-runtime-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase7 browser runtime dogfood passed" in result.stdout
    assert "vite-saas-dashboard-browser: pack=saas-dashboard" in result.stdout
    assert "vite-phaser-game-browser: pack=browser-game" in result.stdout
    assert "dashboard browser check ok" in result.stdout
    assert "game browser check ok" in result.stdout
    assert "retro=0" in result.stdout
