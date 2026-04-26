from __future__ import annotations

import subprocess
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "mcp" / "tests" / "fixtures"


def test_publish_verified_release_cli_dry_run_passes_with_fixtures(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, text=True).strip()
    run = json.loads((FIXTURES / "remote-run-pass.json").read_text(encoding="utf-8"))
    run["headSha"] = head
    run_path = tmp_path / "remote-run-pass-current-head.json"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    result = subprocess.run(
        [
            "python3",
            "scripts/publish-verified-release.py",
            "--dry-run",
            "--allow-dirty",
            "--skip-local-release-checks",
            "--run-json",
            str(run_path),
            "--runner-json",
            str(FIXTURES / "remote-runner-pass.json"),
            "--version",
            "3.19.0",
            "--branch",
            branch,
            "--format",
            "json",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert '"verdict": "pass"' in result.stdout
    assert f'"head": "{head}"' in result.stdout
    assert '"dry_run": true' in result.stdout


def test_publish_verified_release_cli_blocks_failed_remote_fixture(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    run = json.loads((FIXTURES / "remote-run-failed.json").read_text(encoding="utf-8"))
    run["headSha"] = head
    run_path = tmp_path / "remote-run-failed-current-head.json"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    result = subprocess.run(
        [
            "python3",
            "scripts/publish-verified-release.py",
            "--dry-run",
            "--allow-dirty",
            "--skip-local-release-checks",
            "--run-json",
            str(run_path),
            "--runner-json",
            str(FIXTURES / "remote-runner-pass.json"),
            "--version",
            "3.19.0",
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
    assert "remote release gate is not pass" in result.stdout
