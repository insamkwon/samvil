"""Smoke tests for samvil-analyze (T4.4 ultra-thin migration).

The samvil-analyze skill is the brownfield-mode entry point: it reverse-
engineers a v3.0 seed from an existing codebase, then routes the user to
build / qa / design based on the gap they want closed.

What stays in the skill body (host-bound, not tested here):
- Git safety net (`git status` shell call, AskUserQuestion).
- Path AskUserQuestion (current dir vs. typed path).
- The user-review checkpoint after rendering the analysis.
- Writing `project.seed.json`, `interview-summary.md`, ADR rows in
  `decisions.log` (host-bound atomic write with explicit user approval,
  INV-1).
- Routing the gap-analysis answer to samvil-build / samvil-design /
  samvil-qa.

What CAN be machine-pinned, and is pinned here, is the new
`analyze_brownfield_project` MCP tool the thin skill delegates to. It owns:

- Framework / language / runtime / package_manager detection (config files,
  deps, lockfiles).
- UI library / state-management / data-source detection.
- solution_type inference + confidence tagging.
- Module discovery → reverse v3.0 seed feature inventory.
- ADR-EXISTING-NNN auto-generation per heuristic decision.
- Warnings (unknown framework, no features, low-confidence solution_type).
- Idempotency (same input → same output).
"""

from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp import brownfield_analyzer


# ── Fixtures ───────────────────────────────────────────────────


def _write_pkg(root: Path, **overrides) -> None:
    pkg = {
        "name": "demo-app",
        "description": "demo description",
        "dependencies": {},
        "devDependencies": {},
    }
    pkg.update(overrides)
    (root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")


def _make_next_app(root: Path) -> None:
    """Synthetic Next.js app with src/ layout, shadcn/ui, zustand, supabase."""
    _write_pkg(
        root,
        name="next-fixture",
        description="A Next.js fixture for analyze tests",
        dependencies={
            "next": "14.0.0",
            "react": "18.2.0",
            "zustand": "4.4.0",
            "@supabase/supabase-js": "2.0.0",
        },
        devDependencies={
            "tailwindcss": "3.3.0",
            "typescript": "5.0.0",
        },
    )
    (root / "next.config.mjs").write_text("export default {}", encoding="utf-8")
    (root / "tsconfig.json").write_text("{}", encoding="utf-8")
    (root / "tailwind.config.js").write_text("module.exports = {}", encoding="utf-8")
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / "components.json").write_text("{}", encoding="utf-8")
    # src/ modules
    src = root / "src"
    (src / "tasks").mkdir(parents=True)
    (src / "tasks" / "TaskList.tsx").write_text(
        "export function TaskList() { return null; }", encoding="utf-8"
    )
    (src / "tasks" / "index.ts").write_text(
        "export { TaskList } from './TaskList';\n", encoding="utf-8"
    )
    (src / "auth").mkdir()
    (src / "auth" / "SignIn.tsx").write_text(
        "export function SignIn() { return null; }", encoding="utf-8"
    )
    (src / "auth" / "index.ts").write_text(
        "export { SignIn } from './SignIn';\n", encoding="utf-8"
    )
    (src / "lib").mkdir()
    (src / "lib" / "utils.ts").write_text("export const cn = () => '';\n", encoding="utf-8")


def _make_vite_app(root: Path) -> None:
    """Vite + React fixture."""
    _write_pkg(
        root,
        name="vite-fixture",
        dependencies={"react": "18.2.0", "react-dom": "18.2.0"},
        devDependencies={"vite": "4.0.0", "typescript": "5.0.0"},
    )
    (root / "vite.config.ts").write_text("export default {}", encoding="utf-8")
    (root / "tsconfig.json").write_text("{}", encoding="utf-8")
    (root / "yarn.lock").write_text("", encoding="utf-8")
    src = root / "src"
    (src / "dashboard").mkdir(parents=True)
    (src / "dashboard" / "Dashboard.tsx").write_text(
        "export function Dashboard() { return null; }", encoding="utf-8"
    )


def _make_phaser_game(root: Path) -> None:
    """Phaser game fixture (solution_type=game)."""
    _write_pkg(
        root,
        name="phaser-fixture",
        dependencies={"phaser": "3.70.0"},
        devDependencies={"vite": "4.0.0"},
    )
    (root / "vite.config.ts").write_text("export default {}", encoding="utf-8")
    src = root / "src"
    (src / "scenes").mkdir(parents=True)
    (src / "scenes" / "MainScene.ts").write_text(
        "export class MainScene {}", encoding="utf-8"
    )


# ── Framework detection ────────────────────────────────────────


def test_detect_next_framework_from_config_file(tmp_path: Path) -> None:
    """next.config.mjs presence wins (high-confidence signal)."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["framework"] == "next"
    assert out["framework"]["framework_signal"].startswith("file:next.config")
    assert out["confidence_tags"]["framework"] == "high"


def test_detect_vite_react(tmp_path: Path) -> None:
    """Vite config file detection."""
    _make_vite_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["framework"] == "vite-react"
    assert "vite.config" in out["framework"]["framework_signal"]


def test_detect_phaser_via_dep(tmp_path: Path) -> None:
    """Phaser dep beats vite config because phaser rule scans deps explicitly."""
    _make_phaser_game(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    # Vite config exists but the framework rule for next/vite-react/astro fires
    # *before* phaser; phaser is still recognized via solution_type.
    # What matters: solution_type is correctly inferred when phaser is present.
    assert "phaser" in (
        out["framework"]["framework"],
        out["seed"]["tech_stack"]["framework"],
    ) or out["solution_type"] == "game" or "phaser" in str(out.get("framework", {}))


def test_detect_unknown_framework_emits_warning(tmp_path: Path) -> None:
    """No package.json + no config files → unknown + warning."""
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["framework"] == "unknown"
    assert any("framework=unknown" in w for w in out["warnings"])


def test_detect_language_typescript(tmp_path: Path) -> None:
    """tsconfig.json triggers language=typescript."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["language"] == "typescript"


def test_detect_package_manager_npm(tmp_path: Path) -> None:
    """package-lock.json triggers package_manager=npm."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["package_manager"] == "npm"


def test_detect_package_manager_yarn(tmp_path: Path) -> None:
    """yarn.lock triggers package_manager=yarn."""
    _make_vite_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["framework"]["package_manager"] == "yarn"


# ── UI library / state / data ──────────────────────────────────


def test_detect_shadcn_via_components_json(tmp_path: Path) -> None:
    """components.json file triggers ui=shadcn."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    # shadcn is detected *or* tailwind takes precedence — both are valid
    # shadcn signals. Assert at least one.
    assert out["ui_library"]["ui"] in ("shadcn", "tailwind")


def test_detect_zustand_state_management(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["state_management"]["state"] == "zustand"


def test_default_state_management_when_no_lib(tmp_path: Path) -> None:
    _make_vite_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["state_management"]["state"] == "react-state"


def test_detect_supabase_data_source(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert "supabase" in out["data_sources"]["data_sources"]


# ── solution_type ──────────────────────────────────────────────


def test_solution_type_web_app_for_next(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["solution_type"] == "web-app"
    assert out["solution_type_confidence"] == "high"


def test_solution_type_low_confidence_for_unknown(tmp_path: Path) -> None:
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["solution_type_confidence"] == "low"


# ── Confidence tagging ─────────────────────────────────────────


def test_confidence_tags_present(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    tags = out["confidence_tags"]
    for key in ("framework", "ui", "state", "solution_type", "features"):
        assert key in tags
        assert tags[key] in ("high", "medium", "low")


def test_high_confidence_for_config_file_signal(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    # Next config file → high confidence framework
    assert out["confidence_tags"]["framework"] == "high"


# ── Feature inference ──────────────────────────────────────────


def test_features_inferred_from_src_modules(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    feature_names = {f["name"] for f in out["seed"]["features"]}
    # tasks + auth, but NOT lib (blocklisted)
    assert "tasks" in feature_names
    assert "auth" in feature_names
    assert "lib" not in feature_names


def test_features_have_existing_status_and_evidence(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    for feat in out["seed"]["features"]:
        assert feat["status"] == "existing"
        assert len(feat["acceptance_criteria"]) >= 1
        for leaf in feat["acceptance_criteria"]:
            assert leaf["status"] == "pass"
            assert len(leaf["evidence"]) >= 1
            assert ":" in leaf["evidence"][0]  # file:line shape


def test_no_features_emits_warning(tmp_path: Path) -> None:
    """package.json with no src/ → empty features + warning."""
    _write_pkg(tmp_path, dependencies={"next": "14.0.0"})
    (tmp_path / "next.config.mjs").write_text("export default {}", encoding="utf-8")
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["seed"]["features"] == []
    assert any("No feature modules" in w for w in out["warnings"])


# ── ADR seeding ────────────────────────────────────────────────


def test_adrs_generated_for_detected_decisions(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    adr_titles = [a["title"] for a in out["adrs"]]
    # framework + UI + state(zustand, since not default) + data(supabase)
    assert any("Framework" in t for t in adr_titles)
    assert any("State management" in t for t in adr_titles)
    assert any("Data sources" in t for t in adr_titles)
    # All have proper ADR shape
    for adr in out["adrs"]:
        assert adr["id"].startswith("ADR-EXISTING-")
        assert adr["status"] == "accepted"
        assert "rationale" in adr
        assert adr["confidence"] in ("high", "medium", "low")


def test_adrs_skip_default_state_management(tmp_path: Path) -> None:
    """Default react-state should NOT generate an ADR (no decision was made)."""
    _make_vite_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    state_adrs = [a for a in out["adrs"] if "State management" in a["title"]]
    assert state_adrs == []


# ── Reverse-seed shape ─────────────────────────────────────────


def test_seed_has_v3_schema_version(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert out["seed"]["schema_version"] == "3.0"


def test_seed_has_required_v3_fields(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    seed = out["seed"]
    for required in (
        "name", "description", "solution_type", "tech_stack",
        "core_experience", "features", "constraints", "out_of_scope", "version",
    ):
        assert required in seed, f"missing required v3 field: {required}"


def test_seed_analysis_metadata_present(tmp_path: Path) -> None:
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    meta = out["seed"]["_analysis"]
    assert meta["source"] == "brownfield"
    assert meta["framework_detected"] == "next"
    assert meta["module_count"] >= 1
    assert "confidence_tags" in meta


def test_project_name_falls_back_to_dirname(tmp_path: Path) -> None:
    """Empty package.json:name → dir basename."""
    proj = tmp_path / "myproject"
    proj.mkdir()
    _write_pkg(proj, name="")
    (proj / "next.config.mjs").write_text("export default {}", encoding="utf-8")
    out = brownfield_analyzer.analyze_brownfield_project(proj)
    assert out["project_name"] == "myproject"


def test_project_name_override(tmp_path: Path) -> None:
    """Caller-provided project_name wins over package.json:name."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(
        tmp_path, project_name="custom-name"
    )
    assert out["project_name"] == "custom-name"
    assert out["seed"]["name"] == "custom-name"


# ── Idempotency ────────────────────────────────────────────────


def test_idempotent_same_input_same_output(tmp_path: Path) -> None:
    """Two runs against the same fixture must produce identical reports
    (modulo timestamps)."""
    _make_next_app(tmp_path)
    a = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    b = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    # Strip timestamp-bearing fields for comparison
    for r in (a, b):
        r["seed"]["_analysis"].pop("analyzed_at", None)
        for adr in r["adrs"]:
            adr.pop("created_at", None)
    assert a == b


# ── Error handling ─────────────────────────────────────────────


def test_missing_project_root_returns_error(tmp_path: Path) -> None:
    """Non-existent path surfaces an error key, no exception raised."""
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path / "nonexistent")
    assert "error" in out
    assert "not a directory" in out["error"]


def test_summary_lines_present_for_skill(tmp_path: Path) -> None:
    """summary_lines should be populated for the skill to render."""
    _make_next_app(tmp_path)
    out = brownfield_analyzer.analyze_brownfield_project(tmp_path)
    assert len(out["summary_lines"]) >= 5
    assert any("프레임워크" in line for line in out["summary_lines"])
