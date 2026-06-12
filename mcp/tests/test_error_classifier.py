"""Tests for transient/permanent failure classification (v4.30 W2.3)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from samvil_mcp.error_classifier import (
    DEFAULT_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    classify_failure,
)
from samvil_mcp.server import classify_build_failure


def test_npm_network_error_is_transient() -> None:
    v = classify_failure("npm ERR! network request to https://registry failed")
    assert v.failure_class == "transient"
    assert "npm_network" in v.matched_transient
    assert v.counts_against_circuit_breaker is False
    assert v.backoff_seconds == DEFAULT_BACKOFF_SECONDS


def test_typescript_error_is_permanent() -> None:
    v = classify_failure("src/app.tsx(3,1): error TS2304: Cannot find name 'x'")
    assert v.failure_class == "permanent"
    assert v.counts_against_circuit_breaker is True
    assert v.backoff_seconds == 0


def test_permanent_override_wins_over_transient_hit() -> None:
    log = "warn 503 service unavailable while fetching\nerror TS1005: ';' expected"
    v = classify_failure(log)
    assert v.failure_class == "permanent"
    assert "typescript" in v.matched_permanent


def test_unknown_error_defaults_to_permanent() -> None:
    v = classify_failure("something exploded for no clear reason")
    assert v.failure_class == "permanent"


def test_empty_log_is_permanent() -> None:
    assert classify_failure("").failure_class == "permanent"


def test_backoff_scales_with_attempt_and_caps() -> None:
    assert classify_failure("ETIMEDOUT", attempt=2).backoff_seconds == 60
    assert classify_failure("ETIMEDOUT", attempt=99).backoff_seconds == MAX_BACKOFF_SECONDS


def test_transient_examples() -> None:
    for log in (
        "connect ECONNREFUSED 127.0.0.1:443",
        "read ECONNRESET",
        "getaddrinfo ENOTFOUND registry.npmjs.org",
        "socket hang up",
        "fetch failed",
        "429 Too Many Requests",
        "registry request timed out",
    ):
        assert classify_failure(log).failure_class == "transient", log


def test_mcp_tool_reads_log_tail(tmp_path: Path) -> None:
    samvil = tmp_path / ".samvil"
    samvil.mkdir()
    (samvil / "build.log").write_text("npm ERR! network socket hang up\n")
    result = json.loads(
        asyncio.run(classify_build_failure(str(tmp_path), attempt=1))
    )
    assert result["failure_class"] == "transient"
    assert result["counts_against_circuit_breaker"] is False


def test_mcp_tool_missing_log_is_permanent(tmp_path: Path) -> None:
    result = json.loads(asyncio.run(classify_build_failure(str(tmp_path))))
    assert result["failure_class"] == "permanent"
