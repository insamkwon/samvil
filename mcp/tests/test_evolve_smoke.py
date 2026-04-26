"""Smoke tests for samvil-evolve (T4.2 ultra-thin migration).

The samvil-evolve skill is the autonomous Wonder→Reflect→Converge loop. It
keeps the bits that need a real shell / LLM call:

- Spawning wonder-analyst + reflect-proposer agents (per-cycle model routing).
- 4-dim eval scoring (LLM judgement on Quality/Intent/Purpose/Beyond).
- AskUserQuestion checkpoint (yes/no/edit) with autonomous-mode bypass.
- Mutating `project.seed.json` (skill body, atomic write).

What CAN be machine-pinned, and is pinned here, is the new
`aggregate_evolve_context` MCP tool the thin skill delegates to. It owns:

- Auto-trigger detection from `project.state.json` (build_retries ≥ 5,
  qa_history ≥ 2, partial_count ≥ 5).
- Mode resolution from `project.config.json` (`evolve_mode`,
  `evolve_max_cycles`, `max_total_builds` quota).
- Cycle state (current cycle index + cap_reached flag).
- 4-dim baseline inputs (interview core problem, seed.description,
  qa verdict + AC counts) — the LLM scores these in the skill body.

Idempotency: re-aggregating the same project_root yields the same dict.

The 5 evolve_checks themselves (eval/per_ac/regression/evolution/validation)
are tested in `test_convergence_check.py`. Wonder/Reflect agent prompt
construction is host-bound and not unit-tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp import evolve_aggregate


# ── Fixtures ───────────────────────────────────────────────────


def _write_seed(root: Path, **overrides) -> None:
    seed = {
        "schema_version": "3.0",
        "name": "demo-evolve",
        "version": 1,
        "description": "A todo app that helps users track tasks across devices.",
        "features": [
            {
                "name": "task_crud",
                "acceptance_criteria": [
                    {
                        "id": "AC-1",
                        "description": "user can create a task",
                        "children": [],
                        "status": "pending",
                        "evidence": [],
                    }
                ],
            }
        ],
    }
    seed.update(overrides)
    (root / "project.seed.json").write_text(json.dumps(seed), encoding="utf-8")


def _write_state(
    root: Path,
    *,
    build_retries: int = 0,
    qa_history: list[dict] | None = None,
    evolve_cycle: int | None = None,
) -> None:
    state = {
        "session_id": "test-session-evolve",
        "current_stage": "evolve",
        "build_retries": build_retries,
        "qa_history": qa_history or [],
    }
    if evolve_cycle is not None:
        state["evolve_cycle"] = evolve_cycle
    (root / "project.state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_config(root: Path, **overrides) -> None:
    config = {}
    config.update(overrides)
    (root / "project.config.json").write_text(json.dumps(config), encoding="utf-8")


def _write_qa_results(root: Path, *, verdict: str = "PASS",
                     pass_n: int = 5, fail_n: int = 0,
                     partial_n: int = 0) -> None:
    samvil = root / ".samvil"
    samvil.mkdir(exist_ok=True)
    qa = {
        "synthesis": {
            "verdict": verdict,
            "reason": f"{pass_n} pass / {fail_n} fail / {partial_n} partial",
            "pass2": {
                "counts": {
                    "pass": pass_n,
                    "fail": fail_n,
                    "partial": partial_n,
                }
            },
        }
    }
    (samvil / "qa-results.json").write_text(json.dumps(qa), encoding="utf-8")


def _write_interview(root: Path, body: str) -> None:
    (root / "interview-summary.md").write_text(body, encoding="utf-8")


# ── Tests ──────────────────────────────────────────────────────


def test_aggregate_minimal_files(tmp_path: Path) -> None:
    """Empty project → returns defaults + non-fatal errors, never raises."""
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["schema_version"] == "1.0"
    assert result["project_root"] == str(tmp_path)
    # Missing files surface as errors but the call succeeds.
    assert "errors" in result
    assert any("seed.json" in e for e in result["errors"])
    # All four sections present.
    for key in ("auto_trigger", "mode", "cycle", "four_dim_baseline"):
        assert key in result
    # Defaults
    assert result["mode"]["evolve_mode"] == "spec-only"
    assert result["mode"]["evolve_max_cycles"] == 5
    assert result["auto_trigger"]["should_offer"] is False


def test_auto_trigger_build_retries(tmp_path: Path) -> None:
    """build_retries ≥ 5 triggers auto-offer."""
    _write_seed(tmp_path)
    _write_state(tmp_path, build_retries=7)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["auto_trigger"]["should_offer"] is True
    assert result["auto_trigger"]["build_retries"] == 7
    assert any("build_retries=7" in t for t in result["auto_trigger"]["triggers"])


def test_auto_trigger_qa_history(tmp_path: Path) -> None:
    """qa_history length ≥ 2 triggers auto-offer."""
    _write_seed(tmp_path)
    _write_state(
        tmp_path,
        qa_history=[
            {"verdict": "PASS"},
            {"verdict": "FAIL"},
        ],
    )
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["auto_trigger"]["should_offer"] is True
    assert result["auto_trigger"]["qa_history_count"] == 2


def test_auto_trigger_partial_count(tmp_path: Path) -> None:
    """5 PARTIAL verdicts in qa_history trigger auto-offer."""
    _write_seed(tmp_path)
    _write_state(
        tmp_path,
        qa_history=[{"verdict": "PARTIAL"} for _ in range(5)],
    )
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["auto_trigger"]["should_offer"] is True
    assert result["auto_trigger"]["partial_count"] == 5
    # qa_history_count also fires (5 ≥ 2).
    assert len(result["auto_trigger"]["triggers"]) >= 2


def test_auto_trigger_no_triggers(tmp_path: Path) -> None:
    """Healthy run → no auto-offer."""
    _write_seed(tmp_path)
    _write_state(
        tmp_path,
        build_retries=2,
        qa_history=[{"verdict": "PASS"}],
    )
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["auto_trigger"]["should_offer"] is False
    assert result["auto_trigger"]["triggers"] == []


def test_mode_default_spec_only(tmp_path: Path) -> None:
    """No config → spec-only default with cycles=5, builds=unlimited."""
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["mode"]["evolve_mode"] == "spec-only"
    assert result["mode"]["evolve_max_cycles"] == 5
    assert result["mode"]["max_total_builds"] == 0
    assert result["mode"]["build_quota_reached"] is False


def test_mode_full_with_explicit_config(tmp_path: Path) -> None:
    """Explicit full mode with custom cycle / build caps."""
    _write_seed(tmp_path)
    _write_state(tmp_path, build_retries=3)
    _write_config(
        tmp_path,
        evolve_mode="full",
        evolve_max_cycles=3,
        max_total_builds=10,
    )
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["mode"]["evolve_mode"] == "full"
    assert result["mode"]["evolve_max_cycles"] == 3
    assert result["mode"]["max_total_builds"] == 10
    assert result["mode"]["build_quota_reached"] is False


def test_mode_build_quota_reached(tmp_path: Path) -> None:
    """build_retries ≥ max_total_builds → quota reached, force stop."""
    _write_seed(tmp_path)
    _write_state(tmp_path, build_retries=10)
    _write_config(tmp_path, evolve_mode="full", max_total_builds=10)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["mode"]["build_quota_reached"] is True


def test_mode_invalid_mode_falls_back_to_default(tmp_path: Path) -> None:
    """Unknown evolve_mode → reset to spec-only (defensive)."""
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_config(tmp_path, evolve_mode="experimental-v2-bogus")
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["mode"]["evolve_mode"] == "spec-only"


def test_cycle_explicit_counter(tmp_path: Path) -> None:
    """state.evolve_cycle is the source of truth when present."""
    _write_seed(tmp_path)
    _write_state(tmp_path, evolve_cycle=3)
    _write_config(tmp_path, evolve_max_cycles=5)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["cycle"]["current_cycle"] == 3
    assert result["cycle"]["max_cycles"] == 5
    assert result["cycle"]["cap_reached"] is False
    assert result["cycle"]["cycles_remaining"] == 2


def test_cycle_cap_reached(tmp_path: Path) -> None:
    """current_cycle ≥ max_cycles → cap_reached = True (stop next pass)."""
    _write_seed(tmp_path)
    _write_state(tmp_path, evolve_cycle=5)
    _write_config(tmp_path, evolve_max_cycles=5)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["cycle"]["cap_reached"] is True
    assert result["cycle"]["cycles_remaining"] == 0


def test_four_dim_baseline_full_inputs(tmp_path: Path) -> None:
    """Full set of inputs → all baseline fields populated."""
    _write_seed(
        tmp_path,
        description="A focused todo app for solo developers.",
        version=4,
    )
    _write_state(tmp_path)
    _write_qa_results(tmp_path, verdict="PARTIAL", pass_n=4, fail_n=1, partial_n=2)
    _write_interview(
        tmp_path,
        "# Interview Summary\n\n## 핵심 문제\n사용자가 여러 디바이스에서 할일을 동기화하는 게 너무 번거롭다.\n\n## Solution\n클라우드 동기화.\n",
    )
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    baseline = result["four_dim_baseline"]
    assert baseline["seed_name"] == "demo-evolve"
    assert baseline["seed_version"] == 4
    assert "todo app" in baseline["seed_description"]
    assert "동기화" in baseline["core_problem_excerpt"]
    assert baseline["qa_verdict"] == "PARTIAL"
    assert baseline["ac_pass_count"] == 4
    assert baseline["ac_fail_count"] == 1
    assert baseline["ac_partial_count"] == 2


def test_four_dim_baseline_english_header(tmp_path: Path) -> None:
    """English 'Core problem' header also detected."""
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_qa_results(tmp_path)
    _write_interview(
        tmp_path,
        "# Summary\n\n## Core Problem\nUsers cannot sync data across devices.\n",
    )
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert "sync data" in result["four_dim_baseline"]["core_problem_excerpt"]


def test_four_dim_baseline_no_interview(tmp_path: Path) -> None:
    """Missing interview-summary.md → empty excerpt, no error."""
    _write_seed(tmp_path)
    _write_state(tmp_path)
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["four_dim_baseline"]["core_problem_excerpt"] == ""


def test_idempotent_repeated_call(tmp_path: Path) -> None:
    """Same project_root → same dict (no hidden state, no clock-dependent fields)."""
    _write_seed(tmp_path)
    _write_state(tmp_path, build_retries=6, qa_history=[{"verdict": "PARTIAL"}])
    _write_config(tmp_path, evolve_mode="full", evolve_max_cycles=4)
    _write_qa_results(tmp_path, verdict="PARTIAL", pass_n=3, fail_n=2)
    _write_interview(tmp_path, "## 핵심 문제\nProblem text.\n")
    a = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    b = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert a == b


def test_state_fallback_to_samvil_dir(tmp_path: Path) -> None:
    """If project.state.json missing, falls back to .samvil/state.json."""
    _write_seed(tmp_path)
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "state.json").write_text(
        json.dumps({"build_retries": 8, "qa_history": []}), encoding="utf-8"
    )
    _write_qa_results(tmp_path)
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    assert result["auto_trigger"]["build_retries"] == 8
    assert result["auto_trigger"]["should_offer"] is True


def test_corrupt_qa_results_handled(tmp_path: Path) -> None:
    """Corrupted qa-results.json → empty defaults, no exception."""
    _write_seed(tmp_path)
    _write_state(tmp_path)
    samvil = tmp_path / ".samvil"
    samvil.mkdir(exist_ok=True)
    (samvil / "qa-results.json").write_text("{not valid json", encoding="utf-8")
    result = evolve_aggregate.aggregate_evolve_context(str(tmp_path))
    # Doesn't raise; baseline qa fields are empty.
    assert result["four_dim_baseline"]["qa_verdict"] == ""
    assert result["four_dim_baseline"]["ac_pass_count"] == 0


# ── MCP tool wrapper integration ───────────────────────────────


@pytest.mark.asyncio
async def test_mcp_tool_returns_valid_json(tmp_path: Path) -> None:
    """The @mcp.tool() wrapper in server.py returns parseable JSON."""
    _write_seed(tmp_path)
    _write_state(tmp_path, build_retries=6)
    _write_qa_results(tmp_path)
    from samvil_mcp.server import aggregate_evolve_context as mcp_tool

    raw = await mcp_tool(str(tmp_path))
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "1.0"
    assert parsed["auto_trigger"]["should_offer"] is True
    assert parsed["mode"]["evolve_mode"] == "spec-only"


@pytest.mark.asyncio
async def test_mcp_tool_handles_invalid_path(tmp_path: Path) -> None:
    """Even a path that doesn't exist returns parseable JSON, not an exception."""
    from samvil_mcp.server import aggregate_evolve_context as mcp_tool

    raw = await mcp_tool(str(tmp_path / "nope"))
    parsed = json.loads(raw)
    # Either a graceful empty result with errors[] OR an {"error": "..."}
    # envelope from the wrapper. Both are acceptable; just must be JSON.
    assert isinstance(parsed, dict)
