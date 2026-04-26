"""Validate the suggestions_v2 schema introduced in v3-021.

The retro skill writes each new feedback-log entry with a `suggestions_v2`
list containing dicts. This test pins the required fields and priority enum
so future drift gets caught by CI.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = {
    "id",
    "priority",
    "component",
    "name",
    "problem",
    "fix",
    "expected_impact",
}

OPTIONAL_FIELDS = {"source", "sprint", "risk_of_worse"}

PRIORITY_VALUES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "BENEFIT"}

FEEDBACK_LOG = Path(__file__).parent / "fixtures" / "harness-feedback.json"


def _load_log() -> list[dict]:
    assert FEEDBACK_LOG.exists(), f"Expected {FEEDBACK_LOG} to exist"
    with FEEDBACK_LOG.open(encoding="utf-8") as f:
        return json.load(f)


def test_feedback_log_is_array() -> None:
    data = _load_log()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_suggestions_v2_fields_are_well_formed() -> None:
    data = _load_log()
    for entry in data:
        items = entry.get("suggestions_v2") or []
        if not items:
            continue  # legacy-only entries are fine
        for it in items:
            missing = REQUIRED_FIELDS - set(it.keys())
            assert not missing, (
                f"Entry {entry.get('run_id')} suggestion {it.get('id')} "
                f"missing required fields: {missing}"
            )
            assert it["priority"] in PRIORITY_VALUES, (
                f"Entry {entry.get('run_id')} suggestion {it.get('id')} has "
                f"invalid priority {it['priority']!r}"
            )
            # ID format: vX-NNN (major version prefix)
            iid = it["id"]
            assert iid.startswith("v") and "-" in iid, (
                f"ID {iid!r} does not follow v<major>-<NNN> pattern"
            )


def test_suggestion_ids_are_unique_within_a_run() -> None:
    data = _load_log()
    for entry in data:
        items = entry.get("suggestions_v2") or []
        ids = [it["id"] for it in items]
        assert len(ids) == len(set(ids)), (
            f"Duplicate IDs within entry {entry.get('run_id')}: {ids}"
        )


def test_no_tbd_in_fix_or_impact() -> None:
    """New retro writes must not leave TBD placeholders."""
    data = _load_log()
    for entry in data:
        for it in entry.get("suggestions_v2") or []:
            # JTBD is an allowed acronym; check for standalone 'TBD'
            for field in ("fix", "expected_impact"):
                value = it.get(field, "") or ""
                tokens = value.replace(",", " ").replace(".", " ").split()
                assert "TBD" not in tokens, (
                    f"Entry {entry.get('run_id')} suggestion {it['id']} "
                    f"still has TBD placeholder in {field}: {value[:120]!r}"
                )


def test_legacy_suggestions_never_grows_beyond_entry_six() -> None:
    """Entries created after v3.0.1 must not write to legacy string list."""
    data = _load_log()
    for entry in data[6:]:  # index 6 = 7th entry onward
        legacy = entry.get("suggestions") or []
        # Post-v3.0.1 entries either (a) use suggestions_v2 only, or
        # (b) were written by an older retro (legacy still allowed historically).
        # New retro skill must produce entries where suggestions_v2 is populated
        # OR suggestions is empty. It must never produce entries with
        # suggestions populated *and* suggestions_v2 empty.
        v2 = entry.get("suggestions_v2") or []
        if legacy and not v2:
            # entry #7 (samvil-2026-04-20-007) predates schema fix — tolerated
            # as historical. Flag but don't fail.
            assert entry.get("run_id") == "samvil-2026-04-20-007", (
                f"Entry {entry.get('run_id')} uses legacy-only schema; new "
                "retro must write suggestions_v2."
            )
