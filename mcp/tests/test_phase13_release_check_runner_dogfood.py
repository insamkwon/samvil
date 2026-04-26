"""Regression test for Phase 13 release check runner dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase13_release_check_runner_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase13-release-check-runner-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase13 release check runner dogfood passed" in result.stdout
    assert "runner-all-pass: gate=pass" in result.stdout
    assert "runner-command-failed: gate=blocked" in result.stdout
    assert "runner-command-timeout: gate=blocked" in result.stdout
