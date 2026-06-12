"""health_check hook-health aggregation tests (v4.30 W1.2).

Hooks append entries with source="hook" to ~/.samvil/mcp-health.jsonl.
health_check must count only hook failures from the last 24h.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samvil_mcp.server import health_check


def _write_health(home: Path, entries: list[dict]) -> None:
    samvil = home / ".samvil"
    samvil.mkdir(parents=True, exist_ok=True)
    with (samvil / "mcp-health.jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_counts_only_recent_hook_failures(isolated_home: Path) -> None:
    now = datetime.now(timezone.utc)
    _write_health(
        isolated_home,
        [
            # counted: hook fail within 24h
            {
                "status": "fail",
                "tool": "hook:stage-start",
                "error": "recent fail",
                "timestamp": now.isoformat(),
                "source": "hook",
            },
            # NOT counted: older than 24h
            {
                "status": "fail",
                "tool": "hook:stage-end",
                "error": "old fail",
                "timestamp": (now - timedelta(hours=30)).isoformat(),
                "source": "hook",
            },
            # NOT counted: hook ok
            {
                "status": "ok",
                "tool": "hook:stage-start",
                "error": "",
                "timestamp": now.isoformat(),
                "source": "hook",
            },
            # NOT counted: server-side fail (no source=hook)
            {
                "status": "fail",
                "tool": "create_session",
                "error": "not a hook",
                "timestamp": now.isoformat(),
            },
        ],
    )
    result = json.loads(asyncio.run(health_check()))
    assert result["hook_failures_24h"] == 1
    assert result["last_hook_failure"]["error"] == "recent fail"
    assert "Hooks ⚠️ 1 fail(24h)" in result["summary"]


def test_no_health_file_means_hooks_green(isolated_home: Path) -> None:
    result = json.loads(asyncio.run(health_check()))
    assert result["hook_failures_24h"] == 0
    assert result["last_hook_failure"] is None
    assert "Hooks ✅" in result["summary"]


def test_malformed_lines_are_skipped(isolated_home: Path) -> None:
    now = datetime.now(timezone.utc)
    samvil = isolated_home / ".samvil"
    samvil.mkdir(parents=True, exist_ok=True)
    with (samvil / "mcp-health.jsonl").open("w", encoding="utf-8") as f:
        f.write("not json at all\n")
        f.write(
            json.dumps(
                {
                    "status": "fail",
                    "tool": "hook:stage-start",
                    "error": "bad ts",
                    "timestamp": "not-a-date",
                    "source": "hook",
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "status": "fail",
                    "tool": "hook:stage-end",
                    "error": "good",
                    "timestamp": now.isoformat(),
                    "source": "hook",
                }
            )
            + "\n"
        )
    result = json.loads(asyncio.run(health_check()))
    assert result["hook_failures_24h"] == 1
    assert result["last_hook_failure"]["error"] == "good"
