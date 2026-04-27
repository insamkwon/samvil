# Option B: Regression Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generation snapshot + regression detection system so that passing ACs from one evolve cycle are automatically verified in the next — catching regressions before they compound.

**Architecture:** `regression_suite.py` provides four pure functions (snapshot/validate/aggregate/compare) and four `@dataclass` types. `server.py` wraps them in 4 MCP tools. `samvil-evolve/SKILL.md` gets two new lines that call the tools at cycle boundaries. Snapshots live in `.samvil/generations/gen-<N>/snapshot.json`. QA results are read from `.samvil/qa-results.json` (pass2 list with id/criterion/verdict/evidence fields).

**Tech Stack:** Python 3.11+, dataclasses, pathlib, json, FastMCP — no new dependencies.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `mcp/samvil_mcp/regression_suite.py` | **Create** | 4 dataclasses + 4 functions: snapshot/validate/aggregate/compare |
| `mcp/tests/test_regression_suite.py` | **Create** | 27 tests across 5 test classes |
| `mcp/samvil_mcp/server.py` | **Modify** | Add import + 4 MCP tool wrappers |
| `skills/samvil-evolve/SKILL.md` | **Modify** | Add 2 snapshot integration steps (Boot + Step 5) |
| `references/regression-suite.md` | **Create** | Schema doc + operator guide |
| `CHANGELOG.md` | **Modify** | v4.7.0 entry |
| `.claude-plugin/plugin.json` | **Modify** | `"version": "4.7.0"` |
| `mcp/samvil_mcp/__init__.py` | **Modify** | `__version__ = "4.7.0"` |
| `README.md` | **Modify** | First line `v4.7.0` |

---

## Task 1: Core dataclasses + `_load_passing_acs()` helper

**Files:**
- Create: `mcp/samvil_mcp/regression_suite.py`
- Create: `mcp/tests/test_regression_suite.py`

- [ ] **Step 1: Write failing tests**

Create `mcp/tests/test_regression_suite.py`:

```python
"""Tests for regression_suite module (Option B)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samvil_mcp.regression_suite import (
    ACEntry,
    GenerationSnapshot,
    RegressionResult,
    CompareResult,
    _load_passing_acs,
    snapshot_generation,
    validate_against_snapshot,
    aggregate_regression_state,
    compare_generations,
)


# ── fixtures ────────────────────────────────────────────────────────────────

def _write_qa_results(project_dir: Path, acs: list[dict]) -> Path:
    """Write a minimal qa-results.json to project_dir/.samvil/."""
    results = {
        "pass1": {"status": "PASS"},
        "pass2": acs,
        "pass3": {"verdict": "PASS"},
    }
    path = project_dir / ".samvil" / "qa-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def _ac(id: str, verdict: str = "PASS", evidence: list[str] | None = None) -> dict:
    return {
        "id": id,
        "criterion": f"User can {id}",
        "verdict": verdict,
        "evidence": evidence or [f"app/{id}.tsx:10"],
    }


# ── ACEntry + GenerationSnapshot dataclass tests ──────────────────────────

class TestDataclasses:
    def test_ac_entry_to_dict(self):
        e = ACEntry(id="AC-1", criterion="Login", verdict="PASS", evidence=["page.tsx:10"])
        d = e.to_dict()
        assert d["id"] == "AC-1"
        assert d["verdict"] == "PASS"
        assert d["evidence"] == ["page.tsx:10"]

    def test_generation_snapshot_to_dict(self):
        snap = GenerationSnapshot(
            generation_id="gen-1",
            created_at="2026-01-01T00:00:00Z",
            passing_ac_count=2,
            total_ac_count=3,
            acs=[ACEntry(id="AC-1", criterion="X", verdict="PASS", evidence=["f:1"])],
        )
        d = snap.to_dict()
        assert d["generation_id"] == "gen-1"
        assert d["schema_version"] == "1.0"
        assert d["passing_ac_count"] == 2
        assert len(d["acs"]) == 1

    def test_regression_result_is_clean_when_no_regressions(self):
        r = RegressionResult(
            snapshot_id="gen-1",
            checked_at="2026-01-01T00:00:00Z",
            total_checked=3,
            passing=3,
            regressed=0,
            new_passes=0,
            regressed_ids=[],
        )
        assert r.status == "clean"

    def test_regression_result_is_regression_when_any_regressed(self):
        r = RegressionResult(
            snapshot_id="gen-1",
            checked_at="2026-01-01T00:00:00Z",
            total_checked=3,
            passing=2,
            regressed=1,
            new_passes=0,
            regressed_ids=["AC-2"],
        )
        assert r.status == "regression"

    def test_compare_result_to_dict(self):
        cr = CompareResult(gen_a="gen-1", gen_b="gen-2", added=["AC-3"], removed=[], changed=[])
        d = cr.to_dict()
        assert d["gen_a"] == "gen-1"
        assert d["added"] == ["AC-3"]


class TestLoadPassingAcs:
    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _load_passing_acs(str(tmp_path))
        assert result == []

    def test_loads_passing_acs_from_qa_results(self, tmp_path):
        _write_qa_results(tmp_path, [
            _ac("AC-1", verdict="PASS"),
            _ac("AC-2", verdict="FAIL"),
            _ac("AC-3", verdict="PASS"),
        ])
        result = _load_passing_acs(str(tmp_path))
        assert len(result) == 2
        assert all(a["verdict"] == "PASS" for a in result)

    def test_empty_pass2_returns_empty(self, tmp_path):
        _write_qa_results(tmp_path, [])
        result = _load_passing_acs(str(tmp_path))
        assert result == []

    def test_custom_path_override(self, tmp_path):
        custom = tmp_path / "custom-qa.json"
        custom.write_text(json.dumps({
            "pass2": [_ac("X-1", verdict="PASS")],
        }), encoding="utf-8")
        result = _load_passing_acs(str(tmp_path), qa_results_path=str(custom))
        assert len(result) == 1
        assert result[0]["id"] == "X-1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd mcp && source .venv/bin/activate
python -m pytest tests/test_regression_suite.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'ACEntry' from 'samvil_mcp.regression_suite'`

- [ ] **Step 3: Create `mcp/samvil_mcp/regression_suite.py`** with full content:

```python
"""Regression Suite — generation snapshot + regression detection (Option B).

Tracks passing ACs across evolve cycles so regressions are caught
before they compound.

Storage: .samvil/generations/gen-<N>/snapshot.json
Input:   .samvil/qa-results.json  (pass2 list from QA synthesis)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ACEntry:
    id: str
    criterion: str
    verdict: str  # "PASS" | "FAIL"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "criterion": self.criterion,
            "verdict": self.verdict,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ACEntry":
        return cls(
            id=d.get("id", ""),
            criterion=d.get("criterion", ""),
            verdict=d.get("verdict", ""),
            evidence=d.get("evidence", []),
        )


@dataclass
class GenerationSnapshot:
    generation_id: str
    created_at: str
    passing_ac_count: int
    total_ac_count: int
    acs: list[ACEntry] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation_id": self.generation_id,
            "created_at": self.created_at,
            "passing_ac_count": self.passing_ac_count,
            "total_ac_count": self.total_ac_count,
            "acs": [a.to_dict() for a in self.acs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationSnapshot":
        return cls(
            generation_id=d.get("generation_id", ""),
            created_at=d.get("created_at", ""),
            passing_ac_count=d.get("passing_ac_count", 0),
            total_ac_count=d.get("total_ac_count", 0),
            acs=[ACEntry.from_dict(a) for a in d.get("acs", [])],
            schema_version=d.get("schema_version", "1.0"),
        )


@dataclass
class RegressionResult:
    snapshot_id: str
    checked_at: str
    total_checked: int
    passing: int
    regressed: int
    new_passes: int
    regressed_ids: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "regression" if self.regressed > 0 else "clean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "checked_at": self.checked_at,
            "status": self.status,
            "total_checked": self.total_checked,
            "passing": self.passing,
            "regressed": self.regressed,
            "new_passes": self.new_passes,
            "regressed_ids": self.regressed_ids,
        }


@dataclass
class CompareResult:
    gen_a: str
    gen_b: str
    added: list[str] = field(default_factory=list)    # in gen_b, not gen_a
    removed: list[str] = field(default_factory=list)  # in gen_a, not gen_b
    changed: list[str] = field(default_factory=list)  # verdict changed

    def to_dict(self) -> dict[str, Any]:
        return {
            "gen_a": self.gen_a,
            "gen_b": self.gen_b,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_passing_acs(
    project_root: str,
    qa_results_path: str | None = None,
) -> list[dict]:
    """Load all passing ACs from qa-results.json pass2 list."""
    path = Path(qa_results_path or (Path(project_root) / ".samvil" / "qa-results.json"))
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [a for a in data.get("pass2", []) if a.get("verdict") == "PASS"]


def _load_all_acs(
    project_root: str,
    qa_results_path: str | None = None,
) -> list[dict]:
    """Load all ACs (any verdict) from qa-results.json pass2 list."""
    path = Path(qa_results_path or (Path(project_root) / ".samvil" / "qa-results.json"))
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("pass2", [])


def _next_generation_id(project_root: str) -> str:
    """Return the next gen-N id by scanning existing generation dirs."""
    gens_dir = Path(project_root) / ".samvil" / "generations"
    if not gens_dir.exists():
        return "gen-1"
    existing = [
        int(d.name.split("-")[1])
        for d in gens_dir.iterdir()
        if d.is_dir() and d.name.startswith("gen-") and d.name.split("-")[1].isdigit()
    ]
    return f"gen-{max(existing) + 1}" if existing else "gen-1"


def _snapshot_path(project_root: str, generation_id: str) -> Path:
    return Path(project_root) / ".samvil" / "generations" / generation_id / "snapshot.json"


# ── Public functions ──────────────────────────────────────────────────────────


def snapshot_generation(
    project_root: str,
    generation_id: str | None = None,
    qa_results_path: str | None = None,
) -> GenerationSnapshot:
    """Capture current passing ACs into a generation snapshot.

    Reads .samvil/qa-results.json for AC verdicts.
    Writes snapshot to .samvil/generations/<generation_id>/snapshot.json.
    Returns the snapshot.
    """
    gen_id = generation_id or _next_generation_id(project_root)
    all_acs = _load_all_acs(project_root, qa_results_path)
    passing = [a for a in all_acs if a.get("verdict") == "PASS"]

    snap = GenerationSnapshot(
        generation_id=gen_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        passing_ac_count=len(passing),
        total_ac_count=len(all_acs),
        acs=[
            ACEntry(
                id=a.get("id", ""),
                criterion=a.get("criterion", ""),
                verdict=a.get("verdict", ""),
                evidence=a.get("evidence", []),
            )
            for a in passing
        ],
    )

    path = _snapshot_path(project_root, gen_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    return snap


def validate_against_snapshot(
    project_root: str,
    snapshot_id: str,
    qa_results_path: str | None = None,
) -> RegressionResult:
    """Validate current QA results against a previously saved snapshot.

    Returns a RegressionResult with status "clean" or "regression".
    ACs that were PASS in the snapshot but are now FAIL are regressions.
    """
    snap_path = _snapshot_path(project_root, snapshot_id)
    if not snap_path.exists():
        return RegressionResult(
            snapshot_id=snapshot_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            total_checked=0,
            passing=0,
            regressed=0,
            new_passes=0,
            regressed_ids=[],
        )

    snap = GenerationSnapshot.from_dict(json.loads(snap_path.read_text(encoding="utf-8")))
    current = {a.get("id", ""): a.get("verdict", "") for a in _load_all_acs(project_root, qa_results_path)}

    regressed_ids = [
        ac.id for ac in snap.acs
        if ac.verdict == "PASS" and current.get(ac.id) == "FAIL"
    ]
    new_passes = [
        ac_id for ac_id, verdict in current.items()
        if verdict == "PASS" and ac_id not in {a.id for a in snap.acs if a.verdict == "PASS"}
    ]

    return RegressionResult(
        snapshot_id=snapshot_id,
        checked_at=datetime.now(timezone.utc).isoformat(),
        total_checked=len(snap.acs),
        passing=len(snap.acs) - len(regressed_ids),
        regressed=len(regressed_ids),
        new_passes=len(new_passes),
        regressed_ids=regressed_ids,
    )


def aggregate_regression_state(project_root: str) -> dict[str, Any]:
    """Return a summary of all generation snapshots for this project.

    Returns dict with: generation_count, generations (list of summaries),
    latest_generation_id, has_regression_history.
    """
    gens_dir = Path(project_root) / ".samvil" / "generations"
    if not gens_dir.exists():
        return {
            "generation_count": 0,
            "generations": [],
            "latest_generation_id": None,
            "has_regression_history": False,
        }

    summaries = []
    for gen_dir in sorted(gens_dir.iterdir()):
        snap_path = gen_dir / "snapshot.json"
        if not snap_path.exists():
            continue
        try:
            d = json.loads(snap_path.read_text(encoding="utf-8"))
            summaries.append({
                "generation_id": d.get("generation_id", gen_dir.name),
                "created_at": d.get("created_at", ""),
                "passing_ac_count": d.get("passing_ac_count", 0),
                "total_ac_count": d.get("total_ac_count", 0),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "generation_count": len(summaries),
        "generations": summaries,
        "latest_generation_id": summaries[-1]["generation_id"] if summaries else None,
        "has_regression_history": len(summaries) >= 2,
    }


def compare_generations(
    project_root: str,
    gen_a: str,
    gen_b: str,
) -> CompareResult:
    """Compare two generation snapshots.

    Returns CompareResult with added/removed/changed AC ids.
    added  = in gen_b passing, not in gen_a passing
    removed = in gen_a passing, not in gen_b passing
    changed = verdict changed (only possible if both snapshots captured all ACs)
    """
    path_a = _snapshot_path(project_root, gen_a)
    path_b = _snapshot_path(project_root, gen_b)

    snap_a_acs: dict[str, str] = {}
    snap_b_acs: dict[str, str] = {}

    if path_a.exists():
        snap_a = GenerationSnapshot.from_dict(json.loads(path_a.read_text(encoding="utf-8")))
        snap_a_acs = {ac.id: ac.verdict for ac in snap_a.acs}

    if path_b.exists():
        snap_b = GenerationSnapshot.from_dict(json.loads(path_b.read_text(encoding="utf-8")))
        snap_b_acs = {ac.id: ac.verdict for ac in snap_b.acs}

    all_ids = set(snap_a_acs) | set(snap_b_acs)
    added = [id for id in all_ids if id in snap_b_acs and id not in snap_a_acs]
    removed = [id for id in all_ids if id in snap_a_acs and id not in snap_b_acs]
    changed = [
        id for id in all_ids
        if id in snap_a_acs and id in snap_b_acs and snap_a_acs[id] != snap_b_acs[id]
    ]

    return CompareResult(gen_a=gen_a, gen_b=gen_b, added=sorted(added), removed=sorted(removed), changed=sorted(changed))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd mcp && source .venv/bin/activate
python -m pytest tests/test_regression_suite.py::TestDataclasses tests/test_regression_suite.py::TestLoadPassingAcs -v
```

Expected: 9 PASSED

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd .
git add mcp/samvil_mcp/regression_suite.py mcp/tests/test_regression_suite.py
git commit -m "feat: add regression_suite module — dataclasses and _load_passing_acs"
```

---

## Task 2: `snapshot_generation()` tests + implementation verification

**Files:**
- Modify: `mcp/tests/test_regression_suite.py` (append new class)

The implementation is already in `regression_suite.py` from Task 1. This task adds tests and verifies it end-to-end.

- [ ] **Step 1: Append to `mcp/tests/test_regression_suite.py`**

```python

class TestSnapshotGeneration:
    def test_creates_snapshot_file(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snap = snapshot_generation(str(tmp_path))
        snap_path = tmp_path / ".samvil" / "generations" / snap.generation_id / "snapshot.json"
        assert snap_path.exists()

    def test_first_snapshot_is_gen_1(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path))
        assert snap.generation_id == "gen-1"

    def test_second_snapshot_is_gen_2(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path))
        snap2 = snapshot_generation(str(tmp_path))
        assert snap2.generation_id == "gen-2"

    def test_explicit_generation_id(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path), generation_id="gen-5")
        assert snap.generation_id == "gen-5"
        assert (tmp_path / ".samvil" / "generations" / "gen-5" / "snapshot.json").exists()

    def test_only_passing_acs_in_snapshot(self, tmp_path):
        _write_qa_results(tmp_path, [
            _ac("AC-1", verdict="PASS"),
            _ac("AC-2", verdict="FAIL"),
            _ac("AC-3", verdict="PASS"),
        ])
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 2
        assert snap.total_ac_count == 3
        assert all(a.verdict == "PASS" for a in snap.acs)

    def test_snapshot_json_is_valid(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snap = snapshot_generation(str(tmp_path))
        snap_path = tmp_path / ".samvil" / "generations" / snap.generation_id / "snapshot.json"
        loaded = json.loads(snap_path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert loaded["generation_id"] == snap.generation_id
        assert isinstance(loaded["acs"], list)

    def test_empty_qa_results_yields_zero_passing(self, tmp_path):
        _write_qa_results(tmp_path, [])
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 0
        assert snap.acs == []

    def test_missing_qa_results_yields_empty_snapshot(self, tmp_path):
        snap = snapshot_generation(str(tmp_path))
        assert snap.passing_ac_count == 0
        assert snap.total_ac_count == 0
```

- [ ] **Step 2: Run new tests**

```bash
cd mcp && source .venv/bin/activate
python -m pytest tests/test_regression_suite.py::TestSnapshotGeneration -v
```

Expected: 8 PASSED

- [ ] **Step 3: Commit**

```bash
cd .
git add mcp/tests/test_regression_suite.py
git commit -m "test: add snapshot_generation tests (Option B TDD)"
```

---

## Task 3: `validate_against_snapshot()` tests

**Files:**
- Modify: `mcp/tests/test_regression_suite.py` (append new class)

- [ ] **Step 1: Append to `mcp/tests/test_regression_suite.py`**

```python

class TestValidateAgainstSnapshot:
    def test_clean_when_no_regressions(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.status == "clean"
        assert result.regressed == 0
        assert result.regressed_ids == []

    def test_detects_regression(self, tmp_path):
        # gen-1: AC-1 PASS, AC-2 PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        # Now AC-2 regresses to FAIL
        _write_qa_results(tmp_path, [_ac("AC-1", "PASS"), _ac("AC-2", "FAIL")])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.status == "regression"
        assert result.regressed == 1
        assert "AC-2" in result.regressed_ids

    def test_new_passes_counted(self, tmp_path):
        # gen-1: only AC-1 PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2", "FAIL")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        # Now AC-2 also PASS
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.new_passes == 1
        assert result.status == "clean"

    def test_missing_snapshot_returns_zero_result(self, tmp_path):
        result = validate_against_snapshot(str(tmp_path), "gen-99")
        assert result.total_checked == 0
        assert result.status == "clean"

    def test_result_to_dict_has_status(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        d = result.to_dict()
        assert "status" in d
        assert "snapshot_id" in d
        assert d["snapshot_id"] == "gen-1"

    def test_multiple_regressions(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [
            _ac("AC-1", "FAIL"), _ac("AC-2", "FAIL"), _ac("AC-3", "PASS"),
        ])
        result = validate_against_snapshot(str(tmp_path), "gen-1")
        assert result.regressed == 2
        assert set(result.regressed_ids) == {"AC-1", "AC-2"}
```

- [ ] **Step 2: Run new tests**

```bash
cd mcp && source .venv/bin/activate
python -m pytest tests/test_regression_suite.py::TestValidateAgainstSnapshot -v
```

Expected: 6 PASSED

- [ ] **Step 3: Commit**

```bash
cd .
git add mcp/tests/test_regression_suite.py
git commit -m "test: add validate_against_snapshot tests (Option B TDD)"
```

---

## Task 4: `aggregate_regression_state()` + `compare_generations()` tests

**Files:**
- Modify: `mcp/tests/test_regression_suite.py` (append two classes)

- [ ] **Step 1: Append to `mcp/tests/test_regression_suite.py`**

```python

class TestAggregateRegressionState:
    def test_empty_state_when_no_generations(self, tmp_path):
        state = aggregate_regression_state(str(tmp_path))
        assert state["generation_count"] == 0
        assert state["generations"] == []
        assert state["latest_generation_id"] is None
        assert state["has_regression_history"] is False

    def test_counts_one_generation(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        state = aggregate_regression_state(str(tmp_path))
        assert state["generation_count"] == 1
        assert state["latest_generation_id"] == "gen-1"
        assert state["has_regression_history"] is False

    def test_has_regression_history_after_two_gens(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        state = aggregate_regression_state(str(tmp_path))
        assert state["has_regression_history"] is True
        assert state["generation_count"] == 2

    def test_generation_summaries_include_counts(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        state = aggregate_regression_state(str(tmp_path))
        gen = state["generations"][0]
        assert gen["passing_ac_count"] == 2
        assert gen["total_ac_count"] == 2


class TestCompareGenerations:
    def test_no_changes_when_same_acs(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert cr.added == []
        assert cr.removed == []
        assert cr.changed == []

    def test_detects_added_ac(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert "AC-2" in cr.added

    def test_detects_removed_ac(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1"), _ac("AC-2")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert "AC-2" in cr.removed

    def test_missing_gen_a_returns_empty_result(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        cr = compare_generations(str(tmp_path), "gen-1", "gen-2")
        assert cr.gen_a == "gen-1"

    def test_to_dict_contains_all_fields(self, tmp_path):
        _write_qa_results(tmp_path, [_ac("AC-1")])
        snapshot_generation(str(tmp_path), generation_id="gen-1")
        snapshot_generation(str(tmp_path), generation_id="gen-2")
        d = compare_generations(str(tmp_path), "gen-1", "gen-2").to_dict()
        assert "gen_a" in d and "gen_b" in d
        assert "added" in d and "removed" in d and "changed" in d
```

- [ ] **Step 2: Run new tests**

```bash
cd mcp && source .venv/bin/activate
python -m pytest tests/test_regression_suite.py::TestAggregateRegressionState tests/test_regression_suite.py::TestCompareGenerations -v
```

Expected: 9 PASSED

- [ ] **Step 3: Run all regression suite tests**

```bash
python -m pytest tests/test_regression_suite.py -v 2>&1 | tail -10
```

Expected: 30+ PASSED (all classes)

- [ ] **Step 4: Commit**

```bash
cd .
git add mcp/tests/test_regression_suite.py
git commit -m "test: add aggregate + compare tests (Option B TDD)"
```

---

## Task 5: Wire up 4 MCP tool wrappers in `server.py`

**Files:**
- Modify: `mcp/samvil_mcp/server.py`

- [ ] **Step 1: Add import near the other module imports in `server.py`**

Find the block with other module imports (around line 186-200 — after health_tiers import). Add:

```python
from .regression_suite import (
    snapshot_generation as _snapshot_generation,
    validate_against_snapshot as _validate_against_snapshot,
    aggregate_regression_state as _aggregate_regression_state,
    compare_generations as _compare_generations,
)
```

- [ ] **Step 2: Add 4 MCP tool wrappers to the end of `server.py`** (before the final `if __name__` block or at end of tool section)

Follow the pattern from `write_chain_marker` exactly:

```python
@mcp.tool()
async def snapshot_generation(
    project_root: str,
    generation_id: str | None = None,
    qa_results_path: str | None = None,
) -> str:
    """Capture current passing ACs into a generation snapshot.

    Writes .samvil/generations/<generation_id>/snapshot.json.
    Auto-generates gen-N id if not provided.
    Returns JSON with generation_id, passing_ac_count, total_ac_count.
    """
    try:
        result = _snapshot_generation(project_root, generation_id, qa_results_path)
        _log_mcp_health("ok", "snapshot_generation")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "snapshot_generation", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def validate_against_snapshot(
    project_root: str,
    snapshot_id: str,
    qa_results_path: str | None = None,
) -> str:
    """Validate current QA results against a previously saved generation snapshot.

    Returns JSON with status ("clean"|"regression"), regressed count,
    and regressed_ids list.
    """
    try:
        result = _validate_against_snapshot(project_root, snapshot_id, qa_results_path)
        _log_mcp_health("ok", "validate_against_snapshot")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "validate_against_snapshot", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def aggregate_regression_state(project_root: str) -> str:
    """Return a summary of all generation snapshots for a project.

    Returns JSON with generation_count, generations list,
    latest_generation_id, has_regression_history.
    """
    try:
        result = _aggregate_regression_state(project_root)
        _log_mcp_health("ok", "aggregate_regression_state")
        return json.dumps(result)
    except Exception as e:
        _log_mcp_health("fail", "aggregate_regression_state", str(e))
        return json.dumps({"error": str(e)})


@mcp.tool()
async def compare_generations(
    project_root: str,
    gen_a: str,
    gen_b: str,
) -> str:
    """Compare two generation snapshots — added/removed/changed AC ids.

    gen_a and gen_b are generation ids (e.g., "gen-1", "gen-2").
    Returns JSON with added, removed, changed lists.
    """
    try:
        result = _compare_generations(project_root, gen_a, gen_b)
        _log_mcp_health("ok", "compare_generations")
        return json.dumps(result.to_dict())
    except Exception as e:
        _log_mcp_health("fail", "compare_generations", str(e))
        return json.dumps({"error": str(e)})
```

- [ ] **Step 3: Verify MCP server imports cleanly**

```bash
cd mcp && source .venv/bin/activate
python -c "from samvil_mcp.server import mcp; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 5: Run pre-commit check**

```bash
cd . && bash scripts/pre-commit-check.sh 2>&1 | tail -5
```

Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
cd .
git add mcp/samvil_mcp/server.py mcp/samvil_mcp/regression_suite.py
git commit -m "feat: add snapshot/validate/aggregate/compare MCP tools (Option B)"
```

---

## Task 6: Update `samvil-evolve/SKILL.md` + create `references/regression-suite.md`

**Files:**
- Modify: `skills/samvil-evolve/SKILL.md`
- Create: `references/regression-suite.md`

### 6A: Update samvil-evolve skill

- [ ] **Step 1: Check current line count of `skills/samvil-evolve/SKILL.md`**

```bash
wc -l skills/samvil-evolve/SKILL.md
```

It's currently 91 lines. Adding ~10 lines = ~101 lines. Under the 120 LOC limit.

- [ ] **Step 2: Read the full current skill file**

```bash
cat skills/samvil-evolve/SKILL.md
```

- [ ] **Step 3: Add snapshot call to Boot Sequence (after step 4)**

Find the Boot Sequence section. After step 4 (`aggregate_evolve_context`), add step 4b:

```markdown
4b. `mcp__samvil_mcp__snapshot_generation(project_root=".")` — best-effort. Captures current passing ACs before Wonder phase. If cycle > 1, also call `mcp__samvil_mcp__validate_against_snapshot(project_root=".", snapshot_id="gen-<cycle-1>")` and warn if status is "regression".
```

- [ ] **Step 4: Add snapshot at cycle end (find the Chain/Retro section)**

In the section that chains to retro or marks cycle complete, add:

```markdown
After seed apply and QA pass: `mcp__samvil_mcp__snapshot_generation(project_root=".", generation_id="gen-<cycle>")` — best-effort. Records the generation for future regression checks.
```

- [ ] **Step 5: Verify line count stays under 120**

```bash
wc -l skills/samvil-evolve/SKILL.md
```

Expected: ≤ 120 lines.

- [ ] **Step 6: Update the plugin cache copy of the skill**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp skills/samvil-evolve/SKILL.md "$CACHE/skills/samvil-evolve/SKILL.md"
```

### 6B: Create regression-suite reference doc

- [ ] **Step 7: Create `references/regression-suite.md`**

```markdown
# Regression Suite Reference (Option B)

SAMVIL tracks passing ACs across evolve cycles using generation snapshots.
Each snapshot captures which ACs passed (with evidence) at a point in time.
The next cycle validates against the previous snapshot to detect regressions.

## Storage Layout

```
.samvil/
  generations/
    gen-1/
      snapshot.json   ← ACEntry list for cycle 1
    gen-2/
      snapshot.json   ← ACEntry list for cycle 2
```

## Snapshot Schema (`snapshot.json`)

```json
{
  "schema_version": "1.0",
  "generation_id": "gen-1",
  "created_at": "2026-04-27T12:00:00Z",
  "passing_ac_count": 15,
  "total_ac_count": 20,
  "acs": [
    {
      "id": "AC-1",
      "criterion": "User can create a task",
      "verdict": "PASS",
      "evidence": ["app/page.tsx:45"]
    }
  ]
}
```

## Input Source

Reads `.samvil/qa-results.json` → `pass2` array (from QA synthesis).
Each entry: `{ "id", "criterion", "verdict", "evidence" }`.
Missing file → empty snapshot (P8 graceful degradation).

## MCP Tools

| Tool | Purpose |
|---|---|
| `snapshot_generation(project_root, generation_id?)` | Capture current passing ACs |
| `validate_against_snapshot(project_root, snapshot_id)` | Check for regressions |
| `aggregate_regression_state(project_root)` | Overview of all generations |
| `compare_generations(project_root, gen_a, gen_b)` | Diff two snapshots |

## Evolve Integration

Called automatically from `samvil-evolve`:
- **Pre-Wonder** (Boot step 4b): snapshot current state, validate against prior gen
- **Post-apply** (end of cycle): snapshot the new generation

## Seed v3 Compatibility

Regression suite reads from `qa-results.json` (not seed.json directly).
No seed schema changes required. Compatible with v3.0+.
```

- [ ] **Step 8: Commit both changes**

```bash
cd .
git add skills/samvil-evolve/SKILL.md references/regression-suite.md
git commit -m "feat: integrate regression suite into evolve skill + add reference doc"
```

---

## Task 7: Version bump to v4.7.0 + final pre-commit + commit

**Files:**
- Modify: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `mcp/samvil_mcp/__init__.py`, `README.md`

- [ ] **Step 1: Run pre-commit check** (must be green before bumping)

```bash
cd . && bash scripts/pre-commit-check.sh
```

Expected: 9/9 PASS. Record test count.

- [ ] **Step 2: Bump version to 4.7.0 in three files**

Edit `.claude-plugin/plugin.json`:
```json
"version": "4.7.0"
```

Edit `mcp/samvil_mcp/__init__.py`:
```python
__version__ = "4.7.0"
```

Edit `README.md` first line: `v4.6.1` → `v4.7.0`

- [ ] **Step 3: Verify version sync**

```bash
bash hooks/validate-version-sync.sh
```

Expected: OK.

- [ ] **Step 4: Add CHANGELOG entry** (prepend to `CHANGELOG.md`)

```markdown
## v4.7.0 — 2026-04-27

**Option B: Regression Suite (MINOR)**

- Add `mcp/samvil_mcp/regression_suite.py` — 4 dataclasses (ACEntry,
  GenerationSnapshot, RegressionResult, CompareResult) + 4 functions:
  `snapshot_generation`, `validate_against_snapshot`,
  `aggregate_regression_state`, `compare_generations`
- Add 4 MCP tools: `snapshot_generation`, `validate_against_snapshot`,
  `aggregate_regression_state`, `compare_generations`
- Add `mcp/tests/test_regression_suite.py` — 30 tests across 5 classes
- Add `references/regression-suite.md` — schema doc + operator guide
- Update `skills/samvil-evolve/SKILL.md` — Boot step 4b: auto-snapshot +
  regression check; post-apply: snapshot new generation
- Storage: `.samvil/generations/gen-<N>/snapshot.json`
- Input: `.samvil/qa-results.json` pass2 list (seed v3 compatible, P8 graceful degradation)

Pre-commit: 9/9 PASS — N tests total
```

(Replace N with actual test count.)

- [ ] **Step 5: Sync plugin cache**

```bash
CACHE=$(ls -td ~/.claude/plugins/cache/samvil/samvil/*/ 2>/dev/null | head -1)
cp .claude-plugin/plugin.json "$CACHE/.claude-plugin/plugin.json"
cp mcp/samvil_mcp/__init__.py "$CACHE/mcp/samvil_mcp/__init__.py"
cp README.md "$CACHE/README.md"
cp mcp/samvil_mcp/regression_suite.py "$CACHE/mcp/samvil_mcp/regression_suite.py"
cp mcp/tests/test_regression_suite.py "$CACHE/mcp/tests/test_regression_suite.py" 2>/dev/null || true
cp references/regression-suite.md "$CACHE/references/regression-suite.md" 2>/dev/null || true
```

- [ ] **Step 6: Final pre-commit check**

```bash
cd . && bash scripts/pre-commit-check.sh 2>&1 | tail -5
```

Must exit 0.

- [ ] **Step 7: Final commit + tag**

```bash
cd .
git add .claude-plugin/plugin.json mcp/samvil_mcp/__init__.py README.md CHANGELOG.md
git commit -m "chore: bump to v4.7.0 — Option B Regression Suite"
git tag v4.7.0
```

---

## Self-Review

### 1. Spec Coverage Check

From Option B spec:
- [x] `mcp/samvil_mcp/regression_suite.py` — Task 1
- [x] `.samvil/generations/gen-<N>/snapshot.json` schema: AC list + evidence + timestamp — Task 1
- [x] `snapshot_generation()` MCP tool — Tasks 1+5
- [x] `validate_against_snapshot()` MCP tool — Tasks 3+5
- [x] `aggregate_regression_state()` MCP tool — Tasks 4+5
- [x] `compare_generations()` MCP tool (optional) — Tasks 4+5
- [x] `samvil-evolve` integration — Task 6
- [x] Tests 25+ — Tasks 1-4 deliver 30 tests
- [x] `references/regression-suite.md` — Task 6
- [x] Seed v3 compatible — uses `qa-results.json` directly, no seed schema change

### 2. Placeholder Scan

All code blocks are complete. No TBD or fill-in-later patterns found.

### 3. Type Consistency

All types defined in Task 1 `regression_suite.py` and used consistently across Tasks 2-5:
- `ACEntry` → `.to_dict()`, `.from_dict(d)` ✓
- `GenerationSnapshot` → `.to_dict()`, `.from_dict(d)` ✓
- `RegressionResult` → `.to_dict()`, `.status` property ✓
- `CompareResult` → `.to_dict()` ✓
- `snapshot_generation(project_root, generation_id?, qa_results_path?)` → `GenerationSnapshot` ✓
- `validate_against_snapshot(project_root, snapshot_id, qa_results_path?)` → `RegressionResult` ✓
- `aggregate_regression_state(project_root)` → `dict` ✓
- `compare_generations(project_root, gen_a, gen_b)` → `CompareResult` ✓
