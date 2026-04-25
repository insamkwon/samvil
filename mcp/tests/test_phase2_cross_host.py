"""Cross-host replay smoke for Phase 2 fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_phase2_cross_host_smoke_script_passes():
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "phase2-cross-host-smoke.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "seed_next: samvil-design" in result.stdout
    assert "design_next: samvil-scaffold" in result.stdout
