"""Shared small utilities for samvil_mcp modules.

Keep this module dependency-free (stdlib only) — it is imported by
build/qa/orchestrator paths that must never fail at import time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_safe(path: Path) -> dict[str, Any] | None:
    """Best-effort JSON read. Returns None on missing/invalid file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    """Best-effort JSON read. Returns {} on missing/invalid/non-dict."""
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
