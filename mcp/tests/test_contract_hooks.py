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


def test_python_backed_helpers_noop_cleanly_without_python(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    command = (
        'source hooks/_contract-helpers.sh; '
        'samvil_contract_extract_skill_name \'{"skill":"samvil-build"}\'; '
        f'samvil_contract_append_claim {project} evidence_posted subject statement authority agent; '
        f'samvil_contract_verify_claim {project} subject agent; '
        f'samvil_contract_update_state {project} key value; '
        f'samvil_contract_append_stage_claim_to_state {project} build claim_1'
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
    assert "command not found" not in result.stderr
    assert not (project / "project.state.json").exists()


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


def test_explicit_invalid_project_root_does_not_fall_back_to_cwd(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    fallback_state = fallback / "project.state.json"
    fallback_state.write_text("{}", encoding="utf-8")
    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("x", encoding="utf-8")
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
            json.dumps({"skill": "samvil-build", "project_root": str(invalid_root)}),
        ],
        cwd=fallback,
        env=env,
        check=True,
    )

    assert json.loads(fallback_state.read_text(encoding="utf-8")) == {}
    assert not (fallback / ".samvil").exists()


def test_stage_end_hook_includes_interview_ambiguity_metric(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    (project / "project.state.json").write_text(
        json.dumps(
            {
                "samvil_tier": "standard",
                "seed_readiness": 0.99,
                "ambiguity_converged": True,
            }
        ),
        encoding="utf-8",
    )
    (project / "project.seed.json").write_text(
        json.dumps({"schema_version": "3.2"}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "TOOL_NAME": "Skill",
            "CLAUDE_PLUGIN_ROOT": str(REPO),
        }
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-interview"}),
            "0",
        ],
        cwd=project,
        env=env,
        check=True,
    )

    health_rows = [
        json.loads(line)
        for line in (home / ".samvil" / "mcp-health.jsonl").read_text().splitlines()
        if '"tool": "hook:stage-end"' in line
    ]
    assert health_rows
    assert "verdict=pass" in health_rows[-1]["error"]

    claim_rows = [
        json.loads(line)
        for line in (project / ".samvil" / "claims.jsonl").read_text().splitlines()
        if '"subject": "interview_to_seed"' in line
    ]
    assert claim_rows
    assert "ambiguity_converged" in claim_rows[-1]["statement"]


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
