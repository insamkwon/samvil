"""Smoke tests for scripts/dogfood-smoke.sh (Phase D.5).

These verify that the script + fixture stay coherent. The actual
end-to-end smoke runs nightly via GitHub Actions (.github/workflows/
dogfood-nightly.yml). Locally we still run the script as part of these
tests so commit-time failures surface immediately if a fixture regresses.

What we cover here:
- The fixture seed validates against the v3.0 schema.
- The fixture has at least one feature with at least one AC.
- The shell script exists and is executable.
- Running the script exits 0 (5/5 modules consistent).
- The GH Actions workflow file is valid YAML.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dogfood-smoke.sh"
FIXTURE_DIR = REPO_ROOT / "scripts" / "dogfood-smoke-fixtures"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dogfood-nightly.yml"


def test_fixture_seed_passes_v3_schema() -> None:
    """The fixture seed must validate cleanly so the smoke can rely on it."""
    from samvil_mcp.seed_manager import validate_seed

    seed = json.loads((FIXTURE_DIR / "seed.json").read_text(encoding="utf-8"))
    result = validate_seed(seed)
    assert result.get("valid") is not False, result
    assert seed["schema_version"].startswith("3."), seed["schema_version"]


def test_fixture_has_features_and_ac_tree() -> None:
    """Fixture must exercise the AC tree path (at least one AC leaf)."""
    seed = json.loads((FIXTURE_DIR / "seed.json").read_text(encoding="utf-8"))
    features = seed.get("features") or []
    assert features, "fixture seed must have at least 1 feature"

    leaves = 0
    for f in features:
        for ac in f.get("acceptance_criteria") or []:
            if not ac.get("children"):
                leaves += 1
    assert leaves >= 1, "fixture seed must contain at least one AC leaf"


def test_fixture_state_has_qa_pass() -> None:
    """Fixture state must declare qa_status=PASS so deploy/retro fallbacks
    have something to chew on."""
    state = json.loads((FIXTURE_DIR / "state.json").read_text(encoding="utf-8"))
    assert state.get("qa_status") == "PASS"


def test_smoke_script_exists_and_executable() -> None:
    assert SCRIPT.exists(), f"missing: {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"not executable: {SCRIPT}"


def test_smoke_script_runs_against_fixture() -> None:
    """Running the smoke script must succeed (5/5 modules pass)."""
    result = subprocess.run(
        ["bash", str(SCRIPT), "--quiet"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "5/5 modules consistent" in result.stdout


def test_workflow_yaml_is_parseable() -> None:
    """GH Actions workflow file must parse cleanly so CI doesn't break silently."""
    try:
        import yaml  # type: ignore
    except ImportError:
        pytest.skip("PyYAML not available; skipping workflow parse check")
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML normalizes the `on:` key to True (boolean) — accept both forms.
    on_key = data.get("on") or data.get(True) or data.get("on:")
    assert on_key is not None, f"workflow missing 'on' key: keys={list(data.keys())}"
    assert "jobs" in data
    job = next(iter(data["jobs"].values()))
    steps = [s for s in job["steps"] if "run" in s]
    assert any("dogfood-smoke.sh" in s["run"] for s in steps), (
        "workflow must invoke scripts/dogfood-smoke.sh"
    )
