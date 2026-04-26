from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "mcp" / "tests" / "fixtures"


def test_remote_release_cli_pass_fixture() -> None:
    result = subprocess.run(
        [
            "python3",
            "scripts/check-remote-release-gate.py",
            "--run-json",
            str(FIXTURES / "remote-run-pass.json"),
            "--runner-json",
            str(FIXTURES / "remote-runner-pass.json"),
            "--head",
            "abc123",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Verdict: pass" in result.stdout
    assert "5 passed / 0 failed / 0 missing" in result.stdout


def test_remote_release_cli_blocks_failed_artifact_fixture() -> None:
    result = subprocess.run(
        [
            "python3",
            "scripts/check-remote-release-gate.py",
            "--run-json",
            str(FIXTURES / "remote-run-pass.json"),
            "--runner-json",
            str(FIXTURES / "remote-runner-blocked.json"),
            "--head",
            "abc123",
            "--format",
            "json",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert '"verdict": "blocked"' in result.stdout
    assert "fix release check: pre_commit" in result.stdout
