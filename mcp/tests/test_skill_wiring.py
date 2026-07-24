"""Regression tests for documentation-to-MCP wiring checks."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


def _load_wiring_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "check-skill-wiring.py"
    spec = importlib.util.spec_from_file_location("check_skill_wiring", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reference_tool_check_rejects_unregistered_tool(tmp_path: Path) -> None:
    server = tmp_path / "mcp" / "samvil_mcp" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_text(
        "@mcp.tool()\nasync def rate_budget_stats(budget_path: str):\n    pass\n",
        encoding="utf-8",
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "protocol.md").write_text(
        "Use `rate_budget_stats(path='x')`, then the `budget_status` tool.\n",
        encoding="utf-8",
    )

    wiring = _load_wiring_module()

    unresolved = wiring.find_unresolved_reference_tools(tmp_path)

    assert unresolved == {"budget_status": ["references/protocol.md:1"]}


def test_reference_tool_check_catches_non_allowlisted_tool_prefix(tmp_path: Path) -> None:
    server = tmp_path / "mcp" / "samvil_mcp" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_text(
        "@mcp.tool()\nasync def validate_seed(seed_path: str):\n    pass\n",
        encoding="utf-8",
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "protocol.md").write_text(
        "Call `validate_missing(seed_path='x')` through MCP.\n",
        encoding="utf-8",
    )

    wiring = _load_wiring_module()

    assert wiring.find_unresolved_reference_tools(tmp_path) == {
        "validate_missing": ["references/protocol.md:1"]
    }


def test_reference_tool_check_rejects_removed_interview_readiness_tool(
    tmp_path: Path,
) -> None:
    server = tmp_path / "mcp" / "samvil_mcp" / "server.py"
    server.parent.mkdir(parents=True)
    server.write_text(
        "@mcp.tool()\nasync def score_ambiguity(interview_state: str):\n    pass\n",
        encoding="utf-8",
    )
    references = tmp_path / "references"
    references.mkdir()
    (references / "contract-layer-protocol.md").write_text(
        "Call `compute_seed_readiness(dimensions={})` before the gate.\n",
        encoding="utf-8",
    )

    wiring = _load_wiring_module()

    assert wiring.find_unresolved_reference_tools(tmp_path) == {
        "compute_seed_readiness": ["references/contract-layer-protocol.md:1"]
    }


def test_agents_validate_seed_signature_matches_server_tool() -> None:
    repo = Path(__file__).resolve().parents[2]
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    server = (repo / "mcp" / "samvil_mcp" / "server.py").read_text(encoding="utf-8")

    assert "async def validate_seed(seed_json: str)" in server
    assert "validate_seed(seed_json)" in agents
    assert "validate_seed(seed_path)" not in agents


def test_interview_question_limits_use_decision_boundaries_ssot() -> None:
    repo = Path(__file__).resolve().parents[2]
    thin = (repo / "skills" / "samvil-interview" / "SKILL.md").read_text()
    legacy = (repo / "skills" / "samvil-interview" / "SKILL.legacy.md").read_text()
    boundaries = (repo / "references" / "decision-boundaries.md").read_text()

    assert "references/decision-boundaries.md" in thin
    assert "references/decision-boundaries.md" in legacy
    assert "minimal 5 / standard 10 / thorough 20 / full 30 / deep 40" not in thin
    assert "| minimal | 3-4개 |" not in legacy
    assert "`min_questions_reference`" in boundaries
    assert "`max_questions`" in boundaries


def test_canonical_gate_docs_match_runtime_gate_names() -> None:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "mcp"))
    from samvil_mcp.gates import GateName

    boundaries = (repo / "references" / "decision-boundaries.md").read_text(
        encoding="utf-8"
    )
    glossary = (repo / "references" / "glossary.md").read_text(encoding="utf-8")
    section = boundaries.split("## Canonical stage gates", 1)[1].split(
        "\n## ", 1
    )[0]
    documented = re.findall(r"\d+\. `([^`]+)`", section)
    runtime = [gate.value for gate in GateName]

    assert documented == runtime
    assert "9 named gates" in glossary
    for gate in runtime:
        assert gate in glossary


def test_save_event_examples_use_named_arguments() -> None:
    repo = Path(__file__).resolve().parents[2]
    for relative in (
        "skills/samvil-pm-interview/SKILL.md",
        "skills/samvil-update/SKILL.md",
    ):
        text = (repo / relative).read_text()
        assert 'mcp__samvil_mcp__save_event("' not in text
        assert "session_id=" in text
        assert "event_type=" in text
        assert "stage=" in text
        assert "data=" in text


def test_interview_completion_uses_trusted_stage_transition() -> None:
    repo = Path(__file__).resolve().parents[2]
    text = (repo / "skills" / "samvil-interview" / "SKILL.md").read_text()

    assert (
        'mcp__samvil_mcp__complete_stage(session_id="<sid>", '
        'stage="interview", verdict="pass")'
    ) in text
    assert 'save_event(event_type="interview_complete"' not in text

    codex = (
        repo / "references" / "codex-commands" / "samvil-interview.md"
    ).read_text()
    gate_index = codex.index('gate_check(gate_name="interview_to_seed"')
    claim_index = codex.index('claim_type="gate_verdict"')
    complete_index = codex.index(
        'complete_stage(session_id=<sid>, stage="interview", verdict="pass")'
    )
    assert gate_index < claim_index < complete_index


def test_codex_build_command_gets_gate_input_from_phase_z() -> None:
    repo = Path(__file__).resolve().parents[2]
    text = (repo / "references" / "codex-commands" / "samvil-build.md").read_text()

    phase_z_index = text.index("finalize_build_phase_z")
    gate_index = text.index('gate_check(gate_name="build_to_qa"')
    assert phase_z_index < gate_index
    assert "metrics_json=<phase_z.gate_input.metrics>" in text
    assert "metrics_json=<gate_input>" not in text


def test_all_stage_skills_fail_closed_without_trusted_gate_override() -> None:
    repo = Path(__file__).resolve().parents[2]
    wiring = _load_wiring_module()

    for skill in wiring.BOOT_CONTRACT_SKILLS:
        text = (repo / "skills" / skill / "SKILL.md").read_text()
        assert "gate_override" in text, skill
        assert "unavailable" in text.lower() or "사용할 수 없" in text, skill
        assert "force_proceed" in text, skill


def test_interview_batches_only_independent_questions() -> None:
    repo = Path(__file__).resolve().parents[2]
    thin = (repo / "skills" / "samvil-interview" / "SKILL.md").read_text()
    legacy = (repo / "skills" / "samvil-interview" / "SKILL.legacy.md").read_text()

    for text in (thin, legacy):
        assert "독립 질문 2~3개" in text
        assert "의존 질문" in text
    assert "Asking 2+ questions in a single AskUserQuestion" not in thin


def test_orchestrator_skips_only_resolved_entry_questions() -> None:
    repo = Path(__file__).resolve().parents[2]
    thin = (repo / "skills" / "samvil" / "SKILL.md").read_text()
    legacy = (repo / "skills" / "samvil" / "SKILL.legacy.md").read_text()

    for text in (thin, legacy):
        assert 'solution_type.confidence == "high"' in text
        assert "ℹ️" in text
        assert "저신뢰" in text
    assert "Skipping the L3 user confirmation on a high-confidence" not in thin
    assert 'errors[]' in thin
    assert '"brownfield:"' in thin


def test_council_is_only_an_explicit_seed_opt_in() -> None:
    repo = Path(__file__).resolve().parents[2]
    orchestrator = (repo / "skills" / "samvil" / "SKILL.md").read_text()
    seed = (repo / "skills" / "samvil-seed" / "SKILL.md").read_text()

    assert "Council (skip if minimal)" not in orchestrator
    assert "--council" in seed
    assert "default" in seed.lower()
    assert "samvil-design" in seed


def test_deep_tier_is_defined_in_downstream_skill_matrices() -> None:
    repo = Path(__file__).resolve().parents[2]
    qa = (repo / "skills" / "samvil-qa" / "SKILL.md").read_text()
    design = (repo / "skills" / "samvil-design" / "SKILL.md").read_text()
    council = (repo / "skills" / "samvil-council" / "SKILL.md").read_text()

    assert "standard` / `thorough` / `full` / `deep" in qa
    assert "thorough/full/deep" in design
    assert "`deep`" in council


def test_qa_selects_gate_after_next_skill_routing() -> None:
    repo = Path(__file__).resolve().parents[2]
    qa = (repo / "skills" / "samvil-qa" / "SKILL.md").read_text()

    assert "qa_to_evolve" in qa
    assert "any_to_retro" in qa
    assert "next_skill_decision.suggested" in qa
    assert qa.index("emit_ac_spec") < qa.index("collect_ac_verification")


def test_pm_and_codex_seed_paths_keep_council_opt_in_only() -> None:
    repo = Path(__file__).resolve().parents[2]
    pm = (repo / "skills" / "samvil-pm-interview" / "SKILL.md").read_text()
    codex = (repo / "references" / "codex-commands" / "samvil-seed.md").read_text()

    assert "--council" in pm
    assert "flags" in pm
    assert "default" in pm.lower()
    assert "prepare_seed_verify_contracts" in codex
    assert "schema_version `3.3` only after approval" in codex
    assert 'next_skill="samvil-design"' in codex
    assert 'next_skill="samvil-council"' in codex


def test_codex_orchestrator_initializes_the_selected_stage() -> None:
    repo = Path(__file__).resolve().parents[2]
    codex = (repo / "references" / "codex-commands" / "samvil.md").read_text()

    assert '"current_stage":"<chain.state_stage>"' in codex
    assert '"current_stage":"interview"' not in codex


def test_codex_build_uses_mechanical_build_gate_before_chain() -> None:
    repo = Path(__file__).resolve().parents[2]
    codex = (repo / "references" / "codex-commands" / "samvil-build.md").read_text()

    assert "collect_stage_evidence" in codex
    assert 'gate_name="build_to_qa"' in codex
    assert 'evidence_mode="mechanical"' in codex
    assert "Any tool error or non-`pass` verdict halts" in codex
    assert codex.index("collect_stage_evidence") < codex.index("gate_check")
    assert codex.index("gate_check") < codex.index("write_chain_marker")


def test_codex_interview_respects_question_budget_action() -> None:
    repo = Path(__file__).resolve().parents[2]
    codex = (
        repo / "references" / "codex-commands" / "samvil-interview.md"
    ).read_text()

    assert "**No cap on reprompts**" not in codex
    assert 'budget_action="offer_draft_or_extend"' in codex
    assert "effective_max_questions" in codex
    assert "explicit user choice" in codex


def test_codex_qa_uses_dynamic_finalize_route() -> None:
    repo = Path(__file__).resolve().parents[2]
    codex = (repo / "references" / "codex-commands" / "samvil-qa.md").read_text()

    assert "finalize.next_skill_decision.suggested" in codex
    assert "finalize_qa_verdict" in codex
    assert "materialize_qa_synthesis" in codex
    assert codex.index("finalize_qa_verdict") < codex.index("materialize_qa_synthesis")
    assert codex.index("materialize_qa_synthesis") < codex.index("gate_check")
    assert "qa_to_deploy" in codex
    assert "qa_to_evolve" in codex
    assert "any_to_retro" in codex
    assert "samvil_tier=<finalize.samvil_tier>" in codex
    assert "metrics_json=<finalize.gate_input.metrics>" in codex
    assert "three_pass_pass" in codex
    assert "Only after materialize + gate PASS" in codex
    assert 'next_skill="<finalize.next_skill_decision.suggested>"' in codex
    assert "Deploy/Evolve/Retro" in codex
    assert "samvil-qa" in codex
    assert "no cross-stage gate" in codex


def test_codex_commands_use_root_seed_ssot_and_deploy_fails_closed() -> None:
    repo = Path(__file__).resolve().parents[2]
    command_dir = repo / "references" / "codex-commands"
    command_text = "\n".join(
        path.read_text() for path in sorted(command_dir.glob("samvil-*.md"))
    )
    deploy = (command_dir / "samvil-deploy.md").read_text()

    assert ".samvil/project.seed.json" not in command_text
    assert "ready=false" in deploy
    assert 'qa_gate.verdict!="pass"' in deploy
    assert "no marker is written" in deploy or "continuation marker" in deploy
    assert 'next_skill="samvil-retro"' in deploy


def test_codex_design_council_input_is_optional_and_gate_is_correct() -> None:
    repo = Path(__file__).resolve().parents[2]
    design = (
        repo / "references" / "codex-commands" / "samvil-design.md"
    ).read_text()

    assert "If `.samvil/council-results.md` exists" in design
    assert 'gate_name="design_to_scaffold"' in design
    assert "any non-`pass` verdict halts" in design
    assert "project.blueprint.json" in design


def test_codex_scaffold_reads_root_blueprint_ssot() -> None:
    repo = Path(__file__).resolve().parents[2]
    scaffold = (
        repo / "references" / "codex-commands" / "samvil-scaffold.md"
    ).read_text()

    assert "root `project.blueprint.json`" in scaffold
    assert ".samvil/blueprint.json" not in scaffold


def test_design_stage_preserves_explicit_council_opt_in() -> None:
    repo = Path(__file__).resolve().parents[2]
    thin = (repo / "skills" / "samvil-design" / "SKILL.md").read_text()
    codex = (
        repo / "references" / "codex-commands" / "samvil-design.md"
    ).read_text()

    for text in (thin, codex):
        assert "--council" in text
        assert "council_opt_in" in text
        assert "get_orchestration_state" in text
        assert "stage_can_proceed" in text


def test_numeric_drift_check_rejects_mismatched_named_constants(tmp_path: Path) -> None:
    wiring = _load_wiring_module()
    skill = tmp_path / "skills" / "samvil-build"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "references/decision-boundaries.md\nMAX_RETRIES=2\n",
        encoding="utf-8",
    )
    (skill / "SKILL.legacy.md").write_text(
        "references/decision-boundaries.md\nMAX_RETRIES=3\n",
        encoding="utf-8",
    )

    issues = wiring.find_skill_numeric_drift(tmp_path)

    assert issues == ["samvil-build: MAX_RETRIES thin=['2'] legacy=['3']"]


def test_numeric_drift_check_requires_ssot_citation(tmp_path: Path) -> None:
    wiring = _load_wiring_module()
    skill = tmp_path / "skills" / "samvil-build"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("MAX_RETRIES=2\n", encoding="utf-8")
    (skill / "SKILL.legacy.md").write_text("MAX_RETRIES=2\n", encoding="utf-8")

    issues = wiring.find_skill_numeric_drift(tmp_path)

    assert issues == [
        "samvil-build: named constants missing decision-boundaries SSOT citation"
    ]


def test_numeric_drift_check_rejects_one_sided_constant(tmp_path: Path) -> None:
    wiring = _load_wiring_module()
    skill = tmp_path / "skills" / "samvil-build"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "references/decision-boundaries.md\nMAX_RETRIES=2\n",
        encoding="utf-8",
    )
    (skill / "SKILL.legacy.md").write_text(
        "references/decision-boundaries.md\n",
        encoding="utf-8",
    )

    assert wiring.find_skill_numeric_drift(tmp_path) == [
        "samvil-build: MAX_RETRIES missing from legacy"
    ]
