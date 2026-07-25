"""Contract hook lifecycle regressions for trustworthy-core Wave 4.2."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _stage_end_env(tmp_path: Path, project: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "TOOL_NAME": "Skill",
            "CLAUDE_PLUGIN_ROOT": str(REPO),
            "SAMVIL_PROJECT_ROOT": str(project),
        }
    )
    return env


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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


def test_pm_interview_stage_end_skips_interview_gate_and_writes_design_marker(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "pm-interview"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-pm-interview"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    claims_path = project / ".samvil" / "claims.jsonl"
    claims = claims_path.read_text() if claims_path.exists() else ""
    assert marker["next_skill"] == "samvil-design"
    assert marker["from_stage"] == "samvil-pm-interview"
    assert '"subject": "interview_to_seed"' not in claims


def test_pm_interview_stage_end_preserves_explicit_council_route(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "pm-interview"},
    )
    _write_json(
        project / "project.config.json",
        {"samvil_tier": "standard", "flags": ["--council"]},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-pm-interview"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    assert marker["next_skill"] == "samvil-council"
    assert marker["from_stage"] == "samvil-pm-interview"


def test_pm_interview_stage_end_ignores_stale_council_marker_without_flag(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "pm-interview"},
    )
    _write_json(project / "project.config.json", {"flags": []})
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "next-skill.json",
        {
            "from_stage": "samvil-pm-interview",
            "next_skill": "samvil-council",
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-pm-interview"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    assert marker["next_skill"] == "samvil-design"


def test_qa_stage_end_marker_uses_failed_qa_retro_route(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "synthesis": {
                "verdict": "FAIL",
                "verification_mode": "static",
                "pass1": {"status": "PASS"},
                "pass2": {"counts": {"PASS": 0, "PARTIAL": 0, "UNIMPLEMENTED": 0, "FAIL": 1}},
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "failed"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert marker["next_skill"] == "samvil-retro"
    assert marker["from_stage"] == "samvil-qa"
    assert '"subject": "any_to_retro"' in claims


def test_qa_stage_end_continue_keeps_ralph_loop_without_marker_or_gate(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "synthesis": {
                "verdict": "REVISE",
                "verification_mode": "static",
                "pass1": {"status": "PASS"},
                "pass2": {
                    "counts": {
                        "PASS": 0,
                        "PARTIAL": 0,
                        "UNIMPLEMENTED": 0,
                        "FAIL": 1,
                    }
                },
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "continue"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    assert not (project / ".samvil" / "next-skill.json").exists()
    claims_path = project / ".samvil" / "claims.jsonl"
    claims = claims_path.read_text() if claims_path.exists() else ""
    assert '"subject": "qa_to_deploy"' not in claims
    assert '"subject": "qa_to_evolve"' not in claims
    assert '"subject": "any_to_retro"' not in claims


def test_qa_stage_end_marker_uses_auto_evolve_route(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "synthesis": {
                "verdict": "PASS",
                "verification_mode": "static",
                "pass1": {"status": "PASS"},
                "pass2": {"counts": {"PASS": 0, "PARTIAL": 5, "UNIMPLEMENTED": 0, "FAIL": 0}},
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "continue"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert marker["next_skill"] == "samvil-evolve"
    assert marker["from_stage"] == "samvil-qa"
    assert '"subject": "qa_to_evolve"' in claims


def test_qa_stage_end_skips_marker_when_deploy_gate_blocks(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "generated_at": "2026-07-22T00:00:01Z",
            "synthesis": {
                "verdict": "PASS",
                "verification_mode": "static",
                "pass1": {"status": "PASS"},
                "pass2": {"counts": {"PASS": 1, "PARTIAL": 0, "UNIMPLEMENTED": 0, "FAIL": 0}},
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "continue"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert not (project / ".samvil" / "next-skill.json").exists()
    assert '"subject": "qa_to_deploy"' in claims
    assert '"verdict": "block"' in claims


def test_qa_stage_end_ignores_stale_qa_routing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-routing.json",
        {
            "generated_at": "2026-07-22T00:00:00Z",
            "primary_route": {"next_skill": "samvil-retro"},
        },
    )
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "generated_at": "2026-07-22T00:00:01Z",
            "synthesis": {
                "verdict": "PASS",
                "verification_mode": "runtime",
                "pass1": {"status": "PASS"},
                "pass2": {"counts": {"PASS": 1, "PARTIAL": 0, "UNIMPLEMENTED": 0, "FAIL": 0}},
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "continue"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert marker["next_skill"] == "samvil-deploy"
    assert '"subject": "qa_to_deploy"' in claims
    assert '"subject": "any_to_retro"' not in claims


def test_qa_stage_end_ignores_future_qa_routing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {"samvil_tier": "standard", "current_stage": "qa"},
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-routing.json",
        {
            "generated_at": "2099-01-01T00:00:00Z",
            "primary_route": {"next_skill": "samvil-retro"},
        },
    )
    _write_json(
        project / ".samvil" / "qa-results.json",
        {
            "generated_at": "2026-07-22T00:00:01Z",
            "synthesis": {
                "verdict": "PASS",
                "verification_mode": "runtime",
                "pass1": {"status": "PASS"},
                "pass2": {"counts": {"PASS": 1, "PARTIAL": 0, "UNIMPLEMENTED": 0, "FAIL": 0}},
                "pass3": {"verdict": "PASS"},
            },
            "convergence": {"verdict": "continue"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    marker = json.loads((project / ".samvil" / "next-skill.json").read_text())
    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert marker["next_skill"] == "samvil-deploy"
    assert '"subject": "qa_to_deploy"' in claims
    assert '"subject": "any_to_retro"' not in claims


def test_qa_stage_end_ignores_routing_without_qa_results(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_json(
        project / "project.state.json",
        {
            "samvil_tier": "standard",
            "current_stage": "qa",
            "qa_verdict": "PASS",
        },
    )
    _write_json(project / "project.seed.json", {"schema_version": "3.2"})
    _write_json(
        project / ".samvil" / "qa-routing.json",
        {
            "generated_at": "2026-07-22T00:00:00Z",
            "primary_route": {"next_skill": "samvil-retro"},
        },
    )

    subprocess.run(
        [
            "bash",
            str(REPO / "hooks" / "contract-stage-end.sh"),
            json.dumps({"skill": "samvil-qa"}),
            "0",
        ],
        cwd=project,
        env=_stage_end_env(tmp_path, project),
        check=True,
    )

    claims = (project / ".samvil" / "claims.jsonl").read_text()
    assert not (project / ".samvil" / "next-skill.json").exists()
    assert '"subject": "qa_to_deploy"' in claims
    assert '"subject": "any_to_retro"' not in claims


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
