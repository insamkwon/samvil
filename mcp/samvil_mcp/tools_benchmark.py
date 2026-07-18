"""External benchmark MCP tool registrations."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable


def register_benchmark_tools(
    mcp: Any,
    log_mcp_health: Callable[..., None],
) -> None:
    """Register the four tools backing the samvil-benchmark skill."""

    @mcp.tool()
    async def benchmark_fetch_target(url: str, timeout: float = 5.0) -> str:
        """Fetch a remote changelog and extract the latest release sections."""
        try:
            from .benchmark import fetch_external_changelog as _fetch

            result = await asyncio.to_thread(_fetch, url=url, timeout=timeout)
            log_mcp_health(
                "ok" if result.get("ok") else "fail",
                "benchmark_fetch_target",
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log_mcp_health("fail", "benchmark_fetch_target", str(e))
            return json.dumps({"ok": False, "error": str(e)})

    @mcp.tool()
    async def benchmark_classify_items(
        items_json: str,
        already_have_json: str = "",
        rejected_json: str = "",
    ) -> str:
        """Classify changelog items into already-have, rejected, and gaps."""
        try:
            from .benchmark import classify_changelog_items as _classify

            items = json.loads(items_json) if items_json else []
            already_have = json.loads(already_have_json) if already_have_json else []
            rejected = json.loads(rejected_json) if rejected_json else []
            result = _classify(
                items=items,
                samvil_already_have=already_have,
                samvil_rejected=rejected,
            )
            log_mcp_health(
                "ok" if result.get("ok") else "fail",
                "benchmark_classify_items",
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log_mcp_health("fail", "benchmark_classify_items", str(e))
            return json.dumps({"ok": False, "error": str(e)})

    @mcp.tool()
    async def benchmark_append_gap(
        gap_json: str,
        target_name: str,
        target_url: str,
        feedback_log_path: str,
    ) -> str:
        """Render a benchmark gap and append its deduplicated feedback entry."""
        try:
            from .benchmark import append_gap_to_feedback_log as _append
            from .benchmark import render_gap_entry as _render

            gap = json.loads(gap_json) if gap_json else {}
            entry = _render(
                gap=gap,
                target_name=target_name,
                target_url=target_url,
            )
            result = _append(
                gap_entry=entry,
                feedback_log_path=feedback_log_path,
            )
            log_mcp_health(
                "ok" if result.get("ok") else "fail",
                "benchmark_append_gap",
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log_mcp_health("fail", "benchmark_append_gap", str(e))
            return json.dumps({"ok": False, "error": str(e)})

    @mcp.tool()
    async def benchmark_load_targets(config_path: str = "") -> str:
        """Load the benchmark target registry and optional user overrides."""
        try:
            from .benchmark import load_benchmark_targets as _load

            result = _load(config_path=(config_path or None))
            log_mcp_health(
                "ok" if result.get("ok") else "fail",
                "benchmark_load_targets",
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log_mcp_health("fail", "benchmark_load_targets", str(e))
            return json.dumps({"ok": False, "error": str(e)})
