"""Regression test for Phase 19 QA synthesis gate dogfood."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase19_qa_synthesis_gate_dogfood_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase19-qa-synthesis-gate-dogfood.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: phase19 QA synthesis gate dogfood passed" in result.stdout
    assert "unimplemented-non-core-revise: verdict=REVISE" in result.stdout
    assert "core-unimplemented-fail: verdict=FAIL" in result.stdout
