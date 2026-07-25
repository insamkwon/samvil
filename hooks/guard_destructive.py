#!/usr/bin/env python3
"""Parse a Bash tool payload and report a destructive command reason."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
from contextvars import ContextVar
from pathlib import Path, PurePath
from typing import Any


MALFORMED_TOOL_INPUT_REASON = "malformed tool input"
SHELL_PARSE_ERROR_REASON = "shell parse error"
FILE_INSPECTION_LIMIT_BYTES = 1_000_000
MAX_ANALYSIS_DEPTH = 64
NESTED_ANALYSIS_LIMIT_REASON = "nested command depth exceeds inspection limit"
SQL_CLIENTS = {"mariadb", "mysql", "psql", "sqlite3", "sqlcmd"}
SHELLS = {"bash", "dash", "sh", "zsh"}
SOURCE_BUILTINS = {".", "source"}
PROTECTED_ROOT_SSOT_PATHS = {
    "interview-summary.md",
    "project.config.json",
    "project.seed.json",
    "project.state.json",
}
PROTECTED_SAMVIL_SSOT_PATHS = {
    ".samvil/claims.jsonl",
    ".samvil/events.jsonl",
    ".samvil/handoff.md",
    ".samvil/next-skill.json",
    ".samvil/project.seed.json",
    ".samvil/project.state.json",
    ".samvil/qa-results.json",
}
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
    "cp",
    "eval",
    "find",
    "git",
    "install",
    "ln",
    "mv",
    "perl",
    "rm",
    "rsync",
    "sed",
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
SQL_COMMAND_OPTIONS_WITH_VALUE = {
    "-c",
    "-e",
    "-q",
    "-Q",
    "--command",
    "--execute",
}
SAMVIL_EVENT_STORE_SUFFIX = "/.samvil/samvil.db"
SAMVIL_EVENT_STORE_RELATIVE = ".samvil/samvil.db"
SQL_WRITE_STATEMENT = re.compile(
    r"\b(?:ALTER|ATTACH|CREATE|DELETE|DETACH|DROP|INSERT|REINDEX|REPLACE|"
    r"UPDATE|VACUUM)\b",
    re.IGNORECASE,
)
INLINE_LANGUAGE_RUNTIME_OPTIONS = {
    "node": {"-e", "--eval"},
    "perl": {"-e"},
    "php": {"-r"},
    "python": {"-c"},
    "ruby": {"-e"},
}
INLINE_LANGUAGE_MUTATION = re.compile(
    r"(?:\bFile\.write\b|\b(?:copy|copy2|copyfile|createWriteStream|delete|file_put_contents|"
    r"fopen|remove|rename|replace|rmSync|rmtree|"
    r"move|symlink|symlink_to|truncate|truncateSync|unlink|unlinkSync|write_bytes|write_text|"
    r"writeFile|writeFileSync)\b)",
    re.IGNORECASE,
)
INLINE_LANGUAGE_COMMAND_EXECUTION = re.compile(
    r"\b(?:call|check_call|check_output|exec|execSync|popen|Popen|run|spawn|"
    r"spawnSync|system)\b",
    re.IGNORECASE,
)
INLINE_LANGUAGE_WRITE_OPEN = re.compile(
    r"\bopen\b[^\r\n]*(?:['\"](?:w|a|x|>|>>|\+>)[^'\"]*['\"])",
    re.IGNORECASE,
)
UNINSPECTABLE_PATH_CHARS = "`$*?[{"
_SCRIPT_INSPECTION_STACK: list[str] = []
_ANALYSIS_DEPTH: ContextVar[int] = ContextVar("guard_analysis_depth", default=0)


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
    if token == ".":
        return "."
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


def _normalized_rm_target(target: str) -> str:
    for prefix in ("$PWD/", "${PWD}/"):
        if target.startswith(prefix):
            target = target[len(prefix) :]
            break
    normalized = os.path.normpath(target)
    path = Path(normalized).expanduser()
    if path.is_absolute():
        try:
            normalized = str(path.resolve(strict=False).relative_to(Path.cwd().resolve()))
        except ValueError:
            pass
    return normalized


def _is_protected_ssot_target(target: str) -> bool:
    normalized = _normalized_rm_target(target)
    return (
        normalized == ".samvil"
        or normalized in PROTECTED_ROOT_SSOT_PATHS
        or normalized in PROTECTED_SAMVIL_SSOT_PATHS
    )


def _is_samvil_event_store_target(target: str) -> bool:
    """Recognize the canonical EventStore through URI, home, or symlink aliases."""
    normalized = target.replace("\\", "/")
    if normalized.startswith("file:"):
        normalized = normalized.removeprefix("file:").split("?", 1)[0]
    candidates = {normalized}
    try:
        path = Path(normalized).expanduser()
        candidates.add(str(path).replace("\\", "/"))
        candidates.add(str(path.resolve(strict=False)).replace("\\", "/"))
    except (OSError, RuntimeError):
        pass
    return any(
        candidate == SAMVIL_EVENT_STORE_RELATIVE
        or candidate.endswith(SAMVIL_EVENT_STORE_SUFFIX)
        for candidate in candidates
    )


def _protected_mutation_reason(target: str) -> str | None:
    if _is_samvil_event_store_target(target):
        return "protected SAMVIL EventStore overwrite"
    if _is_protected_ssot_target(target):
        return "protected SAMVIL SSOT overwrite"
    return None


def _literal_path_key(target: str) -> str | None:
    if any(marker in target for marker in UNINSPECTABLE_PATH_CHARS):
        return None
    normalized = target
    if normalized.startswith("file:"):
        normalized = normalized.removeprefix("file:").split("?", 1)[0]
    try:
        return str(Path(normalized).expanduser().resolve(strict=False))
    except (OSError, RuntimeError):
        return None


def _ln_is_symbolic(args: list[str]) -> bool:
    return any(
        token == "--symbolic"
        or (
            token.startswith("-")
            and not token.startswith("--")
            and "s" in token[1:]
        )
        for token in args
    )


def _literal_link_sources(args: list[str]) -> list[str]:
    target_directory: str | None = None
    operands: list[str] = []
    literal_operands = False
    index = 0
    while index < len(args):
        token = args[index]
        if literal_operands:
            operands.append(token)
        elif token == "--":
            literal_operands = True
        elif token in {"-t", "--target-directory"} and index + 1 < len(args):
            target_directory = args[index + 1]
            index += 1
        elif token.startswith("--target-directory="):
            target_directory = token.split("=", 1)[1]
        elif token.startswith("-t") and len(token) > 2:
            target_directory = token[2:]
        elif token in {"-S", "--suffix"}:
            index += 1
        elif not token.startswith("-") or token == "-":
            operands.append(token)
        index += 1
    if target_directory is not None:
        return operands
    return operands[:-1] if len(operands) >= 2 else []


def _register_literal_symlink_alias(
    executable: str,
    args: list[str],
    aliases: dict[str, str],
    alias_literals: dict[str, str],
    known_directories: set[str],
) -> bool:
    if executable != "ln" or not _ln_is_symbolic(args):
        return False
    target_directory: str | None = None
    operands: list[str] = []
    literal_operands = False
    index = 0
    while index < len(args):
        token = args[index]
        if literal_operands:
            operands.append(token)
        elif token == "--":
            literal_operands = True
        elif token in {"-t", "--target-directory"} and index + 1 < len(args):
            target_directory = args[index + 1]
            index += 1
        elif token.startswith("--target-directory="):
            target_directory = token.split("=", 1)[1]
        elif token.startswith("-t") and len(token) > 2:
            target_directory = token[2:]
        elif token == "-S" or token == "--suffix":
            index += 1
        elif not token.startswith("-") or token == "-":
            operands.append(token)
        index += 1
    if target_directory is None and len(operands) < 2:
        return True
    if target_directory is not None and not operands:
        return True
    if target_directory is None:
        sources = operands[:-1]
        destination = operands[-1]
    else:
        sources = operands
        destination = target_directory
    destination_key = _literal_path_key(destination)
    destination_is_directory = destination_key in known_directories
    try:
        destination_is_directory = (
            destination_is_directory or Path(destination).expanduser().is_dir()
        )
    except (OSError, RuntimeError):
        pass
    for source in sources:
        source_key = _literal_path_key(source)
        protected_source = aliases.get(source_key or "", source)
        if not (
            _is_samvil_event_store_target(protected_source)
            or _is_protected_ssot_target(protected_source)
        ):
            continue
        alias = (
            str(PurePath(destination) / PurePath(source).name)
            if destination_is_directory
            else destination
        )
        alias_key = _literal_path_key(alias)
        if alias_key:
            aliases[alias_key] = protected_source
            spellings = {alias, alias_key}
            if not Path(alias).is_absolute() and not alias.startswith("./"):
                spellings.add(f"./{alias}")
            for spelling in spellings:
                alias_literals[spelling] = protected_source
    return True


def _register_literal_directory_creation(
    executable: str,
    args: list[str],
    known_directories: set[str],
) -> bool:
    if executable != "mkdir":
        return False
    literal_operands = False
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if not literal_operands and token == "--":
            literal_operands = True
            continue
        if not literal_operands and token in {"-m", "--mode", "-Z", "--context"}:
            skip_next = True
            continue
        if not literal_operands and token.startswith("-"):
            continue
        directory_key = _literal_path_key(token)
        if directory_key:
            known_directories.add(directory_key)
    return True


def _register_literal_directory_removal(
    executable: str,
    args: list[str],
    known_directories: set[str],
) -> bool:
    if executable != "rmdir":
        return False
    for token in args:
        if token.startswith("-") and token != "-":
            continue
        directory_key = _literal_path_key(token)
        if directory_key:
            known_directories.discard(directory_key)
    return True


def _nested_alias_commands(executable: str, args: list[str]) -> list[str]:
    if executable in SHELLS:
        invocation = _shell_command_invocation(args)
        if invocation:
            shell_command, argv0, positional = invocation
            expanded, unresolved = _expand_shell_positional_parameters(
                shell_command,
                argv0=argv0,
                positional=positional,
            )
            return [] if unresolved else [expanded]
    if executable == "eval" and args:
        nested_args = args[1:] if args[0] == "--" else args
        return [" ".join(nested_args)]
    return []


def _collect_literal_symlink_aliases(
    command: str,
    aliases: dict[str, str],
    alias_literals: dict[str, str],
    known_directories: set[str],
    *,
    depth: int = 0,
) -> None:
    if depth >= MAX_ANALYSIS_DEPTH:
        return
    for segment in _segments(command):
        tokens = _unwrap_prefix(segment)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        args = tokens[start + 1 :]
        if _register_literal_directory_removal(
            executable,
            args,
            known_directories,
        ):
            continue
        if _register_literal_directory_creation(
            executable,
            args,
            known_directories,
        ):
            continue
        if _register_literal_symlink_alias(
            executable,
            args,
            aliases,
            alias_literals,
            known_directories,
        ):
            continue
        for nested in _nested_alias_commands(executable, args):
            _collect_literal_symlink_aliases(
                nested,
                aliases,
                alias_literals,
                known_directories,
                depth=depth + 1,
            )


def _rewrite_chained_alias_token(
    token: str,
    aliases: dict[str, str],
    alias_literals: dict[str, str],
) -> tuple[str, bool]:
    alias_target = aliases.get(_literal_path_key(token) or "")
    if alias_target is not None:
        return alias_target, True
    try:
        nested_tokens = shlex.split(token)
    except ValueError:
        nested_tokens = []
    nested_changed = False
    for index, nested_token in enumerate(nested_tokens):
        nested_target = aliases.get(_literal_path_key(nested_token) or "")
        if nested_target is not None:
            nested_tokens[index] = nested_target
            nested_changed = True
    if nested_changed:
        token = shlex.join(nested_tokens)
    changed = nested_changed
    for alias_literal, protected_source in sorted(
        alias_literals.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        pattern = (
            rf"(?<![A-Za-z0-9_./~-]){re.escape(alias_literal)}"
            r"(?![A-Za-z0-9_./~-])"
        )
        token, replacements = re.subn(pattern, protected_source, token)
        changed = changed or bool(replacements)
    return token, changed


def _chained_protected_alias_reason(command: str) -> str | None:
    """Track literal symlinks created earlier in the same shell command."""
    aliases: dict[str, str] = {}
    alias_literals: dict[str, str] = {}
    known_directories: set[str] = set()
    for segment in _segments(command):
        tokens = _unwrap_prefix(segment)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        args = tokens[start + 1 :]
        if _register_literal_directory_removal(
            executable,
            args,
            known_directories,
        ):
            continue
        if _register_literal_directory_creation(
            executable,
            args,
            known_directories,
        ):
            continue
        if _register_literal_symlink_alias(
            executable,
            args,
            aliases,
            alias_literals,
            known_directories,
        ):
            continue
        if aliases:
            rewritten = list(tokens[start:])
            changed = False
            for index, command_token in enumerate(rewritten):
                rewritten[index], token_changed = _rewrite_chained_alias_token(
                    command_token,
                    aliases,
                    alias_literals,
                )
                changed = changed or token_changed
            if changed:
                reason = analyze_command(shlex.join(rewritten))
                if reason:
                    return reason
        for nested in _nested_alias_commands(executable, args):
            _collect_literal_symlink_aliases(
                nested,
                aliases,
                alias_literals,
                known_directories,
            )
    return None


def _copy_like_mutation_targets(args: list[str]) -> list[str]:
    """Expand copy-style destination directories into their final file targets."""
    target_directory: str | None = None
    operands: list[str] = []
    literal_operands = False
    index = 0
    while index < len(args):
        token = args[index]
        if literal_operands:
            operands.append(token)
        elif token == "--":
            literal_operands = True
        elif token in {"-t", "--target-directory"} and index + 1 < len(args):
            target_directory = args[index + 1]
            index += 1
        elif token.startswith("--target-directory="):
            target_directory = token.split("=", 1)[1]
        elif token.startswith("-t") and len(token) > 2:
            target_directory = token[2:]
        elif not token.startswith("-") or token == "-":
            operands.append(token)
        index += 1

    if target_directory is None:
        if len(operands) < 2:
            return []
        sources = operands[:-1]
        destination = operands[-1]
    else:
        if not operands:
            return []
        sources = operands
        destination = target_directory

    targets = [destination]
    targets.extend(
        str(PurePath(destination) / PurePath(source).name)
        for source in sources
        if PurePath(source).name
    )
    return targets


def _brace_expansion_candidates(target: str, *, limit: int = 32) -> list[str] | None:
    candidates = [target]
    while len(candidates) < limit:
        expanded = False
        next_candidates: list[str] = []
        for candidate in candidates:
            match = re.search(r"\{([^{}]+)\}", candidate)
            if not match or "," not in match.group(1):
                next_candidates.append(candidate)
                continue
            expanded = True
            for choice in match.group(1).split(","):
                if len(next_candidates) >= limit:
                    return None
                next_candidates.append(
                    candidate[: match.start()] + choice + candidate[match.end() :]
                )
        candidates = next_candidates
        if not expanded:
            break
    if any(re.search(r"\{[^{}]*,[^{}]*\}", candidate) for candidate in candidates):
        return None
    return candidates


def _rm_target_may_expand_to_protected_ssot(target: str) -> bool:
    normalized = _normalized_rm_target(target)
    allowed_cache = normalized == ".next" or normalized.startswith(".next/")
    allowed_samvil_cache = normalized == ".samvil/cache" or normalized.startswith(
        ".samvil/cache/"
    )
    if allowed_cache or allowed_samvil_cache:
        return False
    if any(marker in target for marker in ("$", "`")):
        return True
    protected = PROTECTED_ROOT_SSOT_PATHS | PROTECTED_SAMVIL_SSOT_PATHS | {
        ".samvil"
    }
    candidates = _brace_expansion_candidates(normalized)
    if candidates is None:
        return True
    for candidate in candidates:
        if candidate in protected:
            return True
        if any(marker in candidate for marker in "*?[") and any(
            fnmatch.fnmatchcase(path, candidate) for path in protected
        ):
            return True
    return False


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
    targets = [token for token in args if not token.startswith("-")]
    if any(_is_samvil_event_store_target(target) for target in targets):
        return "protected SAMVIL EventStore removal"
    if any(_is_protected_ssot_target(target) for target in targets):
        return "protected SAMVIL SSOT removal"
    if any(_rm_target_may_expand_to_protected_ssot(target) for target in targets):
        return "dynamic removal target may match protected SAMVIL SSOT"
    if not (recursive or dynamic_flag):
        return None
    for target in targets:
        normalized = _normalized_rm_target(target)
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
            or normalized in PROTECTED_ROOT_SSOT_PATHS
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


def _perl_option_enables_in_place_edit(token: str) -> bool:
    """Parse Perl short-option clusters without scanning option arguments."""
    if token == "-i":
        return True
    if not token.startswith("-") or token.startswith("--"):
        return False
    cluster = token[1:]
    index = 0
    while index < len(cluster):
        option = cluster[index]
        index += 1
        if option == "i":
            return True
        if option == "0":
            if index < len(cluster) and cluster[index] in {"x", "X"}:
                index += 1
                while (
                    index < len(cluster)
                    and cluster[index] in "0123456789abcdefABCDEF"
                ):
                    index += 1
            else:
                digits = 0
                while (
                    index < len(cluster)
                    and digits < 3
                    and cluster[index] in "01234567"
                ):
                    index += 1
                    digits += 1
            continue
        if option == "l":
            while index < len(cluster) and cluster[index] in "01234567":
                index += 1
            continue
        if option == "d":
            remainder = cluster[index:]
            if remainder.startswith("i"):
                return False
            if remainder.startswith(":"):
                return False
            if remainder.startswith("t"):
                index += 1
                if index < len(cluster) and cluster[index] == ":":
                    return False
            continue
        if option == "V":
            if index < len(cluster) and cluster[index] == ":":
                return False
            continue
        if option in "acflnpsStTuUvwWX":
            continue
        if option in {"C", "D", "e", "E", "F", "I", "m", "M", "x"}:
            return False
        return False
    return False


def _protected_overwrite_reason(executable: str, args: list[str]) -> str | None:
    if executable in {">", ">>", ">|", "<>", "&>", "&>>"} and args:
        reason = _protected_mutation_reason(args[0])
        if reason:
            return reason

    for index, token in enumerate(args[:-1]):
        if token in {">", ">>", ">|", "<>", "&>", "&>>"}:
            reason = _protected_mutation_reason(args[index + 1])
            if reason:
                return reason

    if executable == "truncate":
        for token in args:
            if not token.startswith("-"):
                reason = _protected_mutation_reason(token)
                if reason:
                    return reason

    hard_link_sources: list[str] = []
    if executable == "ln" and not _ln_is_symbolic(args):
        hard_link_sources = _literal_link_sources(args)
    elif executable == "link" and len(args) >= 2:
        hard_link_sources = args[:-1]
    elif executable == "cp" and any(
        token == "--link"
        or (
            token.startswith("-")
            and not token.startswith("--")
            and "l" in token[1:]
        )
        for token in args
    ):
        hard_link_sources = _literal_link_sources(args)
    for source in hard_link_sources:
        if _is_samvil_event_store_target(source):
            return "protected SAMVIL EventStore hard link"
        if _is_protected_ssot_target(source):
            return "protected SAMVIL SSOT hard link"

    if executable in {"cp", "install", "ln", "mv", "rsync"} and len(args) >= 2:
        for target in _copy_like_mutation_targets(args):
            reason = _protected_mutation_reason(target)
            if reason:
                return reason

    if executable == "perl" and any(
        _perl_option_enables_in_place_edit(token) for token in args
    ):
        for token in args:
            reason = _protected_mutation_reason(token)
            if reason:
                return reason

    if executable == "sed" and any(
        token == "-i"
        or token.startswith("-i")
        or token == "--in-place"
        or token.startswith("--in-place=")
        for token in args
    ):
        for token in args:
            reason = _protected_mutation_reason(token)
            if reason:
                return reason

    if executable == "tee":
        for token in args:
            if not token.startswith("-"):
                reason = _protected_mutation_reason(token)
                if reason:
                    return reason

    if executable == "dd":
        options = dict(token.split("=", 1) for token in args if "=" in token)
        reason = _protected_mutation_reason(options.get("of", ""))
        if reason:
            return reason
    return None


def _inline_language_runtime_reason(
    executable: str,
    args: list[str],
    *,
    command_context: str = "",
) -> str | None:
    runtime = re.sub(r"(?:\d+(?:\.\d+)*)$", "", executable.casefold())
    options = INLINE_LANGUAGE_RUNTIME_OPTIONS.get(runtime)
    if not options:
        return None

    payloads: list[str] = []
    for index, arg in enumerate(args):
        if arg in options and index + 1 < len(args):
            payloads.append(args[index + 1])
            continue
        for option in options:
            if arg.startswith(option) and len(arg) > len(option):
                payloads.append(arg[len(option) :])
                break

    for payload in payloads:
        if _language_runtime_event_store_mutates(payload, command_context):
            return "direct SAMVIL EventStore mutation"
        if _language_runtime_payload_mutates(payload, command_context):
            return "inline language runtime may mutate protected SAMVIL SSOT"
    return None


def _language_runtime_payload_mutates(payload: str, command_context: str = "") -> bool:
    normalized = payload.replace("\\", "/")
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = re.sub(r"(['\"])\s*\+\s*\1", "", normalized)

    if INLINE_LANGUAGE_COMMAND_EXECUTION.search(normalized):
        literals = [
            match.group(2)
            for match in re.finditer(r"(['\"])(.*?)(?<!\\)\1", normalized)
        ]
        command_candidates = literals + ([shlex.join(literals)] if literals else [])
        if any(analyze_command(candidate) for candidate in command_candidates):
            return True

    protected_paths = PROTECTED_ROOT_SSOT_PATHS | PROTECTED_SAMVIL_SSOT_PATHS | {
        ".samvil",
        SAMVIL_EVENT_STORE_RELATIVE,
    }
    normalized_context = command_context.replace("\\", "/")
    protected_context = f"{normalized}\n{normalized_context}"
    if not any(path in protected_context for path in protected_paths):
        return False
    return bool(
        INLINE_LANGUAGE_MUTATION.search(normalized)
        or INLINE_LANGUAGE_WRITE_OPEN.search(normalized)
    )


def _language_runtime_event_store_mutates(
    payload: str,
    command_context: str = "",
) -> bool:
    normalized = payload.replace("\\", "/")
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = re.sub(r"(['\"])\s*\+\s*\1", "", normalized)
    normalized_context = command_context.replace("\\", "/")
    literals = [
        match.group(2)
        for match in re.finditer(r"(['\"])(.*?)(?<!\\)\1", normalized)
    ]
    path_context = "\n".join(
        (normalized, normalized_context, "/".join(literals))
    )
    if re.search(r"\bsave_event_and_update_stage\s*\(", normalized):
        return True
    event_store_reference = bool(
        SAMVIL_EVENT_STORE_RELATIVE in path_context
        or re.search(r"\b(?:DB_PATH|get_store)\b", normalized)
    )
    return bool(
        event_store_reference
        and SQL_WRITE_STATEMENT.search(f"{normalized}\n{normalized_context}")
    )


def _language_runtime_script_file_reason(
    executable: str,
    args: list[str],
    command_context: str,
) -> str | None:
    runtime = re.sub(r"(?:\d+(?:\.\d+)*)$", "", executable.casefold())
    inline_options = INLINE_LANGUAGE_RUNTIME_OPTIONS.get(runtime)
    if not inline_options:
        return None
    if any(
        arg in inline_options
        or any(arg.startswith(option) and len(arg) > len(option) for option in inline_options)
        for arg in args
    ):
        return None

    script: str | None = None
    after_options = False
    for arg in args:
        if arg == "--":
            after_options = True
            continue
        if arg == "-":
            return None
        if not after_options and arg.startswith("-"):
            continue
        script = arg
        break
    if script is None:
        return None

    try:
        script_key = str(Path(script).expanduser().resolve())
    except RuntimeError:
        script_key = script
    if script_key in _SCRIPT_INSPECTION_STACK:
        return None
    _SCRIPT_INSPECTION_STACK.append(script_key)
    try:
        text, error = _read_inspectable_file(script, "language runtime script")
        if error:
            return error
        if text is None:
            return None
        if _language_runtime_event_store_mutates(text, command_context):
            return "direct SAMVIL EventStore mutation"
        if _language_runtime_payload_mutates(text, command_context):
            return "language runtime script file with protected SSOT mutation"
        return None
    finally:
        _SCRIPT_INSPECTION_STACK.pop()


def _language_runtime_heredoc_reason(command: str) -> str | None:
    header, separator, remainder = command.partition("\n")
    if not separator:
        return None
    marker = re.search(
        r"<<(?P<strip>-?)\s*(?P<quote>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)"
        r"(?P=quote)",
        header,
    )
    if marker is None:
        return None
    try:
        tokens = shlex.split(header[: marker.start()])
    except ValueError:
        return None
    tokens = _unwrap_prefix(tokens)
    start = _command_start(tokens)
    if start >= len(tokens):
        return None
    executable = _executable(tokens[start])
    runtime = re.sub(r"(?:\d+(?:\.\d+)*)$", "", executable.casefold())
    if runtime not in INLINE_LANGUAGE_RUNTIME_OPTIONS:
        return None

    tag = marker.group("tag")
    indentation = r"[\t]*" if marker.group("strip") else ""
    terminator = re.compile(rf"(?m)^{indentation}{re.escape(tag)}[ \t]*$")
    end = terminator.search(remainder)
    if end is None:
        return "language runtime stdin cannot be inspected"
    payload = remainder[: end.start()]
    if _language_runtime_event_store_mutates(payload, header):
        return "direct SAMVIL EventStore mutation"
    if _language_runtime_payload_mutates(payload, header):
        return "language runtime may mutate protected SAMVIL SSOT"
    return None


def _language_runtime_stdin_payload_reason(
    payload: str,
    command_context: str,
) -> str | None:
    if _language_runtime_event_store_mutates(payload, command_context):
        return "direct SAMVIL EventStore mutation"
    if _language_runtime_payload_mutates(payload, command_context):
        return "language runtime may mutate protected SAMVIL SSOT"
    return None


def _language_runtime_argument_stdin_reason(
    executable: str,
    args: list[str],
    command_context: str,
) -> str | None:
    runtime = re.sub(r"(?:\d+(?:\.\d+)*)$", "", executable.casefold())
    if runtime not in INLINE_LANGUAGE_RUNTIME_OPTIONS:
        return None
    for index, token in enumerate(args):
        if token == "<<<" and index + 1 < len(args):
            return _language_runtime_stdin_payload_reason(
                args[index + 1],
                command_context,
            )
        if token.startswith("<<<") and len(token) > 3:
            return _language_runtime_stdin_payload_reason(
                token[3:],
                command_context,
            )
        if token == "<" and index + 1 < len(args):
            text, error = _read_inspectable_file(
                args[index + 1],
                "language runtime stdin",
            )
            if error:
                return error
            if text is not None:
                return _language_runtime_stdin_payload_reason(
                    text,
                    command_context,
                )
    return None


def _piped_language_runtime_reason(command: str) -> str | None:
    if re.search(r"(?<!\|)\|(?!\|)", command) is None:
        return None
    segments = _segments(command)
    for index in range(1, len(segments)):
        runtime_tokens = _unwrap_prefix(segments[index])
        start = _command_start(runtime_tokens)
        if start >= len(runtime_tokens):
            continue
        executable = _executable(runtime_tokens[start])
        runtime = re.sub(r"(?:\d+(?:\.\d+)*)$", "", executable.casefold())
        if runtime not in INLINE_LANGUAGE_RUNTIME_OPTIONS:
            continue
        runtime_args = runtime_tokens[start + 1 :]
        if runtime_args and "-" not in runtime_args:
            continue

        producer_tokens = _unwrap_prefix(segments[index - 1])
        producer_start = _command_start(producer_tokens)
        if producer_start >= len(producer_tokens):
            return "language runtime stdin cannot be inspected"
        producer = _executable(producer_tokens[producer_start])
        producer_args = producer_tokens[producer_start + 1 :]
        if producer in {"echo", "printf"}:
            payload = " ".join(producer_args)
        elif producer == "cat" and producer_args:
            chunks: list[str] = []
            for source in producer_args:
                if source.startswith("-"):
                    continue
                text, error = _read_inspectable_file(
                    source,
                    "language runtime stdin",
                )
                if error:
                    return error
                if text is not None:
                    chunks.append(text)
            if not chunks:
                return "language runtime stdin cannot be inspected"
            payload = "\n".join(chunks)
        else:
            return "language runtime stdin cannot be inspected"
        reason = _language_runtime_stdin_payload_reason(payload, command)
        if reason:
            return reason
    return None


def _sql_reason(executable: str, args: list[str]) -> str | None:
    if executable not in SQL_CLIENTS:
        return None
    if executable == "sqlite3" and _direct_samvil_event_store_reason(args):
        return "direct SAMVIL EventStore mutation"
    payloads = _sql_command_payloads(args) or [" ".join(args)]
    for payload in payloads:
        meta_reason = _sql_meta_shell_reason(payload)
        if meta_reason:
            return meta_reason
        if _has_dynamic_destructive_sql(payload) or _has_destructive_sql(payload):
            return "destructive SQL statement"
    file_reason = _sql_file_reason(args)
    if file_reason:
        return file_reason
    return None


def _direct_samvil_event_store_reason(args: list[str]) -> bool:
    database_index: int | None = None
    for index, token in enumerate(args):
        if _is_samvil_event_store_target(token):
            database_index = index
            break
    if database_index is None:
        return False
    statement = " ".join(args[database_index + 1 :]).strip()
    if not statement:
        return True
    if SQL_WRITE_STATEMENT.search(statement):
        return True
    return (
        re.match(
            r"^(?:SELECT\b|EXPLAIN\s+(?:QUERY\s+PLAN\s+)?SELECT\b)",
            statement,
            re.IGNORECASE,
        )
        is None
    )


def _sql_command_payloads(args: list[str]) -> list[str]:
    payloads: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        key = token.split("=", 1)[0]
        if key in SQL_COMMAND_OPTIONS_WITH_VALUE:
            if "=" in token:
                payloads.append(token.split("=", 1)[1])
                index += 1
                continue
            if len(token) > 2 and key in {"-c", "-e", "-q", "-Q"}:
                payloads.append(token[2:])
                index += 1
                continue
            if index + 1 < len(args):
                payloads.append(args[index + 1])
                index += 2
                continue
        index += 1
    return payloads


def _sql_meta_shell_reason(text: str) -> str | None:
    for raw_line in text.splitlines() or [text]:
        line = raw_line.lstrip()
        if not line.startswith(r"\!"):
            continue
        nested = analyze_command(line[2:].lstrip())
        if nested:
            return "SQL client shell command with destructive command"
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
        if text is not None:
            reason = _sql_text_reason(text, base_dir=Path(file_token).expanduser().parent)
            if reason:
                return reason
    return None


def _sql_text_reason(
    text: str,
    *,
    base_dir: Path | None = None,
    seen: set[str] | None = None,
) -> str | None:
    if _has_destructive_sql(text):
        return "destructive SQL file"
    include_reason = _sql_include_reason(text, base_dir=base_dir, seen=seen or set())
    if include_reason:
        return include_reason
    return None


def _sql_include_reason(
    text: str,
    *,
    base_dir: Path | None,
    seen: set[str],
) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip().rstrip(";").strip()
        if not line or line.startswith(("--", "#")):
            continue
        match = re.match(r"^(?:\\i|\\include|\\\.|source)\s+(.+)$", line, re.IGNORECASE)
        if not match:
            continue
        try:
            parts = shlex.split(match.group(1), posix=True)
        except ValueError:
            return "SQL include file cannot be inspected"
        if not parts:
            continue
        include_token = parts[0]
        if base_dir is not None and not Path(include_token).expanduser().is_absolute():
            include_token = str(base_dir / include_token)
        try:
            include_key = str(Path(include_token).expanduser().resolve())
        except RuntimeError:
            include_key = include_token
        if include_key in seen:
            continue
        seen.add(include_key)
        include_text, error = _read_inspectable_file(include_token, "SQL include")
        if error:
            return error
        if include_text is None:
            continue
        nested = _sql_text_reason(
            include_text,
            base_dir=Path(include_token).expanduser().parent,
            seen=seen,
        )
        if nested:
            return "destructive SQL include file"
    return None


def _sql_tokens(text: str) -> list[str]:
    """Tokenize SQL policy keywords while discarding comments and literals."""
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index].isspace():
            index += 1
            continue
        if text.startswith("--", index) or text[index] == "#":
            newline = text.find("\n", index + 1)
            index = length if newline == -1 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                return tokens
            if text.startswith("/*!", index):
                body = re.sub(r"^[0-9]+\s*", "", text[index + 3 : end])
                tokens.extend(_sql_tokens(body))
            index = end + 2
            continue
        if text[index] == "'":
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "'":
                    if index + 1 < length and text[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if text[index] == "$":
            dollar_tag = re.match(r"\$[A-Za-z_0-9]*\$", text[index:])
            if dollar_tag:
                delimiter = dollar_tag.group(0)
                end = text.find(delimiter, index + len(delimiter))
                index = length if end == -1 else end + len(delimiter)
                continue
        if text[index] in {'"', "`", "["}:
            opener = text[index]
            closer = "]" if opener == "[" else opener
            index += 1
            while index < length:
                if text[index] == closer:
                    if index + 1 < length and text[index + 1] == closer:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            tokens.append("IDENT")
            continue
        if text[index].isalnum() or text[index] in {"_", "$"}:
            end = index + 1
            while end < length and (
                text[end].isalnum() or text[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(text[index:end].upper())
            index = end
            continue
        if text[index] == ";":
            tokens.append(";")
        index += 1
    return tokens


def _sql_sequence_at(tokens: list[str], index: int, sequence: tuple[str, ...]) -> bool:
    return tokens[index : index + len(sequence)] == list(sequence)


def _sql_string_literals(text: str) -> list[str]:
    literals: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "'":
            index += 1
            continue
        index += 1
        value: list[str] = []
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                value.append(text[index + 1])
                index += 2
                continue
            if text[index] == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    value.append("'")
                    index += 2
                    continue
                index += 1
                break
            value.append(text[index])
            index += 1
        literals.append("".join(value))
    return literals


def _sql_without_string_literals(text: str) -> str:
    output: list[str] = []
    index = 0
    in_literal = False
    while index < len(text):
        char = text[index]
        if not in_literal and char == "'":
            in_literal = True
            output.append(" ")
            index += 1
            continue
        if in_literal:
            if char == "\\" and index + 1 < len(text):
                output.extend((" ", " "))
                index += 2
                continue
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    output.extend((" ", " "))
                    index += 2
                    continue
                in_literal = False
            output.append(" ")
            index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _has_dynamic_destructive_sql(text: str) -> bool:
    without_literals = _sql_without_string_literals(text)
    if re.search(r"\\gexec\b", without_literals, re.IGNORECASE):
        return True
    tokens = _sql_tokens(text)
    dynamic_execution = (
        "PREPARE" in tokens
        or "SP_EXECUTESQL" in tokens
        or any(
            _sql_sequence_at(tokens, index, sequence)
            for index in range(len(tokens))
            for sequence in (("EXECUTE", "IMMEDIATE"), ("EXEC",))
        )
    )
    if not dynamic_execution:
        return False
    literals = _sql_string_literals(text)
    if any(_has_destructive_sql(literal) for literal in literals):
        return True
    if "PREPARE" in tokens and "FROM" in tokens and not literals:
        return True
    return False


def _has_destructive_sql(text: str) -> bool:
    tokens = _sql_tokens(text)
    drop_objects = (
        ("TABLE",),
        ("DATABASE",),
        ("SCHEMA",),
        ("ROLE",),
        ("USER",),
        ("VIEW",),
        ("MATERIALIZED", "VIEW"),
        ("INDEX",),
        ("SEQUENCE",),
        ("FUNCTION",),
        ("PROCEDURE",),
        ("TRIGGER",),
        ("TYPE",),
        ("POLICY",),
        ("EXTENSION",),
        ("OWNED", "BY"),
        ("SERVER",),
        ("PUBLICATION",),
        ("SUBSCRIPTION",),
        ("EVENT", "TRIGGER"),
        ("FOREIGN", "TABLE"),
        ("FOREIGN", "DATA", "WRAPPER"),
    )
    alter_drop_objects = (
        ("COLUMN",),
        ("CONSTRAINT",),
        ("FOREIGN", "KEY"),
        ("PRIMARY", "KEY"),
        ("INDEX",),
        ("KEY",),
        ("CHECK",),
        ("PARTITION",),
    )

    for index, token in enumerate(tokens):
        if token == "DROP":
            object_index = index + 1
            if object_index < len(tokens) and tokens[object_index] == "TEMPORARY":
                object_index += 1
            if any(
                _sql_sequence_at(tokens, object_index, sequence)
                for sequence in drop_objects
            ):
                return True
        if token == "TRUNCATE":
            return True
        if token == "DELETE":
            if index == 0 or tokens[index - 1] in {";", "THEN"}:
                return True
            for following in tokens[index + 1 :]:
                if following == ";":
                    break
                if following == "FROM":
                    return True
        if token == "ALTER" and _sql_sequence_at(tokens, index, ("ALTER", "TABLE")):
            for drop_index in range(index + 2, len(tokens)):
                if tokens[drop_index] == ";":
                    break
                if tokens[drop_index] != "DROP":
                    continue
                object_index = drop_index + 1
                if any(
                    _sql_sequence_at(tokens, object_index, sequence)
                    for sequence in alter_drop_objects
                ):
                    return True
    return False


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


def _shell_command_invocation(
    args: list[str],
) -> tuple[str, str, list[str]] | None:
    """Return ``bash -c`` command text, argv0, and positional arguments."""
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
                tail = args[command_index + 1 :]
                argv0 = tail[0] if tail else ""
                return args[command_index], argv0, tail[1:]
    return None


def _double_quote_shell_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def _shell_positional_value(
    name: str,
    *,
    argv0: str,
    positional: list[str],
) -> str | list[str]:
    if name in {"@", "*"}:
        return positional
    if name == "#":
        return str(len(positional))
    if name == "0":
        return argv0
    index = int(name) - 1
    return positional[index] if 0 <= index < len(positional) else ""


def _expand_shell_positional_parameters(
    command: str,
    *,
    argv0: str,
    positional: list[str],
) -> tuple[str, bool]:
    """Model the positional parameters visible to a ``shell -c`` body.

    Values are shell-quoted because parameter expansion cannot introduce new
    control operators. A remaining positional expression means the static
    analyzer cannot model the command safely and must fail closed.
    """
    output: list[str] = []
    index = 0
    in_single = False
    in_double = False
    unresolved = False
    exact_quoted = re.compile(r'^"\$(?:\{(?P<braced>[@*#]|[0-9]+)\}|(?P<plain>[@*#0-9]))"')
    parameter = re.compile(r'^\$(?:\{(?P<braced>[@*#]|[0-9]+)\}|(?P<plain>[@*#0-9]))')

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
        if in_single:
            output.append(char)
            index += 1
            continue
        if char == '"':
            quoted = exact_quoted.match(command[index:])
            if quoted:
                name = quoted.group("braced") or quoted.group("plain") or ""
                value = _shell_positional_value(
                    name, argv0=argv0, positional=positional
                )
                if isinstance(value, list):
                    output.append(shlex.join(value))
                else:
                    output.append(shlex.quote(value))
                index += quoted.end()
                continue
            in_double = not in_double
            output.append(char)
            index += 1
            continue
        if char == "$":
            matched = parameter.match(command[index:])
            if matched:
                name = matched.group("braced") or matched.group("plain") or ""
                value = _shell_positional_value(
                    name, argv0=argv0, positional=positional
                )
                if isinstance(value, list):
                    replacement = shlex.join(value)
                elif in_double:
                    replacement = _double_quote_shell_value(value)
                else:
                    replacement = shlex.quote(value)
                output.append(replacement)
                index += matched.end()
                continue
            if re.match(r"^\$(?:\{(?:[@*#0-9])[^}]*\}|[@*#0-9])", command[index:]):
                unresolved = True
        output.append(char)
        index += 1
    return "".join(output), unresolved


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


def _source_script_reason(args: list[str]) -> str | None:
    index = _skip_options(args)
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
        text, error = _read_inspectable_file(script, "shell source")
        if error:
            return error
        if text is None:
            return None
        nested = _shell_script_text_reason(text)
        if nested:
            return "shell source file with destructive command"
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
    depth = _ANALYSIS_DEPTH.get()
    if depth >= MAX_ANALYSIS_DEPTH:
        return NESTED_ANALYSIS_LIMIT_REASON
    token = _ANALYSIS_DEPTH.set(depth + 1)
    try:
        return _analyze_command_impl(command)
    finally:
        _ANALYSIS_DEPTH.reset(token)


def _analyze_command_impl(command: str) -> str | None:
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
    chained_alias_reason = _chained_protected_alias_reason(command)
    if chained_alias_reason:
        return chained_alias_reason
    piped_sql_reason = _piped_sql_reason(command)
    if piped_sql_reason:
        return piped_sql_reason
    piped_runtime_reason = _piped_language_runtime_reason(command)
    if piped_runtime_reason:
        return piped_runtime_reason
    piped_shell_reason = _piped_shell_reason(command)
    if piped_shell_reason:
        return piped_shell_reason
    runtime_stdin_reason = _language_runtime_heredoc_reason(command)
    if runtime_stdin_reason:
        return runtime_stdin_reason
    for tokens in _segments(command):
        command_context = shlex.join(tokens)
        tokens = _unwrap_prefix(tokens)
        start = _command_start(tokens)
        if start >= len(tokens):
            continue
        executable = _executable(tokens[start])
        args = tokens[start + 1 :]
        interpreter_reason = _inline_language_runtime_reason(
            executable,
            args,
            command_context=command_context,
        )
        if interpreter_reason:
            return interpreter_reason
        runtime_stdin_argument_reason = _language_runtime_argument_stdin_reason(
            executable,
            args,
            command_context,
        )
        if runtime_stdin_argument_reason:
            return runtime_stdin_argument_reason
        runtime_script_reason = _language_runtime_script_file_reason(
            executable,
            args,
            command_context,
        )
        if runtime_script_reason:
            return runtime_script_reason
        overwrite_reason = _protected_overwrite_reason(executable, args)
        if overwrite_reason:
            return overwrite_reason
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
            shell_invocation = _shell_command_invocation(args)
            if shell_invocation:
                shell_command, argv0, positional = shell_invocation
                expanded_command, unresolved = _expand_shell_positional_parameters(
                    shell_command,
                    argv0=argv0,
                    positional=positional,
                )
                if unresolved:
                    return "shell positional expansion cannot be inspected"
                nested = analyze_command(expanded_command)
                if nested:
                    return nested
            script_file_reason = _shell_script_file_reason(args)
            if script_file_reason:
                return script_file_reason
            stdin_reason = _shell_stdin_reason(args)
            if stdin_reason:
                return stdin_reason
        if executable in SOURCE_BUILTINS:
            source_reason = _source_script_reason(args)
            if source_reason:
                return source_reason
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
    segments = _segments(command)
    if not any(_segment_executable_is(tokens, SQL_CLIENTS) for tokens in segments):
        return None
    payload = " ".join(" ".join(tokens) for tokens in segments)
    if _has_destructive_sql(payload):
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
