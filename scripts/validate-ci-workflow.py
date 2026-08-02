#!/usr/bin/env python3
"""Validate the SAMVIL GitHub Actions release-check workflow contract."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only outside project envs.
    yaml = None  # type: ignore[assignment]


REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "release-checks.yml"
REQUIRED_FRAGMENTS = (
    "name: SAMVIL Release Checks",
    "actions/checkout@v4",
    "actions/setup-python@v5",
    'python-version: "3.12"',
    "actions/setup-node@v4",
    'node-version: "20"',
    "npx --yes playwright@1.52.0 install --with-deps chromium",
    "set -o pipefail",
    "mcp/.venv/bin/python scripts/run-release-checks.py --format json",
    "mcp/.venv/bin/python scripts/build-release-bundle.py --format json",
    "actions/upload-artifact@v4",
    "samvil-release-evidence",
    "release-report.json",
    "release-summary.md",
    "release-runner.json",
    "release-bundle.json",
)
PINNED_PYTEST_FIXTURE_COMPONENTS = (
    "pytest==9.1.1",
    "pytest-asyncio==1.4.0",
    "iniconfig==2.3.0",
    "packaging==26.2",
    "pluggy==1.6.0",
    "pygments==2.20.0",
    "typing-extensions==4.16.0",
)
PORTABLE_RELEASE_CONTROL_STEP = "Run portable release-control contract suite"
PORTABLE_RELEASE_CONTROL_COMMAND = (
    "mcp/.venv/bin/python -B tools/release-control/tests/test_release_control.py"
)
REQUIRED_PORTABLE_EXPORTS = {
    "HOME": "${test_home}",
    "CODEX_HOME": "${test_codex_home}",
    "TMPDIR": "${test_tmpdir}",
    "XDG_CACHE_HOME": "${test_xdg_cache}",
    "XDG_CONFIG_HOME": "${test_xdg_config}",
    "XDG_DATA_HOME": "${test_xdg_data}",
    "XDG_STATE_HOME": "${test_xdg_state}",
    "GIT_CONFIG_GLOBAL": "${test_gitconfig}",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
FORBIDDEN_PORTABLE_HOST_BOUND_ENV = (
    "SAMVIL_PINNED_RUNTIME_SOURCE",
    "SAMVIL_REQUIRE_COMPLETE_RELEASE_CONTROL",
    "SAMVIL_ENABLE_REAL_SEATBELT_TESTS",
    "SAMVIL_ENABLE_DARWIN_COPIED_RUNTIME_TESTS",
    "SAMVIL_ENABLE_REAL_LINUX_PROC_TESTS",
)


def _load_workflow() -> dict[str, Any]:
    if yaml is None:
        raise AssertionError(
            "PyYAML is required for structural workflow validation; "
            "run with mcp/.venv/bin/python"
        )
    with WORKFLOW.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise AssertionError("workflow root must be a mapping")
    return data


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must be a mapping")
    return value


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list):
        raise AssertionError("jobs.release-checks.steps must be a list")
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            raise AssertionError(f"jobs.release-checks.steps[{index}] must be a mapping")
        steps.append(step)
    return steps


def _named_step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [step for step in steps if step.get("name") == name]
    if len(matches) != 1:
        raise AssertionError(f"workflow must contain exactly one {name!r} step")
    return matches[0]


def _logical_shell_commands(script: str) -> list[str]:
    commands: list[str] = []
    pending = ""
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pending += line
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        commands.append(pending)
        pending = ""
    if pending:
        raise AssertionError("workflow shell block ends with an unfinished continuation")
    return commands


def _shell_exports(script: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for command in _logical_shell_commands(script):
        tokens = shlex.split(command)
        if not tokens or tokens[0] != "export":
            continue
        for assignment in tokens[1:]:
            name, separator, value = assignment.partition("=")
            if not separator:
                raise AssertionError(f"export must assign a value: {assignment}")
            if name in exports:
                raise AssertionError(f"portable release-control step exports {name} more than once")
            exports[name] = value
    return exports


def _requirement_tokens(arguments: list[str], package: str) -> list[str]:
    operators = ("===", "==", "~=", "!=", "<=", ">=", "<", ">")
    return [
        argument
        for argument in arguments
        if argument == package or any(argument.startswith(package + op) for op in operators)
    ]


def _validate_pinned_pytest_fixture(steps: list[dict[str, Any]]) -> None:
    install_step = _named_step(steps, "Install Python package")
    install_script = install_step.get("run")
    if not isinstance(install_script, str):
        raise AssertionError("Install Python package step must contain a shell run block")

    pip_prefix = ["mcp/.venv/bin/python", "-m", "pip", "install"]
    install_arguments: list[str] = []
    installs_editable_mcp = False
    for command in _logical_shell_commands(install_script):
        tokens = shlex.split(command)
        if tokens[: len(pip_prefix)] != pip_prefix:
            continue
        arguments = tokens[len(pip_prefix) :]
        install_arguments.extend(arguments)
        installs_editable_mcp = installs_editable_mcp or any(
            arguments[index : index + 2] == ["-e", "mcp"]
            for index in range(len(arguments) - 1)
        )

    if not installs_editable_mcp:
        raise AssertionError("Install Python package step must install -e mcp")
    for requirement in PINNED_PYTEST_FIXTURE_COMPONENTS:
        package = requirement.partition("==")[0]
        actual = _requirement_tokens(install_arguments, package)
        if actual != [requirement]:
            raise AssertionError(
                f"{package} must be installed exactly once as {requirement}; found {actual}"
            )


def _validate_portable_release_control_step(
    data: dict[str, Any],
    job: dict[str, Any],
    steps: list[dict[str, Any]],
    workflow_text: str,
) -> None:
    portable_step = _named_step(steps, PORTABLE_RELEASE_CONTROL_STEP)
    portable_script = portable_step.get("run")
    if not isinstance(portable_script, str):
        raise AssertionError(f"{PORTABLE_RELEASE_CONTROL_STEP} must contain a shell run block")

    commands = _logical_shell_commands(portable_script)
    if commands.count(PORTABLE_RELEASE_CONTROL_COMMAND) != 1:
        raise AssertionError(
            "portable release-control step must run the contract test module exactly once with -B"
        )
    for required_command in ("set -euo pipefail", "umask 077"):
        if required_command not in commands:
            raise AssertionError(
                f"portable release-control step is missing shell guard: {required_command}"
            )

    exports = _shell_exports(portable_script)
    for name, expected_value in REQUIRED_PORTABLE_EXPORTS.items():
        actual_value = exports.get(name)
        if actual_value != expected_value:
            raise AssertionError(
                f"portable release-control step must export {name}={expected_value}; "
                f"found {actual_value!r}"
            )

    env_scopes = (
        _mapping(data.get("env") or {}, "workflow env"),
        _mapping(job.get("env") or {}, "jobs.release-checks.env"),
        _mapping(portable_step.get("env") or {}, f"{PORTABLE_RELEASE_CONTROL_STEP} env"),
    )
    for name in FORBIDDEN_PORTABLE_HOST_BOUND_ENV:
        if name in workflow_text or name in exports:
            raise AssertionError(
                f"portable CI must not configure host-bound release-control env {name}"
            )
        if any(name in env_scope for env_scope in env_scopes):
            raise AssertionError(
                f"portable CI must not configure host-bound release-control env {name}"
            )


def validate_workflow() -> list[str]:
    if not WORKFLOW.exists():
        raise AssertionError(f"missing workflow: {WORKFLOW}")

    text = WORKFLOW.read_text(encoding="utf-8")
    missing = [fragment for fragment in REQUIRED_FRAGMENTS if fragment not in text]
    if missing:
        raise AssertionError("missing workflow fragments: " + ", ".join(missing))

    data = _load_workflow()
    jobs = _mapping(data.get("jobs") or {}, "jobs")
    if "release-checks" not in jobs:
        raise AssertionError("missing jobs.release-checks")
    job = _mapping(jobs["release-checks"] or {}, "jobs.release-checks")
    if job.get("runs-on") != "ubuntu-latest":
        raise AssertionError("release-checks must run on ubuntu-latest")
    steps = _steps(job)
    if len(steps) < 9:
        raise AssertionError(
            "release-checks must include setup, portable suite, runner, bundle, and artifact steps"
        )
    step_text = "\n".join(str(step) for step in steps)
    for expected in (
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/setup-node@v4",
        "scripts/run-release-checks.py",
        "scripts/build-release-bundle.py",
        "actions/upload-artifact@v4",
        "set -o pipefail",
    ):
        if expected not in step_text:
            raise AssertionError(f"missing parsed workflow step: {expected}")

    _validate_pinned_pytest_fixture(steps)
    _validate_portable_release_control_step(data, job, steps, text)

    return [
        *REQUIRED_FRAGMENTS,
        *(f"pinned fixture: {requirement}" for requirement in PINNED_PYTEST_FIXTURE_COMPONENTS),
        f"portable step: {PORTABLE_RELEASE_CONTROL_STEP}",
        *(f"portable export: {name}={value}" for name, value in REQUIRED_PORTABLE_EXPORTS.items()),
        *(
            f"portable host-bound env forbidden: {name}"
            for name in FORBIDDEN_PORTABLE_HOST_BOUND_ENV
        ),
    ]


def main() -> int:
    fragments = validate_workflow()
    print("OK: ci workflow validation passed")
    for fragment in fragments:
        print(f"- {fragment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
