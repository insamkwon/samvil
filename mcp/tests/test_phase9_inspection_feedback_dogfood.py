"""Regression test for Phase 9 inspection feedback dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase9_inspection_feedback_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase9-inspection-feedback-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase9 inspection feedback dogfood passed" in result.stdout
    assert "broken-dashboard-feedback: status=fail" in result.stdout
    assert "broken-game-feedback: status=fail" in result.stdout
    assert "console-error" in result.stdout
    assert "canvas-blank" in result.stdout
    assert "interaction-failed" in result.stdout
    assert "next_action='repair inspection failure:" in result.stdout
