"""Contract hook lifecycle regressions for trustworthy-core Wave 4.2."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_contract_helper_reports_missing_python_explicitly() -> None:
    command = (
        'source hooks/_contract-helpers.sh; '
        'samvil_contract_python_status'
    )
    env = os.environ.copy()
    env["SAMVIL_FORCE_NO_PYTHON"] = "1"
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=REPO,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "DEGRADED(no python)"


def test_interview_start_hook_seeds_project_root_before_state_exists(tmp_path: Path) -> None:
    project = tmp_path / "fresh-project"
    project.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "TOOL_NAME": "Skill",
            "CLAUDE_PLUGIN_ROOT": str(REPO),
        }
    )
    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-start.sh"),
            json.dumps(
                {
                    "skill": "samvil-interview",
                    "project_root": str(project),
                }
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )

    marker = project / ".samvil" / "contract-project-root"
    state = json.loads((project / "project.state.json").read_text())
    assert marker.read_text().strip() == str(project.resolve())
    assert state["stage_claims"]["interview"].startswith("claim_")


def test_plugin_does_not_run_stage_end_on_skill_prompt_load() -> None:
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    post_commands = [
        hook["command"]
        for group in plugin["hooks"].get("PostToolUse", [])
        for hook in group.get("hooks", [])
    ]
    assert not any("contract-stage-end.sh" in command for command in post_commands)


def test_orchestrator_health_table_surfaces_contract_degradation() -> None:
    skill = (REPO / "skills" / "samvil" / "SKILL.md").read_text()
    assert "Contract" in skill
    assert "DEGRADED(no python)" in skill
