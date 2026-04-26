"""Regression test for Phase 12 release readiness dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase12_release_readiness_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase12-release-readiness-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase12 release readiness dogfood passed" in result.stdout
    assert "release-repair-blocked: gate=blocked" in result.stdout
    assert "release-check-failed: gate=blocked" in result.stdout
    assert "release-ready: gate=pass" in result.stdout
