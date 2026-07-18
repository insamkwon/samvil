"""Agent persona count and registry drift checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_agent_inventory_ci_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check-agent-inventory.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
