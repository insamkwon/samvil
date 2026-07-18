"""AC verify contract preparation and mechanical execution."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path

from samvil_mcp.ac_verification import (
    prepare_seed_verify_contracts,
    run_ac_verification,
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


def test_automation_candidate_requires_explicit_confirmed_command() -> None:
    seed = _seed("automation")
    leaf = seed["features"][0]["acceptance_criteria"][0]
    leaf["verification"] = "Run `python main.py --dry-run`; output contains DRY RUN OK"
    leaf["expected"] = "DRY RUN OK"

    prepared = prepare_seed_verify_contracts(seed)

    assert "verify" not in prepared["seed"]["features"][0]["acceptance_criteria"][0]
    assert prepared["automation_candidates"] == [
        {
            "ac_id": "F1.AC1",
            "feature": "task-list",
            "verify": {
                "command": "python main.py --dry-run",
                "assertion": "DRY RUN OK",
            },
        }
    ]


def test_command_exit_assertion_and_artifact_are_primary_evidence(tmp_path: Path) -> None:
    python = shlex.quote(sys.executable)
    command = (
        f"{python} -c \"from pathlib import Path; "
        "Path('result.txt').write_text('ok'); print('READY')\""
    )

    result = run_ac_verification(
        tmp_path,
        "F1.AC1",
        {
            "command": command,
            "artifacts": ["result.txt"],
            "assertion": "READY",
        },
    )

    assert result["ran"] is True
    assert result["exit_code"] == 0
    assert result["assertion_matched"] is True
    assert result["artifacts"]["missing"] == []
    assert result["passed"] is True
    assert result["primary_evidence"] is True
    assert (tmp_path / result["log_file"]).read_text().endswith("SAMVIL_EXIT:0\n")


def test_failed_assertion_fails_closed(tmp_path: Path) -> None:
    python = shlex.quote(sys.executable)

    result = run_ac_verification(
        tmp_path,
        "F1.AC2",
        {"command": f"{python} -c \"print('actual')\"", "assertion": "expected"},
    )

    assert result["exit_code"] == 0
    assert result["assertion_matched"] is False
    assert result["passed"] is False


def test_pipeline_cannot_hide_failing_test_command(tmp_path: Path) -> None:
    python = shlex.quote(sys.executable)

    result = run_ac_verification(
        tmp_path,
        "F1.AC-pipe",
        {"command": f"{python} -c \"raise SystemExit(7)\" | tail -1"},
    )

    assert result["exit_code"] == 7
    assert result["passed"] is False


def test_ac_verification_mcp_tool(tmp_path: Path) -> None:
    from samvil_mcp.server import collect_ac_verification

    python = shlex.quote(sys.executable)
    result = json.loads(
        asyncio.run(
            collect_ac_verification(
                project_root=str(tmp_path),
                ac_id="F1.AC3",
                verify_json=json.dumps(
                    {"command": f"{python} -c \"print('OK')\"", "assertion": "OK"}
                ),
            )
        )
    )

    assert result["passed"] is True


def test_prepare_seed_verify_contracts_mcp_tool() -> None:
    from samvil_mcp.server import prepare_seed_verify_contracts as prepare_tool

    result = json.loads(asyncio.run(prepare_tool(json.dumps(_seed()))))

    assert result["seed"]["schema_version"] == "3.3"
    assert result["filled_count"] == 2
