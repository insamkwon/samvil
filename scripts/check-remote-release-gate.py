#!/usr/bin/env python3
"""Verify the latest remote GitHub Actions release evidence for the current HEAD."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.release_guards import evaluate_remote_release_gate, render_remote_release_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default="SAMVIL Release Checks")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--artifact", default="samvil-release-evidence")
    parser.add_argument("--head", default="", help="expected commit SHA; defaults to git HEAD")
    parser.add_argument("--run-id", default="", help="specific GitHub Actions run id")
    parser.add_argument("--run-json", default="", help="fixture/local run metadata JSON")
    parser.add_argument("--runner-json", default="", help="fixture/local release-runner JSON")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    expected_head = args.head or _git("rev-parse", "HEAD")
    if args.run_json and args.runner_json:
        run = _load_json(Path(args.run_json))
        runner = _load_json(Path(args.runner_json))
    else:
        run = _find_run(args, expected_head)
        runner = _download_runner(args, str(run.get("databaseId") or run.get("id") or ""))

    gate = evaluate_remote_release_gate(run=run, runner=runner, expected_head=expected_head)
    if args.format == "json":
        print(json.dumps({"status": "ok", "gate": gate}, indent=2, ensure_ascii=False))
    else:
        print(render_remote_release_gate(gate))
    return 0 if gate["verdict"] == "pass" else 1


def _find_run(args: argparse.Namespace, expected_head: str) -> dict[str, Any]:
    if args.run_id:
        return _gh_json([
            "run",
            "view",
            args.run_id,
            "--json",
            "databaseId,status,conclusion,workflowName,headBranch,headSha,url,createdAt,updatedAt",
        ])
    runs = _gh_json([
        "run",
        "list",
        "--workflow",
        args.workflow,
        "--branch",
        args.branch,
        "--limit",
        "20",
        "--json",
        "databaseId,status,conclusion,workflowName,headBranch,headSha,url,createdAt,updatedAt",
    ])
    if not isinstance(runs, list):
        raise SystemExit("gh run list did not return a list")
    for run in runs:
        head = str(run.get("headSha") or "")
        if expected_head and head == expected_head:
            return run
    if runs:
        return runs[0]
    raise SystemExit("no remote release check runs found")


def _download_runner(args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    if not run_id:
        raise SystemExit("missing run id for artifact download")
    temp = Path(tempfile.mkdtemp(prefix="samvil-remote-release-"))
    try:
        _run([
            "gh",
            "run",
            "download",
            run_id,
            "-n",
            args.artifact,
            "-D",
            str(temp),
        ])
        runner_path = temp / "release-runner.json"
        if not runner_path.exists():
            raise SystemExit(f"release-runner.json missing from artifact {args.artifact}")
        return _load_json(runner_path)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _gh_json(command: list[str]) -> Any:
    result = _run(["gh", *command])
    return json.loads(result.stdout)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise SystemExit(f"{' '.join(command)} failed: {message}")
    return result


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
