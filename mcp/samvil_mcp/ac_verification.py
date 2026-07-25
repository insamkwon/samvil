"""Prepare and validate AC verification contracts without host execution."""

from __future__ import annotations

import copy
import re
import shlex
from pathlib import Path
from typing import Any, Iterator

from .test_deliverable import feature_spec_filename


VERIFY_KEYS = frozenset({"command", "artifacts", "assertion"})
BROWSER_SOLUTION_TYPES = frozenset(
    {"web-app", "dashboard", "game", "mobile-app"}
)
_BACKTICK_COMMAND = re.compile(r"`([^`]+)`")
_SHELL_SYNTAX = re.compile(r"[\r\n;&|<>`$(){}]")


def validate_verify_contract(verify: Any) -> list[str]:
    """Return validation errors for an optional AC ``verify`` object."""
    if not isinstance(verify, dict):
        return ["verify must be an object"]
    unknown = sorted(set(verify) - VERIFY_KEYS)
    errors = [f"verify has unknown fields: {unknown}"] if unknown else []
    command = verify.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append("verify.command is required")
    elif (command_error := _command_policy_error(command.strip())) is not None:
        errors.append(command_error)
    assertion = verify.get("assertion")
    if assertion is not None and (
        not isinstance(assertion, str) or not assertion.strip()
    ):
        errors.append("verify.assertion must be a non-empty string")
    artifacts = verify.get("artifacts")
    if artifacts is not None and (
        not isinstance(artifacts, list)
        or not all(isinstance(item, str) and item.strip() for item in artifacts)
    ):
        errors.append("verify.artifacts must be a list of non-empty paths")
    return errors


def _leaf_nodes(items: list[Any]) -> Iterator[dict[str, Any]]:
    for item in items:
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if isinstance(children, list) and children:
            yield from _leaf_nodes(children)
        else:
            yield item


def _automation_candidate(leaf: dict[str, Any]) -> dict[str, Any] | None:
    source = str(leaf.get("verification") or leaf.get("description") or "")
    match = _BACKTICK_COMMAND.search(source)
    if not match:
        return None
    command = match.group(1).strip()
    if _command_policy_error(command):
        return None
    verify: dict[str, Any] = {"command": command}
    expected = str(leaf.get("expected") or "").strip()
    if expected:
        verify["assertion"] = expected
    return verify


def prepare_seed_verify_contracts(seed: dict[str, Any]) -> dict[str, Any]:
    """Return a v3.3 seed with browser contracts and automation proposals."""
    prepared = copy.deepcopy(seed)
    prepared["schema_version"] = "3.3"
    solution_type = str(prepared.get("solution_type") or "")
    filled_count = 0
    candidates: list[dict[str, Any]] = []

    for feature in prepared.get("features") or []:
        if not isinstance(feature, dict):
            continue
        feature_name = str(feature.get("name") or "feature")
        command = (
            f"npx playwright test {feature_spec_filename(feature_name)}"
            if solution_type in BROWSER_SOLUTION_TYPES
            else ""
        )
        for leaf in _leaf_nodes(feature.get("acceptance_criteria") or []):
            if isinstance(leaf.get("verify"), dict):
                continue
            if command:
                leaf["verify"] = {"command": command}
                filled_count += 1
                continue
            candidate = _automation_candidate(leaf)
            if candidate:
                candidates.append(
                    {
                        "ac_id": str(leaf.get("id") or ""),
                        "feature": feature_name,
                        "verify": candidate,
                    }
                )

    return {
        "seed": prepared,
        "filled_count": filled_count,
        "automation_candidates": candidates,
    }


def _artifact_status(root: Path, artifacts: list[str]) -> dict[str, list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for relative in artifacts:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            missing.append(relative)
            continue
        (present if candidate.exists() else missing).append(relative)
    return {"present": present, "missing": missing}


def _command_policy_error(command: str) -> str | None:
    """Validate portable test-runner syntax without resolving or executing it."""
    if _SHELL_SYNTAX.search(command):
        return "verify.command contains unsupported shell syntax"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"verify.command cannot be parsed: {exc}"
    if not argv:
        return "verify.command is required"
    if Path(argv[0]).name != argv[0]:
        return "verify.command executable must be an exact runner name, not a path"

    executable = argv[0]
    args = argv[1:]
    allowed = False
    if executable in {"python", "python3"}:
        allowed = len(args) >= 2 and args[0] == "-m" and args[1] in {
            "pytest",
            "unittest",
        }
    elif executable in {"pytest", "py.test"}:
        allowed = True
    elif executable == "npx":
        allowed = len(args) >= 2 and args[:2] in (
            ["playwright", "test"],
            ["vitest", "run"],
        )
    elif executable in {"cargo", "go", "swift"}:
        allowed = bool(args) and args[0] == "test"
    elif executable == "gradle":
        allowed = bool(args) and args[0] == "test"

    if not allowed:
        return "verify.command is not an allowed test runner invocation"
    return None


def run_ac_verification(
    project_root: str | Path,
    ac_id: str,
    verify: Any,
    *,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    """Validate an AC contract and fail closed without a trusted runner.

    The MCP process intentionally does not execute model- or seed-authored
    commands. Current hosts lack a portable sandbox that can prevent a test
    process from escaping its process tree or mutating the host. Host-driven
    Playwright and emitted test files remain available as secondary evidence.
    """
    errors = validate_verify_contract(verify)
    verify_obj = verify if isinstance(verify, dict) else {}
    root = Path(project_root).expanduser().resolve()
    command = str(verify_obj.get("command") or "").strip()
    artifacts = list(verify_obj.get("artifacts") or [])
    assertion = str(verify_obj.get("assertion") or "")
    artifact_status = _artifact_status(root, artifacts)
    if errors or not command:
        if not command and isinstance(verify, dict):
            errors = errors + ["verify.command is required"]
        return {
            "ac_id": ac_id,
            "ran": False,
            "exit_code": None,
            "passed": False,
            "assertion_matched": False if assertion else None,
            "artifacts": artifact_status,
            "log_file": "",
            "primary_evidence": False,
            "errors": errors,
        }
    return {
        "ac_id": ac_id,
        "ran": False,
        "exit_code": None,
        "passed": False,
        "assertion_matched": False if assertion else None,
        "artifacts": artifact_status,
        "log_file": "",
        "primary_evidence": False,
        "timed_out": False,
        "output_truncated": False,
        "errors": [
            "trusted AC command runner unavailable; command was validated but not executed"
        ],
    }
