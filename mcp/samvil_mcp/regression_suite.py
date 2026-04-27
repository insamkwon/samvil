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
from typing import Any


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


def _gen_sort_key(p: Path) -> int:
    parts = p.name.split("-")
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0


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
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    except OSError:
        pass  # return snap even if write fails — P8 graceful degradation
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

    try:
        snap = GenerationSnapshot.from_dict(json.loads(snap_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return RegressionResult(
            snapshot_id=snapshot_id,
            checked_at=datetime.now(timezone.utc).isoformat(),
            total_checked=0,
            passing=0,
            regressed=0,
            new_passes=0,
            regressed_ids=[],
        )
    current = {a.get("id", ""): a.get("verdict", "") for a in _load_all_acs(project_root, qa_results_path)}

    regressed_ids = [
        ac.id for ac in snap.acs
        if ac.verdict == "PASS" and current.get(ac.id, "FAIL") != "PASS"
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
    for gen_dir in sorted(gens_dir.iterdir(), key=_gen_sort_key):
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
        try:
            snap_a = GenerationSnapshot.from_dict(json.loads(path_a.read_text(encoding="utf-8")))
            snap_a_acs = {ac.id: ac.verdict for ac in snap_a.acs}
        except (json.JSONDecodeError, OSError):
            pass  # treat as empty — graceful degradation

    if path_b.exists():
        try:
            snap_b = GenerationSnapshot.from_dict(json.loads(path_b.read_text(encoding="utf-8")))
            snap_b_acs = {ac.id: ac.verdict for ac in snap_b.acs}
        except (json.JSONDecodeError, OSError):
            pass

    all_ids = set(snap_a_acs) | set(snap_b_acs)
    added = [id for id in all_ids if id in snap_b_acs and id not in snap_a_acs]
    removed = [id for id in all_ids if id in snap_a_acs and id not in snap_b_acs]
    changed = [
        id for id in all_ids
        if id in snap_a_acs and id in snap_b_acs and snap_a_acs[id] != snap_b_acs[id]
    ]

    return CompareResult(gen_a=gen_a, gen_b=gen_b, added=sorted(added), removed=sorted(removed), changed=sorted(changed))
