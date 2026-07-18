#!/usr/bin/env bash
# SAMVIL Hook: block destructive Bash commands before execution.

set -u

TOOL_INPUT="${1:-}"
if [ -z "$TOOL_INPUT" ]; then
  TOOL_INPUT="{}"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[SAMVIL] 🛑 BLOCKED: Cannot inspect Bash command (python3 unavailable)."
  exit 1
fi

REASON=$(TOOL_INPUT="$TOOL_INPUT" python3 - <<'PY'
import json
import os
import re
import shlex


def find_command(value):
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            return command
        tool_input = value.get("tool_input")
        found = find_command(tool_input)
        if found is not None:
            return found
        for child in value.values():
            found = find_command(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_command(child)
            if found is not None:
                return found
    return None


raw = os.environ.get("TOOL_INPUT", "")
try:
    command = find_command(json.loads(raw)) or ""
except (json.JSONDecodeError, TypeError):
    # Backward compatibility for hosts that still pass the command directly.
    command = raw

normalized = re.sub(r"\s+", " ", command.strip()).lower()

if re.search(r"\bdrop\s+(?:table|database)\b", normalized):
    print("destructive SQL statement")
    raise SystemExit

for segment in re.split(r"\s*(?:&&|\|\||;|\n)\s*", normalized):
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    if not tokens:
        continue

    if "git" in tokens:
        git_index = tokens.index("git")
        git_args = tokens[git_index + 1 :]
        if git_args[:1] == ["reset"] and "--hard" in git_args[1:]:
            print("git reset --hard")
            raise SystemExit
        if git_args[:1] == ["clean"]:
            clean_flags = "".join(
                token[1:]
                for token in git_args[1:]
                if token.startswith("-") and not token.startswith("--")
            )
            if "d" in clean_flags and "f" in clean_flags:
                print("git clean with force and directory removal")
                raise SystemExit
        if git_args[:1] == ["push"]:
            push_flags = git_args[1:]
            forced = any(
                token == "-f"
                or token == "--force"
                or token.startswith("--force=")
                for token in push_flags
            )
            if forced:
                print("git force push")
                raise SystemExit

    if "rm" not in tokens:
        continue
    rm_index = tokens.index("rm")
    rm_args = tokens[rm_index + 1 :]
    short_flags = "".join(
        token[1:]
        for token in rm_args
        if token.startswith("-") and not token.startswith("--")
    )
    recursive = "r" in short_flags or "--recursive" in rm_args
    forced = "f" in short_flags or "--force" in rm_args
    if not (recursive and forced):
        continue
    targets = [token for token in rm_args if not token.startswith("-")]
    for target in targets:
        allowed_cache = target == ".next" or target.startswith(".next/")
        allowed_state = target == ".samvil" or target.startswith(".samvil/")
        dangerous = (
            target in {"/", "~", ".", "./", "..", "../", "*", "./*"}
            or target.startswith("/")
            or target.startswith("~/")
            or target.startswith("$")
            or "${" in target
        )
        if dangerous and not (allowed_cache or allowed_state):
            print(f"recursive forced removal of {target}")
            raise SystemExit
PY
)

if [ -n "$REASON" ]; then
  echo "[SAMVIL] 🛑 BLOCKED: Destructive command detected ($REASON)."
  echo "Command: $TOOL_INPUT"
  echo "If you really need this, run it manually outside SAMVIL."
  exit 1
fi

exit 0
