"""Test Phase 22 QA recovery routing dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase22_qa_recovery_routing_dogfood_passes():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts" / "phase22-qa-recovery-routing-dogfood.py")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase22 QA recovery routing dogfood passed" in result.stdout
    assert "next_skill=samvil-evolve" in result.stdout
