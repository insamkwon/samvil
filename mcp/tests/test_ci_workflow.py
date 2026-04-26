from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "release-checks.yml"


def test_release_checks_workflow_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for expected in (
        "SAMVIL Release Checks",
        "actions/checkout@v4",
        "actions/setup-python@v5",
        'python-version: "3.12"',
        "actions/setup-node@v4",
        'node-version: "20"',
        "npx --yes playwright@1.52.0 install --with-deps chromium",
        "set -o pipefail",
        "python3 scripts/run-release-checks.py --format json",
        "python3 scripts/build-release-bundle.py --format json",
        "actions/upload-artifact@v4",
        "samvil-release-evidence",
        "release-report.json",
        "release-summary.md",
        "release-runner.json",
        "release-bundle.json",
    ):
        assert expected in text


def test_ci_workflow_validator_script_passes() -> None:
    result = subprocess.run(
        ["python3", "scripts/validate-ci-workflow.py"],
        cwd=REPO,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: ci workflow validation passed" in result.stdout
