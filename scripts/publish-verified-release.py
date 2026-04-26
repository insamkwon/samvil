#!/usr/bin/env python3
"""Publish a release tag only after local and remote release gates pass."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "mcp"))

from samvil_mcp.release import evaluate_release_gate, read_release_report  # noqa: E402
from samvil_mcp.release_guards import (  # noqa: E402
    evaluate_publish_guard,
    evaluate_remote_release_gate,
    release_tag,
    render_publish_guard,
)

import importlib.util  # noqa: E402


def _load_remote_gate_cli():
    script = REPO / "scripts" / "check-remote-release-gate.py"
    spec = importlib.util.spec_from_file_location("check_remote_release_gate", script)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load check-remote-release-gate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REMOTE_GATE_CLI = _load_remote_gate_cli()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="", help="release version; defaults to plugin.json")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--workflow", default="SAMVIL Release Checks")
    parser.add_argument("--artifact", default="samvil-release-evidence")
    parser.add_argument("--run-id", default="", help="specific GitHub Actions run id")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="do not push branch or create/push tag")
    parser.add_argument("--allow-dirty", action="store_true", help="allow dirty tree for dry-run fixture checks")
    parser.add_argument("--skip-local-release-checks", action="store_true")
    parser.add_argument("--run-json", default="", help="fixture/local run metadata JSON")
    parser.add_argument("--runner-json", default="", help="fixture/local release-runner JSON")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    version = args.version or _plugin_version()
    tag = release_tag(version)
    head = _git("rev-parse", "HEAD")

    if not args.skip_local_release_checks:
        _run_checked(["python3", "scripts/run-release-checks.py", "--format", "json"])
        local_gate = evaluate_release_gate(REPO, release_report=read_release_report(REPO))
    else:
        local_gate = {"verdict": "pass", "next_action": "local release checks skipped"}

    if not args.dry_run and not args.run_json:
        _run_checked(["git", "push", args.remote, args.branch])
        _wait_for_remote_run(args, head)

    remote_gate = _remote_gate(args, head)
    state = {
        "version": version,
        "tag": tag,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "target_branch": args.branch,
        "head": head,
        "clean": args.allow_dirty or not bool(_git("status", "--porcelain")),
        "version_synced": _version_synced(),
        "local_tag_exists": _tag_exists(tag),
        "remote_tag_exists": _remote_tag_exists(args.remote, tag),
        "remote_branch_pushed": args.dry_run or _remote_branch_head(args.remote, args.branch) == head,
        "local_release_gate": local_gate,
        "remote_release_gate": remote_gate,
    }
    gate = evaluate_publish_guard(state)

    if gate["verdict"] == "pass" and not args.dry_run:
        _run_checked(["git", "tag", tag])
        _run_checked(["git", "push", "--no-verify", args.remote, tag])

    if args.format == "json":
        print(json.dumps({"status": "ok", "gate": gate, "dry_run": args.dry_run}, indent=2, ensure_ascii=False))
    else:
        print(render_publish_guard(gate))
        if gate["verdict"] == "pass" and args.dry_run:
            print("dry-run: tag push skipped")
    return 0 if gate["verdict"] == "pass" else 1


def _remote_gate(args: argparse.Namespace, head: str) -> dict[str, Any]:
    if args.run_json and args.runner_json:
        run = _load_json(Path(args.run_json))
        runner = _load_json(Path(args.runner_json))
    else:
        run = REMOTE_GATE_CLI._find_run(args, head)
        runner = REMOTE_GATE_CLI._download_runner(args, str(run.get("databaseId") or run.get("id") or ""))
    return evaluate_remote_release_gate(run=run, runner=runner, expected_head=head)


def _wait_for_remote_run(args: argparse.Namespace, head: str) -> None:
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        try:
            run = REMOTE_GATE_CLI._find_run(args, head)
        except SystemExit:
            run = {}
        if run and run.get("headSha") == head and run.get("status") == "completed":
            return
        time.sleep(max(1, args.poll_seconds))
    raise SystemExit(f"timed out waiting for remote release check run for {head}")


def _plugin_version() -> str:
    data = _load_json(REPO / ".claude-plugin" / "plugin.json")
    return str(data.get("version") or "")


def _version_synced() -> bool:
    result = subprocess.run(["bash", "hooks/validate-version-sync.sh"], cwd=REPO, text=True, capture_output=True)
    return result.returncode == 0


def _tag_exists(tag: str) -> bool:
    return bool(_git("tag", "--list", tag))


def _remote_tag_exists(remote: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", remote, tag],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    return bool(result.stdout.strip())


def _remote_branch_head(remote: str, branch: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", remote, branch],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    return result.stdout.split()[0]


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise SystemExit(f"{' '.join(command)} failed: {message}")
    return result


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
