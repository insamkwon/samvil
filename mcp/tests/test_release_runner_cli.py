"""Tests for scripts/run-release-checks.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_release_checks_cli_with_custom_commands(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "run-release-checks.py"
    commands = json.dumps([
        {"name": "cli_ok", "command": "python3 -c 'print(\"cli ok\")'", "timeout_seconds": 5},
    ])

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--commands-json",
            commands,
            "--format",
            "json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    data = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert data["status"] == "ok"
    assert data["report"]["source"] == "runner"
    assert data["report"]["checks"][0]["name"] == "cli_ok"
    assert data["report"]["checks"][0]["exit_code"] == 0
    assert data["gate"]["verdict"] == "pass"
    assert (tmp_path / ".samvil" / "release-report.json").exists()
