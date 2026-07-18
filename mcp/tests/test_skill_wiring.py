"""Regression tests for documentation-to-MCP wiring checks."""

from __future__ import annotations

import importlib.util
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


def test_all_stage_skills_forbid_unapproved_force_proceed() -> None:
    repo = Path(__file__).resolve().parents[2]
    wiring = _load_wiring_module()

    for skill in wiring.BOOT_CONTRACT_SKILLS:
        text = (repo / "skills" / skill / "SKILL.md").read_text()
        assert "gate_override" in text, skill
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
