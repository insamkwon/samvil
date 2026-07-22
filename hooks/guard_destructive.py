#!/usr/bin/env python3
"""Parse a Bash tool payload and report a destructive command reason."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path, PurePath
from typing import Any


MALFORMED_TOOL_INPUT_REASON = "malformed tool input"
SHELL_PARSE_ERROR_REASON = "shell parse error"
FILE_INSPECTION_LIMIT_BYTES = 1_000_000
SQL_CLIENTS = {"mariadb", "mysql", "psql", "sqlite3", "sqlcmd"}
SHELLS = {"bash", "dash", "sh", "zsh"}
CHAIN_TOKENS = {";", "&&", "||", "|", "|&", "&", "\n", ";\n", "(", ")", "{", "}"}
SHELL_CONTROL_PREFIXES = {
    "!",
    "if",
    "then",
    "while",
    "until",
    "do",
    "else",
    "elif",
    "coproc",
}
SIMPLE_WRAPPERS = {"builtin", "command", "exec", "nohup"}
DETECTABLE_EXECUTABLES = SQL_CLIENTS | SHELLS | {
    "builtin",
    "eval",
    "find",
    "git",
    "rm",
    "timeout",
    "nohup",
    "nice",
    "command",
    "exec",
    "time",
    "xargs",
}
GIT_GLOBAL_WITH_VALUE = {
    "-c",
    "-C",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}
SUDO_OPTIONS_WITH_VALUE = {
    "-C", "-D", "-R", "-T", "-g", "-h", "-p", "-u",
    "--chdir", "--chroot", "--close-from", "--command-timeout",
    "--group", "--host", "--prompt", "--user",
}
ENV_OPTIONS_WITH_VALUE = {"-C", "-S", "-u", "--chdir", "--split-string", "--unset"}
EXEC_OPTIONS_WITH_VALUE = {"-a"}
SHELL_OPTIONS_WITH_VALUE = {"--init-file", "--rcfile", "-o"}
SQL_FILE_OPTIONS_WITH_VALUE = {"-f", "--file"}
UNINSPECTABLE_PATH_CHARS = "`$*?[{"
_SCRIPT_INSPECTION_STACK: list[str] = []


def _normalize_shell_source(command: str) -> str:
    """Apply shell lexical normalizations that affect executable tokens."""
    return command.replace("\\\r\n", "").replace("\\\n", "")


def _simple_assignments_from_tokens(tokens: list[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    for token in tokens:
        if not pattern.match(token):
            continue
        name, _, value = token.partition("=")
        assignments[name] = value
    return assignments


def _shell_unquote_assignment_value(value: str) -> str:
    if value.startswith(("$(", "`")):
        return value
    try:
        parts = shlex.split(value)
    except ValueError:
        return value
    return parts[0] if len(parts) == 1 else value


def _simple_assignments_from_part(part: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    pattern = re.compile(
        r"\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)="
        r"(?P<value>\$\([^)]*\)|`[^`]*`|'[^']*'|\"[^\"]*\"|[^ \t\r\n;&|(){}]+)"
    )
    index = 0
    while index < len(part):
        match = pattern.match(part, index)
        if not match:
            break
        assignments[match.group("name")] = _shell_unquote_assignment_value(
            match.group("value")
        )
        index = match.end()
    return assignments


def _simple_assignments(command: str) -> dict[str, str]:
    """Collect simple shell assignments for conservative static expansion."""
    assignments: dict[str, str] = {}
    for part in _top_level_command_parts(command):
        assignments.update(_simple_assignments_from_part(part))
    return assignments


def _expand_shell_variables(command: str, assignments: dict[str, str]) -> str:
    if not assignments:
        return command

    def replace(match: re.Match[str]) -> str:
        name = match.group("braced") or match.group("plain") or ""
        return assignments.get(name, match.group(0))

    return re.sub(
        r"\$(?P<plain>[A-Za-z_][A-Za-z0-9_]*)|\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}",
        replace,
        command,
    )


def _expand_shell_variables_fixed_point(
    command: str, assignments: dict[str, str], *, limit: int = 8
) -> str:
    """Expand simple shell variables until values stabilize.

    This is intentionally bounded: the hook is a conservative static guard, not
    a shell interpreter, and recursive assignments should not make it loop.
    """
    expanded = command
    for _ in range(limit):
        next_expanded = _expand_shell_variables(expanded, assignments)
        if next_expanded == expanded:
            return expanded
        expanded = next_expanded
    return expanded


def _literal_printf_substitution_output(source: str) -> str | None:
    """Return a safe literal for simple `printf <literal>` substitutions.

    The hook is not a shell interpreter. This intentionally recognizes only the
    deterministic no-format shape that existing bypasses use, and leaves all
    other command substitutions untouched for the conservative dynamic checks.
    """
    try:
        tokens = shlex.split(source)
    except ValueError:
        return None
    if len(tokens) == 2 and _executable(tokens[0]) == "printf":
        return tokens[1]
    return None


def _expand_literal_command_substitutions(command: str) -> str:
    output: list[str] = []
    index = 0
    in_single = False
    in_double = False
    while index < len(command):
        char = command[index]
        if char == "\\":
            output.append(command[index : index + 2])
            index += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            output.append(char)
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            output.append(char)
            index += 1
            continue
        if in_single:
            output.append(char)
            index += 1
            continue
        if command.startswith("$(", index):
            end = command.find(")", index + 2)
            if end == -1:
                output.append(command[index:])
                break
            body = command[index + 2 : end]
            replacement = _literal_printf_substitution_output(body)
            output.append(replacement if replacement is not None else command[index : end + 1])
            index = end + 1
            continue
        if char == "`":
            end = command.find("`", index + 1)
            if end == -1:
                output.append(char)
                index += 1
                continue
            body = command[index + 1 : end]
            replacement = _literal_printf_substitution_output(body)
            output.append(replacement if replacement is not None else command[index : end + 1])
            index = end + 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _resolved_line_assignments(
    line_assignments: dict[str, str], assignments: dict[str, str]
) -> dict[str, str]:
    """Resolve assignment RHS values before persisting them across script lines."""
    resolved: dict[str, str] = {}
    for name, value in line_assignments.items():
        scope = {**assignments, **resolved}
        resolved[name] = _expand_shell_variables_fixed_point(value, scope)
    return resolved


def _resolved_command_assignments(command: str) -> dict[str, str]:
    """Resolve assignments in command order across top-level shell segments."""
    resolved: dict[str, str] = {}
    for part in _top_level_command_parts(command):
        line_assignments = _simple_assignments_from_part(part)
        resolved.update(_resolved_line_assignments(line_assignments, resolved))
    return resolved


def _find_command(value: Any) -> str | None:
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            return command
        nested = _find_command(value.get("tool_input"))
        if nested is not None:
            return nested
        for child in value.values():
            nested = _find_command(child)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _find_command(child)
            if nested is not None:
                return nested
    return None


def extract_command(raw: str) -> str:
    try:
        return _find_command(json.loads(raw)) or ""
    except (json.JSONDecodeError, TypeError):
        if raw.lstrip().startswith(("{", "[")):
            return MALFORMED_TOOL_INPUT_REASON
        return raw


def _executable(token: str) -> str:
    return PurePath(token).name.casefold()


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n<>")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments: list[list[str]] = [[]]
    for token in lexer:
        if token in CHAIN_TOKENS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _top_level_command_parts(command: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    index = 0
    in_single = False
    in_double = False
    in_backtick = False
    substitution_depth = 0
    while index < len(command):
        char = command[index]
        if char == "\\":
            current.append(command[index : index + 2])
            index += 2
            continue
        if not in_single and not in_backtick and command.startswith("$(", index):
            substitution_depth += 1
            current.append("$(")
            index += 2
            continue
        if substitution_depth:
            current.append(char)
            if char == ")" and not in_single and not in_double and not in_backtick:
                substitution_depth -= 1
            index += 1
            continue
        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            current.append(char)
            index += 1
            continue
        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            current.append(char)
            index += 1
            continue
        if char == "`" and not in_single:
            in_backtick = not in_backtick
            current.append(char)
            index += 1
            continue
        if not in_single and not in_double and not in_backtick and char in ";&|\n(){}":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _command_start(tokens: list[str]) -> int:
    index = 0
    while index < len(tokens):
        if tokens[index] in SHELL_CONTROL_PREFIXES:
            index += 1
            continue
        if "=" in tokens[index] and not tokens[index].startswith(("/", "./", "../")):
            index += 1
            continue
        break
    return index


def _consume_options(
    tokens: list[str],
    start: int,
    *,
    with_value: set[str],
) -> tuple[int, str | None]:
    index = start
    split_command: str | None = None
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1, split_command
        if not token.startswith("-") or token == "-":
            return index, split_command
        key = token.split("=", 1)[0]
        attached_short_value = False
        if "=" not in token:
            for option in with_value:
                if len(option) == 2 and token.startswith(option) and len(token) > 2:
                    key = option
                    attached_short_value = True
                    break
        index += 1
        if key in with_value and "=" not in token and attached_short_value:
            if key in {"-S", "--split-string"}:
                split_command = token[len(key):]
        elif key in with_value and "=" not in token:
            if index >= len(tokens):
                return index, split_command
            value = tokens[index]
            index += 1
            if key in {"-S", "--split-string"}:
                split_command = value
        elif key in {"-S", "--split-string"} and "=" in token:
            split_command = token.split("=", 1)[1]
    return index, split_command


def _unwrap_prefix(tokens: list[str]) -> list[str]:
    current = list(tokens)
    while current:
        executable = _executable(current[0])
        if executable == "sudo":
            index, _ = _consume_options(current, 1, with_value=SUDO_OPTIONS_WITH_VALUE)
            current = current[index:]
            continue
        if executable == "env":
            index, split_command = _consume_options(
                current, 1, with_value=ENV_OPTIONS_WITH_VALUE
            )
            while index < len(current) and "=" in current[index]:
                index += 1
            suffix = current[index:]
            current = (shlex.split(split_command) if split_command else []) + suffix
            continue
        break
    return current


def _git_subcommand(args: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        key = token.split("=", 1)[0]
        if key in GIT_GLOBAL_WITH_VALUE:
            index += 1 if "=" in token else 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        alias_tokens = _git_alias_tokens(args, token)
        if alias_tokens:
            return alias_tokens[0].casefold(), alias_tokens[1:] + args[index + 1 :]
        return token.casefold(), args[index + 1 :]
    if index < len(args):
        return args[index].casefold(), args[index + 1 :]
    return "", []


def _git_alias_tokens(args: list[str], subcommand: str) -> list[str] | None:
    alias_prefix = f"alias.{subcommand}="
    index = 0
    while index < len(args):
        token = args[index]
        key = token.split("=", 1)[0]
        value = ""
        if key in {"-c", "--config"}:
            if "=" in token and key != "-c":
                value = token.split("=", 1)[1]
            elif index + 1 < len(args):
                value = args[index + 1]
                index += 1
        if value.casefold().startswith(alias_prefix.casefold()):
            raw = value.split("=", 1)[1]
            try:
                alias_tokens = shlex.split(raw)
            except ValueError:
                return None
            if alias_tokens:
                return alias_tokens
        index += 1
    return None


def _git_reason(args: list[str]) -> str | None:
    config_reason = _git_config_reason(args)
    if config_reason:
        return config_reason
    subcommand, sub_args = _git_subcommand(args)
    if subcommand == "reset" and "--hard" in sub_args:
        return "git reset --hard"
    if subcommand == "clean":
        short_flags = "".join(
            token[1:]
            for token in sub_args
            if token.startswith("-") and not token.startswith("--")
        )
        forced = "f" in short_flags or "--force" in sub_args
        directories = "d" in short_flags or "--dirs" in sub_args
        dry_run = "n" in short_flags or "--dry-run" in sub_args
        if forced and directories and not dry_run:
            return "git clean with force and directory removal"
    if subcommand == "push":
        short_flags = "".join(
            token[1:]
            for token in sub_args
            if token.startswith("-") and not token.startswith("--")
        )
        forced = any(
            token == "-f"
            or "f" in short_flags
            or token == "--force"
            or token.startswith("--force=")
            or (token.startswith("+") and len(token) > 1)
            for token in sub_args
        )
        if forced:
            return "git force push"
        destructive_ref_update = any(
            token == "--mirror"
            or token.startswith("--mirror=")
            or "d" in short_flags
            or token == "--prune"
            or token.startswith("--prune=")
            or token == "--delete"
            or token.startswith("--delete=")
            or (token.startswith(":") and len(token) > 1)
            for token in sub_args
        )
        if destructive_ref_update:
            return "git destructive push"
    return None


def _find_reason(args: list[str]) -> str | None:
    for index, token in enumerate(args):
        if token == "-delete":
            return "find delete"
        if token in {"-exec", "-execdir"}:
            nested_tokens: list[str] = []
            for nested_token in args[index + 1 :]:
                if nested_token in {";", "+"}:
                    break
                nested_tokens.append(nested_token)
            if nested_tokens:
                nested = analyze_command(shlex.join(nested_tokens))
                if nested:
                    return f"find {token} with destructive command"
    return None


def _git_config_reason(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        key = token.split("=", 1)[0]
        value = ""
        if key in {"-c", "--config"}:
            if "=" in token and key != "-c":
                value = token.split("=", 1)[1]
            elif index + 1 < len(args):
                value = args[index + 1]
                index += 1
        if value:
            name, _, raw = value.partition("=")
            if name.casefold().startswith("alias.") and raw.startswith("!"):
                nested = analyze_command(raw[1:])
                if nested:
                    return "git shell alias with destructive command"
        index += 1
    return None


def _rm_reason(args: list[str]) -> str | None:
    short_flags = "".join(
        token[1:]
        for token in args
        if token.startswith("-") and not token.startswith("--")
    )
    recursive = "r" in short_flags or "R" in short_flags or "--recursive" in args
    forced = "f" in short_flags or "--force" in args
    dynamic_flag = any(
        token.startswith("-")
        and any(marker in token for marker in ("$", "`"))
        for token in args
    )
    if not (recursive or dynamic_flag):
        return None
    targets = [token for token in args if not token.startswith("-")]
    for target in targets:
        normalized = os.path.normpath(target)
        allowed_cache = normalized == ".next" or normalized.startswith(".next/")
        allowed_samvil_cache = normalized == ".samvil/cache" or normalized.startswith(
            ".samvil/cache/"
        )
        parent_escape = normalized == ".." or normalized.startswith("../")
        root_level_glob = "/" not in normalized and any(
            char in normalized for char in "*?[{"
        )
        shell_expansion = any(char in normalized for char in "*?[{")
        dangerous = (
            normalized in {"/", "~", ".", "*", ".git", ".samvil"}
            or parent_escape
            or root_level_glob
            or shell_expansion
            or normalized.startswith(".samvil/")
            or target.startswith("/")
            or target.startswith("~")
            or target.startswith("$")
            or "${" in target
        )
        if dangerous and not (allowed_cache or allowed_samvil_cache):
            if dynamic_flag and not (recursive and forced):
                return "dynamic removal flags with dangerous target"
            if forced:
                return "recursive forced removal"
            return "recursive removal with dangerous target"
    return None


def _sql_reason(executable: str, args: list[str]) -> str | None:
    if executable not in SQL_CLIENTS:
        return None
    if _has_destructive_sql(" ".join(args)):
        return "destructive SQL statement"
    file_reason = _sql_file_reason(args)
    if file_reason:
        return file_reason
    return None


def _read_inspectable_file(token: str, label: str) -> tuple[str | None, str | None]:
    if not token or token == "-":
        return None, None
    if any(char in token for char in UNINSPECTABLE_PATH_CHARS):
        return None, f"{label} file cannot be inspected"
    try:
        path = Path(token).expanduser()
    except RuntimeError:
        return None, f"{label} file cannot be inspected"
    if not path.exists():
        return None, None
    if not path.is_file():
        return None, f"{label} file cannot be inspected"
    try:
        if path.stat().st_size > FILE_INSPECTION_LIMIT_BYTES:
            return None, f"{label} file too large to inspect"
        with path.open("rb") as handle:
            raw = handle.read(FILE_INSPECTION_LIMIT_BYTES + 1)
    except OSError:
        return None, f"{label} file cannot be inspected"
    if len(raw) > FILE_INSPECTION_LIMIT_BYTES:
        return None, f"{label} file too large to inspect"
    return raw.decode("utf-8", errors="replace"), None


def _sql_file_reason(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        file_token: str | None = None
        if token == "<" and index + 1 < len(args):
            file_token = args[index + 1]
            index += 2
        elif token.startswith("<") and token != "<>" and len(token) > 1:
            file_token = token[1:]
            index += 1
        elif token in SQL_FILE_OPTIONS_WITH_VALUE and index + 1 < len(args):
            file_token = args[index + 1]
            index += 2
        elif token.startswith("--file="):
            file_token = token.split("=", 1)[1]
            index += 1
        elif token.startswith("-f") and token != "-f":
            file_token = token[2:]
            index += 1
        else:
            index += 1
        if not file_token:
            continue
        text, error = _read_inspectable_file(file_token, "SQL")
        if error:
            return error
        if text is not None and _has_destructive_sql(text):
            return "destructive SQL file"
    return None


def _has_destructive_sql(text: str) -> bool:
    text = re.sub(r"/\*![0-9]*\s*(.*?)\*/", r" \1 ", text, flags=re.DOTALL)
    without_block_comments = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    without_line_comments = re.sub(r"--[^\n]*(?:\n|$)", " ", without_block_comments)
    return bool(
        re.search(
            r"\b(?:"
            r"drop\s+(?:"
            r"table|database|schema|role|user|view|materialized\s+view|index|"
            r"sequence|function|procedure|trigger|type|policy|extension"
            r")"
            r"|truncate\s+table"
            r"|delete\s+from"
            r"|alter\s+table\b[^;]*\bdrop\s+(?:column|constraint)\b"
            r")\b",
            without_line_comments,
            re.IGNORECASE,
        )
    )


def _skip_options(args: list[str], *, with_value: set[str] | None = None) -> int:
    value_options = with_value or set()
    index = 0
    while index < len(args) and args[index].startswith("-"):
        token = args[index]
        key = token.split("=", 1)[0]
        index += 1
        if key in value_options and "=" not in token and index < len(args):
            index += 1
    return index


def _wrapped_tokens(executable: str, args: list[str]) -> list[str] | None:
    if executable in SIMPLE_WRAPPERS - {"exec"}:
        return args[_skip_options(args) :]
    if executable == "exec":
        return args[_skip_options(args, with_value=EXEC_OPTIONS_WITH_VALUE) :]
    if executable == "nice":
        index = _skip_options(args, with_value={"-n", "--adjustment"})
        return args[index:]
    if executable == "time":
        index = _skip_options(args, with_value={"-f", "-o", "--format", "--output"})
        return args[index:]
    if executable == "timeout":
        index = _skip_options(
            args,
            with_value={"-k", "--kill-after", "-s", "--signal"},
        )
        return args[index + 1 :] if index < len(args) else []
    if executable == "xargs":
        for index, token in enumerate(args):
            if _executable(token) in DETECTABLE_EXECUTABLES:
                return args[index:]
        return []
    return None


def _shell_command(args: list[str]) -> str | None:
    for index, token in enumerate(args):
        if token == "--":
            continue
        key = token.split("=", 1)[0]
        if key in SHELL_OPTIONS_WITH_VALUE:
            continue
        if token.startswith("--"):
            continue
        if token.startswith("-") and "c" in token[1:] and index + 1 < len(args):
            command_index = index + 1
            if args[command_index] == "--":
                command_index += 1
            if command_index < len(args):
                return args[command_index]
    return None


def _shell_script_file_reason(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        key = token.split("=", 1)[0]
        if key in SHELL_OPTIONS_WITH_VALUE:
            index += 1
            if "=" not in token and index < len(args):
                index += 1
            continue
        if token.startswith("--"):
            index += 1
            continue
        if token.startswith("-") and token != "-":
            if "c" in token[1:]:
                return None
            if token.startswith("-o") and token == "-o" and index + 1 < len(args):
                index += 2
                continue
            index += 1
            continue
        break
    if index >= len(args):
        return None
    script = args[index]
    try:
        script_key = str(Path(script).expanduser().resolve())
    except RuntimeError:
        script_key = script
    if script_key in _SCRIPT_INSPECTION_STACK:
        return None
    _SCRIPT_INSPECTION_STACK.append(script_key)
    try:
        text, error = _read_inspectable_file(script, "shell script")
        if error:
            return error
        if text is None:
            return None
        nested = _shell_script_text_reason(text)
        if nested:
            return "shell script file with destructive command"
        return None
    finally:
        _SCRIPT_INSPECTION_STACK.pop()


def _shell_script_text_reason(text: str) -> str | None:
    pending = ""
    assignments: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        line = pending + line
        pending = ""
        try:
            line_assignments = _simple_assignments(line)
            resolved_line_assignments = _resolved_line_assignments(
                line_assignments, assignments
            )
            effective_assignments = {**assignments, **resolved_line_assignments}
            expanded_line = _expand_shell_variables_fixed_point(
                line, effective_assignments
            )
            nested = analyze_command(expanded_line)
        except ValueError:
            continue
        if nested:
            return nested
        assignments.update(resolved_line_assignments)
    return None


def _shell_stdin_reason(args: list[str]) -> str | None:
    for index, token in enumerate(args):
        if token == "<<<" and index + 1 < len(args):
            nested = analyze_command(args[index + 1])
            if nested:
                return nested
        if token.startswith("<<"):
            return "shell stdin execution"
        if token == "<" or (token.startswith("<") and token != "<>"):
            return "shell stdin execution"
    return None


def _command_substitution_reason(command: str) -> str | None:
    index = 0
    in_single = False
    in_double = False
    while index < len(command):
        char = command[index]
        if char == "\\":
            index += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if in_single:
            index += 1
            continue
        if char == "`":
            end = index + 1
            while end < len(command):
                if command[end] == "\\":
                    end += 2
                    continue
                if command[end] == "`":
                    nested = analyze_command(command[index + 1 : end])
                    if nested:
                        return nested
                    index = end + 1
                    break
                end += 1
            else:
                index += 1
            continue
        if command.startswith("$(", index):
            depth = 1
            end = index + 2
            while end < len(command) and depth:
                if command[end] == "\\":
                    end += 2
                    continue
                if command[end] == "'" and not in_double:
                    quote_end = command.find("'", end + 1)
                    if quote_end == -1:
                        index = len(command)
                        break
                    end = quote_end + 1
                    continue
                if command[end] == '"' and not in_single:
                    in_double = not in_double
                elif command.startswith("$(", end):
                    depth += 1
                    end += 1
                elif command[end] == ")":
                    depth -= 1
                    if depth == 0:
                        nested = analyze_command(command[index + 2 : end])
                        if nested:
                            return nested
                        index = end + 1
                        break
                end += 1
            else:
                index += 1
            continue
        index += 1
    return None


def _command_substitution_executable_reason(command: str) -> str | None:
    """Conservatively block dynamic executables with destructive arguments."""
    for match in re.finditer(r"(?:\$\([^)]*\)|`[^`]*`)(?P<tail>(?:\s+[^;&|\n(){}]+)+)", command):
        try:
            tail_tokens = shlex.split(match.group("tail"))
        except ValueError:
            continue
        if _rm_reason(tail_tokens):
            return "dynamic executable with destructive removal arguments"
        if _git_reason(tail_tokens):
            return "dynamic executable with destructive git arguments"
    return None


def _dynamic_rm_flag_reason(command: str) -> str | None:
    for part in _top_level_command_parts(command):
        try:
            tokens = shlex.split(part)
        except ValueError:
            continue
        if not tokens:
            continue
        tokens = _unwrap_prefix(tokens)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        if executable != "rm":
            continue
        reason = _rm_reason(tokens[start + 1 :])
        if reason and reason.startswith("dynamic removal flags"):
            return reason
    return None


def analyze_command(command: str) -> str | None:
    command = _normalize_shell_source(command)
    if command == MALFORMED_TOOL_INPUT_REASON:
        return MALFORMED_TOOL_INPUT_REASON
    command = _expand_shell_variables_fixed_point(
        command, _resolved_command_assignments(command)
    )
    command = _expand_literal_command_substitutions(command)
    dynamic_rm_flag_reason = _dynamic_rm_flag_reason(command)
    if dynamic_rm_flag_reason:
        return dynamic_rm_flag_reason
    substitution_reason = _command_substitution_reason(command)
    if substitution_reason:
        return substitution_reason
    dynamic_substitution_reason = _command_substitution_executable_reason(command)
    if dynamic_substitution_reason:
        return dynamic_substitution_reason
    piped_sql_reason = _piped_sql_reason(command)
    if piped_sql_reason:
        return piped_sql_reason
    piped_shell_reason = _piped_shell_reason(command)
    if piped_shell_reason:
        return piped_shell_reason
    for tokens in _segments(command):
        tokens = _unwrap_prefix(tokens)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        args = tokens[start + 1 :]
        if any(char in executable for char in "`$*?[{"):
            if _rm_reason(args):
                return "dynamic executable with destructive removal arguments"
            if _git_reason(args):
                return "dynamic executable with destructive git arguments"
            if _find_reason(args):
                return "dynamic executable with destructive find arguments"
        if executable.startswith("$"):
            if _rm_reason(args):
                return "dynamic executable with destructive removal arguments"
            if _git_reason(args):
                return "dynamic executable with destructive git arguments"
            if _find_reason(args):
                return "dynamic executable with destructive find arguments"
            sql_reason = _sql_reason("psql", args)
            if sql_reason:
                return "dynamic executable with destructive SQL arguments"
        wrapped = _wrapped_tokens(executable, args)
        if wrapped:
            nested = analyze_command(shlex.join(wrapped))
            if nested:
                return nested
        if executable in SHELLS:
            shell_command = _shell_command(args)
            if shell_command:
                nested = analyze_command(shell_command)
                if nested:
                    return nested
            script_file_reason = _shell_script_file_reason(args)
            if script_file_reason:
                return script_file_reason
            stdin_reason = _shell_stdin_reason(args)
            if stdin_reason:
                return stdin_reason
        if executable == "eval" and args:
            nested_args = args[1:] if args and args[0] == "--" else args
            nested = analyze_command(" ".join(nested_args))
            if nested:
                return nested
        if executable == "git":
            reason = _git_reason(args)
        elif executable == "find":
            reason = _find_reason(args)
        elif executable == "rm":
            reason = _rm_reason(args)
        else:
            reason = _sql_reason(executable, args)
        if reason:
            return reason
    return None


def _piped_sql_reason(command: str) -> str | None:
    if "|" not in command and "<<" not in command:
        return None
    if not _has_destructive_sql(command):
        return None
    for tokens in _segments(command):
        if _segment_executable_is(tokens, SQL_CLIENTS):
            return "destructive SQL statement"
    return None


def _piped_shell_reason(command: str) -> str | None:
    if "|" not in command:
        return None
    for tokens in _segments(command):
        if _segment_executable_is(tokens, SHELLS):
            return "shell stdin execution"
    return None


def _embedded_shell_payload_reason(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for token in tokens:
        if token == command:
            continue
        nested = analyze_command(token)
        if nested:
            return nested
    return None


def _segment_executable_is(tokens: list[str], names: set[str]) -> bool:
    current = _unwrap_prefix(tokens)
    while current:
        start = _command_start(current)
        if start >= len(current):
            return False
        executable = _executable(current[start])
        args = current[start + 1:]
        if executable in names:
            return True
        wrapped = _wrapped_tokens(executable, args)
        if not wrapped:
            return False
        current = wrapped
    return False


def main() -> int:
    try:
        reason = analyze_command(extract_command(os.environ.get("TOOL_INPUT", "")))
    except ValueError:
        reason = SHELL_PARSE_ERROR_REASON
    if reason:
        print(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
