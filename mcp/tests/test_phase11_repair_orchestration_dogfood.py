"""Regression test for Phase 11 repair orchestration dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase11_repair_orchestration_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase11-repair-orchestration-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: phase11 repair orchestration dogfood passed" in result.stdout
    assert "repair-gate-missing-plan: gate=blocked" in result.stdout
    assert "repair-gate-plan-only: gate=blocked" in result.stdout
    assert "repair-gate-verified: gate=pass" in result.stdout
    assert "policy_signals=1 first=repair-policy:console-error" in result.stdout
