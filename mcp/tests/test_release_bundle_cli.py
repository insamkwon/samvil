"""Tests for scripts/build-release-bundle.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_build_release_bundle_cli(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "run-release-checks.py"
    bundler = repo / "scripts" / "build-release-bundle.py"
    commands = json.dumps([
        {"name": "cli_ok", "command": "python3 -c 'print(\"cli ok\")'", "timeout_seconds": 5},
    ])
    run_result = subprocess.run(
        [
            sys.executable,
            str(runner),
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
    assert run_result.returncode == 0, run_result.stderr

    bundle_result = subprocess.run(
        [
            sys.executable,
            str(bundler),
            "--root",
            str(tmp_path),
            "--format",
            "json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    data = json.loads(bundle_result.stdout)
    assert bundle_result.returncode == 0, bundle_result.stderr
    assert data["status"] == "ok"
    assert data["bundle"]["release"]["source"] == "runner"
    assert data["bundle"]["checks"][0]["name"] == "cli_ok"
    assert (tmp_path / ".samvil" / "release-summary.md").exists()
