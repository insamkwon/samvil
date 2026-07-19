"""AC verify contract preparation and mechanical execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from samvil_mcp.ac_verification import (
    prepare_seed_verify_contracts,
    run_ac_verification,
    validate_verify_contract,
)


def _seed(solution_type: str = "web-app") -> dict:
    return {
        "schema_version": "3.2",
        "name": "demo-app",
        "solution_type": solution_type,
        "tech_stack": {"framework": "nextjs"},
        "features": [
            {
                "name": "task-list",
                "acceptance_criteria": [
                    {"id": "F1.AC1", "description": "task can be created"},
                    {
                        "id": "F1.AC2",
                        "description": "task persists",
                        "children": [
                            {"id": "F1.AC2.1", "description": "reload keeps task"}
                        ],
                    },
                ],
            }
        ],
    }


def test_browser_ac_contracts_reuse_feature_playwright_spec() -> None:
    prepared = prepare_seed_verify_contracts(_seed())
    leaves = prepared["seed"]["features"][0]["acceptance_criteria"]

    assert prepared["seed"]["schema_version"] == "3.3"
    assert leaves[0]["verify"] == {
        "command": "npx playwright test tests/e2e/task-list.spec.ts"
    }
    assert leaves[1]["children"][0]["verify"] == leaves[0]["verify"]
    assert prepared["filled_count"] == 2


def test_existing_verify_contract_is_preserved() -> None:
    seed = _seed()
    existing = {"command": "npm run test:unit", "assertion": "12 passed"}
    seed["features"][0]["acceptance_criteria"][0]["verify"] = existing

    prepared = prepare_seed_verify_contracts(seed)

    assert prepared["seed"]["features"][0]["acceptance_criteria"][0]["verify"] == existing


def test_automation_candidate_omits_unsupported_arbitrary_script() -> None:
    seed = _seed("automation")
    leaf = seed["features"][0]["acceptance_criteria"][0]
    leaf["verification"] = "Run `python main.py --dry-run`; output contains DRY RUN OK"
    leaf["expected"] = "DRY RUN OK"

    prepared = prepare_seed_verify_contracts(seed)

    assert "verify" not in prepared["seed"]["features"][0]["acceptance_criteria"][0]
    assert prepared["automation_candidates"] == []


def test_verify_contract_requires_executable_command() -> None:
    errors = validate_verify_contract({"artifacts": ["result.txt"]})

    assert errors == ["verify.command is required"]


def test_allowed_contract_is_validated_but_not_executed_without_trusted_runner(
    tmp_path: Path,
) -> None:
    (tmp_path / "test_sample.py").write_text(
        "import unittest\n"
        "class Sample(unittest.TestCase):\n"
        "    def test_ready(self):\n"
        "        print('READY')\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )

    result = run_ac_verification(
        tmp_path,
        "F1.AC1",
        {
            "command": "python -m unittest test_sample.py",
            "assertion": "READY",
        },
    )

    assert result["ran"] is False
    assert result["exit_code"] is None
    assert result["assertion_matched"] is False
    assert result["passed"] is False
    assert result["primary_evidence"] is False
    assert "trusted AC command runner unavailable" in result["errors"][0]


def test_failed_assertion_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(
        "import unittest\n"
        "class Sample(unittest.TestCase):\n"
        "    def test_actual(self): print('actual')\n",
        encoding="utf-8",
    )

    result = run_ac_verification(
        tmp_path,
        "F1.AC2",
        {"command": "python -m unittest test_sample.py", "assertion": "expected"},
    )

    assert result["exit_code"] is None
    assert result["assertion_matched"] is False
    assert result["passed"] is False


def test_shell_pipeline_is_rejected_instead_of_executed(tmp_path: Path) -> None:

    result = run_ac_verification(
        tmp_path,
        "F1.AC-pipe",
        {"command": "python -m unittest | tail -1"},
    )

    assert result["ran"] is False
    assert "shell syntax" in result["errors"][0]
    assert result["passed"] is False


def test_untrusted_runner_never_starts_process_or_detached_child(tmp_path: Path) -> None:
    (tmp_path / "test_slow.py").write_text(
        "import subprocess, sys, time, unittest\n"
        "class Slow(unittest.TestCase):\n"
        "    def test_slow(self):\n"
        "        subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(0.4); open(\\\"escaped.txt\\\", \\\"w\\\").close()'], "
        "start_new_session=True)\n"
        "        time.sleep(1)\n",
        encoding="utf-8",
    )
    result = run_ac_verification(
        tmp_path,
        "AC-timeout",
        {"command": "python -m unittest test_slow.py"},
        timeout_seconds=0.05,
    )

    assert result["ran"] is False
    assert result["timed_out"] is False
    assert result["exit_code"] is None
    assert not (tmp_path / "escaped.txt").exists()


def test_ac_verification_mcp_tool(tmp_path: Path) -> None:
    from samvil_mcp.server import collect_ac_verification

    (tmp_path / "test_sample.py").write_text(
        "import unittest\n"
        "class Sample(unittest.TestCase):\n"
        "    def test_ok(self): print('OK')\n",
        encoding="utf-8",
    )
    result = json.loads(
        asyncio.run(
            collect_ac_verification(
                project_root=str(tmp_path),
                ac_id="F1.AC3",
                verify_json=json.dumps(
                    {"command": "python -m unittest test_sample.py", "assertion": "OK"}
                ),
            )
        )
    )

    assert result["ran"] is False
    assert result["passed"] is False
    assert "trusted AC command runner unavailable" in result["errors"][0]


def test_arbitrary_python_and_destructive_commands_are_rejected(tmp_path: Path) -> None:
    for command in (
        "python -c 'print(1)'",
        "python main.py --dry-run",
        "./pytest",
        "/tmp/pytest",
        "npm test",
        "npm run test:unit",
        "PYTEST",
        "Python -m unittest",
        "NPX playwright test tests/e2e/demo.spec.ts",
        "GRADLE TEST",
        "rm -rf .samvil",
        "sudo -u root rm -rf /",
    ):
        result = run_ac_verification(tmp_path, "AC-denied", {"command": command})
        assert result["ran"] is False
        assert result["passed"] is False
        assert result["errors"]


def test_prepare_seed_verify_contracts_mcp_tool() -> None:
    from samvil_mcp.server import prepare_seed_verify_contracts as prepare_tool

    result = json.loads(asyncio.run(prepare_tool(json.dumps(_seed()))))

    assert result["seed"]["schema_version"] == "3.3"
    assert result["filled_count"] == 2
