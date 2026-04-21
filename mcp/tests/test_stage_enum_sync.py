"""v3-009: Ensure Stage enum in models.py matches references/state-schema.json.

Historically ``council`` and ``design`` were missing from the enum, so
``save_event(stage="council")`` silently routed to a fallback. This test
pins the sync so future edits to either side can't drift apart unnoticed.
"""
from __future__ import annotations

import json
from pathlib import Path

from samvil_mcp.models import Stage

SCHEMA_PATH = Path(__file__).parents[2] / "references" / "state-schema.json"


def _schema_stage_values() -> set[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    enum_list = schema["properties"]["current_stage"]["enum"]
    return set(enum_list)


def _enum_values() -> set[str]:
    return {e.value for e in Stage}


def test_enum_is_superset_of_schema() -> None:
    """Every state in the schema must exist in the Python enum."""
    schema_vals = _schema_stage_values()
    enum_vals = _enum_values()
    missing = schema_vals - enum_vals
    assert not missing, (
        f"Stage enum missing schema values: {sorted(missing)}. "
        "Update mcp/samvil_mcp/models.py Stage enum to match."
    )


def test_council_and_design_are_present() -> None:
    """Regression guard for v3-009 — these two were historically absent."""
    assert "council" in _schema_stage_values()
    assert "design" in _schema_stage_values()
    assert "council" in _enum_values()
    assert "design" in _enum_values()


def test_every_schema_stage_is_valid_enum_call() -> None:
    for value in _schema_stage_values():
        # Must not raise
        assert Stage(value).value == value
