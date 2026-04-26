"""Smoke tests for the samvil orchestrator skill (T4.5 ultra-thin migration).

The samvil orchestrator skill is the `/samvil` entry point. It keeps the
bits that need a real shell / user interaction:

- Health Check shell calls (Node/Python/uv/gh/MCP discovery).
- AskUserQuestion checkpoints (project mode, tier, L3 solution_type
  confirmation, resume vs fresh start).
- Chain dispatch (Skill tool when claude_code, file marker otherwise).

What CAN be machine-pinned, and is pinned here, is the new
`aggregate_orchestrator_state` MCP tool the thin skill delegates to. It owns:

- Tier resolution with precedence cli > state > config > default
  (deprecated v3.1 'deep' alias mapped to 'full' with `aliased_from`).
- 3-layer solution_type detection (L1 keyword + L2 context, web-app fallback).
  Layer-3 user confirmation still happens in the skill body.
- PM-mode detection from the one-line prompt.
- Brownfield + resume detection from filesystem artifacts + state.
- First-skill selection (analyze / interview / pm-interview / resume target).

Idempotency: re-aggregating the same inputs yields the same dict.

The chain mechanics themselves (HostCapability resolution, Skill vs file
marker) are tested in `test_orchestrator.py` + `test_orchestrator_mcp.py`.
The Health Check shell calls and AskUserQuestion prompts are host-bound
and not unit-tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import orchestrator
from samvil_mcp.orchestrator import (
    aggregate_orchestrator_state,
    detect_pm_mode,
    detect_solution_type,
)


# ── Fixtures ───────────────────────────────────────────────────


def _write_state(root: Path, **payload) -> None:
    (root / "project.state.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_config(root: Path, **payload) -> None:
    (root / "project.config.json").write_text(json.dumps(payload), encoding="utf-8")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


# ── solution_type detection ───────────────────────────────────


def test_detect_solution_type_web_app_default() -> None:
    """Bare 'todo app' falls through to web-app default."""
    result = detect_solution_type("할일 관리 앱")
    assert result["solution_type"] == "web-app"
    assert result["layer"] == "default"
    assert result["confidence"] == "low"


def test_detect_solution_type_automation_keyword() -> None:
    """L1: '자동화' → automation, high confidence."""
    result = detect_solution_type("이메일 자동화 스크립트")
    assert result["solution_type"] == "automation"
    assert result["layer"] == "L1_keyword"
    assert "자동화" in result["matched"]
    assert result["confidence"] == "high"


def test_detect_solution_type_game_keyword() -> None:
    """L1: '게임' → game."""
    result = detect_solution_type("플랫포머 게임")
    assert result["solution_type"] == "game"
    assert result["layer"] == "L1_keyword"


def test_detect_solution_type_mobile_app_keyword() -> None:
    """L1: '모바일 앱' → mobile-app, not just web-app."""
    result = detect_solution_type("운동 기록 모바일 앱")
    assert result["solution_type"] == "mobile-app"
    assert result["layer"] == "L1_keyword"


def test_detect_solution_type_dashboard_keyword() -> None:
    """L1: 'dashboard' → dashboard."""
    result = detect_solution_type("Sales analytics dashboard")
    assert result["solution_type"] == "dashboard"
    assert result["layer"] == "L1_keyword"


def test_detect_solution_type_l2_context_automation() -> None:
    """L2 fires when no L1 keyword: '자동으로 ... 트리거' → automation."""
    result = detect_solution_type("주문이 들어오면 자동으로 슬랙에 알림")
    assert result["solution_type"] == "automation"
    assert result["layer"] == "L2_context"
    assert result["confidence"] == "medium"


def test_detect_solution_type_l2_context_game() -> None:
    """L2: '점수 ... 캐릭터' nudges to game without 'game' keyword."""
    result = detect_solution_type("캐릭터를 키워서 점수를 올리는 콘텐츠")
    assert result["solution_type"] == "game"
    assert result["layer"] == "L2_context"


def test_detect_solution_type_empty_prompt() -> None:
    """Empty prompt → web-app default, no crash."""
    result = detect_solution_type("")
    assert result["solution_type"] == "web-app"
    assert result["matched"] == []


# ── PM-mode detection ─────────────────────────────────────────


def test_detect_pm_mode_explicit() -> None:
    """'/samvil pm vision' triggers PM mode."""
    assert detect_pm_mode("/samvil pm vision: collaborate on docs") is True


def test_detect_pm_mode_signal_words() -> None:
    """Vision/MVP/epics keywords trigger PM mode."""
    assert detect_pm_mode("MVP for collab editor with user segments") is True
    assert detect_pm_mode("Define epics for sprint 1") is True


def test_detect_pm_mode_engineering_default() -> None:
    """No PM signal → engineering mode."""
    assert detect_pm_mode("todo app with drag and drop") is False


# ── Tier resolution ───────────────────────────────────────────


def test_aggregate_tier_default_when_nothing(tmp_path: Path) -> None:
    """Empty project → standard tier from default."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["tier"]["samvil_tier"] == "standard"
    assert result["tier"]["source"] == "default"
    assert result["tier"]["aliased_from"] == ""


def test_aggregate_tier_cli_overrides_config(tmp_path: Path) -> None:
    """CLI tier wins over config tier."""
    _write_config(tmp_path, samvil_tier="minimal")
    result = aggregate_orchestrator_state(
        tmp_path, prompt="todo app", cli_tier="thorough"
    )
    assert result["tier"]["samvil_tier"] == "thorough"
    assert result["tier"]["source"] == "cli"


def test_aggregate_tier_state_overrides_config(tmp_path: Path) -> None:
    """State tier wins over config tier (resume scenario)."""
    _write_state(tmp_path, samvil_tier="full")
    _write_config(tmp_path, samvil_tier="minimal")
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["tier"]["samvil_tier"] == "full"
    assert result["tier"]["source"] == "state"


def test_aggregate_tier_deep_alias_mapped_to_full(tmp_path: Path) -> None:
    """v3.1 'deep' alias is mapped to v3.2 'full' with `aliased_from`."""
    result = aggregate_orchestrator_state(
        tmp_path, prompt="todo app", cli_tier="deep"
    )
    assert result["tier"]["samvil_tier"] == "full"
    assert result["tier"]["aliased_from"] == "deep"


def test_aggregate_tier_invalid_falls_back_to_default(tmp_path: Path) -> None:
    """Bogus tier flag → default standard, never raises."""
    result = aggregate_orchestrator_state(
        tmp_path, prompt="todo app", cli_tier="banana"
    )
    assert result["tier"]["samvil_tier"] == "standard"
    assert result["tier"]["source"] == "default"


# ── Brownfield + resume detection ─────────────────────────────


def test_aggregate_brownfield_greenfield_default(tmp_path: Path) -> None:
    """Empty dir → greenfield, no resume."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["brownfield"]["is_brownfield"] is False
    assert result["brownfield"]["can_resume"] is False
    assert result["brownfield"]["state_present"] is False


def test_aggregate_brownfield_explicit_hint(tmp_path: Path) -> None:
    """mode_hint='brownfield' wins regardless of artifacts."""
    result = aggregate_orchestrator_state(
        tmp_path, prompt="add 2fa", mode_hint="brownfield"
    )
    assert result["brownfield"]["is_brownfield"] is True
    assert result["chain"]["next_skill"] == "samvil-analyze"


def test_aggregate_brownfield_inferred_from_package_json(tmp_path: Path) -> None:
    """package.json present, no state → infer brownfield."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    result = aggregate_orchestrator_state(tmp_path, prompt="add 2fa")
    assert result["brownfield"]["is_brownfield"] is True
    assert result["brownfield"]["artifacts"]["package_json"] is True


def test_aggregate_resume_state_present(tmp_path: Path) -> None:
    """state.json with completed_stages → resume after last completed."""
    _write_state(
        tmp_path,
        completed_stages=["interview", "seed", "scaffold"],
        current_stage="build",
        samvil_tier="standard",
    )
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["brownfield"]["can_resume"] is True
    assert result["brownfield"]["state_present"] is True
    assert result["brownfield"]["completed_stages"] == [
        "interview",
        "seed",
        "scaffold",
    ]
    # After scaffold the next non-skipped stage is build.
    assert result["chain"]["resume_point"] == "build"
    assert result["chain"]["next_skill"] == "samvil-build"


# ── Chain / first-skill selection ─────────────────────────────


def test_aggregate_chain_default_engineering_interview(tmp_path: Path) -> None:
    """Fresh + no PM signals → samvil-interview."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["chain"]["next_skill"] == "samvil-interview"
    assert result["is_pm_mode"] is False


def test_aggregate_chain_pm_mode_routes_to_pm_interview(tmp_path: Path) -> None:
    """PM signals route to samvil-pm-interview."""
    result = aggregate_orchestrator_state(
        tmp_path, prompt="MVP for collab editor with user segments"
    )
    assert result["is_pm_mode"] is True
    assert result["chain"]["next_skill"] == "samvil-pm-interview"


def test_aggregate_chain_brownfield_beats_pm_signals(tmp_path: Path) -> None:
    """Brownfield mode wins over PM signals — analyze first, then chain."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    result = aggregate_orchestrator_state(
        tmp_path, prompt="add MVP analytics dashboard"
    )
    assert result["chain"]["next_skill"] == "samvil-analyze"


def test_aggregate_chain_resume_overrides_pm_default(tmp_path: Path) -> None:
    """Resume target wins over PM signals when state present."""
    _write_state(
        tmp_path,
        completed_stages=["interview"],
        current_stage="seed",
        samvil_tier="standard",
    )
    result = aggregate_orchestrator_state(
        tmp_path, prompt="MVP collab editor"
    )
    assert result["chain"]["resume_point"] == "seed"
    assert result["chain"]["next_skill"] == "samvil-seed"


# ── Misc + invariants ─────────────────────────────────────────


def test_aggregate_kebab_project_name(tmp_path: Path) -> None:
    """Project name slugified from prompt."""
    result = aggregate_orchestrator_state(tmp_path, prompt="할일 관리 앱!!")
    assert result["project_name"] == "할일-관리-앱"
    # Empty prompt falls back to placeholder.
    result2 = aggregate_orchestrator_state(tmp_path, prompt="")
    assert result2["project_name"] == "samvil-project"


def test_aggregate_host_name_default_generic(tmp_path: Path) -> None:
    """No host_name → generic."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["host_name"] == "generic"


def test_aggregate_host_name_normalized(tmp_path: Path) -> None:
    """Host name lowercased + trimmed."""
    result = aggregate_orchestrator_state(
        tmp_path, prompt="todo app", host_name=" Claude_Code "
    )
    assert result["host_name"] == "claude_code"


def test_aggregate_idempotent(tmp_path: Path) -> None:
    """Re-aggregating same inputs yields same dict."""
    _write_state(tmp_path, completed_stages=["interview"], current_stage="seed")
    a = aggregate_orchestrator_state(tmp_path, prompt="todo app", cli_tier="full")
    b = aggregate_orchestrator_state(tmp_path, prompt="todo app", cli_tier="full")
    assert a == b


def test_aggregate_schema_version_pinned(tmp_path: Path) -> None:
    """Schema version is stable so skills can rely on it."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["schema_version"] == orchestrator.ORCHESTRATOR_AGGREGATE_SCHEMA_VERSION
    assert result["schema_version"] == "1.0"


def test_aggregate_never_raises_on_corrupt_state(tmp_path: Path) -> None:
    """Corrupt state.json is treated as missing, not an exception."""
    (tmp_path / "project.state.json").write_text("not-json", encoding="utf-8")
    # Should not raise; corrupt JSON falls through to empty dict.
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert result["brownfield"]["state_present"] is False
    assert result["chain"]["next_skill"] == "samvil-interview"


def test_aggregate_returns_errors_list(tmp_path: Path) -> None:
    """`errors` is always a list (even when empty)."""
    result = aggregate_orchestrator_state(tmp_path, prompt="todo app")
    assert isinstance(result["errors"], list)
