"""Canonical schema and runtime verifier must agree."""

from __future__ import annotations

import json
from pathlib import Path


def test_every_verify_schema_requires_command() -> None:
    repo = Path(__file__).resolve().parents[2]
    schema = json.loads((repo / "references" / "seed-schema.json").read_text())
    one_of = schema["properties"]["acceptance_criteria"]["items"]["oneOf"]
    verify_schemas = [
        branch["properties"]["verify"]
        for branch in one_of
        if isinstance(branch, dict)
        and isinstance(branch.get("properties"), dict)
        and "verify" in branch["properties"]
    ]

    assert len(verify_schemas) == 2
    assert all(verify.get("required") == ["command"] for verify in verify_schemas)
