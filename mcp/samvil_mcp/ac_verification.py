"""Prepare and execute lightweight AC verification contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Any, Iterator

from .ssot_io import atomic_write_text
from .test_deliverable import feature_spec_filename


VERIFY_KEYS = frozenset({"command", "artifacts", "assertion"})
BROWSER_SOLUTION_TYPES = frozenset({"web-app", "dashboard", "game"})
_BACKTICK_COMMAND = re.compile(r"`([^`]+)`")


def validate_verify_contract(verify: Any) -> list[str]:
    """Return validation errors for an optional AC ``verify`` object."""
    if not isinstance(verify, dict):
        return ["verify must be an object"]
    unknown = sorted(set(verify) - VERIFY_KEYS)
    errors = [f"verify has unknown fields: {unknown}"] if unknown else []
    command = verify.get("command")
    if not isinstance(command, str) or not command.strip():
        errors.append("verify.command is required")
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
    verify: dict[str, Any] = {"command": match.group(1).strip()}
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


def _safe_log_name(ac_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", ac_id).strip("-.")
    digest = hashlib.sha256(ac_id.encode("utf-8")).hexdigest()[:10]
    return f"{safe or 'ac'}-{digest}"


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


def run_ac_verification(
    project_root: str | Path,
    ac_id: str,
    verify: dict[str, Any],
    *,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    """Execute an AC command and judge exit, assertion, and artifacts."""
    errors = validate_verify_contract(verify)
    root = Path(project_root).expanduser().resolve()
    command = str(verify.get("command") or "").strip()
    artifacts = list(verify.get("artifacts") or [])
    assertion = str(verify.get("assertion") or "")
    artifact_status = _artifact_status(root, artifacts)
    if errors or not command:
        return {
            "ac_id": ac_id,
            "ran": False,
            "exit_code": None,
            "passed": False,
            "assertion_matched": False if assertion else None,
            "artifacts": artifact_status,
            "log_file": "",
            "primary_evidence": False,
            "errors": errors + ([] if command else ["verify.command is required"]),
        }

    exit_code = 1
    timed_out = False
    process = subprocess.Popen(
            ["bash", "-o", "pipefail", "-c", command],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    try:
        stdout, stderr = process.communicate(timeout=max(0.01, timeout_seconds))
        exit_code = process.returncode
        output = (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        output = (stdout or "") + (stderr or "")

    relative_log = f".samvil/ac-evidence/{_safe_log_name(ac_id)}.log"
    separator = "" if not output or output.endswith("\n") else "\n"
    atomic_write_text(
        root / relative_log,
        f"{output}{separator}SAMVIL_EXIT:{exit_code}\n",
    )
    artifact_status = _artifact_status(root, artifacts)
    assertion_matched = assertion in output if assertion else None
    passed = (
        exit_code == 0
        and not artifact_status["missing"]
        and assertion_matched is not False
    )
    return {
        "ac_id": ac_id,
        "ran": True,
        "exit_code": exit_code,
        "passed": passed,
        "assertion_matched": assertion_matched,
        "artifacts": artifact_status,
        "log_file": relative_log,
        "primary_evidence": True,
        "timed_out": timed_out,
        "errors": [],
    }
