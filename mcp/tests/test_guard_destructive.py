"""Regression tests for the destructive Bash pre-tool guard."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "hooks" / "guard-destructive.sh"
PLUGIN = REPO / ".claude-plugin" / "plugin.json"


def run_guard(
    command: str,
    *,
    nested: bool = True,
    env: dict[str, str] | None = None,
    timeout: float = 5,
) -> subprocess.CompletedProcess[str]:
    payload = {"tool_input": {"command": command}} if nested else {"command": command}
    return subprocess.run(
        ["bash", str(HOOK), json.dumps(payload)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
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
        "rm -rf .git",
        "git reset   --hard HEAD~1",
        "git clean -df",
        "git push -f origin main",
        "git push -fu origin main",
        "git push --force origin main",
        "git push origin +HEAD:main",
        "git push origin +feature",
        "git push --mirror origin",
        "git push -d origin main",
        "git push --prune origin",
        "git push origin --delete main",
        "git push origin :main",
        "P=push; git $P -f origin main",
        "S=reset; git $S --hard HEAD",
        "C=clean; git $C -df",
        "F=-f; git push $F origin main",
        "git -c alias.nuke='push --force' nuke origin main",
        "find . -delete",
        "find /tmp -exec rm -rf {} +",
        "find /tmp -execdir sh -c 'rm -rf /' ';'",
        "F=find; $F . -delete",
        "/bin/rm -fr /",
        "/usr/bin/git -C /tmp push --force origin main",
        "git --git-dir=.git reset --hard HEAD~1",
        "git -c alias.nuke='!git reset --hard' nuke",
        "psql -c 'Drop Table users'",
        'mysql -e "dRoP dAtAbAsE production"',
        "printf 'DROP TABLE users;' | psql '$DATABASE_URL'",
        "echo safe\nrm -rf /",
        "cd /tmp\ngit reset --hard HEAD~1",
        "rm -rf ../sibling-project",
        "rm -rf ../..",
        "timeout 5 rm -rf /",
        "nohup git reset --hard HEAD~1",
        "nice rm -rf /home",
        "time rm -rf /",
        "! rm -rf /",
        "if true; then rm -rf /; fi",
        "if rm -rf /; then :; fi",
        "while rm -rf /; do :; done",
        "until rm -rf /; do :; done",
        "coproc rm -rf /",
        "command rm -rf /",
        "exec rm -rf ~",
        "exec -a fake rm -rf .",
        "exec -cl -a fake rm -rf /",
        "xargs rm -rf /",
        'bash -lc "rm -rf /"',
        "bash --norc -c 'rm -rf /'",
        "bash --noprofile --norc -c 'rm -rf /'",
        "bash --rcfile /tmp/x -c 'rm -rf /'",
        "bash -c -- 'rm -rf /'",
        "sh -c -- 'rm -rf /'",
        "zsh -c -- 'rm -rf /'",
        "eval 'rm -rf /'",
        "builtin eval 'rm -rf /'",
        "R=rm; $R -rf /",
        "F=-rf; rm $F /",
        "G=git; $G reset --hard HEAD",
        "CMD='rm -rf /'; bash -c \"$CMD\"",
        "$(printf rm) -rf ~/.ssh",
        "`printf r`m -rf /",
        "/bin/r? -rf /",
        "r\\\nm -rf /",
        "echo `rm -rf /`",
        "printf 'rm -rf /' | bash",
        "bash <<< 'rm -rf /'",
        "bash < script.sh",
        "cat script.sh | bash",
        "rm -rf {*,.*}",
        "rm -rf {../outside,local}",
        "rm -rf .[!.]* ?*",
        "rm -rf .*",
        "rm -rf ?*",
        "(rm -rf /)",
        "sudo -u root rm -rf /",
        "sudo --user root rm -rf /",
        "env -u HOME rm -rf /",
        "env --unset HOME rm -rf /",
        'env -S "rm -rf /"',
        'env -S"rm -rf /"',
        "/usr/bin/time -o /tmp/time.log rm -rf /",
        "eval -- 'rm -rf /'",
        "builtin eval -- 'rm -rf /'",
        "psql -c 'DROP/**/TABLE users'",
        "mysql -e '/*!50000 DROP TABLE users */'",
        "psql -c 'TRUNCATE TABLE users'",
        "psql -c 'DELETE FROM users'",
        "psql -c 'DROP SCHEMA public'",
        "D=drop; psql -c \"$D table users\"",
        "T=TABLE; psql -c \"DROP $T users\"",
        "printf 'DROP/**/TABLE users;' | psql '$DATABASE_URL'",
        "P=psql; printf 'DROP TABLE users;' | $P",
        "S=bash; printf 'rm -rf /' | $S",
        "psql <<'SQL'\nDROP TABLE users;\nSQL",
        "printf 'DROP TABLE users;' | time psql",
    ],
)
def test_destructive_variants_are_blocked(command: str) -> None:
    result = run_guard(command)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .next",
        "rm -rf .samvil/cache",
        "rm -rf node_modules",
        "git clean -fdn",
        "git clean --force --dirs --dry-run",
        "find . -print",
        "find . -name '*.py'",
        "find . -exec echo {} +",
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


@pytest.mark.parametrize("shell", ["bash", "sh"])
def test_shell_script_file_with_destructive_command_is_blocked(
    tmp_path: Path, shell: str
) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text("rm -rf /\n", encoding="utf-8")

    result = run_guard(f"{shell} {script}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_shell_script_file_after_shell_options_is_blocked(tmp_path: Path) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text("git reset --hard HEAD~1\n", encoding="utf-8")

    result = run_guard(f"bash --noprofile --norc {script}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_shell_script_file_passes(tmp_path: Path) -> None:
    script = tmp_path / "safe.sh"
    script.write_text("echo safe\n", encoding="utf-8")

    result = run_guard(f"bash {script}")

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "command_template",
    [
        "psql -f {sql}",
        "psql --file={sql}",
        "mysql < {sql}",
    ],
)
def test_sql_file_with_destructive_statement_is_blocked(
    tmp_path: Path, command_template: str
) -> None:
    sql = tmp_path / "drop.sql"
    sql.write_text("DROP TABLE users;\n", encoding="utf-8")

    result = run_guard(command_template.format(sql=sql))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_sql_file_passes(tmp_path: Path) -> None:
    sql = tmp_path / "select.sql"
    sql.write_text("SELECT * FROM users;\n", encoding="utf-8")

    result = run_guard(f"psql -f {sql}")

    assert result.returncode == 0, result.stdout + result.stderr


def test_long_shell_pipeline_blocks_without_recursive_analyzer_failure() -> None:
    command = "echo safe " + " | bash" * 850

    result = run_guard(command, timeout=3)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr
    assert "analyzer failed" not in result.stderr.casefold()


def test_block_message_does_not_echo_sensitive_tool_input() -> None:
    sensitive_value = "token=" + "fixture-value"
    result = run_guard(f"rm -fr /tmp/{sensitive_value}")

    assert result.returncode == 2
    assert sensitive_value not in result.stdout
    assert sensitive_value not in result.stderr


def test_malformed_command_substitution_does_not_hang() -> None:
    result = run_guard("echo $(echo 'unterminated)", timeout=1)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        '{"tool_input":{"command":"rm -rf /',
        json.dumps({"tool_input": {"command": 'rm -rf /\necho "'}}),
    ],
)
def test_malformed_payload_or_shell_syntax_fails_closed(payload: str) -> None:
    result = subprocess.run(
        ["bash", str(HOOK), payload],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_analyzer_failure_blocks_command(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = run_guard("echo safe", env=env)

    assert result.returncode == 2
    assert "analyzer failed" in result.stderr.casefold()


def test_guard_hook_uses_environment_not_argv_for_tool_input() -> None:
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    command = plugin["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

    assert "guard-destructive.sh \"$TOOL_INPUT\"" not in command
    assert "$TOOL_INPUT" not in command
