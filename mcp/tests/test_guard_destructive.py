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
        "python3 -c \"from pathlib import Path; Path('project.seed.json').unlink()\"",
        "python -c \"open('.samvil/events.jsonl', 'w').close()\"",
        "ruby -e \"File.delete('project.state.json')\"",
        "perl -e \"unlink 'project.config.json'\"",
        "node -e \"require('fs').truncateSync('.samvil/claims.jsonl', 0)\"",
        "php -r \"unlink('interview-summary.md');\"",
        "python3 -c \"import os; os.system('rm project.seed.json')\"",
        "python3 -c \"import subprocess; subprocess.run(['rm', '.samvil/events.jsonl'])\"",
        "node -e \"require('child_process').execSync('rm project.state.json')\"",
        "python3 -c \"from pathlib import Path; Path('project.' + 'seed.json').unlink()\"",
        "python3 -c \"import shutil; shutil.copyfile('/dev/null', 'project.seed.json')\"",
        "ruby -e \"File.write('project.state.json', '')\"",
        "node -e \"require('fs').createWriteStream('.samvil/claims.jsonl')\"",
        "php -r \"fopen('interview-summary.md', 'w');\"",
    ],
)
def test_inline_language_runtime_cannot_mutate_protected_ssot(command: str) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(command)

    assert reason == "inline language runtime may mutate protected SAMVIL SSOT"


def test_inline_language_runtime_can_read_protected_ssot() -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        "python3 -c \"print(open('project.seed.json').read())\""
    )

    assert reason is None


def test_language_runtime_heredoc_cannot_mutate_protected_ssot() -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "Path('project.seed.json').unlink()\n"
        "PY"
    )

    assert reason == "language runtime may mutate protected SAMVIL SSOT"


@pytest.mark.parametrize(
    "command",
    [
        (
            "python3 - <<< \"from pathlib import Path; "
            "Path('project.seed.json').unlink()\""
        ),
        (
            "printf \"%s\" \"from pathlib import Path; "
            "Path('project.seed.json').unlink()\" | python3 -"
        ),
        "echo \"require('fs').unlinkSync('.samvil/events.jsonl')\" | node",
    ],
)
def test_language_runtime_stdin_cannot_mutate_protected_ssot(command: str) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(command)

    assert reason == "language runtime may mutate protected SAMVIL SSOT"


def test_language_runtime_script_file_cannot_mutate_protected_ssot(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    script = tmp_path / "mutate.py"
    script.write_text(
        "from pathlib import Path\nPath('project.seed.json').unlink()\n",
        encoding="utf-8",
    )

    reason = guard.analyze_command(f"python3 {script}")

    assert reason == "language runtime script file with protected SSOT mutation"


def test_language_runtime_env_path_cannot_hide_protected_ssot_mutation() -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        "TARGET=project.seed.json "
        "python3 -c \"import os; os.remove(os.environ['TARGET'])\""
    )

    assert reason == "inline language runtime may mutate protected SAMVIL SSOT"


def test_language_runtime_safe_stdin_and_script_file_pass(tmp_path: Path) -> None:
    guard = load_guard_module()
    script = tmp_path / "safe.py"
    script.write_text("print(open('project.seed.json').read())\n", encoding="utf-8")

    assert guard.analyze_command(f"python3 {script}") is None
    assert (
        guard.analyze_command(
            "python3 - <<'PY'\n"
            "print(open('project.seed.json').read())\n"
            "PY"
        )
        is None
    )
    assert (
        guard.analyze_command(
            "TARGET=/tmp/samvil-cache "
            "python3 -c \"import os; os.remove(os.environ['TARGET'])\""
        )
        is None
    )


@pytest.mark.parametrize(
    "command",
    [
        "sqlite3 ~/.samvil/samvil.db \"INSERT INTO events VALUES ('forged')\"",
        (
            "python3 -c \"import sqlite3; "
            "sqlite3.connect('/tmp/home/.samvil/samvil.db')"
            ".execute('UPDATE events SET trusted_transition=1')\""
        ),
        (
            "python3 - <<'PY'\n"
            "import sqlite3\n"
            "from pathlib import Path\n"
            "db = Path.home() / '.samvil' / 'samvil.db'\n"
            "sqlite3.connect(db).execute('INSERT INTO events DEFAULT VALUES')\n"
            "PY"
        ),
        (
            "python3 -c \"store.save_event_and_update_stage("
            "session_id, event_type, stage)\""
        ),
        (
            "sqlite3 'file:/tmp/home/.samvil/samvil.db?mode=rw' "
            "\"REPLACE INTO events VALUES ('forged')\""
        ),
        (
            "sqlite3 ~/.samvil/samvil.db "
            "\"SELECT id FROM events; UPDATE events SET trusted_transition=1\""
        ),
        (
            "python3 -c \"import sqlite3; "
            "sqlite3.connect('/tmp/home/.samvil/samvil.db')"
            ".execute('UP' + 'DATE events SET trusted_transition=1')\""
        ),
        (
            "python3 -c \"from samvil_mcp.server import DB_PATH; import sqlite3; "
            "sqlite3.connect(DB_PATH).execute('INSERT INTO events DEFAULT VALUES')\""
        ),
    ],
)
def test_direct_samvil_event_store_mutation_is_blocked(command: str) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(command)

    assert reason == "direct SAMVIL EventStore mutation"


def test_read_only_samvil_event_store_query_passes() -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        "sqlite3 ~/.samvil/samvil.db \"SELECT id FROM events LIMIT 1\""
    )

    assert reason is None


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
        "mysql -e \"PREPARE stmt FROM 'DROP TABLE users'; EXECUTE stmt\"",
        "psql -c \"SELECT 'DROP TABLE users;' \\\\gexec\"",
        "psql -c '\\! rm -f project.seed.json'",
        "sqlcmd -Q 'DELETE dbo.Users WHERE id = 1'",
        "sqlcmd -Q 'DELETE TOP (1) dbo.Users WHERE id = 1'",
        "sqlcmd -Q 'MERGE dbo.Users AS target USING src ON 1=1 WHEN MATCHED THEN DELETE;'",
    ],
)
def test_dynamic_and_dialect_specific_sql_deletion_is_blocked(command: str) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "mysql -e \"PREPARE stmt FROM 'SELECT 1'; EXECUTE stmt\"",
        "psql -c '\\! echo safe'",
        "sqlcmd -Q 'GRANT DELETE ON dbo.Users TO app_user'",
    ],
)
def test_safe_dynamic_or_permission_sql_variants_pass(command: str) -> None:
    result = run_guard(command)

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
        "rm -f project.seed.*",
        "rm -f project.{seed,state}.json",
        'rm -f "$(pwd)/project.seed.json"',
        'rm -f "$TARGET"',
        "rm -f .samvil/*.jsonl",
    ],
)
def test_dynamic_or_expanded_targets_cannot_hide_protected_ssot(
    command: str,
) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_brace_expansion_limit_cannot_hide_protected_ssot() -> None:
    harmless = [f"tmp-{index}.json" for index in range(32)]
    command = "rm -f {" + ",".join([*harmless, "project.seed.json"]) + "}"

    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


def test_exact_brace_expansion_limit_cannot_leave_nested_ssot_unchecked() -> None:
    first_brace = ",".join(["", *(f"x{index}" for index in range(31))])
    command = f"rm -f {{{first_brace}}}{{project.seed.json,safe}}"

    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "truncate -s 0 project.seed.json",
        "cp /dev/null .samvil/events.jsonl",
        "install /dev/null project.seed.json",
        "tee project.state.json",
        "dd if=/dev/null of=.samvil/qa-results.json",
        "> project.seed.json",
        "printf '{}' > project.state.json",
        "echo corrupt >> .samvil/qa-results.json",
    ],
)
def test_non_rm_overwrites_cannot_destroy_protected_ssot(command: str) -> None:
    result = run_guard(command)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "cp /tmp/forged project.seed.json",
        "cp /tmp/forged project.seed.json -f",
        "cp /tmp/project.seed.json .",
        "cp -t . /tmp/project.seed.json",
        "install /tmp/forged project.config.json",
        "mv replacement project.state.json",
        "rsync /tmp/forged project.seed.json",
        "perl -pi -e 's/old/forged/' project.config.json",
        "perl -0777pi -e 's/old/forged/' project.seed.json",
        "perl -0pi -e 's/old/forged/' project.seed.json",
        "perl -0777pi.bak -e 's/old/forged/' project.seed.json",
        "perl -i0 -pe 's/old/forged/' project.seed.json",
        "perl -piABC -e 's/old/forged/' project.seed.json",
        "perl -0777pi0 -e 's/old/forged/' project.seed.json",
        "perl -Upi0 -e 's/old/forged/' project.seed.json",
        "perl -dpi0 -e 's/old/forged/' project.seed.json",
        "sed -i 's/old/forged/' project.config.json",
    ],
)
def test_arbitrary_sources_cannot_replace_protected_ssot(command: str) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(command)

    assert reason is not None and "protected SAMVIL" in reason


def test_perl_numeric_record_separator_without_in_place_edit_still_passes() -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        "perl -0777 -ne 'print if /project/' project.seed.json"
    )

    assert reason is None


@pytest.mark.parametrize(
    "options",
    ["-Mstrict -ne", "-xinput", "-di0"],
)
def test_perl_option_arguments_containing_i_are_not_mistaken_for_in_place_edit(
    options: str,
) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(
        f"perl {options} -e 'print if /project/' project.seed.json"
    )

    assert reason is None


@pytest.mark.parametrize(
    "command",
    [
        "cp /tmp/forged ~/.samvil/samvil.db",
        "cp /tmp/samvil.db ~/.samvil",
        "mv /tmp/forged ~/.samvil/samvil.db",
        "ln -sf /tmp/forged ~/.samvil/samvil.db",
        "sed -i 's/old/forged/' ~/.samvil/samvil.db",
    ],
)
def test_shell_commands_cannot_replace_samvil_event_store(command: str) -> None:
    guard = load_guard_module()

    reason = guard.analyze_command(command)

    assert reason == "protected SAMVIL EventStore overwrite"


def test_event_store_symlink_alias_cannot_bypass_write_or_overwrite_guard(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    db_path = tmp_path / ".samvil" / "samvil.db"
    db_path.parent.mkdir()
    db_path.touch()
    alias = tmp_path / "event-store-alias.db"
    alias.symlink_to(db_path)

    assert (
        guard.analyze_command(f"sqlite3 {alias} 'UPDATE events SET stage=\"qa\"'")
        == "direct SAMVIL EventStore mutation"
    )
    assert (
        guard.analyze_command(f"cp /tmp/forged {alias}")
        == "protected SAMVIL EventStore overwrite"
    )


@pytest.mark.parametrize(
    "operation",
    [
        "sqlite3 {alias} 'UPDATE events SET trusted_transition=1'",
        "cp /tmp/forged {alias}",
    ],
)
def test_new_event_store_symlink_in_same_command_cannot_bypass_guard(
    tmp_path: Path,
    operation: str,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "new-event-store-alias.db"
    command = (
        f"ln -s ~/.samvil/samvil.db {alias} && "
        + operation.format(alias=alias)
    )

    reason = guard.analyze_command(command)

    assert reason in {
        "direct SAMVIL EventStore mutation",
        "protected SAMVIL EventStore overwrite",
    }


@pytest.mark.parametrize(
    "operation",
    [
        "sh -c 'cp /tmp/forged {alias}'",
        "eval 'cp /tmp/forged {alias}'",
        (
            'python -c "from shutil import copyfile; '
            "copyfile('/tmp/forged', '{alias}')\""
        ),
    ],
)
def test_new_event_store_symlink_in_nested_payload_cannot_bypass_guard(
    tmp_path: Path,
    operation: str,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "new-event-store-nested-alias.db"
    command = (
        f"ln -s ~/.samvil/samvil.db {alias} && "
        + operation.format(alias=alias)
    )

    reason = guard.analyze_command(command)

    assert reason in {
        "direct SAMVIL EventStore mutation",
        "inline language runtime may mutate protected SAMVIL SSOT",
        "protected SAMVIL EventStore overwrite",
    }


@pytest.mark.parametrize(
    "creator",
    [
        "sh -c 'ln -s ~/.samvil/samvil.db {alias}'",
        "eval 'ln -s ~/.samvil/samvil.db {alias}'",
    ],
)
def test_nested_payload_created_event_store_alias_cannot_escape_to_outer_command(
    tmp_path: Path,
    creator: str,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "nested-created-event-store-alias.db"

    reason = guard.analyze_command(
        creator.format(alias=alias) + f" && cp /tmp/forged {alias}"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


def test_new_event_store_symlink_relative_spelling_cannot_bypass_nested_guard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    guard = load_guard_module()
    monkeypatch.chdir(tmp_path)
    alias = "relative-event-store-alias.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {alias} && "
        f"sh -c 'cp /tmp/forged ./{alias}'"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


def test_new_event_store_symlink_directory_destination_cannot_bypass_guard(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    alias_dir = tmp_path / "aliases"
    alias_dir.mkdir()
    alias = alias_dir / "samvil.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {alias_dir} && cp /tmp/forged {alias}"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


@pytest.mark.parametrize(
    "creator",
    [
        "ln ~/.samvil/samvil.db {alias}",
        "link ~/.samvil/samvil.db {alias}",
        "cp -l ~/.samvil/samvil.db {alias}",
        "cp --link ~/.samvil/samvil.db {alias}",
    ],
)
def test_event_store_hard_link_cannot_create_an_unprotected_write_alias(
    tmp_path: Path,
    creator: str,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "event-store-hard-link.db"

    reason = guard.analyze_command(
        creator.format(alias=alias) + f" && cp /tmp/forged {alias}"
    )

    assert reason == "protected SAMVIL EventStore hard link"


@pytest.mark.parametrize(
    "creator",
    [
        "mkdir {alias_dir} && ln -s ~/.samvil/samvil.db {alias_dir}",
        "mkdir -p {alias_dir} && ln -s -t {alias_dir} ~/.samvil/samvil.db",
        (
            "mkdir {alias_dir} && ln -s "
            "--target-directory={alias_dir} ~/.samvil/samvil.db"
        ),
        (
            "sh -c 'mkdir {alias_dir} && "
            "ln -s ~/.samvil/samvil.db {alias_dir}'"
        ),
    ],
)
def test_same_command_created_directory_symlink_destination_cannot_bypass_guard(
    tmp_path: Path,
    creator: str,
) -> None:
    guard = load_guard_module()
    alias_dir = tmp_path / "future-aliases"
    alias = alias_dir / "samvil.db"

    reason = guard.analyze_command(
        creator.format(alias_dir=alias_dir) + f" && cp /tmp/forged {alias}"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


def test_removed_same_command_directory_is_not_used_for_symlink_destination(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    alias_dir = tmp_path / "removed-alias-dir"

    reason = guard.analyze_command(
        f"mkdir {alias_dir} && rmdir {alias_dir} && "
        f"ln -s ~/.samvil/samvil.db {alias_dir} && cp /tmp/forged {alias_dir}"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


def test_moved_symlink_alias_keeps_event_store_provenance(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    source_alias = tmp_path / "before.db"
    destination_alias = tmp_path / "after.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {source_alias} && "
        f"mv {source_alias} {destination_alias} && "
        f"cp /tmp/forged {destination_alias}"
    )

    assert reason == "protected SAMVIL EventStore overwrite"


def test_new_event_store_symlink_nested_read_only_query_still_passes(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "nested-read-only-event-store-alias.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {alias} && "
        f"sh -c \"sqlite3 {alias} 'SELECT id FROM events LIMIT 1'\""
    )

    assert reason is None


def test_new_event_store_symlink_name_prefix_in_nested_payload_is_not_rewritten(
    tmp_path: Path,
) -> None:
    guard = load_guard_module()
    alias = tmp_path / "nested-event-store-alias.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {alias} && "
        f"sh -c 'cp /tmp/forged {alias}.backup'"
    )

    assert reason is None


def test_new_event_store_symlink_read_only_query_still_passes(tmp_path: Path) -> None:
    guard = load_guard_module()
    alias = tmp_path / "read-only-event-store-alias.db"

    reason = guard.analyze_command(
        f"ln -s ~/.samvil/samvil.db {alias} && "
        f"sqlite3 {alias} 'SELECT id FROM events LIMIT 1'"
    )

    assert reason is None


def test_event_store_file_cannot_be_removed_or_replaced_by_runtime() -> None:
    guard = load_guard_module()

    assert (
        guard.analyze_command("rm -f ~/.samvil/samvil.db")
        == "protected SAMVIL EventStore removal"
    )
    assert (
        guard.analyze_command(
            "python3 -c \"import shutil; "
            "shutil.copyfile('/tmp/forged', '/tmp/home/.samvil/samvil.db')\""
        )
        == "inline language runtime may mutate protected SAMVIL SSOT"
    )


def test_safe_file_copy_and_in_place_edit_still_pass() -> None:
    guard = load_guard_module()

    assert guard.analyze_command("cp /tmp/source /tmp/destination") is None
    assert guard.analyze_command("rsync /tmp/source /tmp/destination") is None
    assert guard.analyze_command("perl -pe 's/old/new/' /tmp/cache.json") is None
    assert guard.analyze_command("sed -i 's/old/new/' /tmp/cache.json") is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -f tmp.log",
        "rm -f *.tmp",
        "rm -f .samvil/cache/tmp.json",
        "rm -f .samvil/cache/*.tmp",
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


def test_deep_eval_nesting_fails_closed_without_analyzer_crash() -> None:
    command = "eval " * 200 + "echo safe"

    result = run_guard(command, timeout=2)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stderr
    assert "analyzer failed" not in result.stderr.casefold()


def test_shallow_safe_eval_passes() -> None:
    result = run_guard("eval 'echo safe'")

    assert result.returncode == 0, result.stdout + result.stderr


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
