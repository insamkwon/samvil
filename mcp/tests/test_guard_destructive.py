"""Regression tests for the destructive Bash pre-tool guard."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "hooks" / "guard-destructive.sh"
PLUGIN = REPO / ".claude-plugin" / "plugin.json"


def load_guard_module():
    spec = importlib.util.spec_from_file_location(
        "guard_destructive_py", REPO / "hooks" / "guard_destructive.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "bash -c 'rm \"$@\"' -- -rf /",
        "bash -c 'git \"$@\"' -- reset --hard HEAD",
        "bash -c 'psql -c \"$1\"' -- 'DROP TABLE users'",
    ],
)
def test_shell_c_positional_arguments_cannot_hide_destructive_commands(
    command: str,
) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_shell_c_safe_positional_arguments_pass() -> None:
    result = run_guard("bash -c 'printf \"%s\\n\" \"$@\"' -- hello world")

    assert result.returncode == 0, result.stdout + result.stderr


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
        "rm -R ~/.ssh",
        "rm -r ../sibling-project",
        "rm -rf .samvil",
        "rm -rf .samvil/claims.jsonl",
        "rm -rf .samvil/next-skill.json",
        "rm -rf project.seed.json",
        "rm -rf project.state.json",
        "rm -rf project.config.json",
        "rm -rf interview-summary.md",
        'bash -c "rm -r /"',
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
        "F=$(printf rf); rm -$F /",
        "F=$(printf rf); rm -$F ~/.ssh",
        "R=$(printf recursive); F=$(printf force); rm --$R --$F /",
        "F=$(printf force); rm --recursive --$F /",
        "R=$(printf recursive); rm --$R --force /",
        "G=git; $G reset --hard HEAD",
        "CMD='rm -rf /'; bash -c \"$CMD\"",
        "A='rm'; B='-rf /'; CMD=\"$A $B\"; bash -c \"$CMD\"",
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
        "psql -c 'TRUNCATE users'",
        "psql -c 'TRUNCATE ONLY users'",
        "psql -c 'DELETE FROM users'",
        "psql -c 'DROP SCHEMA public'",
        "psql -c 'ALTER TABLE users DROP COLUMN password_hash'",
        "psql -c 'ALTER TABLE users DROP CONSTRAINT users_email_key'",
        "psql -c 'DROP ROLE app_user'",
        "psql -c 'DROP VIEW user_reports'",
        "psql -c 'DROP OWNED BY app_user'",
        "psql -c 'DROP SERVER foreign_srv CASCADE'",
        "psql -c 'DROP PUBLICATION app_pub'",
        "D=drop; psql -c \"$D table users\"",
        "T=TABLE; psql -c \"DROP $T users\"",
        "D='DROP'; T='TABLE users'; SQL=\"$D $T\"; psql -c \"$SQL\"",
        "D=$(printf DROP); T=$(printf TABLE); psql -c \"$D $T users\"",
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
        "mysql -e 'DROP # comment\nTABLE users'",
        "mysql -e 'TRUNCATE # comment\nTABLE users'",
        "mysql -e 'DELETE # comment\nFROM users'",
        "mysql -e 'ALTER TABLE users DROP FOREIGN KEY fk_user'",
        "mysql -e 'ALTER TABLE users DROP PRIMARY KEY'",
        "mysql -e 'ALTER TABLE users DROP INDEX idx_email'",
        "mysql -e 'DROP TEMPORARY TABLE scratch_users'",
    ],
)
def test_mysql_comment_and_alter_drop_variants_are_blocked(command: str) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_destructive_words_inside_sql_string_literal_pass() -> None:
    result = run_guard("mysql -e \"SELECT 'DROP # comment\\nTABLE users'\"")

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "rm -f project.seed.json",
        "rm project.state.json",
        "rm --force ./project.config.json",
        "rm -f interview-summary.md",
        "rm -f .samvil/claims.jsonl",
        "rm .samvil/next-skill.json",
        "rm -f .samvil/events.jsonl",
        "rm -f .samvil/qa-results.json",
        "rm -f .samvil/handoff.md",
        "rm -f $PWD/project.seed.json",
    ],
)
def test_protected_ssot_files_cannot_be_removed_non_recursively(command: str) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "rm -f tmp.log",
        "rm -f .samvil/cache/tmp.json",
        "rm -f .next/cache.json",
    ],
)
def test_non_ssot_files_can_be_removed_non_recursively(command: str) -> None:
    result = run_guard(command)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .next",
        "rm -rf .samvil/cache",
        "rm -r .samvil/cache",
        "rm -rf node_modules",
        "rm -r .next",
        "rm -r node_modules",
        "git clean -fdn",
        "git clean --force --dirs --dry-run",
        "find . -print",
        "find . -name '*.py'",
        "find . -exec echo {} +",
        "git push --force-with-lease origin feature",
        "git push origin feature",
        "select * from users",
        "psql -c 'ALTER TABLE users ADD COLUMN nickname text'",
        "echo 'DROP TABLE users'",
        "printf 'DROP DATABASE demo\\n'",
        "F=$(printf rf); rm -$F .next",
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


@pytest.mark.parametrize("source_command", ["source {script}", ". {script}"])
def test_shell_source_file_with_destructive_command_is_blocked(
    tmp_path: Path, source_command: str
) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text("rm -rf /\n", encoding="utf-8")

    result = run_guard(source_command.format(script=script))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_nested_shell_source_file_with_destructive_command_is_blocked(
    tmp_path: Path,
) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text("rm -rf /\n", encoding="utf-8")

    result = run_guard(f'bash -c "source {script}"')

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_shell_source_file_passes(tmp_path: Path) -> None:
    script = tmp_path / "safe.sh"
    script.write_text("echo safe\n", encoding="utf-8")

    result = run_guard(f"source {script}")

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_script_cross_line_assignment_payload_is_blocked(
    tmp_path: Path,
) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text("CMD='rm -rf /'\nbash -c \"$CMD\"\n", encoding="utf-8")

    result = run_guard(f"bash {script}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_shell_script_cross_line_assignment_passes(tmp_path: Path) -> None:
    script = tmp_path / "safe.sh"
    script.write_text("MSG='hello world'\necho \"$MSG\"\n", encoding="utf-8")

    result = run_guard(f"bash {script}")

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_script_multi_var_payload_assembly_is_blocked(tmp_path: Path) -> None:
    script = tmp_path / "nuke.sh"
    script.write_text(
        "A='rm'\nB='-rf /'\nCMD=\"$A $B\"\nbash -c \"$CMD\"\n",
        encoding="utf-8",
    )

    result = run_guard(f"bash {script}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_shell_script_multi_var_sql_payload_assembly_is_blocked(
    tmp_path: Path,
) -> None:
    script = tmp_path / "drop.sh"
    script.write_text(
        "D='DROP'\nT='TABLE users'\nSQL=\"$D $T\"\npsql -c \"$SQL\"\n",
        encoding="utf-8",
    )

    result = run_guard(f"bash {script}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_shell_script_multi_var_assignment_passes(tmp_path: Path) -> None:
    script = tmp_path / "safe.sh"
    script.write_text(
        "FIRST='hello'\nSECOND='world'\nMSG=\"$FIRST $SECOND\"\necho \"$MSG\"\n",
        encoding="utf-8",
    )

    result = run_guard(f"bash {script}")

    assert result.returncode == 0, result.stdout + result.stderr


def test_safe_self_referential_shell_script_does_not_fail_analyzer(
    tmp_path: Path,
) -> None:
    script = tmp_path / "self.sh"
    script.write_text(f"bash {script}\n", encoding="utf-8")

    result = run_guard(f"bash {script}")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "analyzer failed" not in result.stderr.casefold()


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


@pytest.mark.parametrize(
    "outer_sql",
    [
        "\\i {inner}\n",
        "\\include {inner}\n",
        "source {inner}\n",
        "\\. {inner}\n",
    ],
)
def test_sql_include_file_with_destructive_statement_is_blocked(
    tmp_path: Path, outer_sql: str
) -> None:
    inner = tmp_path / "inner.sql"
    inner.write_text("DROP TABLE users;\n", encoding="utf-8")
    outer = tmp_path / "outer.sql"
    outer.write_text(outer_sql.format(inner=inner), encoding="utf-8")

    result = run_guard(f"psql -f {outer}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_sql_relative_include_file_with_destructive_statement_is_blocked(
    tmp_path: Path,
) -> None:
    inner = tmp_path / "inner.sql"
    inner.write_text("DROP TABLE users;\n", encoding="utf-8")
    outer = tmp_path / "outer.sql"
    outer.write_text("\\i inner.sql\n", encoding="utf-8")

    result = run_guard(f"psql -f {outer}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_safe_sql_file_passes(tmp_path: Path) -> None:
    sql = tmp_path / "select.sql"
    sql.write_text("SELECT * FROM users;\n", encoding="utf-8")

    result = run_guard(f"psql -f {sql}")

    assert result.returncode == 0, result.stdout + result.stderr


def test_large_inspectable_file_is_rejected_before_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard = load_guard_module()
    script = tmp_path / "huge.sh"
    script.write_bytes(b"x" * (guard.FILE_INSPECTION_LIMIT_BYTES + 2))

    def fail_read_bytes(self: Path) -> bytes:
        raise AssertionError("read_bytes must not run before size guard")

    monkeypatch.setattr(guard.Path, "read_bytes", fail_read_bytes)

    text, error = guard._read_inspectable_file(str(script), "shell script")

    assert text is None
    assert error == "shell script file too large to inspect"


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
