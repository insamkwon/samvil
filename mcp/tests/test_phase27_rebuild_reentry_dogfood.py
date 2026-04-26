"""Test Phase 27 rebuild reentry dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase27_rebuild_reentry_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase27-rebuild-reentry-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase27 rebuild reentry dogfood passed" in result.stdout
    assert "status=ready" in result.stdout
