"""Regression test for Phase 10 inspection repair dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase10_inspection_repair_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase10-inspection-repair-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase10 inspection repair dogfood passed" in result.stdout
    assert "repair-dashboard: before_failed=" in result.stdout
    assert "repair-game: before_failed=" in result.stdout
    assert "after_failed=0" in result.stdout
    assert "status=verified" in result.stdout
    assert "next_action='repair verified: re-run release checks'" in result.stdout
