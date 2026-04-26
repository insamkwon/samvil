"""Smoke tests for samvil-interview (T4.6 ultra-thin migration).

These tests pin the behaviors that the now-ultra-thin SKILL.md delegates
to MCP. The skill body itself is mostly the user-facing Korean phase
prompts (Phase 0–4) — those cannot move to MCP without losing the
skill's purpose — but every machine-checkable contract the skill relies
on lives below:

- `aggregate_interview_state` MCP wrapper resolves tier (state > config
  > default) including the v3.1 `deep` alias which interview keeps.
- Built-in preset matching for each major solution_type keyword set.
- Custom-preset scan honors `~/.samvil/presets/*.json` (or
  `$SAMVIL_PRESET_DIR`) and beats built-ins on overlapping keywords.
- Zero-Question Mode signal detection (Korean + English).
- Required-phases set per tier (mirrors `interview_engine.tier_phases`).
- Ambiguity target per tier (mirrors `interview_engine.TIER_TARGETS`).
- Idempotency — repeated calls on the same project_root yield the
  same payload.
- Graceful degradation — missing files / unreadable preset dir never
  raises, only populates `errors[]`.
- Wiring — both the new aggregator and the legacy MCP tools the skill
  still calls (`route_question`, `score_ambiguity`, `compute_seed_readiness`,
  `gate_check`, `claim_post`, `render_domain_context`, `save_event`)
  are registered on `samvil_mcp.server.mcp`.

The Korean phase prompts and tier-routing prose stay in SKILL.md and are
validated by interactive `/samvil:samvil-interview` runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from samvil_mcp.interview_aggregate import (
    INTERVIEW_TIERS,
    TIER_AMBIGUITY_TARGETS,
    TIER_REQUIRED_PHASES,
    aggregate_interview_state,
    detect_zero_question_mode,
)
from samvil_mcp.interview_engine import TIER_TARGETS, tier_phases


# ── Fixtures ───────────────────────────────────────────────────


def _write_state(root: Path, **fields) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.state.json").write_text(
        json.dumps(fields), encoding="utf-8"
    )


def _write_config(root: Path, **fields) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.config.json").write_text(
        json.dumps(fields), encoding="utf-8"
    )


def _write_custom_preset(
    preset_dir: Path,
    name: str,
    keywords: list[str],
    description: str = "",
) -> None:
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / f"{name}.json").write_text(
        json.dumps(
            {"name": name, "keywords": keywords, "description": description}
        ),
        encoding="utf-8",
    )


# ── Tier resolution ───────────────────────────────────────────


def test_tier_default_when_no_state_or_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["tier"]["samvil_tier"] == "standard"
    assert result["tier"]["source"] == "default"


def test_tier_from_state_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="thorough")
    _write_config(tmp_path, samvil_tier="minimal")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["tier"]["samvil_tier"] == "thorough"
    assert result["tier"]["source"] == "state"


def test_tier_from_config_when_state_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_config(tmp_path, samvil_tier="full")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["tier"]["samvil_tier"] == "full"
    assert result["tier"]["source"] == "config"


def test_tier_legacy_selected_tier_alias(tmp_path, monkeypatch):
    """Legacy `selected_tier` (v3.1) still recognized as an alias."""
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_config(tmp_path, selected_tier="minimal")
    result = aggregate_interview_state(tmp_path, prompt="todo app")
    assert result["tier"]["samvil_tier"] == "minimal"
    assert result["tier"]["source"] == "config"


def test_tier_deep_preserved_in_interview(tmp_path, monkeypatch):
    """Interview keeps `deep` as a real 5th tier (stricter ambiguity)."""
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="deep")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["tier"]["samvil_tier"] == "deep"
    assert result["ambiguity_target"] == 0.005


def test_tier_unknown_falls_back_to_standard(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="ultra-mega-deep")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["tier"]["samvil_tier"] == "standard"


# ── Ambiguity target + required phases mirror engine ──────────


def test_ambiguity_target_matches_engine_for_all_tiers():
    for tier in INTERVIEW_TIERS:
        assert TIER_AMBIGUITY_TARGETS[tier] == TIER_TARGETS[tier], (
            f"{tier}: aggregate target diverges from engine"
        )


def test_required_phases_mirror_engine_for_all_tiers():
    for tier in INTERVIEW_TIERS:
        agg = set(TIER_REQUIRED_PHASES[tier])
        engine = tier_phases(tier)
        assert agg == engine, (
            f"{tier}: aggregate phases {agg} != engine phases {engine}"
        )


def test_aggregate_returns_phases_in_pipeline_order(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="thorough")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    phases = result["required_phases"]
    # core must come before lifecycle, scope before unknown
    assert phases.index("core") < phases.index("lifecycle")
    assert phases.index("scope") < phases.index("unknown")


# ── Zero-Question mode detection ──────────────────────────────


def test_zero_question_korean_short_signal():
    r = detect_zero_question_mode("할일 앱 ㄱ")
    assert r["is_zero_question"] is True
    assert "ㄱ" in r["matched_signals"]


def test_zero_question_korean_phrase_signal():
    r = detect_zero_question_mode("그냥 만들어 적당히")
    assert r["is_zero_question"] is True
    assert "그냥 만들어" in r["matched_signals"]


def test_zero_question_english_signal():
    r = detect_zero_question_mode("just build a todo app")
    assert r["is_zero_question"] is True


def test_zero_question_negative_normal_prompt():
    r = detect_zero_question_mode("팀을 위한 할일 관리 앱을 만들고 싶어요")
    assert r["is_zero_question"] is False
    assert r["matched_signals"] == []


def test_zero_question_short_signal_not_substring(tmp_path, monkeypatch):
    """Short signals like `고`/`ㄱ` must be whole-token, not substring.

    A prompt mentioning 고객 (customer) or 고민 (worry) must not trigger
    Zero-Question Mode by accident.
    """
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    r = detect_zero_question_mode("고객 관리 앱을 만들고 싶어요")
    assert r["is_zero_question"] is False


# ── Built-in preset matching per solution_type ────────────────


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("할일 관리 앱", "todo"),
        ("todo list app", "todo"),
        ("실시간 대시보드", "dashboard"),
        ("KPI dashboard", "dashboard"),
        ("개인 블로그 사이트", "blog"),
        ("personal blog", "blog"),
        ("칸반 보드 앱", "kanban"),
        ("랜딩 페이지", "landing-page"),
        ("쇼핑몰 결제", "e-commerce"),
        ("간단한 계산기", "calculator"),
        ("실시간 채팅 앱", "chat"),
        ("디자이너 포트폴리오", "portfolio"),
        ("설문 폼 만들기", "form-builder"),
    ],
)
def test_builtin_preset_matches(tmp_path, monkeypatch, prompt, expected):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    result = aggregate_interview_state(tmp_path, prompt=prompt)
    assert result["preset"]["name"] == expected, prompt
    assert result["preset"]["source"] == "builtin"
    assert result["preset"]["keywords"], "built-in matches must list hits"


def test_no_preset_match_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    result = aggregate_interview_state(tmp_path, prompt="random unique gizmo")
    assert result["preset"]["name"] == ""
    assert result["preset"]["source"] == "none"


# ── Custom preset matching ────────────────────────────────────


def test_custom_preset_overrides_builtin(tmp_path, monkeypatch):
    custom = tmp_path / "custom-presets"
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(custom))
    _write_custom_preset(
        custom,
        "team-todo",
        keywords=["할일", "team"],
        description="Team-oriented todo",
    )
    result = aggregate_interview_state(tmp_path, prompt="팀 할일 앱")
    assert result["preset"]["name"] == "team-todo"
    assert result["preset"]["source"] == "custom"
    assert result["custom_presets_count"] == 1


def test_custom_preset_best_of_n_wins(tmp_path, monkeypatch):
    """Highest keyword-hit count wins among custom presets."""
    custom = tmp_path / "custom-presets"
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(custom))
    _write_custom_preset(custom, "narrow", keywords=["할일"])
    _write_custom_preset(custom, "wide", keywords=["할일", "team", "협업"])
    result = aggregate_interview_state(tmp_path, prompt="팀 할일 협업 앱")
    assert result["preset"]["name"] == "wide"


def test_custom_preset_dir_missing_is_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "no-such-dir"))
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    # Built-in still works
    assert result["preset"]["name"] == "todo"
    assert result["custom_presets_count"] == 0
    assert result["errors"] == [] or all(
        "preset" not in e for e in result["errors"]
    )


def test_custom_preset_corrupt_json_does_not_break(tmp_path, monkeypatch):
    custom = tmp_path / "custom-presets"
    custom.mkdir(parents=True)
    (custom / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(custom))
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    # Built-in still resolves; corrupt file silently skipped
    assert result["preset"]["name"] == "todo"


# ── Manifest scan integration ─────────────────────────────────


def test_manifest_greenfield_returns_undetected(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["manifest"].get("detected") is False


def test_manifest_brownfield_detected_with_package_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "dependencies": {"next": "14.2.0", "react": "18.2.0"},
            }
        ),
        encoding="utf-8",
    )
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["manifest"].get("detected") is True


# ── Paths block ───────────────────────────────────────────────


def test_paths_block_uses_project_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "p"))
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    paths = result["paths"]
    assert paths["interview_summary"].endswith("interview-summary.md")
    assert paths["state_file"].endswith("project.state.json")
    assert paths["config_file"].endswith("project.config.json")
    assert paths["preset_dir"] == str(tmp_path / "p")


# ── Idempotency + graceful degradation ────────────────────────


def test_idempotent_repeat_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="thorough", session_id="sess-1")
    a = aggregate_interview_state(tmp_path, prompt="할일 앱")
    b = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert a == b


def test_session_id_propagated_from_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    _write_state(tmp_path, samvil_tier="standard", session_id="abc-123")
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert result["session_id"] == "abc-123"


def test_never_raises_on_garbage_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    (tmp_path / "project.state.json").write_text("{not valid", encoding="utf-8")
    # Should not raise
    result = aggregate_interview_state(tmp_path, prompt="할일 앱")
    assert isinstance(result, dict)
    assert result["tier"]["samvil_tier"] == "standard"  # fallback


def test_empty_prompt_yields_no_preset_no_zero_question(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    result = aggregate_interview_state(tmp_path, prompt="")
    assert result["preset"]["name"] == ""
    assert result["mode"]["is_zero_question"] is False


# ── MCP wrapper + wiring ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_wrapper_returns_json_string(tmp_path, monkeypatch):
    from samvil_mcp.server import aggregate_interview_state as tool

    monkeypatch.setenv("SAMVIL_PRESET_DIR", str(tmp_path / "presets-empty"))
    raw = await tool(project_root=str(tmp_path), prompt="할일 관리 앱")
    payload = json.loads(raw)
    assert payload["schema_version"] == "1.0"
    assert payload["preset"]["name"] == "todo"


@pytest.mark.asyncio
async def test_mcp_wrapper_handles_unexpected_path(monkeypatch):
    """Unknown project_root must not raise — empty payload + errors[]."""
    from samvil_mcp.server import aggregate_interview_state as tool

    monkeypatch.setenv("SAMVIL_PRESET_DIR", "/tmp/nope-dir")
    raw = await tool(
        project_root="/path/that/does/not/exist", prompt="할일 앱"
    )
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    # Either the payload comes back with empty defaults, or the wrapper
    # caught an exception and returned an error envelope.
    assert "tier" in payload or "error" in payload


def test_interview_tools_registered_on_server() -> None:
    """All MCP tools the thin skill calls must be wired into server.mcp."""
    from samvil_mcp.server import mcp

    tool_map = mcp._tool_manager._tools
    names = set(tool_map.keys())
    # New aggregator
    assert "aggregate_interview_state" in names
    # Existing tools the thin skill still references directly
    for required in (
        "score_ambiguity",
        "scan_manifest",
        "route_question",
        "extract_answer_source",
        "update_answer_streak",
        "manage_tracks",
        "get_tier_phases",
        "compute_seed_readiness",
        "gate_check",
        "claim_post",
        "render_domain_context",
        "save_event",
    ):
        assert required in names, f"missing MCP tool: {required}"
