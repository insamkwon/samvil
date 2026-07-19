#!/usr/bin/env python3
"""Parse a Bash tool payload and report a destructive command reason."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import PurePath
from typing import Any


SQL_CLIENTS = {"mariadb", "mysql", "psql", "sqlite3", "sqlcmd"}
SHELLS = {"bash", "dash", "sh", "zsh"}
CHAIN_TOKENS = {";", "&&", "||", "|", "&", "\n", "(", ")", "{", "}"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup"}
DETECTABLE_EXECUTABLES = SQL_CLIENTS | SHELLS | {
    "git",
    "rm",
    "timeout",
    "nohup",
    "nice",
    "command",
    "exec",
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
        return raw


def _executable(token: str) -> str:
    return PurePath(token).name.casefold()


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n{}")
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


def _command_start(tokens: list[str]) -> int:
    index = 0
    while index < len(tokens):
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
        if key in with_value and "=" not in token and not attached_short_value:
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
        return token.casefold(), args[index + 1 :]
    if index < len(args):
        return args[index].casefold(), args[index + 1 :]
    return "", []


def _git_reason(args: list[str]) -> str | None:
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
        if forced and directories:
            return "git clean with force and directory removal"
    if subcommand == "push":
        forced = any(
            token == "-f"
            or token == "--force"
            or token.startswith("--force=")
            for token in sub_args
        )
        if forced:
            return "git force push"
    return None


def _rm_reason(args: list[str]) -> str | None:
    short_flags = "".join(
        token[1:]
        for token in args
        if token.startswith("-") and not token.startswith("--")
    )
    recursive = "r" in short_flags or "R" in short_flags or "--recursive" in args
    forced = "f" in short_flags or "--force" in args
    if not (recursive and forced):
        return None
    targets = [token for token in args if not token.startswith("-")]
    for target in targets:
        normalized = os.path.normpath(target)
        allowed_cache = normalized == ".next" or normalized.startswith(".next/")
        allowed_state = normalized == ".samvil" or normalized.startswith(".samvil/")
        parent_escape = normalized == ".." or normalized.startswith("../")
        dangerous = (
            normalized in {"/", "~", ".", "*"}
            or parent_escape
            or target.startswith("/")
            or target.startswith("~")
            or target.startswith("$")
            or "${" in target
        )
        if dangerous and not (allowed_cache or allowed_state):
            return f"recursive forced removal of {target}"
    return None


def _sql_reason(executable: str, args: list[str]) -> str | None:
    if executable not in SQL_CLIENTS:
        return None
    if re.search(r"\bdrop\s+(?:table|database)\b", " ".join(args), re.IGNORECASE):
        return "destructive SQL statement"
    return None


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
    if executable in SIMPLE_WRAPPERS:
        return args[_skip_options(args) :]
    if executable == "nice":
        index = _skip_options(args, with_value={"-n", "--adjustment"})
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
        if token.startswith("-") and "c" in token[1:] and index + 1 < len(args):
            return args[index + 1]
    return None


def analyze_command(command: str) -> str | None:
    for tokens in _segments(command):
        tokens = _unwrap_prefix(tokens)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        args = tokens[start + 1 :]
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
        if executable == "git":
            reason = _git_reason(args)
        elif executable == "rm":
            reason = _rm_reason(args)
        else:
            reason = _sql_reason(executable, args)
        if reason:
            return reason
    return None


def main() -> int:
    reason = analyze_command(extract_command(os.environ.get("TOOL_INPUT", "")))
    if reason:
        print(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
