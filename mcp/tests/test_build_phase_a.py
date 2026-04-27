"""Unit tests for build_phase_a.py — boot aggregator (T4.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import build_phase_a


def _write(path: Path, payload: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed(name: str = "demo", solution_type: str = "web-app", framework: str = "nextjs") -> dict:
    return {
        "schema_version": "3.0",
        "name": name,
        "solution_type": solution_type,
        "tech_stack": {"framework": framework},
        "features": [
            {
                "name": "feat-1",
                "description": "a feature",
                "acceptance_criteria": [{"id": "AC-1", "description": "do thing"}],
            }
        ],
    }


# ── Stack resolution ────────────────────────────────────────────────


def test_resolves_web_app_build_verify(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["solution_type"] == "web-app"
    assert "npm run build" in out["build_verify"]["command"]
    assert out["build_verify"]["log_path"] == ".samvil/build.log"


def test_resolves_game_uses_tsc(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed(solution_type="game", framework="phaser"))
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "tsc --noEmit" in out["build_verify"]["command"]


def test_resolves_mobile_uses_expo_export(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed(solution_type="mobile-app", framework="expo"))
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "expo export" in out["build_verify"]["command"]


def test_resolves_automation_python_uses_py_compile(tmp_path: Path) -> None:
    seed = _seed(solution_type="automation", framework="python-script")
    seed["implementation"] = {"runtime": "python"}
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "py_compile" in out["build_verify"]["command"]
    assert out["build_verify"]["language"] == "python"


def test_resolves_automation_node_uses_tsc(tmp_path: Path) -> None:
    seed = _seed(solution_type="automation", framework="node-script")
    seed["implementation"] = {"runtime": "node"}
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "tsc --noEmit" in out["build_verify"]["command"]


def test_resolves_automation_cc_skill_no_build(tmp_path: Path) -> None:
    seed = _seed(solution_type="automation", framework="cc-skill")
    seed["implementation"] = {"runtime": "cc-skill"}
    _write(tmp_path / "project.seed.json", seed)
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["build_verify"]["command"] == ""


def test_resolves_dashboard_uses_npm_build(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed(solution_type="dashboard"))
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "npm run build" in out["build_verify"]["command"]


def test_unknown_solution_type_falls_back_to_web_app(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed(solution_type="fictional"))
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert "npm run build" in out["build_verify"]["command"]
    assert any("unknown solution_type" in n for n in out["notes"])


# ── Recipe path mapping ──────────────────────────────────────────────


def test_recipe_path_per_solution_type(tmp_path: Path) -> None:
    for st, expected in [
        ("web-app", "references/web-recipes.md"),
        ("game", "references/game-recipes.md"),
        ("automation", "references/automation-recipes.md"),
        ("mobile-app", "references/mobile-recipes.md"),
        ("dashboard", "references/dashboard-recipes.md"),
    ]:
        _write(tmp_path / "project.seed.json", _seed(solution_type=st))
        out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
        assert out["recipe_path"] == expected


# ── Paths ────────────────────────────────────────────────────────────


def test_paths_contain_all_critical_files(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    paths = out["paths"]
    for key in ("seed", "state", "config", "blueprint", "build_log", "fix_log",
                "handoff", "events", "rate_budget", "sanity_log"):
        assert key in paths, f"missing path key: {key}"


# ── State + resume hint ─────────────────────────────────────────────


def test_resume_hint_pulls_completed_features(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    _write(tmp_path / "project.state.json", {
        "session_id": "sess-123",
        "current_stage": "build",
        "completed_features": ["feat-A", "feat-B"],
    })
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["state_loaded"] is True
    assert out["resume_hint"]["session_id"] == "sess-123"
    assert out["resume_hint"]["completed_features"] == ["feat-A", "feat-B"]


def test_missing_seed_emits_error(tmp_path: Path) -> None:
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["seed_loaded"] is False
    assert any("project.seed.json" in e for e in out["errors"])


# ── Phase A.6 sanity scan ───────────────────────────────────────────


def test_sanity_passes_on_empty_project(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    assert out["sanity"]["passed"] is True
    assert out["sanity"]["failures"] == []


def test_sanity_detects_empty_package_json(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    (tmp_path / "package.json").write_text("", encoding="utf-8")
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    assert out["sanity"]["passed"] is False
    assert any("empty config file: package.json" in f for f in out["sanity"]["failures"])


def test_sanity_detects_unsubstituted_template_vars(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    src = tmp_path / "src" / "main.ts"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("const apiKey = '{{API_KEY}}';\n", encoding="utf-8")
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    assert out["sanity"]["passed"] is False
    assert any("unsubstituted template variable" in f for f in out["sanity"]["failures"])


def test_sanity_detects_broken_relative_import(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    src = tmp_path / "src" / "main.ts"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("import x from './missing-module';\n", encoding="utf-8")
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    assert out["sanity"]["passed"] is False
    assert any("broken imports" in f for f in out["sanity"]["failures"])


def test_sanity_skipped_when_run_sanity_checks_false(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["sanity"]["skipped"] is True


# ── Schema stability ────────────────────────────────────────────────


def test_schema_version_present(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=False)
    assert out["schema_version"] == build_phase_a.BUILD_PHASE_A_SCHEMA_VERSION


def test_returns_serializable_json(tmp_path: Path) -> None:
    _write(tmp_path / "project.seed.json", _seed())
    out = build_phase_a.aggregate_build_phase_a(tmp_path, run_sanity_checks=True)
    # Round-trips cleanly.
    assert json.loads(json.dumps(out)) == out
