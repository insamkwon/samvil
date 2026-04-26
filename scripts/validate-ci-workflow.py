#!/usr/bin/env python3
"""Validate the SAMVIL GitHub Actions release-check workflow contract."""

from __future__ import annotations

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
    "python3 scripts/run-release-checks.py --format json",
    "python3 scripts/build-release-bundle.py --format json",
    "actions/upload-artifact@v4",
    "samvil-release-evidence",
    "release-report.json",
    "release-summary.md",
    "release-runner.json",
    "release-bundle.json",
)


def _load_workflow() -> dict[str, Any]:
    if yaml is None:
        return {}
    with WORKFLOW.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise AssertionError("workflow root must be a mapping")
    return data


def validate_workflow() -> list[str]:
    if not WORKFLOW.exists():
        raise AssertionError(f"missing workflow: {WORKFLOW}")

    text = WORKFLOW.read_text(encoding="utf-8")
    missing = [fragment for fragment in REQUIRED_FRAGMENTS if fragment not in text]
    if missing:
        raise AssertionError("missing workflow fragments: " + ", ".join(missing))

    data = _load_workflow()
    if data:
        jobs = data.get("jobs") or {}
        if "release-checks" not in jobs:
            raise AssertionError("missing jobs.release-checks")
        job = jobs["release-checks"] or {}
        if job.get("runs-on") != "ubuntu-latest":
            raise AssertionError("release-checks must run on ubuntu-latest")
        steps = job.get("steps") or []
        if len(steps) < 8:
            raise AssertionError("release-checks must include setup, runner, bundle, and artifact steps")
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

    return list(REQUIRED_FRAGMENTS)


def main() -> int:
    fragments = validate_workflow()
    print("OK: ci workflow validation passed")
    for fragment in fragments:
        print(f"- {fragment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
