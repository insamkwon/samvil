"""Regression test for Phase 14 release evidence bundle dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase14_release_evidence_bundle_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase14-release-evidence-bundle-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase14 release evidence bundle dogfood passed" in result.stdout
    assert "bundle-all-pass: status=pass" in result.stdout
    assert "bundle-failed-output: status=blocked" in result.stdout
