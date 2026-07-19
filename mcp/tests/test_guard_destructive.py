"""Regression tests for the destructive Bash pre-tool guard."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "hooks" / "guard-destructive.sh"


def run_guard(
    command: str,
    *,
    nested: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = {"tool_input": {"command": command}} if nested else {"command": command}
    return subprocess.run(
        ["bash", str(HOOK), json.dumps(payload)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm  -rf /",
        "rm -fr /",
        "rm -r -f $TARGET",
        "rm --force --recursive ~",
        "rm -rf ~+",
        "rm -rf ~-",
        "rm -rf ~root",
        "rm -rf . && echo .next",
        "git reset   --hard HEAD~1",
        "git clean -df",
        "git push -f origin main",
        "git push --force origin main",
        "/bin/rm -fr /",
        "/usr/bin/git -C /tmp push --force origin main",
        "git --git-dir=.git reset --hard HEAD~1",
        "psql -c 'Drop Table users'",
        'mysql -e "dRoP dAtAbAsE production"',
        "echo safe\nrm -rf /",
        "cd /tmp\ngit reset --hard HEAD~1",
        "rm -rf ../sibling-project",
        "rm -rf ../..",
        "timeout 5 rm -rf /",
        "nohup git reset --hard HEAD~1",
        "nice rm -rf /home",
        "command rm -rf /",
        "exec rm -rf ~",
        "exec -a fake rm -rf .",
        "exec -cl -a fake rm -rf /",
        "xargs rm -rf /",
        'bash -lc "rm -rf /"',
        "(rm -rf /)",
        "sudo -u root rm -rf /",
        "sudo --user root rm -rf /",
        "env -u HOME rm -rf /",
        "env --unset HOME rm -rf /",
        'env -S "rm -rf /"',
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
        "echo 'DROP TABLE users'",
        "printf 'DROP DATABASE demo\\n'",
    ],
)
def test_safe_or_explicitly_allowed_variants_pass(command: str) -> None:
    result = run_guard(command, nested=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_block_message_does_not_echo_sensitive_tool_input() -> None:
    sensitive_value = "token=" + "fixture-value"
    result = run_guard(f"rm -fr / {sensitive_value}")

    assert result.returncode == 1
    assert sensitive_value not in result.stdout
    assert sensitive_value not in result.stderr


def test_analyzer_failure_blocks_command(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = run_guard("echo safe", env=env)

    assert result.returncode == 1
    assert "analyzer failed" in result.stdout.casefold()
