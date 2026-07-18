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
