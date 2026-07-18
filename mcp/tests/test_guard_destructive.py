"""Regression tests for the destructive Bash pre-tool guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "hooks" / "guard-destructive.sh"


def run_guard(command: str, *, nested: bool = True) -> subprocess.CompletedProcess[str]:
    payload = {"tool_input": {"command": command}} if nested else {"command": command}
    return subprocess.run(
        ["bash", str(HOOK), json.dumps(payload)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm  -rf /",
        "rm -fr /",
        "rm -r -f $TARGET",
        "rm --force --recursive ~",
        "rm -rf . && echo .next",
        "git reset   --hard HEAD~1",
        "git clean -df",
        "git push -f origin main",
        "git push --force origin main",
        "psql -c 'Drop Table users'",
        'mysql -e "dRoP dAtAbAsE production"',
    ],
)
def test_destructive_variants_are_blocked(command: str) -> None:
    result = run_guard(command)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .next",
        "rm -rf .samvil/cache",
        "rm -rf node_modules",
        "git push --force-with-lease origin feature",
        "git push origin feature",
        "select * from users",
    ],
)
def test_safe_or_explicitly_allowed_variants_pass(command: str) -> None:
    result = run_guard(command, nested=False)
    assert result.returncode == 0, result.stdout + result.stderr
