from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "release-checks.yml"
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
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict)
    return data


def _release_job(data: dict[str, Any]) -> dict[str, Any]:
    jobs = data.get("jobs")
    assert isinstance(jobs, dict)
    job = jobs.get("release-checks")
    assert isinstance(job, dict)
    return job


def _named_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    matches = [step for step in steps if isinstance(step, dict) and step.get("name") == name]
    assert len(matches) == 1
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
    assert not pending
    return commands


def _shell_exports(script: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for command in _logical_shell_commands(script):
        tokens = shlex.split(command)
        if not tokens or tokens[0] != "export":
            continue
        for assignment in tokens[1:]:
            name, separator, value = assignment.partition("=")
            assert separator, f"export must assign a value: {assignment}"
            exports[name] = value
    return exports


def _requirement_tokens(arguments: list[str], package: str) -> list[str]:
    operators = ("===", "==", "~=", "!=", "<=", ">=", "<", ">")
    return [
        argument
        for argument in arguments
        if argument == package or any(argument.startswith(package + op) for op in operators)
    ]


def test_release_checks_workflow_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for expected in (
        "SAMVIL Release Checks",
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
    ):
        assert expected in text

    assert "python3 scripts/run-release-checks.py --format json" not in text
    assert "python3 scripts/build-release-bundle.py --format json" not in text

    data = _load_workflow()
    job = _release_job(data)

    install_step = _named_step(job, "Install Python package")
    install_script = install_step.get("run")
    assert isinstance(install_script, str)
    install_commands = _logical_shell_commands(install_script)
    fixture_install = [
        command
        for command in install_commands
        if command.startswith("mcp/.venv/bin/python -m pip install ") and "-e mcp" in command
    ]
    assert len(fixture_install) == 1
    install_tokens = shlex.split(fixture_install[0])
    install_arguments = install_tokens[4:]
    for requirement in PINNED_PYTEST_FIXTURE_COMPONENTS:
        package = requirement.partition("==")[0]
        assert _requirement_tokens(install_arguments, package) == [requirement]

    portable_step = _named_step(job, PORTABLE_RELEASE_CONTROL_STEP)
    portable_script = portable_step.get("run")
    assert isinstance(portable_script, str)
    assert PORTABLE_RELEASE_CONTROL_COMMAND in _logical_shell_commands(portable_script)
    portable_exports = _shell_exports(portable_script)
    for name, expected_value in REQUIRED_PORTABLE_EXPORTS.items():
        assert portable_exports.get(name) == expected_value

    workflow_env = data.get("env") or {}
    job_env = job.get("env") or {}
    step_env = portable_step.get("env") or {}
    for env_scope in (workflow_env, job_env, step_env):
        assert isinstance(env_scope, dict)
    for name in FORBIDDEN_PORTABLE_HOST_BOUND_ENV:
        assert name not in portable_exports
        assert name not in text
        assert name not in workflow_env
        assert name not in job_env
        assert name not in step_env


def test_ci_workflow_validator_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "-B", "scripts/validate-ci-workflow.py"],
        cwd=REPO,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert "OK: ci workflow validation passed" in result.stdout
